# 🐳 Server Production Deployment Guide — EduMi 2

This guide covers production-grade deployments of **EduMi 2** on cloud servers (Ubuntu 20.04/22.04/24.04 LTS) using a custom domain and SSL/TLS.

---

## 🛠️ Option A: Automated Systemd Setup (Recommended)

EduMi 2 provides a master deployment orchestration script (`deploy.sh`) that installs dependencies, sets up local databases, generates credentials, registers systemd services, and configures Nginx.

### Step 1: Clone and Execute Deployment Orchestrator
```bash
# SSH into your clean VPS
ssh root@your-server-ip

# Run the deploy orchestrator
git clone -b new_edumi https://github.com/GAuravgiy87/Edumi2.git
cd Edumi2
sudo bash deploy.sh --domain yourdomain.com
```

### What this configures:
- **System Packages**: Installs Python, Redis, Nginx, FFMpeg, and PostgreSQL.
- **SSL**: Obtains a Let's Encrypt SSL certificate or falls back to a custom configuration.
- **Systemd**: Sets up daemon processes for `edumi-auth`, `edumi-meeting`, `edumi-camera`, `edumi-celery`, and `edumi-livekit`.
- **Nginx Reverse Proxy**: Forwards HTTPS traffic (port 443) and handles WebSocket connections correctly.

### Monitoring Services:
Check status of all daemons:
```bash
systemctl status edumi-*
```
Stream logs:
```bash
journalctl -u edumi-auth -f
```

---

## 🐳 Option B: Containerized Docker Deployment

This setup runs all microservices inside Docker containers using `docker-compose`. Nginx routes HTTPS, Daphne runs Django, and Redis/PostgreSQL provide caching and data persistence.

### Step 1: Copy Environment Template
```bash
cp config/.env.example .env
nano .env
```
Ensure you set:
- `DEBUG=False`
- A secure `SECRET_KEY` and `FACE_ENCRYPTION_KEY`
- Your domain name in `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
- LiveKit internal connection hosts mapping to `livekit` container

### Step 2: Build and Run Containers
```bash
# Build images and start services in background
docker-compose up --build -d
```

### Step 3: Run Setup Commands
```bash
# Run database migrations
docker-compose exec web python manage.py migrate

# Create your primary administrator account
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput
```

### Useful Commands:
```bash
# Check running containers
docker-compose ps

# Stream logs from all services
docker-compose logs -f

# Shut down the stack
docker-compose down
```

---

## 🔒 Production Security Checklist
1. **Firewall (UFW)**: Allow ports `80`, `443` (Nginx), `7880`, `7881` (LiveKit WebRTC signaling/media), and UFW blocking for all database ports (`5432`, `6379`) to isolate them to local interfaces.
2. **DEBUG Flags**: Keep `DEBUG=False` in `.env` to prevent sensitive traceback details from showing to users.
3. **Database Backups**: Schedule regular database dumps for PostgreSQL to ensure system recovery capabilities.
