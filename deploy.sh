#!/usr/bin/env bash
# ==============================================================================
#  EduMi2 — Single-File Master Deployment Orchestrator for Ubuntu Server
#  Tested on: Ubuntu 20.04 / 22.04 / 24.04 LTS, Debian 11 / 12 (Without Docker)
# ==============================================================================
#  USAGE:
#    sudo bash deploy.sh
#
#  OPTIONAL OPTIONS:
#    --domain       Your domain name (e.g. --domain eclass.dei.ac.in)
#    --email        Notification email for SSL (e.g. --email admin@edumi.ac.in)
#    --db-host      Remote database host IP (Default: 127.0.0.1)
#    --db-pass      Custom database password
#    --letsencrypt  Request an official Let's Encrypt public SSL cert
# ==============================================================================

set -eo pipefail

# ANSI Color Utilities
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "  ${GREEN}[✓]${NC} $1"; }
info() { echo -e "  ${BLUE}[i]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[!]${NC} $1"; }
err()  { echo -e "  ${RED}[✗]${NC} $1"; exit 1; }
step() {
    echo ""
    echo -e "${BOLD}${CYAN}================================================= ${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BOLD}${CYAN}================================================= ${NC}"
}

DOMAIN="eclass.dei.ac.in"
EMAIL=""
DB_HOST="127.0.0.1"
USE_LETSENCRYPT=false
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="edumi"
DB_NAME="edumi_db"
DB_USER="edumi_admin"
DB_PASS=""
NODE_IP=""

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)       DOMAIN="$2";   shift 2 ;;
        --email)        EMAIL="$2";    shift 2 ;;
        --db-host)      DB_HOST="$2";  shift 2 ;;
        --db-pass)      DB_PASS="$2";  shift 2 ;;
        --node-ip)      NODE_IP="$2";  shift 2 ;;
        --letsencrypt)  USE_LETSENCRYPT=true; shift ;;
        *) warn "Unknown argument: $1"; shift ;;
    esac
done

# Resolve DB_PASS: Use CLI arg -> existing .env -> generate secure random
if [ -z "$DB_PASS" ]; then
    DB_PASS=$(grep '^POSTGRES_PASSWORD=' "$APP_DIR/.env" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- | tr -d '"' | tr -d "'" || echo "")
fi
if [ -z "$DB_PASS" ]; then
    DB_PASS=$(grep '^DATABASE_URL=' "$APP_DIR/.env" 2>/dev/null | sed -n 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/p' || echo "")
fi
if [ -z "$DB_PASS" ]; then
    DB_PASS=$(openssl rand -hex 16 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(16))" 2>/dev/null || echo "edumi_$(date +%s)_dbpass")
fi

# Detect Ubuntu Server LAN IP Address
LAN_IP=$(ip route get 8.8.8.8 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1); exit}')
if [ -z "$LAN_IP" ]; then
    LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
if [ -z "$LAN_IP" ]; then
    LAN_IP="127.0.0.1"
fi

# Detect Public IP if available (for cloud VPS deployments)
PUBLIC_IP=$(curl -s --max-time 3 https://api.ipify.org 2>/dev/null || curl -s --max-time 3 https://icanhazip.com 2>/dev/null || echo "")
if [ "$PUBLIC_IP" = "$LAN_IP" ]; then
    PUBLIC_IP=""
fi

echo ""
echo -e "${BOLD}${GREEN}"
echo "  ███████╗██████╗ ██╗   ██╗███╗   ███╗██╗"
echo "  ██╔════╝██╔══██╗██║   ██║████╗ ████║██║"
echo "  █████╗  ██║  ██║██║   ██║██╔████╔██║██║"
echo "  ██╔══╝  ██║  ██║██║   ██║██║╚██╔╝██║██║"
echo "  ███████╗██████╔╝╚██████╔╝██║ ╚═╝ ██║██║"
echo "  ╚══════╝╚═════╝  ╚═════╝ ╚═╝     ╚═╝╚═╝"
echo -e "${NC}"
echo -e "  ${BOLD}EduMi2 Single-File Ubuntu Server Deployment Orchestrator${NC}"
echo -e "  Directory  : ${CYAN}${APP_DIR}${NC}"
echo -e "  Domain     : ${CYAN}${DOMAIN}${NC} (HTTPS Enforced)"
echo -e "  LAN IP     : ${CYAN}${LAN_IP}${NC}"
if [ -n "$PUBLIC_IP" ]; then
    echo -e "  Public IP  : ${CYAN}${PUBLIC_IP}${NC}"
fi
echo -e "  DB Host    : ${CYAN}${DB_HOST}${NC}"
echo ""

# ------------------------------------------------------------------------------
step "STEP 1: Root Check, Swap Allocation, & Ubuntu Packages"
# ------------------------------------------------------------------------------
IS_ROOT=false
if [ "$(id -u)" -eq 0 ]; then IS_ROOT=true; fi

if [ "$IS_ROOT" = false ]; then
    warn "Running without root privileges. If package installation fails, re-run with: sudo bash deploy.sh"
fi

# Set up Local DNS entries in /etc/hosts for domain
if [ "$IS_ROOT" = true ]; then
    if ! grep -q "$DOMAIN" /etc/hosts; then
        info "Configuring Local DNS in /etc/hosts for $DOMAIN..."
        echo -e "\n# EduMi2 Local DNS Resolution\n127.0.0.1\t$DOMAIN www.$DOMAIN\n$LAN_IP\t$DOMAIN www.$DOMAIN" >> /etc/hosts
        log "Added $DOMAIN and www.$DOMAIN to /etc/hosts"
    fi
fi

# Apply UFW Firewall rules for LAN IP, LiveKit, & HTTPS access
if command -v ufw &>/dev/null && [ "$IS_ROOT" = true ]; then
    ufw allow 80/tcp 2>/dev/null || true
    ufw allow 443/tcp 2>/dev/null || true
    ufw allow 8008/tcp 2>/dev/null || true
    ufw allow 7880/tcp 2>/dev/null || true
    ufw allow 7881/tcp 2>/dev/null || true
    ufw allow 7882/udp 2>/dev/null || true
    ufw allow 50000:50200/udp 2>/dev/null || true
    info "UFW firewall rules applied (Ports 80, 443, 8008, 7880, 7881, 7882/udp allowed)."
fi

info "Checking system memory capacity..."
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)
TOTAL_RAM_GB=$(awk "BEGIN {print $TOTAL_RAM_KB / 1024 / 1024}")
info "RAM Capacity: ${TOTAL_RAM_GB:0:4} GB"

