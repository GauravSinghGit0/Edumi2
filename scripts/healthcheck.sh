#!/bin/bash
# ==============================================================================
#  EduMi 2 — Health Watchdog & Auto-Recovery Script
#  Runs as a systemd service (edumi-watchdog) — checks every 30 seconds
#  Auto-restarts any crashed EduMi service and sends alerts
# ==============================================================================

APP_DIR="/opt/edumi"
LOG_FILE="/var/log/edumi-watchdog.log"
ALERT_EMAIL=""  # Set to get email alerts: admin@yourdomain.com
MAX_FAILURES=3

declare -A FAIL_COUNT

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

alert() {
    log "🚨 ALERT: $1"
    if [[ -n "$ALERT_EMAIL" ]] && command -v mail &>/dev/null; then
        echo "$1" | mail -s "EduMi Alert: $1" "$ALERT_EMAIL"
    fi
}

check_and_heal_service() {
    local SERVICE="$1"
    local STATUS
    STATUS=$(systemctl is-active "$SERVICE" 2>/dev/null || echo "inactive")

    if [[ "$STATUS" != "active" ]]; then
        FAIL_COUNT[$SERVICE]=$((${FAIL_COUNT[$SERVICE]:-0} + 1))
        log "⚠ Service DOWN: $SERVICE (failure #${FAIL_COUNT[$SERVICE]})"

        if [[ ${FAIL_COUNT[$SERVICE]} -le $MAX_FAILURES ]]; then
            log "→ Attempting restart of $SERVICE..."
            systemctl restart "$SERVICE" 2>/dev/null && {
                sleep 3
                if [[ "$(systemctl is-active $SERVICE)" == "active" ]]; then
                    log "✓ $SERVICE restarted successfully"
                    FAIL_COUNT[$SERVICE]=0
                else
                    alert "$SERVICE failed to restart (attempt ${FAIL_COUNT[$SERVICE]})"
                fi
            }
        else
            alert "$SERVICE has failed $MAX_FAILURES times — manual intervention required"
        fi
    else
        # Reset failure count on successful check
        FAIL_COUNT[$SERVICE]=0
    fi
}

check_http() {
    local URL="$1"
    local NAME="$2"
    local HTTP_CODE
    HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 5 "$URL" 2>/dev/null || echo "000")

    if [[ "$HTTP_CODE" == "000" || "$HTTP_CODE" == "502" || "$HTTP_CODE" == "503" ]]; then
        log "⚠ HTTP check FAILED for $NAME (code: $HTTP_CODE)"
        return 1
    fi
    return 0
}

check_redis() {
    if ! redis-cli ping &>/dev/null; then
        log "⚠ Redis is down — attempting restart..."
        systemctl restart redis-server
        sleep 2
        if redis-cli ping &>/dev/null; then
            log "✓ Redis restarted"
            # Restart Celery & Web too (they depend on Redis)
            systemctl restart edumi-celery edumi-web
        else
            alert "Redis is down and could not be restarted!"
        fi
    fi
}

check_disk() {
    local USAGE
    USAGE=$(df "$APP_DIR" | awk 'NR==2 {print $5}' | tr -d '%')
    if [[ "$USAGE" -gt 90 ]]; then
        alert "Disk usage is at ${USAGE}% — clean up recordings or expand disk!"
    fi
}

check_memory() {
    local MEM_AVAILABLE
    MEM_AVAILABLE=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
    if [[ "$MEM_AVAILABLE" -lt 200 ]]; then
        log "⚠ Low memory: ${MEM_AVAILABLE}MB available — restarting heavy services..."
        systemctl restart edumi-web edumi-celery
    fi
}

cleanup_stale_recordings() {
    # Clean up any incomplete recordings older than 2 hours
    find "$APP_DIR/database/media/recordings" -name "*.ts.tmp" -mmin +120 -delete 2>/dev/null || true
}

# ─── Main watchdog loop ────────────────────────────────────────────────────────
log "====== EduMi Watchdog Started ======"

SERVICES=("edumi-web" "edumi-celery" "edumi-camera" "edumi-livekit" "redis-server")
COUNTER=0

while true; do
    # ── Check all services ────────────────────────────────────────────────────
    for svc in "${SERVICES[@]}"; do
        check_and_heal_service "$svc"
    done

    # ── HTTP health check (every 5 cycles = ~2.5 min) ─────────────────────────
    if (( COUNTER % 5 == 0 )); then
        check_http "https://localhost:8002/admin/login/" "Django App" || \
            systemctl restart edumi-web
        check_redis
    fi

    # ── System checks (every 20 cycles = ~10 min) ─────────────────────────────
    if (( COUNTER % 20 == 0 )); then
        check_disk
        check_memory
        cleanup_stale_recordings
    fi

    COUNTER=$((COUNTER + 1))
    sleep 30
done
