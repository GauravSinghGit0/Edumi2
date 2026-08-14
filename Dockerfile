# Dockerfile – builds the EduMi2 Django application
FROM python:3.11-slim AS base

# Build arguments for secret and settings
ARG SECRET_KEY
ARG DJANGO_SETTINGS_MODULE=school_project.settings
ARG LIVEKIT_API_KEY
ARG LIVEKIT_API_SECRET
ARG FACE_ENCRYPTION_KEY
ARG LIVEKIT_URL
ARG LIVEKIT_INTERNAL_URL
ARG LIVEKIT_INTERNAL_HTTP_URL

# Default fall‑backs for build time (do NOT contain real secrets)
ENV SECRET_KEY=${SECRET_KEY:-dummy_secret}
ENV DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE}
ENV LIVEKIT_API_KEY=${LIVEKIT_API_KEY:-dummy_livekit_key}
ENV LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET:-dummy_livekit_secret}
ENV FACE_ENCRYPTION_KEY=${FACE_ENCRYPTION_KEY:-dummy_face_key}
ENV LIVEKIT_URL=${LIVEKIT_URL:-ws://localhost:7880}
ENV LIVEKIT_INTERNAL_URL=${LIVEKIT_INTERNAL_URL:-ws://localhost:7880}
ENV LIVEKIT_INTERNAL_HTTP_URL=${LIVEKIT_INTERNAL_HTTP_URL:-http://localhost:7880}

# OS‑level dependencies (psycopg2, cryptography, ffmpeg, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libffi-dev python3-dev \
    ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Expose service ports (will be overridden per container in docker‑compose)
EXPOSE 8002 8003 8004 8005 8006 8007 7880 7881

# Install Python dependencies first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Collect static files at build time (WhiteNoise will serve them)
RUN python manage.py collectstatic --noinput
# Default command – overridden per service in docker‑compose.yml
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
