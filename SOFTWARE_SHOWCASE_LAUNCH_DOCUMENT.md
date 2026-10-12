# EduMi 2: Enterprise Smart Educational Operating System & Learning Management Platform
## Complete Architectural Specification, Codebase Blueprint & Software Showcase Document

---

## 1. Executive Summary & Purpose

### 1.1 What is EduMi 2?
**EduMi 2** is a comprehensive, production-hardened Educational Operating System and Learning Management System (LMS) designed to unify modern academic administration, real-time multimedia collaboration, AI-driven computer vision, and local AI study acceleration into a single cohesive platform.

Traditional academic institutions typically stitch together 5 to 7 disconnected commercial tools:
1. Video conferencing (Zoom, Google Meet, Microsoft Teams)
2. Learning management & assignments (Google Classroom, Canvas, Moodle)
3. Biometric attendance hardware (fingerprint scanners, physical punch cards)
4. Classroom surveillance & campus CCTV (isolated DVR/NVR appliances)
5. Video recording, trimming & editing software (Premiere Pro, CapCut, OBS)
6. Anti-cheating proctoring software for remote exams
7. AI study assistants & tutoring tools (external ChatGPT / Claude subscriptions)

**EduMi 2 eliminates this fragmentation entirely.** It integrates all of these capabilities into an open, secure, self-hosted web operating system that operates over local campus networks (LAN/Wi-Fi) and the public Internet (HTTPS/WSS).

---

### 1.2 Core Capabilities Matrix

| Domain | Core Functionality | Underlying Engine & Technologies |
| :--- | :--- | :--- |
| **Real-Time Video Meetings** | Ultra-low latency virtual classrooms, WebRTC audio/video mesh & SFU, screen sharing, encrypted chat, live reactions, breakout controls, and sleeping/freeze rooms | **LiveKit SFU Server** (`livekit-server`), **Django Channels 4.0**, WebRTC API, WebSocket relay proxies |
| **Biometric Attendance** | Zero-touch facial recognition attendance; anti-spoofing motion variance detection; low-light CLAHE enhancement; no raw photo persistence | **dlib**, **face_recognition**, **OpenCV**, AES-256 Fernet encrypted 128-d vector embeddings |
| **Live Facial Tracking & Engagement** | Real-time teacher HUD showing bounding boxes, student identification, and emotion detection (Focused, Happy, Tired, Confused, Distracted) | **FaceTrackingConsumer** WebSocket, 68-point facial geometry heuristics, JSON snapshots |
| **Campus CCTV & Head-Counting** | RTSP IP camera aggregation, Android (IP Webcam) & iPhone (DroidCam) integration, multi-teacher permission matrices, automated human head-counting | **OpenCV Haar cascades**, custom Daphne **Camera Microservice** (port 8008), MJPEG streaming |
| **Audio-Visual Studio & Recording** | Multi-source lecture recording (IP camera video + PC or smartphone mic), hardware-accelerated video encoding, automated 1-second video thumbnails | **FFmpeg** (`h264_nvenc`, `h264_qsv`, `h264_amf`, `libx264`), multi-threaded recording engine |
| **Cloud Video Editing Suite** | Non-linear browser video editor: trimming, cutting, volume adjustments, audio mute/unmute, text overlays, speed changes, rotation, multi-asset timelines | Custom **Timeline Compiler**, FFmpeg filter graphs, non-destructive undo/redo history |
| **Curriculum AI & RAG Engine** | Retrieval-Augmented Generation study assistant; strictly isolated to classroom uploaded materials; no internet hallucination | **nomic-embed-text** embeddings, local **Ollama** / Cloudflare / OpenAI fallback, Cosine Similarity reranker |
| **Academic LMS & Proctoring** | Classrooms, schedules, assignments with file uploads, deadline tracking, quizzes with anti-cheat proctoring (tab-switch tracking, copy alerts) | Django ORM, PostgreSQL / SQLite auto-failover, WebSocket proctoring alerts |
| **Enterprise Security & Telemetry** | Centralized Identity SSOT, AES-256 data-at-rest encryption, dated forensic logs, attack detection WAF (SQLi, XSS, Path Traversal) | `SystemPerformanceLoggingMiddleware`, Fernet `EncryptedTextField`, SHA-256 OTP hashing |

