import os
import subprocess
import json
from django.conf import settings
from .ffmpeg_utils import FFmpegError, get_metadata

def compile_timeline_to_ffmpeg(project, timeline_json, output_path):
    """
    Takes a JSON timeline state and compiles it into a complex FFmpeg filtergraph
    to render the final video. Handles multiple audio tracks, text overlays, 
    video speed/volume adjustments, grayscale/sepia effects, cropping, scale, 
    rotation, and opacity.
    """
    from cameras.ffmpeg_helpers import get_ffmpeg_binary
    ffmpeg_bin = get_ffmpeg_binary()

    # Step 1: Normalize flat or track-based timeline inputs
    if not isinstance(timeline_json, dict):
        timeline_json = {}

    # Extract parameters from normalized schema
    tracks = timeline_json.get('tracks', [])
    
    # Try to find tracks. If empty, try to construct from root-level metadata
    v_track = next((t for t in tracks if t.get('type') == 'video'), None)
    t_track = next((t for t in tracks if t.get('type') == 'text'), None)
    a_track = next((t for t in tracks if t.get('type') == 'audio'), None)
    e_track = next((t for t in tracks if t.get('type') == 'effect'), None)
    i_track = next((t for t in tracks if t.get('type') == 'image'), None)
    s_track = next((t for t in tracks if t.get('type') == 'sticker'), None)

    # Fallback to map flat format
    if not v_track and timeline_json.get('clips'):
        v_track = {"type": "video", "clips": timeline_json.get("clips")}
    if not v_track:
        # Construct standard single video track clip using original file metadata
        try:
            meta = get_metadata(project.original_file.path)
            duration = meta.get("duration", 10.0)
        except Exception:
            duration = 10.0
        v_track = {
            "type": "video",
            "clips": [{"title": os.path.basename(project.original_file.name), "start": 0, "end": duration, "trimStart": 0, "trimEnd": duration}]
        }

    # Gather background audio clips
    audio_clips = []
    if a_track and a_track.get('clips'):
        audio_clips = a_track['clips']
    elif timeline_json.get('background_audios'):
        audio_clips = timeline_json.get('background_audios')

    # Gather text overlay clips
    text_clips = []
    if t_track and t_track.get('clips'):
        text_clips = t_track['clips']
    elif timeline_json.get('text_overlays'):
        text_clips = timeline_json.get('text_overlays')

    # Input gathering
    inputs = [project.original_file.path]
    cmd = [ffmpeg_bin, '-y', '-i', project.original_file.path]

    # Map extra audio files to FFmpeg inputs
    audio_inputs_start_idx = len(inputs)
    for ac in audio_clips:
        audio_path = ac.get('temp_path') or ac.get('path')
        if audio_path and os.path.exists(audio_path):
            inputs.append(audio_path)
            cmd.extend(['-i', audio_path])

    filter_complex = []
    video_outs = []
    audio_outs = []

    has_audio = False
    try:
        meta = get_metadata(project.original_file.path)
        has_audio = meta.get("has_audio", False)
    except Exception:
        pass

    # Process video clips
    clips = v_track.get('clips', [])
    for i, clip in enumerate(clips):
        trim_start = clip.get('trimStart', clip.get('start', 0))
        trim_end = clip.get('trimEnd', clip.get('end', 10))
        
        v_label = f"[v{i}]"
        a_label = f"[a{i}]"
        
        # Trim video stream
        filter_complex.append(f"[0:v]trim=start={trim_start}:end={trim_end},setpts=PTS-STARTPTS{v_label}")
        video_outs.append(v_label)
        
        if has_audio:
            # Trim audio stream
            filter_complex.append(f"[0:a]atrim=start={trim_start}:end={trim_end},asetpts=PTS-STARTPTS{a_label}")
            audio_outs.append(a_label)
        else:
            # Create silent audio channel matching video clip duration
            dur = max(0.5, trim_end - trim_start)
            filter_complex.append(f"anullsrc=d={dur}{a_label}")
            audio_outs.append(a_label)
            
    # Concatenate clips
    current_v = None
    current_a = None
    if len(clips) > 1:
        concat_inputs = "".join(f"{v}{a}" for v, a in zip(video_outs, audio_outs))
        n = len(clips)
        filter_complex.append(f"{concat_inputs}concat=n={n}:v=1:a=1[v_concat][a_concat]")
        current_v = "[v_concat]"
        current_a = "[a_concat]"
    elif len(clips) == 1:
        current_v = video_outs[0]
        current_a = audio_outs[0]
    else:
        current_v = "[0:v]"
        current_a = "[0:a]"

    # Video speed adjust
    speed_factor = float(timeline_json.get('speed', 1.0))
    if speed_factor != 1.0:
        next_v = "[v_speed]"
        filter_complex.append(f"{current_v}setpts={1/speed_factor}*PTS{next_v}")
        current_v = next_v
        
        # Audio speed tempo filters
        atempo_filters = []
        rem = speed_factor
        while rem > 2.0:
            atempo_filters.append("atempo=2.0")
            rem /= 2.0
        while rem < 0.5:
            atempo_filters.append("atempo=0.5")
            rem /= 0.5
        atempo_filters.append(f"atempo={rem}")
        next_a = "[a_speed]"
        filter_complex.append(f"{current_a}{','.join(atempo_filters)}{next_a}")
        current_a = next_a

    # Apply video rotation & crop & grayscale effects
    effects_state = timeline_json.get('effects', {})
    
    # Grayscale
    if effects_state.get('grayscale') or (e_track and any(c.get('effect') == 'grayscale' for c in e_track.get('clips', []))):
        next_v = "[v_gray]"
        filter_complex.append(f"{current_v}hue=s=0{next_v}")
        current_v = next_v

    # Sepia
    if e_track and any(c.get('effect') == 'sepia' for c in e_track.get('clips', [])):
        next_v = "[v_sepia]"
        filter_complex.append(f"{current_v}colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131{next_v}")
        current_v = next_v

    # Rotation
    rotate_deg = int(effects_state.get('rotate', 0)) % 360
    if rotate_deg in [90, 180, 270]:
        transpose_map = {90: "transpose=1", 180: "transpose=1,transpose=1", 270: "transpose=2"}
        vf_rot = transpose_map[rotate_deg]
        next_v = "[v_rot]"
        filter_complex.append(f"{current_v}{vf_rot}{next_v}")
        current_v = next_v

    # Custom Resize
    resize_state = timeline_json.get('resize')
    if resize_state:
        r_width = resize_state.get("width")
        r_height = resize_state.get("height")
        if r_width and r_height:
            try:
                w = int(r_width)
                h = int(r_height)
                w = w + (w % 2)
                h = h + (h % 2)
                next_v = "[v_resize]"
                filter_complex.append(f"{current_v}scale={w}:{h}{next_v}")
                current_v = next_v
            except (TypeError, ValueError):
                pass

    # Fade In / Out
    fade_state = effects_state.get("fade")
    trim_state = timeline_json.get("trim", {})
    fade_in_sec = 0.0
    fade_out_sec = 0.0
    if fade_state:
        fade_in_sec = float(fade_state.get("in", 0.0))
        fade_out_sec = float(fade_state.get("out", 0.0))
    else:
        if trim_state.get("fade_in"):
            fade_in_sec = 1.0
        if trim_state.get("fade_out"):
            fade_out_sec = 1.0

    if fade_in_sec > 0.0 or fade_out_sec > 0.0:
        # Calculate timeline duration
        v_duration = 0.0
        for clip in clips:
            c_start = float(clip.get('trimStart', clip.get('start', 0)))
            c_end = float(clip.get('trimEnd', clip.get('end', 10)))
            v_duration += max(0.0, c_end - c_start)
        if speed_factor != 1.0:
            v_duration /= speed_factor

        fade_out_start = max(0.0, v_duration - fade_out_sec)
        vf_fade_parts = []
        if fade_in_sec > 0.0:
            vf_fade_parts.append(f"fade=t=in:st=0:d={fade_in_sec}")
        if fade_out_sec > 0.0:
            vf_fade_parts.append(f"fade=t=out:st={fade_out_start}:d={fade_out_sec}")

        next_v = "[v_fade]"
        filter_complex.append(f"{current_v}{','.join(vf_fade_parts)}{next_v}")
        current_v = next_v

        if has_audio:
            af_fade_parts = []
            if fade_in_sec > 0.0:
                af_fade_parts.append(f"afade=t=in:ss=0:d={fade_in_sec}")
            if fade_out_sec > 0.0:
                af_fade_parts.append(f"afade=t=out:st={fade_out_start}:d={fade_out_sec}")
            next_a = "[a_fade]"
            filter_complex.append(f"{current_a}{','.join(af_fade_parts)}{next_a}")
            current_a = next_a

    # Overlay Text layers
    for idx, text_clip in enumerate(text_clips):
        txt = text_clip.get('text', '').replace("'", "").replace(":", r"\:")
        if not txt:
            continue
            
        position = text_clip.get('position', 'bottom')
        if position == 'top':
            x = '(w-text_w)/2'
            y = 'h*0.1'
        elif position == 'center':
            x = '(w-text_w)/2'
            y = '(h-text_h)/2'
        elif isinstance(position, str) and position.startswith("custom:"):
            try:
                parts = position[7:].split(",")
                x = f"(w-text_w)*{float(parts[0])/100:.3f}"
                y = f"(h-text_h)*{float(parts[1])/100:.3f}"
            except Exception:
                x = '(w-text_w)/2'
                y = 'h-text_h-h*0.1'
        else: # bottom
            x = '(w-text_w)/2'
            y = 'h-text_h-h*0.1'
            
        fontsize = text_clip.get('fontsize', text_clip.get('font_size', 48))
        fontcolor = text_clip.get('color', 'white')
        start = text_clip.get('start', 0.0)
        end = text_clip.get('end', 10.0)
        
        enable_str = f"between(t,{start},{end})"
        next_v = f"[v_txt{idx}]"
        
        font_path = "C\\:/Windows/Fonts/arial.ttf"
        drawtext_filter = (f"{current_v}drawtext=fontfile='{font_path}':text='{txt}':x={x}:y={y}:"
                           f"fontsize={fontsize}:fontcolor={fontcolor}:box=1:boxcolor=black@0.5:boxborderw=8:enable='{enable_str}'{next_v}")
        filter_complex.append(drawtext_filter)
        current_v = next_v

    # Resolution scaling based on exportResolution
    resolution = timeline_json.get('exportResolution', '1080p')
    scale_label = "[v_scaled]"
    if resolution == '480p':
        filter_complex.append(f"{current_v}scale=-2:480{scale_label}")
        current_v = scale_label
    elif resolution == '720p':
        filter_complex.append(f"{current_v}scale=-2:720{scale_label}")
        current_v = scale_label
    elif resolution == '1440p':
        filter_complex.append(f"{current_v}scale=-2:1440{scale_label}")
        current_v = scale_label
    elif resolution == '4k':
        filter_complex.append(f"{current_v}scale=-2:2160{scale_label}")
        current_v = scale_label
    else: # default 1080p
        filter_complex.append(f"{current_v}scale=-2:1080{scale_label}")
        current_v = scale_label

    # Volume / Mute
    audio_state = timeline_json.get("audio", {})
    vol_multiplier = float(audio_state.get("volume", 1.0))
    is_muted = audio_state.get("muted", False)
    
    if has_audio:
        if is_muted:
            next_a = "[a_vol]"
            filter_complex.append(f"{current_a}volume=0{next_a}")
            current_a = next_a
        elif vol_multiplier != 1.0:
            next_a = "[a_vol]"
            filter_complex.append(f"{current_a}volume={vol_multiplier}{next_a}")
            current_a = next_a

    # Mix background audio inputs
    mixed_audio_out = current_a
    audio_mix_labels = [current_a]
    
    # Process multiple audio inputs
    for idx, ac in enumerate(audio_clips):
        audio_path = ac.get('temp_path') or ac.get('path')
        if audio_path and os.path.exists(audio_path):
            input_idx = audio_inputs_start_idx + idx
            ac_start = float(ac.get('start', 0.0))
            ac_end = float(ac.get('end', 10.0))
            ac_dur = max(0.5, ac_end - ac_start)
            
            # Trim background audio, add delay offset
            start_ms = int(ac_start * 1000)
            delay_str = f",adelay={start_ms}|{start_ms}" if start_ms > 0 else ""
            vol = float(ac.get('bg_volume', ac.get('volume', 0.5)))
            
            label_trim = f"[a_trimmed_{idx}]"
            filter_complex.append(f"[{input_idx}:a]atrim=0:{ac_dur},asetpts=PTS-STARTPTS{delay_str},volume={vol}{label_trim}")
            audio_mix_labels.append(label_trim)

    # Perform amix if multiple audio streams are active
    if len(audio_mix_labels) > 1:
        mix_inputs = "".join(audio_mix_labels)
        n_inputs = len(audio_mix_labels)
        filter_complex.append(f"{mix_inputs}amix=inputs={n_inputs}:duration=first:dropout_transition=2[a_mixed]")
        mixed_audio_out = "[a_mixed]"

    if filter_complex:
        cmd.extend(['-filter_complex', ";".join(filter_complex)])
        cmd.extend(['-map', current_v, '-map', mixed_audio_out])
        cmd.extend(['-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac'])
    else:
        cmd.extend(['-c', 'copy'])
        
    # Bitrate/Quality settings based on exportQuality
    quality = timeline_json.get('exportQuality', 'high')
    if quality == 'low':
        cmd.extend(['-crf', '28'])
    elif quality == 'medium':
        cmd.extend(['-crf', '23'])
    elif quality == 'ultra':
        cmd.extend(['-crf', '14'])
    else: # high (default)
        cmd.extend(['-crf', '18'])
        
    cmd.append(output_path)
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore")
        raise FFmpegError(stderr[-3000:])
