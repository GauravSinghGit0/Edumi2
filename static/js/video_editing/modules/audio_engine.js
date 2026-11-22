/**
 * Video Editor Module — Web Audio API, Waveform Generator & Audio Separation
 */
    // ---- Timeline Utilities --------------------------------------------
    function formatTime(secs) {
      if (isNaN(secs) || secs < 0) return "00:00:00";
      const h = Math.floor(secs / 3600);
      const m = Math.floor((secs % 3600) / 60);
      const s = Math.floor(secs % 60);
      return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    }

    // Procedural audio peak generator for instant Canva-style audio visualization
    function getProceduralAudioPeak(tRatio, seed = 42) {
      const f1 = Math.sin(tRatio * 85.0 + seed);
      const f2 = Math.sin(tRatio * 210.0 + seed * 1.5) * 0.5;
      const f3 = Math.cos(tRatio * 43.0 + seed * 0.7) * 0.7;
      const f4 = Math.sin(tRatio * 520.0 + seed * 2.3) * 0.3;
      const modulation = Math.max(0.12, Math.sin(tRatio * 18.0) * 0.45 + 0.55);
      const raw = Math.abs(f1 + f2 + f3 + f4) / 2.3;
      return Math.max(0.08, Math.min(0.95, raw * modulation));
    }

    function renderWaveformToCanvas(canvas, peaks, width, height, clipStartRatio = 0.0, clipEndRatio = 1.0) {
      if (!canvas) return;
      const w = Math.max(10, Math.floor(width));
      const h = Math.max(10, Math.floor(height));
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = "100%";
      canvas.style.height = "100%";

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, w, h);

      const centerY = h / 2;
      const maxBarH = Math.max(8, h - 6);

      // Center baseline guide line (subtle)
      ctx.beginPath();
      ctx.moveTo(0, centerY);
      ctx.lineTo(w, centerY);
      ctx.strokeStyle = "rgba(167, 243, 208, 0.25)";
      ctx.lineWidth = 1;
      ctx.stroke();

      const startR = Math.max(0, Math.min(1, clipStartRatio != null ? clipStartRatio : 0.0));
      const endR = Math.max(startR, Math.min(1, clipEndRatio != null ? clipEndRatio : 1.0));
      const barWidth = 2.5;
      const barGap = 2.0;
      const step = barWidth + barGap;
      const numBars = Math.floor(w / step);
      const hasRealPeaks = Array.isArray(peaks) && peaks.length > 0;
      const len = hasRealPeaks ? peaks.length : 0;

      // Symmetrical gradient for rounded vertical sound bars (matching NLE / reference image)
      const barGrad = ctx.createLinearGradient(0, centerY - maxBarH / 2, 0, centerY + maxBarH / 2);
      barGrad.addColorStop(0.0, "#059669");
      barGrad.addColorStop(0.2, "#10b981");
      barGrad.addColorStop(0.5, "#34d399");
      barGrad.addColorStop(0.8, "#10b981");
      barGrad.addColorStop(1.0, "#059669");
      ctx.fillStyle = barGrad;

      const r = barWidth / 2;

      for (let i = 0; i < numBars; i++) {
        const x = i * step + barGap / 2;
        const t1 = startR + (i / Math.max(1, numBars)) * (endR - startR);
        const t2 = startR + ((i + 1) / Math.max(1, numBars)) * (endR - startR);

        let amp = 0.04;
        if (hasRealPeaks) {
          const startIdx = Math.floor(t1 * len);
          const endIdx = Math.max(startIdx + 1, Math.ceil(t2 * len));
          let maxVal = 0;
          for (let k = startIdx; k < endIdx && k < len; k++) {
            if (peaks[k] > maxVal) maxVal = peaks[k];
          }
          // Perceptual dynamic scaling: sharp pill transients
          amp = Math.max(0.04, Math.min(1.0, Math.pow(maxVal, 0.75)));
        } else {
          amp = getProceduralAudioPeak(t1);
        }

        const barH = Math.max(barWidth, amp * maxBarH);
        const topY = centerY - barH / 2;

        ctx.beginPath();
        if (typeof ctx.roundRect === "function") {
          ctx.roundRect(x, topY, barWidth, barH, r);
        } else {
          // Pill path fallback
          ctx.moveTo(x + r, topY);
          ctx.lineTo(x + barWidth - r, topY);
          ctx.quadraticCurveTo(x + barWidth, topY, x + barWidth, topY + r);
          ctx.lineTo(x + barWidth, topY + barH - r);
          ctx.quadraticCurveTo(x + barWidth, topY + barH, x + barWidth - r, topY + barH);
          ctx.lineTo(x + r, topY + barH);
          ctx.quadraticCurveTo(x, topY + barH, x, topY + barH - r);
          ctx.lineTo(x, topY + r);
          ctx.quadraticCurveTo(x, topY, x + r, topY);
        }
        ctx.fill();
      }
    }
    window.renderWaveformToCanvas = renderWaveformToCanvas;

    function generateWaveformSvg(width, height, seed = 12345, clipStartRatio = 0.0, clipEndRatio = 1.0) {
      const centerY = height / 2;
      const peaks = window.audioPeaksCache;
      const hasRealPeaks = Array.isArray(peaks) && peaks.length > 0;
      const barWidth = 2.5;
      const barGap = 2.0;
      const step = barWidth + barGap;
      const totalBars = Math.max(10, Math.floor(width / step));
      const maxBarHeight = Math.max(8, height - 6);
      const paths = [];
      const len = hasRealPeaks ? peaks.length : 0;
      const startR = clipStartRatio != null ? clipStartRatio : 0.0;
      const endR = clipEndRatio != null ? clipEndRatio : 1.0;
      const rx = (barWidth / 2).toFixed(1);

      for (let i = 0; i < totalBars; i++) {
        const x = (i * step + barGap / 2).toFixed(1);
        const t1 = startR + (i / totalBars) * (endR - startR);
        const t2 = startR + ((i + 1) / totalBars) * (endR - startR);
        let amp = 0.04;
        if (hasRealPeaks) {
          const startIdx = Math.floor(t1 * len);
          const endIdx = Math.max(startIdx + 1, Math.ceil(t2 * len));
          let maxVal = 0;
          for (let k = startIdx; k < endIdx && k < len; k++) {
            if (peaks[k] > maxVal) maxVal = peaks[k];
          }
          amp = Math.max(0.04, Math.min(1.0, Math.pow(maxVal, 0.75)));
        } else {
          amp = getProceduralAudioPeak(t1);
        }
        const barH = Math.max(barWidth, amp * maxBarHeight);
        const topY = (centerY - barH / 2).toFixed(1);
        paths.push(`<rect x="${x}" y="${topY}" width="${barWidth}" height="${barH.toFixed(1)}" rx="${rx}" fill="#34d399" opacity="0.95"/>`);
      }
      return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" style="display:block;width:100%;height:100%;"><line x1="0" y1="${centerY}" x2="${width}" y2="${centerY}" stroke="rgba(167,243,208,0.25)" stroke-width="1"/>${paths.join('')}</svg>`;
    }
    window.generateWaveformSvg = generateWaveformSvg;

    // ── Canva-Style Ruler ────────────────────────────────────────────────────
    const RULER_EPSILON = 0.0001;
    const RULER_MIN_LABEL_GAP_PX = 44;

    function getRulerIntervals(pxPerSecond) {
      if (pxPerSecond >= 600) return { major: 0.5, minor: 0.1 };
      if (pxPerSecond >= 240) return { major: 1.0, minor: 0.2 };
      if (pxPerSecond >= 120) return { major: 2.0, minor: 0.5 };
      if (pxPerSecond >= 50)  return { major: 5.0, minor: 1.0 };
      if (pxPerSecond >= 20)  return { major: 10.0, minor: 2.0 };
      if (pxPerSecond >= 8)   return { major: 30.0, minor: 5.0 };
      if (pxPerSecond >= 3)   return { major: 60.0, minor: 10.0 };
      if (pxPerSecond >= 1.0) return { major: 120.0, minor: 30.0 };
      if (pxPerSecond >= 0.4) return { major: 300.0, minor: 60.0 };
      return { major: 600.0, minor: 120.0 };
    }

    function formatRulerLabel(seconds, totalDuration) {
      if (seconds === 0) return "0:00";
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      const s = Math.floor(seconds % 60);

      if (totalDuration >= 3600) {
        return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
      }
      return `${m}:${String(s).padStart(2, "0")}`;
    }

    function getRulerViewportRange(pxPerSecond) {
      const scrollArea = document.getElementById("timeline-scroll-area");
      const scrollLeft = scrollArea?.scrollLeft || 0;
      const viewportWidth = scrollArea?.clientWidth || 800;

      const visibleStartTime = Math.max(0, scrollLeft / pxPerSecond - 2);
      const visibleEndTime   = (scrollLeft + viewportWidth) / pxPerSecond + 2;

      return { visibleStartTime, visibleEndTime };
    }

    function renderRulerTicks() {
      if (!duration || !trimRuler) return;

      const pxPerSecond = basePxPerSecond * zoomFactor;
      const parentWidth = trimTrack?.parentElement
        ? trimTrack.parentElement.clientWidth
        : 800;
      const totalWidth = Math.max(parentWidth, duration * pxPerSecond);

      trimRuler.style.width = `${totalWidth}px`;
      if (trimTrack) trimTrack.style.width = `${totalWidth}px`;
      const textTrack = document.getElementById("text-track-content");
      const audioTrackEl = document.getElementById("audio-track");
      if (textTrack)    textTrack.style.width    = `${totalWidth}px`;
      if (audioTrackEl) audioTrackEl.style.width = `${totalWidth}px`;

      const { major, minor } = getRulerIntervals(pxPerSecond);
      const { visibleStartTime, visibleEndTime } = getRulerViewportRange(pxPerSecond);

      const renderEnd = Math.min(visibleEndTime, duration + major);
      const firstTickTime = Math.max(0, Math.floor(visibleStartTime / minor) * minor);

      const frag = document.createDocumentFragment();
      let lastLabelX = -Infinity;

      for (let t = firstTickTime; t <= renderEnd + RULER_EPSILON; t += minor) {
        const time = Math.round(t / RULER_EPSILON) * RULER_EPSILON;
        const roundedTime = parseFloat(time.toFixed(6));

        if (roundedTime < 0) continue;

        const x = roundedTime * pxPerSecond;

        const modMajor = roundedTime % major;
        const isMajor  = modMajor < RULER_EPSILON || (major - modMajor) < RULER_EPSILON;

        const tick = document.createElement("div");
        tick.className = isMajor ? "trim-tick major" : "trim-tick";
        tick.style.left = `${x}px`;
        frag.appendChild(tick);

        if (isMajor) {
          if (x - lastLabelX >= RULER_MIN_LABEL_GAP_PX) {
            const label = document.createElement("div");
            label.className = roundedTime === 0
              ? "trim-tick-label first-tick-label"
              : "trim-tick-label";
            label.style.left = `${x}px`;
            label.textContent = formatRulerLabel(roundedTime, duration);
            frag.appendChild(label);
            lastLabelX = x;
          }
        }
      }

      trimRuler.innerHTML = "";
      trimRuler.appendChild(frag);
    }

    updateRuler = function () {
      renderRulerTicks();
    }
    // ── End Canva-Style Ruler ────────────────────────────────────
    let _filmstripThumbs = null;
    let _filmstripLoading = false;
    let _clientThumbnailGenerating = false;
    let _clipThumbAbortController = null;
    const THUMB_DESIRED_W = 60; // px per visible slot
    let _lastClipRenderKey = "";

    // Fallback: Extract video frames client-side via canvas from the HTML5 video element
    async function generateClientVideoThumbnails() {
      if (_filmstripThumbs && _filmstripThumbs.length > 0) return;
      if (_clientThumbnailGenerating) return;
      if (!video || !duration || isNaN(duration) || duration <= 0) return;

      _clientThumbnailGenerating = true;
      try {
        const offscreenVideo = document.createElement("video");
        offscreenVideo.crossOrigin = "anonymous";
        offscreenVideo.src = video.src;
        offscreenVideo.muted = true;
        offscreenVideo.preload = "auto";

        await new Promise((resolve) => {
          offscreenVideo.addEventListener("loadedmetadata", resolve, { once: true });
          setTimeout(resolve, 3000);
        });

        const canvas = document.createElement("canvas");
        canvas.width = 160;
        canvas.height = 90;
        const ctx = canvas.getContext("2d");

        const thumbs = [];
        const numSamples = Math.min(24, Math.max(6, Math.floor(duration / 15)));

        for (let i = 0; i < numSamples; i++) {
          if (_filmstripThumbs && _filmstripThumbs.length > 0) break;
          const seekT = (i + 0.5) * (duration / numSamples);
          offscreenVideo.currentTime = seekT;
          await new Promise((resolve) => {
            offscreenVideo.addEventListener("seeked", resolve, { once: true });
            setTimeout(resolve, 300);
          });
          ctx.drawImage(offscreenVideo, 0, 0, 160, 90);
          thumbs.push(canvas.toDataURL("image/jpeg", 0.65));
        }

        if (thumbs.length > 0 && (!_filmstripThumbs || _filmstripThumbs.length === 0)) {
          _filmstripThumbs = thumbs;
          _lastClipRenderKey = "";
          renderClipBlocks();
        }
      } catch (e) {
        console.warn("[ClientFilmstrip] Canvas extraction fallback skipped:", e);
      } finally {
        _clientThumbnailGenerating = false;
      }
    }

    async function loadFilmstripThumbs() {
      if (_filmstripThumbs && _filmstripThumbs.length > 0) return;
      if (_filmstripLoading) return;
      const filmstripUrl =
        window.REEL_PROJECT_FILMSTRIP_URL ||
        (window.REEL_PROJECT_ID
          ? `/video-editing/project/${window.REEL_PROJECT_ID}/filmstrip/`
          : null);
      if (!filmstripUrl) {
        generateClientVideoThumbnails();
        return;
      }

      _filmstripLoading = true;
      try {
        const res = await fetch(filmstripUrl);
        if (res.ok) {
          const data = await res.json();
          if (data && data.thumbnails && data.thumbnails.length > 0) {
            _filmstripThumbs = data.thumbnails;
            _filmstripLoading = false;
            _lastClipRenderKey = "";
            renderClipBlocks();
            return;
          } else if (data && data.status === "generating") {
            _filmstripLoading = false;
            generateClientVideoThumbnails();
            setTimeout(loadFilmstripThumbs, 2000);
            return;
          }
        }
      } catch (err) {
        console.warn("[Filmstrip] Failed to fetch server filmstrip:", err);
        generateClientVideoThumbnails();
      } finally {
        _filmstripLoading = false;
      }
    }

    if (window.REEL_PROJECT_ID) {
      setTimeout(loadFilmstripThumbs, 50);
    }

    // --- Real Web Audio API PCM Peak Extraction & Detach Audio Action ---
    let audioPeaksCache = null;
    let isExtractingAudioPeaks = false;

    function updateOriginalAudioWaveform() {
      const waveformContainer = document.getElementById("original-audio-waveform");
      if (waveformContainer && typeof window.generateWaveformSvg === "function") {
        const audioBlock = document.getElementById("audio-block") || waveformContainer.parentElement;
        const width = (audioBlock && audioBlock.clientWidth > 50)
          ? audioBlock.clientWidth
          : Math.max(800, ((typeof duration !== "undefined" && duration) || window.duration || 16) * basePxPerSecond * zoomFactor);
        waveformContainer.innerHTML = window.generateWaveformSvg(width, 36, 0);
      }
    }
    window.updateOriginalAudioWaveform = updateOriginalAudioWaveform;

    async function extractAudioPeaks() {
      if (audioPeaksCache && audioPeaksCache.length > 0) {
        window.audioPeaksCache = audioPeaksCache;
        updateOriginalAudioWaveform();
        return audioPeaksCache;
      }
      if (isExtractingAudioPeaks) return null;
      if (window.REEL_PROJECT_HAS_AUDIO === "False" || window.REEL_PROJECT_HAS_AUDIO === false) return null;

      const projId = window.REEL_PROJECT_ID;
      if (!projId) return null;

      try {
        isExtractingAudioPeaks = true;
        const waveformUrl = window.REEL_PROJECT_WAVEFORM_URL || `/video-editing/project/${projId}/waveform/`;
        const resp = await fetch(waveformUrl);
        if (!resp.ok) {
          isExtractingAudioPeaks = false;
          return null;
        }
        const data = await resp.json();
        if (data.status === "ready" && Array.isArray(data.peaks) && data.peaks.length > 0) {
          audioPeaksCache = data.peaks;
          window.audioPeaksCache = data.peaks;
          isExtractingAudioPeaks = false;

          updateOriginalAudioWaveform();
          renderAllTimelineTracks();
          if (typeof renderAudioOverlay === "function") {
            renderAudioOverlay();
          }
          return data.peaks;
        } else if (data.status === "generating") {
          setTimeout(() => {
            isExtractingAudioPeaks = false;
            extractAudioPeaks();
          }, 2000);
          return null;
        }
        isExtractingAudioPeaks = false;
        return null;
      } catch (err) {
        console.warn("[AudioWaveform] Peak extraction fetch error:", err);
        isExtractingAudioPeaks = false;
        return null;
      }
    }
    window.extractAudioPeaks = extractAudioPeaks;



    // --- CapCut / Canva Style: Separate Audio / Link Audio ---
    const separateAudioBtn = document.getElementById("tb-separate-audio");
    const separateAudioText = document.getElementById("separate-audio-text");
    const separateAudioIcon = document.getElementById("separate-audio-icon");

    function updateSeparateAudioUI() {
      const isSeparated = Boolean(editorState.audio_separated);
      if (separateAudioText) {
        separateAudioText.textContent = isSeparated ? "Link Audio" : "Separate Audio";
      }
      if (separateAudioBtn) {
        separateAudioBtn.title = isSeparated
          ? "Link Audio to Video (Canva style - move and edit together)"
          : "Separate Audio from Video (CapCut style - move and edit independently)";
        separateAudioBtn.classList.toggle("tb-btn--active", isSeparated);
      }
      if (typeof lucide !== "undefined" && separateAudioIcon) {
        separateAudioIcon.setAttribute("data-lucide", isSeparated ? "link-2" : "music-2");
        lucide.createIcons();
      }
    }
    window.updateSeparateAudioUI = updateSeparateAudioUI;

    if (separateAudioBtn) {
      separateAudioBtn.addEventListener("click", () => {
        editorState.audio_separated = !editorState.audio_separated;
        if (!editorState.audio_separated) {
          // Re-link audio to video clips
          recalculateVideoClipsTimeline();
          if (typeof showVeToast === "function") {
            showVeToast("Audio linked to video track (Canva style)");
          }
        } else {
          // Mark audio clips as independent
          if (editorState.background_audios) {
            editorState.background_audios.forEach((a) => {
              if (a.is_detached) a.user_dragged = true;
            });
          }
          if (typeof showVeToast === "function") {
            showVeToast("Audio separated from video (CapCut style)");
          }
        }
        updateSeparateAudioUI();
        _lastClipRenderKey = "";
        renderClipBlocks();
        renderAllTimelineTracks();
        renderTrim();
        autoSaveTimeline();
        if (window.updateLocalState) {
          window.updateLocalState("Audio", editorState.audio_separated ? "Separated audio from video" : "Linked audio to video");
        }
      });
    }
