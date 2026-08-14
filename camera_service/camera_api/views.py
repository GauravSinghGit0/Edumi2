# camera_service/camera_api/views.py  —  THIN SHIM
# All logic lives in camera_service/camera_api/views/ sub-package.
#
# Sub-files:
#   views/streamer.py        — CameraStreamer, CameraManager (RTSP)
#   views/mobile_streamer.py — MobileCameraStreamer, MobileCameraManager
#   views/rtsp_views.py      — list_cameras, camera_feed, zoom, test_camera
#   views/mobile_views.py    — mobile_camera_feed, test_mobile_camera
#   views/headcount_views.py — start/stop/list head-count sessions

from camera_api.views.rtsp_views import (
    list_cameras, camera_feed, update_camera_zoom, test_camera,
)
from camera_api.views.mobile_views import (
    mobile_camera_feed, test_mobile_camera,
)
from camera_api.views.headcount_views import (
    start_head_count, stop_head_count, active_head_count_sessions,
)
