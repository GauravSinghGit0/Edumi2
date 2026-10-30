# 🧠 Camera Service (AI Microservice)

<details open>
<summary><b>1. Core Purpose</b></summary>
The `camera_service` is an independent AI processing microservice running on port `8008` (via Waitress). It consumes RTSP/MJPEG video streams, runs them through OpenCV YuNet + SFace neural models and head-counting algorithms, and calculates real-time room occupancy and attendance metrics.
</details>

<details open>
<summary><b>2. Rationale & Architecture</b></summary>
Computer Vision operations (such as multi-face bounding box extraction and vector embeddings) are CPU-intensive. If executed inside the main Django application worker pool, they would block the ASGI event loop and cause WebSocket latency spikes. By decoupling this into a lightweight, standalone Waitress process communicating via internal HTTP with a shared `CAMERA_SERVICE_SECRET`, the service can scale independently and crash without bringing down the main academic portal.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Execution**: Run via `python manage.py run_camera_service` or standalone Waitress on port `8008`.
- **API Interaction**: The main EduMi Django app sends internal HTTP requests to start/stop stream processing sessions and fetch occupancy headcounts.
- **Nginx Routing**: In production, Nginx proxies `/camera-service/` directly to `http://127.0.0.1:8008`.
</details>

<details>
<summary><b>4. System Integrations</b></summary>
- **Main App (`cameras`)**: Receives commands from the main `cameras` app and posts headcount snapshots back to Django.
- **Biometric Attendance**: Can feed frames into the YuNet + SFace facial recognition pipeline.
- **Compression**: Snapshot frames and thumbnails are processed and stored as lightweight WebP images via `EduMiCompressionService`.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `settings.py`: Configured to share the main project's database and media storage safely.
- `camera_api/views/streamer.py`: Manages OpenCV `VideoCapture` instances, reading RTSP feeds.
- `camera_api/views/headcount_views.py`: Executes real-time crowd head-counting with bounding boxes and occupancy tracking.
- `head_count_service.py`: Core OpenCV detection logic for head counting and crowd density estimation.
</details>