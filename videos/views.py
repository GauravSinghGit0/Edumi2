# videos/views.py — THIN SHIM
# All logic lives in videos/views_logic/ sub-package.
# This file only re-exports so Django's URL resolver and any
# direct `from videos.views import X` imports keep working.
#
# Sub-files (videos/views_logic/):
#   core_views.py      — video_list, video_detail, upload_video
#   utils.py           — process_video_sync, get_video_duration, create_quality_version, create_video_chunks
#   streaming_views.py — stream_video_chunk, stream_quality_video

from videos.views_logic import (
    video_list,
    video_detail,
    upload_video,
    edit_video,
    delete_video,
    stream_video_chunk,
    stream_quality_video,
    like_video,
)
