"""
Video streaming views (chunks and quality)
"""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import FileResponse

from videos.models import VideoQuality, VideoChunk


@login_required
def stream_video_chunk(request, quality_id, chunk_number):
    """Stream a specific 10-second chunk of a video."""
    quality = get_object_or_404(VideoQuality, id=quality_id)
    chunk = get_object_or_404(VideoChunk, quality=quality, chunk_number=chunk_number)

    return FileResponse(
        chunk.file.open('rb'),
        content_type='video/mp4'
    )


@login_required
def stream_quality_video(request, quality_id):
    """Stream an entire quality version (fallback if chunks not available)."""
    quality = get_object_or_404(VideoQuality, id=quality_id)
    return FileResponse(
        quality.file.open('rb'),
        content_type='video/mp4'
    )
