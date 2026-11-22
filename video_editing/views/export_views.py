"""
Video export and download views.
Phase 4.1 refactor.
Phase 2.3 integration: Always async, direct Celery dispatch.
"""
import os
import json
import threading
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse, HttpResponseForbidden
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST
from ..models import VideoProject
from .. import ffmpeg_utils
from .utils import _get_owned_project


@login_required
@require_POST
def export_project(request, pk):
    """
    Export video project (always async).
    Phase 2.3 / 4.1 refactor: Direct Celery task dispatch without blocking inspect.
    """
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "forbidden"}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    project.timeline_state = data
    project.status = "processing"
    project.save()

    try:
        from ..tasks import export_video_task

        def _run_in_thread():
            threading.Thread(
                target=export_video_task,
                args=(project.id, data),
                daemon=True,
            ).start()

        celery_active = False
        try:
            from edumi_core.celery import app as celery_app
            insp = celery_app.control.inspect()
            if insp and insp.stats():
                celery_active = True
        except Exception:
            celery_active = False

        if celery_active:
            try:
                export_video_task.delay(project.id, data)
            except Exception:
                _run_in_thread()
        else:
            _run_in_thread()

        messages.success(request, "Export started! Your video is being processed.")
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
def project_download(request, pk):
    """Download exported project MP4."""
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
    """Download exported project converted to MKV."""
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
    """Non-blocking status poll endpoint for video export and proxies."""
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
def publish_to_lecture(request, pk):
    """
    Publish the edited VideoProject back to its CameraRecording and set it to published.
    """
    from cameras.models import CameraRecording
    from django.core.files import File

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
