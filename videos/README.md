# 📹 Videos Module & Lecture Library

<details open>
<summary><b>1. Core Purpose</b></summary>
The `videos` app handles the ingestion, storage, processing, thumbnail generation, and progressive streaming of recorded academic sessions and supplementary video materials.
</details>

<details open>
<summary><b>2. Thumbnail & Compression Pipeline</b></summary>

### Modern WebP Thumbnailing
In `videos/views_logic/utils.py`:
- `extract_thumbnail(video_path, output_path)` delegates to `EduMiCompressionService.generate_video_thumbnail_webp()`.
- Captures video frames at 1.0s, resizes to 480x270, and encodes to `.webp` at `quality=80`.
- Generates 15-25 KB thumbnails (vs 80-120 KB JPEG), decreasing lecture catalog payload weight by **~40%**.
</details>

<details>
<summary><b>3. Rationale & Architecture</b></summary>
Decoupled from live meetings to strictly handle the lifecycle of at-rest video files. It utilizes chunked uploading to support massive files (multi-gigabytes) over unstable connections, and relies on Celery for heavy transcoding tasks, ensuring the web server remains unblocked.
</details>

<details>
<summary><b>4. Usage Instructions</b></summary>

- **Uploading**: Users go to the Upload interface. Large files are broken into chunks in the browser and reassembled on the server.
- **Playback**: Users navigate to the video detail page. The backend serves the video via streaming HTTP range responses (`StreamingHttpResponse`) to support instant scrub seeking and buffer management.
</details>

<details>
<summary><b>5. System Integrations</b></summary>
- **Video Editing**: Integrates closely with `video_editing` for post-processing and timeline compilation.
- **Common App**: Uses `EduMiCompressionService` for WebP video thumbnail extraction.
- **Storage**: Reads and writes to `database/media/videos/`.
</details>

<details>
<summary><b>6. Key Files Breakdown</b></summary>

- `models.py`: Defines the `Video` model which tracks file paths, processing status, and metadata.
- `views_logic/core_views.py`: Handles the standard HTTP request/response cycle for viewing and managing videos.
- `views_logic/streaming_views.py`: Contains the logic for HTTP range requests, allowing users to scrub through large videos without downloading the entire file.
- `views_logic/utils.py`: Contains helper functions including `extract_thumbnail()` powered by `EduMiCompressionService`.
- `views.py`: The routing hub that exposes the logic defined in `views_logic/`.
</details>