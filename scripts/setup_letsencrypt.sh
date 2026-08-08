#!/usr/bin/env bash
# ==============================================================================
#  EduMi2 — Automated Let's Encrypt SSL Provisioner for Ubuntu/Debian Server
# ==============================================================================
#  USAGE:
#    sudo bash scripts/setup_letsencrypt.sh --domain eclass.dei.ac.in --email admin@dei.ac.in
# ==============================================================================

set -eo pipefail

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

DOMAIN="eclass.dei.ac.in"
EMAIL=""
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain) DOMAIN="$2"; shift 2 ;;
        --email)  EMAIL="$2";  shift 2 ;;
        *) warn "Unknown argument: $1"; shift ;;
    esac
done

echo ""
echo -e "${BOLD}${CYAN}=================================================${NC}"
echo -e "${BOLD}${CYAN}  EduMi2 Let's Encrypt SSL Automated Provisioner ${NC}"
echo -e "${BOLD}${CYAN}=================================================${NC}"
echo -e "  Target Domain : ${CYAN}${DOMAIN}${NC}"
echo -e "  App Directory : ${CYAN}${APP_DIR}${NC}"
if [ -n "$EMAIL" ]; then
    echo -e "  Notice Email  : ${CYAN}${EMAIL}${NC}"
fi
echo ""

if [ "$(id -u)" -ne 0 ]; then
    err "This script must be run as root. Re-run with: sudo bash scripts/setup_letsencrypt.sh"
fi

# 1. Install Certbot & Nginx plugin
info "Installing Certbot package..."
apt-get update -qq
apt-get install -y -qq certbot python3-certbot-nginx cron 2>/dev/null || true
log "Certbot and Nginx plugin ready."

# 2. Check UFW Firewall
if command -v ufw &>/dev/null; then
    ufw allow 80/tcp 2>/dev/null || true
    ufw allow 443/tcp 2>/dev/null || true
    log "Ports 80 & 443 open in UFW firewall."
fi

# 3. Obtain Certificate via Certbot
info "Obtaining trusted Let's Encrypt SSL certificate for ${DOMAIN}..."

CERTBOT_ARGS=(--nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos)
if [ -n "$EMAIL" ]; then
    CERTBOT_ARGS+=(--email "$EMAIL")
else
    CERTBOT_ARGS+=(--register-unsafely-without-email)
fi

if certbot "${CERTBOT_ARGS[@]}"; then
    log "Let's Encrypt SSL certificate successfully issued for ${DOMAIN}!"
else
    warn "Certbot auto-configuration encountered an issue. Retrying in webroot/standalone mode..."
    systemctl stop nginx 2>/dev/null || true
    certbot certonly --standalone -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos ${EMAIL:+-m "$EMAIL"} || true
    systemctl start nginx 2>/dev/null || true
fi

# 4. Link SSL certificates into EduMi certs directory
mkdir -p "$APP_DIR/certs"
LE_DIR="/etc/letsencrypt/live/$DOMAIN"

if [ -f "$LE_DIR/fullchain.pem" ] && [ -f "$LE_DIR/privkey.pem" ]; then
    cp -L "$LE_DIR/fullchain.pem" "$APP_DIR/certs/edumi.crt"
    cp -L "$LE_DIR/privkey.pem" "$APP_DIR/certs/edumi.key"
    chmod 644 "$APP_DIR/certs/edumi.crt"
    chmod 600 "$APP_DIR/certs/edumi.key"
    log "Linked Let's Encrypt certificate & private key to $APP_DIR/certs/"
else
    err "Failed to locate Let's Encrypt certificate in $LE_DIR"
fi

# 5. Enable Auto-Renewal Cron Job / Systemd Timer
info "Configuring automatic SSL certificate renewal..."
systemctl enable certbot.timer 2>/dev/null || true
systemctl start certbot.timer 2>/dev/null || true

RENEW_HOOK="cp -L $LE_DIR/fullchain.pem $APP_DIR/certs/edumi.crt && cp -L $LE_DIR/privkey.pem $APP_DIR/certs/edumi.key && systemctl reload nginx"
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/edumi-renewal.sh <<EOF
#!/usr/bin/env bash
$RENEW_HOOK
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/edumi-renewal.sh
log "SSL renewal deploy hook registered in /etc/letsencrypt/renewal-hooks/deploy/"

# 6. Update .env for production SSL security flags
ENV_FILE="$APP_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    info "Updating production .env security headers..."
    sed -i 's/SECURE_SSL_REDIRECT=False/SECURE_SSL_REDIRECT=True/g' "$ENV_FILE" 2>/dev/null || true
    sed -i 's/SESSION_COOKIE_SECURE=False/SESSION_COOKIE_SECURE=True/g' "$ENV_FILE" 2>/dev/null || true
    sed -i 's/CSRF_COOKIE_SECURE=False/CSRF_COOKIE_SECURE=True/g' "$ENV_FILE" 2>/dev/null || true
    log "Updated .env: SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True"
fi

# 7. Reload Nginx and systemd services
if command -v systemctl &>/dev/null; then
    nginx -t 2>/dev/null && systemctl reload nginx || true
    systemctl restart edumi-auth edumi-admin edumi-meeting edumi-msg edumi-profile edumi-video 2>/dev/null || true
fi

echo ""
echo -e "${GREEN}${BOLD}=================================================${NC}"
echo -e "${GREEN}${BOLD}   Let's Encrypt SSL Setup Completed!            ${NC}"
echo -e "${GREEN}${BOLD}=================================================${NC}"
echo -e "  Website URL   : ${CYAN}https://${DOMAIN}${NC}"
echo -e "  Incognito Fix : ${GREEN}Active (Trusted CA Root)${NC}"
echo -e "  Auto-Renew    : ${GREEN}Enabled (certbot.timer)${NC}"
echo ""
