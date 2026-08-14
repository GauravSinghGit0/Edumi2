<div align="center">

# 🎓 EduMi 2 — Unified Enterprise Academic Command Center

**A self-hosted, end-to-end educational platform integrating real-time WebRTC virtual classrooms, AI-driven biometric attendance, live engagement analytics, RTSP camera processing, and non-destructive video editing.**

<br/>

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-4.2-092E20?style=for-the-badge&logo=django&logoColor=white)](https://djangoproject.com)
[![LiveKit](https://img.shields.io/badge/LiveKit-WebRTC%20SFU-00C58E?style=for-the-badge)](https://livekit.io)
[![Daphne](https://img.shields.io/badge/Daphne-ASGI%20%2F%20HTTPS-7B3F85?style=for-the-badge)](https://github.com/django/daphne)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Video%20Processing-007808?style=for-the-badge&logo=ffmpeg&logoColor=white)](https://ffmpeg.org)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

</div>

---

## 📌 Executive Summary

**EduMi 2** consolidates fragmented educational tools — video conferencing systems, manual attendance registers, hardware surveillance monitors, and standalone video editing tools — into a single **enterprise-grade, self-hosted platform**.

Built with privacy and performance at its core:
- **100% On-Premise & Self-Hosted**: Zero third-party cloud locking or per-user subscription fees.
- **AES-256 Encrypted Biometrics**: Facial embeddings encrypted at rest using Python `cryptography` (Fernet).
- **Zero Latency WebRTC & WSS**: Powered by LiveKit SFU, Daphne ASGI, and Django Channels.
- **Resilient Multi-Database Engine**: Auto-detects PostgreSQL connectivity with zero-downtime fallback to SQLite for local deployment.

---

## ✨ Core Pillars & Feature Highlights

### 📽️ Real-Time Virtual Classrooms
- **LiveKit WebRTC SFU Integration**: Ultra-low latency multi-party video & audio streaming.
- **Interactive Session Tools**: Screen sharing, raised hands queue, live chat, and automated session attendance logs.
- **Adaptive Quality Control**: Automatic resolution scaling and bandwidth adaptation.

### 🤖 AI Biometrics & Automated Attendance
- **Instant Roll Call**: 128-dimensional facial embedding matching via `dlib` and OpenCV.
- **Presence Verification**: Continuous passive sampling to verify physical presence throughout sessions.
- **Encrypted Storage**: Biometric vectors stored using AES-256 encryption.

### 📊 Engagement & Sentiment Analytics
- **Attention Indexing**: Real-time eye tracking and head pose estimation metrics.
- **Emotion Recognition**: Visual sentiment categorization (Attentive, Neutral, Distracted).
- **Teacher Analytics Dashboard**: Aggregated class metrics, heatmaps, and downloadable attendance summaries.

### 📷 Hardware & Mobile Camera Management
- **RTSP Surveillance Feeds**: Native ingestion for IP CCTV cameras.
- **Mobile IP Camera Integration**: Transform any smartphone (Android / iOS) into a live classroom camera feed.
- **Automated Head Counting**: Microservice-based CV pipeline for physical classroom crowd analysis.

### ✂️ Non-Destructive Video Editing Studio
- **In-Browser Timeline Editor**: Split, trim, reorder, and layer video and audio tracks without altering raw recordings.
- **Single-Pass FFmpeg Rendering**: High-speed, loss-free export filtergraph compilation.
- **Automated Storage Pipeline**: Direct storage integration with session recordings.

---

## 🏗️ System Architecture

```
                                  ┌───────────────────────────┐
                                  │    Browser Client (HTTPS) │
                                  └─────────────┬─────────────┘
                                                │
                                  ┌─────────────▼─────────────┐
                                  │   Daphne / Nginx Ingress  │ (Port 8002 / 443)
                                  └─────────────┬─────────────┘
                                                │
                 ┌──────────────────────────────┼──────────────────────────────┐
                 │                              │                              │
    ┌────────────▼────────────┐    ┌────────────▼────────────┐    ┌────────────▼────────────┐
    │     Django ASGI App     │    │   Waitress Camera Svc   │    │    LiveKit WebRTC SFU   │
    │  (Auth, Sessions, Admin)│    │  (CV, Head Count, RTSP) │    │  (Media Peer Routing)   │
    └────────────┬────────────┘    └────────────┬────────────┘    └────────────┬────────────┘
                 │                              │                              │
                 ├──────────────────────────────┴──────────────────────────────┤
                 │
    ┌────────────▼────────────┐    ┌─────────────────────────┐    ┌─────────────────────────┐
    │ PostgreSQL / SQLite DB  │    │      Redis Broker       │    │   Celery Task Worker    │
    │  (Smart Auto-Fallback)  │    │  (Channels & Queue)     │    │  (Async Media & Face AI)│
    └─────────────────────────┘    └─────────────────────────┘    └─────────────────────────┘
```

---

## 🛠️ Quickstart & Deployment

### 📋 Prerequisites
- **Python**: 3.11+
- **PowerShell**: 5.1+ (Windows) or **Bash** (Linux/macOS)
- **FFmpeg & FFprobe**: Installed and available on system `PATH`

---

### 🚀 One-Click Windows Launcher

EduMi 2 includes a unified, production-tested PowerShell launcher that cleans process ports, runs database migrations, compiles static assets, launches background microservices (LiveKit SFU, Camera Service, Celery), and starts the Daphne HTTPS server:

```powershell
# 1. Clone the repository
git clone https://github.com/GAuravgiy87/Edumi2.git
cd Edumi2

# 2. Setup Virtual Environment
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# 3. Launch Enterprise Suite
.\start_app.ps1
```

> [!NOTE]
> Upon startup, EduMi 2 automatically displays your **Local URL** (`https://localhost:8002`) and **LAN URL** (`https://<YOUR-IP>:8002`), allowing devices on the same Wi-Fi network to connect securely.

---

### 🐧 Linux / Production Deployment

For Linux servers or production deployment using Nginx and systemd:

```bash
# 1. Environment configuration
cp .env.example .env
nano .env

# 2. Run Database Migrations & Static Build
python3 manage.py migrate
python3 manage.py collectstatic --noinput
python3 manage.py compress --force

# 3. Run Application via Daphne
daphne -b 0.0.0.0 -p 8002 school_project.asgi:application
```

Alternatively, use the Docker container setup:
```bash
docker-compose up -d --build
```

---

## 🔢 Port & Microservice Reference

| Service | Port | Protocol | Description |
|---|---|---|---|
| **Daphne (Main App)** | `8002` | HTTPS / WSS | Primary application server & WebSocket engine |
| **Camera Microservice** | `8008` | HTTP | Computer vision proxy & head counting API |
| **LiveKit SFU** | `7880` | HTTP / WS | WebRTC media signaling server |
| **LiveKit RTC TCP/UDP** | `7881` / `7882` | TCP / UDP | WebRTC media transport ports |
| **Redis** | `6379` | TCP | Channel layer & Celery message broker |
| **Nginx Ingress** | `443` | HTTPS | Production SSL termination reverse proxy |

---

## 🔒 Security & Privacy Architecture

- **End-to-End SSL/TLS**: All browser traffic forced over TLS 1.3 with secure HTTP-only session cookies (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`).
- **Biometric Encryption at Rest**: Face descriptors are encrypted using Fernet symmetric encryption before insertion into database records.
- **Non-Invasive Architecture**: Biometric raw images are discarded immediately after embedding extraction; only encrypted vectors remain stored.

---

## 📁 Repository Structure

```
Edumi2/
├── school_project/          # Django core settings, middleware, ASGI configuration
├── accounts/                # User authentication, roles, profile management
├── attendance/              # Facial AI recognition & continuous engagement metrics
├── cameras/                 # Hardware RTSP camera integration & stream relay
├── camera_service/          # Waitress microservice for dedicated OpenCV pipelines
├── mobile_cameras/          # Phone IP camera endpoints & stream parsing
├── meetings/                # LiveKit WebRTC meeting rooms & signaling handlers
├── video_editing/           # Non-destructive video editor & FFmpeg filter builder
├── videos/                  # Video recording storage & metadata management
├── common/                  # Shared helper functions, baseline models, utilities
├── certs/                   # Development SSL/TLS certificates
├── config/                  # Microservice configuration files (LiveKit, Nginx)
├── scripts/                 # System administration & cert generator scripts
└── start_app.ps1            # One-click enterprise PowerShell launcher
```

---

## 📄 License & Credits

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.

Developed with ❤️ for modern classrooms by [GAuravgiy87](https://github.com/GAuravgiy87) and [tarunkumar-sys](https://github.com/tarunkumar-sys).