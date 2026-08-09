# 🏁 Windows Developer Setup Guide — EduMi 2

This guide walks you through setting up a complete **EduMi 2** development environment on a brand-new Windows machine.

---

## 📋 Prerequisites

Install the following software packages before setting up the repository.

### 1. Python 3.11+
1. Go to [python.org/downloads](https://python.org/downloads/) and download Python 3.11.x or 3.12.x.
2. Run the installer.
3. ⚠️ **IMPORTANT**: Check the box for **"Add Python to PATH"** at the bottom of the first screen.
4. Click **Install Now**.
5. Verify in Command Prompt:
   ```cmd
   python --version
   ```

### 2. Git
1. Download from [git-scm.com/download/win](https://git-scm.com/download/win).
2. Install with all default settings.

### 3. FFmpeg (For Recording & Video Processing)
1. Go to [ffmpeg.org/download.html](https://ffmpeg.org/download.html) and select **Windows builds by BtbN**.
2. Download `ffmpeg-master-latest-win64-gpl.zip`.
3. Extract the ZIP and move the folder to `C:\ffmpeg`.
4. Add the binary to your Path:
   - Search for **"Environment Variables"** in the Windows Start menu.
   - Click **Environment Variables...**
   - Select the **Path** variable under System Variables and click **Edit**.
   - Click **New** and type `C:\ffmpeg\bin`.
   - Click **OK** on all dialog boxes to save.
5. Verify in a new Command Prompt:
   ```cmd
   ffmpeg -version
   ```

### 4. Redis (Choose Option A or B)

#### Option A: Native Windows Redis (Easiest)
1. Download `Redis-x64-3.0.504.msi` from [microsoftarchive/redis releases](https://github.com/microsoftarchive/redis/releases).
2. Run the installer. Redis will run automatically as a Windows background service.
3. Verify:
   ```cmd
   redis-cli ping
   # Expected response: PONG
   ```

#### Option B: WSL2 Redis (Recommended for Production Parity)
1. Enable WSL2 in an Administrator PowerShell:
   ```powershell
   wsl --install
   ```
2. Restart your computer if prompted.
3. Open the **Ubuntu** app from the Start menu, configure your username/password, and run:
   ```bash
   sudo apt update
   sudo apt install redis-server -y
   sudo service redis-server start
   ```

### 5. LiveKit Server Binary
1. Create a directory named `livekit-bin` in the root of the project.
2. Download the latest Windows release from [LiveKit GitHub Releases](https://github.com/livekit/livekit/releases) (e.g. `livekit-server_windows_amd64.zip`).
3. Extract it and place `livekit-server.exe` inside your project's `livekit-bin/` directory.

---

## ⚙️ Project Setup

### Step 1: Clone the Repository
Open Command Prompt and navigate to where you want the project:
```cmd
git clone -b new_edumi https://github.com/GAuravgiy87/Edumi2.git
cd Edumi2
```

### Step 2: Create a Virtual Environment
```cmd
python -m venv venv
venv\Scripts\activate
```

### Step 3: Install Dependencies
```cmd
pip install -r requirements.txt
```

### Step 4: Configure Environment File
```cmd
copy config\.env.example .env
```
Open the `.env` file in a text editor (e.g. `notepad .env`) and populate:
- `SECRET_KEY`: Generate one using `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- `FACE_ENCRYPTION_KEY`: Generate one using `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Make sure `LIVEKIT_API_SECRET` matches your configuration in `config/livekit.yaml` (default is `devsecret_must_be_32_characters_long_1234`).

### Step 5: Run Database Migrations
```cmd
python manage.py migrate
```

### Step 6: Create Admin User
```cmd
python manage.py createsuperuser
```

### Step 7: Generate and Trust SSL/TLS Certificates
To enable secure HTTPS & WSS (WebSocket) capabilities locally:
1. Generate the certificates:
   ```cmd
   python scripts/generate_ssl_cert.py
   ```
2. Trust the certificates (removes browser privacy warnings):
   Double-click the file `scripts\trust_ssl_cert.bat` in File Explorer, and approve the Administrator (UAC) prompt.
3. Restart your browser (`chrome://restart` in Chrome).

---

## ▶️ Running the Application

### 1. One-Click Startup (Recommended)
Double-click `start_app.bat` in the project root, or execute via PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File start_app.ps1
```
This script validates your environment, starts Redis, runs Celery workers, starts the camera microservice, launches the LiveKit server, and spins up the Daphne HTTPS server.

### 2. Manual Startup (Advanced)
If you prefer running services in separate terminals, open 5 Command Prompts and activate the virtual environment in each:

- **Terminal 1 (Redis)**: `redis-server` (if not running as service)
- **Terminal 2 (LiveKit)**: `.\livekit-bin\livekit-server.exe --config config\livekit.yaml`
- **Terminal 3 (Camera Service)**: `python camera_service/serve.py`
- **Terminal 4 (Celery)**: `celery -A school_project worker -l info -P threads`
- **Terminal 5 (Daphne Web)**: `python run_ssl_server.py`

Navigate to: `https://localhost:8002` (or `https://edumi.ac.in:8002` if hosts file is configured).
