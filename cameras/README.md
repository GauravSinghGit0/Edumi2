# 🎥 Cameras Module

<details open>
<summary><b>1. Core Purpose</b></summary>
The `cameras` app manages hardware IP cameras (RTSP feeds). It allows administrators to register physical cameras installed in classrooms, assign viewing permissions, and trigger DVR-style recordings.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Provides a centralized registry for all physical monitoring hardware. It abstracts away complex RTSP URLs, allowing users to view feeds natively in the browser by proxying the feed through HTTP streaming.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Registration**: Admins add a camera by providing an IP, Port, Username, Password, and RTSP path.
- **Permissions**: Use the `CameraPermission` model to grant specific Teachers or Admins access to specific cameras.
- **Recording**: Trigger the recording engine to capture the feed to the local disk.
</details>

<details>
<summary><b>4. System Integrations</b></summary>
- **Camera Service**: Passes RTSP URLs to the `camera_service` for facial recognition and headcount analytics.
- **Meetings**: Can optionally inject hardware camera feeds directly into LiveKit virtual classrooms.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `models.py`: Defines `Camera`, `CameraPermission`, and `CameraRecording`.
- `recording_engine.py`: Manages background threads that use FFmpeg to rip RTSP streams to `.mp4` chunks.
- `views_logic/streaming_views.py`: Generates MJPEG streams (`multipart/x-mixed-replace`) by continuously yielding frames from OpenCV, allowing RTSP to be viewed in a standard HTML `<img>` tag.
</details>