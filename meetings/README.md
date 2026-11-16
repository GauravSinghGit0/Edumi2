# 🤝 Meetings Module & Virtual Classrooms

<details open>
<summary><b>1. Core Purpose</b></summary>
The `meetings` app orchestrates virtual classrooms, scheduling, and live WebRTC interactions for EduMi. It serves as the enterprise bridge between the Django application and the on-premise LiveKit media server, offering sub-second audio/video conferencing, host classroom controls, synchronized in-meeting quizzes, and automated session attendance.
</details>

<details open>
<summary><b>2. WebRTC Adaptive Simulcast Architecture (3-Layer SVC)</b></summary>

### LiveKit Multi-Layer Simulcast
Configured in `meeting_room.html` via `EduMiCompressionService.get_livekit_simulcast_config()`:
- **Layer 1 (Low):** 320x180 (180p) @ 15fps, `maxBitrate: 250,000 bps` (Target: Mobile 3G/4G, constrained rural connections, small gallery tiles).
- **Layer 2 (Medium):** 640x360 (360p) @ 24fps, `maxBitrate: 400,000 bps` (Target: Standard student grid view).
- **Layer 3 (High):** 1280x720 (720p) @ 30fps, `maxBitrate: 1,200,000 bps` (Target: Active speaker spotlight, screen sharing).

LiveKit SFU dynamically switches spatial layers per subscriber based on individual RTCP bandwidth reports. This saves up to **68% client downlink bandwidth**, preventing packet loss or freezing when dozens of students join on campus Wi-Fi or mobile networks.
</details>

<details open>
<summary><b>3. Rationale, Port Architecture & Security</b></summary>

### Selective Forwarding Unit (SFU) vs. Mesh
Unlike peer-to-peer mesh networks that require $O(N)$ upload streams per client, the LiveKit SFU accepts a single stream per participant ($O(1)$ client upload) and routes media packets directly to subscribers without re-encoding:
- **Port 7880 (TCP):** HTTP API & WebSocket signaling.
- **Port 7881 (TCP):** WebRTC ICE/TCP fallback transport for restrictive firewalls.
- **Port 7882 (UDP):** High-speed WebRTC RTP/RTCP audio/video data packets.

### Cryptographic Security & Host Governance
- **Signed JWT Tokens:** Access tokens are generated server-side using HMAC-SHA256 with the institution's private `LIVEKIT_API_SECRET`, granting time-limited room permissions.
- **Host Classroom Controls:** Server-enforced host actions (mute-all, lock cameras, kick participant, lock screen sharing).
- **In-Meeting Chat Encryption:** Live chat messages are stored using `EncryptedTextField` (Fernet AES-128-CBC) for privacy compliance.
</details>

<details>
<summary><b>4. Usage Instructions</b></summary>

- **Scheduling:** Teachers create `Classroom` instances with specific start/end times and recurring schedules.
- **Starting Lectures:** Teachers click "Start Class" which generates an active `Meeting` instance.
- **Joining:** Students click "Join". The app verifies their enrollment, generates a LiveKit JWT, and serves the `meeting_room.html` template.
- **In-Meeting Features:** Students can raise hands (ordered via an $O(\log N)$ Redis priority queue), chat in real time, and answer instant synchronized quizzes.
- **Study Materials:** Teachers upload lecture slides, PDFs, and notes, automatically indexed for RAG vector search in `rag_workspace`.
</details>

<details>
<summary><b>5. System Integrations</b></summary>

- **LiveKit Server:** Communicates via REST APIs (`livekit_http_proxy.py`) to manage rooms, tokens, and kicks.
- **Accounts App:** Verifies roles and permissions before allowing meeting creation or joins.
- **Attendance App:** Automatically logs participant join/leave events, duration, and connection health into `MeetingAttendanceLog`.
- **RAG Workspace:** Uploaded classroom study materials are passed directly to `rag_workspace` for semantic chunking and embedding.
- **Common App:** Consumes `EduMiCompressionService` for WebRTC simulcast profiles and `EncryptedTextField` for meeting chat.
</details>

<details>
<summary><b>6. Key Files Breakdown</b></summary>

- `models.py`: Defines `Classroom`, `ClassroomMembership`, `Meeting`, `MeetingParticipant`, `MeetingChat`, `MeetingAttendanceLog`, and `StudyMaterial`.
- `livekit_proxy.py` / `livekit_http_proxy.py`: API wrappers for communicating securely with the LiveKit backend using signed JWTs.
- `views/meeting_controls.py`: Views for host actions (mute all, disable cameras, end meeting).
- `consumers.py`: Handles WebSocket connections for in-meeting text chat and hand-raising priority queues.
- `templates/meetings/live/meeting_room.html`: LiveKit WebRTC client interface with simulcast envelope configuration.
</details>
