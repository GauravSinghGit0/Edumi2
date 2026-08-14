
from .video import urlpatterns as video_urls
from .camera import urlpatterns as camera_urls
from .streaming import urlpatterns as streaming_urls
from .permissions import urlpatterns as permissions_urls
from .head_count import urlpatterns as head_count_urls

urlpatterns = video_urls + camera_urls + streaming_urls + permissions_urls + head_count_urls
