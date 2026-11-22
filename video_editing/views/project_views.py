"""
Video project CRUD views.
Phase 4.1 refactor.
"""
import os
import json
import re
import shutil
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from ..models import VideoProject, EditOperation
from ..forms import (
    VideoUploadForm, TrimForm, VolumeForm, MergeForm,
    TextOverlayForm, SpeedForm, BackgroundAudioForm,
)
from .. import ffmpeg_utils
from .utils import _get_owned_project


@login_required
def project_list(request):
    """List and create video projects."""
    if request.method == "POST":
        form = VideoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            project = form.save(commit=False)
            project.owner = request.user
            project.status = "ready"
            if not project.title or not project.title.strip():
                orig_filename = request.FILES["original_file"].name
                project.title = os.path.splitext(orig_filename)[0]
            project.save()

            EditOperation.objects.create(
                project=project,
                operation_type="upload",
                description=f"Uploaded {project.original_file.name.split('/')[-1]}",
            )

            try:
                from ..tasks import extract_metadata_and_proxies_task
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


def convert_legacy_project_to_timeline(project):
    """Convert legacy operation stack to modern timeline JSON state."""
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
            "url": project.working_file_url or (project.original_file.url if project.original_file else ""),
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
    """View project details and timeline editor."""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden("You do not have access to this project.")

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

    state = project.timeline_state
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except Exception:
            pass
    timeline_state_json = json.dumps(state) if state else "null"

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
        "workingFileUrl": project.working_file_url or "",
        "originalUrl": project.original_file.url if project.original_file else "",
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
        "bg_audio_form": BackgroundAudioForm(),
        "operations": operations_list,
        "has_redo": project.operations.filter(active=False).exists(),
        "timeline_state_json": timeline_state_json,
        "project_config": project_config,
    }
    return render(request, "video_editing/project_detail.html", context)


@login_required
def project_delete(request, pk):
    """Delete video project and associated media files."""
    project = _get_owned_project(request, pk)
    if project is None:
        return HttpResponseForbidden()
    title = project.display_title

    for f in [project.original_file, project.current_file]:
        if f and f.name:
            try:
                if os.path.exists(f.path):
                    os.remove(f.path)
            except (OSError, ValueError):
                pass

    proxy_dir = os.path.join(settings.MEDIA_ROOT, "proxies", str(project.owner_id), str(project.pk))
    if os.path.isdir(proxy_dir):
        try:
            shutil.rmtree(proxy_dir)
        except OSError:
            pass

    for asset in project.assets.all():
        if asset.file and asset.file.name:
            try:
                if os.path.exists(asset.file.path):
                    os.remove(asset.file.path)
            except (OSError, ValueError):
                pass

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
@require_POST
def project_rename(request, pk):
    """Rename project title."""
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
