# 🎥 Smart Classroom Cameras & Lecture Capture

<details open>
<summary><b>1. Core Purpose</b></summary>
The `cameras` app manages smart classroom hardware IP cameras (RTSP feeds from interactive panels, podiums, and labs) and mobile camera streams. It provides camera registration, teacher/admin lecture permissions, lecture recording pipelines, classroom occupancy & head-counting analytics, and optimized media storage.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Provides a centralized registry and proxy engine for classroom and studio camera hardware. Rather than opening insecure direct RTSP connections to student/teacher browsers, EduMi proxies streams internally via HTTP MJPEG/HLS and executes AI occupancy analytics on dedicated background threads. Lecture recording processes are encoded with modern compression algorithms to prevent storage exhaustion on local school servers.
</details>

<details open>
<summary><b>3. Storage & Multimedia Optimizations</b></summary>

### 1. High-Efficiency H.265 Lecture Archival
- Handled by `recording_engine.py` and `EduMiCompressionService.compress_cctv_storage()` (aliased as `compress_lecture_storage()`).
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
- **Camera Service (`camera_service`)**: Passes RTSP URLs to the background Waitress service for OpenCV head-counting and live streaming.
- **LiveKit Meetings**: RTSP streams can be routed directly into LiveKit virtual classrooms as auxiliary teacher video sources.
- **Common Compression Service**: Utilizes `common.compression_service.EduMiCompressionService` for all frame extraction and lecture transcoding.
</details>

<details>
<summary><b>6. Key Files Breakdown</b></summary>

- `models.py`: Defines `Camera`, `CameraPermission`, `CameraRecording` (with WebP thumbnail generation), and `RecordingChunk`.
- `recording_engine.py`: Manages background FFmpeg threads ripping RTSP streams to optimized H.265/H.264 containers.
- `tasks.py`: Celery workers processing post-recording operations and generating WebP previews.
- `views_logic/streaming_views.py`: Emits low-latency MJPEG feeds for browser viewing.
</details>