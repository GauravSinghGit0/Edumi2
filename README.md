<div align="center">

# 🎓 EduMi 2 — Enterprise AI-Powered Educational Platform

**A next-generation, self-hosted academic operating system integrating ultra-low latency WebRTC virtual classrooms, facial biometric attendance, crowd head-counting, automated homework & quizzes, real-time messaging, and an in-browser non-destructive video editing studio.**

<br/>

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-4.2-092E20?style=for-the-badge&logo=django&logoColor=white)](https://djangoproject.com)
[![LiveKit](https://img.shields.io/badge/LiveKit-WebRTC%20SFU-00C58E?style=for-the-badge)](https://livekit.io)
[![Daphne](https://img.shields.io/badge/Daphne-ASGI%20%2F%20HTTPS-7B3F85?style=for-the-badge)](https://github.com/django/daphne)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Multimedia%20Engine-007808?style=for-the-badge&logo=ffmpeg&logoColor=white)](https://ffmpeg.org)
[![Redis](https://img.shields.io/badge/Redis-Cache%20%26%20Channels-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

</div>

---

## 📑 Table of Contents

1. [Executive Summary](#-executive-summary)
2. [Key Value Propositions & Modules](#-key-value-propositions--modules)
3. [System Architecture](#-system-architecture)
4. [Technology Stack](#-technology-stack)
5. [Prerequisites & System Requirements](#-prerequisites--system-requirements)
6. [Getting Started & Local Setup](#-getting-started--local-setup)
7. [Running Diagnostic & Test Scripts](#-running-diagnostic--test-scripts)
8. [Configuration & Environment Variables](#-configuration--environment-variables)
9. [Microservices & Port Matrix](#-microservices--port-matrix)
10. [Repository Structure](#-repository-structure)
11. [User Roles & Permissions](#-user-roles--permissions)
12. [Security & Production Hardening](#-security--production-hardening)
13. [License & Maintainers](#-license--maintainers)

---

## 📌 Executive Summary

**EduMi 2** replaces fractured third-party education software (Zoom/Teams subscriptions, manual roll-call registers, separate LMS platforms, and standalone video editors) with a unified, **self-hosted, privacy-first monolith**.

### 🌟 Core Design Principles
- **100% Data Sovereignty**: Self-hosted on on-premise servers or private cloud. Zero external telemetry or per-seat licensing.
- **Biometric Privacy**: Face embeddings are 128-dimensional mathematical vectors encrypted at rest with **AES-256 (Fernet)**. Raw face images are never permanently stored.
- **Ultra-Low Latency Media**: Powered by a co-located **LiveKit WebRTC SFU** and **Django Channels (ASGI/Daphne)** over WebSocket.
- **Zero-Downtime Multi-Database Support**: Native PostgreSQL with automated SQLite fallback for rapid offline development.

---

## ✨ Key Value Propositions & Modules

| Module | Features & Capabilities |
|---|---|
| **Live Virtual Classrooms** | • WebRTC conferencing with sub-second latency via LiveKit SFU.<br/>• Host permission controls (mute, kick, screen share lock, camera toggle).<br/>• Real-time hand-raising queue, live text chat, and attendance logging. |
| **AI Biometric Attendance** | • Pre-join instant face verification using `dlib` and OpenCV 128D vectors.<br/>• Passive background verification during live meetings.<br/>• AES-256 encrypted biometric storage. |
| **Hardware & Mobile CCTV** | • RTSP IP camera feed ingestion and multi-stream live dashboard.<br/>• Mobile IP camera support (turn iOS/Android phones into classroom cameras).<br/>• Automated crowd head-counting with bounding-box analytics. |
| **Assignments & Quizzes** | • File-based homework submissions with secure multi-mime validation.<br/>• Timed MCQ & text quizzes with automatic grading and scorecards. |
| **Video Editing Studio** | • Browser-based non-destructive timeline editor.<br/>• Multi-track audio overlay, volume adjust, trimming, rotate, resize, text captioning.<br/>• High-performance FFmpeg filtergraph compiler with zero quality loss. |
| **Secure Authentication** | • 6-digit Email OTP verification with signed cryptographic token fallback.<br/>• Strict password entropy validator & live username availability checker.<br/>• IP/Action rate limiting to protect against brute-force and spam attacks. |
| **Messaging & Notifications** | • 1-to-1 real-time direct messaging with file attachments.<br/>• Instant WebSocket push notifications for meeting starts, grades, and classroom events. |

---

## 🏗️ System Architecture

```
                                  ┌────────────────────────────────────────┐
                                  │      Client Browser (HTTPS / WSS)      │
                                  └───────────────────┬────────────────────┘
                                                      │
                                  ┌───────────────────▼────────────────────┐
                                  │     Nginx / Daphne Reverse Proxy       │ (Port 8002 / 443)
                                  └─────────┬───────────────────┬──────────┘
                                            │                   │
                     ┌──────────────────────┴──────┐     ┌──────┴──────────────────────┐
                     │                             │     │                             │
        ┌────────────▼────────────┐   ┌────────────▼─────┴──────┐   ┌──────────────────▼──────┐
        │   Django Monolith ASGI  │   │   Waitress Camera API   │   │   LiveKit WebRTC SFU    │
        │ (Auth, LMS, WS Channels)│   │ (OpenCV, RTSP, Headcount)│  │   (Real-Time Media SFU) │
        └────────────┬────────────┘   └────────────┬────────────┘   └────────────┬────────────┘
                     │                             │                             │
                     ├─────────────────────────────┴─────────────────────────────┤
                     │
        ┌────────────▼────────────┐   ┌─────────────────────────┐   ┌────────────▼────────────┐
        │  PostgreSQL / SQLite DB │   │      Redis Service      │   │   Celery Task Worker    │
        │ (Encrypted Biometrics)  │   │ (Channels & Task Broker)│   │ (Video Encoding & AI)   │
        └─────────────────────────┘   └─────────────────────────┘   └─────────────────────────┘
```

---

## 🧰 Technology Stack

- **Backend Web Framework**: Django 4.2.9 + Django Channels (ASGI)
- **ASGI & Web Server**: Daphne, Waitress (Microservices), Nginx (Reverse Proxy)
- **Real-Time Communication**: LiveKit SFU (WebRTC), WebSockets (`ws://` / `wss://`)
- **Computer Vision & AI**: OpenCV 4, `dlib`, `face_recognition`, NumPy
- **Multimedia Processing**: FFmpeg 6.x, FFprobe
- **Task Queue & Caching**: Celery 5.3, Redis 7
- **Database**: PostgreSQL (Primary) / SQLite 3 (Development Fallback)
- **Security & Crypto**: `cryptography` (Fernet AES-256), Django Sessions, CSRF Protection

---

## 📋 Prerequisites & System Requirements

Before running the application, ensure the following are installed:

| Requirement | Minimum Version | Notes |
|---|---|---|
| **Python** | `3.11+` or `3.12+` | Ensure `pip` and `venv` are available |
| **FFmpeg & FFprobe** | `6.0+` | Must be added to system `PATH` |
| **Redis Server** | `6.0+` / `7.0+` | Required for Celery and WebSocket Channels |
| **LiveKit Server** | `1.5+` | Self-hosted binary included in `livekit-bin/` or Docker |
| **C++ Build Tools** | `Visual Studio C++` (Windows) / `build-essential` (Linux) | Required for `dlib` compilation |

---

## 🚀 Getting Started & Local Setup

### Step 1: Clone the Repository
```bash
git clone https://github.com/GAuravgiy87/Edumi2.git
cd Edumi2
```

### Step 2: Configure Environment Variables
Create your local `.env` file from the provided template:
```bash
# Windows PowerShell:
Copy-Item .env.example .env

# Linux / macOS:
cp .env.example .env
```

Open `.env` and configure your database, Redis, and SMTP email credentials:
```ini
SECRET_KEY=your-strong-production-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,*
DATABASE_URL=postgres://edumi_admin:edumi_pass@127.0.0.1:5432/edumi_db
REDIS_URL=redis://127.0.0.1:6379/0
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_gmail_app_password
```

### Step 3: Set Up Python Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
.\venv\Scripts\activate

# On Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Run Database Migrations
```bash
python manage.py migrate
```

### Step 5: Create Superuser (Admin)
```bash
python manage.py createsuperuser
```

---

### 💻 Launching the Application

#### Option A: One-Click Windows PowerShell Launcher (Recommended)
EduMi 2 includes an automated startup manager that terminates old port collisions, generates SSL certs, runs migrations, spins up LiveKit SFU, Celery, Camera Service, and Daphne in unified background tasks:
```powershell
.\start_app.ps1
```
Access the application at `https://localhost:8002` or `https://<YOUR-LAN-IP>:8002`.

#### Option B: Manual Service Startup (Linux / Docker)
```bash
# 1. Start Redis
redis-server

# 2. Start LiveKit SFU
./livekit-bin/livekit-server --config config/livekit.yaml

# 3. Start Celery Worker
celery -A school_project worker --loglevel=info

# 4. Start Camera Microservice (Waitress)
python camera_service/serve.py

# 5. Start Daphne ASGI Server
daphne -b 0.0.0.0 -p 8002 school_project.asgi:application
```

---

## 🧪 Running Diagnostic & Test Scripts

EduMi 2 comes equipped with automated test suites and diagnostic scripts for validating system health, network readiness, and email delivery.

### 1. Run Automated Unit & Integration Tests
Execute the full Django test suite:
```bash
python manage.py test
```

Run tests for a specific module:
```bash
# Assignments & Quizzes tests
python manage.py test assignments

# Common utilities & validation tests
python manage.py test common

# Live meeting participant & session tests
python manage.py test meetings

# Video storage & streaming tests
python manage.py test videos
```

### 2. Test SMTP Email & OTP Delivery
Verify that your email credentials, TLS/SSL handshake, and 6-digit OTP delivery work properly:
```bash
# Syntax: python scripts/test_smtp.py <recipient_email>
python scripts/test_smtp.py student@example.com --verbose
```

### 3. Generate Local SSL/TLS Certificates
Generate SAN-enabled self-signed HTTPS certificates for local and LAN testing:
```bash
python scripts/generate_ssl_cert.py
```

### 4. Health Check Endpoint
Query the live system health and database connectivity status:
```bash
curl -k https://localhost:8002/health/
```
**Sample Response:**
```json
{
  "status": "ok",
  "db": true,
  "version": "2.0"
}
```

---

## ⚙️ Configuration & Environment Variables

| Variable | Default Value | Description |
|---|---|---|
| `SECRET_KEY` | *(Required)* | Cryptographic salt for Django sessions and tokens |
| `DEBUG` | `False` | Enable/disable Django debug mode |
| `ALLOWED_HOSTS` | `*` | Allowed hostnames/IP addresses |
| `DATABASE_URL` | `sqlite:///database/db.sqlite3` | PostgreSQL/SQLite connection URI |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis broker and cache endpoint |
| `LIVEKIT_URL` | `wss://localhost:8002/livekit-proxy` | Public WebSocket endpoint for WebRTC clients |
| `LIVEKIT_INTERNAL_URL` | `ws://127.0.0.1:7880` | Internal LiveKit signaling address |
| `LIVEKIT_API_KEY` | `devkey` | LiveKit API authentication key |
| `LIVEKIT_API_SECRET` | *(32-char string)* | LiveKit API shared secret |
| `FACE_ENCRYPTION_KEY` | *(Fernet key)* | AES-256 symmetric key for biometric descriptors |
| `FACE_MATCH_THRESHOLD` | `0.50` | Maximum Euclidean distance for facial verification |
| `EMAIL_BACKEND` | `smtp.EmailBackend` | Django email delivery backend |
| `EMAIL_HOST` | `smtp.gmail.com` | SMTP relay server host |
| `EMAIL_PORT` | `587` | SMTP port (`587` for TLS, `465` for SSL) |
| `EMAIL_HOST_USER` | *(Email address)* | SMTP sender authentication user |
| `EMAIL_HOST_PASSWORD` | *(App Password)* | SMTP application password |

---

## 🔢 Microservices & Port Matrix

| Service | Port | Protocol | Purpose |
|---|---|---|---|
| **Daphne (Main ASGI)** | `8002` | HTTPS / WSS | Primary application, UI templates, WebSocket channels |
| **Camera Microservice** | `8008` | HTTP | RTSP stream relay, OpenCV processing, crowd counting |
| **LiveKit Signaling** | `7880` | HTTP / WS | WebRTC room coordination & participant SDP exchange |
| **LiveKit RTC Media** | `7881` / `7882` | TCP / UDP | WebRTC audio/video media packet transport |
| **Redis Server** | `6379` | TCP | Channel Layer group broadcast & Celery queue |
| **PostgreSQL** | `5432` | TCP | Relational database (when configured) |

---

## 📁 Repository Structure

```
Edumi2/
├── accounts/                # User authentication, profiles, OTP verification, messaging
│   ├── email_tokens.py      # 6-digit OTP & cryptographic token generators
│   ├── ratelimit.py         # Memory/Redis sliding-window rate limiters
│   ├── serializers.py       # User input validators & sanitizers
│   ├── views/               # Modular auth, profile, admin, messaging views
│   └── urls/                # Namespaced URL routes
├── assignments/             # Homework assignments, question files, and quiz engine
│   ├── views/               # Assignment & quiz submission/grading logic
│   └── urls/                # Assignment & quiz URL routes
├── attendance/              # Facial recognition, attendance logs, engagement analytics
│   ├── face_service.py      # dlib vector extraction & matching engine
│   └── views/               # Biometric registration & attendance reporting views
├── cameras/                 # Hardware RTSP CCTV camera feeds, recording & playback
│   ├── head_count_service.py# OpenCV crowd head-counter & bounding box drawer
│   └── views_logic/         # Modular camera streaming, recordings, and permission views
├── camera_service/          # Standalone microservice for camera processing
├── mobile_cameras/          # Turn mobile phone cameras (IP Webcam) into classroom feeds
├── meetings/                # LiveKit WebRTC meetings, classrooms, and chat
│   ├── consumers.py         # WebSocket consumers for real-time room signaling
│   └── views/               # Classroom & meeting session controllers
├── video_editing/           # Non-destructive in-browser video editor
│   ├── ffmpeg_utils.py      # Low-level FFmpeg wrapper functions
│   └── timeline_compiler.py # Multi-track JSON timeline to FFmpeg filtergraph compiler
├── videos/                  # On-demand video library with multi-quality streaming
├── common/                  # Shared cross-app utilities, validators, template tags
│   └── validators.py        # Magic-byte file upload signatures & security sanitizers
├── config/                  # Microservice configurations (LiveKit YAML, Nginx)
├── scripts/                 # System diagnostic & SSL utility scripts
│   ├── test_smtp.py         # Standalone SMTP email & OTP delivery tester
│   └── generate_ssl_cert.py # Local SSL/TLS certificate generator
├── templates/               # Django HTML5 semantic UI templates
├── static/                  # CSS stylesheets, JavaScript modules, SVG icons
├── school_project/          # Root Django settings, routing, ASGI/WSGI entrypoints
├── requirements.txt         # Production Python dependencies
└── start_app.ps1            # One-click Windows PowerShell startup manager
```

---

## 👥 User Roles & Permissions

```
                     ┌───────────────────────────┐
                     │        Admin / Root       │
                     │ (Full Platform Oversight) │
                     └─────────────┬─────────────┘
                                   │
                 ┌─────────────────┴─────────────────┐
                 │                                   │
   ┌─────────────▼─────────────┐       ┌─────────────▼─────────────┐
   │          Teacher          │       │          Student          │
   │  • Create/Manage Classes  │       │  • Join Approved Classes  │
   │  • Host WebRTC Meetings   │       │  • Attend Live Sessions   │
   │  • View Biometric Reports │       │  • Complete Face Setup    │
   │  • Access CCTV / Studio   │       │  • Submit Work & Quizzes  │
   └───────────────────────────┘       └───────────────────────────┘
```

---

## 🔒 Security & Production Hardening

- **Email Verification & OTPs**: Unverified accounts cannot access student or teacher workspaces until email ownership is confirmed.
- **Biometric Encryption**: Biometric vector databases are encrypted with AES-256. If database records are leaked, raw biometric reconstruction is impossible.
- **Magic-Byte Signature Verification**: Uploaded assignment and video files undergo binary header inspection ([`common/validators.py`](file:///d:/Edumi2/common/validators.py)) to prevent extension spoofing and executable uploads.
- **Strict Rate Limiting**: Registration, login, and OTP resend requests are rate-limited via sliding-window IP buckets.
- **Isolated Microservices**: RTSP camera processing and FFmpeg encoding run in decoupled processes to keep ASGI request loops responsive.

---

## 📄 License & Maintainers

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for the complete license agreement.

Developed with ❤️ by:
- **Gaurav Singh** ([@GAuravgiy87](https://github.com/GAuravgiy87))
- **Tarun Kumar** ([@tarunkumar-sys](https://github.com/tarunkumar-sys))