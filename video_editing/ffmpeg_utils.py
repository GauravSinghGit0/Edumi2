"""
Thin wrapper around ffmpeg / ffprobe for the video editor.

Every function here takes an input path and returns the path to a newly
created output file. Callers are responsible for moving/saving that output
onto the VideoProject model. Keeping this as small composable functions
(rather than one giant "apply edits" function) makes it easy to add new
editing features later.
"""
import json
import os
import shlex
import subprocess
import tempfile
import uuid

from django.conf import settings


class FFmpegError(Exception):
    """Raised when an ffmpeg/ffprobe command fails."""
    pass


def _run(cmd):
    """Run a command list, raise FFmpegError with stderr on failure."""
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
    import sys
    print("DEBUG: add_text_overlay called with position:", repr(position), file=sys.stderr)
    out_path = _tmp_path()

    if isinstance(position, str) and position.startswith("custom:"):
        print("DEBUG: using custom position!", file=sys.stderr)
        try:
            parts = position[7:].split(",")
            x_pct = float(parts[0])
            y_pct = float(parts[1])
            print("DEBUG: x_pct, y_pct:", x_pct, y_pct, file=sys.stderr)
            pos = f"x=(w-text_w)*{x_pct/100:.3f}:y=(h-text_h)*{y_pct/100:.3f}"
            print("DEBUG: ffmpeg pos string:", pos, file=sys.stderr)
        except Exception as e:
            print("DEBUG: exception parsing custom position:", e, file=sys.stderr)
            pos = "x=(w-text_w)/2:y=h-th-40"
    else:
        print("DEBUG: using predefined position:", position, file=sys.stderr)
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


