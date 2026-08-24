#!/usr/bin/env bash
# ==============================================================================
#  EduMi2 — Single-File Master Deployment Orchestrator for Ubuntu Server
#  Tested on: Ubuntu 20.04 / 22.04 / 24.04 LTS, Debian 11 / 12 (Without Docker)
# ==============================================================================
#  USAGE:
#    sudo bash deploy.sh
#
#  OPTIONAL OPTIONS:
#    --domain    Your domain name (e.g. --domain edumi.ac.in)
#    --email     Notification email for SSL (e.g. --email admin@edumi.ac.in)
#    --db-host   Remote database host IP (Default: 127.0.0.1)
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
DB_PASS="edumi_pass_2026"

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)       DOMAIN="$2";  shift 2 ;;
        --email)        EMAIL="$2";   shift 2 ;;
        --db-host)      DB_HOST="$2"; shift 2 ;;
        --letsencrypt)  USE_LETSENCRYPT=true; shift ;;
        *) warn "Unknown argument: $1"; shift ;;
    esac
done

# Detect Ubuntu Server LAN IP Address
LAN_IP=$(ip route get 8.8.8.8 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1); exit}')
if [ -z "$LAN_IP" ]; then
    LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
if [ -z "$LAN_IP" ]; then
    LAN_IP="127.0.0.1"
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
echo -e "  Directory : ${CYAN}${APP_DIR}${NC}"
echo -e "  Domain    : ${CYAN}${DOMAIN}${NC} (HTTPS Only)"
echo -e "  Server IP : ${CYAN}${LAN_IP}${NC}"
echo -e "  DB Host   : ${CYAN}${DB_HOST}${NC}"
echo ""

# ------------------------------------------------------------------------------
step "STEP 1: Root Check & Ubuntu Pre-Flight Inspector & Local DNS"
# ------------------------------------------------------------------------------
IS_ROOT=false
if [ "$(id -u)" -eq 0 ]; then IS_ROOT=true; fi

if [ "$IS_ROOT" = false ]; then
    warn "Running without root privileges. If package installation fails, re-run with: sudo bash deploy.sh"
fi

# Set up Local DNS entries in /etc/hosts for edumi.ac.in
if [ "$IS_ROOT" = true ]; then
    if ! grep -q "$DOMAIN" /etc/hosts; then
        info "Configuring Local DNS in /etc/hosts for $DOMAIN..."
        echo -e "\n# EduMi2 Local DNS Resolution\n127.0.0.1\t$DOMAIN www.$DOMAIN\n$LAN_IP\t$DOMAIN www.$DOMAIN" >> /etc/hosts
        log "Added $DOMAIN and www.$DOMAIN to /etc/hosts"
    fi
fi

# Apply UFW Firewall rules for LAN IP & HTTPS access
if command -v ufw &>/dev/null && [ "$IS_ROOT" = true ]; then
    ufw allow 80/tcp 2>/dev/null || true
    ufw allow 443/tcp 2>/dev/null || true
    ufw allow 8008/tcp 2>/dev/null || true
    ufw allow 7880/tcp 2>/dev/null || true
    ufw allow 7881/tcp 2>/dev/null || true
    ufw allow 50000:50200/udp 2>/dev/null || true
    info "UFW firewall rules applied (Ports 80, 443, 8008, 7880, 7881 allowed)."
fi

info "Checking system requirements..."
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)
TOTAL_RAM_GB=$(awk "BEGIN {print $TOTAL_RAM_KB / 1024 / 1024}")
info "RAM Capacity: ${TOTAL_RAM_GB:0:4} GB"

