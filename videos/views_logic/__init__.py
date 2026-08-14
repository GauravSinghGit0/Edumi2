"""
Re-export for videos views
"""
from videos.views_logic.core_views import video_list, video_detail, upload_video, edit_video, delete_video, like_video
from videos.views_logic.utils import process_video_sync
from videos.views_logic.streaming_views import stream_video_chunk, stream_quality_video