def process_combined_edits(input_path, state):
    """
    Constructs a single FFmpeg execution with a filtergraph applying all edits together:
    - Trim (Extract / Delete modes)
    - Playback Speed
    - Grayscale
    - Rotation
    - Text Overlays
    - Fades (in/out)
    - Volume adjustments / muting
    """
    meta = get_metadata(input_path)
    duration = meta["duration"] or 0.0
    has_audio = meta["has_audio"]
    out_path = _tmp_path()

    filter_complex_parts = []
    
    v_in = "0:v"
    a_in = "0:a"
    
    # 1. Clips Operation (Multiple sequential extractions)
    clips = state.get("clips", [{"start": 0.0, "end": duration}])
    
    final_duration = duration
    temp_files_to_cleanup = []

    if len(clips) == 1 and (float(clips[0].get("start", 0)) > 0.0 or float(clips[0].get("end", duration)) < duration):
        # OPTIMIZATION: Single clip uses -c copy to pre-trim instantly!
        trim_start = float(clips[0]["start"])
        trim_end = float(clips[0]["end"])
        trim_duration = max(0.0, trim_end - trim_start)
        pre_trimmed_path = _tmp_path()
        trim_cmd = [
            settings.FFMPEG_BINARY, "-y",
            "-ss", str(trim_start),
            "-i", input_path,
            "-t", str(trim_duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            pre_trimmed_path
        ]
        _run(trim_cmd)
        input_path = pre_trimmed_path
        temp_files_to_cleanup.append(pre_trimmed_path)
        final_duration = trim_duration
    elif len(clips) > 1:
        # Complex concatenation of multiple clips
        concat_inputs = ""
        total_dur = 0.0
        for i, clip in enumerate(clips):
            start = float(clip["start"])
            end = float(clip["end"])
            total_dur += max(0.0, end - start)
            
            filter_complex_parts.append(f"[{v_in}]trim=start={start}:end={end},setpts=PTS-STARTPTS[v_clip{i}]")
            concat_inputs += f"[v_clip{i}]"
            
            if has_audio:
                filter_complex_parts.append(f"[{a_in}]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a_clip{i}]")
                concat_inputs += f"[a_clip{i}]"
                
        if has_audio:
            filter_complex_parts.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=1[v_concat][a_concat]")
            v_in = "v_concat"
            a_in = "a_concat"
        else:
            filter_complex_parts.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=0[v_concat]")
            v_in = "v_concat"
            
        final_duration = total_dur
    elif len(clips) == 0:
        final_duration = 0.0

    # 2. Speed Operation
    speed_factor = float(state.get("speed", 1.0))
    if speed_factor != 1.0:
        filter_complex_parts.append(f"[{v_in}]setpts={1/speed_factor}*PTS[v_speed]")
        v_in = "v_speed"
        
        if has_audio:
            atempo_filters = []
            remaining = speed_factor
            while remaining > 2.0:
                atempo_filters.append("atempo=2.0")
                remaining /= 2.0
            while remaining < 0.5:
                atempo_filters.append("atempo=0.5")
                remaining /= 0.5
            atempo_filters.append(f"atempo={remaining}")
            audio_filter = ",".join(atempo_filters)
            filter_complex_parts.append(f"[{a_in}]{audio_filter}[a_speed]")
            a_in = "a_speed"
            
        final_duration /= speed_factor

    # 3. Grayscale
    effects_state = state.get("effects", {})
    if effects_state.get("grayscale"):
        filter_complex_parts.append(f"[{v_in}]hue=s=0[v_gray]")
        v_in = "v_gray"

    # 4. Rotation
    rotate_deg = int(effects_state.get("rotate", 0)) % 360
    if rotate_deg in [90, 180, 270]:
        transpose_map = {90: "transpose=1", 180: "transpose=1,transpose=1", 270: "transpose=2"}
        vf_rot = transpose_map[rotate_deg]
        filter_complex_parts.append(f"[{v_in}]{vf_rot}[v_rot]")
        v_in = "v_rot"

    # 4b. Resize
    resize_state = state.get("resize", {})
    if resize_state:
        r_width = resize_state.get("width")
        r_height = resize_state.get("height")
        if r_width and r_height:
            try:
                width = int(r_width)
                height = int(r_height)
                width = width + (width % 2)
                height = height + (height % 2)
                filter_complex_parts.append(f"[{v_in}]scale={width}:{height}[v_resize]")
                v_in = "v_resize"
            except (TypeError, ValueError):
                pass

    # 5. Text Overlays
    text_overlays = state.get("text_overlays", [])
    for idx, overlay in enumerate(text_overlays):
        txt = overlay.get("text", "")
        if not txt:
            continue
        pos_name = overlay.get("position", "bottom")
        if isinstance(pos_name, str) and pos_name.startswith("custom:"):
            try:
                parts = pos_name[7:].split(",")
                x_pct = float(parts[0])
                y_pct = float(parts[1])
                pos = f"x=(w-text_w)*{x_pct/100:.3f}:y=(h-text_h)*{y_pct/100:.3f}"
            except Exception:
                pos = "x=(w-text_w)/2:y=h-th-40"
        else:
            position_map = {
                "top": "x=(w-text_w)/2:y=40",
                "bottom": "x=(w-text_w)/2:y=h-th-40",
                "center": "x=(w-text_w)/2:y=(h-text_h)/2",
            }
            pos = position_map.get(pos_name, position_map["bottom"])
        font_size = int(overlay.get("font_size", 80))
        color = overlay.get("color", "white") or "white"
        
        o_start = overlay.get("start")
        o_end = overlay.get("end")
        
        enable_clause = ""
        if o_start is not None and o_end is not None:
            enable_clause = f":enable='between(t,{o_start},{o_end})'"
            
        safe_text = txt.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")
        font_arg = _get_font_arg()
        drawtext = (
            f"drawtext={font_arg}text='{safe_text}':fontcolor={color}:fontsize={font_size}:"
            f"box=1:boxcolor=black@0.5:boxborderw=8:{pos}{enable_clause}"
        )
        filter_complex_parts.append(f"[{v_in}]{drawtext}[v_txt{idx}]")
        v_in = f"v_txt{idx}"

    # 6. Fades
    fade_state = effects_state.get("fade")
    fade_in_sec = 0.0
    fade_out_sec = 0.0
    if fade_state:
        fade_in_sec = float(fade_state.get("in", 0.0))
        fade_out_sec = float(fade_state.get("out", 0.0))
    elif trim_state.get("fade_in") or trim_state.get("fade_out"):
        if trim_state.get("fade_in"):
            fade_in_sec = 1.0
        if trim_state.get("fade_out"):
            fade_out_sec = 1.0

    if fade_in_sec > 0.0 or fade_out_sec > 0.0:
        fade_out_start = max(0.0, final_duration - fade_out_sec)
        vf_fade_parts = []
        if fade_in_sec > 0.0:
            vf_fade_parts.append(f"fade=t=in:st=0:d={fade_in_sec}")
        if fade_out_sec > 0.0:
            vf_fade_parts.append(f"fade=t=out:st={fade_out_start}:d={fade_out_sec}")
            
        filter_complex_parts.append(f"[{v_in}]{','.join(vf_fade_parts)}[v_fade]")
        v_in = "v_fade"
        
        if has_audio:
            af_fade_parts = []
            if fade_in_sec > 0.0:
                af_fade_parts.append(f"afade=t=in:ss=0:d={fade_in_sec}")
            if fade_out_sec > 0.0:
                af_fade_parts.append(f"afade=t=out:st={fade_out_start}:d={fade_out_sec}")
            filter_complex_parts.append(f"[{a_in}]{','.join(af_fade_parts)}[a_fade]")
            a_in = "a_fade"

    # 7. Volume / Mute
    audio_state = state.get("audio", {})
    vol_multiplier = float(audio_state.get("volume", 1.0))
    is_muted = audio_state.get("muted", False)
    
    if has_audio:
        if is_muted:
            filter_complex_parts.append(f"[{a_in}]volume=0[a_vol]")
            a_in = "a_vol"
        elif vol_multiplier != 1.0:
            filter_complex_parts.append(f"[{a_in}]volume={vol_multiplier}[a_vol]")
            a_in = "a_vol"

    # 8. Background Audios Mix
    background_audios = state.get("background_audios", [])
    valid_bg_inputs = []
    
    for bg in background_audios:
        bg_path = bg.get("temp_path")
        if bg_path and os.path.exists(bg_path):
            bg_vol = float(bg.get("bg_volume", 0.5))
            vid_vol = float(bg.get("video_volume", 1.0))
            bg_start = float(bg.get("start", 0.0))
            bg_end = bg.get("end")
            
            start_ms = int(bg_start * 1000)
            bg_duration = (float(bg_end) - bg_start) if bg_end else (final_duration - bg_start)
            
            delay_str = f",adelay={start_ms}|{start_ms}" if start_ms > 0 else ""
            
            valid_bg_inputs.append(bg_path)
            input_idx = len(valid_bg_inputs) # 1-indexed since video is 0
            
            if has_audio:
                filter_complex_parts.append(
                    f"[{a_in}]volume={vid_vol}[a_vid{input_idx}];"
                    f"[{input_idx}:a]atrim=0:{bg_duration:.2f},asetpts=PTS-STARTPTS{delay_str},volume={bg_vol}[a_bg{input_idx}];"
                    f"[a_vid{input_idx}][a_bg{input_idx}]amix=inputs=2:duration=first:dropout_transition=2[a_mixed{input_idx}]"
                )
                a_in = f"a_mixed{input_idx}"
            else:
                filter_complex_parts.append(
                    f"[{input_idx}:a]atrim=0:{bg_duration:.2f},asetpts=PTS-STARTPTS{delay_str},volume={bg_vol}[a_bg{input_idx}];"
                    f"[a_bg{input_idx}]anull[a_mixed{input_idx}]"
                )
                a_in = f"a_mixed{input_idx}"
                has_audio = True

    # Assemble final command
    cmd = [settings.FFMPEG_BINARY, "-y", "-i", input_path]
    for bg_path in valid_bg_inputs:
        cmd += ["-i", bg_path]
    
    if filter_complex_parts:
        filter_complex_str = ";".join(filter_complex_parts)
        cmd += ["-filter_complex", filter_complex_str]
        cmd += ["-map", f"[{v_in}]"]
        if has_audio:
            cmd += ["-map", f"[{a_in}]"]
        cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-c:a", "aac"]
    else:
        cmd += ["-c:v", "copy"]
        if has_audio:
            cmd += ["-c:a", "copy"]

    cmd += ["-avoid_negative_ts", "make_zero", out_path]
    
    try:
        _run(cmd)
    finally:
        for tmp_file in temp_files_to_cleanup:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass
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


def delete_range(input_path, start_seconds, end_seconds):
    """Cut out the [start_seconds, end_seconds] range from the video and stitch the remaining parts together.
    Uses extremely fast stream copying (-c copy) without re-encoding to minimize latency.
    """
    meta = get_metadata(input_path)
    duration = meta["duration"] or 0.0
    out_path = _tmp_path()

    start_seconds = float(start_seconds)
    end_seconds = float(end_seconds)

    # Edge cases
    if start_seconds <= 0.0:
        # Just keep the part from end_seconds to the end
        cmd = [
            settings.FFMPEG_BINARY, "-y",
            "-ss", str(end_seconds),
            "-i", input_path,
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            out_path
        ]
        _run(cmd)
        return out_path

    if end_seconds >= duration:
        # Just keep the part from start to start_seconds
        cmd = [
            settings.FFMPEG_BINARY, "-y",
            "-ss", "0",
            "-i", input_path,
            "-t", str(start_seconds),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            out_path
        ]
        _run(cmd)
        return out_path

    # General case: slice part 1, slice part 2, concat
    part1_path = _tmp_path()
    part2_path = _tmp_path()
    
    try:
        # 1. Slice part 1 (0 to start_seconds)
        cmd1 = [
            settings.FFMPEG_BINARY, "-y",
            "-ss", "0",
            "-i", input_path,
            "-t", str(start_seconds),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            part1_path
        ]
        _run(cmd1)

        # 2. Slice part 2 (end_seconds to end)
        cmd2 = [
            settings.FFMPEG_BINARY, "-y",
            "-ss", str(end_seconds),
            "-i", input_path,
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            part2_path
        ]
        _run(cmd2)

        # 3. Write concat text file
        concat_txt = _tmp_path(suffix=".txt")
        # In FFmpeg, escape single quotes and backslashes
        def safe_path(p):
            return p.replace('\\', '/').replace("'", "'\\''")
            
        with open(concat_txt, "w", encoding="utf-8") as f:
            f.write(f"file '{safe_path(part1_path)}'\n")
            f.write(f"file '{safe_path(part2_path)}'\n")

        # 4. Perform concat stream copy
        cmd_concat = [
            settings.FFMPEG_BINARY, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_txt,
            "-c", "copy",
            out_path
        ]
        _run(cmd_concat)
        
        # Clean up concat txt
        if os.path.exists(concat_txt):
            try:
                os.remove(concat_txt)
            except OSError:
                pass

    finally:
        # Clean up temporary slices
        for temp_file in [part1_path, part2_path]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

    return out_path
