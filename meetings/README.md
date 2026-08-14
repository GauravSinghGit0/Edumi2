# 🤝 Meetings Module

<details open>
<summary><b>1. Core Purpose</b></summary>
The `meetings` app orchestrates virtual classrooms, scheduling, and live WebRTC interactions. It acts as the bridge between the Django application and the LiveKit media server.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Centralizes all synchronous academic interactions. By offloading the actual video routing to LiveKit and maintaining only the state and permissions in Django, the system achieves massive scalability and low latency.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Scheduling**: Teachers create `Classroom` instances with specific start/end times.
- **Starting**: Teachers hit "Start Class" which generates an active `Meeting` instance.
- **Joining**: Students click "Join". The app verifies their schedule, generates a LiveKit JWT, and serves the `meeting_room.html` template.
</details>

<details>
<summary><b>4. System Integrations</b></summary>
- **LiveKit Server**: Communicates via REST APIs (`livekit_http_proxy.py`) to manage rooms and kick users.
- **Accounts App**: Verifies roles before allowing meeting creation or joins.
- **Attendance App**: Pings the attendance service when a user successfully connects or disconnects.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `models.py`: Defines `Classroom`, `Meeting`, and `MeetingParticipant`.
- `livekit_proxy.py` / `livekit_http_proxy.py`: API wrappers for communicating securely with the LiveKit backend using JWTs.
- `meeting_controls.py`: Views for host actions (mute all, disable cameras, end meeting).
- `consumers.py`: Handles WebSocket connections for in-meeting text chat and hand-raising.
</details>