FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_COMPILE=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY camera_service/requirements.txt .
RUN pip install --upgrade pip --quiet && \
    pip install --quiet -r requirements.txt && \
    pip install --quiet psycopg2-binary dj-database-url

COPY . .

RUN mkdir -p /app/media/temp && chmod -R 755 /app/media

EXPOSE 10000
WORKDIR /app/camera_service
