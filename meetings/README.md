# 🤝 Meetings Module & Virtual Classrooms

<details open>
<summary><b>1. Core Purpose</b></summary>
The `meetings` app orchestrates virtual classrooms, scheduling, and live WebRTC interactions. It acts as the bridge between the Django application and the LiveKit media server, offering sub-second audio/video conferencing, classroom controls, and study material management.
</details>

<details open>
<summary><b>2. WebRTC Adaptive Simulcast Architecture (3-Layer SVC)</b></summary>

### LiveKit Multi-Layer Simulcast
Configured in `meeting_room.html` via `EduMiCompressionService.get_livekit_simulcast_config()`:
- **Layer 1 (Low)**: 320x180 (180p) @ 15fps, `maxBitrate: 250,000 bps` (Target: Mobile 3G/4G, small grid tiles)
- **Layer 2 (Medium)**: 640x360 (360p) @ 24fps, `maxBitrate: 400,000 bps` (Target: Standard student gallery view)
- **Layer 3 (High)**: 1280x720 (720p) @ 30fps, `maxBitrate: 1,200,000 bps` (Target: Active speaker spotlight, screen sharing)

LiveKit SFU dynamically switches spatial layers per subscriber based on individual RTCP bandwidth reports. This saves up to **68% client downlink bandwidth**, preventing packet loss or freezing when dozens of students join on campus Wi-Fi or mobile networks.
</details>

<details>
<summary><b>3. Rationale & Architecture</b></summary>
Centralizes all synchronous academic interactions. By offloading video routing to LiveKit SFU and maintaining only the state and permissions in Django, the system achieves massive concurrency and low latency. In-meeting chat messages are encrypted at rest using `EncryptedTextField` (AES-256).
</details>

<details>
<summary><b>4. Usage Instructions</b></summary>

- **Scheduling**: Teachers create `Classroom` instances with specific start/end times.
- **Starting**: Teachers hit "Start Class" which generates an active `Meeting` instance.
- **Joining**: Students click "Join". The app verifies their schedule, generates a LiveKit JWT, and serves the `meeting_room.html` template.
- **Study Materials**: Teachers upload lecture slides, PDFs, and notes, automatically indexed for RAG vector search.
</details>

<details>
<summary><b>5. System Integrations</b></summary>
- **LiveKit Server**: Communicates via REST APIs (`livekit_http_proxy.py`) to manage rooms, tokens, and kicks.
- **Accounts App**: Verifies roles before allowing meeting creation or joins.
- **Attendance App**: Pings the attendance service when a user successfully connects or disconnects.
- **Common App**: Consumes `EduMiCompressionService` for WebRTC simulcast profiles and `EncryptedTextField` for meeting chat.
</details>

<details>
<summary><b>6. Key Files Breakdown</b></summary>

- `models.py`: Defines `Classroom`, `Meeting`, `MeetingParticipant`, `MeetingChat`, and `StudyMaterial`.
- `livekit_proxy.py` / `livekit_http_proxy.py`: API wrappers for communicating securely with the LiveKit backend using JWTs.
- `meeting_controls.py`: Views for host actions (mute all, disable cameras, end meeting).
- `consumers.py`: Handles WebSocket connections for in-meeting text chat and hand-raising.
- `templates/meetings/live/meeting_room.html`: LiveKit WebRTC client interface with simulcast envelope configuration.
</details>