from django.urls import path
from . import views

urlpatterns = [
    path('', views.video_list, name='video_list'),
    path('upload/', views.upload_video, name='upload_video'),
    path('<int:video_id>/', views.video_detail, name='video_detail'),
    path('<int:video_id>/edit/', views.edit_video, name='edit_video'),
    path('<int:video_id>/delete/', views.delete_video, name='delete_video'),
    path('<int:video_id>/hls/master.m3u8', views.stream_hls_master, name='stream_hls_master'),
    path('<int:video_id>/hls/<str:quality_name>/playlist.m3u8', views.stream_hls_variant, name='stream_hls_variant'),
    path('<int:video_id>/hls/<str:quality_name>/<str:segment_name>', views.stream_hls_segment, name='stream_hls_segment'),
    path('quality/<int:quality_id>/stream/', views.stream_quality_video, name='stream_quality_video'),
    path('quality/<int:quality_id>/chunk/<int:chunk_number>/', views.stream_video_chunk, name='stream_video_chunk'),
    path('like/<int:video_id>/', views.like_video, name='like_video'),
]