import logging
import os
import subprocess
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.temp import NamedTemporaryFile

from videos.models import Video, VideoQuality, VideoChunk

logger = logging.getLogger(__name__)


def process_video_sync(video_id):
    """Process video to create multiple qualities, chunks, and thumbnails."""
    try:
        video = Video.objects.get(id=video_id)

        # Get video metadata (duration)
        duration = get_video_duration(video.original_file.path)
        video.duration_seconds = int(duration)
        
        # Auto-extract thumbnail if not present
        if not video.thumbnail:
            extract_thumbnail(video)
            
        video.save()

        # Process for each quality
        qualities = Video.VIDEO_QUALITY_CHOICES
        for quality_key, _ in qualities:
            create_quality_version(video, quality_key)

        video.is_processed = True
        video.is_chunked = True
        video.save()

    except Exception as e:
        logger.error(f"Error processing video {video_id}: {e}")


def extract_thumbnail(video):
    """Extract a thumbnail from the middle of the video."""
    try:
        # Extract frame at 25% of the video
        time_pos = video.duration_seconds * 0.25 if video.duration_seconds else 1
        
        temp_thumb = NamedTemporaryFile(suffix='.jpg', delete=False)
        temp_thumb_path = temp_thumb.name
        temp_thumb.close()

        subprocess.run(
            [
                'ffmpeg',
                '-ss', str(time_pos),
                '-i', video.original_file.path,
                '-vframes', '1',
                '-q:v', '2',
                '-y',
                temp_thumb_path
            ],
            capture_output=True,
            check=True
        )

        with open(temp_thumb_path, 'rb') as f:
            video.thumbnail.save(f'thumb_{video.id}.jpg', ContentFile(f.read()), save=False)
        
        if os.path.exists(temp_thumb_path):
            os.remove(temp_thumb_path)
            
    except Exception as e:
        logger.error(f"Error extracting thumbnail for video {video.id}: {e}")


def get_video_duration(file_path):
    """Get video duration using FFprobe."""
    try:
        result = subprocess.run(
            [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ],
            capture_output=True,
            text=True,
            check=True
        )
        return float(result.stdout.strip())
    except Exception:
        return 0


def create_quality_version(video, quality):
    """Create a specific quality version of the video using FFmpeg."""
    # Map quality to resolution
    resolution_map = {
        '1080p': '1920x1080',
        '720p': '1280x720',
        '480p': '854x480',
        '360p': '640x360',
    }

    resolution = resolution_map.get(quality, '1280x720')
    output_path = os.path.join(settings.MEDIA_ROOT, f'temp_{video.id}_{quality}.mp4')

    # Use FFmpeg to transcode
    try:
        subprocess.run(
            [
                'ffmpeg',
                '-i', video.original_file.path,
                '-vf', f'scale={resolution}',
                '-c:v', 'libx264',
                '-crf', '23',
                '-c:a', 'aac',
                '-y',
                output_path
            ],
            capture_output=True,
            check=True
        )

        # Create VideoQuality object
        with open(output_path, 'rb') as f:
            content = f.read()
            video_quality = VideoQuality.objects.create(
                video=video,
                quality=quality,
                file_size=len(content)
            )
            video_quality.file.save(f'{video.id}_{quality}.mp4', ContentFile(content))

        # Create chunks (10 seconds each)
        create_video_chunks(video_quality)

        # Cleanup temp file
        if os.path.exists(output_path):
            os.remove(output_path)

    except Exception as e:
        logger.error(f"Error creating {quality} version: {e}")


def create_video_chunks(video_quality):
    """Split a quality version into 10-second chunks using FFmpeg."""
    chunk_duration = 10  # seconds
    output_dir = os.path.join(settings.MEDIA_ROOT, 'temp_chunks')
    os.makedirs(output_dir, exist_ok=True)

    # Split video into chunks
    try:
        pattern = os.path.join(output_dir, f'chunk_{video_quality.id}_%03d.mp4')
        subprocess.run(
            [
                'ffmpeg',
                '-i', video_quality.file.path,
                '-c', 'copy',
                '-segment_time', str(chunk_duration),
                '-f', 'segment',
                '-reset_timestamps', '1',
                '-y',
                pattern
            ],
            capture_output=True,
            check=True
        )

        # Create VideoChunk objects
        chunk_num = 0
        while True:
            chunk_file = os.path.join(output_dir, f'chunk_{video_quality.id}_{chunk_num:03d}.mp4')
            if not os.path.exists(chunk_file):
                break

            with open(chunk_file, 'rb') as f:
                content = f.read()
                start_time = chunk_num * chunk_duration
                end_time = min((chunk_num + 1) * chunk_duration, video_quality.video.duration_seconds or 0)
                chunk = VideoChunk.objects.create(
                    quality=video_quality,
                    chunk_number=chunk_num,
                    start_time=start_time,
                    end_time=end_time,
                    file_size=len(content)
                )
                chunk.file.save(f'chunk_{video_quality.id}_{chunk_num:03d}.mp4', ContentFile(content))

            chunk_num += 1

        # Cleanup temp chunks
        for file in os.listdir(output_dir):
            if file.startswith(f'chunk_{video_quality.id}_'):
                os.remove(os.path.join(output_dir, file))

    except Exception as e:
        logger.error(f"Error creating chunks: {e}")