---

## 2. High-Level Architecture & System Topography

EduMi 2 is structured as a modular, event-driven service-oriented architecture running on Django 4.2 LTS and ASGI (Daphne). It supports both **distributed containerized production deployments** (Ubuntu / Debian / Docker) and **one-click unified developer deployments** (Windows PowerShell / Batch).

```
                            [ USER AGENTS ]
       (Teachers, Students, Administrators, IP Webcams, Smart Phones)
                                   │
                                   │ HTTPS (443) / WSS
                                   ▼
                       ┌────────────────────────┐
                       │   NGINX REVERSE PROXY   │  (TLS Termination, Rate Limiting,
                       │ (Brotli/Gzip, Cache)   │   Byte-range video streaming)
                       └───────────┬────────────┘
                                   │
        ┌──────────────────────────┼───────────────────────────┐
        │                          │                           │
        ▼ (Port 7880 /ws)          ▼ (/cameras/ /head-count/)  ▼ (Port 8002-8007)
┌───────────────┐          ┌───────────────┐          ┌─────────────────────────┐
│ LIVEKIT SFU   │          │ CAMERA ENGINE │          │ DAPHNE ASGI CLUSTER     │
│ MEDIA SERVER  │          │ MICROSERVICE  │          │ (Django Channels HTTP & │
│ (RTC/WebRTC)  │          │ (Daphne:8008) │          │  WebSocket Workers)     │
└───────┬───────┘          └───────┬───────┘          └────────────┬────────────┘
        │                          │                               │
        │                          │    ┌──────────────────────────┘
        │                          │    ▼
        │                  ┌──────────────────┐
        │                  │ REDIS 7 INSTANCE │
        │                  │ (Channel Layer,  │
        │                  │  Celery Broker,  │
        │                  │  Cache SSOT)     │
        │                  └────────┬─────────┘
        │                           │
        ▼                           ▼
┌──────────────────┐       ┌──────────────────┐       ┌─────────────────────────┐
│ HARDWARE CAMERAS │       │ CELERY WORKERS   │       │ DATABASE STORAGE        │
│ RTSP, IP-Webcam, │       │ (Async Video     │       │ PostgreSQL 15 Primary   │
│ DroidCam Streams │       │  Processing, RAG)│       │ (SQLite Dev Fallback)   │
└──────────────────┘       └──────────────────┘       └─────────────────────────┘
```

---

## 3. Comprehensive Application Breakdown

The codebase is organized into modular Django applications, each owning distinct operational boundaries.

### 3.1 `accounts` — Identity, Authentication & Administrative Core
The `accounts` app serves as the backbone of user identity, security, authentication, and inter-user communication across the system.

#### Key Architectural Components:
1. **User Roles**: Supports three first-class user roles:
   - `admin`: Full administrative control, system metrics, hardware camera permissions, audit logs, and account management.
   - `teacher`: Classroom creation, meeting hosting, live camera switching, attendance reporting, video recording/editing, assignment grading, and quiz proctoring.
   - `student`: Classroom enrollment, virtual meeting participation, biometric face registration, assignment submission, quiz participation, and RAG study workspace access.
2. **Centralized Identity Service (`accounts/identity.py`)**:
   - Acts as the **Single Source of Truth (SSOT)** for all identity lookups across all applications.
   - Implements `IdentityService.get_identity(user)` and `IdentityService.get_identity_by_id(user_id)`.
   - Normalizes usernames, avatar fallbacks (`ui-avatars.com`), roles, contact numbers, biometric face registration states, and enrollment IDs into a high-performance dictionary cached in Redis (10-minute TTL).
   - Features `get_identities_batch(user_ids)` which resolves up to 100 user profiles in a single query.
3. **Database-Backed Email Verification OTPs (`EmailVerificationOTP`)**:
   - Secures account registration and email changes.
   - Generates cryptographically secure 6-digit verification codes.
   - Persists only **SHA-256 hashes** (`otp_hash`), strictly enforcing a 5-minute Time-To-Live (TTL), single-use invalidation (`is_used`), and max attempt throttling.
