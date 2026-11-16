# 📸 Attendance Module & Facial Biometrics

<details open>
<summary><b>1. Core Purpose</b></summary>
The `attendance` app manages both manual and automated presence tracking for EduMi. It is powered by high-speed facial recognition and engagement tracking algorithms to ensure academic integrity during live virtual sessions and physical classrooms.
</details>

<details open>
<summary><b>2. Rationale & Architecture</b></summary>
Separated from `meetings` to encapsulate computationally intensive computer vision pipelines (face detection, 128-D vector extraction, and distance calculations). It acts as the institution's immutable "source of truth" for academic records:
- **Zero Raw Photo Retention:** When students register their face, the image is held temporarily in RAM solely for 128D extraction and then immediately destroyed. No raw facial image files are ever stored on disk.
- **Biometric Encryption at Rest:** Extracted 128-d vectors are serialized and encrypted using Fernet (`AES-128-CBC` with `HMAC-SHA256` integrity signatures). Even in the event of a database compromise, zero recognizable facial photographs can be reconstructed.
- **Asynchronous Aggregation:** Asynchronous Celery workers compile student session logs into daily attendance aggregates without blocking web request event loops.
</details>

<details open>
<summary><b>3. Biometric Verification & Matching Mathematics</b></summary>

### OpenCV Model Zoo Apache 2.0 AI Stack
1. **Face Detection (`YuNet` ONNX):** `face_detection_yunet_2023mar.onnx` detects face bounding boxes and 5 facial landmarks (eyes, nose, mouth corners) in sub-15ms on CPU.
2. **Feature Extraction (`SFace` ONNX):** `face_recognition_sface_2021dec.onnx` maps facial landmarks into a normalized 128-dimensional unit hypersphere vector $\vec{v} \in \mathbb{R}^{128}$ where $\|\vec{v}\|_2 = 1.0$.
3. **Dual Metric Verification:**
   - **Cosine Similarity:**
     $$\text{Sim}(\vec{u}, \vec{v}) = \sum_{i=1}^{128} u_i v_i \ge 0.363 \quad (\text{Official SFace Match Threshold})$$
   - **Euclidean Distance:**
     $$d(\vec{u}, \vec{v}) = \sqrt{\sum_{i=1}^{128} (u_i - v_i)^2} \le 0.55 \quad (\text{Max Distance Threshold})$$
4. **Anti-Spoofing & Liveness:**
   - `MiniFASNetV2.onnx` neural network analyzes skin texture variance and light reflection to differentiate real human faces from 2D photos, tablets, and screen replays.
   - Client-side `face-api.js` guidance directs students to align their face within an elliptical guide before capturing verification frames.
</details>

<details>
<summary><b>4. Usage Instructions</b></summary>

- **Student Setup:** Students visit their profile, navigate to "Face Setup", and complete the live camera registration.
- **Teacher View:** Teachers access `/attendance/classroom/<id>/` to view real-time presence data, attendance percentages, and export CSV/PDF reports.
- **Admin Governance:** Configure schedule restrictions and custom threshold strictness via `AttendanceSettings`.
</details>

<details>
<summary><b>5. System Integrations</b></summary>

- **Meetings App:** Verifies student identity before granting virtual classroom entry and tracks active connection duration.
- **Cameras App:** Smart classroom cameras can forward snapshot frames to verify physical classroom presence.
- **Common App:** Uses Fernet encryption fields and shared telemetry.
- **Celery:** Offloads attendance report generation and historical aggregation tasks to background workers.
</details>

<details>
<summary><b>6. Key Files Breakdown</b></summary>

- `models.py`: Contains `StudentFaceProfile` (encrypted face encodings), `AttendanceRecord`, `AttendanceSettings`, and `StudentEngagementSnapshot`.
- `face_service.py`: Core OpenCV DNN logic for YuNet detection, SFace 128-d vector extraction, and cosine/Euclidean distance matching.
- `encryption_service.py`: Transparent Fernet symmetric authenticated encryption (`AES-128-CBC` + `HMAC-SHA256`) for biometric vectors.
- `tasks.py`: Celery tasks for calculating daily attendance aggregates from raw event logs.
- `face_tracking_consumer.py`: WebSocket endpoint for receiving real-time face detection coordinates from client camera feeds.
</details>
