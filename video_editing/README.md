# 🎬 Video Editing Module

<details open>
<summary><b>1. Core Purpose</b></summary>
The `video_editing` app is an industry-standard, Canva-style web video editor and rendering suite. It enables users to create non-destructive multi-track video projects, perform real-time canvas previewing, edit audio waveforms, apply text/image overlays, and compile final videos via FFmpeg.
</details>

<details>
<summary><b>2. Rationale & Architecture</b></summary>
Designed as a full multi-track non-destructive timeline engine (Video V1/V2, Audio A1/A2, Text T1, Image I1). Timeline state is stored as a rich JSON document (`timeline_state`), decoupling the real-time browser canvas editing experience from heavy backend rendering. Asynchronous FFmpeg tasks compile filtergraphs on the server without blocking main application threads.
</details>

<details>
<summary><b>3. Usage Instructions</b></summary>

- **Create Project**: Upload a base video file via the project list dashboard `/video_editing/`.
- **Multi-Track Editing**: Drag and drop video, image, text, and audio clips on timeline tracks.
- **Trimming & Splitting**: Use clip handles to adjust start/end boundaries, or press `S` / click "Split" to split clips at the playhead position.
- **Audio Editing**: Adjust track/clip volume levels, toggle track mute, and inspect audio waveform visualization on audio track clips.
- **Exporting**: Click "Process & Export Video" to dispatch an asynchronous FFmpeg compilation job.
</details>

<details>
<summary><b>4. System Integrations</b></summary>

- **Videos App**: Integrates with the `videos` app to publish completed edits directly as lecture recordings or student video resources.
- **FFmpeg & Celery**: Leverages background Celery workers and `ffmpeg_utils.py` / `timeline_compiler.py` for multi-stream audio mixing (`amix`), video overlays (`overlay`), and filtergraph compilation.
- **Media Range Streaming**: Uses `serve_media_ranges` HTTP range streaming for smooth playback seeking and proxy video serving.
</details>

<details>
<summary><b>5. Key Files Breakdown</b></summary>

- `models.py`: Defines `VideoProject` (holding `timeline_state` JSON and working files), `ProjectAsset`, and logged `EditOperation` entries.
- `timeline_compiler.py`: Converts multi-track JSON timeline states into complex FFmpeg filtergraphs for multi-video overlays, text placement, and multi-audio mixing.
- `ffmpeg_utils.py`: Low-level wrapper functions for video rotation, grayscale filters, trimming, resizing, and probe metadata extraction.
- `views.py`: API endpoints for project detail rendering, JSON timeline state auto-saving (`save_timeline`), asset uploads, and export dispatch (`export_timeline`).
- `templates/video_editing/project_detail.html`: HTML layout housing the Fabric.js preview canvas, multi-track timeline panel, and tool drawer.
</details>