4. **Direct Messaging Engine (`Conversation`, `Message`)**:
   - Real-time 1-on-1 private messaging and classroom-wide group messaging.
   - Messages are transparently encrypted at rest with AES-256 Fernet cryptography (`EncryptedTextField`).
   - Supports image/attachment uploads and unread badge counters.
5. **Universal Notification System (`Notification`)**:
   - Dispatches in-app notifications across 11 distinct event triggers:
     - `message`, `meeting_scheduled`, `meeting_started`, `meeting_cancelled`
     - `classroom_joined`, `classroom_approved`, `classroom_denied`, `classroom_removed`
     - `student_joined`, `meeting_reminder`, and `system` broadcast notices.
6. **Administrative Management Control Center**:
   - Comprehensive administrative views for browsing students, teachers, active meetings, virtual classrooms, student verification photo archives, and real-time activity feeds.

---

### 3.2 `attendance` — Biometric Computer Vision & Engagement Analytics
The `attendance` app provides enterprise facial recognition attendance verification and classroom engagement monitoring without violating student privacy.

#### Architectural Principles:
1. **Privacy-Preserving Vector Storage (`StudentFaceProfile`)**:
   - Students register their facial biometric profile through a guided webcam capture interface (`templates/attendance/face_setup.html`).
   - The face embedding (a 128-dimensional floating-point vector) is extracted using `face_recognition` with the 68-landmark 'large' model.
   - **The raw photo is NEVER stored on disk for recognition.** The 128-d float array is serialized to JSON and encrypted using **AES-256 CBC with HMAC-SHA256 authenticated encryption** (`face_embedding_encrypted`).
   - An integrity checksum (`SHA-256`) is stored alongside the encrypted payload to ensure vectors cannot be tampered with.
2. **Anti-Spoofing & Liveness Pipeline (`FaceService`)**:
   - **Low-Light Adaptive Equalization**: Automatically assesses frame brightness; if brightness is below threshold (<65), it runs CLAHE (Contrast Limited Adaptive Histogram Equalization) in LAB color space to preserve edge contrast.
   - **Motion Liveness Detection**: Compares consecutive webcam frames (`MIN_MOTION_DIFF = 1.5`). A flat printed photograph or static mobile screen held in front of the lens exhibits near-zero inter-frame delta, triggering anti-spoof rejection.
   - **Pixel Variance Checking**: Evaluates standard deviation across color channels (`MIN_LIVENESS_VARIANCE = 6.0`) to catch low-frequency screen captures.
   - **Cosine / Euclidean Match Distance**: Evaluates face distance against stored vectors using `MATCH_THRESHOLD` (default 0.55).
   - **OpenCV Haar Fallback**: If the heavy `face_recognition` / `dlib` library is unavailable on low-power devices, the system automatically falls back to an OpenCV equalized 8x8 grayscale + Sobel edge gradient pseudo-embedding vector.
3. **Teacher Real-Time HUD (`FaceTrackingConsumer`)**:
   - A dedicated WebSocket endpoint (`ws/face-tracking/<meeting_code>/`) streams video frame snapshots from student tiles to the server.
   - Computes facial landmarks and categorizes student emotion/attention:
     - 🎯 **Focused**: Head erect, eyes oriented forward.
     - 😊 **Happy**: Mouth corners upturned, relaxed cheeks.
     - 😲 **Surprised**: Elevated eyebrow geometry and open mouth.
     - 😴 **Tired / Sleeping**: Closed eyelids, drooping head angle.
     - 🤔 **Confused**: Furrowed brow, asymmetrical landmark shift.
     - 😶 **Distracted**: Sustained yaw/pitch deviation away from display.
4. **Auditing & Reporting**:
   - `AttendanceRecord`: Captures present/absent/late status, verified timestamp, match confidence score, and teacher manual override audit logs.
   - `EngagementReport`: Post-meeting analytical summary aggregating total attention score, focus percentages, and participation graphs for the entire classroom.
   - `FaceResetRequest`: Formal administrative ticketing workflow allowing students to request re-registration if their biometric verification fails or their appearance changes.

---

### 3.3 `meetings` — WebRTC Virtual Classrooms & LiveKit SFU Collaboration
The `meetings` app handles real-time audio/video transmission, screen sharing, classroom collaboration, and curriculum resource management.

