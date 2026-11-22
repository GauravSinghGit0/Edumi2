"""
Video editing views module.
Phase 4.1 Refactoring: Modularized from monolithic views.py.
All endpoints are re-exported for complete backward compatibility.
"""
from .utils import (
    serve_media_ranges,
    _get_owned_project,
    _apply_new_working_file,
    extract_video_metadata,
    generate_thumbnail,
)
from .project_views import (
    project_list,
    project_detail,
    project_delete,
    project_rename,
    convert_legacy_project_to_timeline,
)
from .timeline_views import (
    op_trim,
    op_text,
    op_bg_audio,
    op_speed,
    op_split,
    op_reset,
    save_timeline,
)
from .asset_views import (
    upload_audio_temp,
    upload_asset,
    delete_asset,
    rename_asset,
    chunked_upload_view,
    proxy_status_view,
    project_filmstrip,
    project_filmstrip_frame,
    project_waveform,
)
from .export_views import (
    export_project,
    project_download,
    project_download_mkv,
    project_status,
    publish_to_lecture,
)

__all__ = [
    'serve_media_ranges',
    'project_list',
    '_get_owned_project',
    '_apply_new_working_file',
    'extract_video_metadata',
    'generate_thumbnail',
    'project_detail',
    'project_delete',
    'project_rename',
    'convert_legacy_project_to_timeline',
    'op_trim',
    'op_text',
    'op_bg_audio',
    'op_speed',
    'op_split',
    'op_reset',
    'save_timeline',
    'upload_audio_temp',
    'upload_asset',
    'delete_asset',
    'rename_asset',
    'chunked_upload_view',
    'proxy_status_view',
    'project_filmstrip',
    'project_filmstrip_frame',
    'project_waveform',
    'export_project',
    'project_download',
    'project_download_mkv',
    'project_status',
    'publish_to_lecture',
]
