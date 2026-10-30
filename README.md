<div align="center">

# 🎓 EduMi — Enterprise AI-Powered Academic Operating System

**A self-hosted, on-premise educational operating system integrating ultra-low latency WebRTC virtual classrooms, facial biometric attendance, smart classroom & mobile camera streaming, classroom occupancy analytics, automated assignments & quizzes, real-time messaging, and an in-browser non-destructive video editing studio.**

<br/>

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-4.2-092E20?style=for-the-badge&logo=django&logoColor=white)](https://djangoproject.com)
[![LiveKit](https://img.shields.io/badge/LiveKit-WebRTC%20SFU-00C58E?style=for-the-badge)](https://livekit.io)
[![Daphne](https://img.shields.io/badge/Daphne-ASGI%20%2F%20HTTPS-7B3F85?style=for-the-badge)](https://github.com/django/daphne)
[![OpenCV](https://img.shields.io/badge/OpenCV-YuNet%20%2B%20SFace-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Multimedia%20Engine-007808?style=for-the-badge&logo=ffmpeg&logoColor=white)](https://ffmpeg.org)
[![Compression](https://img.shields.io/badge/Compression-WebP%20%7C%20H.265%20%7C%20SVC-blueviolet?style=for-the-badge)](common/compression_service.py)
[![Redis](https://img.shields.io/badge/Redis-Cache%20%26%20Channels-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![License](https://img.shields.io/badge/License-Commercial%20Enterprise-blue?style=for-the-badge)](LICENSE)

</div>

---

## 📑 Table of Contents

1. [Executive Summary](#-executive-summary)
2. [Key Value Propositions & Modules](#-key-value-propositions--modules)
3. [Institute On-Premise Deployment & Data Sovereignty](#-institute-on-premise-deployment--data-sovereignty)
4. [System Architecture](#-system-architecture)
5. [Technology Stack](#-technology-stack)
6. [Prerequisites & System Requirements](#-prerequisites--system-requirements)
7. [Getting Started & Local Setup](#-getting-started--local-setup)
8. [Configuration & Environment Variables](#-configuration--environment-variables)
9. [Microservices & Port Matrix](#-microservices--port-matrix)
10. [Diagnostic & Test Utilities](#-diagnostic--test-utilities)
11. [Repository Structure](#-repository-structure)
12. [User Roles & Permissions](#-user-roles--permissions)
13. [Security, Privacy & Biometric Hardening](#-security-privacy--biometric-hardening)
14. [License & Maintainers](#-license--maintainers)

---

## 📌 Executive Summary

**EduMi** is engineered to eliminate fragmented, subscription-heavy third-party school software (Zoom/Teams licenses, manual paper roll-calls, external LMS portals, and standalone video editors) with a unified, **self-hosted, privacy-first institution platform**.

### 🌟 Core Design Principles
- **100% Data Sovereignty**: Operates completely on the institute's local LAN server or private cloud. Zero external telemetry, zero recurring per-seat fees, and zero cloud lock-in.
- **Commercial-Grade Biometric Privacy**: Replaces restrictive models with **OpenCV Model Zoo's Apache 2.0 YuNet (Detection) + SFace (Recognition)** neural networks. Extracted 128-dimensional vectors are encrypted at rest with **Fernet (AES-128-CBC + HMAC-SHA256)**. Raw facial images are discarded after registration to uphold strict privacy.
- **Domain-Adaptive Multimedia Compression**: Implements tailored, benchmark-backed codecs across modules: WebP for images/thumbnails (35% size cut), H.265 CRF 28/32 for smart classroom lecture storage (50% disk savings), 360p ultrafast for video proxies (<10s turnaround, 95ms seek latency), faststart container exports, and 3-layer SVC simulcast for WebRTC.
- **Ultra-Low Latency Media**: Real-time virtual classrooms powered by an on-premise **LiveKit WebRTC SFU** and real-time WebSocket state synchronisation via **Django Channels (ASGI/Daphne)**.
- **Dual Database Resilience**: Native production support for **PostgreSQL** with automated, self-healing fallback to SQLite for offline testing.

---

## ✨ Key Value Propositions & Modules

| Module | Features & Capabilities |
|---|---|
| **Live Virtual Classrooms** | • Sub-second WebRTC audio/video conferencing via dedicated LiveKit SFU.<br/>• 3-layer SVC simulcast (180p, 360p, 720p) ensuring smooth video delivery on constrained networks.<br/>• Host classroom management (mute-all, remove user, camera lock, screen-share permissions).<br/>• Live in-meeting chat, hand-raising queue, interactive quiz launches, and automated attendance logs. |
| **AI Biometric Attendance** | • Pre-join face verification using OpenCV **YuNet + SFace (128D)** neural vectors with Cosine/Euclidean matching.<br/>• Client-side positioning guidance powered by `face-api.js` and anti-spoofing via `MiniFASNetV2`.<br/>• Encrypted at rest via Fernet AES-256; raw biometric photos are never retained on disk. |
| **Smart Classroom & Studio Cameras** | • Ingestion of classroom RTSP IP camera feeds (interactive boards, teacher podiums, smart labs).<br/>• Mobile IP camera integration (converts iOS/Android smartphones into wireless classroom studio cameras).<br/>• Real-time classroom occupancy & head-counting analytics.<br/>• High-efficiency H.265 CRF 28/32 lecture archival compression saving >50% disk storage. |
| **Academic LMS & Quizzes** | • File-based homework submissions with magic-byte MIME security validation.<br/>• Automated WebP image thumbnailing for classroom resources and study materials.<br/>• Timed multiple-choice quizzes with automated instant scorecards and analytics. |
| **Video Editing Studio** | • Browser-based non-destructive timeline video editor.<br/>• Sub-10 second 360p ultrafast proxy generation with 95ms seek latency for smooth scrubbing.<br/>• Multi-track audio overlay, volume balance, trim, split, rotate, resize, and custom text captions.<br/>• Web-optimized `-movflags +faststart` timeline compiler rendering via Celery workers. |
| **Multimedia Compression Engine** | • Centralized `EduMiCompressionService` delivering domain-adaptive compression across all assets.<br/>• 3-phase dynamic chunked parallel transcoder with keyframe GOP boundary splitting.<br/>• Dual export pipeline (H.264 web stream + H.265 cold storage archive). |
| **Enterprise Authentication** | • 6-digit email OTP verification with signed cryptographic fallback tokens.<br/>• Automated in-memory WebP avatar compression on save (75-80% smaller avatars).<br/>• Sliding-window rate limiters to protect against brute-force attacks and credential stuffing.<br/>• Strict role-based access control (Admin, Teacher, Student). |
| **Messaging & Notifications** | • 1-to-1 direct messaging and campus-wide real-time WebSocket announcements.<br/>• Persistent in-app notifications for classes, assignment deadlines, and grade releases. |

---

## 🏛️ Institute On-Premise Deployment & Data Sovereignty

EduMi is designed to run directly inside an educational institute's **Local Area Network (LAN)** or private data centre:

```
                  ┌──────────────────────────────────────────────┐
                  │    Institute Local Server (Server Room/Lab)   │
                  │   (Ubuntu 22.04 LTS / Windows - 16-32GB RAM) │
                  │                                              │
                  │   • PostgreSQL Database (Internal Storage)   │
                  │   • LiveKit WebRTC SFU (LAN Streaming)       │
                  │   • Daphne ASGI + Nginx (HTTPS: 443 / 8002)  │
                  │   • Redis (Task Queue & Channel Layers)      │
                  └──────────────────────┬───────────────────────┘
                                         │
             ┌───────────────────────────┼───────────────────────────┐
             │       Campus Gigabit LAN / Wi-Fi Access Points        │
             │                     (192.168.x.x)                     │
    ┌────────▼────────┐             ┌────────▼────────┐     ┌────────▼────────┐
    │ Student Devices │             │ Teacher Laptops │     │ Campus RTSP /   │
    │ (Phones / PCs)  │             │ (Live Classes)  │     │ Mobile Cameras  │
    └─────────────────┘             └─────────────────┘     └─────────────────┘
```

### Why On-Premise Deployment Wins for Schools:
1. **Zero Internet Bandwidth Usage for Classes**: Video conferencing and classroom camera streaming stay entirely inside the local school network. Even if the external internet connection drops, classes and smart classroom cameras continue without interruption.
2. **Absolute Privacy Compliance**: Biometrics, grades, attendance, and recordings never leave the school's physical premises, complying with DPDP (India), FERPA (US), and GDPR data sovereignty standards.
3. **No Per-Student Subscription Costs**: Deploy for 500 or 5,000 students without paying per-user monthly SaaS fees.

---

## 🏗️ System Architecture

```
                                  ┌────────────────────────────────────────┐
                                  │      Client Browser (HTTPS / WSS)      │
                                  └───────────────────┬────────────────────┘
                                                      │
                                  ┌───────────────────▼────────────────────┐
                                  │     Nginx Reverse Proxy / SSL Term     │ (Port 443 / 8002)
                                  └─────────┬───────────────────┬──────────┘
                                            │                   │
                     ┌──────────────────────┴──────┐     ┌──────┴──────────────────────┐
                     │                             │     │                             │
        ┌────────────▼────────────┐   ┌────────────▼─────┴──────┐   ┌──────────────────▼──────┐
        │   Django Monolith ASGI  │   │   Camera Microservice   │   │   LiveKit WebRTC SFU    │
        │ (Auth, LMS, Channels)   │   │ (OpenCV, RTSP, Headcount│   │ (Low-Latency Video SFU) │
        └────────────┬────────────┘   └────────────┬────────────┘   └────────────┬────────────┘
                     │                             │                             │
                     ├─────────────────────────────┴─────────────────────────────┤
                     │
        ┌────────────▼────────────┐   ┌─────────────────────────┐   ┌────────────▼────────────┐
        │   PostgreSQL Database   │   │      Redis Service      │   │   Celery Task Worker    │
        │ (Encrypted Biometrics)  │   │ (Channels & Task Broker)│   │ (FFmpeg & Background AI)│
        └─────────────────────────┘   └─────────────────────────┘   └─────────────────────────┘
```

---

## 🧰 Technology Stack

- **Backend Framework**: Django 4.2 LTS with Django Channels (ASGI)
- **ASGI & Web Servers**: Daphne, Waitress (Camera Microservice), Nginx (Reverse Proxy & SSL)
- **Real-Time Communication**: LiveKit SFU (WebRTC), WebSockets (`ws://` / `wss://`)
- **Computer Vision & AI**: OpenCV DNN, YuNet ONNX (Face Detection), SFace ONNX (128D Embeddings), MiniFASNetV2 (Liveness), `face-api.js` (Client-side)
- **Multimedia Processing & Compression**: `EduMiCompressionService`, FFmpeg 6.x & FFprobe (libx264, libx265, WebP, HLS muxer, 3-phase chunked parallel transcoding, and background Celery render workers)
- **Task Queue & Caching**: Celery 5.3, Redis 7
- **Database**: PostgreSQL 15+ (Production Primary) / SQLite 3 (Dev Fallback)
- **Cryptography**: Fernet `AES-128-CBC` with `HMAC-SHA256` authentication

---

## 📋 Prerequisites & System Requirements

| Requirement | Minimum Version | Notes |
|---|---|---|
| **Operating System** | Ubuntu 20.04/22.04/24.04 LTS or Windows 10/11 Server | Ubuntu recommended for production |
| **Python** | `3.11+` | With `pip` and `venv` |
| **FFmpeg & FFprobe** | `6.0+` | Must be added to system `PATH` |
| **Redis Server** | `6.0+` / `7.0+` | Required for Celery queues and WebSocket Channels |
| **LiveKit Server** | `1.5+` | Self-hosted binary in `livekit-bin/` or Docker |
| **Database** | PostgreSQL `14+` | Strongly recommended over SQLite for multi-user concurrency |

---

## 🚀 Getting Started & Local Setup

### Step 1: Clone the Repository
```bash
git clone https://github.com/GAuravgiy87/Edumi2.git
cd Edumi2
```

### Step 2: Configure Environment Variables
Copy the template configuration file:
```bash
# Windows PowerShell:
Copy-Item .env.example .env

# Linux / macOS:
cp .env.example .env
```

Open `.env` and set your production keys. Generate a valid Fernet key for biometric encryption:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Paste the generated output into `FACE_ENCRYPTION_KEY` in your `.env`.

### Step 3: Set Up Python Virtual Environment
```bash
# Create and activate virtual environment
python -m venv venv

# Windows:
.\venv\Scripts\activate

# Linux:
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Run Migrations & Create Superuser
```bash
python manage.py migrate
python manage.py createsuperuser
```

---

### 💻 Launching the Application

#### Option A: One-Click Windows PowerShell Launcher (Development & Testing)
EduMi includes a unified launcher that automatically resolves LAN IP addresses, configures LiveKit, runs migrations, compiles static assets, and boots background services:
```powershell
# Double-click start_app.bat OR run in PowerShell:
.\start_app.ps1
```
Access the application at:
- **Local URL**: `https://localhost:8002`
- **LAN URL**: `https://<YOUR-LAN-IP>:8002` (Accessible by phones/tablets on the same Wi-Fi)

#### Option B: Master Ubuntu Server Deployment (Production)
For dedicated Linux servers, use the automated single-file deployment orchestrator:
```bash
sudo bash deploy.sh --domain edumi.yourcollege.ac.in --email admin@yourcollege.ac.in
```

#### Option C: Docker Compose Deployment
```bash
docker compose up -d --build
```

---

## ⚙️ Configuration & Environment Variables

Key parameters in `.env`:

| Variable | Default Value | Purpose |
|---|---|---|
| `SECRET_KEY` | *(Required)* | Django session and cryptographic signature seed |
| `DEBUG` | `False` | Debug mode (must be `False` in production) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hostnames and LAN IPs permitted to connect |
| `DATABASE_URL` | `postgres://user:pass@127.0.0.1:5432/edumi_db` | PostgreSQL connection string |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis channel layer & Celery broker |
| `LIVEKIT_URL` | `wss://<DOMAIN>/livekit-proxy/` | WebRTC public signaling endpoint |
| `LIVEKIT_API_KEY` | `edumi_livekit_key_2026` | LiveKit API authentication key |
| `LIVEKIT_API_SECRET` | `edumi_livekit_sec_32chars_key_2026_prod` | LiveKit shared secret (min 32 characters) |
| `FACE_ENCRYPTION_KEY` | *(Fernet Base64 Key)* | AES-256 key for encrypting 128D facial vectors |
| `FACE_MATCH_THRESHOLD` | `0.50` | Maximum Euclidean distance for facial verification |
| `CAMERA_SERVICE_PORT` | `8008` | Port for the camera streaming microservice |
| `CAMERA_SERVICE_URL` | `http://127.0.0.1:8008` | Internal camera microservice address |
| `CAMERA_SERVICE_SECRET` | *(Random 32-char string)* | Service-to-service authentication token |

---

## 🔢 Microservices & Port Matrix

| Service | Port | Protocol | Purpose |
|---|---|---|---|
| **Daphne (Main ASGI)** | `8002` | HTTPS / WSS | Primary application UI, auth, API, and WebSockets |
| **Camera Microservice** | `8008` | HTTP | Ingests RTSP feeds, executes head counting, emits streams |
| **LiveKit Signaling** | `7880` | HTTP / WS | WebRTC session creation and room coordination |
| **LiveKit RTC Media** | `7881` / `7882` | TCP / UDP | WebRTC audio/video packet transport |
| **LiveKit UDP Range** | `50000–60000` | UDP | High-concurrency peer media streams |
| **Redis Server** | `6379` | TCP | Channel layers and Celery task broker |
| **PostgreSQL** | `5432` | TCP | Relational enterprise database |

---

## 🧪 Diagnostic & Test Utilities

EduMi includes automated tools in `scripts/` to verify infrastructure health:

1. **Django System Health & Model Checks:**
   ```bash
   python manage.py check
   python manage.py test
   ```

2. **Test SMTP Email & OTP Delivery:**
   ```bash
   python scripts/test_smtp.py student@yourcollege.ac.in --verbose
   ```

3. **Generate HTTPS SSL Certificates:**
   ```bash
   python scripts/generate_ssl_cert.py
   ```

4. **Firewall & Certificate Helpers (Windows):**
   ```powershell
   # Add firewall exceptions for ports 8002, 8008, 7880-7882:
   .\scripts\allow_firewall.ps1

   # Trust self-signed certificate in Windows Certificate Store:
   .\scripts\trust_ssl_cert.ps1
   ```

5. **Live Health Endpoint:**
   ```bash
   curl -k https://localhost:8002/health/
   ```

---

## 📁 Repository Structure

```
Edumi2/
├── accounts/                # Authentication, profiles, OTPs, rate-limiting & direct messaging
├── assignments/             # Homework submissions, timed quizzes, and automatic grading
├── attendance/              # YuNet + SFace biometric recognition, attendance ledgers
├── cameras/                 # Smart classroom RTSP cameras, lecture recording engine, and occupancy counting
├── camera_service/          # Dedicated streaming gateway for classroom camera feeds
├── mobile_cameras/          # Mobile IP Webcam streaming (smartphones as classroom cameras)
├── meetings/                # LiveKit WebRTC virtual classrooms, room controls, live chat
├── rag_workspace/           # Academic document search and AI knowledge-base
├── video_editing/           # Non-destructive in-browser video editor & FFmpeg filtergraphs
├── videos/                  # On-demand lecture library with multi-bitrate HLS streaming
├── common/                  # Cross-app utilities, telemetry, audit logs, magic-byte checks
├── config/                  # Microservice configurations (livekit.yaml)
├── scripts/                 # SSL generation, firewall tools, SMTP verification scripts
├── templates/               # Semantic HTML5 templates (responsive layouts, dark mode)
├── static/                  # CSS stylesheets, JavaScript modules, ONNX/face-api vendor models
├── school_project/          # Root Django settings, ASGI/WSGI entrypoints, and routing
├── deploy.sh                # Single-file master deployment script for Ubuntu Server
├── start_app.bat            # Double-click launcher wrapper for Windows
├── start_app.ps1            # Automated PowerShell microservice orchestrator
└── requirements.txt         # Production Python dependencies
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
   │  • Schedule Live Classes  │       │  • Join Approved Classes  │
   │  • Host WebRTC Rooms      │       │  • Attend Live Sessions   │
   │  • View Biometric Reports │       │  • Complete Face Setup    │
   │  • Manage Assignments     │       │  • Submit Work & Quizzes  │
   │  • Access Classroom Studio│       │  • Watch Lecture Library  │
   └───────────────────────────┘       └───────────────────────────┘
```

---

## 🔒 Security, Privacy & Biometric Hardening

- **Zero Raw Photo Retention**: The system computes 128D mathematical embeddings in memory, encrypts them immediately, and deletes raw face images to ensure no sensitive biometric imagery can be leaked.
- **Biometric Encryption**: Vectors are encrypted using authenticated symmetric encryption (`AES-128-CBC` with `HMAC-SHA256`).
- **Magic-Byte Upload Inspection**: All uploaded media and documents undergo binary file signature checks (`common/validators.py`) to prevent extension spoofing and web shell uploads.
- **Brute-Force Rate Limiting**: Authentication endpoints and OTP verifications are protected by sliding-window rate limiters.
- **Process Isolation**: CPU-intensive video rendering (FFmpeg) and camera transcoding run in separate Celery workers and microservices, keeping web request loops fast and responsive.

---

## 📄 License & Maintainers

**Copyright (c) 2026 EduMi Systems. All Rights Reserved.**

This software is licensed under the **EduMi Commercial Enterprise Software License Agreement**. See [`LICENSE`](LICENSE) for terms, conditions, and usage restrictions.

### Project Authors & Core Maintainers:
- **Gaurav Singh** ([@GAuravgiy87](https://github.com/GAuravgiy87))
- **Tarun Kumar** ([@tarunkumar-sys](https://github.com/tarunkumar-sys))
