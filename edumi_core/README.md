# ⚙️ Edumi Core (`edumi_core`) — Master Configuration & ASGI Engine

<details open>
<summary><b>1. Core Purpose</b></summary>
The `edumi_core` directory is the central Django configuration root for EduMi. It coordinates all modular applications, binds ASGI and WSGI entry points, configures the dual-database architecture, orchestrates Celery distributed tasks, injects global context processors (including Granular RBAC permissions), and enforces institutional security policies.
</details>

<details open>
<summary><b>2. Rationale & Architecture</b></summary>

### 1. Daphne ASGI & WebSockets Engine (`asgi.py`)
Configures asynchronous protocol routing via Django Channels:
- **HTTP / HTTPS Traffic:** Routed directly to the standard Django application handler.
- **WebSocket (`ws://` / `wss://`) Traffic:** Authenticated via `AuthMiddlewareStack` and routed to URL routers in `accounts`, `meetings`, `attendance`, and `cameras`.
- Runs via Daphne on port `8002`, multiplexing thousands of concurrent real-time connections without worker starvation.

### 2. Dual Database Resilient Architecture
- **Primary Production Engine:** PostgreSQL 15+ configured via `DATABASE_URL` in `.env`, providing full ACID transactions and relational integrity.
- **Automated Self-Healing Fallback:** If PostgreSQL is unreachable during local offline testing or container reboots, the system automatically routes to local SQLite storage without dropping the web server process.

### 3. Distributed Task Queue (`celery.py`)
- Initializes Celery 5.3 with Redis broker (`redis://127.0.0.1:6379/0`).
- Auto-discovers asynchronous tasks across all installed apps:
  - `accounts.tasks.admin_import_users_task` (Asynchronous bulk user CSV onboarding)
  - Video proxy transcoding, audio waveform extraction, and lecture archival tasks.

### 4. Enterprise Context Processors (`settings.py`)
- `accounts.context_processors.admin_permissions_context`: Evaluates user roles against `AdminRole` capability flags, exposing the `admin_perms` dictionary globally to templates for dynamic UI element hiding.
- `accounts.context_processors.admin_approvals_context`: Injects real-time pending enrollment and teacher verification counts for sidebar notification badges.
</details>

<details>
<summary><b>3. Usage & Automated Startup Scripts</b></summary>

The system provides fully automated startup scripts that verify dependencies, start Redis and Daphne, and launch microservices:
- **Windows Batch:** `start_app.bat`
- **Windows PowerShell:** `start_app.ps1`
- **SSL Development Server:** `python run_ssl_server.py` or `python scripts/run_ssl_server.py` (serves Daphne with self-signed SSL on port 8002)
- **Linux Deployment:** `sudo bash deploy.sh`
</details>

<details>
<summary><b>4. Security & Middleware Stack (`middleware.py`, `settings.py`)</b></summary>

- `SecurityMiddleware`: Enforces HTTPS redirection, HTTP Strict Transport Security (HSTS), and `X-Content-Type-Options: nosniff`.
- `XFrameOptionsMiddleware`: Enforces `X-Frame-Options: DENY` preventing clickjacking.
- `CsrfViewMiddleware`: Enforces cryptographic token verification on all mutation requests.
- `DatabaseErrorMiddleware`: Gracefully catches and recovers from temporary database lock conditions.
- Performance logging middleware tracking high-latency endpoints and slow queries.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `settings.py`: Master configuration file. Contains database routers, security policies, LiveKit credentials, cache tiers, context processors, and automated FFmpeg/FFprobe binary detection (`FFMPEG_BINARY`, `FFPROBE_BINARY`) for `EduMiCompressionService`.
- `asgi.py`: ASGI entry point configuring Daphne protocol routers for HTTP and WebSockets.
- `wsgi.py`: Standard WSGI entry point for traditional web servers.
- `celery.py`: Initializes the Celery application and worker discovery.
- `urls.py`: Master URL routing table distributing paths across all modular applications and administrative endpoints.
- `middleware.py`: Custom middleware for error handling, database locking resilience, and telemetry.
</details>
