# mobile_cameras/views/__init__.py
# Re-exports everything for backwards compatibility.
from .camera_views import (
    mobile_camera_dashboard, add_mobile_camera, delete_mobile_camera,
    mobile_camera_feed, view_mobile_camera, test_mobile_camera,
)
from .headcount_views import mobile_camera_headcount_feed
from .permission_views import grant_permission, revoke_permission, manage_permissions
