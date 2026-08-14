# 📸 Attendance Module

<details open>
<summary><b>1. Core Purpose</b></summary>
The `attendance` app manages both manual and automated presence tracking. It is heavily powered by facial recognition and engagement tracking algorithms to ensure academic integrity during live sessions.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Separated from `meetings` to encapsulate heavy data processing (face encoding, L2 distance calculations). It acts as the "source of truth" for academic records, relying on asynchronous processing to prevent blocking web requests during heavy CV operations.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Student Setup**: Students must visit their profile, navigate to "Face Setup", and upload a clear reference photo.
- **Teacher View**: Teachers access `/attendance/classroom/<id>/` to view real-time presence data and export daily reports.
- **Admin**: Can enforce schedule restrictions via the `AttendanceSettings` model.
</details>

<details>
<summary><b>4. System Integrations</b></summary>
- **External/AI**: Integrates with the `camera_service` which runs OpenCV and `face_recognition`.
- **Database**: Reads/Writes to `database/media/face_photos/` for reference images.
- **Celery**: Dispatches long-running engagement aggregation tasks to background workers.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `models.py`: Contains `StudentFaceProfile` (encrypted face encodings), `AttendanceRecord`, and `StudentEngagementSnapshot`.
- `face_service.py`: Core logic for extracting 128-d face embeddings and calculating similarity thresholds.
- `encryption_service.py`: Uses Fernet symmetric encryption to secure biometric data at rest.
- `tasks.py`: Celery tasks for calculating daily attendance aggregates from raw event logs.
- `face_tracking_consumer.py`: WebSocket endpoint for receiving real-time face detection coordinates from the client/camera service.
</details>