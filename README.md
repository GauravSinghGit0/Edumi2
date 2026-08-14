<div align="center">

<img src="https://github.com/tarunkumar-sys/tarunkumar-sys/blob/main/matrix.svg" alt="Matrix Animation" width="100%"/>

<br/>

<h1>
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=36&duration=3000&pause=1000&color=00C58E&center=true&vCenter=true&width=600&lines=🎓+EduMi+2;Academic+Command+Center;Built+for+Better+Classrooms" alt="Typing SVG" />
</h1>

<p align="center">
  <strong>A unified, self-hosted educational platform combining virtual classrooms,<br/>AI-powered attendance, real-time engagement analytics, and non-destructive video editing —<br/>all secured over HTTPS with end-to-end encryption.</strong>
</p>

<br/>

<!-- Badges Row 1 -->
<p align="center">
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/></a>
  <a href="https://djangoproject.com"><img src="https://img.shields.io/badge/Django-4.2-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"/></a>
  <a href="https://github.com/django/daphne"><img src="https://img.shields.io/badge/Daphne-ASGI%20%2F%20HTTPS-7B3F85?style=for-the-badge" alt="Daphne"/></a>
  <a href="https://livekit.io"><img src="https://img.shields.io/badge/LiveKit-WebRTC%20SFU-00C58E?style=for-the-badge" alt="LiveKit"/></a>
</p>

<!-- Badges Row 2 -->
<p align="center">
  <a href="https://opencv.org"><img src="https://img.shields.io/badge/OpenCV-Computer%20Vision-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white" alt="OpenCV"/></a>
  <a href="https://ffmpeg.org"><img src="https://img.shields.io/badge/FFmpeg-Video%20Processing-007808?style=for-the-badge" alt="FFmpeg"/></a>
  <a href="https://redis.io"><img src="https://img.shields.io/badge/Redis-Celery%20Queue-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis"/></a>
  <img src="https://img.shields.io/badge/HTTPS-SSL%20%2F%20TLS-4CAF50?style=for-the-badge&logo=letsencrypt&logoColor=white" alt="HTTPS"/>
</p>

<!-- Badges Row 3 -->
<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License"/></a>
  <img src="https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge" alt="Status"/>
  <img src="https://img.shields.io/badge/PRs-Welcome-orange?style=for-the-badge" alt="PRs Welcome"/>
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20Docker-blue?style=for-the-badge" alt="Platform"/>
</p>

<br/>

</div>

---

## 📌 Table of Contents

