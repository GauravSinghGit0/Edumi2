# 🎥 Smart Classroom Cameras & Media Library

<details open>
<summary><b>1. Core Purpose</b></summary>
The `cameras` app manages smart classroom hardware IP cameras (RTSP feeds from interactive panels, podiums, and labs), mobile studio camera streams, lecture recording capture pipelines, classroom occupancy analytics, and the unified institutional Media Library.
</details>

<details open>
<summary><b>2. Unified Media Library & Hardware Control Room</b></summary>

### 1. Unified Media Library (`/cameras/recordings/`)
- Merges the legacy Content Manager and Recordings Library into a single multi-tab media workspace:
  - **Recordings Tab**: LiveKit virtual classroom sessions and multi-track meetings.
  - **Uploaded Videos Tab**: Course materials and staff lecture uploads.
  - **Camera Recordings Tab**: Physical smart classroom recordings captured via RTSP.
- **Card & Table Metadata**: Human-formatted video duration, thumbnail preview, associated course, uploader, file size, and publication status.
- **Actions**: In-browser video preview, 1-click publish/unpublish toggle, and soft-delete with `EdumiConfirm` impact summary and `AdminAuditTrail` logging.

### 2. Live Cameras Control Room (`/cameras/admin-dashboard/`)
- Status cards for all registered smart classroom cameras:
  - **Live Online / Offline Status** with color-coded badges and last seen timestamps.
  - **Headcount Telemetry**: Current physical room occupancy derived from OpenCV stream processing.
  - **Test Connection**: Instant RTSP handshake verification button to test network reachability.
  - **Add Camera Modal**: Includes strict RTSP URL syntax validation (`rtsp://user:pass@host:port/path`) and user-friendly empty states.
  - **Dashboard Integration**: Real-time camera online/offline status is surfaced directly on the Executive Dashboard *"Needs Attention"* panel.
</details>

<details open>
<summary><b>3. Storage & Multimedia Optimizations</b></summary>

### 1. High-Efficiency H.265 Lecture Archival
- Handled by `recording_engine.py` (with distributed Redis coordinator `recording_engine_v2.py`) and `EduMiCompressionService.compress_cctv_storage()` (aliased as `compress_lecture_storage()`).
- Uses `libx265 -crf 28 -preset fast` (with automatic fallback to `libx264 -crf 26`) alongside 2.0s GOP keyframes.
- **Impact**: Reduces raw 5.2 Mbps classroom camera streams to ~1.8 Mbps, achieving **>50% disk storage savings** while maintaining sharp board readability and occupancy accuracy.

### 2. Modern WebP Thumbnailing
- Video frame extraction in `CameraRecording.generate_thumbnail()` and `generate_chunked_thumbnail()` routes through `EduMiCompressionService.generate_video_thumbnail_webp()`.
- Produces lightweight `.webp` thumbnails at 480x270 (`quality=80`), reducing file sizes by 35-40% compared to legacy JPEG frames.

### 3. Deduplicated Celery Background Tasks
- `cameras/tasks.py` (`process_recording_thumbnail`) has been cleaned of redundant raw FFmpeg subprocess calls and delegates directly to `CameraRecording.generate_thumbnail()`, ensuring single-source-of-truth logic and zero dead code.
</details>

<details>
<summary><b>4. Usage Instructions</b></summary>

- **Registration**: Admins add cameras via IP, Port, RTSP path, and credentials.
- **Permissions**: Grant classroom teachers access to room cameras via `CameraPermission`.
- **Lecture Recording**: Toggle recording sessions manually or programmatically. Footages are saved to disk with non-destructive start/end trim capabilities.
- **Head Counting**: HeadCount sessions log periodic occupancy snapshots with bounding boxes.
</details>

<details>
<summary><b>5. System Integrations</b></summary>
- **Streaming Service (`streaming_service`)**: Passes RTSP URLs to the background Waitress service for OpenCV head-counting and live streaming.
- **LiveKit Meetings**: RTSP streams can be routed directly into LiveKit virtual classrooms as auxiliary teacher video sources.
- **Common Compression Service**: Utilizes `common.compression_service.EduMiCompressionService` for all frame extraction and lecture transcoding.
</details>

<details>
<summary><b>6. Key Files Breakdown</b></summary>

- `models.py`: Defines `Camera`, `CameraPermission`, `CameraRecording` (with WebP thumbnail generation), and `RecordingChunk`.
- `recording_engine.py`: Core background FFmpeg engine capturing RTSP streams to optimized H.265/H.264 containers.
- `recording_engine_v2.py`: Scalable Redis-backed coordinator wrapping recording engine for multi-worker environments.
- `tasks.py`: Celery workers processing post-recording operations and generating WebP previews.
- `views/camera_views.py`: Camera dashboard, connection test, and hardware management endpoints.
- `views/streaming_views.py`: Emits low-latency MJPEG feeds for browser viewing.
</details>
