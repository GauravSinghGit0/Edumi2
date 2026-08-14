# mobile_cameras/urls/camera_urls.py
from django.urls import path
from mobile_cameras import views

# NOTE: app_name is set in mobile_cameras/urls/__init__.py (the package Django loads)

urlpatterns = [
    path('dashboard/',                                  views.mobile_camera_dashboard,      name='dashboard'),
    path('add/',                                        views.add_mobile_camera,            name='add'),
    path('delete/<int:mobile_camera_id>/',              views.delete_mobile_camera,         name='delete'),
    path('feed/<int:mobile_camera_id>/',                views.mobile_camera_feed,           name='feed'),
    path('feed/<int:mobile_camera_id>/headcount/',      views.mobile_camera_headcount_feed, name='headcount_feed'),
    path('view/<int:mobile_camera_id>/',                views.view_mobile_camera,           name='view'),
    path('test/<int:mobile_camera_id>/',                views.test_mobile_camera,           name='test'),
]
