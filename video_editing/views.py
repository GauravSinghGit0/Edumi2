import os
import shutil
import uuid
import json
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.http import FileResponse, JsonResponse, HttpResponseForbidden, StreamingHttpResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import ffmpeg_utils
from .forms import (
    VideoUploadForm, TrimForm, VolumeForm, MergeForm,
    TextOverlayForm, SpeedForm, RotateForm, ResizeForm, FadeForm,
    BackgroundAudioForm,
)
from .models import VideoProject, EditOperation, ProjectAsset


def serve_media_ranges(request, path):
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.exists(file_path):
        raise Http404("File not found")

    file_size = os.path.getsize(file_path)
    range_header = request.META.get('HTTP_RANGE', '').strip()
    
    def file_iterator(fn, offset, length):
        with open(fn, 'rb') as f:
            f.seek(offset)
            remaining = length
            while remaining > 0:
                chunk_size = min(remaining, 65536)
                data = f.read(chunk_size)
                if not data:
                    break
                remaining -= len(data)
                yield data

    if range_header:
        match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            start = int(match.group(1))
            end = match.group(2)
            end = int(end) if end else file_size - 1
            
            if start >= file_size:
                return StreamingHttpResponse(status=416)
                
            length = end - start + 1
            response = StreamingHttpResponse(file_iterator(file_path, start, length), status=206, content_type='video/mp4')
            response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
            response['Accept-Ranges'] = 'bytes'
            response['Content-Length'] = str(length)
            return response

    response = StreamingHttpResponse(file_iterator(file_path, 0, file_size), content_type='video/mp4')
    response['Accept-Ranges'] = 'bytes'
    response['Content-Length'] = str(file_size)
    return response


# ---------------------------------------------------------------------------
# Project list / upload (triggered reload check)
# ---------------------------------------------------------------------------

@login_required
def project_list(request):
    if request.method == "POST":
        form = VideoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            project = form.save(commit=False)
            project.owner = request.user
            # Set initial ready status so the editor can load immediately
            project.status = "ready"
            if not project.title or not project.title.strip():
                orig_filename = request.FILES["original_file"].name
                project.title = os.path.splitext(orig_filename)[0]
            project.save()

            # Create the upload operation entry
            EditOperation.objects.create(
                project=project,
                operation_type="upload",
                description=f"Uploaded {project.original_file.name.split('/')[-1]}",
            )
            
            # Start background metadata extraction task with fallback
            try:
                from .tasks import extract_metadata_and_proxies_task
                extract_metadata_and_proxies_task.delay(project.id)
            except Exception:
                try:
                    meta = ffmpeg_utils.get_metadata(project.original_file.path)
                    project.duration_seconds = meta.get("duration", 0.0)
                    project.width = meta.get("width", 1920)
                    project.height = meta.get("height", 1080)
                    project.has_audio = meta.get("has_audio", True)
                    project.status = "ready"
                    orig_filename = os.path.basename(project.original_file.name)
                    project.clips_json = json.dumps([{"title": orig_filename, "duration": meta.get("duration", 0.0)}])
                    project.save()
                except Exception:
                    pass

            
            messages.success(request, "Video uploaded. Editor is loading...")
            return redirect("project_detail", pk=project.pk)
    else:
        form = VideoUploadForm()
    
    projects = VideoProject.objects.filter(owner=request.user)
    return render(request, "video_editing/project_list.html", {"projects": projects, "form": form})


def _get_owned_project(request, pk):
    project = get_object_or_404(VideoProject, pk=pk)
    if project.owner_id != request.user.id:
        return None
    return project


