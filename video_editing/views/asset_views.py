"""
Video asset upload and management views.
Phase 4.1 refactor.
"""
import os
import math
import json
import shutil
import threading
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files import File
from django.http import JsonResponse, FileResponse, Http404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from ..models import VideoProject, ProjectAsset, EditOperation
from .. import ffmpeg_utils
from .utils import _get_owned_project
from common.validators import (
    check_uploaded_file,
    sanitize_filename,
    get_file_extension,
    get_safe_temp_upload_dir,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_AUDIO_EXTENSIONS,
    MAX_VIDEO_SIZE,
    MAX_AUDIO_SIZE,
    MAX_IMAGE_SIZE,
)
from .project_views import convert_legacy_project_to_timeline


@login_required
@require_POST
def upload_audio_temp(request, pk):
    """
    Backward-compatible adapter for audio uploads.
    Creates a persistent ProjectAsset and returns both legacy and modern response keys.
    """
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "forbidden"}, status=403)

    audio_file = (
        request.FILES.get("audio_file") or
        request.FILES.get("file") or
        request.FILES.get("media_file") or
        next(iter(request.FILES.values()), None)
    )
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

    clean_name = sanitize_filename(audio_file.name)
    asset = ProjectAsset.objects.create(
        project=project,
        file=audio_file,
        title=clean_name,
        filename=clean_name,
        asset_type="audio"
    )
    try:
        meta = ffmpeg_utils.get_metadata(asset.file.path)
        asset.duration_seconds = meta.get("duration", 0.0)
        asset.save(update_fields=["duration_seconds"])
    except Exception:
        pass

    return JsonResponse({
        "status": "success",
        "success": True,
        "temp_path": asset.file.path,
        "filename": clean_name,
        "asset": {
            "id": asset.id,
            "url": asset.file.url,
            "title": asset.display_title,
            "duration": asset.display_duration or "0:00",
            "duration_seconds": asset.duration_seconds or 0.0,
            "asset_type": "audio",
            "delete_url": reverse("delete_asset", args=[project.pk, asset.id]),
            "rename_url": reverse("rename_asset", args=[project.pk, asset.id]),
        }
    })


@login_required
@require_POST
def upload_asset(request, pk):
    """
    Unified modular media asset upload endpoint for Edumi Video Editing.
    Handles video, audio, and image files through a single pipeline.
    """
    project = _get_owned_project(request, pk)
    if project is None:
        return JsonResponse({"error": "Forbidden"}, status=403)

    uploaded_file = (
        request.FILES.get("file") or
        request.FILES.get("media_file") or
        request.FILES.get("video_file") or
        request.FILES.get("audio_file") or
        next(iter(request.FILES.values()), None)
    )
    if not uploaded_file:
        return JsonResponse({"error": "No file uploaded"}, status=400)

    ext = get_file_extension(uploaded_file.name)
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
        uploaded_file,
        allowed_extensions=allowed_exts,
        max_size=max_size,
        file_category=asset_type
    )
    if not is_valid:
        return JsonResponse({"error": err_msg}, status=400)

    clean_name = sanitize_filename(uploaded_file.name)

    client_duration = 0.0
    try:
        if request.POST.get("clientDuration"):
            client_duration = float(request.POST.get("clientDuration"))
    except (ValueError, TypeError):
        client_duration = 0.0

    if asset_type == "image" and client_duration <= 0:
        client_duration = 5.0

    asset = ProjectAsset.objects.create(
        project=project,
        file=uploaded_file,
        title=clean_name,
        filename=clean_name,
        asset_type=asset_type,
        duration_seconds=client_duration if client_duration > 0 else None
    )

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
        "status": "success",
        "asset": {
            "id": asset.id,
            "url": asset.file.url,
            "title": asset.display_title,
            "duration": asset.display_duration or "0:00",
            "duration_seconds": asset.duration_seconds or (5.0 if asset.asset_type == "image" else 0.0),
            "asset_type": asset.asset_type,
            "delete_url": reverse("delete_asset", args=[project.pk, asset.id]),
            "rename_url": reverse("rename_asset", args=[project.pk, asset.id]),
        }
    })


