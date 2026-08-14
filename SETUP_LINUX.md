# 🐧 Linux Developer Setup Guide — EduMi 2

This guide outlines setup instructions for running a **EduMi 2** development environment on **Ubuntu / Debian** based Linux systems.

---

## 📋 System Prerequisites

Install the required operating system dependencies:

```bash
# 1. Update package managers
sudo apt update && sudo apt upgrade -y

# 2. Install Python 3.11+, virtual environments, and compiler tools
sudo apt install python3.11 python3.11-dev python3.11-venv python3-pip git -y

# 3. Install build tools and libraries for OpenCV / dlib compilation
sudo apt install cmake build-essential libopenblas-dev liblapack-dev libx11-dev libgtk-3-dev -y

# 4. Install Redis (Real-time broker)
sudo apt install redis-server -y
sudo systemctl enable redis-server
sudo systemctl start redis-server

# 5. Install FFmpeg (Multimedia operations)
sudo apt install ffmpeg -y
```

Verify your prerequisite stack is running:
```bash
python3.11 --version   # Python 3.11.x
ffmpeg -version        # FFmpeg details
redis-cli ping         # Returns: PONG
```

---

## 📡 LiveKit Server (SFU) Setup

Download and extract the LiveKit server binary in the repository space:

```bash
wget https://github.com/livekit/livekit/releases/latest/download/livekit_linux_amd64.tar.gz
tar -xzf livekit_linux_amd64.tar.gz
# Place it under livekit-bin in the cloned repository directory (see below)
```

---

## ⚙️ Project Installation

### Step 1: Clone the Repository
```bash
git clone -b new_edumi https://github.com/GAuravgiy87/Edumi2.git
cd Edumi2
```

### Step 2: Organize Binaries
```bash
mkdir -p livekit-bin
mv ../livekit-server livekit-bin/
chmod +x livekit-bin/livekit-server
```

### Step 3: Setup Virtual Environment & Install Requirements
```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### Step 4: Environment Configurations
```bash
cp config/.env.example .env
nano .env
```
Generate and populate keys:
- Generate `SECRET_KEY`: `python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- Generate `FACE_ENCRYPTION_KEY`: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Make sure `LIVEKIT_API_SECRET` matches your configuration key in `config/livekit.yaml` (default: `devsecret_must_be_32_characters_long_1234`).

### Step 5: Database Schema Provisioning
```bash
python manage.py migrate
python manage.py createsuperuser
```

### Step 6: SSL Certificate Generation
Generate certificates to enable HTTPS & Secure WebSockets:
```bash
python scripts/generate_ssl_cert.py
```
To trust the certificate locally:
```bash
sudo cp certs/edumi.crt /usr/local/share/ca-certificates/edumi.crt
sudo update-ca-certificates
```

---

## ▶️ Running the Application

### Option A: Complete System Startup (Helper script)
```bash
chmod +x start.sh
./start.sh
```

### Option B: Manual Startup (Multi-terminal)
Run these commands in separate terminal sessions with the virtual environment activated:

1. **LiveKit Server**:
   ```bash
   ./livekit-bin/livekit-server --config config/livekit.yaml
   ```
2. **Camera Service**:
   ```bash
   python camera_service/serve.py
   ```
3. **Celery Worker**:
   ```bash
   celery -A school_project worker -l info -P threads
   ```
4. **Daphne Web App**:
   ```bash
   python run_ssl_server.py
   ```

Navigate to: `https://localhost:8002` or your Linux machine's local IP address.