def convert_legacy_project_to_timeline(project):
    import re
    state = {
        "trim": {
            "start": project.trim_start or 0.0,
            "end": project.trim_end or project.duration_seconds or 0.0,
            "mode": "extract",
            "fade_in": False,
            "fade_out": False
        },
        "speed": 1.0,
        "audio": {
            "volume": 1.0,
            "muted": not project.has_audio
        },
        "text_overlays": [],
        "background_audios": [],
        "resize": None,
        "effects": {
            "grayscale": False,
            "rotate": 0,
            "fade": None
        }
    }
    
    try:
        clips = json.loads(project.clips_json) if project.clips_json else []
    except Exception:
        clips = []
    
    normalized_clips = []
    acc = 0.0
    for clip in clips:
        dur = float(clip.get("duration", 0.0))
        normalized_clips.append({
            "title": clip.get("title", "Clip"),
            "start": acc,
            "end": acc + dur,
            "trimStart": acc,
            "trimEnd": acc + dur,
            "duration": dur
        })
        acc += dur
    state["clips"] = normalized_clips

    ops = project.operations.filter(active=True).order_by('created_at')
    for op in ops:
        op_type = op.operation_type
        desc = op.description or ""
        
        if op_type == "grayscale":
            state["effects"]["grayscale"] = True
        elif op_type == "rotate":
            deg = 0
            if op.parameters and "degrees" in op.parameters:
                deg = int(op.parameters["degrees"])
            else:
                match = re.search(r'(\d+)', desc)
                if match:
                    deg = int(match.group(1))
            state["effects"]["rotate"] = deg
        elif op_type == "speed":
            speed = 1.0
            if op.parameters and "speed_factor" in op.parameters:
                speed = float(op.parameters["speed_factor"])
            else:
                match = re.search(r'(\d+\.?\d*)', desc)
                if match:
                    speed = float(match.group(1))
            state["speed"] = speed
        elif op_type == "volume":
            vol = 1.0
            if op.parameters and "volume" in op.parameters:
                vol = float(op.parameters["volume"])
            else:
                match = re.search(r'(\d+\.?\d*)', desc)
                if match:
                    vol = float(match.group(1))
            state["audio"]["volume"] = vol
        elif op_type == "mute":
            state["audio"]["muted"] = True
            state["audio"]["volume"] = 0.0
        elif op_type == "resize":
            w, h = None, None
            if op.parameters and "width" in op.parameters:
                w = op.parameters["width"]
                h = op.parameters["height"]
            else:
                match = re.search(r'(\d+)x(\d+)', desc)
                if match:
                    w, h = match.group(1), match.group(2)
            if w and h:
                state["resize"] = {"width": w, "height": h}
        elif op_type == "fade":
            fin, fout = 0.0, 0.0
            if op.parameters and "fade_in" in op.parameters:
                fin = op.parameters["fade_in"]
                fout = op.parameters["fade_out"]
            else:
                match = re.findall(r'(\d+\.?\d*)', desc)
                if len(match) >= 2:
                    fin, fout = float(match[0]), float(match[1])
            state["effects"]["fade"] = {"in": fin, "out": fout}
        elif op_type == "trim":
            state["trim"]["start"] = op.trim_start or 0.0
            state["trim"]["end"] = op.trim_end or project.duration_seconds or 0.0
            if "delete" in desc.lower() or (op.parameters and op.parameters.get("trim_mode") == "delete"):
                state["trim"]["mode"] = "delete"
            else:
                state["trim"]["mode"] = "extract"

    project.timeline_state = state
    project.save(update_fields=["timeline_state"])
    return state


