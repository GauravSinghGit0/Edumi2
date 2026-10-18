"""
Thin wrapper around ffmpeg / ffprobe for the video editor.

Every function here takes an input path and returns the path to a newly
created output file. Callers are responsible for moving/saving that output
onto the VideoProject model. Keeping this as small composable functions
(rather than one giant "apply edits" function) makes it easy to add new
editing features later.
"""
import json
import logging
import os
import subprocess
import uuid

from django.conf import settings

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    """Raised when an ffmpeg/ffprobe command fails."""
    pass


def _run(cmd, timeout=300):
    """Run a command list, raise FFmpegError with stderr on failure or timeout."""
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise FFmpegError(f"FFmpeg operation timed out after {timeout} seconds.")
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore")
        raise FFmpegError(stderr[-3000:])  # last part of stderr is usually the useful bit
    return result


def _tmp_path(suffix=".mp4"):
    tmp_dir = os.path.join(settings.MEDIA_ROOT, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    return os.path.join(tmp_dir, f"{uuid.uuid4().hex}{suffix}")


def _get_font_arg():
    win_font = "C:/Windows/Fonts/arial.ttf"
    if os.path.exists(win_font):
        return "fontfile='C\\:/Windows/Fonts/arial.ttf':"
    return ""


def probe(path):
    """Return parsed ffprobe JSON info for a media file: duration, streams, etc."""
    cmd = [
        settings.FFPROBE_BINARY,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    result = _run(cmd)
    return json.loads(result.stdout.decode("utf-8"))


def get_metadata(path):
    """Extract duration, width, height, has_audio from a media file."""
    data = probe(path)
    duration = None
    width = height = None
    has_audio = False

    fmt = data.get("format", {})
    if fmt.get("duration"):
        try:
            duration = float(fmt["duration"])
        except (TypeError, ValueError):
            duration = None

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and width is None:
            width = stream.get("width")
            height = stream.get("height")
            if duration is None and stream.get("duration"):
                try:
                    duration = float(stream["duration"])
                except (TypeError, ValueError):
                    pass
        elif stream.get("codec_type") == "audio":
            has_audio = True

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "has_audio": has_audio,
    }


def trim(input_path, start_seconds, end_seconds):
    """Cut the video to the [start, end] range (in seconds) without re-encoding (extremely fast stream copy)."""
    out_path = _tmp_path()
    duration = max(0.0, float(end_seconds) - float(start_seconds))
    cmd = [
        settings.FFMPEG_BINARY, "-y",
        "-ss", str(start_seconds),
        "-i", input_path,
        "-t", str(duration),
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        out_path,
    ]
    _run(cmd)
    return out_path


def mute(input_path):
    """Remove/silence the audio track entirely."""
    out_path = _tmp_path()
    cmd = [
        settings.FFMPEG_BINARY, "-y",
        "-i", input_path,
        "-c:v", "copy",
        "-an",
        out_path,
    ]
    _run(cmd)
    return out_path


def set_volume(input_path, volume_multiplier):
    """
    Adjust audio volume. volume_multiplier: 0.0 = silent, 1.0 = original, 2.0 = double.
    If the source has no audio track, this is a no-op copy.
    """
    meta = get_metadata(input_path)
    out_path = _tmp_path()
    if not meta["has_audio"]:
        cmd = [settings.FFMPEG_BINARY, "-y", "-i", input_path, "-c", "copy", out_path]
    else:
        cmd = [
            settings.FFMPEG_BINARY, "-y",
            "-i", input_path,
            "-c:v", "copy",
            "-filter:a", f"volume={volume_multiplier}",
            out_path,
        ]
    _run(cmd)
    return out_path


def merge(input_paths):
    """
    Concatenate multiple video files in order into a single output.
    Uses the filter_complex concat approach so inputs don't need matching
    codecs/formats beforehand (more robust than the concat demuxer for
    arbitrary user uploads, at the cost of a re-encode).

    Inputs may differ in whether they have audio (e.g. one clip was muted)
    and in resolution (e.g. one clip was rotated or is a different source).
    To keep the concat filter happy we pad missing audio with silence and
    scale every video stream to match the first clip's dimensions.
    """
    out_path = _tmp_path()
    metas = [get_metadata(p) for p in input_paths]

    target_width = metas[0]["width"] or 1280
    target_height = metas[0]["height"] or 720
    # ensure even dimensions for libx264
    target_width += target_width % 2
    target_height += target_height % 2

    cmd = [settings.FFMPEG_BINARY, "-y"]
    for p in input_paths:
        cmd += ["-i", p]

    n = len(input_paths)
    silent_input_indices = {}
    next_input_index = n
    for i, meta in enumerate(metas):
        if not meta["has_audio"]:
            duration = meta["duration"] or 1.0
            cmd += [
                "-f", "lavfi", "-t", str(duration),
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            ]
            silent_input_indices[i] = next_input_index
            next_input_index += 1

    filter_chunks = []
    concat_refs = []
    for i in range(n):
        video_label = f"v{i}"
        filter_chunks.append(
            f"[{i}:v:0]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,setsar=1[{video_label}]"
        )
        audio_ref = f"[{silent_input_indices[i]}:a:0]" if i in silent_input_indices else f"[{i}:a:0]"
        concat_refs.append(f"[{video_label}]{audio_ref}")

    filter_complex = ";".join(filter_chunks) + ";" + "".join(concat_refs) + f"concat=n={n}:v=1:a=1[outv][outa]"

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-c:a", "aac",
        out_path,
    ]
    _run(cmd)
    return out_path