if [ "$IS_ROOT" = true ]; then
    info "Installing/updating required Ubuntu system packages..."
    apt-get update -qq
    apt-get install -y -qq software-properties-common curl wget git openssl net-tools 2>/dev/null || true

    apt-get install -y -qq \
        python3 python3-venv python3-dev python3-pip \
        build-essential cmake g++ libpq-dev libffi-dev \
        ffmpeg postgresql postgresql-contrib redis-server nginx supervisor \
        libopenblas-dev liblapack-dev libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev 2>/dev/null || true
    log "Ubuntu system packages installed."

    if command -v ufw &>/dev/null; then
        info "Configuring UFW firewall rules for HTTP, HTTPS, and LiveKit WebRTC..."
        ufw allow 80/tcp >/dev/null 2>&1 || true
        ufw allow 443/tcp >/dev/null 2>&1 || true
        ufw allow 7880/tcp >/dev/null 2>&1 || true
        ufw allow 7881/tcp >/dev/null 2>&1 || true
        ufw allow 50000:50200/udp >/dev/null 2>&1 || true
        log "Firewall ports allowed (80, 443, 7880, 7881, 50000-50200/udp)."
    fi
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
        sudo -u postgres psql -c "ALTER USER $DB_USER CREATEDB SUPERUSER;" 2>/dev/null || true
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
    # Remove Windows .exe if accidentally present (wrong platform binary)
    if [ -f "$LIVEKIT_DIR/livekit-server.exe" ]; then
        warn "Found Windows binary (livekit-server.exe) — removing it and downloading the correct Linux binary..."
        rm -f "$LIVEKIT_DIR/livekit-server.exe"
    fi

    info "Downloading LiveKit Server Linux (amd64) binary from GitHub releases..."
    LIVEKIT_DL_URL=$(curl -s https://api.github.com/repos/livekit/livekit/releases/latest \
        | grep "browser_download_url" | grep "linux_amd64.tar.gz" | head -1 \
        | cut -d '"' -f 4 || echo "")

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

info "Configuring config/livekit.yaml for server IP ($LAN_IP)..."
mkdir -p "$APP_DIR/config"

# Read existing LiveKit credentials from .env if present, otherwise default to devkey/devsecret
LK_KEY=$(grep '^LIVEKIT_API_KEY=' "$APP_DIR/.env" 2>/dev/null | cut -d '=' -f 2- | tr -d '"' | tr -d "'" || echo "")
LK_SECRET=$(grep '^LIVEKIT_API_SECRET=' "$APP_DIR/.env" 2>/dev/null | cut -d '=' -f 2- | tr -d '"' | tr -d "'" || echo "")

if [ -z "$LK_KEY" ]; then
    LK_KEY="devkey"
    if [ -f "$APP_DIR/.env" ]; then
        echo "LIVEKIT_API_KEY=$LK_KEY" >> "$APP_DIR/.env"
    fi
fi

if [ -z "$LK_SECRET" ]; then
    LK_SECRET="devsecret_must_be_32_characters_long_1234"
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
  use_external_ip: true
  node_ip: "$LAN_IP"
  stun_servers:
    - stun.l.google.com:19302
    - stun1.l.google.com:19302

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
step "STEP 5: Python Virtual Environment & Dependencies"
# ------------------------------------------------------------------------------
VENV_DIR="venv"
if [ -d ".venv" ]; then
    VENV_DIR=".venv"
elif [ -d "venv" ]; then
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
$VENV_PIP install -r requirements.txt -q
log "Python environment ready inside ./$VENV_DIR"


# ------------------------------------------------------------------------------
step "STEP 6: Environment File (.env) Setup (HTTPS Only)"
# ------------------------------------------------------------------------------
ENV_FILE="$APP_DIR/.env"
info "Writing production .env file configured for HTTPS & local DNS ($DOMAIN)..."

# Preserve existing secrets if they exist
EXISTING_SECRET=$(grep '^SECRET_KEY=' "$ENV_FILE" 2>/dev/null | cut -d '=' -f 2- | tr -d '"' | tr -d "'" || echo "")
EXISTING_FACE=$(grep '^FACE_ENCRYPTION_KEY=' "$ENV_FILE" 2>/dev/null | cut -d '=' -f 2- | tr -d '"' | tr -d "'" || echo "")

