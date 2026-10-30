# 📱 Mobile Cameras Module

<details open>
<summary><b>1. Core Purpose</b></summary>
The `mobile_cameras` app allows educators to use their smartphones (via apps like IP Webcam on Android or DroidCam on iOS) as wireless IP cameras for classrooms, science labs, and lecture demonstrations.
</details>

<details open>
<summary><b>2. Rationale & Architecture</b></summary>
Hardware IP cameras are expensive and fixed to walls or ceilings. This module provides mobile flexibility, allowing an instructor to walk around a lab or lecture hall with a smartphone while EduMi streams the feed, records DVR footage, and monitors attendance in real time.
</details>

<details open>
<summary><b>3. Multimedia & Compression Pipeline</b></summary>
Mobile camera streams ingested into EduMi inherit all enterprise optimizations from `common.compression_service.EduMiCompressionService` and the `cameras` app:
- **H.265 / HEVC Archival**: Mobile lecture demonstrations recorded to disk are encoded via `libx265 -crf 28` (or `libx264 -crf 26`), cutting bandwidth and local storage by >50%.
- **WebP Snapshot Previews**: Recording thumbnails and gallery snapshots are stored as `.webp` at `quality=80`, ensuring fast preview loading on mobile devices.
</details>

<details>
<summary><b>4. Usage Instructions</b></summary>

- **Setup**: The teacher installs "IP Webcam" (Android) or "DroidCam" (iOS) and connects to the campus Wi-Fi network.
- **Linking**: In the EduMi dashboard, the teacher enters the IP address and Port shown on their smartphone.
- **Streaming & Recording**: The feed can be monitored live, injected into LiveKit meetings, or recorded to disk.
</details>

<details>
<summary><b>5. System Integrations</b></summary>
- **Cameras App**: Shares the underlying RTSP/MJPEG streaming logic and DVR recording engines.
- **Common App**: Uses `EduMiCompressionService` for H.265 compression and WebP thumbnailing.
- **Attendance & AI Service**: Feeds can be passed to the OpenCV head-counting and face recognition pipeline.
</details>

<details>
<summary><b>6. Key Files Breakdown</b></summary>

- `models.py`: Defines `MobileCamera`, mapping temporary mobile endpoints to teacher accounts.
- `views/camera_views.py`: Handles the registration, health check validation, and deletion of mobile cameras.
- `views/utils.py`: Network validation logic verifying mobile IP and port reachability before saving.
</details>