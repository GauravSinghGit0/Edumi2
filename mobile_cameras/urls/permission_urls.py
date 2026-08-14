# mobile_cameras/urls/permission_urls.py
from django.urls import path
from mobile_cameras import views

urlpatterns = [
    path('grant-permission/<int:mobile_camera_id>/',                    views.grant_permission,    name='grant_permission'),
    path('revoke-permission/<int:mobile_camera_id>/<int:teacher_id>/',  views.revoke_permission,   name='revoke_permission'),
    path('manage-permissions/<int:mobile_camera_id>/',                  views.manage_permissions,  name='manage_permissions'),
]
