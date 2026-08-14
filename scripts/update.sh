#!/bin/bash
# ==============================================================================
#  EduMi 2 — Zero-Downtime Update Script
#  Run after pushing new code to auto-deploy latest changes
#
#  USAGE (on the server):
#    sudo bash /opt/edumi/scripts/update.sh
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${CYAN}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_USER="$(stat -c '%U' "$APP_DIR" 2>/dev/null || echo "$USER")"
BRANCH="${1:-$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")}"

[[ "$EUID" -ne 0 ]] && err "Run as root: sudo bash scripts/update.sh"

echo -e "\n${BOLD}${CYAN}EduMi 2 — Updating to latest code (directory: $APP_DIR, branch: $BRANCH)${NC}\n"

# 1. Pull latest code
info "Pulling latest code..."
cd "$APP_DIR"
if [ "$APP_USER" != "root" ]; then
    sudo -u "$APP_USER" git fetch origin || git fetch origin
    sudo -u "$APP_USER" git pull origin "$BRANCH" || git pull origin "$BRANCH"
else
    git fetch origin
    git pull origin "$BRANCH"
fi
log "Code updated"

# 2. Install any new dependencies
info "Updating Python dependencies..."
VENV_PYTHON="$APP_DIR/venv/bin/python"
VENV_PIP="$APP_DIR/venv/bin/pip"

if [ -f "$VENV_PIP" ]; then
    $VENV_PIP install -r requirements.txt -q || true
    log "Dependencies updated"
fi

# 3. Apply DB migrations
info "Running database migrations..."
if [ -f "$VENV_PYTHON" ]; then
    $VENV_PYTHON manage.py migrate --noinput
    log "Migrations applied"
fi

# 4. Collect static files
info "Collecting static files..."
if [ -f "$VENV_PYTHON" ]; then
    $VENV_PYTHON manage.py compress --force 2>/dev/null || true
    $VENV_PYTHON manage.py collectstatic --noinput -v 0
    log "Static files collected"
fi

# 5. Restart services gracefully
info "Restarting EduMi services..."
SERVICES=$(systemctl list-unit-files 'edumi-*' --no-legend 2>/dev/null | awk '{print $1}' || echo "")
if [ -n "$SERVICES" ]; then
    systemctl restart $SERVICES
    sleep 3

    for svc in $SERVICES; do
        STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "inactive")
        if [[ "$STATUS" == "active" ]]; then
            log "$svc is running"
        else
            warn "$svc failed to start — check: journalctl -u $svc -n 30"
        fi
    done
else
    # Fallback to standard service names created by deploy.sh
    for svc in edumi-auth edumi-admin edumi-meeting edumi-msg edumi-profile edumi-video edumi-camera edumi-celery edumi-livekit; do
        systemctl restart "$svc" 2>/dev/null || true
    done
fi

echo -e "\n${BOLD}${GREEN}✅ Update complete!${NC}"
echo -e "  Watch logs : ${CYAN}journalctl -u edumi-auth -f${NC}\n"

