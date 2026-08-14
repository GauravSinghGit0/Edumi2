
from django.urls import path, include
from .urls import video_urls, camera_urls, streaming_urls, permissions_urls, head_count_urls

# Combine all sub-URLconfs to maintain backward compatibility
urlpatterns = video_urls + camera_urls + streaming_urls + permissions_urls + head_count_urls
