# 📱 Mobile Cameras Module

<details open>
<summary><b>1. Core Purpose</b></summary>
The `mobile_cameras` app allows educators to use their smartphones (via apps like IP Webcam or DroidCam) as temporary, wireless IP cameras for the platform.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Hardware IP cameras are expensive and fixed. This module provides extreme flexibility, allowing a teacher to walk around a lab or classroom with a phone while the system tracks attendance and records the feed.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Setup**: The teacher installs "IP Webcam" on their phone and connects to the local network.
- **Linking**: In the EduMi2 dashboard, the teacher enters the IP and Port provided by the mobile app.
- **Streaming**: The system treats this exactly like a hardware IP camera.
</details>

<details>
<summary><b>4. System Integrations</b></summary>
- **Cameras App**: Shares the same underlying streaming logic and recording engines as the main `cameras` app.
- **Attendance**: Feeds can be passed to the AI engine for face recognition.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `models.py`: Defines `MobileCamera`, mapping temporary IP addresses to specific user accounts.
- `views/camera_views.py`: Handles the registration, validation, and deletion of temporary mobile endpoints.
- `views/utils.py`: Contains network validation logic to ensure the provided mobile IP is reachable before saving to the database.
</details>