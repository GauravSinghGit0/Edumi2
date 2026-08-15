"""
Utility helpers for resolving FFmpeg / FFprobe binary paths.

Kept in a standalone module (no Django model imports) to avoid
circular-import issues when models.py needs to use these helpers.
"""
import os
import shutil


_user_profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
_WINGET_FFMPEG = os.path.join(
    _user_profile,
    "AppData", "Local", "Microsoft", "WinGet", "Packages",
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe",
    "ffmpeg-8.1.2-full_build", "bin", "ffmpeg.exe"
)
_WINGET_FFPROBE = _WINGET_FFMPEG.replace("ffmpeg.exe", "ffprobe.exe")


def get_ffmpeg_binary():
    """Return the absolute path to ffmpeg, resolved in priority order:
    1. FFMPEG_BINARY env var
    2. settings.FFMPEG_BINARY (if defined in Django settings)
    3. Known winget install path
    4. Anything on PATH via shutil.which
    5. Bare 'ffmpeg' (last resort — works after shell restart)
    """
    # Env var
    env = os.environ.get("FFMPEG_BINARY", "")
    if env and os.path.exists(env):
        return env
    # Django settings
    try:
        from django.conf import settings as _s
        val = getattr(_s, "FFMPEG_BINARY", None)
        if val and os.path.exists(val):
            return val
    except Exception:
        pass
    # Winget path
    if os.path.exists(_WINGET_FFMPEG):
        return _WINGET_FFMPEG
    # PATH
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"


def get_ffprobe_binary():
    """Same resolution logic as get_ffmpeg_binary() but for ffprobe."""
    env = os.environ.get("FFPROBE_BINARY", "")
    if env and os.path.exists(env):
        return env
    try:
        from django.conf import settings as _s
        val = getattr(_s, "FFPROBE_BINARY", None)
        if val and os.path.exists(val):
            return val
    except Exception:
        pass
    if os.path.exists(_WINGET_FFPROBE):
        return _WINGET_FFPROBE
    found = shutil.which("ffprobe")
    if found:
        return found
    return "ffprobe"


def get_video_duration(file_path):
    """Get the duration of a video file in seconds using ffprobe."""
    import subprocess
    if not file_path or not os.path.exists(file_path):
        return None
    ffprobe_bin = get_ffprobe_binary()
    cmd = [
        ffprobe_bin,
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        return float(output)
    except Exception as e:
        # Silently return None
        return None

