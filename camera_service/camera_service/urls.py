"""Camera Service URL Configuration"""
from django.urls import path, include

urlpatterns = [
    path('', include('camera_api.urls')),
]
