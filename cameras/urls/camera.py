
from django.urls import path
from .. import views

urlpatterns = [
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('add-camera/', views.add_camera, name='add_camera'),
    path('edit-camera/<int:camera_id>/', views.edit_camera, name='edit_camera'),
    path('delete-camera/<int:camera_id>/', views.delete_camera, name='delete_camera'),
    path('camera-feed/<int:camera_id>/', views.camera_feed, name='camera_feed'),
    path('test-camera/<int:camera_id>/', views.test_camera, name='test_camera'),
    path('test-feed/', views.test_feed_page, name='test_feed_page'),
    path('probe/', views.probe_camera, name='probe_camera'),
]