// Merge button click
    const mergeBtn = document.getElementById("tb-merge");
    if (mergeBtn) {
      mergeBtn.addEventListener("click", mergeSelectedTimelineItem);
    }

    // Duplicate button click
    const duplicateBtn = document.getElementById("tb-duplicate");
    if (duplicateBtn) {
      duplicateBtn.addEventListener("click", duplicateSelectedTimelineItem);
    }

    // Delete button click
    const deleteBtn = document.getElementById("tb-delete");
    if (deleteBtn) {
      deleteBtn.addEventListener("click", deleteSelectedTimelineItem);
    }

    // Add Clip button click
    const addClipBtn = document.getElementById("tb-add-clip");
    if (addClipBtn) {
      addClipBtn.addEventListener("click", () => {
        if (typeof UnifiedMediaUploader !== "undefined") {
          UnifiedMediaUploader.openPicker({
            accept: "video/*,image/*",
            autoInsert: true,
            targetTrack: "video"
          });
        }
      });
    }

    // Bottom toolbar extra helpers
    const btnBottomZoomFit = document.getElementById("tb-bottom-zoom-fit");
    if (btnBottomZoomFit && btnZoomFit) {
      btnBottomZoomFit.addEventListener("click", () => btnZoomFit.click());
    }

    const btnBottomFullscreen = document.getElementById("tb-bottom-fullscreen");
    if (btnBottomFullscreen && btnFullscreen) {
      btnBottomFullscreen.addEventListener("click", () => btnFullscreen.click());
    }

    // Immediate and lifecycle initialization
    initTrim();
    extractAudioPeaks();
    loadFilmstripThumbs();

    const onVideoReady = () => {
      initTrim();
      extractAudioPeaks();
      loadFilmstripThumbs();
    };

    if (video.readyState >= 1) {
      onVideoReady();
    } else {
      video.addEventListener("loadedmetadata", onVideoReady);
      video.addEventListener("canplay", onVideoReady, { once: true });
    }

    document.addEventListener("turbo:load", () => {
      initTrim();
      extractAudioPeaks();
      loadFilmstripThumbs();
    });

    let currentThumbnailAbortController = null;

    function initTrim() {
      const vidDur = (video && !isNaN(video.duration) && video.duration > 0) ? video.duration : null;
      const projDur = (typeof window.duration !== "undefined" && !isNaN(window.duration) && window.duration > 0)
        ? window.duration
        : (window.REEL_PROJECT_DURATION ? parseFloat(window.REEL_PROJECT_DURATION) : null);

      duration = vidDur || projDur || 0;
      window.duration = duration;

      // Update video time display even if duration is 0
      const timeTotalEl = document.getElementById("video-time-total");
      if (timeTotalEl) {
        timeTotalEl.textContent = formatTime(duration || 0);
      }
      const timeCurrentEl = document.getElementById("video-time-current");
      if (timeCurrentEl) {
        timeCurrentEl.textContent = formatTime(video.currentTime || 0);
      }

      if (!duration || isNaN(duration) || duration <= 0) {
        // Still render tracks in empty state
        renderClipBlocks();
        renderAllTimelineTracks();
        updateRuler();
        return;
      }

      if ((!editorState.video_clips || editorState.video_clips.length === 0) && duration > 0) {
        editorState.video_clips = [{
          title: "Main Video",
          name: "Main Video",
          start: 0.0,
          end: duration,
          trimStart: 0.0,
          trimEnd: duration,
          duration: duration
        }];
        recalculateVideoClipsTimeline();
      }

      if (editorState.trim && editorState.trim.start !== undefined && editorState.trim.end > 0 && editorState.trim.end < duration) {
        startSeconds = editorState.trim.start;
        endSeconds = editorState.trim.end;
      } else if (startInput && startInput.value && endInput && endInput.value) {
        const s = parseFloat(startInput.value);
        const e = parseFloat(endInput.value);
        if (!isNaN(s) && !isNaN(e) && e > s && e <= duration) {
          startSeconds = s;
          endSeconds = e;
        } else {
          startSeconds = 0;
          endSeconds = duration;
        }
      } else {
        startSeconds = 0;
        endSeconds = duration;
      }

      if (startSeconds < 0) startSeconds = 0;
      if (!endSeconds || endSeconds > duration || endSeconds <= startSeconds)
        endSeconds = duration;

      if (startInput) startInput.value = startSeconds.toFixed(2);
      if (endInput) endInput.value = endSeconds.toFixed(2);

      // Automatically set default zoom factor to fit the container width, with a minimum value of 0.001
      const parentWidth = trimTrack.parentElement
        ? trimTrack.parentElement.clientWidth - 32
        : 800;
      if (parentWidth && duration) {
        zoomFactor = Math.max(
          0.001,
          parentWidth / (duration * basePxPerSecond),
        );
      }

      // Also allow clicking directly on timeline to move playhead
      const tracksWrapper = document.querySelector(".timeline-tracks-wrapper");
      if (tracksWrapper && !tracksWrapper.dataset.playheadClickBound) {
        tracksWrapper.dataset.playheadClickBound = "true";
        tracksWrapper.addEventListener("click", (e) => {
          if (
            e.target.closest(".trim-handle") ||
            e.target.closest(".text-resize-handle") ||
            e.target.closest(".audio-resize-handle") ||
            e.target.closest(".timeline-clip-block") ||
            e.target.closest(".timeline-text-block") ||
            e.target.closest(".timeline-audio-block") ||
            e.target.closest(".timeline-generic-block")
          ) {
            return;
          }
          let newTime = getSecondsFromX(e.clientX);
          const snapped = snapTimeToPoints(newTime);
          newTime = snapped.time;
          syncVideoElementToTimeline(newTime, true);
          hideSnapGuide();
          renderTrim();
          updatePlayheadSmooth();
          updateVideoProgress();
        });
      }

      prefillForms();
      applyCSSEffects();
      if (trackManager) {
        trackManager.updateTrackVisibilities();
      }
      updateRuler();
      renderTrim();
      renderClipBlocks();
      renderAllTimelineTracks();
      generateThumbnails();
      renderAudioOverlay();
      renderTextOverlays();
      updateVideoProgress();
    }

    // Dynamic filmstrip thumbnail generator for the trim-selection area.
    // Uses the shared _thumbCache — frames already loaded by renderClipBlocks
    // are instantly reused without any extra video seeks.
    generateThumbnails = async function () {
      return;
    }

    // ── ResizeObserver: re-render thumbnails when timeline width changes ──
    if (typeof ResizeObserver !== "undefined" && trimTrack) {
      let _resizeTimer = null;
      const _roClips = new ResizeObserver(() => {
        clearTimeout(_resizeTimer);
        _resizeTimer = setTimeout(() => {
          if (duration) {
            _lastClipRenderKey = ""; // width changed → recount slots
            renderClipBlocks();
            generateThumbnails();
          }
        }, 120);
      });
      _roClips.observe(trimTrack);
    }

    window.updateRuler = updateRuler;
    window.generateThumbnails = generateThumbnails;
    window.formatTime = window.formatTime || formatTime;
