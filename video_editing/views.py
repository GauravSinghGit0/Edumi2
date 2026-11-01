import os
import math
import uuid
import json
import re
import shutil
import threading

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.http import FileResponse, JsonResponse, HttpResponseForbidden, Http404
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
from common.validators import (
    check_uploaded_file,
    sanitize_filename,
    get_file_extension,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_AUDIO_EXTENSIONS,
    MAX_VIDEO_SIZE,
    MAX_AUDIO_SIZE,
    MAX_IMAGE_SIZE,
    get_safe_temp_upload_dir,
)


@login_required
def serve_media_ranges(request, path):
    """
    Streaming media endpoint for video editor timelines.
    Consolidated into protected_media_serve to enforce global access controls.
    """
    from common.media_views import protected_media_serve
    return protected_media_serve(request, path)



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
                    project.save()
                    convert_legacy_project_to_timeline(project)
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
    if not request.user.is_superuser and project.owner_id != request.user.id:
        return None
    return project


def convert_legacy_project_to_timeline(project):
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
    
    orig_filename = os.path.basename(project.original_file.name) if project.original_file else "Clip"
    if len(orig_filename) > 32:
        orig_filename = (project.title or "Clip") + ".mp4"
    dur = float(project.duration_seconds or 0.0)
    if dur <= 0 and project.original_file:
        try:
            if os.path.exists(project.original_file.path):
                m = ffmpeg_utils.get_metadata(project.original_file.path)
                dur = float(m.get("duration", 0.0) or 0.0)
                if dur > 0:
                    project.duration_seconds = dur
                    project.width = m.get("width", project.width or 1920)
                    project.height = m.get("height", project.height or 1080)
                    project.has_audio = m.get("has_audio", True)
                    project.save(update_fields=["duration_seconds", "width", "height", "has_audio"])
        except Exception:
            pass
    
    normalized_clips = [{
        "title": orig_filename,
        "start": 0.0,
        "end": dur,
        "trimStart": 0.0,
        "trimEnd": dur,
        "duration": dur
    }]
    state["clips"] = normalized_clips

    if project.has_audio and dur > 0:
        state["background_audios"] = [{
            "name": f"Audio Stream — {orig_filename}",
            "filename": orig_filename,
            "path": project.original_file.path if project.original_file else "",
            "start": 0.0,
            "end": dur,
            "trimStart": 0.0,
            "trimEnd": dur,
            "bg_volume": 1.0,
            "video_volume": 1.0,
            "is_detached": True
        }]
        state["audio"]["muted"] = False

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



    # Convert legacy project metadata to timeline JSON if timeline_state is empty or clips duration is 0
    state = project.timeline_state
    clips = []
    if isinstance(state, dict):
        clips = state.get("clips") or state.get("video_clips") or []
        if not clips and isinstance(state.get("tracks"), list):
            v_track = next((t for t in state["tracks"] if t.get("type") == "video"), None)
            if v_track:
                clips = v_track.get("clips", [])
    first_clip_dur = float(clips[0].get("duration", 0.0)) if clips else 0.0
    if project.timeline_state is None or first_clip_dur <= 0.0:
        convert_legacy_project_to_timeline(project)

    # Normalize state to dict/list and serialize to standard JSON string for template rendering
    state = project.timeline_state
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except Exception:
            pass
    timeline_state_json = json.dumps(state) if state else "null"

    # Structured project config for client bootstrap
    operations_list = list(project.operations.filter(active=True)[:20])
    operations_data = [
        {
            "type": op.operation_type,
            "title": op.get_operation_type_display(),
            "description": op.description or "",
            "trim_start": op.trim_start or 0.0,
            "trim_end": op.trim_end or 0.0,
        }
        for op in operations_list
    ]

    clips_data = []
    if isinstance(state, dict):
        clips_data = state.get("clips") or state.get("video_clips") or []
        if not clips_data and isinstance(state.get("tracks"), list):
            v_track = next((t for t in state["tracks"] if t.get("type") == "video"), None)
            if v_track:
                clips_data = v_track.get("clips", [])
    if not clips_data and project.clips_json:
        try:
            clips_data = json.loads(project.clips_json)
        except Exception:
            clips_data = []

    project_config = {
        "projectId": str(project.pk),
        "statusUrl": reverse("project_status", args=[project.pk]),
        "filmstripUrl": reverse("project_filmstrip", args=[project.pk]),
        "waveformUrl": reverse("project_waveform", args=[project.pk]),
        "saveTimelineUrl": reverse("save_timeline", args=[project.pk]),
        "uploadAssetUrl": reverse("upload_asset", args=[project.pk]),
        "chunkedUploadUrl": reverse("chunked_upload"),
        "proxyStatusUrl": reverse("proxy_status", args=[project.pk]),
        "status": project.status,
        "hasAudio": project.has_audio,
        "trimStart": project.trim_start or 0.0,
        "trimEnd": project.trim_end,
        "height": project.height or 720,
        "duration": project.duration_seconds or 0.0,
        "proxyStatus": project.proxy_status,
        "proxyUrl": project.proxy_url or "",
        "timelineState": state,
        "clips": clips_data,
        "operations": operations_data,
    }

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
        "operations": operations_list,
        "has_redo": project.operations.filter(active=False).exists(),
        "timeline_state_json": timeline_state_json,
        "project_config": project_config,
    }
    return render(request, "video_editing/project_detail.html", context)


