from django.urls import path

from . import views

urlpatterns = [
    # Projects
    path("", views.project_list, name="project_list"),
    path("upload/", views.project_list, name="project_upload"),  # kept for back-compat
    path("chunked-upload/", views.chunked_upload_view, name="chunked_upload"),
    path("project/<int:pk>/", views.project_detail, name="project_detail"),
    path("project/<int:pk>/proxy-status/", views.proxy_status_view, name="proxy_status"),
    path("project/<int:pk>/delete/", views.project_delete, name="project_delete"),
    path("project/<int:pk>/download/", views.project_download, name="project_download"),
    path("project/<int:pk>/download/mkv/", views.project_download_mkv, name="project_download_mkv"),
    path("project/<int:pk>/status/", views.project_status, name="project_status"),

    # Media range requests for smooth timeline scrubbing
    path("media-ranges/<path:path>", views.serve_media_ranges, name="serve_media_ranges"),

    # Edit operations
    path("project/<int:pk>/trim/", views.op_trim, name="op_trim"),
    path("project/<int:pk>/text/", views.op_text, name="op_text"),
    path("project/<int:pk>/background-audio/", views.op_bg_audio, name="op_bg_audio"),
    path("project/<int:pk>/rotate/", views.op_rotate, name="op_rotate"),
    path("project/<int:pk>/resize/", views.op_resize, name="op_resize"),
    path("project/<int:pk>/grayscale/", views.op_grayscale, name="op_grayscale"),
    path("project/<int:pk>/fade/", views.op_fade, name="op_fade"),
    path("project/<int:pk>/speed/", views.op_speed, name="op_speed"),
    path("project/<int:pk>/split/", views.op_split, name="op_split"),
    path("project/<int:pk>/reset/", views.op_reset, name="op_reset"),
    path("project/<int:pk>/export/", views.export_project, name="export_project"),
    path("project/<int:pk>/publish/", views.publish_to_lecture, name="publish_to_lecture"),
    path("project/<int:pk>/upload-audio/", views.upload_audio_temp, name="upload_audio_temp"),
    path("project/<int:pk>/upload-asset/", views.upload_asset, name="upload_asset"),
]