#### Architectural Infrastructure:
1. **LiveKit SFU Integration**:
   - Leverages a compiled, standalone **LiveKit SFU server binary** (`livekit-server.exe` on Windows or Linux daemon) communicating via UDP/TCP on ports 7880–7882.
   - Automatically detects host LAN IP and binds dynamic STUN servers (`stun.l.google.com:19302`) so devices across local Wi-Fi or the Internet can join without NAT hairpin issues.
   - Implements internal HTTP/WebSocket proxies (`LiveKitProxyConsumer`, `livekit_http_proxy`) inside Django Channels. Clients connect to `/livekit-proxy/`, and Django handles authorization tokens and transparently proxies traffic to LiveKit.
2. **WebSocket Signalling & Controls (`MeetingConsumer`)**:
   - Handles room join/leave broadcasts, WebRTC offer/answer/ICE candidate relays, lip-sync audio packages (`av_sync_package`), encrypted live chat (`MeetingChat`), and participant rosters.
   - **Meeting Sleep / Freeze Mode**: Teachers can freeze/sleep meetings to pause all media streams and interaction while preserving room state.
   - **Duration Expiration & Continuation**: Automatically monitors meeting schedules. When time limits expire, prompts host with continue/end dialogs, gracefully ending stale meetings.
   - **Host Moderation**: Global mute (`global_mute`), global camera deactivation, student screenshare lockdown, and temporary/permanent user kick actions (`KickedParticipant`).
3. **Classroom Lifecycle (`Classroom`, `ClassroomMembership`)**:
   - Persistent digital spaces bound to courses or subjects.
   - Supports teacher auto-approval or manual approval queues (`pending`, `approved`, `denied`).
   - Generates persistent group discussion channels across members.
4. **Digital Study Library & Curriculum Units**:
   - `MaterialUnit`: Organizes course content into sequential curriculum chapters.
   - `StudyMaterial`: Stores documents (PDF, DOCX), lecture notes (Markdown), presentation slides, recorded video links, and books.
   - Tracks download metrics, view counts, and student personal bookmarks (`MaterialBookmark`).

---

### 3.4 `assignments` — Coursework Submission & Live Quiz Proctoring
The `assignments` app provides coursework distribution and automated exam grading with built-in anti-cheat proctoring.

#### Key Models & Capabilities:
1. **Assignments (`Assignment`, `AssignmentSubmission`)**:
   - Teachers publish coursework with instruction files, links, total marks, and due dates.
   - Students upload submission documents and links.
   - Automatically detects submission timing: marks entries submitted after the deadline as `late`.
   - Teachers evaluate submissions, assign marks, and provide written feedback.
2. **Quizzes & Automated Assessment (`Quiz`, `Question`, `Choice`)**:
   - Supports Multiple Choice Questions (MCQ) with image attachments and descriptive text-answer questions.
   - Automatic grading for MCQs; manual evaluation workflow for free-form text answers.
3. **Remote Proctoring & Anti-Cheat Telemetry**:
   - `QuizSubmission` tracks exam integrity metrics:
     - `started_at` & `time_taken_seconds`: Exact stopwatch tracking with auto-submission when timer expires.
     - `tab_switch_count`: Browser focus monitoring detects when a student switches tabs or minimizes the exam window.
     - **Live Proctoring Alerts**: WebSocket events (`quiz_tab_switch_warning`, `quiz_copy_warning`) notify the teacher's dashboard in real-time when a student copies text or leaves the examination tab.

---

### 3.5 `cameras` & `mobile_cameras` — Campus Surveillance, RTSP & Head Counting
The `cameras` suite transforms commodity hardware into an enterprise security and automated attendance monitoring network.

#### System Architecture:
1. **Multi-Protocol Camera Ingestion**:
   - **RTSP Cameras**: IP cameras, NVRs, and security cameras streaming via `rtsp://`.
   - **IP Webcam (Android)**: Smartphone cameras streaming MJPEG video via `http://<ip>:8080/video`.
   - **DroidCam (iPhone/iOS)**: Smartphone video feeds via `http://<ip>:4747/mjpegfeed`.