@login_required
@require_POST
def delete_asset(request, pk, asset_id):
    """Delete a specific media asset from the project."""
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
    """Rename an asset display title."""
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

        all_chunks_present = all(
            os.path.exists(os.path.join(temp_dir, f'chunk_{i}'))
            for i in range(total_chunks)
        )

        if all_chunks_present:
            lock_path = os.path.join(temp_dir, '.assembling.lock')
            acquired_lock = False
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                acquired_lock = True
            except (FileExistsError, OSError):
                acquired_lock = False

            if not acquired_lock:
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

                if target_type == 'asset' and project_id:
                    try:
                        proj = VideoProject.objects.get(pk=project_id, owner=request.user)
                        ext = get_file_extension(clean_filename)
                        asset_type = "video"
                        if ext in ALLOWED_AUDIO_EXTENSIONS:
                            asset_type = "audio"
                        elif ext in ALLOWED_IMAGE_EXTENSIONS:
                            asset_type = "image"
                            if client_duration <= 0:
                                client_duration = 5.0

                        asset = ProjectAsset.objects.create(
                            project=proj,
                            title=clean_filename,
                            filename=clean_filename,
                            asset_type=asset_type,
                            duration_seconds=client_duration if client_duration > 0 else None
                        )
                        with open(final_file_path, 'rb') as final_file:
                            asset.file.save(clean_filename, File(final_file))

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
                                'duration': asset.display_duration or "0:00",
                                'duration_seconds': asset.duration_seconds or (5.0 if asset.asset_type == "image" else 0.0),
                                'asset_type': asset.asset_type,
                                'delete_url': reverse("delete_asset", args=[proj.pk, asset.id]),
                                'rename_url': reverse("rename_asset", args=[proj.pk, asset.id]),
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

                project.duration_seconds = client_duration if client_duration > 0 else None
                project.width = client_width
                project.height = client_height
                project.has_audio = True
                project.status = "ready"
                project.proxy_status = 'pending'
                project.save()
                convert_legacy_project_to_timeline(project)

                try:
                    EditOperation.objects.create(
                        project=project,
                        operation_type="upload",
                        description=f"Uploaded {clean_filename}",
                    )
                except Exception:
                    pass

                try:
                    if os.path.exists(final_file_path):
                        os.remove(final_file_path)
                    os.rmdir(temp_dir)
                except OSError:
                    pass

                try:
                    from ..tasks import extract_metadata_and_proxies_task, generate_filmstrip_task, dispatch_async
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
    """Query generation progress of low-resolution HLS / proxy streams."""
    try:
        project = VideoProject.objects.get(pk=pk, owner=request.user)
        proxy_dir = os.path.join(settings.MEDIA_ROOT, 'proxies', str(project.owner_id), str(project.id))
        proxy_mp4 = os.path.join(proxy_dir, 'proxy.mp4')
        playlist = os.path.join(proxy_dir, 'proxy.m3u8')

        url = project.proxy_url
        status = project.proxy_status
        if project.proxy_status == 'completed' and os.path.exists(proxy_mp4) and os.path.getsize(proxy_mp4) > 0:
            status = 'completed'
            url = f"{settings.MEDIA_URL}proxies/{project.owner_id}/{project.id}/proxy.mp4"
            if project.proxy_url != url:
                project.proxy_url = url
                project.save(update_fields=['proxy_status', 'proxy_url'])
        elif os.path.exists(playlist) and os.path.getsize(playlist) > 0:
            status = 'completed'
            url = f"{settings.MEDIA_URL}proxies/{project.owner_id}/{project.id}/proxy.m3u8"
            if project.proxy_status != 'completed' or project.proxy_url != url:
                project.proxy_status = 'completed'
                project.proxy_url = url
                project.save(update_fields=['proxy_status', 'proxy_url'])
        elif project.proxy_status == 'completed' and not os.path.exists(proxy_mp4):
            status = 'pending'

        original_url = project.original_file.url if project.original_file else ''
        working_file_url = project.working_file_url or ''

        return JsonResponse({
            'status': status,
            'url': url or working_file_url or original_url,
            'proxy_url': url,
            'original_url': original_url,
            'working_file_url': working_file_url
        })
    except VideoProject.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@login_required
def project_filmstrip(request, pk):
    """
    Filmstrip endpoint:
    Returns existing thumbnail frames or status: 'generating'.
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

    try:
        from ..tasks import generate_filmstrip_task, dispatch_async
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
    """Directly serves a specific WebP filmstrip frame."""
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
    Returns extracted audio waveform peaks for the project's audio.
    Phase 2.3 refactor: Direct Celery dispatch without blocking inspect().
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
        from ..tasks import generate_waveform_task
        try:
            generate_waveform_task.delay(project.id)
        except Exception:
            threading.Thread(target=generate_waveform_task, args=(project.id,), daemon=True).start()
    except Exception:
        pass

    return JsonResponse({
        "status": "generating",
        "peaks": [],
        "duration": project.duration_seconds or 0.0
    })