@login_required
def project_detail(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden("You do not have access to this project.")

    # Ensure clips_json is initialized for existing projects
    if not project.clips_json or project.clips_json.strip() == "":
        orig_filename = os.path.basename(project.original_file.name)
        if len(orig_filename) > 32:
            orig_filename = project.title + ".mp4"
        project.clips_json = json.dumps([
            {"title": orig_filename, "duration": float(project.duration_seconds or 0.0)}
        ])
        project.save(update_fields=["clips_json"])

    # Convert legacy project metadata to timeline JSON if timeline_state is empty
    if project.timeline_state is None:
        convert_legacy_project_to_timeline(project)

    # Normalize state to dict/list and serialize to standard JSON string for template rendering
    state = project.timeline_state
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except Exception:
            pass
    timeline_state_json = json.dumps(state) if state else "null"

    context = {
        "project": project,
        "trim_form": TrimForm(),
        "volume_form": VolumeForm(),
        "merge_form": MergeForm(),
        "text_form": TextOverlayForm(),
        "speed_form": SpeedForm(),
        "rotate_form": RotateForm(),
        "resize_form": ResizeForm(),
        "fade_form": FadeForm(),
        "bg_audio_form": BackgroundAudioForm(),
        "operations": project.operations.filter(active=True)[:20],
        "has_redo": project.operations.filter(active=False).exists(),
        "timeline_state_json": timeline_state_json,
    }
    return render(request, "video_editing/project_detail.html", context)


# ---------------------------------------------------------------------------
# Helper: apply an ffmpeg operation result to the project + log it
# ---------------------------------------------------------------------------

def _apply_new_working_file(project, tmp_output_path, operation_type, description):
    """
    Take a temp file produced by ffmpeg_utils, attach it as the project's new
    current_file, refresh cached metadata, log the operation, and clean up.
    """
    try:
        # Clear Redo stack on new action
        inactive_ops = project.operations.filter(active=False)
        for inactive in list(inactive_ops):
            inactive.delete()

        filename = os.path.basename(tmp_output_path)
        with open(tmp_output_path, "rb") as f:
            # Delete old current_file from disk if it exists and isn't the original
            if project.current_file and project.current_file.name:
                old_path = project.current_file.path
                try:
                    project.current_file.delete(save=False)
                except Exception:
                    pass
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except OSError:
                        pass

            project.current_file.save(filename, File(f), save=False)

        try:
            meta = ffmpeg_utils.get_metadata(project.current_file.path)
            project.duration_seconds = meta["duration"]
            project.width = meta["width"]
            project.height = meta["height"]
            project.has_audio = meta["has_audio"]
            project.status = "ready"
            project.error_message = ""
            
            # Clamp trim bounds to new duration
            if project.trim_start > project.duration_seconds:
                project.trim_start = 0.0
            if project.trim_end is not None and project.trim_end > project.duration_seconds:
                project.trim_end = project.duration_seconds
        finally:
            project.save()

        op = EditOperation(
            project=project,
            operation_type=operation_type,
            description=description,
            trim_start=project.trim_start,
            trim_end=project.trim_end,
        )
        if tmp_output_path and os.path.exists(tmp_output_path):
            try:
                filename = os.path.basename(tmp_output_path)
                with open(tmp_output_path, "rb") as f:
                    op.video_file.save(filename, File(f), save=False)
            except Exception:
                pass
        op.save()
    finally:
        if os.path.exists(tmp_output_path):
            try:
                os.remove(tmp_output_path)
            except OSError:
                pass


def _insert_clip_to_sequence(project, asset_title, asset_duration, timestamp):
    try:
        clips = json.loads(project.clips_json) if project.clips_json else []
    except Exception:
        clips = []
    
    if not clips:
        orig_filename = project.title + ".mp4"
        clips = [{"title": orig_filename, "duration": project.duration_seconds or 0.0}]

    new_clips = []
    current_time = 0.0
    inserted = False
    
    for clip in clips:
        clip_dur = float(clip.get("duration", 0.0))
        clip_title = clip.get("title", "Clip")
        
        if inserted:
            new_clips.append(clip)
            continue
            
        if current_time <= timestamp < (current_time + clip_dur):
            # Split point is within this clip!
            split_offset = timestamp - current_time
            if split_offset <= 0.05:
                # Insert before this clip
                new_clips.append({"title": asset_title, "duration": asset_duration})
                new_clips.append(clip)
            elif (clip_dur - split_offset) <= 0.05:
                # Insert after this clip
                new_clips.append(clip)
                new_clips.append({"title": asset_title, "duration": asset_duration})
            else:
                # Split this clip!
                new_clips.append({"title": clip_title, "duration": round(split_offset, 2)})
                new_clips.append({"title": asset_title, "duration": asset_duration})
                new_clips.append({"title": clip_title, "duration": round(clip_dur - split_offset, 2)})
            inserted = True
        else:
            new_clips.append(clip)
            current_time += clip_dur
            
    if not inserted:
        # Append to the end
        new_clips.append({"title": asset_title, "duration": asset_duration})
        
    project.clips_json = json.dumps(new_clips)
    project.save(update_fields=["clips_json"])





@login_required
@require_POST
def op_trim(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    form = TrimForm(request.POST)
    if form.is_valid():
        start = form.cleaned_data["start_seconds"]
        end = form.cleaned_data["end_seconds"]
        try:
            tmp_out = ffmpeg_utils.trim(project.working_file.path, start, end)
            _apply_new_working_file(project, tmp_out, "trim", f"Trimmed ({start:.1f}s to {end:.1f}s)")
            messages.success(request, "Video trimmed successfully.")
        except Exception as e:
            messages.error(request, f"Trim failed: {str(e)}")
    else:
        messages.error(request, "Invalid trim parameters.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_text(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    form = TextOverlayForm(request.POST)
    if form.is_valid():
        text = form.cleaned_data["text"]
        pos = form.cleaned_data["position"]
        font_size = form.cleaned_data["font_size"]
        color = form.cleaned_data["color"]
        start = form.cleaned_data.get("start_seconds")
        end = form.cleaned_data.get("end_seconds")
        try:
            tmp_out = ffmpeg_utils.add_text_overlay(
                project.working_file.path, text=text, position=pos,
                font_size=font_size, color=color, start_seconds=start, end_seconds=end
            )
            _apply_new_working_file(project, tmp_out, "text_overlay", f"Added text overlay: '{text}'")
            messages.success(request, "Text overlay added.")
        except Exception as e:
            messages.error(request, f"Text overlay failed: {str(e)}")
    else:
        messages.error(request, "Invalid text overlay parameters.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_bg_audio(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    form = BackgroundAudioForm(request.POST, request.FILES)
    if form.is_valid():
        audio_file = form.cleaned_data["audio_file"]
        start = form.cleaned_data.get("start_seconds") or 0.0
        end = form.cleaned_data.get("end_seconds")
        bg_vol = form.cleaned_data.get("bg_volume") or 0.5
        vid_vol = form.cleaned_data.get("video_volume") or 1.0
        
        tmp_dir = os.path.join(settings.MEDIA_ROOT, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        audio_tmp = os.path.join(tmp_dir, f"bg_{uuid.uuid4().hex}_{audio_file.name}")
        with open(audio_tmp, "wb") as f:
            for chunk in audio_file.chunks():
                f.write(chunk)
        try:
            tmp_out = ffmpeg_utils.add_background_audio(
                project.working_file.path, audio_tmp,
                start_seconds=start, end_seconds=end,
                bg_volume=bg_vol, video_volume=vid_vol
            )
            _apply_new_working_file(project, tmp_out, "merge", f"Added background audio '{audio_file.name}'")
            messages.success(request, "Background audio applied.")
        except Exception as e:
            messages.error(request, f"Background audio failed: {str(e)}")
        finally:
            if os.path.exists(audio_tmp):
                try: os.remove(audio_tmp)
                except OSError: pass
    else:
        messages.error(request, "Invalid background audio parameters.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_rotate(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    form = RotateForm(request.POST)
    if form.is_valid():
        deg = int(form.cleaned_data["degrees"])
        try:
            tmp_out = ffmpeg_utils.rotate_video(project.working_file.path, degrees=deg)
            _apply_new_working_file(project, tmp_out, "rotate", f"Rotated {deg}°")
            messages.success(request, f"Rotated video by {deg}°.")
        except Exception as e:
            messages.error(request, f"Rotation failed: {str(e)}")
    else:
        messages.error(request, "Invalid rotation angle.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_resize(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    form = ResizeForm(request.POST)
    if form.is_valid():
        w = form.cleaned_data["width"]
        h = form.cleaned_data["height"]
        try:
            tmp_out = ffmpeg_utils.resize_video(project.working_file.path, width=w, height=h)
            _apply_new_working_file(project, tmp_out, "resize", f"Resized to {w}x{h}")
            messages.success(request, f"Resized video to {w}x{h}.")
        except Exception as e:
            messages.error(request, f"Resize failed: {str(e)}")
    else:
        messages.error(request, "Invalid resolution parameters.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_grayscale(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    try:
        tmp_out = ffmpeg_utils.apply_grayscale(project.working_file.path)
        _apply_new_working_file(project, tmp_out, "grayscale", "Applied grayscale filter")
        messages.success(request, "Grayscale filter applied.")
    except Exception as e:
        messages.error(request, f"Grayscale filter failed: {str(e)}")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_fade(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    form = FadeForm(request.POST)
    if form.is_valid():
        fin = form.cleaned_data["fade_in_seconds"]
        fout = form.cleaned_data["fade_out_seconds"]
        try:
            tmp_out = ffmpeg_utils.apply_fade(project.working_file.path, fade_in_seconds=fin, fade_out_seconds=fout)
            _apply_new_working_file(project, tmp_out, "fade", f"Applied fade in ({fin}s) & fade out ({fout}s)")
            messages.success(request, "Fade effects applied.")
        except Exception as e:
            messages.error(request, f"Fade effect failed: {str(e)}")
    else:
        messages.error(request, "Invalid fade parameters.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_speed(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    form = SpeedForm(request.POST)
    if form.is_valid():
        spf = form.cleaned_data["speed_factor"]
        try:
            tmp_out = ffmpeg_utils.change_speed(project.working_file.path, speed_factor=spf)
            _apply_new_working_file(project, tmp_out, "speed", f"Changed speed to {spf}x")
            messages.success(request, f"Speed changed to {spf}x.")
        except Exception as e:
            messages.error(request, f"Speed change failed: {str(e)}")
    else:
        messages.error(request, "Invalid speed factor.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_split(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    try:
        split_at = float(request.POST.get("split_at", 0.0))
        _insert_clip_to_sequence(project, "Split Clip", 5.0, split_at)
        messages.success(request, f"Split timeline clip at {split_at:.2f}s.")
    except Exception as e:
        messages.error(request, f"Split failed: {str(e)}")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_reset(request, pk):
    """Discard all edits and revert current_file back to the original upload."""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()

    if project.current_file and project.current_file.name:
        old_path = project.current_file.path
        try:
            project.current_file.delete(save=False)
        except Exception:
            pass
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    meta = ffmpeg_utils.get_metadata(project.original_file.path)
    project.duration_seconds = meta["duration"]
    project.width = meta["width"]
    project.height = meta["height"]
    project.has_audio = meta["has_audio"]
    project.status = "ready"
    project.error_message = ""
    
    # Reset clips_json
    orig_filename = os.path.basename(project.original_file.name)
    if len(orig_filename) > 32:
        orig_filename = project.title + ".mp4"
    project.clips_json = json.dumps([
        {"title": orig_filename, "duration": meta["duration"]}
    ])
    project.save()

    EditOperation.objects.create(project=project, operation_type="reset", description="Reset to original upload")
    messages.success(request, "Project reset to the original uploaded video.")
    return redirect("project_detail", pk=pk)





@login_required
@require_POST
def project_delete(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    title = project.display_title
    for f in [project.original_file, project.current_file]:
        if f and f.name and os.path.exists(f.path):
            try:
                os.remove(f.path)
            except OSError:
                pass
    project.delete()
    messages.success(request, f"Project '{title}' deleted.")
    return redirect("project_list")


@login_required
def project_download(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    file_field = project.working_file
    response = FileResponse(open(file_field.path, "rb"), as_attachment=True,
                             filename=f"{project.display_title}{os.path.splitext(file_field.name)[1]}")
    return response


@login_required
def project_download_mkv(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    
    file_field = project.working_file
    if os.path.splitext(file_field.name)[1].lower() == ".mkv":
        response = FileResponse(open(file_field.path, "rb"), as_attachment=True,
                                 filename=f"{project.display_title}.mkv")
        return response
        
    try:
        tmp_mkv = ffmpeg_utils.convert_to_mkv(file_field.path)
        class TemporaryFileResponse(FileResponse):
            def __init__(self, filepath, *args, **kwargs):
                self._temp_filepath = filepath
                super().__init__(open(filepath, "rb"), *args, **kwargs)
                
            def close(self):
                super().close()
                if hasattr(self, "_temp_filepath") and os.path.exists(self._temp_filepath):
                    try:
                        os.remove(self._temp_filepath)
                    except OSError:
                        pass
                        
        response = TemporaryFileResponse(tmp_mkv, as_attachment=True, filename=f"{project.display_title}.mkv")
        return response
    except ffmpeg_utils.FFmpegError:
        messages.error(request, "Failed to convert video container to MKV format.")
        return redirect("project_detail", pk=pk)


@login_required
def project_status(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "forbidden"}, status=403)
    return JsonResponse({
        "status": project.status,
        "error_message": project.error_message,
        "duration_seconds": project.duration_seconds,
        "proxy_status": project.proxy_status,
        "proxy_url": project.proxy_url,
    })


@login_required
@require_POST
def export_project(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    # Save current timeline state in DB
    project.timeline_state = data
    if "clips" in data:
        project.clips_json = json.dumps(data["clips"])
    project.status = "processing"
    project.save()

    try:
        from .tasks import export_video_task
        # Queue the Celery task
        export_video_task.delay(project.id, data)
        messages.success(request, "Export started! Your video is being processed in the background.")
        from django.urls import reverse
        return JsonResponse({
            "status": "success", 
            "redirect_url": reverse("project_detail", args=[project.pk])
        })
    except Exception as e:
        project.status = "error"
        project.error_message = str(e)
        project.save()
        return JsonResponse({"status": "error", "error": str(e)}, status=500)





@login_required
@require_POST
def upload_audio_temp(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "forbidden"}, status=403)
        
    audio_file = request.FILES.get("audio_file")
    if not audio_file:
        return JsonResponse({"error": "no_file"}, status=400)
        
    tmp_dir = os.path.join(settings.MEDIA_ROOT, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    audio_tmp_path = os.path.join(tmp_dir, f"audio_{uuid.uuid4().hex}_{audio_file.name}")
    
    with open(audio_tmp_path, "wb") as dest:
        for chunk in audio_file.chunks():
            dest.write(chunk)
            
    return JsonResponse({
        "status": "success",
        "temp_path": audio_tmp_path,
        "filename": audio_file.name
    })


@login_required
@require_POST
def upload_asset(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "Forbidden"}, status=403)

    video_file = request.FILES.get("video_file")
    if not video_file:
        return JsonResponse({"error": "No file uploaded"}, status=400)

    asset = ProjectAsset.objects.create(
        project=project,
        file=video_file,
        title=video_file.name,
        filename=video_file.name
    )

    try:
        meta = ffmpeg_utils.get_metadata(asset.file.path)
        asset.duration_seconds = meta.get("duration", 0.0)
        asset.save(update_fields=["duration_seconds"])
    except Exception:
        pass

    return JsonResponse({
        "success": True,
        "asset": {
            "id": asset.id,
            "url": asset.file.url,
            "title": asset.display_title,
            "duration": asset.display_duration
        }
    })





@login_required
@require_POST
def publish_to_lecture(request, pk):
    """
    Publish the edited VideoProject back to its CameraRecording and set it to published.
    """
    from cameras.models import CameraRecording
    from django.core.files import File
    import os
    
    project = get_object_or_404(VideoProject, pk=pk)
    recording_id = request.GET.get('recording_id')
    
    if not recording_id:
        messages.error(request, "Recording ID missing. Cannot publish.")
        return redirect('project_detail', pk=pk)
        
    recording = get_object_or_404(CameraRecording, id=recording_id)
    
    if not (request.user.is_superuser or recording.teacher == request.user):
        messages.error(request, "Unauthorized to publish this recording.")
        return redirect('project_detail', pk=pk)
        
    try:
        edited_path = project.working_file.path
        filename = os.path.basename(edited_path)
        
        with open(edited_path, 'rb') as f:
            recording.video_file.save(filename, File(f), save=False)
            
        recording.is_published = True
        recording.recording_status = 'completed'
        
        try:
            if project.duration_seconds:
                from datetime import timedelta
                recording.duration = timedelta(seconds=project.duration_seconds)
        except Exception:
            pass
            
        recording.save()
        
        messages.success(request, f"Lecture '{recording.title}' has been successfully published!")
        return redirect('manage_recordings')
        
    except Exception as e:
        messages.error(request, f"Failed to publish lecture: {str(e)}")
        return redirect(f"{reverse('project_detail', args=[pk])}?recording_id={recording_id}")


# Keep Celery save_timeline / export_timeline stubs for safety
@login_required
@require_POST
def save_timeline(request, pk):
    project = get_object_or_404(VideoProject, pk=pk)
    try:
        data = json.loads(request.body)
        project.timeline_state = data
        project.save(update_fields=['timeline_state'])
        return JsonResponse({"status": "success"})
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)


@login_required
@require_POST
def export_timeline(request, pk):
    project = get_object_or_404(VideoProject, pk=pk)
    try:
        data = json.loads(request.body)
        project.timeline_state = data
        project.save(update_fields=['timeline_state'])
        project.status = "processing"
        project.save(update_fields=['status'])
        from .tasks import export_video_task
        # Pass the parsed dict (not the JSON string) — export_video_task /
        # compile_timeline_to_ffmpeg expect a dict with a "tracks" list.
        export_video_task.delay(project.id, data)
        return JsonResponse({"status": "processing"})
    except Exception as e:
        project.status = "error"
        project.error_message = str(e)
        project.save(update_fields=['status', 'error_message'])
        return JsonResponse({"error": str(e)}, status=500)

from django.views.decorators.csrf import csrf_exempt
from django.core.files import File

@csrf_exempt
@login_required
def chunked_upload_view(request):
    if request.method == 'POST':
        chunk = request.FILES.get('chunk')
        filename = request.POST.get('filename')
        chunk_index = int(request.POST.get('chunkIndex', 0))
        total_chunks = int(request.POST.get('totalChunks', 1))
        upload_id = request.POST.get('uploadId')
        
        if not all([chunk, filename, upload_id]):
            return JsonResponse({'success': False, 'error': 'Missing data'}, status=400)
            
        import os
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads', upload_id)
        os.makedirs(temp_dir, exist_ok=True)
        
        chunk_path = os.path.join(temp_dir, f'chunk_{chunk_index}')
        with open(chunk_path, 'wb+') as f:
            for data in chunk.chunks():
                f.write(data)
                
        if chunk_index == total_chunks - 1:
            # Final chunk received, assemble file
            final_file_path = os.path.join(temp_dir, filename)
            with open(final_file_path, 'wb+') as final_file:
                for i in range(total_chunks):
                    part_path = os.path.join(temp_dir, f'chunk_{i}')
                    with open(part_path, 'rb') as part:
                        final_file.write(part.read())
                    os.remove(part_path)
                    
            # Create VideoProject
            project = VideoProject.objects.create(
                owner=request.user,
                title=filename
            )
            with open(final_file_path, 'rb') as final_file:
                project.original_file.save(filename, File(final_file))
                
            project.proxy_status = 'pending'
            project.save()
            os.remove(final_file_path)
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass
            
            # Start proxy generation task
            try:
                from .tasks import generate_hls_proxy
                generate_hls_proxy.delay(project.id)
            except ImportError:
                pass
            
            return JsonResponse({'success': True, 'project_id': project.id})
            
        return JsonResponse({'success': True, 'message': 'Chunk received'})
        
    return JsonResponse({'success': False}, status=405)

@login_required
def proxy_status_view(request, pk):
    try:
        project = VideoProject.objects.get(pk=pk, owner=request.user)
        return JsonResponse({
            'status': project.proxy_status,
            'url': project.proxy_url
        })
    except VideoProject.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)