# Automatic Swap allocation (prevents OOM-killer crashes on 1GB/2GB VPS during static compile or OpenCV loading)
if [ "$IS_ROOT" = true ]; then
    TOTAL_SWAP_KB=$(grep SwapTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)
    if [ "$TOTAL_SWAP_KB" -lt 1000000 ]; then
        info "Low swap detected ($(($TOTAL_SWAP_KB / 1024)) MB). Allocating 2GB swapfile to prevent Out-Of-Memory crashes..."
        if [ ! -f /swapfile ]; then
            fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 2>/dev/null || true
            chmod 600 /swapfile 2>/dev/null || true
            mkswap /swapfile 2>/dev/null || true
            swapon /swapfile 2>/dev/null || true
            if ! grep -q '/swapfile' /etc/fstab 2>/dev/null; then
                echo '/swapfile none swap sw 0 0' >> /etc/fstab
            fi
            log "2GB swapfile activated successfully."
        fi
    fi
fi

if [ "$IS_ROOT" = true ]; then
    info "Installing/updating required Ubuntu system packages..."
    apt-get update -qq
    apt-get install -y -qq software-properties-common curl wget git openssl net-tools 2>/dev/null || true

    apt-get install -y -qq \
        python3 python3-venv python3-dev python3-pip \
        build-essential cmake g++ libpq-dev libffi-dev \
        ffmpeg postgresql postgresql-contrib redis-server nginx supervisor \
        libopenblas-dev liblapack-dev libgl1 libglx-mesa0 libglib2.0-0 libsm6 libxext6 libxrender-dev 2>/dev/null \
        || apt-get install -y -qq libgl1-mesa-glx libglib2.0-0 2>/dev/null || true
    log "Ubuntu system packages installed."
fi

# ------------------------------------------------------------------------------
step "STEP 2: PostgreSQL Database Provisioning"
# ------------------------------------------------------------------------------
if [ "$DB_HOST" == "127.0.0.1" ] || [ "$DB_HOST" == "localhost" ]; then
    if [ "$IS_ROOT" = true ]; then
        systemctl start postgresql || true
        systemctl enable postgresql || true

        info "Provisioning local PostgreSQL database '$DB_NAME'..."
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true
        sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || true
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true
        sudo -u postgres psql -c "ALTER USER $DB_USER CREATEDB;" 2>/dev/null || true
        sudo -u postgres psql -c "ALTER DATABASE $DB_NAME OWNER TO $DB_USER;" 2>/dev/null || true
        sudo -u postgres psql -d $DB_NAME -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO $DB_USER;" 2>/dev/null || true
        sudo -u postgres psql -d $DB_NAME -c "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;" 2>/dev/null || true
        sudo -u postgres psql -d $DB_NAME -c "GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO $DB_USER;" 2>/dev/null || true
        sudo -u postgres psql -d $DB_NAME -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;" 2>/dev/null || true
        sudo -u postgres psql -d $DB_NAME -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;" 2>/dev/null || true
        sudo -u postgres psql -c "ALTER SYSTEM SET max_connections = '300';" 2>/dev/null || true
        sudo -u postgres psql -c "SELECT pg_reload_conf();" 2>/dev/null || true
        log "Local PostgreSQL database ready with max_connections=300 & full permissions."
    fi
else
    info "Using Remote PostgreSQL Database Host: $DB_HOST"
