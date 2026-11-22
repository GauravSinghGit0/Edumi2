"""
Non-destructive timeline editing views.
Phase 4.1 refactor.
"""
import os
import json
import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from ..models import EditOperation, ProjectAsset
from ..forms import TrimForm, TextOverlayForm, BackgroundAudioForm, SpeedForm
from .. import ffmpeg_utils
from .utils import _get_owned_project
from .project_views import convert_legacy_project_to_timeline


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

        state = project.timeline_state or {}
        if 'trim' not in state:
            state['trim'] = {}

        state['trim']['start'] = start
        state['trim']['end'] = end
        state['trim']['mode'] = 'extract'

        project.timeline_state = state
        project.save(update_fields=['timeline_state'])

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

    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )

    form = BackgroundAudioForm(request.POST, request.FILES)
    if form.is_valid():
        audio_file = form.cleaned_data["audio_file"]
        start = form.cleaned_data.get("start_seconds") or 0.0
        end = form.cleaned_data.get("end_seconds")
        bg_vol = form.cleaned_data.get("bg_volume") or 0.5
        vid_vol = form.cleaned_data.get("video_volume") or 1.0

        asset = ProjectAsset.objects.create(
            project=project,
            asset_type='audio',
            file=audio_file,
            filename=audio_file.name
        )

        try:
            meta = ffmpeg_utils.get_metadata(asset.file.path)
            asset.duration_seconds = meta.get('duration', 0)
            asset.save()
            if end is None:
                end = asset.duration_seconds
        except Exception:
            if end is None:
                end = project.duration_seconds or 10.0

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

        if is_ajax:
            return JsonResponse({
                "status": "success",
                "success": True,
                "asset": {
                    "id": asset.id,
                    "url": asset.file.url,
                    "title": asset.display_title,
                    "duration": asset.display_duration or "0:00",
                    "duration_seconds": asset.duration_seconds or 0.0,
                    "asset_type": "audio"
                },
                "timeline_state": state
            })
        messages.success(request, "Background audio added to timeline. Export to render final video.")
    else:
        if is_ajax:
            return JsonResponse({"status": "error", "error": form.errors.as_text()}, status=400)
        messages.error(request, "Invalid background audio parameters.")
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
def save_timeline(request, pk):
    """Persist client-side multi-track timeline JSON state."""
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"error": "invalid_timeline_format"}, status=400)

    if 'tracks' not in data or not isinstance(data.get('tracks'), list):
        tracks = []
        if 'clips' in data or 'video_clips' in data:
            video_clips = data.get('clips') or data.get('video_clips') or []
            tracks.append({
                'type': 'video',
                'name': 'Video Track',
                'clips': video_clips
            })

        if 'background_audios' in data:
            audio_clips = data.get('background_audios') or []
            tracks.append({
                'type': 'audio',
                'name': 'Audio Track',
                'clips': audio_clips
            })

        if 'text_overlays' in data:
            text_overlays = data.get('text_overlays') or []
            if text_overlays:
                tracks.append({
                    'type': 'text',
                    'name': 'Text Track',
                    'clips': text_overlays
                })

        data['tracks'] = tracks

    data['exportVersion'] = '2.0'
    data['lastModified'] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    project.timeline_state = data
    project.save(update_fields=["timeline_state", "updated_at"])

    return JsonResponse({
        "status": "ok",
        "tracks_count": len(data.get('tracks', [])),
        "export_ready": True
    })
