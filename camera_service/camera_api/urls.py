"""Camera API URLs"""
from django.urls import path
from . import views

urlpatterns = [
    # RTSP Cameras
    path('cameras/', views.list_cameras, name='list_cameras'),
    path('cameras/<int:camera_id>/feed/', views.camera_feed, name='camera_feed'),
    path('cameras/<int:camera_id>/zoom/', views.update_camera_zoom, name='update_camera_zoom'),
    path('cameras/<int:camera_id>/test/', views.test_camera, name='test_camera'),
    
    # Mobile Cameras
    path('mobile-cameras/<int:mobile_camera_id>/feed/', views.mobile_camera_feed, name='mobile_camera_feed'),
    path('mobile-cameras/<int:mobile_camera_id>/test/', views.test_mobile_camera, name='test_mobile_camera'),
    
    # Head Counting (Microservice)
    path('head-count/start/<str:camera_type>/<int:camera_id>/', views.start_head_count, name='start_head_count'),
    path('head-count/stop/<str:camera_type>/<int:camera_id>/', views.stop_head_count, name='stop_head_count'),
    path('head-count/active-sessions/', views.active_head_count_sessions, name='active_head_count_sessions'),
]