fi

# ------------------------------------------------------------------------------
step "STEP 3: Redis Server Setup"
# ------------------------------------------------------------------------------
if [ "$IS_ROOT" = true ]; then
    systemctl start redis-server || systemctl start redis || true
    systemctl enable redis-server 2>/dev/null || systemctl enable redis 2>/dev/null || true
    log "Redis service active."
fi

# ------------------------------------------------------------------------------
step "STEP 4: LiveKit SFU Server Binary Setup"
# ------------------------------------------------------------------------------
LIVEKIT_DIR="$APP_DIR/livekit-bin"
mkdir -p "$LIVEKIT_DIR"

if [ ! -f "$LIVEKIT_DIR/livekit-server" ]; then
    if [ -f "$LIVEKIT_DIR/livekit-server.exe" ]; then
        warn "Found Windows binary (livekit-server.exe) — removing it and downloading the correct Linux binary..."
        rm -f "$LIVEKIT_DIR/livekit-server.exe"
    fi

    ARCH=$(uname -m)
    LK_ARCH_PATTERN="linux_amd64.tar.gz"
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
        LK_ARCH_PATTERN="linux_arm64.tar.gz"
    fi
    info "Downloading LiveKit Server Linux ($ARCH) binary from GitHub releases..."
    LIVEKIT_DL_URL=$(curl -s https://api.github.com/repos/livekit/livekit/releases/latest \
        | grep "browser_download_url" | grep "$LK_ARCH_PATTERN" | head -1 \
        | cut -d '"' -f 4 || echo "")

    if [ -z "$LIVEKIT_DL_URL" ]; then
        info "GitHub API rate limit or network throttle; attempting direct release download..."
        LIVEKIT_DL_URL="https://github.com/livekit/livekit/releases/download/v1.7.2/livekit_1.7.2_${LK_ARCH_PATTERN}"
    fi

    if [ -n "$LIVEKIT_DL_URL" ]; then
        info "Downloading: $LIVEKIT_DL_URL"
        wget -q --show-progress -O /tmp/livekit.tar.gz "$LIVEKIT_DL_URL"
        tar -xzf /tmp/livekit.tar.gz -C "$LIVEKIT_DIR" livekit-server
        rm -f /tmp/livekit.tar.gz
        chmod +x "$LIVEKIT_DIR/livekit-server"
        log "LiveKit Linux binary installed in ./livekit-bin/livekit-server"
    else
        err "Could not fetch LiveKit download URL from GitHub API. Check internet access and try again."
    fi
else
    log "LiveKit Linux binary already present in ./livekit-bin/livekit-server"
fi

info "Configuring config/livekit.yaml for server IP (${NODE_IP:-$LAN_IP})..."
mkdir -p "$APP_DIR/config"

LK_KEY=$(grep '^LIVEKIT_API_KEY=' "$APP_DIR/.env" 2>/dev/null | cut -d '=' -f 2- | tr -d '"' | tr -d "'" || echo "")
LK_SECRET=$(grep '^LIVEKIT_API_SECRET=' "$APP_DIR/.env" 2>/dev/null | cut -d '=' -f 2- | tr -d '"' | tr -d "'" || echo "")

if [ -z "$LK_KEY" ]; then
    LK_KEY="edumi_lk_$(openssl rand -hex 6 2>/dev/null || date +%s)"
    if [ -f "$APP_DIR/.env" ]; then
        echo "LIVEKIT_API_KEY=$LK_KEY" >> "$APP_DIR/.env"
    fi
fi

if [ -z "$LK_SECRET" ]; then
    LK_SECRET=$(openssl rand -hex 20 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(20))" 2>/dev/null || echo "edumi_sec_$(date +%s)_32chars")
    if [ -f "$APP_DIR/.env" ]; then
        echo "LIVEKIT_API_SECRET=$LK_SECRET" >> "$APP_DIR/.env"
    fi
fi

cat > "$APP_DIR/config/livekit.yaml" <<EOF
port: 7880
bind_addresses:
  - "0.0.0.0"
rtc:
  tcp_port: 7881
  udp_port: 7882
  use_external_ip: false
  node_ip: "${NODE_IP:-$LAN_IP}"

keys:
  $LK_KEY: $LK_SECRET

room:
  empty_timeout: 300
  max_participants: 100

logging:
  level: info
EOF
log "LiveKit configuration updated in ./config/livekit.yaml (Keys synced with .env: $LK_KEY)"

# ------------------------------------------------------------------------------
step "STEP 4.5: Facial Recognition ONNX Neural Models Verification"
# ------------------------------------------------------------------------------
MODELS_DIR="$APP_DIR/models"
mkdir -p "$MODELS_DIR"

YUNET_FILE="$MODELS_DIR/face_detection_yunet_2023mar.onnx"
SFACE_FILE="$MODELS_DIR/face_recognition_sface_2021dec.onnx"

