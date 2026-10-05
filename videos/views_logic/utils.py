import logging
import os
import subprocess
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.temp import NamedTemporaryFile

from videos.models import Video, VideoQuality, VideoChunk

logger = logging.getLogger(__name__)


def process_video_sync(video_id):
    """Process video to create HLS (.m3u8) streams with H.265/HEVC high-efficiency encoding."""
    try:
        video = Video.objects.get(id=video_id)

        # Get video metadata (duration)
        duration = get_video_duration(video.original_file.path)
        video.duration_seconds = int(duration)
        
        # Auto-extract thumbnail if not present
        if not video.thumbnail:
            extract_thumbnail(video)
            
        video.save()

        # Generate HLS Master & Variant Playlists with H.265 Codec
        process_hls_encoding(video)

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


def process_hls_encoding(video):
    """
    Encode input video into multi-bitrate HLS (.m3u8) variant playlists using H.265 (libx265).
    Generates a Master Playlist for Adaptive Bitrate (ABR) streaming.
    """
    hls_root = os.path.join(settings.MEDIA_ROOT, 'videos', 'hls', str(video.id))
    os.makedirs(hls_root, exist_ok=True)

    quality_configs = [
        {'name': '1080p', 'res': '1920x1080', 'crf': '24', 'bandwidth': 5000000, 'audio_bitrate': '128k', 'codec_str': 'hvc1.1.6.L150.90'},
        {'name': '720p',  'res': '1280x720',  'crf': '25', 'bandwidth': 2800000, 'audio_bitrate': '128k', 'codec_str': 'hvc1.1.6.L120.90'},
        {'name': '480p',  'res': '854x480',   'crf': '26', 'bandwidth': 1400000, 'audio_bitrate': '96k',  'codec_str': 'hvc1.1.6.L93.90'},
        {'name': '360p',  'res': '640x360',   'crf': '28', 'bandwidth': 800000,  'audio_bitrate': '64k',  'codec_str': 'hvc1.1.6.L90.90'},
    ]

    master_playlist_lines = [
        '#EXTM3U',
        '#EXT-X-VERSION:6',
        '#EXT-X-INDEPENDENT-SEGMENTS',
        ''
    ]

    for cfg in quality_configs:
        quality_dir = os.path.join(hls_root, cfg['name'])
        os.makedirs(quality_dir, exist_ok=True)

        variant_playlist_path = os.path.join(quality_dir, 'playlist.m3u8')
        segment_pattern = os.path.join(quality_dir, 'segment_%03d.ts')

        # Transcode with H.265 (libx265) with hvc1 tag for universal Apple/browser HLS compatibility
        used_codec = 'h265'
        cmd = [
            'ffmpeg', '-y',
            '-i', video.original_file.path,
            '-vf', f"scale={cfg['res']}",
            '-c:v', 'libx265',
            '-crf', cfg['crf'],
            '-preset', 'fast',
            '-tag:v', 'hvc1',
            '-c:a', 'aac',
            '-b:a', cfg['audio_bitrate'],
            '-hls_time', '6',
            '-hls_playlist_type', 'vod',
            '-hls_segment_filename', segment_pattern,
            variant_playlist_path
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"HLS H.265 encoding successful for {cfg['name']} (Video ID {video.id})")
        except subprocess.CalledProcessError as err:
            logger.warning(f"libx265 failed for {cfg['name']}, falling back to libx264: {err.stderr[-500:] if err.stderr else err}")
            used_codec = 'h264'
            cmd[cmd.index('libx265')] = 'libx264'
            if '-tag:v' in cmd:
                tag_idx = cmd.index('-tag:v')
                del cmd[tag_idx:tag_idx+2]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            cfg['codec_str'] = 'avc1.4d401f'

        # Compute file sizes and record VideoQuality
        total_size = 0
        if os.path.exists(quality_dir):
            for f in os.listdir(quality_dir):
                total_size += os.path.getsize(os.path.join(quality_dir, f))

        rel_playlist_path = f"videos/hls/{video.id}/{cfg['name']}/playlist.m3u8"
        
        vq, _ = VideoQuality.objects.update_or_create(
            video=video,
            quality=cfg['name'],
            defaults={
                'hls_playlist': rel_playlist_path,
                'codec': used_codec,
                'bitrate': cfg['bandwidth'],
                'file_size': total_size
            }
        )

        # Build VideoChunk records for each generated segment
        segment_files = sorted([f for f in os.listdir(quality_dir) if f.endswith('.ts')])
        chunk_duration = 6.0
        for idx, seg_name in enumerate(segment_files):
            seg_path = os.path.join(quality_dir, seg_name)
            seg_size = os.path.getsize(seg_path)
            rel_seg_path = f"videos/hls/{video.id}/{cfg['name']}/{seg_name}"

            VideoChunk.objects.update_or_create(
                quality=vq,
                chunk_number=idx,
                defaults={
                    'start_time': idx * chunk_duration,
                    'end_time': (idx + 1) * chunk_duration,
                    'file': rel_seg_path,
                    'file_size': seg_size
                }
            )

        # Add variant to Master Playlist
        master_playlist_lines.append(
            f"#EXT-X-STREAM-INF:BANDWIDTH={cfg['bandwidth']},RESOLUTION={cfg['res']},CODECS=\"{cfg['codec_str']},mp4a.40.2\""
        )
        master_playlist_lines.append(f"{cfg['name']}/playlist.m3u8")
        master_playlist_lines.append('')

    # Save Master Playlist
    master_playlist_path = os.path.join(hls_root, 'master.m3u8')
    with open(master_playlist_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(master_playlist_lines))

    video.hls_master_playlist = f"videos/hls/{video.id}/master.m3u8"
    video.save(update_fields=['hls_master_playlist'])


