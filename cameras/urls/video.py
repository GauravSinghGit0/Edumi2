
from django.urls import path
from .. import views

urlpatterns = [
    path('toggle-publish/<int:recording_id>/', views.toggle_recording_publish, name='toggle_recording_publish'),
    path('manage-recordings/', views.manage_recordings, name='manage_recordings'),
    path('manage-recordings/analytics/', views.recording_analytics, name='recording_analytics'),
    path('recordings-folder/', views.recordings_folder, name='recordings_folder'),
    path('upload-video/', views.upload_video, name='camera_upload_video'),
    path('chunked-upload/', views.camera_chunked_upload, name='camera_chunked_upload'),
    path('stream-video/<int:recording_id>/', views.stream_video, name='stream_video'),
    path('recording-playlist/<int:recording_id>/', views.recording_playlist, name='recording_playlist'),
    path('stream-chunk/<int:recording_id>/<int:sequence>/', views.stream_recording_chunk, name='stream_chunk'),
    path('delete-recording/<int:recording_id>/', views.delete_recording, name='delete_recording'),
    path('watch-recording/<int:recording_id>/', views.watch_recording, name='watch_recording'),
    path('teacher/<int:teacher_id>/', views.teacher_profile, name='teacher_profile'),
    path('update-edit/<int:recording_id>/', views.update_recording_edit, name='update_recording_edit'),
    path('apply-trim/<int:recording_id>/', views.apply_recording_trim, name='apply_recording_trim'),
    path('generate-thumbnail/<int:recording_id>/', views.generate_recording_thumbnail, name='generate_recording_thumbnail'),
    path('edit-recording/<int:recording_id>/', views.edit_recording, name='edit_recording'),
    path('recordings/like/<int:recording_id>/', views.like_recording, name='like_recording'),
]
