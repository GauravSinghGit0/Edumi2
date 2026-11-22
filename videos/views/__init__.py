"""
Re-export for videos views
"""
from .core_views import video_list, video_detail, upload_video, edit_video, delete_video, like_video
from .utils import process_video_sync
from .streaming_views import (
    stream_video_chunk,
    stream_quality_video,
    stream_hls_master,
    stream_hls_variant,
    stream_hls_segment,
)

__all__ = [
    'video_list',
    'video_detail',
    'upload_video',
    'edit_video',
    'delete_video',
    'like_video',
    'process_video_sync',
    'stream_video_chunk',
    'stream_quality_video',
    'stream_hls_master',
    'stream_hls_variant',
    'stream_hls_segment',
]
