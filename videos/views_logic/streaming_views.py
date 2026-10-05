"""
Video streaming views (HLS adaptive streams, playlists, segments, and fallbacks)
"""
import os
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse

from videos.models import Video, VideoQuality, VideoChunk


def stream_hls_master(request, video_id):
    """Stream master HLS (.m3u8) playlist for adaptive bitrate video streaming."""
    video = get_object_or_404(Video, id=video_id)
    if not video.hls_master_playlist:
        raise Http404("HLS master playlist not found for this video")
    
    master_path = os.path.join(settings.MEDIA_ROOT, video.hls_master_playlist.name)
    if not os.path.exists(master_path):
        raise Http404("HLS master playlist file does not exist on disk")

    return FileResponse(
        open(master_path, 'rb'),
        content_type='application/vnd.apple.mpegurl'
    )


def stream_hls_variant(request, video_id, quality_name):
    """Stream specific quality variant HLS (.m3u8) playlist (e.g. 1080p, 720p)."""
    variant_path = os.path.join(settings.MEDIA_ROOT, 'videos', 'hls', str(video_id), quality_name, 'playlist.m3u8')
    if not os.path.exists(variant_path):
        raise Http404("HLS variant playlist file does not exist")

    return FileResponse(
        open(variant_path, 'rb'),
        content_type='application/vnd.apple.mpegurl'
    )


def stream_hls_segment(request, video_id, quality_name, segment_name):
    """Stream individual HLS transport stream (.ts) segment file."""
    segment_path = os.path.join(settings.MEDIA_ROOT, 'videos', 'hls', str(video_id), quality_name, segment_name)
    if not os.path.exists(segment_path):
        raise Http404("HLS segment file does not exist")

    return FileResponse(
        open(segment_path, 'rb'),
        content_type='video/MP2T'
    )


@login_required
def stream_video_chunk(request, quality_id, chunk_number):
    """Stream a specific chunk of a video."""
    quality = get_object_or_404(VideoQuality, id=quality_id)
    chunk = get_object_or_404(VideoChunk, quality=quality, chunk_number=chunk_number)

    content_type = 'video/MP2T' if chunk.file.name.endswith('.ts') else 'video/mp4'
    return FileResponse(
        chunk.file.open('rb'),
        content_type=content_type
    )


@login_required
def stream_quality_video(request, quality_id):
    """Stream an entire quality version (fallback if standalone file exists)."""
    quality = get_object_or_404(VideoQuality, id=quality_id)
    if quality.hls_playlist:
        playlist_path = os.path.join(settings.MEDIA_ROOT, quality.hls_playlist.name)
        if os.path.exists(playlist_path):
            return FileResponse(open(playlist_path, 'rb'), content_type='application/vnd.apple.mpegurl')
            
    if quality.file:
        return FileResponse(quality.file.open('rb'), content_type='video/mp4')
        
    raise Http404("Quality file stream not found")