def add_text_overlay(input_path, text, position="bottom", font_size=80,
                      color="white", start_seconds=None, end_seconds=None):
    """
    Burn a text overlay onto the video using the drawtext filter.
    position: 'top' | 'bottom' | 'center'
    start_seconds/end_seconds: optional window during which text is shown;
    if omitted, text shows for the whole video.
    """
    logger.debug("add_text_overlay called with position: %s", repr(position))
    out_path = _tmp_path()

    if isinstance(position, str) and position.startswith("custom:"):
        logger.debug("using custom position!")
        try:
            parts = position[7:].split(",")
            x_pct = float(parts[0])
            y_pct = float(parts[1])
            logger.debug("x_pct: %s, y_pct: %s", x_pct, y_pct)
            pos = f"x=(w-text_w)*{x_pct/100:.3f}:y=(h-text_h)*{y_pct/100:.3f}"
            logger.debug("ffmpeg pos string: %s", pos)
        except Exception as e:
            logger.debug("exception parsing custom position: %s", e)
            pos = "x=(w-text_w)/2:y=h-th-40"
    else:
        logger.debug("using predefined position: %s", position)
        position_map = {
            "top": "x=(w-text_w)/2:y=40",
            "bottom": "x=(w-text_w)/2:y=h-th-40",
            "center": "x=(w-text_w)/2:y=(h-text_h)/2",
        }
        pos = position_map.get(position, position_map["bottom"])

    # Escape text for the ffmpeg filter graph (colons and quotes are special).
    safe_text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")

    enable_clause = ""
    if start_seconds is not None and end_seconds is not None:
        enable_clause = f":enable='between(t,{start_seconds},{end_seconds})'"

    font_arg = _get_font_arg()
    drawtext = (
        f"drawtext={font_arg}text='{safe_text}':fontcolor={color}:fontsize={font_size}:"
        f"box=1:boxcolor=black@0.5:boxborderw=8:{pos}{enable_clause}"
    )

    cmd = [
        settings.FFMPEG_BINARY, "-y",
        "-i", input_path,
        "-vf", drawtext,
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
        "-c:a", "copy",
        out_path,
    ]
    _run(cmd)
    return out_path


def change_speed(input_path, speed_factor):
    """
    Change playback speed. speed_factor > 1 speeds up, < 1 slows down.
    Handles both video (setpts) and audio (atempo, which only supports
    0.5-2.0 per filter instance so we chain it for extreme values).
    """
    out_path = _tmp_path()
    meta = get_metadata(input_path)

    video_filter = f"setpts={1/speed_factor}*PTS"

    atempo_filters = []
    remaining = speed_factor
    if remaining < 0.5 or remaining > 2.0:
        # chain atempo filters to reach extreme speeds
        while remaining > 2.0:
            atempo_filters.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            atempo_filters.append("atempo=0.5")
            remaining /= 0.5
        atempo_filters.append(f"atempo={remaining}")
    else:
        atempo_filters.append(f"atempo={remaining}")
    audio_filter = ",".join(atempo_filters)

    if meta["has_audio"]:
        cmd = [
            settings.FFMPEG_BINARY, "-y",
            "-i", input_path,
            "-filter_complex", f"[0:v]{video_filter}[v];[0:a]{audio_filter}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
            "-c:a", "aac",
            out_path,
        ]
    else:
        cmd = [
            settings.FFMPEG_BINARY, "-y",
            "-i", input_path,
            "-vf", video_filter,
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
            "-an",
            out_path,
        ]
    _run(cmd)
    return out_path