2. **Dedicated Camera Microservice (`camera_service/serve.py`)**:
   - Operates as an independent Daphne ASGI microservice on port **8008** (or 8003 in container mode).
   - Isolates CPU-intensive MJPEG decoding, dynamic digital PTZ zoom scaling, and video transcoding from the main Django application to prevent UI stutter.
3. **Automated Classroom Head-Counting (`HeadCountService`)**:
   - Runs background computer vision scans over camera streams.
   - Detects human heads using multi-scale Haar cascades, draws bounding boxes, records count metrics, and saves annotated snapshots (`HeadCountLog`).
   - Grouped into sessions (`HeadCountSession`) providing classroom statistics: average occupancy, peak attendance, and minimum headcount.
4. **FFmpeg Multi-Threaded Recording Engine (`RecordingEngine`)**:
   - Records live camera feeds with synchronized audio.
   - **Audio Source Multiplexing**: Captures audio directly from the camera feed, from the teacher's PC microphone, or wirelessly from a smartphone running the mobile mic client (`templates/cameras/control_room/mobile_mic.html`).
   - **Hardware Acceleration Detection**: Dynamically inspects available GPUs and selects the optimal video encoder:
     - NVIDIA NVENC (`h264_nvenc`)
     - Intel QuickSync (`h264_qsv`)
     - AMD AMF (`h264_amf`)
     - Software fallback (`libx264`)
   - **Chunked Storage (`RecordingChunk`)**: Writes video into 10-second Transport Stream (`.ts`) binary chunks stored directly in the database. Enables instant preview, crash-resilient recordings, and automated thumbnail extraction.

---

### 3.6 `videos` & `video_editing` — HLS Streaming & Cloud Video Editor
The media subsystem provides video on demand (VOD) streaming and an integrated non-linear video editing studio.

#### 1. Streaming Infrastructure (`videos`):
- `Video`: Master video entity tracking view count, duration, and metadata.
- Multi-Quality Transcoding (`VideoQuality`): Generates 1080p, 720p, 480p, and 360p renditions using H.264/H.265.
- HLS Video Delivery (`VideoChunk`): Splits videos into 10-second segments with master `.m3u8` playlists for adaptive bitrate streaming over HTTP.

#### 2. Non-Linear Cloud Video Editor (`video_editing`):
A browser-based video editing suite built with HTML5 Canvas, Web Audio API, and server-side FFmpeg processing.
- `VideoProject`: Stores the original master file and the current working file.
- `ProjectAsset`: Multi-track media library holding auxiliary B-roll videos, audio tracks, and graphic overlays.
- `EditOperation`: Complete non-destructive undo/redo history tracking:
  - **Trim & Cut**: Precision sub-second timeline clipping.
  - **Audio Controls**: Mute, unmute, and fine-grained volume amplification.
  - **Transformations**: Video rotation (90°, 180°, 270°), resolution scaling, speed ramping (0.5x, 1.0x, 1.5x, 2.0x).
  - **Effects & Overlays**: Text overlays, watermarks, grayscale filters, and video fade-in/fade-out transitions.
- `timeline_compiler.py`: Compiles timeline states into optimized FFmpeg filtergraph commands, rendering new working files asynchronously.

---

### 3.7 `rag_workspace` — Curriculum-Isolated AI Study Assistant
The `rag_workspace` provides an intelligent tutoring system powered by Retrieval-Augmented Generation (RAG).

#### Technical Implementation:
1. **Strict Curriculum Isolation**:
   - Generic AI chatbots frequently hallucinate or provide information outside the institution's syllabus.
   - EduMi 2's RAG workspace operates in **Strict Mode**: the LLM answers queries **exclusively** using text extracted from documents uploaded to the classroom's digital library (`StudyMaterial`).
   - If information is absent from course materials, the model explicitly notifies the student rather than hallucinating external facts.
2. **Dense Vector Search Pipeline**:
   - Uploaded study documents (PDF, DOCX, Markdown, plain text) are parsed into semantic chunks (`MaterialChunk`, 500–1000 tokens).
   - Generates 768-dimensional dense vector embeddings using **`nomic-embed-text:latest`** hosted on local **Ollama** instances (`http://127.0.0.1:11434`) or OpenAI fallback.
   - Implements a circuit-breaker mechanism: if the embedding server is unreachable, disables embeddings for 30 seconds to prevent worker thread starvation.