- [What is EduMi 2?](#-what-is-edumi-2)
- [Why EduMi 2?](#-why-edumi-2)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Project Directory Structure](#-project-directory-structure)
- [Setup & Installation Guides](#-setup--installation-guides)
- [Technical Architecture Specification](#-technical-architecture-specification)
- [Ports & Credentials Reference](#-ports--credentials-reference)
- [Contributing & License](#-contributing--license)

---

## 🎯 What is EduMi 2?

> **EduMi 2** replaces the fragmented patchwork of tools schools rely on today — video conferencing software, manual attendance registers, surveillance dashboards, and standalone video editors — with a **single, unified, self-hosted platform**.

Everything runs securely over **HTTPS**. Biometrics are **encrypted at rest**. Real-time communications are powered by low-latency **WebSockets** and **WebRTC SFU**. Zero third-party cloud dependencies required.

---

## 💡 Why EduMi 2?

<div align="center">

| ❌ The Old School Way | ✅ The EduMi 2 Way |
| :--- | :--- |
| Manual roll call wastes 5–10 min per class | **AI face-recognition attendance** — 100% automated |
| Zero visibility into student attention/mood | **Real-time engagement scoring** + emotion detection |
| 5+ fragmented tools to manage & pay for | **One platform** for meetings, cameras, recordings & editing |
| Raw biometric data stored in plaintext | **Fernet AES-256 encryption** for all face embeddings |
| Expensive dedicated IP camera hardware | Use any standard **Android / iPhone** as a live classroom feed |
| Video meetings served over insecure channels | Full **HTTPS** via self-signed certs & Daphne ASGI |

</div>

---

## ✨ Key Features

- **🔐 HTTPS Everywhere**: Native SSL support with Daphne ASGI, secure cookies (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`), and simple local trust script integration.
- **🤖 AI Attendance & Engagement**: Automatic roll call using `dlib` face embedding vector analysis. Embeddings are Fernet-encrypted. Continuous polling tracks active presence.
- **📊 Real-Time Emotion & Attention Tracking**: Captures emotional states and attention indexes. Aggregates data into visual trends and teacher report dashboards.
- **🎥 Hybrid Camera Integration**: Interfaces with RTSP surveillance cameras and phones running IP webcam feeds. Runs parallel frames through CV analysis.
- **🖥️ Low-Latency Virtual Classrooms**: Powered by **LiveKit SFU WebRTC** with automated meeting attendance log entries, raised-hands queues, and instant text chats.
- **✂️ Non-Destructive Video Editor**: Browser-level auto-saving, keyboard shortcuts (`Space` to play, `S` to split, `Del` to delete), and single-pass FFmpeg export filtergraphs.

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                       Browser / Client                       │
│           HTTPS  ·  WebSocket (wss://)  ·  WebRTC            │
└────────────────────────────┬─────────────────────────────────┘
                             │
               ┌─────────────▼─────────────┐
               │   Nginx : 443   (prod)     │  ← SSL termination + static files
               │   Daphne : 8002 (dev)      │  ← HTTPS + WSS direct
               └─────────────┬─────────────┘
                             │
              ┌────────────────▼────────────────┐
              │          Django Main App          │
              │        school_project/            │
              │  ┌──────────┐   ┌─────────────┐  │
              │  │ accounts │   │  meetings   │  │  ← Auth, profiles, messaging
              │  │          │   │  (LiveKit)  │  │  ← Virtual classrooms
              │  ├──────────┤   ├─────────────┤  │
              │  │attendance│   │   cameras   │  │  ← Face AI + engagement
              │  │          │   │   (RTSP)    │  │  ← Hardware camera mgmt
              │  ├──────────┤   ├─────────────┤  │
              │  │  videos  │   │video_editing│  │  ← Upload & storage
              │  │          │   │             │  │  ← Non-destructive editor
              │  ├──────────┤   ├─────────────┤  │
              │  │  mobile  │   │   common    │  │  ← Phone cameras
              │  │ cameras  │   │             │  │  ← Shared utilities
              │  └──────────┘   └─────────────┘  │
              └────────────┬──────────┬───────────┘
                           │          │
                 ┌──────────▼──┐  ┌───▼──────┐
                 │  SQLite /    │  │  Redis   │
                 │ PostgreSQL   │  │  :6379   │
                 └─────────────┘  └────┬─────┘
                                       │
                         ┌──────────────┴─────────────┐
                         │                             │
             ┌───────────▼──────────┐   ┌─────────────▼──────┐
             │    Celery Worker     │   │   Camera Service    │
             │  (face processing,   │   │   :8003 (Waitress)  │
             │   report gen,        │   │   ─ MJPEG proxy     │
             │   recording mgmt)    │   │   ─ Head counting   │
             └──────────────────────┘   │   ─ Face detection  │
                                        └──────────┬──────────┘
                                                   │
                                      ┌────────────▼────────────┐
                                      │   LiveKit SFU : 7880    │
                                      │   WebRTC peer routing   │
                                      └─────────────────────────┘
```

For a comprehensive technical breakdown of service topology, client-side track registries, biometric encryption pipelines, and timeline compilation, please consult the complete design documentation.

> [!TIP]
> 📖 Read the detailed **[Technical Architecture & Integration Specifications](TECHNICAL_ARCHITECTURE.md)** for a deep dive into the code infrastructure.

---

## 📁 Project Directory Structure

```
Edumi2/
├── school_project/          # Django project configuration, ASGI & Celery routes
├── accounts/                # User authentication, roles, and notifications
├── attendance/              # Face profiling and attention tracking database logic
├── cameras/                 # Hardware camera MJPEG proxies and controls
├── mobile_cameras/          # Mobile phone IP camera pipelines
├── meetings/                # LiveKit WebRTC meetings room & consumer routes
├── videos/                  # General repository for video upload storage
├── video_editing/           # Non-destructive editor sequencing and commands
├── common/                  # Shared classes and UI elements
├── camera_service/          # Waitress microservice running CV pipelines (port 8003)
├── templates/               # Global templates directory
├── static/                  # Shared CSS, JS files, assets
├── config/                  # Configuration files (LiveKit, environmental examples)
├── certs/                   # Local SSL/TLS keys
└── scripts/                 # Administration and setups script suite
```

---

## 🛠️ Setup & Installation Guides

To make the onboarding process cleaner and easier to read, we have divided the installation instructions based on target environments:

*   🏁 **[Windows Developer Setup Guide](SETUP_WINDOWS.md)** — Detailed steps for running locally on Windows.
*   🐧 **[Linux Developer Setup Guide](SETUP_LINUX.md)** — Instructions for setting up development environments on Linux.
*   🐳 **[Production Server Deployment Guide](SETUP_PRODUCTION.md)** — Instructions for deploying using Docker Compose, systemd, and Nginx.

---

## ⚙️ Technical Architecture Specification

If you are developing features, extending the face-matching service, or contributing to the video editor's FFmpeg filter compilation pipelines, read the architecture runbook:

👉 **[TECHNICAL_ARCHITECTURE.md](TECHNICAL_ARCHITECTURE.md)**

It contains:
- Service topologies and communication protocols (ASGI, Daphne, Redis).
- LiveKit WebRTC SFU client-side track registry details (`TrackManager`).
- Fernet AES-256 biometric encryption specifications.
- Non-destructive video editing and compiler filtergraph setups.
- Waitress CV service orchestration and troubleshooting schemas.

---

## 🔢 Ports & Credentials Reference

<div align="center">

| Service | Port | Protocol | Usage |
|---|---|---|---|
| Django / Daphne | **8002** | HTTPS / WSS | Local web client interface |
| Camera Service (Waitress) | **8003** | HTTP | Internal AI computer vision calculations |
| LiveKit SFU | **7880** | WS / HTTP | WebRTC media engine signaling |
| Redis | **6379** | TCP | Task broker queue & channel layer |
| Nginx (Production) | **443** | HTTPS | Production ingress port |

</div>

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

1. Fork the repository.
2. Create your branch: `git checkout -b feature/your-feature-name`
3. Commit your changes: `git commit -m 'feat: add some feature'`
4. Push to the branch: `git push origin feature/your-feature-name`
5. Open a Pull Request.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

<div align="center">

**Built for better classrooms.**

<sub>Made with ❤️ by <a href="https://github.com/GAuravgiy87">GAuravgiy87</a> and <a href="https://github.com/tarunkumar-sys">tarunkumar-sys</a>.</sub>

</div>