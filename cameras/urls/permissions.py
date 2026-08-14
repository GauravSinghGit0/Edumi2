
from django.urls import path
from .. import views

urlpatterns = [
    path('content-manager/', views.admin_content_manager, name='admin_content_manager'),
    path('delete-recording-admin/<int:recording_id>/', views.delete_recording_admin, name='delete_recording_admin'),
    path('delete-meeting-admin/<int:meeting_id>/', views.delete_meeting_admin, name='delete_meeting_admin'),
    path('grant-permission/<int:camera_id>/', views.grant_permission, name='grant_permission'),
    path('revoke-permission/<int:camera_id>/<int:teacher_id>/', views.revoke_permission, name='revoke_permission'),
    path('manage-permissions/<int:camera_id>/', views.manage_permissions, name='manage_permissions'),
]
