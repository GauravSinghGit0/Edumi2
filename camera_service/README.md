# 🧠 Camera Service (AI Microservice)

<details open>
<summary><b>1. Core Purpose</b></summary>
The `camera_service` is an independent AI processing node. It consumes RTSP/WebRTC video streams, runs them through OpenCV facial recognition models, and calculates real-time engagement and attendance metrics.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Computer Vision operations (like Dlib/OpenCV embeddings) are highly CPU intensive. If placed inside the main Django app, they would block the ASGI event loop and crash WebSockets. By separating it into its own Django service, it can scale independently and crash without bringing down the main academic portal.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Execution**: Run this service separately (often on a different port, e.g., `8003`) or in its own Docker container.
- **API Interaction**: The main app sends HTTP POST requests to this service to start/stop stream processing jobs.
</details>

<details>
<summary><b>4. System Integrations</b></summary>
- **Main App**: Receives commands from the main `attendance` app and pushes results back via WebSockets or Webhooks.
- **Database**: Mounts the exact same `database/db.sqlite3` file and `media/face_photos/` directory as the main app to ensure data consistency without heavy network serialization.
- **Cameras**: Connects directly to IP cameras via RTSP.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `settings.py`: Configured to share the main project's database (`database/db/sqlite/db.sqlite3`).
- `camera_api/views/streamer.py`: Manages OpenCV `VideoCapture` instances, pulling frames from URLs.
- `camera_api/views/headcount_views.py`: Uses Haar Cascades or HOG to count the number of faces in a frame and determine student engagement based on gaze/attention thresholds.
</details>