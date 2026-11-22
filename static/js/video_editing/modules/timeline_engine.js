/**
 * Video Editor Module — Dynamic Track Manager, Ruler & Scroll Sync
 */
    // --- Multi-track Timeline Text Row rendering ---
    const textTrackContent = document.getElementById("text-track-content");
    // Synchronize Text Overlay Start/End Inputs with Playhead position
    const btnTextSetStart = document.getElementById("btn-text-set-start");
    const btnTextSetEnd = document.getElementById("btn-text-set-end");

    if (btnTextSetStart) {
      btnTextSetStart.addEventListener("click", () => {
        const playheadTime = parseFloat(sourceToTimelineTime(video ? video.currentTime : 0).toFixed(2));
        const textFormEl = document.querySelector('form[action*="/text/"]');
        if (textFormEl) {
          const input = textFormEl.querySelector('input[name="start_seconds"]');
          if (input) input.value = playheadTime;
        }

        const activeIndex = (globalSelection && globalSelection.track === "text") ? globalSelection.index : 0;
        if (
          activeIndex !== -1 &&
          editorState.text_overlays &&
          editorState.text_overlays[activeIndex]
        ) {
          const overlay = editorState.text_overlays[activeIndex];
          if (playheadTime < overlay.end) {
            overlay.start = playheadTime;
            renderAllTimelineTracks();
            renderTextOverlays();
          }
        }
      });
    }

    if (btnTextSetEnd) {
      btnTextSetEnd.addEventListener("click", () => {
        const playheadTime = parseFloat(sourceToTimelineTime(video ? video.currentTime : 0).toFixed(2));
        const textFormEl = document.querySelector('form[action*="/text/"]');
        if (textFormEl) {
          const input = textFormEl.querySelector('input[name="end_seconds"]');
          if (input) input.value = playheadTime;
        }

        const activeIndex = (globalSelection && globalSelection.track === "text") ? globalSelection.index : 0;
        if (
          activeIndex !== -1 &&
          editorState.text_overlays &&
          editorState.text_overlays[activeIndex]
        ) {
          const overlay = editorState.text_overlays[activeIndex];
          if (playheadTime > overlay.start) {
            overlay.end = playheadTime;
            renderAllTimelineTracks();
            renderTextOverlays();
          }
        }
      });
    }

    // Synchronize Background Audio Start/End Inputs with Playhead position
    const btnBgSetStart = document.getElementById("btn-bg-set-start");
    const btnBgSetEnd = document.getElementById("btn-bg-set-end");

    if (btnBgSetStart) {
      btnBgSetStart.addEventListener("click", () => {
        const playheadTime = parseFloat(sourceToTimelineTime(video.currentTime).toFixed(2));
        const bgFormEl = document.getElementById("bg-audio-form");
        if (bgFormEl) {
          const input = bgFormEl.querySelector('input[name="start_seconds"]');
          if (input) input.value = playheadTime;
        }
      });
    }

    if (btnBgSetEnd) {
      btnBgSetEnd.addEventListener("click", () => {
        const playheadTime = parseFloat(sourceToTimelineTime(video.currentTime).toFixed(2));
        const bgFormEl = document.getElementById("bg-audio-form");
        if (bgFormEl) {
          const input = bgFormEl.querySelector('input[name="end_seconds"]');
          if (input) input.value = playheadTime;
        }
      });
    }
    globalSelection = { track: null, index: -1 };

    const TRACK_CONFIG = {
      text: {
        stateKey: "text_overlays",
        containerId: "text-track-content",
        color: "linear-gradient(135deg, #0d6b6e 0%, #08494b 100%)",
        borderColor: "#119296",
        icon: "type",
      },
      audio: {
        stateKey: "background_audios",
        containerId: "audio-track",
        color: "transparent",
        borderColor: "rgba(16, 185, 129, 0.35)",
        icon: "music",
      },
      effect: {
        stateKey: "active_effects",
        containerId: "effect-track-content",
        color: "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
        borderColor: "#fbbf24",
        icon: "sparkles",
      },
    };

    function updateToolbarActionButtons() {
      const deleteBtnEl = document.getElementById("tb-delete");
      const duplicateBtnEl = document.getElementById("tb-duplicate");
      const mergeBtnEl = document.getElementById("tb-merge");
      const hasClips = editorState.video_clips && editorState.video_clips.length > 0;
      const isSelected = globalSelection && globalSelection.track !== null && globalSelection.index >= 0;

      if (deleteBtnEl) {
        if (isSelected || (hasClips && editorState.video_clips.length > 1)) {
          deleteBtnEl.removeAttribute("disabled");
        } else {
          deleteBtnEl.setAttribute("disabled", "true");
        }
      }
      if (duplicateBtnEl) {
        if (isSelected || hasClips) {
          duplicateBtnEl.removeAttribute("disabled");
        } else {
          duplicateBtnEl.setAttribute("disabled", "true");
        }
      }
      if (mergeBtnEl) {
        const canMerge = (hasClips && editorState.video_clips.length > 1) || (editorState.background_audios && editorState.background_audios.length > 1);
        if (canMerge) {
          mergeBtnEl.removeAttribute("disabled");
        } else {
          mergeBtnEl.setAttribute("disabled", "true");
        }
      }
    }
    window.updateToolbarActionButtons = updateToolbarActionButtons;

    clearGlobalSelection = function () {
      globalSelection = { track: null, index: -1 };
      selectedClipIndex = -1;
      const editorCard = document.getElementById("ve-text-editor-card");
      if (editorCard) editorCard.style.display = "none";
      if (typeof duration !== "undefined" && duration) {
        startSeconds = Math.min(Math.max(startSeconds, 0), duration);
        endSeconds = Math.max(
          startSeconds,
          Math.min(endSeconds || duration, duration),
        );
      }
      updateToolbarActionButtons();
      if (typeof renderTrim === "function") renderTrim();
    };
    window.clearGlobalSelection = clearGlobalSelection;

    selectTimelineItem = function (trackType, index, item, options = {}) {
      globalSelection = { track: trackType, index };
      selectedClipIndex = trackType === "video" ? index : -1;

      if (trackType === "video") {
        if (
          item &&
          typeof item.start === "number" &&
          typeof item.end === "number"
        ) {
          startSeconds = options.start ?? item.start;
          endSeconds = options.end ?? item.end;
        } else if (typeof duration !== "undefined" && duration) {
          startSeconds = options.start ?? startSeconds ?? 0;
          endSeconds = options.end ?? endSeconds ?? duration;
        }
      }

      if (trackType === "text" && item) {
        // Open the sidebar if collapsed
        const grid = document.querySelector(".ve-editor-grid");
        if (grid && grid.classList.contains("sidebar-collapsed")) {
          grid.classList.remove("sidebar-collapsed");
        }
        // Switch dock to Text tab
        const dockTextBtn = document.querySelector('.ve-dock-btn[data-tab="text"], .ve-tool-tab[data-tab="text"]');
        if (dockTextBtn && !dockTextBtn.classList.contains("active")) {
          dockTextBtn.click();
        }
        // If playhead is outside text duration, sync playhead to text start so it's visible on video stage
        const videoEl = document.getElementById("main-video");
        const curT = videoEl ? sourceToTimelineTime(videoEl.currentTime) : 0;
        const oStart = parseFloat(item.start || 0);
        const oEnd = parseFloat(item.end || duration || 10);
        if (curT < oStart || curT > oEnd) {
          syncVideoElementToTimeline(oStart, true);
        }
        // Populate and display active text editor card
        const editorCard = document.getElementById("ve-text-editor-card");
        if (editorCard) {
          editorCard.style.display = "block";
          const input = document.getElementById("active-text-input");
          if (input) input.value = item.text || "";
          const sizeInput = document.getElementById("active-text-size");
          if (sizeInput) sizeInput.value = item.font_size || item.fontsize || 32;
          const colorInput = document.getElementById("active-text-color");
          if (colorInput) {
            let col = item.color || "#ffffff";
            if (col.toLowerCase() === "white") col = "#ffffff";
            if (col.toLowerCase() === "black") col = "#000000";
            if (col.startsWith("#")) colorInput.value = col;
          }
          const boldBtn = document.getElementById("btn-text-bold-toggle");
          if (boldBtn) {
            boldBtn.style.background = item.bold ? "#ede9fe" : "#ffffff";
            boldBtn.style.color = item.bold ? "#7c3aed" : "#334155";
          }
        }
      } else if (trackType !== "text") {
        const editorCard = document.getElementById("ve-text-editor-card");
        if (editorCard) editorCard.style.display = "none";
      }

      updateToolbarActionButtons();

      if (options.syncForm !== false && trackType === "text") {
        let selectedOverlayIndex = -1;
    const textFormEl = document.querySelector('form[action*="/text/"]');
        if (textFormEl) {
          textFormEl.querySelector("#id_text").value = item?.text || "";
          textFormEl.querySelector("#id_position").value =
            item?.position || "bottom";
          textFormEl.querySelector("#id_color").value = item?.color || "white";
          textFormEl.querySelector("#id_font_size").value =
            item?.font_size || 80;
          textFormEl.querySelector("#id_start_seconds").value =
            item?.start ?? startSeconds;
          textFormEl.querySelector("#id_end_seconds").value =
            item?.end ?? endSeconds;
        }
      } else if (options.syncForm !== false && trackType === "audio") {
        const bgForm = document.getElementById("bg-audio-form");
        if (bgForm) {
          bgForm.querySelector("#id_bg_volume").value = item?.bg_volume || 0.5;
          bgForm.querySelector("#id_video_volume").value =
            item?.video_volume || 1.0;
          bgForm.querySelector("#id_start_seconds").value =
            item?.start ?? startSeconds;
          bgForm.querySelector("#id_end_seconds").value =
            item?.end ?? endSeconds;
        }
      }

      if (typeof renderTrim === "function") renderTrim();
      if (typeof renderAllTimelineTracks === "function") renderAllTimelineTracks();
      if (typeof renderTextOverlays === "function") renderTextOverlays();
    };
    window.selectTimelineItem = selectTimelineItem;

    renderAllTimelineTracks = function () {
      ensureOriginalAudioTrackClip();
      if (window.dynamicTrackManager) {
        window.dynamicTrackManager.updateTrackVisibilities();
      }
      
      // Ensure we have a valid duration
      if (!duration || isNaN(duration) || duration <= 0) {
        if (window.REEL_PROJECT_DURATION && parseFloat(window.REEL_PROJECT_DURATION) > 0) {
          duration = parseFloat(window.REEL_PROJECT_DURATION);
          window.duration = duration;
        } else if (video && !isNaN(video.duration) && video.duration > 0) {
          duration = video.duration;
          window.duration = duration;
        }
      }

      if (!duration || isNaN(duration) || duration <= 0) {
        // Clear all track containers if no duration
        Object.keys(TRACK_CONFIG).forEach(trackType => {
          const container = document.getElementById(TRACK_CONFIG[trackType].containerId);
          if (container) container.innerHTML = "";
        });
        return;
      }

      const pxPerSecond = basePxPerSecond * zoomFactor;
      const parentWidth = trimTrack?.parentElement ? trimTrack.parentElement.clientWidth : 800;
      const totalWidth = Math.max(parentWidth, duration * pxPerSecond);

      syncEffectsToTrack();

      Object.keys(TRACK_CONFIG).forEach((trackType) => {
        const config = TRACK_CONFIG[trackType];
        const container = document.getElementById(config.containerId);
        if (!container) return;

        container.innerHTML = "";
        container.style.width = `${totalWidth}px`;

        const items = editorState[config.stateKey] || [];

        items.forEach((item, index) => {
          // Validate item data to prevent empty tracks
          if (!item || (item.start == null && item.end == null)) {
            console.warn(`Invalid ${trackType} item at index ${index}:`, item);
            return;
          }

          const startSec = item.start || 0;
          const endSec = item.end || duration;
          const leftPx = startSec * pxPerSecond;
          const widthPx = Math.max(20, (endSec - startSec) * pxPerSecond);

          const isSelected = (globalSelection.track === trackType && globalSelection.index === index);

          const el = document.createElement("div");
          el.className = `timeline-generic-block${trackType === 'audio' ? ' timeline-audio-block' : ''}${trackType === 'text' ? ' timeline-text-block' : ''}${isSelected ? ' selected timeline-item--selected' : ''}`;
          el.style.position = "absolute";
          el.style.left = `${leftPx}px`;
          el.style.width = `${widthPx}px`;
          el.style.height =
            trackType === "effect" ? "calc(100% - 16px)" : "100%";
          el.style.top = trackType === "effect" ? "8px" : "0";
          el.style.borderRadius = "4px";
          el.style.display = "flex";
          el.style.alignItems = "center";
          el.style.padding = trackType === "audio" ? "0" : "0 8px";
          el.style.boxSizing = "border-box";
          el.style.color = "white";
          el.style.fontSize = "12px";
          el.style.fontWeight = "600";
          el.style.overflow = "hidden";
          el.style.zIndex = "3";
          el.style.cursor = "grab";

          if (trackType === "audio") {
            el.style.background = isSelected ? "rgba(16, 185, 129, 0.28)" : "rgba(16, 185, 129, 0.18)";
            el.style.border = isSelected ? "1.5px solid #10b981" : "1px solid rgba(16, 185, 129, 0.5)";
            el.style.boxShadow = isSelected ? "0 0 0 2px rgba(16, 185, 129, 0.35)" : "0 1px 3px rgba(0, 0, 0, 0.05)";

            const audioTitle = item.name || (item.file ? item.file.split("/").pop() : "Original Audio");
            el.innerHTML = `
              <div class="audio-clip-header">
                <i data-lucide="music" style="width:11px;height:11px;flex-shrink:0;"></i>
                <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:140px;">${audioTitle}</span>
              </div>
            `;
          } else {
            el.style.background = config.color;
            el.style.border = isSelected ? `2px solid ${config.borderColor}` : `1px solid ${config.borderColor}`;
            if (isSelected) {
              el.style.boxShadow = `0 0 0 2px rgba(13, 148, 136, 0.4)`;
            }
            let name = item.name || item.text || "Item";
            el.innerHTML = `<i data-lucide="${config.icon}" style="width:13px;height:13px;margin-right:6px;flex-shrink:0;position:relative;z-index:2;"></i> <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;position:relative;z-index:2;text-shadow:0 1px 3px rgba(0,0,0,0.7);">${name}</span>`;
          }

          if (trackType === "audio") {
            const canvas = document.createElement("canvas");
            canvas.className = "audio-waveform-canvas";
            canvas.style.position = "absolute";
            canvas.style.inset = "0";
            canvas.style.width = "100%";
            canvas.style.height = "100%";
            canvas.style.pointerEvents = "none";
            canvas.style.zIndex = "1";
            canvas.style.opacity = "0.95";
            const itemTrimStart = item.trimStart != null ? item.trimStart : (item.start || 0);
            const itemTrimEnd = item.trimEnd != null ? item.trimEnd : (item.end || duration);
            const srcDur = parseFloat(window.REEL_PROJECT_DURATION) || duration || 1;
            const startR = Math.max(0, Math.min(1, itemTrimStart / srcDur));
            const endR = Math.max(0, Math.min(1, itemTrimEnd / srcDur));
            renderWaveformToCanvas(canvas, window.audioPeaksCache, widthPx, 36, startR, endR);
            el.appendChild(canvas);
          }

          // Unified resize handle creation for all track types
          const createResizeHandle = (side) => {
            const handle = document.createElement("div");
            handle.className = `${trackType}-resize-handle handle-${side}`;
            handle.style.position = "absolute";
            handle.style[side] = "0";
            handle.style.top = "0";
            handle.style.bottom = "0";
            handle.style.width = "8px";
            handle.style.background = trackType === "audio" ? "#10b981" : "rgba(255, 255, 255, 0.65)";
            handle.style.borderRadius = "2px";
            handle.style.cursor = "ew-resize";
            handle.style.zIndex = "6";
            handle.style.opacity = isSelected ? "1" : "0.65";
            handle.style.transition = "background 0.15s, width 0.15s, opacity 0.15s";
            
            // Hover effect
            handle.addEventListener("mouseenter", () => {
              handle.style.width = "10px";
              handle.style.opacity = "1";
            });
            handle.addEventListener("mouseleave", () => {
              handle.style.width = "8px";
              handle.style.opacity = isSelected ? "1" : "0.65";
            });
            
            return handle;
          };

          const handleL = createResizeHandle("left");
          const handleR = createResizeHandle("right");

          let dragOffsetSeconds = 0;
          const startBlockDrag = (clientX) => {
            const itemDuration = Math.max(
              0.5,
              (item.end || duration) - (item.start || 0),
            );
            if (trackType === "audio") {
              if (item.trimStart == null) item.trimStart = parseFloat((item.start || 0).toFixed(2));
              if (item.trimEnd == null) item.trimEnd = parseFloat(((item.trimStart || 0) + itemDuration).toFixed(2));
            }
            dragOffsetSeconds = getSecondsFromX(clientX) - (item.start || 0);
            el.style.cursor = "grabbing";
            const move = (moveEvent) => {
              const moveClientX = moveEvent.touches
                ? moveEvent.touches[0].clientX
                : moveEvent.clientX;
              let rawStart = getSecondsFromX(moveClientX) - dragOffsetSeconds;
              if (typeof snapTimeToPoints === "function") {
                const snapped = snapTimeToPoints(rawStart);
                rawStart = snapped.time;
              }
              const newStart = Math.max(
                0,
                Math.min(
                  duration - itemDuration,
                  rawStart,
                ),
              );
              item.start = parseFloat(newStart.toFixed(2));
              item.end = parseFloat((newStart + itemDuration).toFixed(2));
              item.duration = itemDuration;
              if (trackType === "audio") {
                item.user_dragged = true;
                if (!editorState.audio_separated) {
                  editorState.audio_separated = true;
                  if (typeof updateSeparateAudioUI === "function") updateSeparateAudioUI();
                }
              }
              // Notice: trimStart and trimEnd DO NOT change during dragging!
              el.style.left = `${item.start * pxPerSecond}px`;
              el.style.width = `${Math.max(20, (item.end - item.start) * pxPerSecond)}px`;
              if (typeof renderTrim === "function") renderTrim();
            };
            const stop = () => {
              el.style.cursor = "grab";
              window.removeEventListener("mousemove", move);
              window.removeEventListener("mouseup", stop);
              window.removeEventListener("touchmove", move);
              window.removeEventListener("touchend", stop);
              autoSaveTimeline();
              if (typeof syncAudioPreviewToTimeline === "function") {
                syncAudioPreviewToTimeline(timelineCurrentTime || 0, true);
              }
            };
            window.addEventListener("mousemove", move);
            window.addEventListener("mouseup", stop);
            window.addEventListener("touchmove", move, { passive: false });
            window.addEventListener("touchend", stop);
          };

          el.addEventListener("mousedown", (e) => {
            if (e.target.closest(".trim-handle") || e.target.classList.contains("audio-resize-handle") || e.target.classList.contains("text-resize-handle")) return;
            selectTimelineItem(trackType, index, item, { start: startSec, end: endSec });
            e.preventDefault();
            e.stopPropagation();
            startBlockDrag(e.clientX);
          });
          el.addEventListener(
            "touchstart",
            (e) => {
              if (e.target.closest(".trim-handle") || e.target.classList.contains("audio-resize-handle") || e.target.classList.contains("text-resize-handle")) return;
              selectTimelineItem(trackType, index, item, { start: startSec, end: endSec });
              e.preventDefault();
              e.stopPropagation();
              startBlockDrag(e.touches[0].clientX);
            },
            { passive: false },
          );

          el.appendChild(handleL);
          el.appendChild(handleR);
          container.appendChild(el);

          el.addEventListener("click", (e) => {
            e.stopPropagation();
            selectTimelineItem(trackType, index, item, {
              start: startSec,
              end: endSec,
            });
          });

          if (trackType === "text") {
            el.addEventListener("dblclick", (e) => {
              e.stopPropagation();
              selectTimelineItem("text", index, item);
              const sidebarInput = document.getElementById("active-text-input");
              if (sidebarInput) {
                sidebarInput.focus();
                sidebarInput.select();
              }
            });
          }

          if (typeof setupDrag === "function") {
            setupDrag(handleL, (clientX) => {
              let s = getSecondsFromX(clientX);
              if (s < 0) s = 0;
              if (s > (item.end || endSec) - 0.5) s = (item.end || endSec) - 0.5;
              const delta = s - (item.start || 0);
              item.start = parseFloat(s.toFixed(2));
              if (trackType === "audio") {
                const curTrimStart = item.trimStart != null ? item.trimStart : (item.start || 0);
                item.trimStart = parseFloat((curTrimStart + delta).toFixed(2));
              }
              renderAllTimelineTracks();
              if (window.updateLocalState)
                window.updateLocalState("Trim", `Trimmed ${trackType} item`);
              if (typeof syncAudioPreviewToTimeline === "function") {
                syncAudioPreviewToTimeline(timelineCurrentTime || 0, true);
              }
            });

            setupDrag(handleR, (clientX) => {
              let e = getSecondsFromX(clientX);
              if (e > duration) e = duration;
              if (e < (item.start || startSec) + 0.5) e = (item.start || startSec) + 0.5;
              const delta = (item.end || duration) - e;
              item.end = parseFloat(e.toFixed(2));
              if (trackType === "audio") {
                const curTrimEnd = item.trimEnd != null ? item.trimEnd : (item.end || duration);
                item.trimEnd = parseFloat((curTrimEnd - delta).toFixed(2));
              }
              renderAllTimelineTracks();
              if (window.updateLocalState)
                window.updateLocalState("Trim", `Trimmed ${trackType} item`);
              if (typeof syncAudioPreviewToTimeline === "function") {
                syncAudioPreviewToTimeline(timelineCurrentTime || 0, true);
              }
            });
          }
        });

        // Inline Canva-style Add button for Audio & Text tracks
        if (trackType === "audio" || trackType === "text") {
          let maxEnd = 0;
          items.forEach((item) => {
            const endSec = item.end != null ? item.end : (item.start || 0);
            if (endSec > maxEnd) maxEnd = endSec;
          });

          const inlineAddBtn = document.createElement("button");
          inlineAddBtn.type = "button";
          inlineAddBtn.className = `timeline-inline-add-btn timeline-inline-add-${trackType}-btn`;
          inlineAddBtn.style.left = `${maxEnd * pxPerSecond + 6}px`;
          const btnLabel = trackType === "audio" ? "Add Audio" : "Add Text";
          inlineAddBtn.innerHTML = `<i data-lucide="plus"></i> <span>${btnLabel}</span>`;

          inlineAddBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            const grid = document.querySelector(".ve-editor-grid");
            if (grid) grid.classList.remove("sidebar-collapsed");

            if (trackType === "audio") {
              const dockUploadBtn = document.querySelector('.ve-dock-btn[data-tab="import"], .ve-tool-tab[data-tab="import"]');
              if (dockUploadBtn) dockUploadBtn.click();
              const audioCatBtn = document.querySelector('.ve-category-btn[data-category="audio"]');
              if (audioCatBtn) audioCatBtn.click();
            } else if (trackType === "text") {
              const dockTextBtn = document.querySelector('.ve-dock-btn[data-tab="text"], .ve-tool-tab[data-tab="text"]');
              if (dockTextBtn) dockTextBtn.click();
            }
          });
          container.appendChild(inlineAddBtn);
        }
      });

      if (typeof lucide !== "undefined") lucide.createIcons();
      updateTrackRowVisibility();
    };
    window.renderAllTimelineTracks = renderAllTimelineTracks;

    function syncEffectsToTrack() {
      editorState.active_effects = editorState.active_effects || [];
      if (editorState.active_effects.length === 0) {
        if (editorState.grayscale)
          editorState.active_effects.push({
            name: "Grayscale",
            type: "grayscale",
            start: 0,
            end: duration,
          });
        if (editorState.rotate)
          editorState.active_effects.push({
            name: `Rotate (${editorState.rotate}°)`,
            type: "rotate",
            start: 0,
            end: duration,
          });
        if (editorState.fade)
          editorState.active_effects.push({
            name: "Fade",
            type: "fade",
            start: 0,
            end: duration,
          });
      }
    }

    function updateTrackRowVisibility() {
      if (window.dynamicTrackManager) {
        window.dynamicTrackManager.updateTrackVisibilities();
      } else {
        const textTrackRow = document.querySelector(".text-track-row");
        const audioTrackRow = document.querySelector(".audio-track-row");
        const videoTrackRow = document.querySelector(".video-track-row");

        if (videoTrackRow && videoTrackRow.style) videoTrackRow.style.setProperty("display", "flex", "important");
        if (audioTrackRow && audioTrackRow.style) audioTrackRow.style.setProperty("display", "flex", "important");
        if (textTrackRow && textTrackRow.style) textTrackRow.style.setProperty("display", "flex", "important");

        const trackBadge = document.getElementById("tb-bottom-track-info");
        if (trackBadge) {
          trackBadge.innerHTML = `<i data-lucide="layers" style="width:13px;height:13px;color:var(--ve-primary);"></i> 3 Tracks`;
          if (typeof lucide !== "undefined") lucide.createIcons();
        }
      }
    }

    // --- Intercept forms to handle preview changes and update state ---

    // Volume adjustments are handled by form submission to the backend.

    // All forms (Speed, Volume, Mute, Text, Rotate, Grayscale, Fade) now submit directly to the server for processing.

    // Master Export submit (AJAX JSON endpoint submission)
    const exportBtn = document.getElementById("btn-master-export");
    if (exportBtn) {
      exportBtn.addEventListener("click", async () => {
        const overlay = document.getElementById("processing-overlay");
        if (overlay) {
          overlay.style.display = "flex";
          const txt = overlay.querySelector("p");
          if (txt) txt.textContent = "Processing edits with FFmpeg...";
        }

        // Append trim configurations directly from visual variables
        editorState.trim.start = startSeconds;
        editorState.trim.end = endSeconds;

        // Get mode and transitions from Trim options
        const modeRadio = document.querySelector(
          'input[name="trim_mode"]:checked',
        );
        if (modeRadio) editorState.trim.mode = modeRadio.value;
        editorState.trim.fade_in =
          document.querySelector('input[name="fade_in"]')?.checked || false;
        editorState.trim.fade_out =
          document.querySelector('input[name="fade_out"]')?.checked || false;

        const payload = buildTimelinePayload();

        try {
          const csrf = document.querySelector(
            'input[name="csrfmiddlewaretoken"]',
          )?.value;
          const res = await fetch(window.location.pathname + "export/", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrf,
            },
            body: JSON.stringify(payload),
          });
          const data = await res.json();
          if (data.status === "success") {
            window.location.reload();
          } else {
            alert("Export failed: " + (data.error || "Unknown error"));
            if (overlay) overlay.style.display = "none";
          }
        } catch (err) {
          alert("Error exporting: " + err);
          if (overlay) overlay.style.display = "none";
        }
      });
    }

    // Add text caption directly from timeline
    const timelineAddTextBtn = document.getElementById("timeline-add-text-btn");
    if (timelineAddTextBtn) {
      timelineAddTextBtn.addEventListener("click", () => {
        const text = prompt("Enter text overlay:");
        if (!text || text.trim() === "") return;

        // Switch to the Text tool tab
        const textTab = document.querySelector('.tool-tab[data-tab="text"]');
        if (textTab) {
          textTab.click();
        }

        // Pre-fill fields with current playhead time
        const start = parseFloat(sourceToTimelineTime(video.currentTime).toFixed(2));
        const end = parseFloat(Math.min(duration, start + 3).toFixed(2));

        const overlay = {
          text: text.trim(),
          position: "bottom",
          color: "white",
          font_size: 80,
          start: start,
          end: end,
        };

        editorState.text_overlays = [overlay]; // Stage this overlay client-side
        selectedOverlayIndex = 0;

        renderTextOverlays();
        renderAllTimelineTracks();
        let selectedOverlayIndex = -1;
    const textFormEl = document.querySelector('form[action*="/text/"]');
        if (textFormEl) {
          textFormEl.querySelector("#id_text").value = text.trim();
          textFormEl.querySelector('input[name="start_seconds"]').value = start;
          textFormEl.querySelector('input[name="end_seconds"]').value = end;

          // Focus the text input field in case they want to refine it
          const textInput = textFormEl.querySelector("#id_text");
          if (textInput) {
            textInput.focus();
            textInput.select();
          }
        }
      });
    }

    // --- Modular Track Manager & Dynamic Timeline Architecture ---
    class DynamicTrackManager {
      constructor() {
        this.tracks = [];
        this.initDefaultTracks();
      }

      initDefaultTracks() {
        // Initialize with all timeline tracks visible (Canva-style multi-track timeline)
        this.tracks = [
          {
            id: "video-track-row",
            type: "video",
            name: "Video Track",
            order: 0,
            height: 56,
            visible: true,
            locked: false,
            clips: [],
          },
          {
            id: "audio-track-row",
            type: "audio",
            name: "Audio Track",
            order: 1,
            height: 36,
            visible: true,
            locked: false,
            clips: [],
          },
          {
            id: "text-track-row",
            type: "text",
            name: "Text Overlay Track",
            order: 2,
            height: 36,
            visible: true,
            locked: false,
            clips: [],
          },
        ];
      }

      getTracks() {
        return this.tracks;
      }

      addTrack(trackObj) {
        this.tracks.push(trackObj);
        this.updateTrackBadge();
      }

      removeTrack(trackId) {
        this.tracks = this.tracks.filter((t) => t.id !== trackId);
        this.updateTrackBadge();
      }

      updateTrackBadge() {
        const trackBadge = document.getElementById("tb-bottom-track-info");
        const trackCountDisplay = document.getElementById("track-count-display");
        const activeCount = this.tracks.filter((t) => t.visible !== false).length;
        if (trackBadge && trackCountDisplay) {
          trackCountDisplay.textContent = `${activeCount} Track${activeCount === 1 ? "" : "s"}`;
          if (typeof lucide !== "undefined") lucide.createIcons();
        } else if (trackBadge) {
          trackBadge.innerHTML = `<i data-lucide="layers" style="width:13px;height:13px;color:var(--ve-primary);"></i> ${activeCount} Track${activeCount === 1 ? "" : "s"}`;
          if (typeof lucide !== "undefined") lucide.createIcons();
        }
      }

      updateTrackVisibilities() {
        this.tracks.forEach((track) => {
          track.visible = true;
        });
        this.renderAllTracks();
      }

      renderAllTracks() {
        this.tracks.forEach((track) => {
          const trackEl = document.getElementById(track.id) || document.querySelector(`.${track.id}`);
          if (trackEl && trackEl.style && typeof trackEl.style.setProperty === "function") {
            trackEl.style.setProperty("display", "flex", "important");
          }
        });
        this.updateTrackBadge();
      }
    }

    const trackManager = new DynamicTrackManager();
    window.dynamicTrackManager = trackManager;
    trackManager.updateTrackVisibilities();

    // --- Horizontal Scroll Sync between Track Scroll Area and Pinned Ruler Header ---
    const mainScrollArea = document.getElementById("timeline-scroll-area");
    const rulerHeaderContainer = document.getElementById("trim-ruler-header");
    if (mainScrollArea && rulerHeaderContainer) {
      mainScrollArea.addEventListener("scroll", () => {
        rulerHeaderContainer.scrollLeft = mainScrollArea.scrollLeft;
      });
    }


    // --- Collapsible & Resizable Timeline Panel (Canva / CapCut Style) ---
    const timelineResizer = document.getElementById("timeline-resizer");
    const collapseBtn = document.getElementById("tb-collapse-timeline");
    const collapseIcon = document.getElementById("collapse-icon");
    const collapseText = document.getElementById("collapse-text");

    let lastExpandedHeight =
      parseFloat(localStorage.getItem("ve_timeline_height")) || 240;
    let isCollapsedState =
      localStorage.getItem("ve_timeline_collapsed") === "true";

    const setCollapseUIState = (collapsed) => {
      if (collapsed) {
        if (trimContainer.classList.contains("fullscreen-mode")) {
          trimContainer.classList.remove("fullscreen-mode");
        }
        trimContainer.classList.add("timeline-collapsed");
        trimContainer.style.height = "42px";
        if (collapseText) collapseText.textContent = "Expand";
        if (collapseIcon)
          collapseIcon.setAttribute("data-lucide", "chevron-up");
      } else {
        trimContainer.classList.remove("timeline-collapsed");
        const restoreHeight = Math.max(180, lastExpandedHeight || 240);
        trimContainer.style.height = `${restoreHeight}px`;
        if (collapseText) collapseText.textContent = "Minimize";
        if (collapseIcon)
          collapseIcon.setAttribute("data-lucide", "chevron-down");
      }
      if (typeof lucide !== "undefined") lucide.createIcons();
      localStorage.setItem(
        "ve_timeline_collapsed",
        collapsed ? "true" : "false",
      );
      _lastClipRenderKey = "";
      updateRuler();
      renderClipBlocks();
      renderAllTimelineTracks();
      updateOriginalAudioWaveform();
      renderTrim();
      renderTextOverlays();
    };

    const toggleCollapse = () => {
      const nowCollapsed =
        !trimContainer.classList.contains("timeline-collapsed");
      setCollapseUIState(nowCollapsed);
    };

    if (collapseBtn) {
      collapseBtn.addEventListener("click", toggleCollapse);
    }

    if (timelineResizer) {
      timelineResizer.addEventListener("dblclick", toggleCollapse);

      let isResizing = false;
      let startY = 0;
      let startH = 0;

      const onStartResize = (e) => {
        e.preventDefault();
        e.stopPropagation();
        isResizing = true;
        trimContainer.classList.add("is-dragging");
        timelineResizer.classList.add("is-dragging");
        startY = e.touches ? e.touches[0].clientY : e.clientY;
        startH = trimContainer.getBoundingClientRect().height;

        document.addEventListener("mousemove", onResizing);
        document.addEventListener("mouseup", onStopResize);
        document.addEventListener("touchmove", onResizing, { passive: false });
        document.addEventListener("touchend", onStopResize);
      };

      const onResizing = (e) => {
        if (!isResizing) return;
        if (e.cancelable) e.preventDefault();
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        const deltaY = startY - clientY; // Dragging UP increases height
        let newH = startH + deltaY;

        const maxH = Math.min(window.innerHeight * 0.75, 650);
        newH = Math.max(124, Math.min(maxH, newH));

        if (newH <= 135) {
          trimContainer.classList.add("timeline-collapsed");
          trimContainer.style.height = `${newH}px`;
          if (collapseText) collapseText.textContent = "Expand";
          if (collapseIcon)
            collapseIcon.setAttribute("data-lucide", "chevron-up");
        } else {
          trimContainer.classList.remove("timeline-collapsed");
          trimContainer.style.height = `${newH}px`;
          lastExpandedHeight = newH;
          if (collapseText) collapseText.textContent = "Minimize";
          if (collapseIcon)
            collapseIcon.setAttribute("data-lucide", "chevron-down");
        }
        if (typeof lucide !== "undefined") lucide.createIcons();
        updateRuler();
        renderTrim();
        renderTextOverlays();
      };

      const onStopResize = () => {
        if (!isResizing) return;
        isResizing = false;
        trimContainer.classList.remove("is-dragging");
        timelineResizer.classList.remove("is-dragging");
        document.removeEventListener("mousemove", onResizing);
        document.removeEventListener("mouseup", onStopResize);
        document.removeEventListener("touchmove", onResizing);
        document.removeEventListener("touchend", onStopResize);

        const finalH = trimContainer.getBoundingClientRect().height;
        const isNowCollapsed = finalH <= 135;
        localStorage.setItem(
          "ve_timeline_collapsed",
          isNowCollapsed ? "true" : "false",
        );
        if (!isNowCollapsed) {
          localStorage.setItem("ve_timeline_height", finalH);
          lastExpandedHeight = finalH;
        }
      };

      timelineResizer.addEventListener("mousedown", onStartResize);
      timelineResizer.addEventListener("touchstart", onStartResize, {
        passive: false,
      });
    }

    // Restore initial state from localStorage
    if (isCollapsedState) {
      setCollapseUIState(true);
    } else if (lastExpandedHeight && lastExpandedHeight !== 240) {
      trimContainer.style.height = `${lastExpandedHeight}px`;
    }

    const playheadTooltip = document.getElementById("playhead-tooltip");

    // Throttle helper to prevent spamming video seek requests during fast drag
    function throttle(func, limit) {
      let inThrottle;
      return function (...args) {
        if (!inThrottle) {
          func.apply(this, args);
          inThrottle = true;
          setTimeout(() => (inThrottle = false), limit);
        }
      };
    }

    let dragLastTime = 0;
    const seekVideoThrottled = throttle((time) => {
      syncVideoElementToTimeline(time);
    }, 60);

    // Drag or click on timeline ruler to seek video with magnetic snapping
    setupDrag(
      trimRuler,
      (clientX) => {
        let time = getSecondsFromX(clientX);
        const snapped = snapTimeToPoints(time);
        time = snapped.time;
        if (time < 0) time = 0;
        if (time > duration) time = duration;
        dragLastTime = time;

        if (!video.paused) {
          video.pause();
        }
        seekVideoThrottled(time);

        const pxPerSecond = basePxPerSecond * zoomFactor;
        trimPlayhead.style.left = `${time * pxPerSecond}px`;
        if (currentDisplay) currentDisplay.textContent = formatTime(time);
        const timeCurrentEl = document.getElementById("video-time-current");
        if (timeCurrentEl) {
          timeCurrentEl.textContent = formatTime(time);
        }
        updateVideoProgress();

        trimPlayhead.classList.add("dragging");
        if (playheadTooltip) {
          playheadTooltip.textContent = formatTime(time);
        }
      },
      () => {
        hideSnapGuide();
        trimPlayhead.classList.remove("dragging");
        syncVideoElementToTimeline(dragLastTime, true);
        updatePlayheadSmooth();
      },
    );

    // Grab and drag the playhead needle/cap directly with magnetic snapping
    setupDrag(
      trimPlayhead,
      (clientX) => {
        let time = getSecondsFromX(clientX);
        const snapped = snapTimeToPoints(time);
        time = snapped.time;
        if (time < 0) time = 0;
        if (time > duration) time = duration;
        dragLastTime = time;

        if (!video.paused) {
          video.pause();
        }
        seekVideoThrottled(time);

        const pxPerSecond = basePxPerSecond * zoomFactor;
        trimPlayhead.style.left = `${time * pxPerSecond}px`;
        if (currentDisplay) currentDisplay.textContent = formatTime(time);
        const timeCurrentEl = document.getElementById("video-time-current");
        if (timeCurrentEl) {
          timeCurrentEl.textContent = formatTime(time);
        }
        updateVideoProgress();

        trimPlayhead.classList.add("dragging");
        if (playheadTooltip) {
          playheadTooltip.textContent = formatTime(time);
        }
      },
      () => {
        hideSnapGuide();
        trimPlayhead.classList.remove("dragging");
        syncVideoElementToTimeline(dragLastTime, true);
        updatePlayheadSmooth();
      },
    );

    const timelineAddAudioBtn = document.getElementById(
      "timeline-add-audio-btn",
    );
    const audioFileIn = document.getElementById("id_audio_file");
    let audioOverlay = null; // To store current audio overlay info

    if (audioFileIn) {
      audioFileIn.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // Default start/end
        let start = parseFloat(sourceToTimelineTime(video.currentTime).toFixed(2));
        let end = parseFloat(Math.min(duration, start + 10).toFixed(2));

        audioOverlay = {
          file: file,
          filename: file.name,
          start: start,
          end: end,
        };

        // Update form inputs
        const bgForm = document.getElementById("bg-audio-form");
        if (bgForm) {
          const startIn = bgForm.querySelector('input[name="start_seconds"]');
          const endIn = bgForm.querySelector('input[name="end_seconds"]');
          if (startIn) startIn.value = start;
          if (endIn) endIn.value = end;
        }

        renderAudioOverlay(); // Render on timeline
      });
    }

    function renderAudioOverlay() {
      const audioTrack = document.getElementById("audio-track");
      if (!audioTrack || !duration || !audioOverlay) return;
      if (editorState.background_audios && editorState.background_audios.length > 0 && !audioOverlay.file) {
        return;
      }

      // Remove existing block if any
      audioTrack
        .querySelectorAll(".temp-audio-block")
        .forEach((el) => el.remove());

      const pxPerSecond = basePxPerSecond * zoomFactor;
      const leftPx = audioOverlay.start * pxPerSecond;
      const widthPx = (audioOverlay.end - audioOverlay.start) * pxPerSecond;

      const el = document.createElement("div");
      el.className = "temp-audio-block audio-block";
      el.style.position = "absolute";
      el.style.left = `${leftPx}px`;
      el.style.width = `${widthPx}px`;
      el.style.height = "100%";
      el.style.top = "0";
      el.style.background = "linear-gradient(135deg, #10b981 0%, #059669 100%)";
      el.style.border = "2.5px solid #34d399";
      el.style.borderRadius = "10px";
      el.style.display = "flex";
      el.style.alignItems = "center";
      el.style.padding = "0 8px";
      el.style.boxSizing = "border-box";
      el.style.zIndex = "3";
      el.style.overflow = "hidden";

      // Waveform
      const waveformContainer = document.createElement("div");
      waveformContainer.innerHTML = generateWaveformSvg(
        widthPx,
        44,
        audioOverlay.filename.length,
      );
      waveformContainer.style.position = "absolute";
      waveformContainer.style.inset = "0";
      waveformContainer.style.display = "flex";
      waveformContainer.style.alignItems = "center";
      waveformContainer.style.opacity = "0.65";
      el.appendChild(waveformContainer);

      // Left resize handle
      const handleL = document.createElement("div");
      handleL.style.position = "absolute";
      handleL.style.left = "-4px";
      handleL.style.top = "0";
      handleL.style.width = "8px";
      handleL.style.height = "100%";
      handleL.style.cursor = "ew-resize";
      handleL.style.zIndex = "4";

      const tooltipL = document.createElement("div");
      tooltipL.style.position = "absolute";
      tooltipL.style.top = "-24px";
      tooltipL.style.left = "50%";
      tooltipL.style.transform = "translateX(-50%)";
      tooltipL.style.background = "#00bfff";
      tooltipL.style.color = "white";
      tooltipL.style.padding = "2px 6px";
      tooltipL.style.borderRadius = "4px";
      tooltipL.style.fontSize = "11px";
      tooltipL.style.whiteSpace = "nowrap";
      tooltipL.textContent = formatTime(audioOverlay.start);
      handleL.appendChild(tooltipL);

      // Right resize handle
      const handleR = document.createElement("div");
      handleR.style.position = "absolute";
      handleR.style.right = "-4px";
      handleR.style.top = "0";
      handleR.style.width = "8px";
      handleR.style.height = "100%";
      handleR.style.cursor = "ew-resize";
      handleR.style.zIndex = "4";

      const tooltipR = document.createElement("div");
      tooltipR.style.position = "absolute";
      tooltipR.style.top = "-24px";
      tooltipR.style.left = "50%";
      tooltipR.style.transform = "translateX(-50%)";
      tooltipR.style.background = "#00bfff";
      tooltipR.style.color = "white";
      tooltipR.style.padding = "2px 6px";
      tooltipR.style.borderRadius = "4px";
      tooltipR.style.fontSize = "11px";
      tooltipR.style.whiteSpace = "nowrap";
      tooltipR.textContent = formatTime(audioOverlay.end);
      handleR.appendChild(tooltipR);

      // Audio label/icon removed per user request

      // Cancel button (X)
      const cancelBtn = document.createElement("button");
      cancelBtn.innerHTML = "✖";
      cancelBtn.style.background = "none";
      cancelBtn.style.border = "none";
      cancelBtn.style.color = "#ff4d4d";
      cancelBtn.style.cursor = "pointer";
      cancelBtn.style.padding = "2px 4px";
      cancelBtn.style.marginRight = "6px";
      cancelBtn.style.fontSize = "11px";
      cancelBtn.style.flexShrink = "0";
      cancelBtn.title = "Cancel";
      cancelBtn.style.position = "relative";
      cancelBtn.style.zIndex = "1";
      cancelBtn.onclick = (e) => {
        e.stopPropagation();
        audioOverlay = null;
        audioTrack
          .querySelectorAll(".temp-audio-block")
          .forEach((el) => el.remove());
        if (audioFileIn) audioFileIn.value = "";
      };

      // Apply button
      const applyBtn = document.createElement("button");
      applyBtn.innerHTML = "Apply";
      applyBtn.style.background = "#52b788";
      applyBtn.style.color = "white";
      applyBtn.style.border = "none";
      applyBtn.style.borderRadius = "4px";
      applyBtn.style.padding = "2px 8px";
      applyBtn.style.cursor = "pointer";
      applyBtn.style.fontSize = "10px";
      applyBtn.style.fontWeight = "bold";
      applyBtn.style.flexShrink = "0";
      applyBtn.title = "Apply background audio";
      applyBtn.style.position = "relative";
      applyBtn.style.zIndex = "1";
      applyBtn.onclick = async (e) => {
        e.stopPropagation();
        const bgForm = document.getElementById("bg-audio-form");
        if (!bgForm) return;

        const fileInput = bgForm.querySelector('input[type="file"]');
        if (!fileInput || !fileInput.files.length) {
          console.warn("No audio file selected for background audio");
          return;
        }

        // Show processing overlay
        const processingOverlay = document.getElementById("processing-overlay");
        if (processingOverlay) {
          processingOverlay.style.display = "flex";
          const txt = processingOverlay.querySelector("p");
          if (txt) txt.textContent = "Adding background audio...";
        }

        applyBtn.disabled = true;
        applyBtn.textContent = "Uploading...";

        const csrf = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
        const formAction = bgForm.getAttribute("action") || "";
        const uploadUrl = formAction.replace("background-audio", "upload-audio-temp");

        const formData = new FormData();
        formData.append("audio_file", fileInput.files[0]);

        try {
          const res = await fetch(uploadUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrf },
            body: formData,
          });
          const data = await res.json();
          if (data.status === "success") {
            const startSec = audioOverlay ? audioOverlay.start : (parseFloat(bgForm.querySelector('input[name="start_seconds"]')?.value) || 0);
            const endSec = audioOverlay ? audioOverlay.end : (parseFloat(bgForm.querySelector('input[name="end_seconds"]')?.value) || null);

            editorState.background_audios = editorState.background_audios || [];
            editorState.background_audios.push({
              temp_path: data.temp_path,
              url: URL.createObjectURL(fileInput.files[0]),
              bg_volume: 0.5,
              video_volume: editorState.volume || 1.0,
              start: startSec,
              end: endSec,
              name: data.filename,
            });
            if (typeof applyCSSEffects === "function") applyCSSEffects();
            if (typeof renderAllTimelineTracks === "function") renderAllTimelineTracks();
            if (typeof autoSaveTimeline === "function") autoSaveTimeline();

            if (window.updateLocalState)
              window.updateLocalState("BgAudio", `Added background audio ${data.filename}`);

            // Clean up the temp overlay
            audioOverlay = null;
            const audioTrack = document.getElementById("audio-track");
            if (audioTrack) audioTrack.querySelectorAll(".temp-audio-block").forEach((el) => el.remove());
            if (fileInput) fileInput.value = "";
          } else {
            alert("Upload failed: " + (data.error || "Unknown error"));
          }
        } catch (err) {
          console.error("Background audio upload error:", err);
          alert("Error uploading audio: " + err.message);
        } finally {
          if (processingOverlay) processingOverlay.style.display = "none";
          applyBtn.disabled = false;
          applyBtn.textContent = "Apply";
        }
      };

      el.appendChild(handleL);
      el.appendChild(cancelBtn);
      el.appendChild(applyBtn);
      el.appendChild(handleR);

      // Drag the whole block
      setupDrag(el, (clientX) => {
        const pxPerSec = basePxPerSecond * zoomFactor;
        let newStart = getSecondsFromX(clientX);
        if (newStart < 0) newStart = 0;
        const blockDur = audioOverlay.end - audioOverlay.start;
        if (newStart + blockDur > duration) newStart = duration - blockDur;

        audioOverlay.start = parseFloat(newStart.toFixed(2));
        audioOverlay.end = parseFloat((newStart + blockDur).toFixed(2));

        // Update styles directly to prevent recursive render glitches
        el.style.left = `${audioOverlay.start * pxPerSec}px`;
        if (tooltipL) tooltipL.textContent = formatTime(audioOverlay.start);
        if (tooltipR) tooltipR.textContent = formatTime(audioOverlay.end);

        // Update form inputs
        const bgForm = document.getElementById("bg-audio-form");
        if (bgForm) {
          const startIn = bgForm.querySelector('input[name="start_seconds"]');
          const endIn = bgForm.querySelector('input[name="end_seconds"]');
          if (startIn) startIn.value = audioOverlay.start;
          if (endIn) endIn.value = audioOverlay.end;
        }
      });

      // Left handle drag
      setupDrag(handleL, (clientX) => {
        const pxPerSec = basePxPerSecond * zoomFactor;
        let newStart = getSecondsFromX(clientX);
        if (newStart < 0) newStart = 0;
        if (newStart > audioOverlay.end - 0.5)
          newStart = audioOverlay.end - 0.5;

        audioOverlay.start = parseFloat(newStart.toFixed(2));

        // Update styles directly to prevent recursive render glitches
        el.style.left = `${audioOverlay.start * pxPerSec}px`;
        el.style.width = `${(audioOverlay.end - audioOverlay.start) * pxPerSec}px`;
        if (tooltipL) tooltipL.textContent = formatTime(audioOverlay.start);

        const bgForm = document.getElementById("bg-audio-form");
        if (bgForm) {
          const startIn = bgForm.querySelector('input[name="start_seconds"]');
          if (startIn) startIn.value = audioOverlay.start;
        }
      });

      // Right handle drag
      setupDrag(handleR, (clientX) => {
        const pxPerSec = basePxPerSecond * zoomFactor;
        let newEnd = getSecondsFromX(clientX);
        if (newEnd > duration) newEnd = duration;
        if (newEnd < audioOverlay.start + 0.5)
          newEnd = audioOverlay.start + 0.5;

        audioOverlay.end = parseFloat(newEnd.toFixed(2));

        // Update styles directly to prevent recursive render glitches
        el.style.width = `${(audioOverlay.end - audioOverlay.start) * pxPerSec}px`;
        if (tooltipR) tooltipR.textContent = formatTime(audioOverlay.end);

        const bgForm = document.getElementById("bg-audio-form");
        if (bgForm) {
          const endIn = bgForm.querySelector('input[name="end_seconds"]');
          if (endIn) endIn.value = audioOverlay.end;
        }
      });

      audioTrack.appendChild(el);
      updateTrackRowVisibility();
    }

    if (timelineAddAudioBtn) {
      timelineAddAudioBtn.addEventListener("click", () => {
        if (typeof UnifiedMediaUploader !== "undefined") {
          UnifiedMediaUploader.openPicker({
            accept: "audio/*",
            autoInsert: true,
            targetTrack: "audio"
          });
        }
      });
    }
    // --- Zoom Control Function & Listeners ---
    function applyTimelineZoom(newZoomFactor) {
      zoomFactor = Math.max(0.01, Math.min(20.0, newZoomFactor));
      window.zoomFactor = zoomFactor;
      _lastClipRenderKey = ""; // Invalidate clip cache so blocks are resized and re-rendered

      updateRuler();
      renderClipBlocks();
      renderAllTimelineTracks();
      updateOriginalAudioWaveform();
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
    }

    if (btnZoomIn) {
      btnZoomIn.addEventListener("click", () => {
        applyTimelineZoom(zoomFactor * 1.35);
      });
    }

    if (btnZoomOut) {
      btnZoomOut.addEventListener("click", () => {
        applyTimelineZoom(zoomFactor / 1.35);
      });
    }

    if (btnZoomFit) {
      btnZoomFit.addEventListener("click", () => {
        const scrollArea = document.getElementById("timeline-scroll-area");
        const availableW = (scrollArea ? scrollArea.clientWidth : (trimTrack && trimTrack.parentElement ? trimTrack.parentElement.clientWidth : 800)) - 48;
        const dur = duration || window.duration || (video && video.duration) || 1;
        if (availableW > 50 && dur > 0) {
          const fitFactor = availableW / (dur * basePxPerSecond);
          applyTimelineZoom(fitFactor);
          if (scrollArea) scrollArea.scrollLeft = 0;
        }
      });
    }

    window.applyTimelineZoom = applyTimelineZoom;
    window.clearGlobalSelection = clearGlobalSelection;
    window.selectTimelineItem = selectTimelineItem;
    window.renderAllTimelineTracks = renderAllTimelineTracks;