# ---------------------------------------------------------------------------
# Helper: apply an ffmpeg operation result to the project + log it
# ---------------------------------------------------------------------------

def _apply_new_working_file(project, tmp_output_path, operation_type, description, clear_proxies=True, update_metadata=True, save_operation_file=True):
    """
    Take a temp file produced by ffmpeg_utils or export, attach it as the project's new
    current_file, optionally refresh cached metadata, log the operation, and clean up.
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
                try:
                    is_orig = (
                        project.original_file
                        and project.original_file.name
                        and os.path.abspath(project.current_file.path) == os.path.abspath(project.original_file.path)
                    )
                except Exception:
                    is_orig = False

                if not is_orig:
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
            if update_metadata:
                meta = ffmpeg_utils.get_metadata(project.current_file.path)
                project.duration_seconds = meta["duration"]
                project.width = meta["width"]
                project.height = meta["height"]
                project.has_audio = meta["has_audio"]
            project.status = "ready"
            project.error_message = ""

            if clear_proxies:
                # Clear old proxies/filmstrip/waveform on destructive working file change
                proxy_dir = os.path.join(settings.MEDIA_ROOT, "proxies", str(project.owner_id), str(project.pk))
                if os.path.isdir(proxy_dir):
                    try:
                        shutil.rmtree(proxy_dir)
                    except OSError:
                        pass
                project.proxy_url = ""
                project.proxy_status = "none"

            # Clamp trim bounds to duration
            if project.duration_seconds:
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
        if save_operation_file and tmp_output_path and os.path.exists(tmp_output_path):
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
    state = project.timeline_state or {}
    clips = state.get("clips", [])
    
    if not clips:
        orig_filename = (project.title or "Clip") + ".mp4"
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
        
    acc = 0.0
    normalized_clips = []
    for c in new_clips:
        dur = float(c.get("duration", 0.0))
        normalized_clips.append({
            "title": c.get("title", "Clip"),
            "start": acc,
            "end": acc + dur,
            "trimStart": c.get("trimStart", 0.0),
            "trimEnd": c.get("trimEnd", dur),
            "duration": dur
        })
        acc += dur

    state["clips"] = normalized_clips
    project.timeline_state = state
    project.save(update_fields=["timeline_state"])





@login_required
@require_POST
def op_trim(request, pk):
    """Non-destructive trim: Only updates timeline state, no FFmpeg processing"""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    
    form = TrimForm(request.POST)
    if form.is_valid():
        start = form.cleaned_data["start_seconds"]
        end = form.cleaned_data["end_seconds"]
        
        # Update timeline state only - no video processing
        state = project.timeline_state or {}
        if 'trim' not in state:
            state['trim'] = {}
        
        state['trim']['start'] = start
        state['trim']['end'] = end
        state['trim']['mode'] = 'extract'
        
        project.timeline_state = state
        project.save(update_fields=['timeline_state'])
        
        # Log the operation without video file
        EditOperation.objects.create(
            project=project,
            operation_type="trim",
            description=f"Trimmed ({start:.1f}s to {end:.1f}s)",
            parameters={"start": start, "end": end}
        )
        
        messages.success(request, "Trim applied to timeline. Export to render final video.")
    else:
        messages.error(request, "Invalid trim parameters.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_text(request, pk):
    """Non-destructive text overlay: Only updates timeline state"""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    
    form = TextOverlayForm(request.POST)
    if form.is_valid():
        text = form.cleaned_data["text"]
        pos = form.cleaned_data["position"]
        font_size = form.cleaned_data["font_size"]
        color = form.cleaned_data["color"]
        start = form.cleaned_data.get("start_seconds") or 0
        end = form.cleaned_data.get("end_seconds") or project.duration_seconds
        
        # Update timeline state only
        state = project.timeline_state or {}
        if 'text_overlays' not in state:
            state['text_overlays'] = []
        
        state['text_overlays'].append({
            'text': text,
            'position': pos,
            'fontsize': font_size,
            'color': color,
            'start': start,
            'end': end
        })
        
        project.timeline_state = state
        project.save(update_fields=['timeline_state'])
        
        EditOperation.objects.create(
            project=project,
            operation_type="text_overlay",
            description=f"Added text overlay: '{text}'",
            parameters={'text': text, 'position': pos, 'fontsize': font_size, 'color': color}
        )
        
        messages.success(request, "Text overlay added to timeline. Export to render final video.")
    else:
        messages.error(request, "Invalid text overlay parameters.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_bg_audio(request, pk):
    """Non-destructive background audio: Only updates timeline state"""
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
        
        # Save uploaded audio file as ProjectAsset
        from .models import ProjectAsset
        asset = ProjectAsset.objects.create(
            project=project,
            asset_type='audio',
            file=audio_file,
            filename=audio_file.name
        )
        
        # Extract duration if possible
        try:
            meta = ffmpeg_utils.get_metadata(asset.file.path)
            asset.duration_seconds = meta.get('duration', 0)
            asset.save()
            if end is None:
                end = asset.duration_seconds
        except Exception:
            if end is None:
                end = project.duration_seconds or 10.0
        
        # Update timeline state only
        state = project.timeline_state or {}
        if 'background_audios' not in state:
            state['background_audios'] = []
        
        state['background_audios'].append({
            'name': audio_file.name,
            'filename': audio_file.name,
            'path': asset.file.path,
            'asset_id': asset.id,
            'start': start,
            'end': end,
            'trimStart': 0,
            'trimEnd': end - start,
            'bg_volume': bg_vol,
            'video_volume': vid_vol,
            'is_detached': False
        })
        
        project.timeline_state = state
        project.save(update_fields=['timeline_state'])
        
        EditOperation.objects.create(
            project=project,
            operation_type="merge",
            description=f"Added background audio '{audio_file.name}'",
            parameters={'filename': audio_file.name}
        )
        
        messages.success(request, "Background audio added to timeline. Export to render final video.")
    else:
        messages.error(request, "Invalid background audio parameters.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_rotate(request, pk):
    """Non-destructive rotation: Only updates timeline state"""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    
    form = RotateForm(request.POST)
    if form.is_valid():
        deg = int(form.cleaned_data["degrees"])
        
        # Update timeline state only
        state = project.timeline_state or {}
        if 'effects' not in state:
            state['effects'] = {}
        
        state['effects']['rotate'] = deg
        
        project.timeline_state = state
        project.save(update_fields=['timeline_state'])
        
        EditOperation.objects.create(
            project=project,
            operation_type="rotate",
            description=f"Rotated {deg}°",
            parameters={'degrees': deg}
        )
        
        messages.success(request, f"Rotation {deg}° added to timeline. Export to render final video.")
    else:
        messages.error(request, "Invalid rotation angle.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_resize(request, pk):
    """Non-destructive resize: Only updates timeline state"""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    
    form = ResizeForm(request.POST)
    if form.is_valid():
        w = form.cleaned_data["width"]
        h = form.cleaned_data["height"]
        
        # Update timeline state only
        state = project.timeline_state or {}
        state['resize'] = {'width': w, 'height': h}
        
        project.timeline_state = state
        project.save(update_fields=['timeline_state'])
        
        EditOperation.objects.create(
            project=project,
            operation_type="resize",
            description=f"Resized to {w}x{h}",
            parameters={'width': w, 'height': h}
        )
        
        messages.success(request, f"Resize to {w}x{h} added to timeline. Export to render final video.")
    else:
        messages.error(request, "Invalid resolution parameters.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_grayscale(request, pk):
    """Non-destructive grayscale: Only updates timeline state"""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    
    # Update timeline state only
    state = project.timeline_state or {}
    if 'effects' not in state:
        state['effects'] = {}
    
    state['effects']['grayscale'] = True
    
    project.timeline_state = state
    project.save(update_fields=['timeline_state'])
    
    EditOperation.objects.create(
        project=project,
        operation_type="grayscale",
        description="Applied grayscale filter"
    )
    
    messages.success(request, "Grayscale filter added to timeline. Export to render final video.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_fade(request, pk):
    """Non-destructive fade: Only updates timeline state"""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    
    form = FadeForm(request.POST)
    if form.is_valid():
        fin = form.cleaned_data["fade_in_seconds"]
        fout = form.cleaned_data["fade_out_seconds"]
        
        # Update timeline state only
        state = project.timeline_state or {}
        if 'effects' not in state:
            state['effects'] = {}
        
        state['effects']['fade'] = {'in': fin, 'out': fout}
        
        project.timeline_state = state
        project.save(update_fields=['timeline_state'])
        
        EditOperation.objects.create(
            project=project,
            operation_type="fade",
            description=f"Applied fade in ({fin}s) & fade out ({fout}s)",
            parameters={'fade_in': fin, 'fade_out': fout}
        )
        
        messages.success(request, "Fade effects added to timeline. Export to render final video.")
    else:
        messages.error(request, "Invalid fade parameters.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_speed(request, pk):
    """Non-destructive speed change: Only updates timeline state"""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    
    form = SpeedForm(request.POST)
    if form.is_valid():
        spf = form.cleaned_data["speed_factor"]
        
        # Update timeline state only
        state = project.timeline_state or {}
        state['speed'] = spf
        
        project.timeline_state = state
        project.save(update_fields=['timeline_state'])
        
        EditOperation.objects.create(
            project=project,
            operation_type="speed",
            description=f"Changed speed to {spf}x",
            parameters={'speed_factor': spf}
        )
        
        messages.success(request, f"Speed {spf}x added to timeline. Export to render final video.")
    else:
        messages.error(request, "Invalid speed factor.")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_split(request, pk):
    """Non-destructive split: Only updates timeline state clips array"""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    
    try:
        split_at = float(request.POST.get("split_at", 0.0))
        
        # Update timeline state only - split is handled by JavaScript
        # This endpoint just logs the operation
        EditOperation.objects.create(
            project=project,
            operation_type="trim",
            description=f"Split timeline at {split_at:.2f}s",
            parameters={'split_at': split_at}
        )
        
        messages.success(request, f"Timeline split at {split_at:.2f}s. Export to render final video.")
    except Exception as e:
        messages.error(request, f"Split failed: {str(e)}")
    return redirect("project_detail", pk=pk)


@login_required
@require_POST
def op_reset(request, pk):
    """Reset timeline to original state - clears all edits from timeline_state"""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()

    # Clear current_file if it exists (no longer needed in non-destructive system)
    if project.current_file and project.current_file.name:
        try:
            is_orig = (
                project.original_file
                and project.original_file.name
                and os.path.abspath(project.current_file.path) == os.path.abspath(project.original_file.path)
            )
        except Exception:
            is_orig = False

        if not is_orig:
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

    # Reset metadata to original
    try:
        meta = ffmpeg_utils.get_metadata(project.original_file.path)
        project.duration_seconds = meta["duration"]
        project.width = meta["width"]
        project.height = meta["height"]
        project.has_audio = meta["has_audio"]
    except Exception:
        pass
    
    project.status = "ready"
    project.error_message = ""
    
    # Reset timeline state to clean state
    convert_legacy_project_to_timeline(project)

    EditOperation.objects.create(
        project=project,
        operation_type="reset",
        description="Reset to original upload - cleared all timeline edits"
    )
    
    messages.success(request, "Project reset to original. All timeline edits have been cleared.")
    return redirect("project_detail", pk=pk)





@login_required
@require_POST
def project_delete(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    title = project.display_title

    # 1. Remove original_file and current_file from disk
    for f in [project.original_file, project.current_file]:
        if f and f.name:
            try:
                if os.path.exists(f.path):
                    os.remove(f.path)
            except (OSError, ValueError):
                pass

    # 2. Remove proxy directory (proxy.mp4, proxy.m3u8, waveform.json, filmstrip/, etc.)
    proxy_dir = os.path.join(settings.MEDIA_ROOT, "proxies", str(project.owner_id), str(project.pk))
    if os.path.isdir(proxy_dir):
        try:
            shutil.rmtree(proxy_dir)
        except OSError:
            pass

    # 3. Remove project asset files from disk
    for asset in project.assets.all():
        if asset.file and asset.file.name:
            try:
                if os.path.exists(asset.file.path):
                    os.remove(asset.file.path)
            except (OSError, ValueError):
                pass

    # 4. Remove temporary audio files uploaded for this project
    tmp_media_dir = os.path.abspath(os.path.join(settings.MEDIA_ROOT, "tmp"))
    if isinstance(project.timeline_state, dict):
        state = project.timeline_state
        candidate_paths = []
        for ac in state.get("audio_clips", []) + state.get("audioClips", []):
            if isinstance(ac, dict):
                candidate_paths.extend([ac.get("temp_path"), ac.get("path")])
        for track in state.get("tracks", []):
            if isinstance(track, dict) and track.get("type") == "audio":
                for clip in track.get("clips", []):
                    if isinstance(clip, dict):
                        candidate_paths.extend([clip.get("temp_path"), clip.get("path")])
        for p in candidate_paths:
            if p and isinstance(p, str):
                abs_p = os.path.abspath(p)
                if abs_p.startswith(tmp_media_dir) and os.path.isfile(abs_p):
                    try:
                        os.remove(abs_p)
                    except OSError:
                        pass

    # 5. Remove operation snapshot files from disk
    for op in project.operations.all():
        for field in [op.video_file, op.resource_file]:
            if field and field.name:
                try:
                    if os.path.exists(field.path):
                        os.remove(field.path)
                except (OSError, ValueError):
                    pass

    project.delete()
    messages.success(request, f"Project '{title}' deleted.")
    return redirect("project_list")


@login_required
def project_download(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()

    if project.status == "processing":
        messages.warning(request, "Export is currently processing. Please wait until rendering completes before downloading.")
        return redirect("project_detail", pk=pk)

    if project.has_unexported_edits:
        messages.warning(
            request,
            "You have unexported timeline edits. Please click 'Export' to render your changes before downloading."
        )
        return redirect("project_detail", pk=pk)

    file_field = project.exported_file or project.original_file
    if not file_field or not file_field.name or not os.path.exists(file_field.path):
        messages.error(request, "Video file not found.")
        return redirect("project_detail", pk=pk)

    response = FileResponse(open(file_field.path, "rb"), as_attachment=True,
                             filename=f"{project.display_title}{os.path.splitext(file_field.name)[1]}")
    return response


@login_required
def project_download_mkv(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()

    if project.status == "processing":
        messages.warning(request, "Export is currently processing. Please wait until rendering completes before downloading.")
        return redirect("project_detail", pk=pk)

    if project.has_unexported_edits:
        messages.warning(
            request,
            "You have unexported timeline edits. Please click 'Export' to render your changes before downloading."
        )
        return redirect("project_detail", pk=pk)

    file_field = project.exported_file or project.original_file
    if not file_field or not file_field.name or not os.path.exists(file_field.path):
        messages.error(request, "Video file not found.")
        return redirect("project_detail", pk=pk)

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
def save_timeline(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    # Validate and normalize timeline structure for export compatibility
    if not isinstance(data, dict):
        return JsonResponse({"error": "invalid_timeline_format"}, status=400)
    
    # Ensure tracks array exists and is properly structured
    if 'tracks' not in data or not isinstance(data.get('tracks'), list):
        # Convert legacy flat format to track-based format
        tracks = []
        
        # Video track
        if 'clips' in data or 'video_clips' in data:
            video_clips = data.get('clips') or data.get('video_clips') or []
            tracks.append({
                'type': 'video',
                'name': 'Video Track',
                'clips': video_clips
            })
        
        # Audio track
        if 'background_audios' in data:
            audio_clips = data.get('background_audios') or []
            tracks.append({
                'type': 'audio',
                'name': 'Audio Track',
                'clips': audio_clips
            })
        
        # Text track
        if 'text_overlays' in data:
            text_overlays = data.get('text_overlays') or []
            if text_overlays:
                tracks.append({
                    'type': 'text',
                    'name': 'Text Track',
                    'clips': text_overlays
                })
        
        # Effects track
        if 'effects' in data or 'active_effects' in data:
            effect_clips = data.get('active_effects') or []
            if effect_clips or data.get('effects'):
                tracks.append({
                    'type': 'effect',
                    'name': 'Effects Track',
                    'clips': effect_clips
                })
        
        data['tracks'] = tracks
    
    # Preserve essential properties for export
    import datetime
    data['exportVersion'] = '2.0'
    data['lastModified'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    project.timeline_state = data
    project.save(update_fields=["timeline_state", "updated_at"])
    
    return JsonResponse({
        "status": "ok",
        "tracks_count": len(data.get('tracks', [])),
        "export_ready": True
    })


@login_required
@require_POST
def project_rename(request, pk):
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "forbidden"}, status=403)

    new_title = ""
    try:
        data = json.loads(request.body)
        new_title = data.get("title", "").strip()
    except Exception:
        new_title = request.POST.get("title", "").strip()

    if not new_title:
        new_title = "Untitled Project"

    project.title = new_title[:255]
    project.save(update_fields=["title"])

    return JsonResponse({
        "status": "ok",
        "title": project.title,
        "display_title": project.display_title
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
    project.status = "processing"
    project.save()

    try:
        from .tasks import export_video_task

        def _run_in_thread():
            threading.Thread(
                target=export_video_task,
                args=(project.id, data),
                daemon=True,
            ).start()

        try:
            from school_project.celery import app as celery_app
            inspect = celery_app.control.inspect()
            if inspect and inspect.stats():
                export_video_task.delay(project.id, data)
            else:
                _run_in_thread()
        except Exception:
            _run_in_thread()

        messages.success(request, "Export started! Your video is being processed.")
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
        return JsonResponse({"error": "no_file", "message": "No audio file provided."}, status=400)

    is_valid, err_msg = check_uploaded_file(
        audio_file,
        allowed_extensions=ALLOWED_AUDIO_EXTENSIONS,
        max_size=MAX_AUDIO_SIZE,
        file_category="audio"
    )
    if not is_valid:
        return JsonResponse({"error": "invalid_file", "message": err_msg}, status=400)
        
    tmp_dir = os.path.join(settings.MEDIA_ROOT, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    clean_name = sanitize_filename(audio_file.name)
    audio_tmp_path = os.path.join(tmp_dir, f"audio_{uuid.uuid4().hex}_{clean_name}")
    
    with open(audio_tmp_path, "wb") as dest:
        for chunk in audio_file.chunks():
            dest.write(chunk)
            
    return JsonResponse({
        "status": "success",
        "temp_path": audio_tmp_path,
        "filename": clean_name
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

    ext = get_file_extension(video_file.name)
    asset_type = "video"
    allowed_exts = ALLOWED_VIDEO_EXTENSIONS
    max_size = MAX_VIDEO_SIZE

    if ext in ALLOWED_AUDIO_EXTENSIONS:
        asset_type = "audio"
        allowed_exts = ALLOWED_AUDIO_EXTENSIONS
        max_size = MAX_AUDIO_SIZE
    elif ext in ALLOWED_IMAGE_EXTENSIONS:
        asset_type = "image"
        allowed_exts = ALLOWED_IMAGE_EXTENSIONS
        max_size = MAX_IMAGE_SIZE
    elif ext in ALLOWED_VIDEO_EXTENSIONS:
        asset_type = "video"
        allowed_exts = ALLOWED_VIDEO_EXTENSIONS
        max_size = MAX_VIDEO_SIZE
    else:
        return JsonResponse({
            "error": f"Unsupported media type '.{ext}'. Supported types: video, audio, and images."
        }, status=400)

    is_valid, err_msg = check_uploaded_file(
        video_file,
        allowed_extensions=allowed_exts,
        max_size=max_size,
        file_category=asset_type
    )
    if not is_valid:
        return JsonResponse({"error": err_msg}, status=400)

    clean_name = sanitize_filename(video_file.name)
    
    # Check if frontend provided client-extracted duration
    client_duration = 0.0
    try:
        if request.POST.get("clientDuration"):
            client_duration = float(request.POST.get("clientDuration"))
    except (ValueError, TypeError):
        client_duration = 0.0

    asset = ProjectAsset.objects.create(
        project=project,
        file=video_file,
        title=clean_name,
        filename=clean_name,
        asset_type=asset_type,
        duration_seconds=client_duration if client_duration > 0 else None
    )

    # If client did not provide duration or for images, extract in background thread without blocking response
    if not asset.duration_seconds and asset_type in ("video", "audio"):
        def _async_asset_metadata(asset_id, file_path):
            try:
                meta = ffmpeg_utils.get_metadata(file_path)
                ProjectAsset.objects.filter(id=asset_id).update(duration_seconds=meta.get("duration", 0.0))
            except Exception:
                pass
        threading.Thread(target=_async_asset_metadata, args=(asset.id, asset.file.path), daemon=True).start()

    return JsonResponse({
        "success": True,
        "asset": {
            "id": asset.id,
            "url": asset.file.url,
            "title": asset.display_title,
            "duration": asset.display_duration or "0:00",
            "asset_type": asset.asset_type
        }
    })


@login_required
@require_POST
def delete_asset(request, pk, asset_id):
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        asset = project.assets.get(id=asset_id)
        if asset.file:
            try:
                asset.file.delete(save=False)
            except Exception:
                pass
        asset.delete()
        return JsonResponse({"status": "ok", "deleted_id": asset_id})
    except ProjectAsset.DoesNotExist:
        return JsonResponse({"error": "Asset not found"}, status=404)


@login_required
@require_POST
def rename_asset(request, pk, asset_id):
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        asset = project.assets.get(id=asset_id)
        new_title = ""
        try:
            data = json.loads(request.body)
            new_title = data.get("title", "").strip()
        except Exception:
            new_title = request.POST.get("title", "").strip()
        if new_title:
            asset.title = new_title[:255]
            asset.save(update_fields=["title"])
        return JsonResponse({"status": "ok", "title": asset.display_title})
    except ProjectAsset.DoesNotExist:
        return JsonResponse({"error": "Asset not found"}, status=404)





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

    if project.status == "processing":
        messages.warning(
            request,
            "Export is currently in progress. Please wait until rendering completes before publishing."
        )
        return redirect(f"{reverse('project_detail', args=[pk])}?recording_id={recording_id}")

    if project.has_unexported_edits:
        messages.warning(
            request,
            "You have unexported timeline edits. Please click 'Export' to render your changes before publishing to students."
        )
        return redirect(f"{reverse('project_detail', args=[pk])}?recording_id={recording_id}")

    target_file = project.exported_file or project.original_file
    if not target_file or not target_file.name or not os.path.exists(target_file.path):
        messages.error(request, "Video file not found on disk.")
        return redirect(f"{reverse('project_detail', args=[pk])}?recording_id={recording_id}")

    try:
        edited_path = target_file.path
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



from django.views.decorators.csrf import csrf_exempt

_upload_assembly_lock = threading.Lock()

@csrf_exempt
@login_required
def chunked_upload_view(request):
    """
    High-throughput parallel chunked upload receiver.
    Supports concurrent chunk streams, client metadata pre-extraction,
    and asynchronous background proxy generation.
    """
    if request.method == 'POST':
        chunk = request.FILES.get('chunk')
        filename = request.POST.get('filename')
        chunk_index = int(request.POST.get('chunkIndex', 0))
        total_chunks = int(request.POST.get('totalChunks', 1))
        upload_id = request.POST.get('uploadId')
        
        target_type = request.POST.get('targetType', 'project')
        project_id = request.POST.get('projectId')
        
        client_duration = float(request.POST.get('clientDuration') or 0.0)
        client_width = int(request.POST.get('clientWidth') or 1920)
        client_height = int(request.POST.get('clientHeight') or 1080)
        
        if not all([chunk, filename, upload_id]):
            return JsonResponse({'success': False, 'error': 'Missing data'}, status=400)
            
        clean_filename = sanitize_filename(filename)
        try:
            temp_dir = get_safe_temp_upload_dir(os.path.join(settings.MEDIA_ROOT, 'temp_uploads'), upload_id)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

        
        # Write chunk with atomic temp file to avoid partial reads across worker threads
        chunk_path = os.path.join(temp_dir, f'chunk_{chunk_index}')
        chunk_tmp_path = os.path.join(temp_dir, f'chunk_{chunk_index}.tmp')
        
        with open(chunk_tmp_path, 'wb') as f:
            for data in chunk.chunks(chunk_size=1048576):
                f.write(data)
        
        if os.path.exists(chunk_path):
            try:
                os.remove(chunk_path)
            except OSError:
                pass
        os.replace(chunk_tmp_path, chunk_path)
        
        # Check if all chunks have arrived
        all_chunks_present = all(
            os.path.exists(os.path.join(temp_dir, f'chunk_{i}'))
            for i in range(total_chunks)
        )
        
        if all_chunks_present:
            # Synchronize final assembly across multiple worker processes & threads
            lock_path = os.path.join(temp_dir, '.assembling.lock')
            acquired_lock = False
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                acquired_lock = True
            except (FileExistsError, OSError):
                acquired_lock = False

            if not acquired_lock:
                # Companion worker thread/process is already assembling the file
                return JsonResponse({'success': True, 'message': 'Assembly in progress by worker'})

            with _upload_assembly_lock:
                final_file_path = os.path.join(temp_dir, clean_filename)
                with open(final_file_path, 'wb') as final_file:
                    for i in range(total_chunks):
                        part_path = os.path.join(temp_dir, f'chunk_{i}')
                        if os.path.exists(part_path):
                            with open(part_path, 'rb') as part:
                                shutil.copyfileobj(part, final_file, length=1048576)
                            try:
                                os.remove(part_path)
                            except OSError:
                                pass
                
                # Check target type: 'asset' vs 'project'
                if target_type == 'asset' and project_id:
                    try:
                        proj = VideoProject.objects.get(pk=project_id, owner=request.user)
                        ext = get_file_extension(clean_filename)
                        asset_type = "video"
                        if ext in ALLOWED_AUDIO_EXTENSIONS:
                            asset_type = "audio"
                        elif ext in ALLOWED_IMAGE_EXTENSIONS:
                            asset_type = "image"
                            
                        asset = ProjectAsset.objects.create(
                            project=proj,
                            title=clean_filename,
                            filename=clean_filename,
                            asset_type=asset_type,
                            duration_seconds=client_duration if client_duration > 0 else None
                        )
                        with open(final_file_path, 'rb') as final_file:
                            asset.file.save(clean_filename, File(final_file))
                            
                        # Probe metadata asynchronously if not client-provided
                        if not asset.duration_seconds and asset_type in ("video", "audio"):
                            def _async_asset_meta(asset_id, file_path):
                                try:
                                    meta = ffmpeg_utils.get_metadata(file_path)
                                    ProjectAsset.objects.filter(id=asset_id).update(duration_seconds=meta.get("duration", 0.0))
                                except Exception:
                                    pass
                            threading.Thread(target=_async_asset_meta, args=(asset.id, asset.file.path), daemon=True).start()
                            
                        os.remove(final_file_path)
                        try:
                            os.rmdir(temp_dir)
                        except OSError:
                            pass
                            
                        return JsonResponse({
                            'success': True,
                            'asset': {
                                'id': asset.id,
                                'url': asset.file.url,
                                'title': asset.display_title,
                                'duration': asset.display_duration or "0:00"
                            }
                        })
                    except Exception as e:
                        return JsonResponse({'success': False, 'error': str(e)}, status=500)
                
                # Default: Create new VideoProject
                project = VideoProject.objects.create(
                    owner=request.user,
                    title=clean_filename
                )
                with open(final_file_path, 'rb') as final_file:
                    project.original_file.save(clean_filename, File(final_file))
                    
                # Initialize metadata immediately from client values so editor opens in < 0.01s
                project.duration_seconds = client_duration if client_duration > 0 else None
                project.width = client_width
                project.height = client_height
                project.has_audio = True
                project.status = "ready"
                project.proxy_status = 'pending'
                project.save()
                convert_legacy_project_to_timeline(project)
                
                # Record upload edit operation
                try:
                    EditOperation.objects.create(
                        project=project,
                        operation_type="upload",
                        description=f"Uploaded {clean_filename}",
                    )
                except Exception:
                    pass

                # Cleanup temp files
                try:
                    if os.path.exists(final_file_path):
                        os.remove(final_file_path)
                    os.rmdir(temp_dir)
                except OSError:
                    pass
                    
                # Dispatch background task for ffprobe verification & proxy / filmstrip generation
                try:
                    from .tasks import extract_metadata_and_proxies_task, generate_filmstrip_task, dispatch_async
                    dispatch_async(extract_metadata_and_proxies_task, project.id)
                    dispatch_async(generate_filmstrip_task, project.id)
                except Exception:
                    pass

                res_data = {'success': True, 'project_id': project.id}
                return JsonResponse(res_data)
                
        return JsonResponse({'success': True, 'message': 'Chunk received', 'chunkIndex': chunk_index})
        
    return JsonResponse({'success': False}, status=405)

@login_required
def proxy_status_view(request, pk):
    try:
        project = VideoProject.objects.get(pk=pk, owner=request.user)
        proxy_dir = os.path.join(settings.MEDIA_ROOT, 'proxies', str(project.owner_id), str(project.id))
        proxy_mp4 = os.path.join(proxy_dir, 'proxy.mp4')
        playlist = os.path.join(proxy_dir, 'proxy.m3u8')

        url = project.proxy_url
        status = project.proxy_status
        if os.path.exists(proxy_mp4) and os.path.getsize(proxy_mp4) > 0:
            status = 'completed'
            url = f"{settings.MEDIA_URL}proxies/{project.owner_id}/{project.id}/proxy.mp4"
            if project.proxy_status != 'completed' or project.proxy_url != url:
                project.proxy_status = 'completed'
                project.proxy_url = url
                project.save(update_fields=['proxy_status', 'proxy_url'])
        elif os.path.exists(playlist) and os.path.getsize(playlist) > 0:
            status = 'completed'
            url = f"{settings.MEDIA_URL}proxies/{project.owner_id}/{project.id}/proxy.m3u8"

        return JsonResponse({
            'status': status,
            'url': url
        })
    except VideoProject.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

@login_required
@login_required
def project_filmstrip(request, pk):
    """
    Industry-level Canva/CapCut filmstrip endpoint:
    Never runs ffmpeg inside the HTTP request. Only returns existing frames or 'generating'.
    Thumbnail generation runs asynchronously via Celery or daemon thread.
    """
    try:
        project = VideoProject.objects.get(pk=pk, owner=request.user)
    except VideoProject.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    media_file = project.working_file or project.original_file
    if not media_file:
        return JsonResponse({"status": "no_media", "thumbnails": []})

    dur = project.duration_seconds or 0.0
    expected_count = min(240, max(12, int(math.ceil(dur / 5.0)))) if dur > 0 else 12

    filmstrip_dir = os.path.join(settings.MEDIA_ROOT, 'proxies', str(project.owner_id), str(project.id), 'filmstrip')
    base_url = f"/video-editing/project/{project.id}/filmstrip/"

    if os.path.exists(filmstrip_dir):
        existing = sorted([f for f in os.listdir(filmstrip_dir) if f.startswith("thumb_") and f.endswith(".webp")])
        if len(existing) > 0:
            thumbs = [f"{base_url}{f}" for f in existing]
            return JsonResponse({
                "status": "ready" if len(existing) >= expected_count or len(existing) >= 12 else "generating",
                "count": len(thumbs),
                "thumbnails": thumbs,
                "duration": dur
            })

    # Dispatch background task if not already generated, with zero-delay thread fallback
    try:
        from .tasks import generate_filmstrip_task, dispatch_async
        dispatch_async(generate_filmstrip_task, project.id)
    except Exception:
        pass

    return JsonResponse({
        "status": "generating",
        "count": 0,
        "thumbnails": [],
        "duration": dur
    })

@login_required
def project_filmstrip_frame(request, pk, filename):
    """
    Directly serves a specific WebP filmstrip frame with proper image content-type
    and CORS headers for canvas extraction.
    """
    safe_name = os.path.basename(filename)
    if not safe_name.endswith('.webp') or not safe_name.startswith('thumb_'):
        raise Http404("Invalid frame name")

    try:
        project = VideoProject.objects.get(pk=pk, owner=request.user)
    except VideoProject.DoesNotExist:
        raise Http404("Project not found")

    frame_path = os.path.join(settings.MEDIA_ROOT, 'proxies', str(project.owner_id), str(project.id), 'filmstrip', safe_name)
    if not os.path.exists(frame_path):
        raise Http404("Frame not found")

    resp = FileResponse(open(frame_path, 'rb'), content_type='image/webp')
    resp['Cache-Control'] = 'public, max-age=86400, immutable'
    resp['Access-Control-Allow-Origin'] = '*'
    return resp

@login_required
def project_waveform(request, pk):
    """
    Returns real extracted audio waveform peaks for the project's audio.
    If waveform.json exists, returns the peak array.
    If not ready yet, dispatches generate_waveform_task and returns status: "generating".
    """
    try:
        project = VideoProject.objects.get(pk=pk, owner=request.user)
    except VideoProject.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    if not project.has_audio:
        return JsonResponse({"status": "no_audio", "peaks": [], "duration": project.duration_seconds or 0.0})

    waveform_path = os.path.join(settings.MEDIA_ROOT, 'proxies', str(project.owner_id), str(project.id), 'waveform.json')
    if os.path.exists(waveform_path):
        try:
            with open(waveform_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return JsonResponse(data)
        except Exception:
            pass

    try:
        from .tasks import generate_waveform_task
        from school_project.celery import app as celery_app
        inspect = celery_app.control.inspect()
        if inspect and inspect.stats():
            generate_waveform_task.delay(project.id)
        else:
            threading.Thread(target=generate_waveform_task, args=(project.id,), daemon=True).start()
    except Exception:
        import threading
        try:
            from .tasks import generate_waveform_task
            threading.Thread(target=generate_waveform_task, args=(project.id,), daemon=True).start()
        except Exception:
            pass

    return JsonResponse({
        "status": "generating",
        "peaks": [],
        "duration": project.duration_seconds or 0.0
    })