if [ ! -f "$YUNET_FILE" ] || [ $(stat -c%s "$YUNET_FILE" 2>/dev/null || echo 0) -lt 50000 ]; then
    info "Downloading YuNet face detection ONNX model from OpenCV Model Zoo..."
    wget -q --show-progress -O "$YUNET_FILE" \
        "https://raw.githubusercontent.com/opencv/opencv_zoo/master/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
        || curl -sSL -o "$YUNET_FILE" "https://raw.githubusercontent.com/opencv/opencv_zoo/master/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
        || true
fi

if [ ! -f "$SFACE_FILE" ] || [ $(stat -c%s "$SFACE_FILE" 2>/dev/null || echo 0) -lt 1000000 ]; then
    info "Downloading SFace face recognition ONNX model (38MB) from OpenCV Model Zoo..."
    wget -q --show-progress -O "$SFACE_FILE" \
        "https://raw.githubusercontent.com/opencv/opencv_zoo/master/models/face_recognition_sface/face_recognition_sface_2021dec.onnx" \
        || curl -sSL -o "$SFACE_FILE" "https://raw.githubusercontent.com/opencv/opencv_zoo/master/models/face_recognition_sface/face_recognition_sface_2021dec.onnx" \
        || true
fi

if [ -f "$YUNET_FILE" ] && [ -f "$SFACE_FILE" ]; then
    log "YuNet & SFace ONNX neural models verified in ./models/"
else
    warn "YuNet / SFace models could not be fetched automatically; fallback Haar cascades will be used if needed."
fi

# ------------------------------------------------------------------------------
step "STEP 5: Python Virtual Environment & Dependencies"
# ------------------------------------------------------------------------------
cd "$APP_DIR"
VENV_DIR="venv"
if [ -d "$APP_DIR/.venv" ]; then
    VENV_DIR=".venv"
elif [ -d "$APP_DIR/venv" ]; then
    VENV_DIR="venv"
fi

if [ ! -d "$VENV_DIR" ]; then
    PYTHON_BIN="python3"
    if command -v python3.11 &>/dev/null; then
        PYTHON_BIN="python3.11"
    fi
    info "Creating Python virtual environment using $PYTHON_BIN..."
    $PYTHON_BIN -m venv venv
    VENV_DIR="venv"
fi

VENV_PYTHON="$APP_DIR/$VENV_DIR/bin/python"
VENV_PIP="$APP_DIR/$VENV_DIR/bin/pip"

info "Installing Python packages from requirements.txt..."
$VENV_PIP install --upgrade pip setuptools wheel -q
$VENV_PIP install -r "$APP_DIR/requirements.txt" -q
log "Python environment ready inside ./$VENV_DIR"

# ------------------------------------------------------------------------------
step "STEP 6: Environment File (.env) Setup (HTTPS Only)"
# ------------------------------------------------------------------------------
ENV_FILE="$APP_DIR/.env"
info "Writing production .env file configured for HTTPS & $DOMAIN..."