# Preserve existing SMTP configurations
EXISTING_EMAIL_BACKEND=$(grep '^EMAIL_BACKEND=' "$ENV_FILE" 2>/dev/null | cut -d '=' -f 2- || echo "django.core.mail.backends.smtp.EmailBackend")
EXISTING_EMAIL_HOST=$(grep '^EMAIL_HOST=' "$ENV_FILE" 2>/dev/null | cut -d '=' -f 2- || echo "")
EXISTING_EMAIL_PORT=$(grep '^EMAIL_PORT=' "$ENV_FILE" 2>/dev/null | cut -d '=' -f 2- || echo "")
EXISTING_EMAIL_USE_TLS=$(grep '^EMAIL_USE_TLS=' "$ENV_FILE" 2>/dev/null | cut -d '=' -f 2- || echo "True")
EXISTING_EMAIL_USE_SSL=$(grep '^EMAIL_USE_SSL=' "$ENV_FILE" 2>/dev/null | cut -d '=' -f 2- || echo "False")
EXISTING_EMAIL_HOST_USER=$(grep '^EMAIL_HOST_USER=' "$ENV_FILE" 2>/dev/null | cut -d '=' -f 2- || echo "")
EXISTING_EMAIL_HOST_PASSWORD=$(grep '^EMAIL_HOST_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d '=' -f 2- || echo "")
EXISTING_DEFAULT_FROM_EMAIL=$(grep '^DEFAULT_FROM_EMAIL=' "$ENV_FILE" 2>/dev/null | cut -d '=' -f 2- || echo "")

if [ -n "$EXISTING_SECRET" ]; then
    SECRET_KEY=$EXISTING_SECRET
else
    SECRET_KEY=$(openssl rand -base64 32 | tr -d '/+=' | head -c 50 2>/dev/null || $VENV_PYTHON -c "import secrets; print(secrets.token_urlsafe(40))" 2>/dev/null || echo "secret_edumi_$(date +%s)_key")
fi

if [ -n "$EXISTING_FACE" ]; then
    FACE_KEY=$EXISTING_FACE
else
    FACE_KEY=$($VENV_PYTHON -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "ZxYxWvUtSrQpOnMlKjIhGfEdCbA9876543210")
fi

DATABASE_URL_STR="postgres://$DB_USER:$DB_PASS@$DB_HOST:5432/$DB_NAME"

cat > "$ENV_FILE" <<EOF
SECRET_KEY=$SECRET_KEY
DEBUG=False
ALLOWED_HOSTS=$DOMAIN,www.$DOMAIN,localhost,127.0.0.1,$LAN_IP
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

CSRF_TRUSTED_ORIGINS=https://$DOMAIN,https://www.$DOMAIN,https://localhost,https://127.0.0.1,https://$LAN_IP

CAMERA_SERVICE_PORT=8008
CAMERA_SERVICE_URL=http://127.0.0.1:8008

FFMPEG_BINARY=ffmpeg
FFPROBE_BINARY=ffprobe

# SMTP Email Configuration
EMAIL_BACKEND=$EXISTING_EMAIL_BACKEND
EMAIL_HOST=$EXISTING_EMAIL_HOST
EMAIL_PORT=$EXISTING_EMAIL_PORT
EMAIL_USE_TLS=$EXISTING_EMAIL_USE_TLS
EMAIL_USE_SSL=$EXISTING_EMAIL_USE_SSL
EMAIL_HOST_USER=$EXISTING_EMAIL_HOST_USER
EMAIL_HOST_PASSWORD=$EXISTING_EMAIL_HOST_PASSWORD
DEFAULT_FROM_EMAIL=$EXISTING_DEFAULT_FROM_EMAIL
EOF
log ".env updated for HTTPS & $DOMAIN."


# ------------------------------------------------------------------------------
step "STEP 7: Directories & SSL Certificate Setup"
# ------------------------------------------------------------------------------
mkdir -p staticfiles media certs logs config

if [ "$USE_LETSENCRYPT" = true ] && [ "$IS_ROOT" = true ]; then
    info "Provisioning official Let's Encrypt public SSL certificate for $DOMAIN..."
    bash "$APP_DIR/scripts/setup_letsencrypt.sh" --domain "$DOMAIN" ${EMAIL:+--email "$EMAIL"} || true
elif [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    info "Using official Let's Encrypt public SSL certificate for $DOMAIN..."
    cp -L "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" certs/edumi.crt
    cp -L "/etc/letsencrypt/live/$DOMAIN/privkey.pem" certs/edumi.key
else
    info "Generating SSL certificate for $DOMAIN, www.$DOMAIN, localhost, and $LAN_IP..."
    if [ -f "scripts/generate_ssl_cert.py" ]; then
        $VENV_PYTHON scripts/generate_ssl_cert.py 2>/dev/null || true
    fi

    if [ ! -f "certs/edumi.crt" ] || [ ! -f "certs/edumi.key" ]; then
        openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
            -keyout certs/edumi.key -out certs/edumi.crt \
            -subj "/C=IN/ST=Academic/L=EduMi/O=EduMi/CN=$DOMAIN" \
            -addext "subjectAltName=DNS:$DOMAIN,DNS:www.$DOMAIN,DNS:localhost,IP:127.0.0.1,IP:$LAN_IP" 2>/dev/null || true
    fi
fi
# Ensure home directory, certs, and logs have proper write/execute permissions
mkdir -p "$APP_DIR/logs" "$APP_DIR/staticfiles" "$APP_DIR/database/media" "$APP_DIR/certs" "$APP_DIR/config"
chmod -R 777 "$APP_DIR/logs" 2>/dev/null || true

if [ "$IS_ROOT" = true ]; then
    chmod 755 $(dirname "$APP_DIR") 2>/dev/null || true
    chmod -R 755 "$APP_DIR/certs" "$APP_DIR/staticfiles" "$APP_DIR/database/media" 2>/dev/null || true
fi
log "SSL Certificates generated in ./certs/"


# ------------------------------------------------------------------------------
step "STEP 8: Django Database Migrations & Static Collection"
# ------------------------------------------------------------------------------
info "Running database migrations & seeding default camera..."
$VENV_PYTHON manage.py migrate --noinput
$VENV_PYTHON -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_project.settings')
django.setup()
from cameras.models import Camera
camera, created = Camera.objects.get_or_create(
    id=1,
    defaults={
        'name': 'Default Classroom Camera (10.7.16.48)',
        'ip_address': '10.7.16.48',
        'port': 554,
        'username': 'test',
        'password': 'dei@12@12',
        'stream_path': '/h264Preview_01_main',
        'location': 'Classroom 1',
        'is_active': True
    }
)
if not created:
    camera.ip_address = '10.7.16.48'
    camera.username = 'test'
    camera.password = 'dei@12@12'
    camera.stream_path = '/h264Preview_01_main'
    camera.is_active = True
    camera.save()
" 2>/dev/null || true
log "Database schema initialized & Camera 1 configured."

info "Collecting static files & compressing template assets..."
$VENV_PYTHON manage.py collectstatic --noinput --clear
$VENV_PYTHON manage.py compress --force || true
$VENV_PYTHON manage.py collectstatic --noinput
chmod -R 755 "$APP_DIR" "$APP_DIR/staticfiles" 2>/dev/null || true
chmod 755 $(dirname "$APP_DIR") 2>/dev/null || true
log "Static assets compressed and collected into ./staticfiles/"


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

    # ---- Start order: LiveKit first (WebRTC depends on it), then Camera, ----
    #      Celery, then the Django upstream instances.
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
    # Ensure Nginx handles high worker connections
    sed -i 's/worker_connections [0-9]*/worker_connections 4096/' /etc/nginx/nginx.conf 2>/dev/null || true

    cat > /etc/nginx/sites-available/edumi <<EOF
upstream edumi_backend {
    server 127.0.0.1:8002;
    server 127.0.0.1:8003;
    server 127.0.0.1:8004;
    server 127.0.0.1:8005;
    server 127.0.0.1:8006;
    server 127.0.0.1:8007;
}

server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN} ${LAN_IP} _;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ${DOMAIN} www.${DOMAIN} ${LAN_IP} _;

    ssl_certificate ${APP_DIR}/certs/edumi.crt;
    ssl_certificate_key ${APP_DIR}/certs/edumi.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    client_max_body_size 500M;

    # ---------------------------------------------------------------------
    # IMPORTANT: Use ^~ so these PREFIX locations beat the camera regex
    # below.  Without ^~ the regex ~ ^/(cameras/...) would run first and
    # prevent /livekit-proxy/* and /ws/* from ever matching.
    # ---------------------------------------------------------------------

    # 1) LiveKit SFU WebSocket + HTTP proxy (bypass Django for speed)
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

    # 2) Django Channels WebSockets (meeting / attendance / chat)
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

    # 3) Camera MJPEG streams — regex is fine here now because it is
    #    matched after the ^~ prefixes above.
    location ~ ^/(cameras/[0-9]+/(feed|zoom|test)|mobile-cameras/[0-9]+/(feed|test)|head-count)/ {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }

    location /static/ {
        alias ${APP_DIR}/staticfiles/;
        expires 30d;
        access_log off;
        include /etc/nginx/mime.types;
    }

    location /media/ {
        alias ${APP_DIR}/database/media/;
        expires 7d;
        access_log off;
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
echo -e "  • LiveKit SFU Signal       : ${CYAN}wss://${DOMAIN}/livekit-proxy${NC}"
echo -e "  • Camera MJPEG Stream      : ${CYAN}https://${DOMAIN}/cameras/${NC}"
echo ""
echo -e "  ${BOLD}Management Commands:${NC}"
echo -e "  • View Service Logs       : ${CYAN}journalctl -u edumi-auth -f${NC}"
echo -e "  • Check Service Status    : ${CYAN}systemctl status edumi-auth edumi-camera edumi-celery${NC}"
echo -e "  • Create Superuser        : ${CYAN}${VENV_PYTHON} manage.py createsuperuser${NC}"
echo ""
