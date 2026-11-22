/**
 * Video Editor Module — Transport Controls, Fullscreen & Keyboard Shortcuts
 */
    renderClipBlocks = async function () {
      const container = document.getElementById("timeline-clip-blocks") || (typeof clipBlocksContainer !== "undefined" ? clipBlocksContainer : null);
      if (!container) return;

      // Ensure we have a valid duration before proceeding with layout
      if ((!duration || isNaN(duration) || duration <= 0)) {
        if (window.REEL_PROJECT_DURATION && parseFloat(window.REEL_PROJECT_DURATION) > 0) {
          duration = parseFloat(window.REEL_PROJECT_DURATION);
          window.duration = duration;
        } else if (video && !isNaN(video.duration) && video.duration > 0) {
          duration = video.duration;
          window.duration = duration;
        }
      }

      const clipsData = editorState.video_clips || [];
      const pxPerSecond = basePxPerSecond * zoomFactor;
      const parentWidth = trimTrack?.parentElement ? trimTrack.parentElement.clientWidth : 800;
      
      // If duration is still 0, we can't render blocks, but we can show the "Add Clip" button
      if (!duration || isNaN(duration) || duration <= 0) {
        container.innerHTML = "";
        const addClipBtn = document.createElement("button");
        addClipBtn.type = "button";
        addClipBtn.className = "timeline-inline-add-btn timeline-inline-add-video-btn";
        addClipBtn.style.left = "10px";
        addClipBtn.innerHTML = `<i data-lucide="plus"></i> <span>Add First Clip</span>`;
        addClipBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          const grid = document.querySelector(".ve-editor-grid");
          if (grid) grid.classList.remove("sidebar-collapsed");
          const uploadTab = document.querySelector('.ve-dock-btn[data-tab="import"], .ve-tool-tab[data-tab="import"]');
          if (uploadTab) uploadTab.click();
        });
        container.appendChild(addClipBtn);
        if (typeof lucide !== "undefined") lucide.createIcons();
        return;
      }

      const totalWidth = Math.max(parentWidth, duration * pxPerSecond);

      if (trimTrack) trimTrack.style.width = `${totalWidth}px`;
      container.style.width = `${totalWidth}px`;

      const stateKey = `${clipsData.map((c) => `${c.start}-${c.end}`).join(",")}|${pxPerSecond.toFixed(3)}|${_filmstripThumbs ? _filmstripThumbs.length : 0}`;

      if (_clipThumbAbortController) {
        _clipThumbAbortController.abort();
      }
      const abortController = new AbortController();
      _clipThumbAbortController = abortController;
      const signal = abortController.signal;

      const domNeedsRebuild = stateKey !== _lastClipRenderKey || !container.children || container.children.length !== clipsData.length;

      if (domNeedsRebuild) {
        container.innerHTML = "";
      }

      let accumTime = 0.0;
      const blockInfos = [];

      clipsData.forEach((clip, index) => {
        const clipDur = parseFloat(clip.duration || 0.0);
        const blockLeft = accumTime * pxPerSecond;
        const blockWidth = Math.max(1, clipDur * pxPerSecond);

        let block, thumbContainer;

        if (domNeedsRebuild) {
          block = document.createElement("div");
          block.className = "timeline-clip-block";
          block.style.position = "absolute";
          block.style.top = "2px";
          block.style.bottom = "2px";
          block.style.background = "#0f172a";
          block.style.borderRadius = "8px";
          block.style.overflow = "hidden";
          block.style.boxSizing = "border-box";
          block.style.border = "2px solid rgba(255, 255, 255, 0.18)";

          thumbContainer = document.createElement("div");
          thumbContainer.className = "timeline-clip-thumb";
          thumbContainer.style.overflow = "hidden";
          thumbContainer.style.display = "flex";
          thumbContainer.style.width = "100%";
          thumbContainer.style.height = "100%";
          thumbContainer.style.position = "absolute";
          thumbContainer.style.inset = "0";
          thumbContainer.style.pointerEvents = "none";
          thumbContainer.style.background = "#0f172a";
          block.appendChild(thumbContainer);



          // Canva Clip Trim Handles
          const handleL = document.createElement("div");
          handleL.className = "clip-trim-handle clip-trim-handle-left";
          handleL.style.cssText = "position:absolute; left:0; top:0; bottom:0; width:10px; cursor:ew-resize; z-index:6; display:flex; align-items:center; justify-content:center; background:rgba(139,92,246,0.85); border-radius:6px 0 0 6px;";
          handleL.innerHTML = '<div style="width:2px; height:14px; background:#ffffff; border-radius:1px;"></div>';
          block.appendChild(handleL);

          const handleR = document.createElement("div");
          handleR.className = "clip-trim-handle clip-trim-handle-right";
          handleR.style.cssText = "position:absolute; right:0; top:0; bottom:0; width:10px; cursor:ew-resize; z-index:6; display:flex; align-items:center; justify-content:center; background:rgba(139,92,246,0.85); border-radius:0 6px 6px 0;";
          handleR.innerHTML = '<div style="width:2px; height:14px; background:#ffffff; border-radius:1px;"></div>';
          block.appendChild(handleR);

          const clipStart = parseFloat(clip.start != null ? clip.start : accumTime);
          const clipEnd = parseFloat(clip.end != null ? clip.end : accumTime + clipDur);

          block.addEventListener("click", (e) => {
            e.stopPropagation();
            startSeconds = parseFloat(clipStart.toFixed(3));
            endSeconds = parseFloat(clipEnd.toFixed(3));
            selectedClipIndex = index;
            selectTimelineItem("video", index, {
              start: startSeconds,
              end: endSeconds,
              name: clip.name || `Clip ${index + 1}`,
            });
            video.currentTime = timelineToSourceTime(startSeconds);
          });

          // Trim dragging on left handle with magnetic snapping and auto-save
          setupDrag(
            handleL,
            (clientX) => {
              let s = getSecondsFromX(clientX);
              const snapped = snapTimeToPoints(s);
              s = snapped.time;
              if (s < 0) s = 0;
              const curEnd = clip.end || (accumTime + clipDur);
              if (s > curEnd - 0.2) s = curEnd - 0.2;
              const delta = s - (clip.start || 0);
              clip.start = parseFloat(s.toFixed(2));
              clip.trimStart = Math.max(0, parseFloat(((clip.trimStart || 0) + delta).toFixed(2)));
              clip.duration = parseFloat((curEnd - clip.start).toFixed(2));
              if (editorState.background_audios && editorState.background_audios[index]) {
                const aClip = editorState.background_audios[index];
                if (aClip.is_detached && !aClip.user_dragged) {
                  aClip.start = clip.start;
                  aClip.trimStart = clip.trimStart;
                  aClip.duration = clip.duration;
                }
              }
              startSeconds = clip.start;
              endSeconds = curEnd;
              block.style.left = `${clip.start * pxPerSecond}px`;
              block.style.width = `${Math.max(1, clip.duration * pxPerSecond)}px`;
              renderTrim();
            },
            () => {
              hideSnapGuide();
              recalculateVideoClipsTimeline();
              _lastClipRenderKey = "";
              renderClipBlocks();
              renderAllTimelineTracks();
              updateRuler();
              renderTrim();
              generateThumbnails();
              updateVideoProgress();
              autoSaveTimeline();
              if (window.updateLocalState) {
                window.updateLocalState("Trim", `Trimmed clip ${clip.name || ''}`);
              }
            }
          );

          // Trim dragging on right handle with magnetic snapping and auto-save
          setupDrag(
            handleR,
            (clientX) => {
              let e = getSecondsFromX(clientX);
              const snapped = snapTimeToPoints(e);
              e = snapped.time;
              const curStart = clip.start || accumTime;
              if (e > duration) e = duration;
              if (e < curStart + 0.2) e = curStart + 0.2;
              const delta = e - (clip.end || curStart + clipDur);
              clip.end = parseFloat(e.toFixed(2));
              clip.trimEnd = parseFloat(((clip.trimEnd || clip.duration) + delta).toFixed(2));
              clip.duration = parseFloat((clip.end - curStart).toFixed(2));
              if (editorState.background_audios && editorState.background_audios[index]) {
                const aClip = editorState.background_audios[index];
                if (aClip.is_detached && !aClip.user_dragged) {
                  aClip.end = clip.end;
                  aClip.trimEnd = clip.trimEnd;
                  aClip.duration = clip.duration;
                }
              }
              endSeconds = clip.end;
              startSeconds = curStart;
              block.style.width = `${Math.max(1, clip.duration * pxPerSecond)}px`;
              renderTrim();
            },
            () => {
              hideSnapGuide();
              recalculateVideoClipsTimeline();
              _lastClipRenderKey = "";
              renderClipBlocks();
              renderAllTimelineTracks();
              updateRuler();
              renderTrim();
              generateThumbnails();
              updateVideoProgress();
              autoSaveTimeline();
              if (window.updateLocalState) {
                window.updateLocalState("Trim", `Trimmed clip ${clip.name || ''}`);
              }
            }
          );

          container.appendChild(block);
        } else {
          block = container.children[index];
          thumbContainer = block ? block.querySelector(".timeline-clip-thumb") : null;
        }

        if (block) {
          block.style.left = `${blockLeft}px`;
          block.style.width = `${blockWidth}px`;
          if (clipsData.length > 1 && index > 0) {
            block.style.borderLeft = "1px solid rgba(255, 255, 255, 0.35)";
          } else {
            block.style.borderLeft = "none";
          }
          block.classList.toggle("selected", globalSelection.track === "video" && globalSelection.index === index);

          // Speed badge
          const clipSpeed = clip.speed || editorState.speed || 1.0;
          let speedBadge = block.querySelector(".clip-speed-badge");
          if (clipSpeed !== 1.0) {
            if (!speedBadge) {
              speedBadge = document.createElement("span");
              speedBadge.className = "clip-speed-badge";
              speedBadge.style.cssText =
                "position: absolute; top: 3px; right: 4px; background: rgba(0,0,0,0.7); border: 1px solid var(--ve-border, #444); border-radius: 3px; font-size: 10px; font-weight: 600; padding: 1px 4px; color: #38bdf8; z-index: 5; pointer-events: none;";
              block.appendChild(speedBadge);
            }
            speedBadge.textContent = `${clipSpeed}x`;
          } else if (speedBadge) {
            speedBadge.remove();
          }
        }

        const clipStart = parseFloat(clip.start != null ? clip.start : accumTime);
        const clipEnd = parseFloat(clip.end != null ? clip.end : accumTime + clipDur);
        const clipTrimStart = parseFloat(clip.trimStart != null ? clip.trimStart : clipStart);
        blockInfos.push({
          block,
          thumbContainer,
          clipStart,
          clipEnd,
          clipTrimStart,
          blockWidthPx: blockWidth,
        });
        accumTime += clipDur;
      });

      if (typeof lucide !== "undefined") lucide.createIcons();

      if (!domNeedsRebuild) {
        return;
      }

      // ── Canva / CapCut Filmstrip Thumbnails ──────
      if (!_filmstripThumbs || _filmstripThumbs.length === 0) {
        // Show loading placeholders while thumbnails are being generated
        loadFilmstripThumbs();
        for (let i = 0; i < blockInfos.length; i++) {
          const { thumbContainer, blockWidthPx } = blockInfos[i];
          if (thumbContainer) {
            const count = Math.max(1, Math.floor(blockWidthPx / THUMB_DESIRED_W));
            let placeholderSlots = '';
            for (let s = 0; s < count; s++) {
              placeholderSlots += `<div class="thumb-placeholder" style="flex:1; height:100%; border-right:1px dashed rgba(255,255,255,0.12); display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg, #1e293b 0%, #0f172a 100%);"><i data-lucide="film" style="width:18px;height:18px;color:rgba(255,255,255,0.3);"></i></div>`;
            }
            thumbContainer.innerHTML = `<div style="display:flex; width:100%; height:100%;">${placeholderSlots}</div>`;
            thumbContainer.classList.add("loading");
          }
        }
        if (typeof lucide !== "undefined") lucide.createIcons();
        _lastClipRenderKey = stateKey;
        return;
      }

      // Render actual thumbnails
      for (let i = 0; i < blockInfos.length; i++) {
        if (signal.aborted) return;
        const { thumbContainer, clipStart, clipEnd, clipTrimStart, blockWidthPx, block } = blockInfos[i];
        const clipDuration = clipEnd - clipStart;
        
        // Validate clip data
        if (!thumbContainer || clipDuration <= 0 || blockWidthPx <= 0) {
          console.warn(`Skipping thumbnail render for clip ${i}: invalid data`, {
            clipDuration,
            blockWidthPx,
            hasContainer: !!thumbContainer
          });
          // Show error placeholder
          if (thumbContainer) {
            thumbContainer.innerHTML = `<div style="width:100%; height:100%; display:flex; align-items:center; justify-content:center; background:#dc2626; color:white; font-size:11px; font-weight:600;"><i data-lucide="alert-circle" style="width:14px;height:14px;margin-right:4px;"></i>Invalid Clip</div>`;
            if (typeof lucide !== "undefined") lucide.createIcons();
          }
          continue;
        }

        const renderedWidth = block?.clientWidth || blockWidthPx;
        const count = Math.max(1, Math.floor(renderedWidth / THUMB_DESIRED_W));
        const slotW = renderedWidth / count;

        thumbContainer.innerHTML = "";
        thumbContainer.classList.remove("loading");

        if (clipsData[i].isImage) {
          const img = document.createElement("img");
          img.src = clipsData[i].url || "";
          img.draggable = false;
          img.style.width = "100%";
          img.style.height = "100%";
          img.style.objectFit = "cover";
          img.style.backgroundColor = "#0f172a";
          thumbContainer.appendChild(img);
          continue;
        }

        const totalSrcDur = window.duration || duration || 779.32;

        for (let j = 0; j < count; j++) {
          const srcTime = clipTrimStart + (clipDuration * (j + 0.5)) / count;
          const frac = Math.max(0, Math.min(0.999, srcTime / totalSrcDur));
          const thumbIdx = Math.min(
            _filmstripThumbs.length - 1,
            Math.floor(frac * _filmstripThumbs.length),
          );
          const thumbUrl = _filmstripThumbs[thumbIdx];

          const isLastSlot = j === count - 1;
          const slotPx = isLastSlot
            ? renderedWidth - Math.round(slotW) * (count - 1)
            : Math.round(slotW);

          const img = document.createElement("img");
          img.src = thumbUrl;
          img.draggable = false;
          img.style.width = `${slotPx}px`;
          img.style.height = "100%";
          img.style.objectFit = "cover";
          img.style.display = "block";
          img.style.flexShrink = "0";
          img.style.backgroundColor = "#0f172a";
          img.style.borderRight = "1px solid rgba(255, 255, 255, 0.15)";
          img.onerror = () => { img.style.opacity = "0"; };
          thumbContainer.appendChild(img);
        }
      }

      // Canva-style Add Clip button at the end of the video blocks
      const existingAddBtn = container.querySelector(".timeline-inline-add-clip-btn, .timeline-inline-add-btn");
      if (existingAddBtn) existingAddBtn.remove();

      const addClipBtn = document.createElement("button");
      addClipBtn.type = "button";
      addClipBtn.className = "timeline-inline-add-btn timeline-inline-add-video-btn";
      addClipBtn.style.left = `${accumTime * pxPerSecond + 6}px`;
      addClipBtn.innerHTML = `<i data-lucide="plus"></i> <span>Add Clip</span>`;
      addClipBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const grid = document.querySelector(".ve-editor-grid");
        if (grid) grid.classList.remove("sidebar-collapsed");
        const uploadTab = document.querySelector('.ve-dock-btn[data-tab="import"], .ve-tool-tab[data-tab="import"]');
        if (uploadTab) uploadTab.click();
        const videoCatBtn = document.querySelector('.ve-category-btn[data-category="video"]');
        if (videoCatBtn) videoCatBtn.click();
      });
      container.appendChild(addClipBtn);

      if (typeof lucide !== "undefined") lucide.createIcons();
      _lastClipRenderKey = stateKey;
    }

    
    // ── Canva-Grade 60fps Playhead Animation Engine ──
    let _playheadRafId = null;
    updatePlayheadSmooth = function () {
      if (!duration || !trimPlayhead) return;
      if (trimPlayhead.classList.contains("dragging")) return;

      const pxPerSecond = basePxPerSecond * zoomFactor;
      const clips = editorState.video_clips || [];
      let timelineTime = sourceToTimelineTime(video.currentTime);

      // Multi-clip playback management in 60fps loop
      if (!video.paused && clips.length > 0) {
        if (activePlayingClipIndex < 0 || activePlayingClipIndex >= clips.length) {
          activePlayingClipIndex = 0;
        }
        const activeClip = clips[activePlayingClipIndex];
        const clipTrimStart = parseFloat(activeClip.trimStart || 0);
        const clipTrimEnd = parseFloat(activeClip.trimEnd !== undefined ? activeClip.trimEnd : (clipTrimStart + (activeClip.duration || 0)));
        const curOffset = Math.max(0, video.currentTime - clipTrimStart);
        timelineTime = (activeClip.start || 0) + Math.min(curOffset, activeClip.duration || 0);

        // Clip trim loop if user has explicitly selected a clip for preview loop
        if (globalSelection.track === "video" && selectedClipIndex !== -1 && endSeconds > startSeconds + 0.1) {
          if (timelineTime >= endSeconds - 0.04) {
            syncVideoElementToTimeline(startSeconds, true);
            return;
          }
        }

        // Check if current clip has ended
        if (!isTransitioningClip && video.currentTime >= clipTrimEnd - 0.05) {
          if (activePlayingClipIndex + 1 < clips.length) {
            isTransitioningClip = true;
            activePlayingClipIndex++;
            const nextClip = clips[activePlayingClipIndex];
            syncVideoElementToTimeline(nextClip.start, true);
            video.play().catch(() => {});
            return;
          } else {
            video.pause();
            activePlayingClipIndex = 0;
            syncVideoElementToTimeline(0, true);
            stopSmoothPlayhead();
            return;
          }
        }
      }

      timelineCurrentTime = timelineTime;
      syncAudioPreviewToTimeline(timelineTime, false);
      const playheadPx = timelineTime * pxPerSecond;
      trimPlayhead.style.left = `${playheadPx}px`;

      const timeCurrentEl = document.getElementById("video-time-current");
      if (timeCurrentEl) timeCurrentEl.textContent = formatTime(timelineTime);

      const playheadTooltip = document.getElementById("playhead-tooltip");
      if (playheadTooltip) playheadTooltip.textContent = formatTime(timelineTime);

      if (currentDisplay) currentDisplay.textContent = formatTime(timelineTime);

      // Text overlays visibility during 60fps playhead (always keep visible if selected!)
      if (editorState.text_overlays && editorState.text_overlays.length > 0) {
        const textContainer = document.getElementById("text-overlay-container");
        if (textContainer && textContainer.children) {
          const textElements = textContainer.children;
          editorState.text_overlays.forEach((overlay, i) => {
            if (textElements[i]) {
              const isSelected = globalSelection && globalSelection.track === "text" && globalSelection.index === i;
              const oStart = parseFloat(overlay.start || 0);
              const oEnd = parseFloat(overlay.end || duration);
              if (isSelected || (timelineTime >= oStart - 0.05 && timelineTime <= oEnd + 0.05)) {
                textElements[i].style.display = "block";
              } else {
                textElements[i].style.display = "none";
              }
            }
          });
        }
      }

      // Auto-scroll timeline to keep playhead in view during playback
      const scrollArea = trimContainer ? trimContainer.querySelector(".timeline-scroll-area") : null;
      if (scrollArea && !video.paused) {
        const viewportWidth = scrollArea.clientWidth;
        const scrollLeft = scrollArea.scrollLeft;
        if (playheadPx > scrollLeft + viewportWidth - 140) {
          scrollArea.scrollLeft = playheadPx - 140;
        } else if (playheadPx < scrollLeft + 20) {
          scrollArea.scrollLeft = Math.max(0, playheadPx - 20);
        }
      }
    }

    function startSmoothPlayhead() {
      if (_playheadRafId) cancelAnimationFrame(_playheadRafId);
      function loop() {
        if (!video.paused && !video.ended) {
          updatePlayheadSmooth();
          _playheadRafId = requestAnimationFrame(loop);
        }
      }
      _playheadRafId = requestAnimationFrame(loop);
    }

    function stopSmoothPlayhead() {
      if (_playheadRafId) {
        cancelAnimationFrame(_playheadRafId);
        _playheadRafId = null;
      }
      updatePlayheadSmooth();
      syncAudioPreviewToTimeline(timelineCurrentTime || 0, true);
    }

    video.addEventListener("play", startSmoothPlayhead);
    video.addEventListener("pause", stopSmoothPlayhead);
    video.addEventListener("ended", stopSmoothPlayhead);
    video.addEventListener("seeking", updatePlayheadSmooth);
    video.addEventListener("seeked", updatePlayheadSmooth);
    video.addEventListener("loadeddata", () => {
      if (video.currentTime === 0) {
        try { video.currentTime = 0.001; } catch (e) {}
      }
      updatePlayheadSmooth();
    });

    renderTrim = function () {
      if (!duration) return;

      const pxPerSecond = basePxPerSecond * zoomFactor;
      const leftPx = startSeconds * pxPerSecond;
      const rightPx = endSeconds * pxPerSecond;
      const timelineTime = sourceToTimelineTime(video.currentTime);
      const playheadPx = timelineTime * pxPerSecond;

      // Position playhead directly on timeline
      trimPlayhead.style.left = `${playheadPx}px`;
      const playheadTooltip = document.getElementById("playhead-tooltip");
      if (playheadTooltip) {
        playheadTooltip.textContent = formatTime(timelineTime);
      }

      // Time displays
      if (currentDisplay) currentDisplay.textContent = formatTime(timelineTime);
      if (totalDisplay) totalDisplay.textContent = formatTime(duration);

      const timeCurrentEl = document.getElementById("video-time-current");
      if (timeCurrentEl) timeCurrentEl.textContent = formatTime(timelineTime);

      const timeTotalEl = document.getElementById("video-time-total");
      if (timeTotalEl) timeTotalEl.textContent = formatTime(duration);

      const tooltipL = document.getElementById("handle-tooltip-left");
      const tooltipR = document.getElementById("handle-tooltip-right");
      if (tooltipL) tooltipL.textContent = formatTime(startSeconds);
      if (tooltipR) tooltipR.textContent = formatTime(endSeconds);

      const durationBadge = document.getElementById("trim-duration-badge");
      if (durationBadge) {
        const diff = endSeconds - startSeconds;
        durationBadge.textContent = `${diff.toFixed(1)}s`;
      }

      // Sync hidden inputs
      if (startInput) startInput.value = startSeconds.toFixed(2);
      if (endInput) endInput.value = endSeconds.toFixed(2);

      // Render multi-track timeline blocks & clips
      renderAllTimelineTracks();
      renderSplitMarkers();
      renderClipBlocks();

      // Enable/disable toolbar buttons
      const deleteBtnEl = document.getElementById("tb-delete");
      const duplicateBtnEl = document.getElementById("tb-duplicate");
      const mergeBtnEl = document.getElementById("tb-merge");
      if (typeof updateToolbarActionButtons === "function") {
        updateToolbarActionButtons();
      }

      updateTrackRowVisibility();
    }

    getSecondsFromX = function (clientX) {
      const rect = trimTrack.getBoundingClientRect();
      const pxPerSecond = basePxPerSecond * zoomFactor;
      const relativeX = clientX - rect.left;
      const s = relativeX / Math.max(0.001, pxPerSecond);
      return Math.max(0, Math.min(duration || 0, s));
    };

    // Dragging helper
    function setupDrag(element, onDrag, onDragEnd) {
      if (!element) return;
      function move(e) {
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        onDrag(clientX);
      }
      function stop() {
        element.classList.remove("dragging");
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", stop);
        window.removeEventListener("touchmove", move);
        window.removeEventListener("touchend", stop);
        if (onDragEnd) onDragEnd();
      }
      element.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        element.classList.add("dragging");
        window.addEventListener("mousemove", move);
        window.addEventListener("mouseup", stop);
      });
      element.addEventListener("touchstart", (e) => {
        e.preventDefault();
        e.stopPropagation();
        element.classList.add("dragging");
        window.addEventListener("touchmove", move);
        window.addEventListener("touchend", stop);
      });
    }

    const autoSubmitTrim = () => {
      if (startInput) startInput.value = startSeconds.toFixed(2);
      if (endInput) endInput.value = endSeconds.toFixed(2);

      editorState.trim.start = startSeconds;
      editorState.trim.end = endSeconds;

      if (globalSelection.track === "video" && selectedClipIndex !== -1) {
        const clip = editorState.video_clips?.[selectedClipIndex];
        if (clip) {
          const deltaStart = startSeconds - clip.start;
          clip.trimStart = parseFloat((clip.trimStart + deltaStart).toFixed(2));
          clip.duration = parseFloat((endSeconds - startSeconds).toFixed(2));
          clip.trimEnd = parseFloat((clip.trimStart + clip.duration).toFixed(2));
          
          recalculateVideoClipsTimeline();
          
          startSeconds = clip.start;
          endSeconds = clip.end;
        }
      }

      if (window.updateLocalState) {
        window.updateLocalState("Trim", `Trimmed video to ${startSeconds.toFixed(2)}s - ${endSeconds.toFixed(2)}s`);
      }

      renderClipBlocks();
      renderAllTimelineTracks();
      updateRuler();
      renderTrim();
      generateThumbnails();
      updateVideoProgress();
    };

    // Left handle drag
    setupDrag(
      handleLeft,
      (clientX) => {
        let s = getSecondsFromX(clientX);
        const snapped = snapTimeToPoints(s);
        s = snapped.time;
        if (s < 0) s = 0;
        if (s > endSeconds - 0.2) s = endSeconds - 0.2;
        startSeconds = s;
        renderTrim();
      },
      () => {
        hideSnapGuide();
        autoSubmitTrim();
      },
    );

    // Right handle drag
    setupDrag(
      handleRight,
      (clientX) => {
        let e = getSecondsFromX(clientX);
        const snapped = snapTimeToPoints(e);
        e = snapped.time;
        if (e > duration) e = duration;
        if (e < startSeconds + 0.2) e = startSeconds + 0.2;
        endSeconds = e;
        renderTrim();
      },
      () => {
        hideSnapGuide();
        autoSubmitTrim();
      },
    );

    // Video playback sync for seeking and paused states
    video.addEventListener("timeupdate", () => {
      if (trimPlayhead && trimPlayhead.classList.contains("dragging")) return;
      if (video.paused) {
        updatePlayheadSmooth();
      }
    });

    // Update time display when metadata loads
    video.addEventListener("loadedmetadata", () => {
      const timeTotalEl = document.getElementById("video-time-total");
      if (timeTotalEl) {
        timeTotalEl.textContent = formatTime(duration);
      }
      const timeCurrentEl = document.getElementById("video-time-current");
      if (timeCurrentEl) {
        timeCurrentEl.textContent = formatTime(sourceToTimelineTime(video.currentTime));
      }
      // Initialize progress bar
      updateVideoProgress();
    });

    // Get progress bar elements
    const videoProgressBar = document.getElementById("video-progress-bar");
    const videoProgressFilled = document.getElementById(
      "video-progress-filled",
    );
    const videoProgressHandle = document.getElementById(
      "video-progress-handle",
    );

    // Function to update progress bar based on video time
    function updateVideoProgress() {
      if (!duration || duration === 0) return;
      const timelineTime = sourceToTimelineTime(video.currentTime);
      const progress = (timelineTime / duration) * 100;
      if (videoProgressFilled) {
        videoProgressFilled.style.width = `${progress}%`;
      }
      if (videoProgressHandle) {
        videoProgressHandle.style.left = `${progress}%`;
      }
      const timeCurrentEl = document.getElementById("video-time-current");
      if (timeCurrentEl) {
        timeCurrentEl.textContent = formatTime(timelineTime);
      }
      const timeTotalEl = document.getElementById("video-time-total");
      if (timeTotalEl) {
        timeTotalEl.textContent = formatTime(duration);
      }
    }

    // Update progress bar on timeupdate
    video.addEventListener("timeupdate", updateVideoProgress);

    // Handle clicking on progress bar to seek
    let isDraggingProgress = false;

    function seekFromProgress(clientX) {
      if (!videoProgressBar || !duration) return;
      const rect = videoProgressBar.getBoundingClientRect();
      let clickX = clientX - rect.left;
      // Clamp to bar bounds
      clickX = Math.max(0, Math.min(clickX, rect.width));
      const progress = clickX / rect.width;
      video.currentTime = timelineToSourceTime(progress * duration);
    }

    if (videoProgressBar) {
      videoProgressBar.addEventListener("mousedown", (e) => {
        isDraggingProgress = true;
        seekFromProgress(e.clientX);
      });
    }

    // Handle mouse move and up on document
    document.addEventListener("mousemove", (e) => {
      if (!isDraggingProgress) return;
      seekFromProgress(e.clientX);
    });

    document.addEventListener("mouseup", () => {
      isDraggingProgress = false;
    });

    // --- Custom Player Control Listeners ---
    const btnMute = document.getElementById("btn-mute");
    const volumeSlider = document.getElementById("volume-slider");

    const syncVolumeUI = () => {
      const isMuted = Boolean(editorState.userMuted);
      if (volumeSlider) {
        volumeSlider.value = isMuted ? 0 : (editorState.volume !== undefined ? editorState.volume : 1.0);
      }
      const volumeIcon = document.getElementById("volume-icon");
      const muteIcon = document.getElementById("mute-icon");
      if (volumeIcon)
        volumeIcon.style.display = isMuted ? "none" : "inline-block";
      if (muteIcon) muteIcon.style.display = isMuted ? "inline-block" : "none";
    };

    if (volumeSlider) {
      volumeSlider.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        video.volume = val;
        editorState.volume = val;
        editorState.userMuted = val === 0;
        editorState.muted = editorState.userMuted;
        video.muted = editorState.userMuted;
        syncVolumeUI();
        syncAudioPreviewToTimeline(timelineCurrentTime || 0, false);
      });
    }

    if (btnMute) {
      btnMute.addEventListener("click", () => {
        const newMuted = !(editorState.userMuted || editorState.muted);
        editorState.userMuted = newMuted;
        editorState.muted = newMuted;
        const mainVid = document.getElementById("main-video");
        if (mainVid) mainVid.muted = newMuted;
        syncVolumeUI();
        syncAudioPreviewToTimeline(timelineCurrentTime || 0, false);
      });
    }

    video.addEventListener("volumechange", () => {
      // NOTE: Do NOT set editorState.muted = video.muted!
      // In timeline playback, video.muted is dynamically toggled to mute gaps where audio was cut/deleted.
      // If we overwrite editorState.muted here, the user's audio becomes permanently muted after any cut!
      if (!video.muted && video.volume > 0) {
        editorState.volume = video.volume;
      }
      syncVolumeUI();
    });

    // --- Speed Dropdown Listener ---
    const speedDropdown = document.getElementById("speed-dropdown");

    const applySpeedChange = (spdVal) => {
      const spd = parseFloat(spdVal);
      if (!Number.isFinite(spd) || spd <= 0) return;
      editorState.speed = spd;
      video.playbackRate = spd;

      if (globalSelection.track === "video" && globalSelection.index !== undefined) {
        const clip = editorState.video_clips?.[globalSelection.index];
        if (clip) {
          clip.speed = spd;
        }
      }

      if (window.updateLocalState) {
        window.updateLocalState("Speed", `Changed speed to ${spd}x`);
      } else if (typeof autoSaveTimeline === "function") {
        autoSaveTimeline();
      }
    };

    if (speedDropdown) {
      const currentSpd = (editorState.speed || 1.0).toString();
      if (speedDropdown.options && Array.from(speedDropdown.options).some((o) => o.value === currentSpd)) {
        speedDropdown.value = currentSpd;
      }

      speedDropdown.addEventListener("change", (e) => {
        applySpeedChange(e.target.value);
      });
    }

    if (btnSkipStart) {
      btnSkipStart.addEventListener("click", () => {
        video.currentTime = timelineToSourceTime(0);
        renderTrim();
        updateVideoProgress();
      });
    }

    if (btnBack5) {
      btnBack5.addEventListener("click", () => {
        const curTimeline = sourceToTimelineTime(video.currentTime);
        video.currentTime = timelineToSourceTime(Math.max(0, curTimeline - 5));
        renderTrim();
        updateVideoProgress();
      });
    }

    // Play/Pause button sync helper
    const syncPlayPauseIcons = () => {
      const isPaused = video.paused;
      const playIcon = document.getElementById("play-icon");
      const pauseIcon = document.getElementById("pause-icon");
      const tbPlayIcon = document.getElementById("tb-bottom-play-icon");
      const tbPauseIcon = document.getElementById("tb-bottom-pause-icon");

      if (playIcon) playIcon.style.display = isPaused ? "inline-block" : "none";
      if (pauseIcon)
        pauseIcon.style.display = isPaused ? "none" : "inline-block";
      if (tbPlayIcon)
        tbPlayIcon.style.display = isPaused ? "inline-block" : "none";
      if (tbPauseIcon)
        tbPauseIcon.style.display = isPaused ? "none" : "inline-block";
    };

    video.addEventListener("play", syncPlayPauseIcons);
    video.addEventListener("pause", syncPlayPauseIcons);

    const togglePlayPause = () => {
      const maxDuration = duration || window.duration || (video && video.duration) || 0;
      if (video.paused) {
        const curTimeline = sourceToTimelineTime(video.currentTime);
        if (video.ended || (maxDuration > 0 && curTimeline >= maxDuration - 0.1)) {
          video.currentTime = timelineToSourceTime(0);
        }
        // Prime and play any preview audio elements synchronously inside user gesture
        const previewAudios = document.querySelectorAll("audio[id^='preview-timeline-audio-']");
        previewAudios.forEach(el => {
          if (el.src && el.src !== window.location.href) {
            try { el.play().catch(() => {}); } catch (e) {}
          }
        });

        // Ensure video has a valid media source loaded before calling play()
        const effectiveSrc = video.currentSrc || video.src;
        if (!effectiveSrc || effectiveSrc === window.location.href || video.error) {
          const fallbackSrc = window.REEL_PROJECT_PROXY_URL || window.REEL_PROJECT_WORKING_URL || window.REEL_PROJECT_ORIGINAL_URL || baseVideoOriginalSrc;
          if (fallbackSrc) {
            video.src = fallbackSrc;
            video.load();
          } else {
            return;
          }
        }

        const p = video.play();
        if (p && typeof p.catch === "function") {
          p.catch((err) => {
            if (err.name === "NotSupportedError" || video.error) {
              const fallback = window.REEL_PROJECT_WORKING_URL || window.REEL_PROJECT_ORIGINAL_URL || window.REEL_PROJECT_PROXY_URL || baseVideoOriginalSrc;
              if (fallback && (!video.src || !video.src.includes(fallback))) {
                video.src = fallback;
                video.load();
                video.play().catch(() => {});
                return;
              }
            }
            if (err.name !== "AbortError" && err.name !== "NotSupportedError") {
              console.warn("Playback prevented:", err);
            }
          });
        }
      } else {
        video.pause();
        const previewAudios = document.querySelectorAll("audio[id^='preview-timeline-audio-']");
        previewAudios.forEach(el => {
          try { el.pause(); } catch (e) {}
        });
      }
    };

    if (btnPlayPause) {
      btnPlayPause.addEventListener("click", (e) => {
        e.stopPropagation();
        togglePlayPause();
      });
    }

    // Clicking on video or stage toggles play/pause
    video.addEventListener("click", (e) => {
      e.stopPropagation();
      togglePlayPause();
    });

    const fabricStageCanvas = document.getElementById("fabric-stage-canvas");
    if (fabricStageCanvas) {
      fabricStageCanvas.addEventListener("click", (e) => {
        togglePlayPause();
      });
    }

    if (btnForward5) {
      btnForward5.addEventListener("click", () => {
        const maxDuration = duration || 0;
        const curTimeline = sourceToTimelineTime(video.currentTime);
        video.currentTime = timelineToSourceTime(Math.min(maxDuration, curTimeline + 5));
        renderTrim();
        updateVideoProgress();
      });
    }

    if (btnSkipEnd) {
      btnSkipEnd.addEventListener("click", () => {
        const maxDuration = duration || 0;
        video.currentTime = timelineToSourceTime(maxDuration);
        renderTrim();
        updateVideoProgress();
      });
    }

    // --- Editor Stage Fullscreen (CapCut / Premiere / Canva style) ---
    const videoStage =
      document.getElementById("video-stage") ||
      document.querySelector(".ve-video-stage");

    const updateFullscreenUI = () => {
      const isFs = !!(
        document.fullscreenElement ||
        document.webkitFullscreenElement ||
        document.msFullscreenElement ||
        (videoStage && videoStage.classList.contains("is-fullscreen"))
      );

      const fsIcon = document.getElementById("fullscreen-icon");
      const exitFsIcon = document.getElementById("exit-fullscreen-icon");

      if (videoStage) {
        videoStage.classList.toggle("is-fullscreen", isFs);
      }

      if (fsIcon) fsIcon.style.display = isFs ? "none" : "inline-block";
      if (exitFsIcon) exitFsIcon.style.display = isFs ? "inline-block" : "none";

      setTimeout(renderTextOverlays, 50);
    };

    const toggleStageFullscreen = () => {
      if (!videoStage) return;

      const isFs = !!(
        document.fullscreenElement ||
        document.webkitFullscreenElement ||
        document.msFullscreenElement ||
        videoStage.classList.contains("is-fullscreen")
      );

      if (!isFs) {
        if (videoStage.requestFullscreen) {
          videoStage.requestFullscreen().catch(() => {
            videoStage.classList.add("is-fullscreen");
            updateFullscreenUI();
          });
        } else if (videoStage.webkitRequestFullscreen) {
          videoStage.webkitRequestFullscreen();
        } else if (videoStage.msRequestFullscreen) {
          videoStage.msRequestFullscreen();
        } else {
          videoStage.classList.add("is-fullscreen");
          updateFullscreenUI();
        }
      } else {
        if (document.exitFullscreen) {
          document.exitFullscreen().catch(() => {
            videoStage.classList.remove("is-fullscreen");
            updateFullscreenUI();
          });
        } else if (document.webkitExitFullscreen) {
          document.webkitExitFullscreen();
        } else if (document.msExitFullscreen) {
          document.msExitFullscreen();
        } else {
          videoStage.classList.remove("is-fullscreen");
          updateFullscreenUI();
        }
      }
    };

    if (btnFullscreen) {
      btnFullscreen.addEventListener("click", toggleStageFullscreen);
    }

    document.addEventListener("fullscreenchange", updateFullscreenUI);
    document.addEventListener("webkitfullscreenchange", updateFullscreenUI);
    document.addEventListener("msfullscreenchange", updateFullscreenUI);

    // Keyboard Shortcuts (Space: Play/Pause, Left/Right: Skip 5s, M: Mute, F: Fullscreen)
    document.addEventListener("keydown", (e) => {
      const active = document.activeElement;
      if (
        active &&
        (active.tagName === "INPUT" ||
          active.tagName === "TEXTAREA" ||
          active.isContentEditable)
      ) {
        return;
      }
      if (e.code === "Space") {
        e.preventDefault();
        togglePlayPause();
      } else if (e.code === "ArrowLeft") {
        e.preventDefault();
        if (btnBack5) btnBack5.click();
      } else if (e.code === "ArrowRight") {
        e.preventDefault();
        if (btnForward5) btnForward5.click();
      } else if (e.code === "KeyM") {
        e.preventDefault();
        const mergeBtn = document.getElementById("tb-merge");
        if (mergeBtn && !mergeBtn.hasAttribute("disabled")) {
          mergeSelectedTimelineItem();
        } else if (btnMute) {
          btnMute.click();
        }
      } else if (e.code === "KeyF") {
        e.preventDefault();
        if (btnFullscreen) btnFullscreen.click();
      } else if (e.code === "KeyS") {
        e.preventDefault();
        const splitBtn = document.getElementById("tb-split");
        if (splitBtn && !splitBtn.hasAttribute("disabled")) {
          splitSelectedTimelineItem();
        }
      } else if ((e.ctrlKey || e.metaKey) && e.code === "KeyD") {
        e.preventDefault();
        duplicateSelectedTimelineItem();
      } else if (e.code === "Delete" || e.code === "Backspace") {
        const deleteBtn = document.getElementById("tb-delete");
        if (deleteBtn && !deleteBtn.hasAttribute("disabled")) {
          e.preventDefault();
          deleteSelectedTimelineItem();
        }
      }
    });

    // --- Timeline Bottom Toolbar Listeners ---
    const tbBottomZoomFit = document.getElementById("tb-bottom-zoom-fit");
    if (tbBottomZoomFit) {
      tbBottomZoomFit.addEventListener("click", () => {
        if (btnZoomFit) btnZoomFit.click();
      });
    }

    // Fullscreen timeline toggle
    const tbBottomFullscreen = document.getElementById("tb-bottom-fullscreen");
    const fsTimelineBtn = document.getElementById("btn-fullscreen-timeline");
    const toggleTimelineFullscreen = () => {
      if (!trimContainer) return;
      if (trimContainer.classList.contains("timeline-collapsed")) {
        setCollapseUIState(false);
      }
      trimContainer.classList.toggle("fullscreen-mode");
      const isFs = trimContainer.classList.contains("fullscreen-mode");

      if (fsTimelineBtn) {
        fsTimelineBtn.innerHTML = isFs
          ? '<i data-lucide="minimize-2" style="width:13px;height:13px;"></i>'
          : '<i data-lucide="maximize-2" style="width:13px;height:13px;"></i>';
        fsTimelineBtn.title = isFs ? "Exit Fullscreen Timeline" : "Maximize Timeline";
      }

      if (tbBottomFullscreen) {
        tbBottomFullscreen.innerHTML = isFs
          ? '<i data-lucide="minimize-2" style="width:13px;height:13px;"></i>'
          : '<i data-lucide="expand" style="width:13px;height:13px;"></i>';
      }

      if (typeof lucide !== "undefined") lucide.createIcons();
      _lastClipRenderKey = "";
      updateRuler();
      renderClipBlocks();
      renderAllTimelineTracks();
      updateOriginalAudioWaveform();
      renderTrim();
      renderTextOverlays();
    };

    if (tbBottomFullscreen)
      tbBottomFullscreen.addEventListener("click", toggleTimelineFullscreen);
    if (fsTimelineBtn)
      fsTimelineBtn.addEventListener("click", toggleTimelineFullscreen);

    window.renderClipBlocks = renderClipBlocks;
    window.updatePlayheadSmooth = updatePlayheadSmooth;
    window.renderTrim = renderTrim;
    window.getSecondsFromX = getSecondsFromX;

