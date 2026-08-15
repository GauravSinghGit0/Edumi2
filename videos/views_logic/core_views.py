"""
Core video management views
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.contrib import messages

from videos.models import Video


@login_required
def video_list(request):
    """List all uploaded videos with YouTube-like grid."""
    videos = Video.objects.all().select_related('uploaded_by').order_by('-uploaded_at')
    return render(request, 'videos/video_list.html', {'videos': videos})


@login_required
def video_detail(request, video_id):
    """Show video detail page with player and quality selector."""
    video = get_object_or_404(Video, id=video_id)
    video.views_count += 1
    video.save(update_fields=['views_count'])
    # Get other videos for recommendations
    recommendations = Video.objects.exclude(id=video.id)[:8]
    return render(request, 'videos/video_detail.html', {
        'video': video,
        'recommendations': recommendations
    })


from common.validators import (
    check_uploaded_file,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_VIDEO_SIZE,
    MAX_IMAGE_SIZE,
)


@login_required
@require_http_methods(["GET", "POST"])
def upload_video(request):
    """Handle video upload and start processing."""
    if request.method == 'POST':
        video_file = request.FILES.get('video')
        if not video_file:
            return JsonResponse({'status': 'error', 'message': 'No video file provided.'}, status=400)

        # Validate video file
        is_valid, err_msg = check_uploaded_file(
            video_file,
            allowed_extensions=ALLOWED_VIDEO_EXTENSIONS,
            max_size=MAX_VIDEO_SIZE,
            file_category="video"
        )
        if not is_valid:
            return JsonResponse({'status': 'error', 'message': err_msg}, status=400)

        # Validate optional thumbnail
        thumbnail = request.FILES.get('thumbnail')
        if thumbnail:
            is_thumb_valid, thumb_err = check_uploaded_file(
                thumbnail,
                allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
                max_size=MAX_IMAGE_SIZE,
                file_category="thumbnail"
            )
            if not is_thumb_valid:
                return JsonResponse({'status': 'error', 'message': f"Thumbnail error: {thumb_err}"}, status=400)

        title = request.POST.get('title', 'Untitled Video')
        description = request.POST.get('description', '')

        # Create video object
        video = Video.objects.create(
            title=title,
            description=description,
            original_file=video_file,
            thumbnail=thumbnail,
            uploaded_by=request.user,
            file_size=video_file.size,
            mime_type=video_file.content_type,
        )

        # Start processing asynchronously
        try:
            from videos.tasks import process_video
            process_video.delay(video.id)
        except Exception:
            # Fallback to sync processing if Celery not available
            from videos.views_logic.utils import process_video_sync
            process_video_sync(video.id)

        return JsonResponse({
            'status': 'success', 
            'video_id': video.id,
            'redirect_url': reverse('video_list')  # Redirect to video list
        })

    # For GET requests, show upload page (using cameras/upload_video.html which we will overhaul)
    from cameras.models import Camera
    cameras = Camera.objects.filter(is_active=True)
    if request.user.userprofile.user_type == 'teacher':
        cameras = cameras.filter(camerapermission__teacher=request.user)
    
    return render(request, 'cameras/upload_video.html', {'cameras': cameras})


@login_required
def edit_video(request, video_id):
    """Allow teachers to edit their own videos."""
    video = get_object_or_404(Video, id=video_id)
    
    # Only uploader or superuser can edit
    if video.uploaded_by != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to edit this video.")
        
    if request.method == 'POST':
        video.title = request.POST.get('title', video.title)
        video.description = request.POST.get('description', video.description)
        
        thumbnail = request.FILES.get('thumbnail')
        if thumbnail:
            is_thumb_valid, thumb_err = check_uploaded_file(
                thumbnail,
                allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
                max_size=MAX_IMAGE_SIZE,
                file_category="thumbnail"
            )
            if not is_thumb_valid:
                messages.error(request, f"Thumbnail error: {thumb_err}")
                return render(request, 'videos/edit_video.html', {'video': video})
            video.thumbnail = thumbnail
            
        video.save()
        messages.success(request, "Video updated successfully!")
        return redirect('video_detail', video_id=video.id)
        
    return render(request, 'videos/edit_video.html', {'video': video})


@login_required
@require_http_methods(["POST"])
def delete_video(request, video_id):
    """Allow teachers to delete their own videos."""
    video = get_object_or_404(Video, id=video_id)
    
    # Only uploader or superuser can delete
    if video.uploaded_by != request.user and not request.user.is_superuser:
        return HttpResponseForbidden("You don't have permission to delete this video.")
        
    video.delete()
    messages.success(request, "Video deleted successfully!")
    return redirect('video_list')


@login_required
@require_http_methods(["POST"])
def like_video(request, video_id):
    """Increment likes for a video."""
    video = get_object_or_404(Video, id=video_id)
    video.likes_count += 1
    video.save(update_fields=['likes_count'])
    return JsonResponse({'status': 'success', 'likes_count': video.likes_count})