EXISTING_SECRET=$(grep '^SECRET_KEY=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- | tr -d '"' | tr -d "'" || echo "")
EXISTING_FACE=$(grep '^FACE_ENCRYPTION_KEY=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- | tr -d '"' | tr -d "'" || echo "")

# Preserve existing SMTP configurations
EXISTING_EMAIL_BACKEND=$(grep '^EMAIL_BACKEND=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
[ -z "$EXISTING_EMAIL_BACKEND" ] && EXISTING_EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"

EXISTING_EMAIL_HOST=$(grep '^EMAIL_HOST=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
[ -z "$EXISTING_EMAIL_HOST" ] && EXISTING_EMAIL_HOST="smtp.gmail.com"

EXISTING_EMAIL_PORT=$(grep '^EMAIL_PORT=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
[ -z "$EXISTING_EMAIL_PORT" ] && EXISTING_EMAIL_PORT="587"

EXISTING_EMAIL_USE_TLS=$(grep '^EMAIL_USE_TLS=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
[ -z "$EXISTING_EMAIL_USE_TLS" ] && EXISTING_EMAIL_USE_TLS="True"

EXISTING_EMAIL_USE_SSL=$(grep '^EMAIL_USE_SSL=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
[ -z "$EXISTING_EMAIL_USE_SSL" ] && EXISTING_EMAIL_USE_SSL="False"

EXISTING_EMAIL_HOST_USER=$(grep '^EMAIL_HOST_USER=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
[ -z "$EXISTING_EMAIL_HOST_USER" ] && EXISTING_EMAIL_HOST_USER="YOUR_EMAIL@gmail.com"

EXISTING_EMAIL_HOST_PASSWORD=$(grep '^EMAIL_HOST_PASSWORD=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
[ -z "$EXISTING_EMAIL_HOST_PASSWORD" ] && EXISTING_EMAIL_HOST_PASSWORD="YOUR_APP_PASSWORD"

EXISTING_DEFAULT_FROM_EMAIL=$(grep '^DEFAULT_FROM_EMAIL=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
[ -z "$EXISTING_DEFAULT_FROM_EMAIL" ] && EXISTING_DEFAULT_FROM_EMAIL="EduMi Support <YOUR_EMAIL@gmail.com>"

# Preserve existing AI configurations
EXISTING_AI_LLM_URL=$(grep '^AI_LLM_URL=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
EXISTING_AI_LLM_BEARER_TOKEN=$(grep '^AI_LLM_BEARER_TOKEN=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
EXISTING_AI_MODEL_NAME=$(grep '^AI_MODEL_NAME=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
EXISTING_AI_EMBEDDING_URL=$(grep '^AI_EMBEDDING_URL=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
EXISTING_AI_EMBEDDING_MODEL=$(grep '^AI_EMBEDDING_MODEL=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
EXISTING_OPENAI_API_KEY=$(grep '^OPENAI_API_KEY=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")
EXISTING_OPENAI_MODEL=$(grep '^OPENAI_MODEL=' "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d '=' -f 2- || echo "")

# Collect any additional custom user environment variables
CUSTOM_ENV_KEYS=$(grep -v '^\s*#' "$ENV_FILE" 2>/dev/null | grep -v '^\s*$' | grep '=' | grep -v '^\(SECRET_KEY\|DEBUG\|ALLOWED_HOSTS\|SERVER_IP\|LOG_LEVEL\|DATABASE_URL\|REDIS_URL\|LIVEKIT_\|SECURE_SSL_REDIRECT\|SESSION_COOKIE_SECURE\|CSRF_COOKIE_SECURE\|FACE_\|CSRF_TRUSTED_ORIGINS\|CAMERA_\|FFMPEG_\|FFPROBE_\|EMAIL_\|DEFAULT_FROM_EMAIL\|AI_\|OPENAI_\|COMPRESS_\)' || echo "")

if [ -n "$EXISTING_SECRET" ]; then
    SECRET_KEY=$EXISTING_SECRET
else
    SECRET_KEY=$(openssl rand -base64 32 | tr -d '/+=' | head -c 50 2>/dev/null || $VENV_PYTHON -c "import secrets; print(secrets.token_urlsafe(40))" 2>/dev/null || echo "secret_edumi_$(date +%s)_key")
fi

if [ -n "$EXISTING_FACE" ]; then
    FACE_KEY=$EXISTING_FACE
else
    FACE_KEY=$($VENV_PYTHON -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || openssl rand -base64 32 2>/dev/null || echo "")
fi

DATABASE_URL_STR="postgres://$DB_USER:$DB_PASS@$DB_HOST:5432/$DB_NAME"

# Assemble complete allowed hosts and trusted origins including both LAN and Public IPs
ALLOWED_HOSTS_STR="$DOMAIN,www.$DOMAIN,localhost,127.0.0.1,$LAN_IP"
CSRF_TRUSTED_STR="https://$DOMAIN,https://www.$DOMAIN,https://localhost,https://127.0.0.1,https://$LAN_IP"
if [ -n "$PUBLIC_IP" ]; then
    ALLOWED_HOSTS_STR="$ALLOWED_HOSTS_STR,$PUBLIC_IP"
    CSRF_TRUSTED_STR="$CSRF_TRUSTED_STR,https://$PUBLIC_IP"
fi

cat > "$ENV_FILE" <<EOF
SECRET_KEY=$SECRET_KEY
DEBUG=False
ALLOWED_HOSTS=$ALLOWED_HOSTS_STR
SERVER_IP=$LAN_IP
LOG_LEVEL=INFO

DATABASE_URL=$DATABASE_URL_STR
REDIS_URL=redis://127.0.0.1:6379/0

LIVEKIT_URL=wss://$DOMAIN/livekit-proxy/
LIVEKIT_INTERNAL_URL=ws://127.0.0.1:7880
LIVEKIT_INTERNAL_HTTP_URL=http://127.0.0.1:7880
LIVEKIT_API_KEY=$LK_KEY
LIVEKIT_API_SECRET=$LK_SECRET

SECURE_SSL_REDIRECT=$([ "$USE_LETSENCRYPT" = true ] || [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ] && echo "True" || echo "False")
SESSION_COOKIE_SECURE=$([ "$USE_LETSENCRYPT" = true ] || [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ] && echo "True" || echo "False")
CSRF_COOKIE_SECURE=$([ "$USE_LETSENCRYPT" = true ] || [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ] && echo "True" || echo "False")

FACE_ENCRYPTION_KEY=$FACE_KEY
FACE_MATCH_THRESHOLD=0.50
FACE_PRESENCE_DURATION=30

CSRF_TRUSTED_ORIGINS=$CSRF_TRUSTED_STR

CAMERA_SERVICE_PORT=8008
CAMERA_SERVICE_URL=http://127.0.0.1:8008

FFMPEG_BINARY=ffmpeg
FFPROBE_BINARY=ffprobe

COMPRESS_ENABLED=True
COMPRESS_OFFLINE=True

# SMTP Email Configuration
EMAIL_BACKEND=$EXISTING_EMAIL_BACKEND
EMAIL_HOST=$EXISTING_EMAIL_HOST
EMAIL_PORT=$EXISTING_EMAIL_PORT
EMAIL_USE_TLS=$EXISTING_EMAIL_USE_TLS
EMAIL_USE_SSL=$EXISTING_EMAIL_USE_SSL
EMAIL_HOST_USER=$EXISTING_EMAIL_HOST_USER
EMAIL_HOST_PASSWORD=$EXISTING_EMAIL_HOST_PASSWORD
DEFAULT_FROM_EMAIL=$EXISTING_DEFAULT_FROM_EMAIL

# AI Model & RAG Workspace Configuration
AI_LLM_URL=$EXISTING_AI_LLM_URL
AI_LLM_BEARER_TOKEN=$EXISTING_AI_LLM_BEARER_TOKEN
AI_MODEL_NAME=${EXISTING_AI_MODEL_NAME:-phi:latest}
AI_EMBEDDING_URL=$EXISTING_AI_EMBEDDING_URL
AI_EMBEDDING_MODEL=${EXISTING_AI_EMBEDDING_MODEL:-nomic-embed-text:latest}
OPENAI_API_KEY=$EXISTING_OPENAI_API_KEY
OPENAI_MODEL=${EXISTING_OPENAI_MODEL:-gpt-4o-mini}
EOF

if [ -n "$CUSTOM_ENV_KEYS" ]; then
    echo "" >> "$ENV_FILE"
    echo "# Custom User Environment Variables (Preserved)" >> "$ENV_FILE"
    echo "$CUSTOM_ENV_KEYS" >> "$ENV_FILE"
fi

# Restrict .env permissions so secrets/keys are only readable by owner
chmod 600 "$ENV_FILE"
log ".env updated and permissions locked down (chmod 600)."

# ------------------------------------------------------------------------------
step "STEP 7: Directories & SSL Certificate Setup"
# ------------------------------------------------------------------------------
mkdir -p staticfiles database/media certs logs config models

if [ "$USE_LETSENCRYPT" = true ] && [ "$IS_ROOT" = true ]; then
    info "Provisioning official Let's Encrypt public SSL certificate for $DOMAIN..."
    bash "$APP_DIR/scripts/setup_letsencrypt.sh" --domain "$DOMAIN" ${EMAIL:+--email "$EMAIL"} || true
elif [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    info "Using official Let's Encrypt public SSL certificate for $DOMAIN..."
    cp -L "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" certs/edumi.crt
    cp -L "/etc/letsencrypt/live/$DOMAIN/privkey.pem" certs/edumi.key
else
    info "Generating SAN SSL certificate for $DOMAIN, www.$DOMAIN, localhost, and $LAN_IP..."
    SAN_EXT="subjectAltName=DNS:$DOMAIN,DNS:www.$DOMAIN,DNS:localhost,IP:127.0.0.1,IP:$LAN_IP"
    if [ -n "$PUBLIC_IP" ]; then
        SAN_EXT="${SAN_EXT},IP:$PUBLIC_IP"
    fi

    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout certs/edumi.key -out certs/edumi.crt \
        -subj "/C=IN/ST=Academic/L=EduMi/O=EduMi/CN=$DOMAIN" \
        -addext "$SAN_EXT" 2>/dev/null || true
fi

# Lock down SSL private keys & directory permissions
mkdir -p "$APP_DIR/logs" "$APP_DIR/staticfiles" "$APP_DIR/database/media" "$APP_DIR/certs" "$APP_DIR/config" "$APP_DIR/models"
chmod 700 "$APP_DIR/certs" 2>/dev/null || true
chmod 600 "$APP_DIR/certs/edumi.key" 2>/dev/null || true
chmod 644 "$APP_DIR/certs/edumi.crt" 2>/dev/null || true
chmod 750 "$APP_DIR/logs" "$APP_DIR/database" 2>/dev/null || true
log "SSL Certificates generated and secured (Key permissions 600)."

# ------------------------------------------------------------------------------
step "STEP 8: Django Database Migrations & Static Collection"
# ------------------------------------------------------------------------------
info "Running database migrations..."
$VENV_PYTHON manage.py migrate --noinput
log "Database schema initialized successfully."

info "Collecting static files & compressing template assets..."
$VENV_PYTHON manage.py collectstatic --noinput --clear
$VENV_PYTHON manage.py compress --force || true
$VENV_PYTHON manage.py collectstatic --noinput

# Ensure parent directory traversal for Nginx www-data user without exposing private keys
if [ "$IS_ROOT" = true ]; then
    info "Setting directory traversal and read permissions for Nginx (www-data)..."
    CUR_DIR="$APP_DIR"
    while [ "$CUR_DIR" != "/" ] && [ "$CUR_DIR" != "." ]; do
        chmod a+rx "$CUR_DIR" 2>/dev/null || true
        CUR_DIR="$(dirname "$CUR_DIR")"
    done
    chmod -R a+rX "$APP_DIR/staticfiles" "$APP_DIR/database/media" "$APP_DIR/models" "$APP_DIR/static" 2>/dev/null || true
    chmod 750 "$APP_DIR/database" "$APP_DIR/logs" 2>/dev/null || true
    chown -R root:www-data "$APP_DIR/staticfiles" "$APP_DIR/database/media" "$APP_DIR/logs" 2>/dev/null || true
fi
log "Static assets compressed, collected, and permissions granted to Nginx."

# ------------------------------------------------------------------------------
step "STEP 9: Systemd Microservice Installation"
# ------------------------------------------------------------------------------
if [ "$IS_ROOT" = true ]; then
    info "Creating Systemd service unit files..."

    VENV_DAPHNE="$APP_DIR/$VENV_DIR/bin/daphne"
    VENV_CELERY="$APP_DIR/$VENV_DIR/bin/celery"

    CREATE_SERVICE() {
        local name=$1
        local cmd=$2
        cat > "/etc/systemd/system/${name}.service" <<EOF
[Unit]
Description=EduMi2 - ${name}
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
ExecStart=${cmd}
Restart=always
RestartSec=5
LimitNOFILE=65535
LimitNPROC=65535
EnvironmentFile=${APP_DIR}/.env
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
    }

    CREATE_SERVICE "edumi-livekit" "${LIVEKIT_DIR}/livekit-server --config ${APP_DIR}/config/livekit.yaml"
    CREATE_SERVICE "edumi-camera"  "${VENV_PYTHON} camera_service/serve.py"
    CREATE_SERVICE "edumi-celery"  "${VENV_CELERY} -A school_project worker -l info -P threads"
    CREATE_SERVICE "edumi-auth"    "${VENV_DAPHNE} -v 1 -b 127.0.0.1 -p 8002 school_project.asgi:application"
    CREATE_SERVICE "edumi-admin"   "${VENV_DAPHNE} -v 1 -b 127.0.0.1 -p 8003 school_project.asgi:application"
    CREATE_SERVICE "edumi-meeting" "${VENV_DAPHNE} -v 1 -b 127.0.0.1 -p 8004 school_project.asgi:application"
    CREATE_SERVICE "edumi-msg"     "${VENV_DAPHNE} -v 1 -b 127.0.0.1 -p 8005 school_project.asgi:application"
    CREATE_SERVICE "edumi-profile" "${VENV_DAPHNE} -v 1 -b 127.0.0.1 -p 8006 school_project.asgi:application"
    CREATE_SERVICE "edumi-video"   "${VENV_DAPHNE} -v 1 -b 127.0.0.1 -p 8007 school_project.asgi:application"

    systemctl daemon-reload

    info "Starting LiveKit first and waiting for port 7880..."
    systemctl enable edumi-livekit 2>/dev/null || true
    systemctl restart edumi-livekit
    sleep 2
    LK_READY=0
    for i in $(seq 1 20); do
        if (echo > /dev/tcp/127.0.0.1/7880) >/dev/null 2>&1; then
            LK_READY=1; break
        fi
        sleep 1
    done
    if [ "$LK_READY" = "1" ]; then
        log "LiveKit is accepting connections on :7880"
    else
        warn "LiveKit port 7880 not open after 20s — inspect: journalctl -u edumi-livekit -n 50"
    fi

    info "Starting remaining microservices..."
    for svc in edumi-camera edumi-celery edumi-auth edumi-admin edumi-meeting edumi-msg edumi-profile edumi-video; do
        systemctl enable ${svc} 2>/dev/null || true
        systemctl restart ${svc}
    done

    sleep 3
    info "Verifying backend ports are open..."
    for p in 8002 8003 8004 8005 8006 8007 8008; do
        if (echo > /dev/tcp/127.0.0.1/$p) >/dev/null 2>&1; then
            info "  Port $p — OK"
        else
            warn "  Port $p — NOT listening (journalctl -u edumi-* for that service)"
        fi
    done
    log "Systemd services started and enabled."
fi

# ------------------------------------------------------------------------------
step "STEP 10: Nginx Reverse Proxy Setup"
# ------------------------------------------------------------------------------
if [ "$IS_ROOT" = true ]; then
    info "Configuring Nginx web server..."
    if systemctl is-active --quiet apache2 2>/dev/null; then
        info "Apache2 detected running on port 80 — stopping and disabling Apache2..."
        systemctl stop apache2 2>/dev/null || true
        systemctl disable apache2 2>/dev/null || true
    fi
    sed -i 's/worker_connections [0-9]*/worker_connections 4096/' /etc/nginx/nginx.conf 2>/dev/null || true

    NGINX_SERVER_NAMES="${DOMAIN} www.${DOMAIN} ${LAN_IP}"
    if [ -n "$PUBLIC_IP" ]; then
        NGINX_SERVER_NAMES="${NGINX_SERVER_NAMES} ${PUBLIC_IP}"
    fi

    cat > /etc/nginx/sites-available/edumi <<EOF
upstream edumi_backend {
    server 127.0.0.1:8002 max_fails=3 fail_timeout=10s;
    server 127.0.0.1:8003 max_fails=3 fail_timeout=10s;
    server 127.0.0.1:8004 max_fails=3 fail_timeout=10s;
    server 127.0.0.1:8005 max_fails=3 fail_timeout=10s;
    server 127.0.0.1:8006 max_fails=3 fail_timeout=10s;
    server 127.0.0.1:8007 max_fails=3 fail_timeout=10s;
}

server {
    listen 80;
    server_name ${NGINX_SERVER_NAMES} _;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ${NGINX_SERVER_NAMES} _;

    ssl_certificate ${APP_DIR}/certs/edumi.crt;
    ssl_certificate_key ${APP_DIR}/certs/edumi.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    server_tokens off;
    client_max_body_size 500M;

    # Security Headers
    add_header Permissions-Policy "camera=(self), microphone=(self), display-capture=(self)" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Block all hidden files (.env, .git, .htaccess)
    location ~ /\. {
        deny all;
        return 404;
    }

    # Block source code, logs, database files, and scripts from web access
    location ~* \.(env|py|pyc|sh|sql|sqlite3|log|yaml|yml|bak|swp)$ {
        deny all;
        return 404;
    }

    # 1) LiveKit SFU WebSocket + HTTP proxy
    location ^~ /livekit-proxy/ {
        proxy_pass http://127.0.0.1:7880/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_buffering off;
        proxy_cache_bypass \$http_upgrade;
    }

    # 2) Django Channels WebSockets (meetings, face tracking, attendance)
    location ^~ /ws/ {
        proxy_pass http://edumi_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_buffering off;
        proxy_cache_bypass \$http_upgrade;
    }

    # 3) Camera MJPEG streams
    location ~ ^/(cameras/[0-9]+/(feed|zoom|test)|mobile-cameras/[0-9]+/(feed|test)|head-count)/ {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }

    # 4) Static Assets (with MIME types & Django fallback)
    location /static/ {
        alias ${APP_DIR}/staticfiles/;
        expires 30d;
        access_log off;
        include /etc/nginx/mime.types;
        types {
            text/css css;
            application/javascript js;
            application/wasm wasm;
            application/octet-stream bin onnx;
            application/json json;
            image/svg+xml svg;
            image/png png;
            image/jpeg jpg jpeg;
            font/woff2 woff2;
            font/woff woff;
            font/ttf ttf;
        }
        # Fallback to Django safe_static_serve if asset is missing or permissions denied
        error_page 403 404 = @django_static_fallback;
    }

    location @django_static_fallback {
        proxy_pass http://edumi_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Protected internal media location for X-Accel-Redirect from Django
    location /internal_media/ {
        internal;
        alias ${APP_DIR}/database/media/;
        add_header Accept-Ranges bytes;
        sendfile on;
        sendfile_max_chunk 1m;
        tcp_nopush on;
    }

    location / {
        proxy_pass http://edumi_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_buffering off;
    }
}
EOF

    ln -sf /etc/nginx/sites-available/edumi /etc/nginx/sites-enabled/edumi
    rm -f /etc/nginx/sites-enabled/default
    nginx -t
    systemctl restart nginx
    log "Nginx web server configured and running."
fi

# ------------------------------------------------------------------------------
step "STEP 11: Deployment Complete & Status Summary"
# ------------------------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}================================================= ${NC}"
echo -e "${GREEN}${BOLD}   EduMi2 Deployment Completed Successfully!     ${NC}"
echo -e "${GREEN}${BOLD}================================================= ${NC}"
echo ""
echo -e "  ${BOLD}Access Endpoints (Local DNS & HTTPS Enforced):${NC}"
echo -e "  • Primary HTTPS Domain     : ${CYAN}https://${DOMAIN}${NC} (or ${CYAN}https://www.${DOMAIN}${NC})"
echo -e "  • Fallback LAN IP (HTTPS)  : ${CYAN}https://${LAN_IP}${NC}"
if [ -n "$PUBLIC_IP" ]; then
    echo -e "  • Fallback Public IP (HTTPS): ${CYAN}https://${PUBLIC_IP}${NC}"
fi
echo -e "  • LiveKit SFU Signal       : ${CYAN}wss://${DOMAIN}/livekit-proxy${NC}"
echo -e "  • Camera MJPEG Stream      : ${CYAN}https://${DOMAIN}/cameras/${NC}"
echo ""
echo -e "  ${BOLD}Management Commands:${NC}"
echo -e "  • View Service Logs        : ${CYAN}journalctl -u edumi-auth -f${NC}"
echo -e "  • Check Service Status     : ${CYAN}systemctl status edumi-auth edumi-camera edumi-celery${NC}"
echo -e "  • Create Superuser         : ${CYAN}${VENV_PYTHON} manage.py createsuperuser${NC}"
echo ""