3. **Multi-Stage Retrieval & Reranking**:
   - **Stage 1 (Candidate Pooling)**: Computes Cosine Similarity between user query embeddings and stored document vectors, selecting the top 20 candidate chunks (`RAG_TOP_K_INITIAL = 20`).
   - **Stage 2 (Similarity Floor)**: Filters out chunks below a 0.08 similarity floor.
   - **Stage 3 (Reranking & Pruning)**: Reranks candidate chunks with an elevated threshold (0.12), selecting the top 8 most relevant passages (`RAG_MAX_FINAL_CHUNKS = 8`).
   - **Stage 4 (Keyword Fallback)**: If vector search returns zero results, executes an automated BM25 / keyword fallback over indexed material text.
4. **Five Specialized Educational Modes**:
   - 💬 **Ask**: Direct question-and-answer with precise page and document citations.
   - 📖 **Explain**: Deep conceptual breakdowns configured at three difficulty levels: *Simple*, *Detailed*, or *Exam Prep*.
   - 📝 **Summarize**: Generates bulleted summaries, formulas, and essential takeaways.
   - ❓ **Practice Quiz**: Automatically generates diagnostic questions based on course readings.
   - 🎯 **Study & Revision**: Creates structured study guides and key-term glossaries.
5. **Instructor Governance (`RagInstructorSetting`)**:
   - Teachers configure student access to specific features per classroom: enable/disable outside knowledge, toggle quiz generation, or enforce strict material boundaries.

---

### 3.8 `common` — Cryptography, Telemetry & Cyber Forensics
The `common` app contains enterprise utilities, encryption services, and security middleware.

#### 1. Cryptography Engine (`common/encryption.py`):
- Implements authenticated encryption using **Fernet (AES-256 CBC with HMAC-SHA256)**.
- Encryption keys are derived deterministically from the production `SECRET_KEY` or loaded from `MESSAGE_ENCRYPTION_KEY`.
- `EncryptedTextField`: A custom Django model field that automatically encrypts plaintext on database insert and decrypts upon model query. Ciphertexts are prefixed with `ENC:`.

#### 2. Forensic Logging Engine (`common/telemetry.py`):
EduMi 2 organizes all logs into daily dated directories:
```
logs/
  └── <YYYY-MM-DD>/
        ├── access.log              # Full HTTP access log with latency and RAM usage
        ├── user_interactions.log   # Human-readable clickstream
        ├── user_interactions.jsonl # Machine-readable event stream
        ├── activity_audit.jsonl    # Master forensic audit trail
        ├── security_audit.log      # WAF alerts: SQLi, XSS, Path Traversal attempts
        ├── crash_reports.log       # Deep crash forensics with full stack traces
        ├── performance.log         # Slow queries and latency warnings
        └── meetings_quiz.log       # Live meeting and exam proctoring events
```

#### 3. Proactive Attack Detection (Web Application Firewall):
`SystemPerformanceLoggingMiddleware` inspects every incoming HTTP request for malicious patterns:
- **SQL Injection (SQLi)**: Regex matching `UNION SELECT`, `OR 1=1`, `' OR ''='`, and SQL meta-characters.
- **Cross-Site Scripting (XSS)**: Flags `<script>`, `javascript:`, `onerror=`, `onload=`, and raw HTML tags in inputs.
- **Path Traversal**: Flags `../`, `..\\`, `/etc/passwd`, and system file patterns.
- **Vulnerability Scanners**: Detects reconnaissance bots querying `wp-login`, `.env`, `phpmyadmin`, or `/actuator`.
- When an attack pattern is detected, the event is immediately recorded in `security_audit.log` alongside client IP, User-Agent, user ID, and full payload context.

---

## 4. Database Architecture & Data Models Summary

