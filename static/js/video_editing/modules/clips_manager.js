/**
 * Video Editor Module — Clip Splitting, Visual Trim & Ripple Edit
 */
  // ---- Visual Trim & Custom Player Controls Implementation -----------
  var video = video || document.getElementById("main-video");
  const startInput = document.getElementById("id_start_seconds");
  const endInput = document.getElementById("id_end_seconds");
  const trimContainer = document.getElementById("visual-trim-container");

  if (video && trimContainer) {
    const trimRuler = document.getElementById("trim-ruler");
    const trimTrack = document.getElementById("trim-track");
    const clipBlocksContainer = document.getElementById("timeline-clip-blocks");
    const trimThumbnails = document.getElementById("trim-thumbnails");
    const trimDimLeft = document.getElementById("trim-dim-left");
    const trimDimRight = document.getElementById("trim-dim-right");
    const trimSelection = document.getElementById("trim-selection");
    const handleLeft = document.getElementById("trim-handle-left");
    const handleRight = document.getElementById("trim-handle-right");
    const trimPlayhead = document.getElementById("trim-playhead");
    const currentDisplay = document.getElementById("time-display-current") || document.getElementById("video-time-current");
    const totalDisplay = document.getElementById("time-display-total");

    // Player Controls elements
    const btnSkipStart = document.getElementById("btn-skip-start");
    const btnBack5 = document.getElementById("btn-back-5");
    const btnPlayPause = document.getElementById("btn-play-pause");
    const btnForward5 = document.getElementById("btn-forward-5");
    const btnSkipEnd = document.getElementById("btn-skip-end");
    const btnFullscreen = document.getElementById("btn-fullscreen");

    // Zoom elements
    const btnZoomIn = document.getElementById("tb-zoom-in");
    const btnZoomOut = document.getElementById("tb-zoom-out");
    const btnZoomFit = document.getElementById("tb-zoom-fit");

    duration = 0;
    let startSeconds = 0;
    let endSeconds = 0;
    zoomFactor = 1.0;
    basePxPerSecond = 15;

    function getSnapPoints(excludePoint = null) {
      const points = [0, duration || 0];
      (editorState.video_clips || []).forEach((c) => {
        if (c.start !== undefined) points.push(c.start);
        if (c.end !== undefined) points.push(c.end);
      });
      (editorState.background_audios || []).forEach((a) => {
        if (a.start !== undefined) points.push(a.start);
        if (a.end !== undefined) points.push(a.end);
      });
      (editorState.text_overlays || []).forEach((t) => {
        if (t.start !== undefined) points.push(t.start);
        if (t.end !== undefined) points.push(t.end);
      });
      return points;
    }

    snapTimeToPoints = function (time, thresholdPx = 10) {
      const pxPerSec = basePxPerSecond * zoomFactor;
      const thresholdSec = thresholdPx / Math.max(1, pxPerSec);
      const points = getSnapPoints();
      const snapGuide = document.getElementById("timeline-snap-guide");

      for (let i = 0; i < points.length; i++) {
        const pt = points[i];
        if (Math.abs(time - pt) <= thresholdSec) {
          if (snapGuide) {
            snapGuide.style.display = "block";
            snapGuide.style.left = `${pt * pxPerSec}px`;
          }
          return { time: pt, snapped: true };
        }
      }
      if (snapGuide) snapGuide.style.display = "none";
      return { time, snapped: false };
    };

    hideSnapGuide = function () {
      const snapGuide = document.getElementById("timeline-snap-guide");
      if (snapGuide) snapGuide.style.display = "none";
    };

    // --- Client-side Accumulative State ---
    editorState = {
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

    // Load server state if available
    if (window.REEL_PROJECT_TIMELINE_STATE) {
      const state = window.REEL_PROJECT_TIMELINE_STATE;
      if (state.speed) editorState.speed = state.speed;
      if (state.audio) {
        if (state.audio.volume !== undefined) editorState.volume = state.audio.volume;
        if (state.audio.muted !== undefined) {
          editorState.muted = state.audio.muted;
          editorState.userMuted = state.audio.muted;
        }
      }
      if (state.text_overlays) editorState.text_overlays = state.text_overlays;
      if (state.background_audios) editorState.background_audios = state.background_audios;
      if (state.audio_deleted_by_user !== undefined) editorState.audio_deleted_by_user = state.audio_deleted_by_user;
      if (state.resize) editorState.resize = state.resize;
      if (state.effects) {
        if (state.effects.grayscale !== undefined) editorState.grayscale = state.effects.grayscale;
        if (state.effects.rotate !== undefined) editorState.rotate = state.effects.rotate;
        if (state.effects.fade !== undefined) editorState.fade = state.effects.fade;
      }
      if (state.trim) {
        editorState.trim = state.trim;
      }
      if (state.clips && state.clips.length > 0) {
        editorState.video_clips = state.clips;
      } else if (state.video_clips && state.video_clips.length > 0) {
        editorState.video_clips = state.video_clips;
      } else if (state.tracks && Array.isArray(state.tracks)) {
        const vTrack = state.tracks.find((t) => t.type === "video");
        if (vTrack && vTrack.clips && vTrack.clips.length > 0) {
          editorState.video_clips = vTrack.clips;
        }
      }
      if (state.background_audios && state.background_audios.length > 0) {
        editorState.background_audios = state.background_audios;
      } else if (state.audio_clips && state.audio_clips.length > 0) {
        editorState.background_audios = state.audio_clips;
      } else if (state.tracks && Array.isArray(state.tracks)) {
        const aTrack = state.tracks.find((t) => t.type === "audio");
        if (aTrack && aTrack.clips && aTrack.clips.length > 0) {
          editorState.background_audios = aTrack.clips;
        }
      }
      if (state.text_overlays && state.text_overlays.length > 0) {
        editorState.text_overlays = state.text_overlays;
      } else if (state.tracks && Array.isArray(state.tracks)) {
        const tTrack = state.tracks.find((t) => t.type === "text");
        if (tTrack && tTrack.clips && tTrack.clips.length > 0) {
          editorState.text_overlays = tTrack.clips;
        }
      }
    }

    // Fallback if video_clips not initialized
    if (!editorState.video_clips || editorState.video_clips.length === 0) {
      const clipsData = window.REEL_PROJECT_CLIPS || [];
      if (clipsData && clipsData.length > 0) {
        editorState.video_clips = JSON.parse(JSON.stringify(clipsData));
      }
    }
    const initProjDur = parseFloat(window.REEL_PROJECT_DURATION) || 0;
    if ((!editorState.video_clips || editorState.video_clips.length === 0) && initProjDur > 0) {
      editorState.video_clips = [{
        title: "Main Video",
        name: "Main Video",
        start: 0.0,
        end: initProjDur,
        trimStart: 0.0,
        trimEnd: initProjDur,
        duration: initProjDur
      }];
    }

    function ensureOriginalAudioTrackClip() {
      if (editorState.audio_deleted_by_user) return;
      const hasOriginalAudio = window.REEL_PROJECT_HAS_AUDIO &&
        (window.REEL_PROJECT_HAS_AUDIO === "True" ||
         window.REEL_PROJECT_HAS_AUDIO === "true" ||
         window.REEL_PROJECT_HAS_AUDIO === true);
      const curDur = (typeof duration !== "undefined" && duration > 0)
        ? duration
        : ((typeof window.duration !== "undefined" && window.duration > 0)
          ? window.duration
          : (parseFloat(window.REEL_PROJECT_DURATION) || 0));
      if (hasOriginalAudio && curDur > 0) {
        if (!editorState.background_audios) {
          editorState.background_audios = [];
        }
        const videoEl = document.getElementById("main-video");
        const videoSrc = (videoEl ? (videoEl.currentSrc || videoEl.src) : "") || window.REEL_PROJECT_PROXY_URL || "";
        
        // If we are in "linked mode" (audio not separated/dragged), 
        // we must ensure the background_audios array exactly matches the video_clips array structure.
        if (!editorState.audio_separated) {
          const vClips = editorState.video_clips || [];
          if (vClips.length > 0) {
            // Re-map background audios to match video clips one-to-one
            editorState.background_audios = vClips.map((vc, i) => {
              // Try to preserve existing audio clip if it was already detached but not dragged
              const existing = (editorState.background_audios && editorState.background_audios[i]) || {};
              const isImage = !!vc.isImage;
              return {
                ...existing,
                name: isImage ? `Silence (Image ${i + 1})` : `Audio Track (A${i + 1})`,
                filename: isImage ? `Silence (Image ${i + 1})` : `Audio Track (A${i + 1})`,
                start: vc.start,
                end: vc.end,
                trimStart: vc.trimStart != null ? vc.trimStart : 0,
                trimEnd: vc.trimEnd != null ? vc.trimEnd : vc.duration,
                duration: vc.duration,
                bg_volume: isImage ? 0.0 : (existing.bg_volume !== undefined ? existing.bg_volume : 1.0),
                video_volume: isImage ? 0.0 : (existing.video_volume !== undefined ? existing.video_volume : 1.0),
                is_detached: true,
                url: isImage ? "" : (existing.url || videoSrc)
              };
            });
          } else if (editorState.background_audios.length === 0) {
            editorState.background_audios.push({
              name: "Audio Track (A1)",
              filename: "Audio Track (A1)",
              start: 0,
              end: curDur,
              trimStart: 0,
              trimEnd: curDur,
              duration: curDur,
              bg_volume: 1.0,
              video_volume: 1.0,
              is_detached: true,
              url: videoSrc
            });
          }
        } else {
          // In separated mode, just ensure URLs are valid for detached clips
          editorState.background_audios.forEach(ac => {
            if (ac.is_detached && !ac.url && videoSrc) {
              ac.url = videoSrc;
            }
          });
        }
      }
    }

    recalculateVideoClipsTimeline = function () {
      let acc = 0.0;
      const clips = editorState.video_clips || [];
      
      if (clips.length > 0) {
        clips.forEach(clip => {
          const trimStart = parseFloat(clip.trimStart !== undefined ? clip.trimStart : 0.0);
          let trimEnd = parseFloat(clip.trimEnd !== undefined ? clip.trimEnd : (clip.duration ? trimStart + parseFloat(clip.duration) : trimStart));
          if (trimEnd <= trimStart) {
            trimEnd = trimStart + (parseFloat(clip.duration) || 1.0);
          }
          const dur = trimEnd - trimStart;
          clip.trimStart = trimStart;
          clip.trimEnd = trimEnd;
          clip.duration = dur;
          clip.start = acc;
          clip.end = acc + dur;
          acc += dur;
        });
        duration = acc;
        window.duration = acc;
      } else {
        // Fallback to project duration if no clips
        const projDur = parseFloat(window.REEL_PROJECT_DURATION) || 0;
        duration = projDur;
        window.duration = projDur;
        acc = projDur;
      }

      startSeconds = 0;
      endSeconds = duration || 0;
      ensureOriginalAudioTrackClip();

      // Keep linked detached original audio tracks synchronized with video clips
      if (editorState.background_audios && editorState.video_clips) {
        editorState.video_clips.forEach((vc, vIdx) => {
          const matchingAudio = editorState.background_audios[vIdx];
          if (matchingAudio && matchingAudio.is_detached && !matchingAudio.user_dragged) {
            matchingAudio.start = vc.start;
            matchingAudio.end = vc.end;
            matchingAudio.trimStart = vc.trimStart;
            matchingAudio.trimEnd = vc.trimEnd;
            matchingAudio.duration = vc.duration;
          }
        });
      }
    }
    recalculateVideoClipsTimeline();

    const prefillForms = () => {
      if (editorState.rotate) {
        const rotateInput = document.querySelector('form[action*="/rotate/"] #id_degrees, form[id="rotate-form"] #id_degrees');
        if (rotateInput) rotateInput.value = editorState.rotate;
      }
      if (editorState.resize) {
        const wInput = document.querySelector('form[action*="/resize/"] #id_width, form[id="resize-form"] #id_width');
        const hInput = document.querySelector('form[action*="/resize/"] #id_height, form[id="resize-form"] #id_height');
        if (wInput) wInput.value = editorState.resize.width;
        if (hInput) hInput.value = editorState.resize.height;
      }
      if (editorState.fade) {
        const finInput = document.querySelector('form[action*="/fade/"] #id_fade_in_seconds, form[id="fade-form"] #id_fade_in_seconds');
        const foutInput = document.querySelector('form[action*="/fade/"] #id_fade_out_seconds, form[id="fade-form"] #id_fade_out_seconds');
        if (finInput) finInput.value = editorState.fade.in;
        if (foutInput) foutInput.value = editorState.fade.out;
      }
      if (editorState.speed) {
        const speedDropdown = document.getElementById("speed-dropdown");
        const spdStr = editorState.speed.toString();
        if (speedDropdown && speedDropdown.options && Array.from(speedDropdown.options).some((o) => o.value === spdStr)) {
          speedDropdown.value = spdStr;
        }
      }
    };

    // UI helper to update CSS filters on the video player
    const applyCSSEffects = () => {
      video.style.filter = "";
      video.style.transform = "";

      // Playback speed and volume
      video.playbackRate = editorState.speed || 1.0;
      video.volume =
        editorState.volume !== undefined ? editorState.volume : 1.0;
    };

    // Add item to custom edit history list
    const addHistoryItem = (type, description) => {
      const list = document.querySelector(".history-list");
      const emptyHint = document.querySelector(
        ".ve-history-drawer-body .muted-text, .history-panel .muted-text",
      );
      if (emptyHint) {
        const hintBox = emptyHint.closest("div") || emptyHint;
        hintBox.remove();
      }

      let ul = list;
      if (!ul) {
        ul = document.createElement("ul");
        ul.className = "history-list";
        ul.style.cssText =
          "list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 12px;";
        const panel = document.querySelector(
          ".ve-history-drawer-body, .history-panel",
        );
        if (panel) {
          panel.appendChild(ul);
        }
      }

      if (ul) {
        const li = document.createElement("li");
        li.style.cssText =
          "display: flex; flex-direction: column; gap: 12px; padding: 16px; background: var(--ve-bg); border: 1px solid var(--ve-border); border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);";
        li.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
            <div style="display: flex; gap: 10px; align-items: flex-start; min-width: 0;">
              <span class="history-tag" style="background: var(--ve-primary); color: white; padding: 4px 8px; font-size: 11px; font-weight: 700; border-radius: 6px; text-transform: uppercase;">${type}</span>
              <span class="history-desc" style="font-weight: 500; font-size: 14px; color: var(--ve-text); line-height: 1.4;">${description}</span>
            </div>
            <span class="history-time" style="font-size: 12px; color: var(--ve-text-muted); white-space: nowrap;">Just now</span>
          </div>
          <div style="display: flex; justify-content: flex-end; align-items: center; border-top: 1px solid var(--ve-border); padding-top: 12px; margin-top: 4px;">
            <button type="button" class="history-revert-btn ve-btn" style="padding: 6px 14px; font-size: 12px; height: auto; background: var(--ve-bg-secondary); color: var(--ve-text); border: 1px solid var(--ve-border); border-radius: 6px; font-weight: 600; cursor: pointer;">Undo</button>
          </div>
        `;

        const revertBtn = li.querySelector(".history-revert-btn");
        if (revertBtn) {
          revertBtn.addEventListener("click", () => {
            revertStateChange(type, description);
            autoSaveTimeline();
            li.remove();
            const undoBtn = document.getElementById("tb-undo");
            if (undoBtn) {
              const remaining = ul.querySelectorAll(".history-revert-btn");
              if (!remaining || remaining.length === 0) {
                undoBtn.setAttribute("disabled", "true");
              }
            }
          });
        }

        ul.insertBefore(li, ul.firstChild);
        const undoBtn = document.getElementById("tb-undo");
        if (undoBtn) undoBtn.removeAttribute("disabled");
      }
    };

    window.updateLocalState = (type, description) => {
      if (type === "Speed") {
        const form = document.querySelector('form[action*="/speed/"]');
        if (form) {
          editorState.speed =
            parseFloat(form.querySelector("#id_speed_factor").value) || 1.0;
        }
        applyCSSEffects();
      } else if (type === "Volume") {
        const form = document.querySelector('form[action*="/volume/"]');
        if (form) {
          editorState.volume =
            parseFloat(form.querySelector("#id_volume_factor").value) || 1.0;
        }
        applyCSSEffects();
      } else if (type === "Mute") {
        editorState.muted = true;
        editorState.userMuted = true;
        video.muted = true;
        editorState.volume = 0;
        if (typeof syncVolumeUI === "function") syncVolumeUI();
        applyCSSEffects();
      }
      addHistoryItem(type, description);
      autoSaveTimeline();
    };

    const revertStateChange = (type, description) => {
      if (type === "Volume") {
        editorState.volume = 1.0;
        video.volume = 1.0;
      } else if (type === "Mute") {
        editorState.muted = false;
        editorState.userMuted = false;
        video.muted = false;
        if (typeof syncVolumeUI === "function") syncVolumeUI();
      } else if (type === "Speed") {
        editorState.speed = 1.0;
        video.defaultPlaybackRate = 1.0;
        video.playbackRate = 1.0;
      } else if (type === "Text") {
        const cleanDesc = description.replace('Caption: "', "").slice(0, -1);
        const idx = editorState.text_overlays.findIndex(
          (o) => o.text === cleanDesc || description === "Added text overlay",
        );
        if (idx !== -1) {
          editorState.text_overlays.splice(idx, 1);
          renderTextOverlays();
        }
      }
    };

    // --- Clips and Split points logic ---
    let splitPoints = [];
    selectedClipIndex = -1;

    function getClips() {
      let clips = [];
      let lastT = 0;
      const sortedSplits = [...splitPoints].sort((a, b) => a - b);
      for (let i = 0; i < sortedSplits.length; i++) {
        let t = sortedSplits[i];
        if (t > lastT && t < duration) {
          clips.push({ start: lastT, end: t });
          lastT = t;
        }
      }
      if (lastT < duration) {
        clips.push({ start: lastT, end: duration });
      }
      return clips;
    }

    function renderSplitMarkers() {
      const tracksWrapper = document.querySelector(".timeline-tracks-wrapper");
      if (!tracksWrapper) return;

      // Remove existing split markers
      tracksWrapper
        .querySelectorAll(".trim-split-marker")
        .forEach((el) => el.remove());

      const pxPerSecond = basePxPerSecond * zoomFactor;
      const vClips = editorState.video_clips || [];
      const splits = vClips.length > 1
        ? vClips.slice(1).map((c) => c.start)
        : splitPoints;

      splits.forEach((t) => {
        const el = document.createElement("div");
        el.className = "trim-split-marker";
        el.style.left = `${t * pxPerSecond}px`;
        tracksWrapper.appendChild(el);
      });
    }

    // Click on the video track to select a segment
    if (trimTrack) {
      trimTrack.addEventListener("click", (e) => {
        // Only select video clip if clicking directly on a video clip block
        if (!e.target.closest(".timeline-clip-block")) {
          return;
        }
        const t = getSecondsFromX(e.clientX);
        const clips = editorState.video_clips || [];
        const index = clips.findIndex((c) => t >= c.start && t <= c.end);
        if (index !== -1) {
          selectedClipIndex = index;
          const clip = clips[index];
          selectTimelineItem("video", index, {
            start: clip.start,
            end: clip.end,
            name: clip.name || `Clip ${index + 1}`,
          });
          video.currentTime = timelineToSourceTime(clip.start);
        }
      });
    }

    function splitSelectedTimelineItem() {
      const curT = parseFloat(sourceToTimelineTime(video.currentTime).toFixed(2));
      if (!Number.isFinite(curT) || curT <= 0.05 || curT >= duration - 0.05) return;

      // Auto-target video track if no track is explicitly selected
      if (!globalSelection.track) {
        const clips = editorState.video_clips || [];
        const foundIdx = clips.findIndex((c) => curT > (c.start || 0) + 0.1 && curT < (c.end || duration) - 0.1);
        if (foundIdx !== -1) {
          globalSelection = { track: "video", index: foundIdx };
        } else if (clips.length > 0) {
          globalSelection = { track: "video", index: 0 };
        } else {
          return;
        }
      }

      if (globalSelection.track === "video") {
        const index = globalSelection.index;
        const clip = editorState.video_clips?.[index];
        if (
          !clip ||
          curT <= (clip.start || 0) + 0.05 ||
          curT >= (clip.end || duration) - 0.05
        )
          return;

        const relativeSplitOffset = curT - clip.start;
        const originalDuration = clip.duration;
        const originalTrimStart = parseFloat(clip.trimStart || 0.0);

        clip.duration = relativeSplitOffset;
        clip.trimEnd = originalTrimStart + relativeSplitOffset;

        const newClip = JSON.parse(JSON.stringify(clip));
        newClip.duration = originalDuration - relativeSplitOffset;
        newClip.trimStart = originalTrimStart + relativeSplitOffset;
        newClip.trimEnd = originalTrimStart + originalDuration;
        newClip.name = `${clip.name || 'Clip'} 2`;

        editorState.video_clips.splice(index + 1, 0, newClip);

        // Also split detached original audio at the same position so audio and video stay 1:1 in sync
        if (editorState.background_audios && editorState.background_audios.length > 0) {
          const aIdx = editorState.background_audios.findIndex(
            (a) => a.is_detached && curT > (a.start || 0) + 0.05 && curT < (a.end || duration) - 0.05
          );
          if (aIdx !== -1) {
            const aItem = editorState.background_audios[aIdx];
            const aRel = curT - aItem.start;
            const aOrigEnd = aItem.end;
            const aOrigTrimStart = parseFloat(aItem.trimStart || 0.0);
            const aOrigTrimEnd = parseFloat(aItem.trimEnd || (aOrigTrimStart + (aOrigEnd - aItem.start)));

            aItem.end = curT;
            aItem.duration = parseFloat((curT - aItem.start).toFixed(2));
            aItem.trimEnd = aOrigTrimStart + aRel;

            const newAItem = JSON.parse(JSON.stringify(aItem));
            newAItem.start = curT;
            newAItem.end = aOrigEnd;
            newAItem.duration = parseFloat((aOrigEnd - curT).toFixed(2));
            newAItem.trimStart = aOrigTrimStart + aRel;
            newAItem.trimEnd = aOrigTrimEnd;

            editorState.background_audios.splice(aIdx + 1, 0, newAItem);
          }
        }
        
        recalculateVideoClipsTimeline();
        selectedClipIndex = index + 1;
        selectTimelineItem("video", index + 1, {
          start: newClip.start,
          end: newClip.end,
          name: newClip.name,
        });

        _lastClipRenderKey = "";
        renderClipBlocks();
        renderAllTimelineTracks();
        updateRuler();
        renderTrim();
        generateThumbnails();
        updateVideoProgress();
        autoSaveTimeline();

        if (window.updateLocalState)
          window.updateLocalState("Video", "Split video clip");
        return;
      }

      if (globalSelection.track === "audio") {
        const items = editorState.background_audios || [];
        const index = globalSelection.index;
        const item = items[index];
        if (!item || curT <= (item.start || 0) || curT >= (item.end || duration)) return;

        const relOffset = curT - item.start;
        const origEnd = item.end;
        const origTrimStart = parseFloat(item.trimStart || 0.0);
        const origTrimEnd = parseFloat(item.trimEnd || (origTrimStart + (origEnd - item.start)));

        // Update first part of audio clip
        item.end = curT;
        item.trimStart = origTrimStart;
        item.trimEnd = origTrimStart + relOffset;

        // Create second part of audio clip
        const newItem = JSON.parse(JSON.stringify(item));
        newItem.start = curT;
        newItem.end = origEnd;
        newItem.trimStart = origTrimStart + relOffset;
        newItem.trimEnd = origTrimEnd;

        items.splice(index + 1, 0, newItem);
        clearGlobalSelection();

        renderClipBlocks();
        renderAllTimelineTracks();
        updateRuler();
        renderTrim();
        generateThumbnails();
        if (typeof renderAudioOverlay === "function") {
          renderAudioOverlay();
        }
        updateVideoProgress();
        autoSaveTimeline();

        if (window.updateLocalState)
          window.updateLocalState("audio", "Split audio clip");
        return;
      }

      const config = TRACK_CONFIG[globalSelection.track];
      if (!config) return;

      const items = editorState[config.stateKey] || [];
      const item = items[globalSelection.index];
      if (!item || curT <= (item.start || 0) || curT >= (item.end || duration))
        return;

      const newItem = JSON.parse(JSON.stringify(item));
      item.end = curT;
      newItem.start = curT;
      items.splice(globalSelection.index + 1, 0, newItem);
      clearGlobalSelection();

      renderClipBlocks();
      renderAllTimelineTracks();
      updateRuler();
      renderTrim();
      generateThumbnails();
      if (typeof renderAudioOverlay === "function") {
        renderAudioOverlay();
      }
      if (typeof renderTextOverlays === "function") {
        renderTextOverlays();
      }
      autoSaveTimeline();
      updateVideoProgress();

      if (window.updateLocalState)
        window.updateLocalState(globalSelection.track, "Split item");
    }

    function duplicateSelectedTimelineItem() {
      // Auto-target video track if no track is explicitly selected
      if (!globalSelection.track) {
        const clips = editorState.video_clips || [];
        const curT = parseFloat(sourceToTimelineTime(video.currentTime).toFixed(2));
        const idx = clips.findIndex((c) => curT >= (c.start || 0) && curT <= (c.end || duration));
        if (idx !== -1) {
          globalSelection = { track: "video", index: idx };
        } else if (clips.length > 0) {
          globalSelection = { track: "video", index: 0 };
        } else {
          return;
        }
      }

      if (globalSelection.track === "video") {
        const index = globalSelection.index;
        const clip = editorState.video_clips?.[index];
        if (!clip) return;

        const newClip = JSON.parse(JSON.stringify(clip));
        newClip.name = `${clip.name || 'Clip'} (Copy)`;
        editorState.video_clips.splice(index + 1, 0, newClip);

        recalculateVideoClipsTimeline();
        selectedClipIndex = index + 1;
        selectTimelineItem("video", index + 1, {
          start: newClip.start,
          end: newClip.end,
          name: newClip.name,
        });

        _lastClipRenderKey = "";
        renderClipBlocks();
        renderAllTimelineTracks();
        updateRuler();
        renderTrim();
        generateThumbnails();
        updateVideoProgress();
        autoSaveTimeline();

        if (window.updateLocalState)
          window.updateLocalState("Video", "Duplicated video clip");
        return;
      }

      if (globalSelection.track === "audio") {
        const items = editorState.background_audios || [];
        const index = globalSelection.index;
        const item = items[index];
        if (!item) return;

        const newItem = JSON.parse(JSON.stringify(item));
        const dur = (item.end || duration) - (item.start || 0);
        newItem.start = parseFloat(((item.end || 0) + 0.1).toFixed(2));
        newItem.end = parseFloat((newItem.start + dur).toFixed(2));
        items.splice(index + 1, 0, newItem);

        clearGlobalSelection();
        renderClipBlocks();
        renderAllTimelineTracks();
        updateRuler();
        renderTrim();
        if (typeof renderAudioOverlay === "function") renderAudioOverlay();
        updateVideoProgress();
        autoSaveTimeline();

        if (window.updateLocalState)
          window.updateLocalState("audio", "Duplicated audio clip");
        return;
      }

      if (globalSelection.track === "text") {
        const items = editorState.text_overlays || [];
        const index = globalSelection.index;
        const item = items[index];
        if (!item) return;

        const newItem = JSON.parse(JSON.stringify(item));
        const dur = (item.end || duration) - (item.start || 0);
        newItem.start = parseFloat(((item.end || 0) + 0.1).toFixed(2));
        newItem.end = parseFloat((newItem.start + dur).toFixed(2));
        items.splice(index + 1, 0, newItem);

        clearGlobalSelection();
        renderTextOverlays();
        renderAllTimelineTracks();
        updateVideoProgress();
        autoSaveTimeline();

        if (window.updateLocalState)
          window.updateLocalState("text", "Duplicated text overlay");
        return;
      }
    }

    function mergeSelectedTimelineItem() {
      if (!globalSelection.track) {
        const clips = editorState.video_clips || [];
        if (clips.length > 1) {
          const curT = parseFloat(sourceToTimelineTime(video.currentTime).toFixed(2));
          const idx = clips.findIndex((c) => curT >= (c.start || 0) && curT <= (c.end || duration));
          if (idx !== -1) {
            globalSelection = { track: "video", index: idx };
          } else {
            globalSelection = { track: "video", index: 0 };
          }
        }
      }
      if (!globalSelection.track) return;

      if (globalSelection.track === "video") {
        const clips = editorState.video_clips || [];
        if (clips.length < 2) {
          console.log("Need at least 2 clips to merge");
          return;
        }

        let idx = globalSelection.index >= 0 ? globalSelection.index : 0;
        let idx1 = idx;
        let idx2 = idx + 1;
        if (idx2 >= clips.length) {
          idx1 = idx - 1;
          idx2 = idx;
        }

        const clip1 = clips[idx1];
        const clip2 = clips[idx2];
        if (!clip1 || !clip2) return;

        const sameSource = (!clip1.url && !clip2.url) || (clip1.url === clip2.url);
        const trimContiguous = Math.abs((clip1.trimEnd || 0) - (clip2.trimStart || 0)) < 0.25;

        if (sameSource && trimContiguous) {
          clip1.trimEnd = clip2.trimEnd;
          clip1.duration = parseFloat((clip1.trimEnd - clip1.trimStart).toFixed(2));
          clip1.name = (clip1.name || "Clip").replace(/ (2|\(Copy\))$/g, "").trim() || clip1.name;
        } else {
          clip1.duration = parseFloat(((clip1.duration || 0) + (clip2.duration || 0)).toFixed(2));
          clip1.trimEnd = parseFloat(((clip1.trimStart || 0) + clip1.duration).toFixed(2));
          clip1.name = `${clip1.name || "Clip 1"} + ${clip2.name || "Clip 2"}`;
        }

        clips.splice(idx2, 1);

        // Also merge adjacent detached audio clips if present at the same time
        if (editorState.background_audios && editorState.background_audios.length > 1) {
          const aClips = editorState.background_audios;
          const aIdx = aClips.findIndex(a => Math.abs((a.start || 0) - (clip1.start || 0)) < 0.25);
          if (aIdx !== -1 && aIdx + 1 < aClips.length) {
            const a1 = aClips[aIdx];
            const a2 = aClips[aIdx + 1];
            if (a1.is_detached && a2.is_detached) {
              a1.trimEnd = a2.trimEnd;
              a1.end = a2.end;
              aClips.splice(aIdx + 1, 1);
            }
          }
        }

        recalculateVideoClipsTimeline();
        selectedClipIndex = idx1;
        selectTimelineItem("video", idx1, clip1);

        _lastClipRenderKey = "";
        renderClipBlocks();
        renderAllTimelineTracks();
        updateRuler();
        renderTrim();
        generateThumbnails();
        updateVideoProgress();
        autoSaveTimeline();

        if (window.updateLocalState) {
          window.updateLocalState("Video", "Merged video clips");
        }
        return;
      }

      if (globalSelection.track === "audio") {
        const aClips = editorState.background_audios || [];
        if (aClips.length < 2) return;
        let idx = globalSelection.index >= 0 ? globalSelection.index : 0;
        let idx1 = idx < aClips.length - 1 ? idx : idx - 1;
        let idx2 = idx1 + 1;
        const a1 = aClips[idx1];
        const a2 = aClips[idx2];
        if (a1 && a2) {
          a1.trimEnd = a2.trimEnd;
          a1.end = a2.end;
          aClips.splice(idx2, 1);
          clearGlobalSelection();
          renderClipBlocks();
          renderAllTimelineTracks();
          updateRuler();
          renderTrim();
          if (typeof renderAudioOverlay === "function") renderAudioOverlay();
          updateVideoProgress();
          autoSaveTimeline();
          if (window.updateLocalState) window.updateLocalState("audio", "Merged audio clips");
        }
      }
    }

    function deleteSelectedTimelineItem() {
      if (!globalSelection.track) {
        const clips = editorState.video_clips || [];
        if (clips.length > 1) {
          const curT = parseFloat(sourceToTimelineTime(video.currentTime).toFixed(2));
          const idx = clips.findIndex((c) => curT >= (c.start || 0) && curT <= (c.end || duration));
          if (idx !== -1) {
            globalSelection = { track: "video", index: idx };
          }
        }
      }
      if (!globalSelection.track) return;

      if (globalSelection.track === "video") {
        const deletedClip = editorState.video_clips?.[globalSelection.index];
        const deletedStart = deletedClip ? (deletedClip.start || 0) : 0;
        const deletedDuration = deletedClip ? (deletedClip.duration || 0) : 0;
        editorState.video_clips?.splice(globalSelection.index, 1);
        
        if (deletedClip && editorState.background_audios && editorState.background_audios.length > 0) {
          const aIdx = editorState.background_audios.findIndex(
            (a) => a.is_detached && Math.abs((a.start || 0) - deletedStart) < 0.2
          );
          if (aIdx !== -1) {
            editorState.background_audios.splice(aIdx, 1);
          }
          // Shift subsequent detached audio clips left by deletedDuration so video & audio remain 1:1 in sync
          if (deletedDuration > 0) {
            editorState.background_audios.forEach((a) => {
              if (a.is_detached && (a.start || 0) >= deletedStart) {
                a.start = Math.max(0, parseFloat(((a.start || 0) - deletedDuration).toFixed(2)));
                a.end = Math.max(a.start, parseFloat(((a.end || 0) - deletedDuration).toFixed(2)));
                a.duration = Math.max(0.01, parseFloat((a.end - a.start).toFixed(2)));
              }
            });
          }
        }
        
        recalculateVideoClipsTimeline();
        clearGlobalSelection();

        _lastClipRenderKey = "";
        renderClipBlocks();
        renderAllTimelineTracks();
        updateRuler();
        renderTrim();
        generateThumbnails();
        updateVideoProgress();
        autoSaveTimeline();

        if (window.updateLocalState)
          window.updateLocalState("Video", "Deleted video clip");
        return;
      }

      if (globalSelection.track === "audio") {
        if (!editorState.audio_separated && editorState.video_clips && editorState.video_clips[globalSelection.index]) {
          // CapCut / Canva Linked Mode: Deleting linked audio also deletes the linked video clip!
          globalSelection.track = "video";
          deleteSelectedTimelineItem();
          return;
        }
        // CapCut Separated Mode: Delete ONLY audio clip, leaving an empty gap on audio track
        editorState.background_audios?.splice(globalSelection.index, 1);
        if (!editorState.background_audios || editorState.background_audios.length === 0) {
          editorState.audio_deleted_by_user = true;
        }
        clearGlobalSelection();

        renderClipBlocks();
        renderAllTimelineTracks();
        updateRuler();
        renderTrim();
        generateThumbnails();
        if (typeof renderAudioOverlay === "function") {
          renderAudioOverlay();
        }
        updateVideoProgress();
        if (typeof syncAudioPreviewToTimeline === "function") {
          syncAudioPreviewToTimeline(timelineCurrentTime || 0, true);
        }
        autoSaveTimeline();

        if (window.updateLocalState)
          window.updateLocalState("audio", "Deleted audio clip");
        return;
      }

      if (globalSelection.track === "text") {
        const items = editorState.text_overlays || [];
        if (globalSelection.index >= 0 && globalSelection.index < items.length) {
          items.splice(globalSelection.index, 1);
        }
        clearGlobalSelection();
        const editorCard = document.getElementById("ve-text-editor-card");
        if (editorCard) editorCard.style.display = "none";

        renderClipBlocks();
        renderAllTimelineTracks();
        updateRuler();
        renderTrim();
        generateThumbnails();
        if (typeof renderTextOverlays === "function") {
          renderTextOverlays();
        }
        if (typeof updateToolbarActionButtons === "function") {
          updateToolbarActionButtons();
        }
        autoSaveTimeline();
        updateVideoProgress();

        if (window.updateLocalState)
          window.updateLocalState("text", "Deleted text overlay");
        return;
      }

      const config = TRACK_CONFIG[globalSelection.track];
      if (!config) return;

      const items = editorState[config.stateKey] || [];
      items.splice(globalSelection.index, 1);
      clearGlobalSelection();

      renderClipBlocks();
      renderAllTimelineTracks();
      updateRuler();
      renderTrim();
      generateThumbnails();
      if (typeof renderAudioOverlay === "function") {
        renderAudioOverlay();
      }
      if (typeof renderTextOverlays === "function") {
        renderTextOverlays();
      }
      if (typeof updateToolbarActionButtons === "function") {
        updateToolbarActionButtons();
      }
      autoSaveTimeline();
      updateVideoProgress();

      if (window.updateLocalState)
        window.updateLocalState(globalSelection.track, "Deleted item");
    }

    // Split button click
    const splitBtn = document.getElementById("tb-split");
    if (splitBtn) {
      splitBtn.addEventListener("click", splitSelectedTimelineItem);
    }

    window.recalculateVideoClipsTimeline = recalculateVideoClipsTimeline;
    window.snapTimeToPoints = snapTimeToPoints;
    window.hideSnapGuide = hideSnapGuide;
    window.splitSelectedTimelineItem = splitSelectedTimelineItem;
    window.deleteSelectedTimelineItem = deleteSelectedTimelineItem;
    window.duplicateSelectedTimelineItem = duplicateSelectedTimelineItem;
    window.mergeSelectedTimelineItem = mergeSelectedTimelineItem;
  }

    
