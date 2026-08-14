# 📹 Videos Module

<details open>
<summary><b>1. Core Purpose</b></summary>
The `videos` app handles the ingestion, storage, processing, and playback of recorded academic sessions and manually uploaded supplementary video materials.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Decoupled from live meetings to strictly handle the lifecycle of at-rest video files. It utilizes chunked uploading to support massive files (GBs) over unstable connections, and relies on Celery for heavy transcoding tasks, ensuring the web server remains unblocked.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Uploading**: Users go to the Upload interface. Large files are broken into chunks in the browser and reassembled on the server.
- **Playback**: Users navigate to the video detail page. The backend serves the video via streaming HTTP responses (`StreamingHttpResponse`) to support seeking and buffer management.
</details>

<details>
<summary><b>4. System Integrations</b></summary>
- **Internal**: Connects closely with `video_editing` for post-processing.
- **Storage**: Reads and writes to `database/media/videos/`.
- **Database**: Records video metadata (duration, resolution, creator) into the centralized `db.sqlite3`.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `models.py`: Defines the `Video` model which tracks file paths, processing status, and metadata.
- `views_logic/core_views.py`: Handles the standard HTTP request/response cycle for viewing and deleting videos.
- `views_logic/streaming_views.py`: Contains the logic for HTTP range requests, allowing users to scrub through large videos without downloading the entire file.
- `views.py`: The routing hub that exposes the logic defined in `views_logic/`.
</details>