Below is an overview of the core database models across the application:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             DATABASE MODELS                                 │
├──────────────────────┬──────────────────────────────────────────────────────┤
│ App                  │ Model Entities                                       │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ accounts             │ UserProfile, EmailVerificationOTP, StudentPhoto,     │
│                      │ UserAchievement, Conversation, Message, Notification │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ attendance           │ StudentFaceProfile, ClassSchedule, AttendanceRecord, │
│                      │ FaceRecognitionLog, AttendanceSettings,              │
│                      │ EngagementReport, StudentEngagementSnapshot,        │
│                      │ FaceResetRequest                                     │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ meetings             │ Classroom, ClassroomMembership, Meeting,             │
│                      │ MeetingParticipant, MeetingAttendanceLog,            │
│                      │ MeetingChat, MeetingSummary, KickedParticipant,       │
│                      │ MaterialUnit, StudyMaterial, MaterialChunk,          │
│                      │ MaterialBookmark                                     │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ assignments          │ Assignment, AssignmentQuestionFile,                  │
│                      │ AssignmentSubmission, AssignmentSubmissionFile,      │
│                      │ Quiz, Question, Choice, QuizSubmission,             │
│                      │ StudentAnswer                                        │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ cameras              │ Camera, CameraPermission, CameraRecording,           │
│                      │ RecordingChunk, HeadCountLog, HeadCountSession       │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ mobile_cameras       │ MobileCamera, MobileCameraPermission                 │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ videos               │ Video, VideoQuality, VideoChunk                      │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ video_editing        │ VideoProject, ProjectAsset, EditOperation            │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ rag_workspace        │ RagSession, RagQueryLog, RagChatMessage,             │
│                      │ RagInstructorSetting                                 │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ common               │ UserActivityLog                                      │
└──────────────────────┴──────────────────────────────────────────────────────┘
```

---

## 5. Security & Cryptographic Standards

1. **Authentication & Session Security**:
   - Password hashing via PBKDF2 with SHA-256 (Django default).
   - Rate-limited login endpoints (Nginx: 5 requests/sec burst 10).
   - Session cookies configured with `HttpOnly=True`, `SameSite='Lax'`, and an 8-hour lifespan.
   - Production HTTPS enforcement: `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS=31536000`, HSTS preload, and sub-domain inclusion.
2. **Encrypted Communications**:
   - Real-time video/audio streams encrypted with DTLS-SRTP via LiveKit SFU.
   - HTTPS / WSS communication terminated with TLS 1.2/1.3.
3. **Data-at-Rest Protection**:
   - Biometric face embeddings: AES-256 Fernet authenticated encryption with SHA-256 integrity checksums.
   - Chat and private messages: AES-256 Fernet field-level encryption.
   - Email verification OTPs: One-way SHA-256 salted hashes.
4. **Network & Web Security**:
   - `X-Frame-Options: DENY` (clickjacking defense).
   - `X-Content-Type-Options: nosniff` (MIME sniffing defense).
   - Strict CSRF protection with origin validation on all state-changing endpoints.
   - Automated server-side file validation enforcing MIME type, extension, and file size checks on all uploads.

---

## 6. Execution, Deployment & Infrastructure Guide

### 6.1 Windows Development & Campus Demonstration Launch
The application includes a unified PowerShell launcher (`start_app.ps1`) that orchestrates all services from a single console:

```powershell
# Run from repository root
.\start_app.ps1
```

#### What `start_app.ps1` executes automatically:
1. **Port Cleanup**: Terminates stale processes on ports `8002`, `8003`, `8008`, `7880`, `7881`, and `7882`.
2. **Environment & Logs**: Validates virtual environment (`venv`), creates daily dated log directory (`logs/<YYYY-MM-DD>/`).
3. **LiveKit SFU Configuration**: Inspects local network adapters, resolves the machine's LAN IP, and updates `config/livekit.yaml` with STUN and dynamic node bindings.
4. **Database Migrations**: Runs `python manage.py migrate --noinput`.
5. **Static Assets**: Executes `collectstatic` and `compress --force` for offline CSS/JS bundling.
6. **Background Services**:
   - Launches `livekit-server.exe` on port `7880`.
   - Launches the Camera Microservice (`camera_service/serve.py`) on port `8008`.
   - Launches the Celery worker thread pool for background tasks.
7. **Main Application**: Starts the Daphne ASGI application server on port `8002` via `run_ssl_server.py`.
8. **Graceful Teardown**: Intercepts `Ctrl+C` to terminate all background child processes and release network sockets.

---

### 6.2 Linux Production Deployment (`deploy.sh`)
For dedicated production servers (Ubuntu 20.04 / 22.04 / 24.04 LTS or Debian 11/12), `deploy.sh` provisions a complete systemd-managed environment:

```bash
sudo bash deploy.sh --domain your-domain.com --email admin@your-domain.com
```

#### Production Architecture Provisioned by `deploy.sh`:
- **Database**: PostgreSQL 15 server (`edumi_db`) with optimized connection pooling.
- **Cache & Channel Layer**: Redis 7 server running on port `6379`.
- **Systemd Microservices**:
  - `edumi-livekit.service`: Native LiveKit SFU media server.
  - `edumi-camera.service`: Dedicated Daphne camera transcode worker (port 8008).
  - `edumi-celery.service`: Multi-threaded background task worker.
  - `edumi-auth.service` through `edumi-video.service`: 6 load-balanced Daphne ASGI instances across ports `8002`–`8007`.
- **Nginx Reverse Proxy**:
  - Automatically redirects HTTP port 80 to HTTPS port 443.
  - TLS 1.2 / 1.3 encryption with Let's Encrypt or auto-generated institutional SSL certificates.
  - Zero-copy media streaming (`sendfile on; tcp_nopush on;`) with HTTP byte-range seeking.
  - WebSocket proxying for `/ws/` and `/livekit-proxy/`.
  - Rate-limiting rules protecting authentication and API endpoints.

---

### 6.3 Docker Compose Multi-Container Deployment
A containerized deployment is available via `docker-compose.yml`:

```bash
docker compose up -d --build
```

#### Containers in the Compose Stack:
- `edumi_db`: PostgreSQL 15 Alpine with persistent volume storage.
- `edumi_redis`: Redis 7 Alpine message broker and cache.
- `edumi_livekit`: Official LiveKit SFU media server.
- `edumi_auth` ... `edumi_video`: 6 discrete Daphne ASGI containers divided by logical service domain.
- `edumi_camera`: Dedicated camera microservice container.
- `edumi_celery`: Celery background worker container.
- `edumi_nginx`: Nginx Alpine reverse proxy terminating SSL and routing traffic.

---

## 7. Key Technology Stack Reference

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          TECHNOLOGY STACK SUMMARY                           │
├──────────────────────┬──────────────────────────────────────────────────────┤
│ Layer                │ Technologies                                         │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ Backend Framework    │ Django 4.2 LTS (Python 3.10+), ASGI Architecture     │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ Real-Time Networking │ Django Channels 4.0, Daphne 4.0, LiveKit SFU, WebSockets│
├──────────────────────┼──────────────────────────────────────────────────────┤
│ Database & Cache     │ PostgreSQL 15, SQLite 3 (Dev Fallback), Redis 7      │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ Task Queue           │ Celery 5.3 + Redis Broker                            │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ Computer Vision & AI │ OpenCV (cv2), dlib, face_recognition (68 landmarks), │
│                      │ nomic-embed-text (Ollama), Cosine Reranker           │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ Media & Transcoding  │ FFmpeg, FFprobe (h264_nvenc, qsv, amf, libx264, HLS) │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ Frontend Stack       │ Vanilla JavaScript (ES6+), HTML5 Canvas, Web Audio,  │
│                      │ Django Templates, WhiteNoise, Django Compressor      │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ Web Server & Proxy   │ Nginx (HTTP/2, TLS 1.3, Brotli, Gzip, Rate Limiting) │
├──────────────────────┼──────────────────────────────────────────────────────┤
│ Operating Systems    │ Windows 10/11, Ubuntu Server 20.04/22.04/24.04, Docker│
└──────────────────────┴──────────────────────────────────────────────────────┘
```

---

## 8. Summary & Project Significance

**EduMi 2** demonstrates how modern web engineering, real-time multimedia protocols, and localized computer vision can be integrated into an elegant, scalable academic operating system.

By unifying virtual classrooms, biometric security, CCTV surveillance, multi-track video editing, and syllabus-grounded AI tutoring within a single architecture, EduMi 2 provides an end-to-end platform for modern educational institutions—ensuring data privacy, operational independence, and cost efficiency.
