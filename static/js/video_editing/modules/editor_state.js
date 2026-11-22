/**
 * Video Editor Module — Core State, Time Sync & Payload Builder
 */
  "use strict";

  var editorState = {
    video_clips: [],
    speed: 1.0,
    volume: 1.0,
    muted: false,
    userMuted: false,
    text_overlays: [],
    background_audios: [],
    active_effects: [],
    rotate: 0,
    resize: null,
    grayscale: false,
    fade: null,
    trim: {
      start: 0,
      end: 0,
      mode: "extract",
      fade_in: false,
      fade_out: false
    }
  };
  var duration = 0;
  var selectedClipIndex = -1;
  var activePlayingClipIndex = 0;
  var timelineCurrentTime = 0;
  var baseVideoOriginalSrc = "";
  var isTransitioningClip = false;
  var globalSelection = { track: null, index: -1 };
  var createAndAppendAssetCard = null;
  var renderTextOverlays = function () {};
  var renderAllTimelineTracks = function () {};
  var selectTimelineItem = function () {};
  var clearGlobalSelection = function () {};
  var zoomFactor = 1.0;
  var video = document.getElementById("main-video");
  var basePxPerSecond = 15;
  var recalculateVideoClipsTimeline = function () {};
  var renderClipBlocks = async function () {};
  var updateRuler = function () {};
  var renderTrim = function () {};
  var generateThumbnails = async function () {};
  var updatePlayheadSmooth = function () {};
  var snapTimeToPoints = function (time) { return { time, snapped: false }; };
  var hideSnapGuide = function () {
    const snapGuide = document.getElementById("timeline-snap-guide");
    if (snapGuide) snapGuide.style.display = "none";
  };
  var getSecondsFromX = function (clientX) {
    const trimTrack = document.getElementById("trim-track") || document.getElementById("timeline-tracks-wrapper");
    if (!trimTrack) return 0;
    const rect = trimTrack.getBoundingClientRect();
    const pxPerSec = (basePxPerSecond || 15) * (zoomFactor || 1.0);
    const relativeX = clientX - rect.left;
    const s = relativeX / Math.max(0.001, pxPerSec);
    return Math.max(0, Math.min(duration || 0, s));
  };

  function formatTime(secs) {
    if (isNaN(secs) || secs < 0) return "00:00:00";
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  function syncVideoElementToTimeline(tTimeline, forceSeek = false) {
    const video = document.getElementById("main-video");
    if (!video) return;
    if (!baseVideoOriginalSrc) {
      baseVideoOriginalSrc = video.currentSrc || video.src || window.REEL_PROJECT_WORKING_URL || window.REEL_PROJECT_ORIGINAL_URL || "";
    }
    const clips = editorState.video_clips || [];
    if (clips.length === 0) {
      if (forceSeek || Math.abs(video.currentTime - tTimeline) > 0.15) {
        try { video.currentTime = tTimeline; } catch (e) {}
      }
      syncAudioPreviewToTimeline(tTimeline, forceSeek);
      return;
    }
    let targetClipIndex = 0;
    for (let i = 0; i < clips.length; i++) {
      const c = clips[i];
      if (tTimeline >= c.start && (tTimeline < c.end || i === clips.length - 1)) {
        targetClipIndex = i;
        break;
      }
    }
    activePlayingClipIndex = targetClipIndex;
    const clip = clips[targetClipIndex];
    const targetSrc = clip.url || baseVideoOriginalSrc;
    const offset = Math.max(0, Math.min(clip.duration || 0, tTimeline - (clip.start || 0)));
    const targetSourceTime = (parseFloat(clip.trimStart) || 0) + offset;

    const isDifferentSrc = targetSrc && video.src && !video.src.endsWith(targetSrc) && video.currentSrc && !video.currentSrc.endsWith(targetSrc);
    if (isDifferentSrc) {
      isTransitioningClip = true;
      const wasPlaying = !video.paused;
      video.src = targetSrc;
      video.load();
      const onCanPlay = () => {
        video.removeEventListener("canplay", onCanPlay);
        try { video.currentTime = targetSourceTime; } catch (e) {}
        const onSeeked = () => {
          video.removeEventListener("seeked", onSeeked);
          isTransitioningClip = false;
          syncAudioPreviewToTimeline(tTimeline, true);
          if (wasPlaying) video.play().catch(() => {});
        };
        video.addEventListener("seeked", onSeeked, { once: true });
        setTimeout(() => { isTransitioningClip = false; }, 400);
      };
      video.addEventListener("canplay", onCanPlay, { once: true });
    } else {
      if (forceSeek || Math.abs(video.currentTime - targetSourceTime) > 0.15) {
        isTransitioningClip = true;
        try { video.currentTime = targetSourceTime; } catch (e) {}
        const onSeeked = () => {
          video.removeEventListener("seeked", onSeeked);
          isTransitioningClip = false;
          syncAudioPreviewToTimeline(tTimeline, true);
        };
        video.addEventListener("seeked", onSeeked, { once: true });
        setTimeout(() => { isTransitioningClip = false; }, 250);
      } else {
        syncAudioPreviewToTimeline(tTimeline, forceSeek);
      }
    }
  }

  function syncAudioPreviewToTimeline(tTimeline, isSeeking = false) {
    const video = document.getElementById("main-video");
    if (!video) return;

    const audioClips = editorState.background_audios || [];
    const hasAudioClips = audioClips.length > 0;
    const isUserMuted = Boolean(editorState.userMuted || editorState.muted);
    const masterVolume = Number.isFinite(editorState.volume) ? editorState.volume : 1.0;
    const isVideoPaused = video.paused || video.ended;
    const playbackSpeed = Number(editorState.speed || video.playbackRate || 1.0);

    // If audio was deleted by user, video internal audio must be muted and previews removed
    if (editorState.audio_deleted_by_user) {
      if (!video.muted) video.muted = true;
      let idx = 0;
      while (document.getElementById(`preview-timeline-audio-${idx}`)) {
        const el = document.getElementById(`preview-timeline-audio-${idx}`);
        el.pause();
        el.removeAttribute("src");
        if (typeof el.load === "function") el.load();
        el.remove();
        idx++;
      }
      return;
    }

    if (!hasAudioClips) {
      // No audio clips on timeline - play video internal audio adhering to user mute
      const shouldMute = isUserMuted;
      if (video.muted !== shouldMute) video.muted = shouldMute;
      if (!shouldMute && Math.abs(video.volume - masterVolume) > 0.01) {
        video.volume = Math.max(0, Math.min(1.0, masterVolume));
      }
      let idx = 0;
      while (document.getElementById(`preview-timeline-audio-${idx}`)) {
        const el = document.getElementById(`preview-timeline-audio-${idx}`);
        el.pause();
        el.removeAttribute("src");
        if (typeof el.load === "function") el.load();
        el.remove();
        idx++;
      }
      return;
    }

    // Default linked mode: audio is attached to video and plays natively through video element
    // but we still want to support overlapping audio clips (e.g. external background music)
    if (!editorState.audio_separated) {
      const overlappingClips = audioClips.filter(ac => {
        const acStart = parseFloat(ac.start != null ? ac.start : 0);
        const acEnd = parseFloat(ac.end != null ? ac.end : (acStart + (parseFloat(ac.duration) || 0)));
        return (tTimeline >= acStart - 0.03 && tTimeline < acEnd - 0.03);
      });

      const defaultVideoSrc = video.currentSrc || video.src || window.REEL_PROJECT_PROXY_URL || "";
      const videoExpectedSourceTime = timelineToSourceTime(tTimeline);
      let nativeVideoAudioHandled = false;

      overlappingClips.forEach((ac, idx) => {
        const clipVol = parseFloat(ac.bg_volume !== undefined ? ac.bg_volume : (ac.volume !== undefined ? ac.volume : 1.0));
        const effectiveVol = Math.max(0, Math.min(1.0, masterVolume * clipVol));
        const targetSrc = ac.url || (ac.is_detached ? defaultVideoSrc : "");
        
        // Check if this is the original video audio aligned with current video playhead
        const offsetInClip = Math.max(0, tTimeline - ac.start);
        const expectedSourceTime = (ac.trimStart || 0) + offsetInClip;
        const isDetachedOriginal = Boolean(ac.is_detached || (!ac.url && !ac.path));
        const isAlignedWithVideo = isDetachedOriginal && !ac.user_dragged && Math.abs(expectedSourceTime - videoExpectedSourceTime) < 0.25;

        if (isAlignedWithVideo && !nativeVideoAudioHandled) {
          nativeVideoAudioHandled = true;
          const shouldMute = isUserMuted;
          if (video.muted !== shouldMute) video.muted = shouldMute;
          if (!shouldMute && Math.abs(video.volume - effectiveVol) > 0.01) {
            video.volume = effectiveVol;
          }
          // Ensure no preview element is playing this same audio
          const existingEl = document.getElementById(`preview-timeline-audio-${idx}`);
          if (existingEl && !existingEl.paused) existingEl.pause();
          return;
        }

        // External audio or non-aligned detached audio -> play through preview element
        let audioEl = document.getElementById(`preview-timeline-audio-${idx}`);
        if (!audioEl) {
          audioEl = document.createElement("audio");
          audioEl.id = `preview-timeline-audio-${idx}`;
          audioEl.preload = "auto";
          audioEl.crossOrigin = "anonymous";
          audioEl.src = targetSrc;
          document.body.appendChild(audioEl);
        } else if (audioEl.src !== targetSrc && targetSrc) {
          audioEl.src = targetSrc;
        }

        if (Math.abs(audioEl.playbackRate - playbackSpeed) > 0.01) audioEl.playbackRate = playbackSpeed;
        
        if (isUserMuted) {
          if (!audioEl.muted) audioEl.muted = true;
        } else {
          if (audioEl.muted) audioEl.muted = false;
          if (Math.abs(audioEl.volume - effectiveVol) > 0.01) audioEl.volume = effectiveVol;
        }

        if (isVideoPaused) {
          if (!audioEl.paused) audioEl.pause();
          if (isSeeking || Math.abs(audioEl.currentTime - expectedSourceTime) > 0.1) {
            try { audioEl.currentTime = expectedSourceTime; } catch (e) {}
          }
        } else {
          if (audioEl.paused) {
            try { audioEl.currentTime = expectedSourceTime; } catch (e) {}
            audioEl.play().catch(() => {});
          } else {
            const drift = audioEl.currentTime - expectedSourceTime;
            if (isSeeking || Math.abs(drift) > 0.25) {
              try { audioEl.currentTime = expectedSourceTime; } catch (e) {}
            } else if (Math.abs(drift) > 0.04) {
              audioEl.playbackRate = playbackSpeed * (drift < 0 ? 1.05 : 0.95);
            } else {
              audioEl.playbackRate = playbackSpeed;
            }
          }
        }
      });

      if (!nativeVideoAudioHandled) {
        if (!video.muted) video.muted = true;
      }

      // Clean up surplus/non-overlapping preview audio elements
      let idx = 0;
      while (document.getElementById(`preview-timeline-audio-${idx}`)) {
        const el = document.getElementById(`preview-timeline-audio-${idx}`);
        const isCurrentlyOverlapping = overlappingClips.some((ac, i) => `preview-timeline-audio-${idx}` === `preview-timeline-audio-${i}`);
        // Simplified cleanup: just pause anything that isn't supposed to be playing
        const clipIdx = parseInt(el.id.replace('preview-timeline-audio-', ''));
        const ac = audioClips[clipIdx];
        const isStillValid = ac && (tTimeline >= (ac.start || 0) - 0.03 && tTimeline < (ac.end || duration) - 0.03);
        
        if (!isStillValid && !el.paused) {
          el.pause();
        }
        idx++;
      }
      return;
    }

    // Separated Mode: handle independent audio clips (which may be shifted, trimmed, or external)
    const defaultVideoSrc = video.currentSrc || video.src || window.REEL_PROJECT_PROXY_URL || "";
    const videoExpectedSourceTime = timelineToSourceTime(tTimeline);

    let nativeVideoAudioHandled = false;

    audioClips.forEach((ac, idx) => {
      let audioEl = document.getElementById(`preview-timeline-audio-${idx}`);
      const targetSrc = ac.url || (ac.is_detached ? defaultVideoSrc : "");
      if (!targetSrc) return;

      const acStart = parseFloat(ac.start != null ? ac.start : 0);
      const acEnd = parseFloat(ac.end != null ? ac.end : (acStart + (parseFloat(ac.duration) || 0)));
      const acTrimStart = parseFloat(ac.trimStart != null ? ac.trimStart : 0);
      const isWithinBounds = (tTimeline >= acStart - 0.03 && tTimeline < acEnd - 0.03);

      const clipVol = parseFloat(ac.bg_volume !== undefined ? ac.bg_volume : (ac.volume !== undefined ? ac.volume : 1.0));
      const effectiveVol = Math.max(0, Math.min(1.0, masterVolume * clipVol));

      if (isWithinBounds) {
        const offsetInClip = Math.max(0, tTimeline - acStart);
        const expectedSourceTime = acTrimStart + offsetInClip;

        // Check if this audio clip is the original video audio AND aligned with video
        const isDetachedOriginal = Boolean(ac.is_detached || (!ac.url && !ac.path) || (ac.name && (ac.name.includes("Audio Track") || ac.name.includes("Audio Stream"))));
        const isAlignedWithVideo = isDetachedOriginal && !ac.user_dragged && Math.abs(expectedSourceTime - videoExpectedSourceTime) < 0.25;

        if (isAlignedWithVideo && !nativeVideoAudioHandled) {
          // Play natively through the video element for 100% sample-accurate, zero-latency lip sync!
          nativeVideoAudioHandled = true;
          const shouldMute = isUserMuted;
          if (video.muted !== shouldMute) video.muted = shouldMute;
          if (!shouldMute && Math.abs(video.volume - effectiveVol) > 0.01) {
            video.volume = effectiveVol;
          }
          if (audioEl && !audioEl.paused) {
            audioEl.pause();
          }
          return;
        }

        // If not aligned with video or is external audio, play through dedicated preview audio element
        if (!audioEl) {
          audioEl = document.createElement("audio");
          audioEl.id = `preview-timeline-audio-${idx}`;
          audioEl.preload = "auto";
          audioEl.crossOrigin = "anonymous";
          audioEl.src = targetSrc;
          document.body.appendChild(audioEl);
        } else if (audioEl.src !== targetSrc && targetSrc) {
          audioEl.src = targetSrc;
        }

        if (Math.abs(audioEl.playbackRate - playbackSpeed) > 0.01) {
          audioEl.playbackRate = playbackSpeed;
        }

        if (isUserMuted) {
          if (!audioEl.muted) audioEl.muted = true;
        } else {
          if (audioEl.muted) audioEl.muted = false;
          if (Math.abs(audioEl.volume - effectiveVol) > 0.01) {
            audioEl.volume = effectiveVol;
          }
        }

        if (isVideoPaused) {
          if (!audioEl.paused) audioEl.pause();
          if (isSeeking || Math.abs(audioEl.currentTime - expectedSourceTime) > 0.1) {
            try { audioEl.currentTime = expectedSourceTime; } catch (e) {}
          }
        } else {
          if (audioEl.paused) {
            try { audioEl.currentTime = expectedSourceTime; } catch (e) {}
            audioEl.play().catch(() => {});
          } else {
            const drift = audioEl.currentTime - expectedSourceTime;
            if (isSeeking || Math.abs(drift) > 0.25) {
              try { audioEl.currentTime = expectedSourceTime; } catch (e) {}
              audioEl.playbackRate = playbackSpeed;
            } else if (Math.abs(drift) > 0.04) {
              // Smooth micro-adjustment to eliminate drift without seek stuttering
              audioEl.playbackRate = playbackSpeed * (drift < 0 ? 1.05 : 0.95);
            } else {
              audioEl.playbackRate = playbackSpeed;
            }
          }
        }
      } else {
        // Outside bounds of this clip
        if (audioEl && !audioEl.paused) {
          audioEl.pause();
        }
        if (audioEl && isSeeking) {
          try { audioEl.currentTime = acTrimStart; } catch (e) {}
        }
      }
    });

    // If native video audio was not handled (e.g. gap, deleted portion, or all active audio is detached/shifted):
    // Video element internal audio MUST be muted so cut/deleted portions remain completely silent!
    if (!nativeVideoAudioHandled) {
      if (!video.muted) video.muted = true;
    }

    // Clean up surplus audio preview elements
    let surplusIdx = audioClips.length;
    while (document.getElementById(`preview-timeline-audio-${surplusIdx}`)) {
      const surplusEl = document.getElementById(`preview-timeline-audio-${surplusIdx}`);
      surplusEl.pause();
      surplusEl.removeAttribute("src");
      if (typeof surplusEl.load === "function") surplusEl.load();
      surplusEl.remove();
      surplusIdx++;
    }
  }

  function timelineToSourceTime(tTimeline) {
    if (!editorState.video_clips || editorState.video_clips.length === 0) {
      return tTimeline;
    }
    tTimeline = Math.max(0, Math.min(tTimeline, duration || 0));
    for (let i = 0; i < editorState.video_clips.length; i++) {
      const clip = editorState.video_clips[i];
      const dur = parseFloat(clip.duration || 0);
      if (tTimeline >= clip.start && (tTimeline < clip.end || i === editorState.video_clips.length - 1)) {
        activePlayingClipIndex = i;
        const offset = Math.max(0, tTimeline - clip.start);
        const trimStart = parseFloat(clip.trimStart !== undefined ? clip.trimStart : 0);
        return trimStart + Math.min(offset, dur);
      }
    }
    const lastClip = editorState.video_clips[editorState.video_clips.length - 1];
    if (lastClip) {
      activePlayingClipIndex = editorState.video_clips.length - 1;
      return parseFloat(lastClip.trimEnd !== undefined ? lastClip.trimEnd : (lastClip.trimStart + lastClip.duration));
    }
    return tTimeline;
  }

  function sourceToTimelineTime(tSource) {
    if (!editorState.video_clips || editorState.video_clips.length === 0) {
      return tSource;
    }
    // Check currently active playing clip first to maintain continuity across split clips
    if (activePlayingClipIndex >= 0 && activePlayingClipIndex < editorState.video_clips.length) {
      const clip = editorState.video_clips[activePlayingClipIndex];
      const trimStart = parseFloat(clip.trimStart !== undefined ? clip.trimStart : 0);
      const trimEnd = parseFloat(clip.trimEnd !== undefined ? clip.trimEnd : (trimStart + clip.duration));
      if (tSource >= trimStart - 0.05 && tSource <= trimEnd + 0.05) {
        return clip.start + Math.max(0, Math.min(clip.duration, tSource - trimStart));
      }
    }
    for (let i = 0; i < editorState.video_clips.length; i++) {
      const clip = editorState.video_clips[i];
      const trimStart = parseFloat(clip.trimStart !== undefined ? clip.trimStart : 0);
      const trimEnd = parseFloat(clip.trimEnd !== undefined ? clip.trimEnd : (trimStart + clip.duration));
      if (tSource >= trimStart && tSource <= trimEnd) {
        activePlayingClipIndex = i;
        return clip.start + (tSource - trimStart);
      }
    }
    for (let i = 0; i < editorState.video_clips.length; i++) {
      const clip = editorState.video_clips[i];
      const trimStart = parseFloat(clip.trimStart !== undefined ? clip.trimStart : 0);
      if (tSource < trimStart) {
        activePlayingClipIndex = i;
        return clip.start;
      }
    }
    return duration;
  }

  function buildTimelinePayload() {
    const tracks = [];
    
    // Video track (always present)
    if (editorState.video_clips && editorState.video_clips.length > 0) {
      tracks.push({
        type: 'video',
        name: 'Video Track',
        clips: editorState.video_clips.map(clip => ({
          ...clip,
          start: clip.start != null ? clip.start : 0,
          end: clip.end != null ? clip.end : (clip.duration || 0),
          trimStart: clip.trimStart != null ? clip.trimStart : 0,
          trimEnd: clip.trimEnd != null ? clip.trimEnd : (clip.duration || 0),
          duration: clip.duration || 0,
          title: clip.title || clip.name || 'Clip'
        }))
      });
    }
    
    // Audio track (when background audio exists)
    const cleanedAudioClips = (editorState.background_audios || []).map(audio => {
      const aStart = parseFloat(audio.start != null ? audio.start : 0);
      const aEnd = parseFloat(audio.end != null ? audio.end : (aStart + (parseFloat(audio.duration) || 0)));
      const aDur = Math.max(0.01, parseFloat((aEnd - aStart).toFixed(2)));
      const aTrimStart = parseFloat(audio.trimStart != null ? audio.trimStart : 0);
      const rawTrimEnd = audio.trimEnd != null ? parseFloat(audio.trimEnd) : (aTrimStart + aDur);
      const aTrimEnd = parseFloat((rawTrimEnd > aTrimStart ? rawTrimEnd : (aTrimStart + aDur)).toFixed(2));
      return {
        ...audio,
        start: parseFloat(aStart.toFixed(2)),
        end: parseFloat(aEnd.toFixed(2)),
        trimStart: parseFloat(aTrimStart.toFixed(2)),
        trimEnd: aTrimEnd,
        duration: aDur
      };
    });

    if (cleanedAudioClips.length > 0) {
      tracks.push({
        type: 'audio',
        name: 'Audio Track',
        clips: cleanedAudioClips
      });
    }
    
    // Text track (when text overlays exist)
    if (editorState.text_overlays && editorState.text_overlays.length > 0) {
      tracks.push({
        type: 'text',
        name: 'Text Track',
        clips: editorState.text_overlays
      });
    }

    return {
      tracks: tracks,
      clips: editorState.video_clips,
      video_clips: editorState.video_clips,
      background_audios: cleanedAudioClips,
      text_overlays: editorState.text_overlays,
      trim: editorState.trim,
      speed: editorState.speed,
      audio: {
        volume: editorState.volume,
        muted: Boolean(editorState.userMuted),
      },
      audio_deleted_by_user: Boolean(editorState.audio_deleted_by_user),
      audio_separated: Boolean(editorState.audio_separated),
      resize: editorState.resize,
      effects: {
        grayscale: editorState.grayscale,
        rotate: editorState.rotate,
        fade: editorState.fade,
      },
      exportResolution: editorState.exportResolution || '1080p',
      exportQuality: editorState.exportQuality || 'high',
      version: '2.0',
      lastModified: new Date().toISOString()
    };
  }

  async function autoSaveTimeline() {
    if (!window.REEL_PROJECT_SAVE_TIMELINE_URL) return;
    const payload = buildTimelinePayload();

    try {
      const csrf = window.REEL_CSRF_TOKEN || document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
      const response = await fetch(window.REEL_PROJECT_SAVE_TIMELINE_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify(payload),
      });
      
      if (response.ok) {
        const result = await response.json();
        // Update track count badge if needed
        if (result.tracks_count != null && window.dynamicTrackManager) {
          window.dynamicTrackManager.updateTrackBadge();
        }
      }
    } catch (err) {
      console.warn("Failed to auto-save timeline:", err);
    }
  }

  // Explicitly bind shared variables and helpers to window
  window.editorState = editorState;
  window.duration = duration;
  window.timelineCurrentTime = timelineCurrentTime;
  window.basePxPerSecond = basePxPerSecond;
  window.zoomFactor = zoomFactor;
  window.formatTime = formatTime;
  window.sourceToTimelineTime = sourceToTimelineTime;
  window.timelineToSourceTime = timelineToSourceTime;
  window.buildTimelinePayload = buildTimelinePayload;
  window.autoSaveTimeline = autoSaveTimeline;
  window.hideSnapGuide = hideSnapGuide;
  window.getSecondsFromX = getSecondsFromX;
  window.syncVideoElementToTimeline = syncVideoElementToTimeline;

