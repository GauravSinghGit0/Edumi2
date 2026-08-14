# cameras/views.py  —  THIN SHIM
# All logic lives in cameras/views_logic/ sub-package.
# This file only re-exports so Django's URL resolver and any
# direct `from cameras.views import X` imports keep working.
#
# Sub-files (cameras/views_logic/):
#   utils.py            — is_admin, can_view_camera, get_video_stream, test_rtsp_paths
#   camera_views.py     — admin_dashboard, add/edit/delete camera, feed, test
#   video_views.py      — stream_video, upload, recordings, watch, playlist, teacher_profile
#   streaming_views.py  — mobile_mic, teacher dashboard, control room, streaming start/stop
#   permissions_views.py — admin_content_manager, delete_recording/meeting, grant/revoke/manage
#   head_count_views.py — head count dashboard, start/stop, logs, API, report, CSV export

from cameras.views_logic import (
    # utils
    get_video_stream, is_admin, can_view_camera, test_rtsp_paths, broadcast_live_status,
    # video
    stream_video, upload_video, camera_chunked_upload, recordings_folder, manage_recordings,
    toggle_recording_publish, watch_recording, stream_recording_chunk,
    recording_playlist, teacher_profile, delete_recording,
    update_recording_edit, apply_recording_trim, generate_recording_thumbnail,
    edit_recording,
    recording_analytics,
    like_recording,
    # camera management
    admin_dashboard, add_camera, edit_camera, delete_camera,
    camera_feed, test_camera, test_feed_page, probe_camera,
    # streaming & control
    mobile_mic, teacher_camera_dashboard, teacher_control_room, update_zoom,
    start_streaming, stop_streaming, live_participants,
    student_lecture_list, watch_live,
    start_camera_recording, stop_camera_recording, publish_recording,
    camera_feed_proxy, clear_stream_cache,
    # permissions & admin content
    admin_content_manager, delete_recording_admin, delete_meeting_admin,
    grant_permission, revoke_permission, manage_permissions,
    # head count
    head_count_dashboard, start_head_count, stop_head_count,
    head_count_logs, head_count_log_detail, head_count_session_history,
    head_count_api, head_count_report, export_head_count_csv,
)