def rotate(input_path, degrees):
    """Rotate video by 90, 180, or 270 degrees clockwise."""
    out_path = _tmp_path()
    degrees = int(degrees) % 360
    transpose_map = {90: "transpose=1", 180: "transpose=1,transpose=1", 270: "transpose=2"}
    vf = transpose_map.get(degrees)
    if vf is None:
        raise FFmpegError("Rotation must be 90, 180, or 270 degrees.")
    cmd = [
        settings.FFMPEG_BINARY, "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
        "-c:a", "copy",
        out_path,
    ]
    _run(cmd)
    return out_path


def resize(input_path, width, height):
    """Resize video to exact width x height (must be even numbers for h264)."""
    out_path = _tmp_path()
    width = int(width) + (int(width) % 2)
    height = int(height) + (int(height) % 2)
    cmd = [
        settings.FFMPEG_BINARY, "-y",
        "-i", input_path,
        "-vf", f"scale={width}:{height}",
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
        "-c:a", "copy",
        out_path,
    ]
    _run(cmd)
    return out_path


def apply_grayscale(input_path):
    """Convert video to grayscale."""
    out_path = _tmp_path()
    cmd = [
        settings.FFMPEG_BINARY, "-y",
        "-i", input_path,
        "-vf", "hue=s=0",
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
        "-c:a", "copy",
        out_path,
    ]
    _run(cmd)
    return out_path


def apply_fade(input_path, fade_in_seconds=1.0, fade_out_seconds=1.0):
    """Apply a fade-in at the start and fade-out at the end of the video."""
    meta = get_metadata(input_path)
    duration = meta["duration"] or 0
    fade_out_start = max(0.0, duration - fade_out_seconds)

    out_path = _tmp_path()
    vf = f"fade=t=in:st=0:d={fade_in_seconds},fade=t=out:st={fade_out_start}:d={fade_out_seconds}"
    cmd = [
        settings.FFMPEG_BINARY, "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
        "-c:a", "copy",
        out_path,
    ]
    _run(cmd)
    return out_path


def generate_thumbnail(input_path, at_seconds=1.0):
    """Grab a single frame as a JPEG thumbnail for preview purposes."""
    out_path = _tmp_path(suffix=".jpg")
    cmd = [
        settings.FFMPEG_BINARY, "-y",
        "-ss", str(at_seconds),
        "-i", input_path,
        "-frames:v", "1",
        "-q:v", "3",
        out_path,
    ]
    _run(cmd)
    return out_path


def convert_to_mkv(input_path):
    """Convert video container format to MKV lossless container without re-encoding."""
    out_path = _tmp_path(suffix=".mkv")
    cmd = [
        settings.FFMPEG_BINARY, "-y",
        "-i", input_path,
        "-c", "copy",
        out_path,
    ]
    _run(cmd)
    return out_path


def add_background_audio(video_path, audio_path, bg_volume=0.5, video_volume=1.0, start_seconds=0.0, end_seconds=None):
    """Mix an external audio file as background music with the video's audio track, starting and ending at specific times."""
    meta = get_metadata(video_path)
    duration = meta["duration"] or 0.0
    has_audio = meta["has_audio"]
    out_path = _tmp_path()
    
    start_seconds = float(start_seconds or 0.0)
    start_ms = int(start_seconds * 1000)
    bg_duration = (float(end_seconds) - start_seconds) if end_seconds else (duration - start_seconds)
    
    # 1. Trim background audio, reset presentation timestamps (pts)
    atrim_filter = f"atrim=0:{bg_duration},asetpts=PTS-STARTPTS"
    
    # 2. Delay the audio by start_ms if greater than 0
    if start_ms > 0:
        delay_filter = f"adelay={start_ms}:all=1"
        bg_filter = f"[1:a]{atrim_filter},{delay_filter},volume={bg_volume}[a_bg]"
    else:
        bg_filter = f"[1:a]{atrim_filter},volume={bg_volume}[a_bg]"
        
    if has_audio:
        filter_complex = (
            f"[0:a]volume={video_volume}[a_vid];"
            f"{bg_filter};"
            f"[a_vid][a_bg]amix=inputs=2:duration=first:dropout_transition=2[a_out]"
        )
        cmd = [
            settings.FFMPEG_BINARY, "-y",
            "-i", video_path,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[a_out]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            out_path
        ]
    else:
        filter_complex = (
            f"{bg_filter};"
            f"[a_bg]anull[a_out]"
        )
        cmd = [
            settings.FFMPEG_BINARY, "-y",
            "-i", video_path,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[a_out]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            out_path
        ]
    _run(cmd)
    return out_path
