# ==============================================================================
# EduMi — Production Container Dockerfile
# Multi-stage image building the unified academic operating system
# ==============================================================================

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Build arguments for configuration
ARG SECRET_KEY=build_time_dummy_secret_key_1234567890
ARG DJANGO_SETTINGS_MODULE=edumi_core.settings
ARG LIVEKIT_API_KEY=dummy_livekit_key
ARG LIVEKIT_API_SECRET=dummy_livekit_secret_32chars_long
ARG FACE_ENCRYPTION_KEY=dummy_face_encryption_key_base64=

# Environment variables
ENV SECRET_KEY=${SECRET_KEY} \
    DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE} \
    LIVEKIT_API_KEY=${LIVEKIT_API_KEY} \
    LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET} \
    FACE_ENCRYPTION_KEY=${FACE_ENCRYPTION_KEY}

# Install essential system libraries (PostgreSQL client, FFmpeg, OpenCV headless libs, FreeType/JPEG for ReportLab)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    python3-dev \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libfreetype6 \
    libjpeg62-turbo \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifest and install Python wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy complete project source
COPY . .

# Collect static files at container build time
RUN python manage.py collectstatic --noinput

# Expose primary application and microservice ports
EXPOSE 8000 8002 8008 7880

# Default entrypoint command (can be overridden in docker-compose.yml)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8002", "edumi_core.asgi:application"]
