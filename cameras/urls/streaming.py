
from django.urls import path
from .. import views

urlpatterns = [
    path('teacher-dashboard/', views.teacher_camera_dashboard, name='teacher_camera_dashboard'),
    path('control-room/<int:camera_id>/', views.teacher_control_room, name='teacher_control_room'),
    path('start-streaming/<int:camera_id>/', views.start_streaming, name='start_streaming'),
    path('stop-streaming/<int:camera_id>/', views.stop_streaming, name='stop_streaming'),
    path('update-zoom/<int:camera_id>/', views.update_zoom, name='update_zoom'),
    path('start-recording/<int:camera_id>/', views.start_camera_recording, name='start_camera_recording'),
    path('stop-recording/<int:camera_id>/', views.stop_camera_recording, name='stop_camera_recording'),
    path('publish-recording/', views.publish_recording, name='publish_recording'),
    path('mobile-mic/<int:camera_id>/', views.mobile_mic, name='mobile_mic'),
    path('live-participants/<int:camera_id>/', views.live_participants, name='live_participants'),
    path('lectures/', views.student_lecture_list, name='student_lecture_list'),
    path('watch-live/<int:camera_id>/', views.watch_live, name='watch_live'),
    path('<int:camera_id>/feed/', views.camera_feed_proxy, name='camera_feed_proxy'),
    path('clear-stream-cache/<int:camera_id>/', views.clear_stream_cache, name='clear_stream_cache'),
]
