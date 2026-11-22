/**
 * Video Editor Module — Canva Text Presets & Live Canvas Overlays
 */
  // ---- Canva Text Presets Quick Insert -------------------------------
  const initCanvaTextPresets = () => {
    const btnAddTextbox = document.getElementById("btn-quick-add-text");
    const presetCards = document.querySelectorAll(".ve-preset-card");

    const addTextPreset = (text, fontSize, isBold = false) => {
      const videoEl = document.getElementById("main-video");
      const currentPlayhead = videoEl ? sourceToTimelineTime(videoEl.currentTime) : 0.0;
      const dur = window.REEL_PROJECT_DURATION || (videoEl ? videoEl.duration : 10) || 10;
      const sSec = Math.max(0, currentPlayhead);
      const eSec = Math.min(dur, sSec + 4.0);

      editorState.text_overlays = editorState.text_overlays || [];
      const newOverlay = {
        text: text,
        position: "center",
        color: "#ffffff",
        font_size: fontSize,
        fontsize: fontSize,
        bold: isBold,
        start: parseFloat(sSec.toFixed(2)),
        end: parseFloat((eSec > sSec ? eSec : sSec + 3.0).toFixed(2)),
      };
      editorState.text_overlays.push(newOverlay);

      if (typeof renderTextOverlays === "function") renderTextOverlays();
      if (typeof renderAllTimelineTracks === "function") renderAllTimelineTracks();
      if (typeof updatePlayheadSmooth === "function") updatePlayheadSmooth();
      if (typeof selectTimelineItem === "function") {
        selectTimelineItem("text", editorState.text_overlays.length - 1, newOverlay);
      }
      if (typeof autoSaveTimeline === "function") autoSaveTimeline();

      if (window.updateLocalState) {
        window.updateLocalState("Text", `Added text: "${text}"`);
      }

      const advInput = document.getElementById("id_text");
      if (advInput) advInput.value = text;
      const advSize = document.getElementById("id_font_size");
      if (advSize) advSize.value = fontSize;

      const sidebarInput = document.getElementById("active-text-input");
      if (sidebarInput) {
        sidebarInput.focus();
        sidebarInput.select();
      }
    };

    if (btnAddTextbox) {
      btnAddTextbox.addEventListener("click", () => {
        addTextPreset("Your text here", 36, false);
      });
    }

    presetCards.forEach((card) => {
      card.setAttribute("draggable", "true");
      card.addEventListener("dragstart", (e) => {
        const presetType = card.dataset.preset;
        let text = "Your text here";
        let fontSize = 36;
        let isBold = false;
        if (presetType === "heading") {
          text = "Add a heading";
          fontSize = 54;
          isBold = true;
        } else if (presetType === "subheading") {
          text = "Add a subheading";
          fontSize = 32;
          isBold = true;
        } else if (presetType === "body") {
          text = "Add a little bit of body text";
          fontSize = 20;
          isBold = false;
        }
        const payload = {
          type: "text",
          assetType: "text",
          text: text,
          fontSize: fontSize,
          isBold: isBold
        };
        try {
          e.dataTransfer.setData("application/json", JSON.stringify(payload));
        } catch (err) {}
        e.dataTransfer.setData("text/plain", text);
        e.dataTransfer.effectAllowed = "copy";
        if (timelineContainer) timelineContainer.classList.add("drag-hover-active");
      });

      card.addEventListener("dragend", () => {
        if (timelineContainer) timelineContainer.classList.remove("drag-hover-active");
        hideSnapGuide();
        document.querySelectorAll(".timeline-track-row").forEach((r) => r.classList.remove("drag-track-hover"));
      });

      card.addEventListener("click", () => {
        const presetType = card.dataset.preset;
        if (presetType === "heading") {
          addTextPreset("Add a heading", 54, true);
        } else if (presetType === "subheading") {
          addTextPreset("Add a subheading", 32, true);
        } else if (presetType === "body") {
          addTextPreset("Add a little bit of body text", 20, false);
        }
      });
    });
  };
  initCanvaTextPresets();

  // Active Text Sidebar Editor Controls
  const setupActiveTextEditor = () => {
    const input = document.getElementById("active-text-input");
    const sizeInput = document.getElementById("active-text-size");
    const sizePlus = document.getElementById("btn-text-size-plus");
    const sizeMinus = document.getElementById("btn-text-size-minus");
    const colorInput = document.getElementById("active-text-color");
    const boldBtn = document.getElementById("btn-text-bold-toggle");
    const deleteBtn = document.getElementById("btn-delete-active-text");

    const getActiveOverlay = () => {
      if (globalSelection && globalSelection.track === "text" && globalSelection.index >= 0) {
        if (editorState.text_overlays && editorState.text_overlays[globalSelection.index]) {
          return editorState.text_overlays[globalSelection.index];
        }
      }
      if (editorState.text_overlays && editorState.text_overlays.length > 0) {
        const idx = (globalSelection && globalSelection.index >= 0 && globalSelection.index < editorState.text_overlays.length)
          ? globalSelection.index
          : editorState.text_overlays.length - 1;
        globalSelection = { track: "text", index: idx };
        return editorState.text_overlays[idx];
      }
      return null;
    };

    if (input) {
      input.addEventListener("input", () => {
        const overlay = getActiveOverlay();
        if (!overlay) return;
        overlay.text = input.value;
        
        // Update live on video stage
        const stageEl = document.querySelector(`.preview-text-overlay[data-index="${globalSelection.index}"]`) || document.querySelector('.preview-text-overlay');
        if (stageEl) {
          const contentSpan = stageEl.querySelector(".preview-text-content") || stageEl;
          contentSpan.textContent = overlay.text;
        }
        
        // Update live on timeline text block
        const textBlocks = document.querySelectorAll("#text-track-content .timeline-text-block");
        if (textBlocks && textBlocks[globalSelection.index]) {
          const span = textBlocks[globalSelection.index].querySelector("span");
          if (span) span.textContent = overlay.text;
        }

        const advInput = document.getElementById("id_text");
        if (advInput) advInput.value = overlay.text;
      });

      input.addEventListener("change", () => {
        if (typeof autoSaveTimeline === "function") autoSaveTimeline();
      });
    }

    if (sizeInput) {
      const updateSize = (newSize) => {
        const overlay = getActiveOverlay();
        if (!overlay) return;
        const parsed = parseInt(newSize, 10);
        overlay.font_size = Math.max(10, Math.min(160, isNaN(parsed) ? 32 : parsed));
        overlay.fontsize = overlay.font_size;
        sizeInput.value = overlay.font_size;
        if (typeof renderTextOverlays === "function") renderTextOverlays();
        if (typeof autoSaveTimeline === "function") autoSaveTimeline();
      };
      sizeInput.addEventListener("change", () => updateSize(sizeInput.value));
      sizeInput.addEventListener("input", () => {
        const val = sizeInput.value.replace(/[^0-9]/g, "");
        if (val) updateSize(val);
      });
      if (sizePlus) {
        sizePlus.addEventListener("click", () => {
          const overlay = getActiveOverlay();
          const cur = overlay?.font_size || overlay?.fontsize || parseInt(sizeInput.value, 10) || 32;
          updateSize(cur + 4);
        });
      }
      if (sizeMinus) {
        sizeMinus.addEventListener("click", () => {
          const overlay = getActiveOverlay();
          const cur = overlay?.font_size || overlay?.fontsize || parseInt(sizeInput.value, 10) || 32;
          updateSize(cur - 4);
        });
      }
    }

    if (colorInput) {
      colorInput.addEventListener("input", () => {
        const overlay = getActiveOverlay();
        if (!overlay) return;
        overlay.color = colorInput.value;
        const stageEl = document.querySelector(`.preview-text-overlay[data-index="${globalSelection.index}"]`) || document.querySelector('.preview-text-overlay');
        if (stageEl) stageEl.style.color = overlay.color;
        const advColor = document.getElementById("id_color");
        if (advColor) advColor.value = overlay.color;
      });
      colorInput.addEventListener("change", () => {
        if (typeof autoSaveTimeline === "function") autoSaveTimeline();
      });
    }

    if (boldBtn) {
      boldBtn.addEventListener("click", () => {
        const overlay = getActiveOverlay();
        if (!overlay) return;
        overlay.bold = !overlay.bold;
        boldBtn.style.background = overlay.bold ? "#ede9fe" : "#ffffff";
        boldBtn.style.color = overlay.bold ? "#7c3aed" : "#334155";
        if (typeof renderTextOverlays === "function") renderTextOverlays();
        if (typeof autoSaveTimeline === "function") autoSaveTimeline();
      });
    }

    if (deleteBtn) {
      deleteBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        let idx = (globalSelection && globalSelection.track === "text" && globalSelection.index >= 0)
          ? globalSelection.index
          : (editorState.text_overlays && editorState.text_overlays.length > 0 ? editorState.text_overlays.length - 1 : -1);
        if (idx >= 0 && editorState.text_overlays && editorState.text_overlays[idx]) {
          editorState.text_overlays.splice(idx, 1);
          if (typeof clearGlobalSelection === "function") {
            clearGlobalSelection();
          } else {
            globalSelection = { track: null, index: -1 };
          }
          if (typeof renderTextOverlays === "function") renderTextOverlays();
          if (typeof renderAllTimelineTracks === "function") renderAllTimelineTracks();
          if (typeof updateToolbarActionButtons === "function") updateToolbarActionButtons();
          if (typeof autoSaveTimeline === "function") autoSaveTimeline();
          const editorCard = document.getElementById("ve-text-editor-card");
          if (editorCard) editorCard.style.display = "none";
        }
      });
    }
  };
  setupActiveTextEditor();

  const setupTimelineDragAndDrop = () => {
    const timelineContainer = document.getElementById("visual-trim-container");
    const scrollArea = document.getElementById("timeline-scroll-area");
    const tracksWrapper = document.getElementById("timeline-tracks-wrapper");
    if (!timelineContainer) return;

    const targets = [timelineContainer, scrollArea, tracksWrapper].filter(Boolean);

    function updateSnapGuidePosition(clientX) {
      const rawTime = getSecondsFromX(clientX);
      const snapped = (typeof snapTimeToPoints === "function") ? snapTimeToPoints(rawTime, 12) : { time: rawTime };
      const targetTime = Math.max(0, Math.min(duration || 0, snapped.time));
      const snapGuide = document.getElementById("timeline-snap-guide");
      if (snapGuide) {
        const pxPerSec = (basePxPerSecond || 15) * (zoomFactor || 1.0);
        snapGuide.style.display = "block";
        snapGuide.style.left = `${targetTime * pxPerSec}px`;
      }
      return targetTime;
    }

    function onDragOver(e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      timelineContainer.classList.add("drag-hover-active");

      updateSnapGuidePosition(e.clientX);

      const trackRow = e.target.closest(".timeline-track-row");
      document.querySelectorAll(".timeline-track-row").forEach((row) => {
        if (trackRow && (row === trackRow || row.contains(trackRow))) {
          row.classList.add("drag-track-hover");
        } else {
          row.classList.remove("drag-track-hover");
        }
      });
    }

    function onDragLeave(e) {
      if (e.relatedTarget && timelineContainer.contains(e.relatedTarget)) {
        return;
      }
      timelineContainer.classList.remove("drag-hover-active");
      timelineContainer.style.borderColor = "";
      timelineContainer.style.background = "";
      hideSnapGuide();
      document.querySelectorAll(".timeline-track-row").forEach((r) => r.classList.remove("drag-track-hover"));
    }

    async function handleDrop(e) {
      e.preventDefault();
      e.stopPropagation();

      timelineContainer.classList.remove("drag-hover-active");
      timelineContainer.style.borderColor = "";
      timelineContainer.style.background = "";
      hideSnapGuide();

      const trackRow = e.target.closest(".timeline-track-row");
      document.querySelectorAll(".timeline-track-row").forEach((r) => r.classList.remove("drag-track-hover"));

      // 1. Files dropped directly from user's computer/desktop
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        console.log("Files dropped from computer onto timeline:", e.dataTransfer.files);
        if (typeof handleUploadFiles === "function") {
          handleUploadFiles(e.dataTransfer.files);
        }
        return;
      }

      // 2. Data payload from sidebar drag
      let assetData = null;
      try {
        const jsonStr = e.dataTransfer.getData("application/json");
        if (jsonStr) assetData = JSON.parse(jsonStr);
      } catch (err) {}

      const assetId = assetData?.assetId || e.dataTransfer.getData("text/plain");

      // Check if text preset
      if (assetData && (assetData.type === "text" || assetData.assetType === "text")) {
        const dropTime = updateSnapGuidePosition(e.clientX);
        const text = assetData.text || "Your text here";
        const fontSize = assetData.fontSize || 36;
        const isBold = !!assetData.isBold;
        const sSec = parseFloat(dropTime.toFixed(2));
        const dur = window.duration || duration || 10;
        const eSec = parseFloat(Math.min(dur, sSec + 4.0).toFixed(2));

        editorState.text_overlays = editorState.text_overlays || [];
        const newOverlay = {
          text: text,
          position: "center",
          color: "#ffffff",
          font_size: fontSize,
          bold: isBold,
          start: sSec,
          end: eSec > sSec ? eSec : parseFloat((sSec + 3.0).toFixed(2))
        };
        editorState.text_overlays.push(newOverlay);
        if (typeof renderTextOverlays === "function") renderTextOverlays();
        if (typeof renderAllTimelineTracks === "function") renderAllTimelineTracks();
        if (typeof updatePlayheadSmooth === "function") updatePlayheadSmooth();
        if (typeof selectTimelineItem === "function") {
          selectTimelineItem("text", editorState.text_overlays.length - 1, newOverlay);
        }
        if (typeof autoSaveTimeline === "function") autoSaveTimeline();
        if (window.updateLocalState) window.updateLocalState("Text", `Added text: "${text}"`);
        return;
      }

      // Look for DOM card or fallback to assetData
      let card = null;
      if (assetId) {
        card = Array.from(document.querySelectorAll(".ve-grid-item.asset-card")).find(
          (c) => c.dataset.assetId === assetId
        );
      }

      const finalAsset = card || assetData;
      if (!finalAsset) {
        console.warn("No asset found for drop event, assetId:", assetId);
        return;
      }

      // Target track lane detection
      let targetTrack = null;
      if (trackRow) {
        if (trackRow.id === "audio-track-row" || trackRow.classList.contains("audio-track-row")) {
          targetTrack = "audio";
        } else if (trackRow.id === "video-track-row" || trackRow.classList.contains("video-track-row")) {
          targetTrack = "video";
        } else if (trackRow.id === "text-track-row" || trackRow.classList.contains("text-track-row")) {
          targetTrack = "text";
        }
      }

      const dropTime = updateSnapGuidePosition(e.clientX);
      console.log(`Dropping asset onto timeline at ${dropTime.toFixed(2)}s (track: ${targetTrack || "auto"})`);
      handleInsertAssetClientSide(finalAsset, dropTime, targetTrack);
    }

    targets.forEach((el) => {
      el.addEventListener("dragenter", (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
        timelineContainer.classList.add("drag-hover-active");
      });
      el.addEventListener("dragover", onDragOver);
      el.addEventListener("dragleave", onDragLeave);
      el.addEventListener("drop", handleDrop);
    });
  };
  setupTimelineDragAndDrop();

  document.querySelectorAll(".tool-panel form, .timeline-speed-control form").forEach((form) => {
    if (form.id === "trim-form" || form.id === "insert-asset-form") return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const action = form.getAttribute("action");

      if (form.id === "bg-audio-form") {
        const fileInput = form.querySelector('input[type="file"]');
        if (!fileInput.files.length) return;

        const btn = form.querySelector("button[type=submit]");
        const originalText = btn.textContent;
        btn.textContent = "Uploading...";

        const formData = new FormData();
        formData.append("audio_file", fileInput.files[0]);

        const csrf = document.querySelector(
          'input[name="csrfmiddlewaretoken"]',
        )?.value;
        const uploadUrl = action.replace(
          "background-audio",
          "upload-audio-temp",
        );

        try {
          const res = await fetch(uploadUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrf },
            body: formData,
          });
          const data = await res.json();
          if (data.status === "success") {
            const bgVol =
              parseFloat(form.querySelector("#id_bg_volume").value) || 0.5;
            const vidVol =
              parseFloat(form.querySelector("#id_video_volume").value) || 1.0;
            const startSec =
              parseFloat(form.querySelector("#id_start_seconds").value) || 0;
            const endSec =
              parseFloat(form.querySelector("#id_end_seconds").value) || null;

            editorState.background_audios = editorState.background_audios || [];
            editorState.background_audios.push({
              temp_path: data.temp_path,
              url: URL.createObjectURL(fileInput.files[0]),
              bg_volume: bgVol,
              video_volume: vidVol,
              start: startSec,
              end: endSec,
              name: data.filename,
            });
            editorState.volume = vidVol;
            applyCSSEffects();

            if (window.updateLocalState)
              window.updateLocalState(
                "BgAudio",
                `Added background audio ${data.filename}`,
              );
            btn.textContent = "Added!";
          } else {
            alert("Upload failed");
            btn.textContent = originalText;
          }
        } catch (err) {
          alert("Error: " + err);
          btn.textContent = originalText;
        }
        setTimeout(() => {
          btn.textContent = originalText;
        }, 2000);
        return;
      }

      if (action.includes("/speed/")) {
        const speed = parseFloat(form.querySelector("#id_speed_factor").value) || 1.0;
        editorState.speed = speed;
        applyCSSEffects();
        renderAllTimelineTracks();
        autoSaveTimeline();
        if (window.updateLocalState)
          window.updateLocalState("Speed", `Speed ${speed}x`);
      } else if (action.includes("/volume/")) {
        const vol = parseFloat(form.querySelector("#id_volume_factor").value) || 1.0;
        editorState.volume = vol;
        applyCSSEffects();
        renderAllTimelineTracks();
        autoSaveTimeline();
        if (window.updateLocalState)
          window.updateLocalState("Volume", `Volume ${vol}x`);
      } else if (action.includes("/mute/")) {
        const newMuted = !(editorState.userMuted || editorState.muted);
        editorState.muted = newMuted;
        editorState.userMuted = newMuted;
        const mainVid = document.getElementById("main-video");
        if (mainVid) mainVid.muted = newMuted;
        if (typeof syncVolumeUI === "function") syncVolumeUI();
        applyCSSEffects();
        renderAllTimelineTracks();
        autoSaveTimeline();
        if (window.updateLocalState)
          window.updateLocalState("Mute", editorState.muted ? `Muted video` : `Unmuted video`);
      } else if (action.includes("/text/")) {
        const txtInput = form.querySelector("#id_text");
        const posInput = form.querySelector("#id_position");
        const colorInput = form.querySelector("#id_color");
        const sizeInput = form.querySelector("#id_font_size");
        const startInput = form.querySelector("#id_start_seconds");
        const endInput = form.querySelector("#id_end_seconds");
        const textVal = txtInput ? txtInput.value.trim() : "";
        if (textVal) {
          editorState.text_overlays = editorState.text_overlays || [];
          const sSec = startInput && startInput.value ? parseFloat(startInput.value) : 0;
          const eSec = endInput && endInput.value ? parseFloat(endInput.value) : (duration || 10);
          editorState.text_overlays.push({
            text: textVal,
            position: posInput ? posInput.value : "bottom",
            color: colorInput ? colorInput.value : "white",
            font_size: sizeInput ? parseInt(sizeInput.value) || 48 : 48,
            start: sSec,
            end: eSec,
          });
          renderTextOverlays();
          renderAllTimelineTracks();
          autoSaveTimeline();
          if (window.updateLocalState)
            window.updateLocalState("Text", `Added text overlay: "${textVal}"`);
        }
      }

      // Visual feedback
      const btn = form.querySelector("button[type=submit]");
      if (btn) {
        const originalText = btn.textContent;
        btn.textContent = "Applied!";
        setTimeout(() => {
          btn.textContent = originalText;
        }, 1500);
      }
    });
  });

    // --- Live Preview rendering for Text overlays ---
    renderTextOverlays = () => {
      const container = document.getElementById("text-overlay-container");
      if (!container) return;
      container.innerHTML = "";

      // Helper function to get actual visible video rect inside container
      const getVideoRect = () => {
        const videoEl = document.getElementById("main-video") || document.getElementById("video-preview");
        if (!videoEl || !videoEl.videoWidth || !videoEl.videoHeight) {
          return {
            x: 0,
            y: 0,
            width: container.clientWidth || 800,
            height: container.clientHeight || 450,
          };
        }
        const containerWidth = container.clientWidth || 800;
        const containerHeight = container.clientHeight || 450;
        const videoRatio = videoEl.videoWidth / videoEl.videoHeight;
        const containerRatio = containerWidth / containerHeight;

        let videoWidth, videoHeight;
        if (containerRatio > videoRatio) {
          // Container is wider than video, scale to height
          videoHeight = containerHeight;
          videoWidth = videoHeight * videoRatio;
        } else {
          // Container is taller than video, scale to width
          videoWidth = containerWidth;
          videoHeight = videoWidth / videoRatio;
        }

        const x = (containerWidth - videoWidth) / 2;
        const y = (containerHeight - videoHeight) / 2;

        return { x, y, width: videoWidth, height: videoHeight };
      };

      const videoRect = getVideoRect();
      const actualHeight = parseFloat(window.REEL_PROJECT_HEIGHT) || 720;
      const videoEl = document.getElementById("main-video") || document.getElementById("video-preview");
      const playerHeight = (videoEl ? videoEl.clientHeight : 0) || 400;
      const scale = playerHeight / actualHeight;
      const curTime = (typeof timelineCurrentTime === "number" && !isNaN(timelineCurrentTime))
        ? timelineCurrentTime
        : (videoEl ? sourceToTimelineTime(videoEl.currentTime) : 0);

      (editorState.text_overlays || []).forEach((overlay, idx) => {
        const el = document.createElement("div");

        const fontSizeVal = overlay.font_size || overlay.fontsize || 36;
        const displayFontSize = Math.max(
          14,
          Math.round(fontSizeVal * (scale > 0 ? scale : 0.6)),
        );

        el.className = `preview-text-overlay pos-${overlay.position || "center"}`;
        el.dataset.index = idx;
        el.textContent = overlay.text || "Text";
        el.style.fontSize = `${displayFontSize}px`;
        el.style.fontWeight = overlay.bold ? "700" : (overlay.font_weight || "600");
        el.style.color = overlay.color || "#ffffff";
        el.style.textShadow = "0 2px 6px rgba(0, 0, 0, 0.95), 0 0 2px rgba(0, 0, 0, 0.9)";
        el.style.pointerEvents = "auto";
        el.style.cursor = "move";
        el.style.userSelect = "none";
        el.style.boxSizing = "border-box";
        el.style.whiteSpace = "pre-wrap";
        el.style.zIndex = "35";

        // Selection highlight
        const isSelected = globalSelection.track === "text" && globalSelection.index === idx;
        if (isSelected) {
          el.classList.add("selected", "is-selected");
        }

        // Time-based visibility: Always visible if selected so user can see and edit immediately
        const oStart = parseFloat(overlay.start || 0);
        const oEnd = parseFloat(overlay.end || duration || 10);
        if (isSelected || (curTime >= oStart - 0.05 && curTime <= oEnd + 0.05)) {
          el.style.display = "block";
        } else {
          el.style.display = "none";
        }

        // Direct inline editing & selection
        let isEditing = false;
        
        const enableInlineEditing = () => {
          isEditing = true;
          el.contentEditable = "true";
          el.style.cursor = "text";
          el.style.userSelect = "text";
          el.focus();
          try {
            const range = document.createRange();
            range.selectNodeContents(el);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
          } catch (err) {}
        };

        const disableInlineEditing = () => {
          if (!isEditing) return;
          isEditing = false;
          el.contentEditable = "false";
          el.style.cursor = "move";
          el.style.userSelect = "none";
          overlay.text = el.innerText.trim() || "Text";
          el.textContent = overlay.text;

          // Sync with sidebar input and form
          const sidebarInput = document.getElementById("active-text-input");
          if (sidebarInput) sidebarInput.value = overlay.text;
          const advInput = document.getElementById("id_text");
          if (advInput) advInput.value = overlay.text;

          if (typeof renderAllTimelineTracks === "function") renderAllTimelineTracks();
          if (typeof autoSaveTimeline === "function") autoSaveTimeline();
        };

        // Click to select & open editor in sidebar
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          selectTimelineItem("text", idx, overlay);
        });

        // Double-click to directly edit text inline on video stage
        el.addEventListener("dblclick", (e) => {
          e.stopPropagation();
          selectTimelineItem("text", idx, overlay);
          enableInlineEditing();
        });

        el.addEventListener("input", () => {
          if (!isEditing) return;
          overlay.text = el.innerText;
          const sidebarInput = document.getElementById("active-text-input");
          if (sidebarInput) sidebarInput.value = overlay.text;
          const advInput = document.getElementById("id_text");
          if (advInput) advInput.value = overlay.text;

          // Live update timeline text block label
          const textBlock = document.querySelectorAll("#text-track-content .timeline-text-block")[idx];
          if (textBlock) {
            const span = textBlock.querySelector("span");
            if (span) span.textContent = overlay.text;
          }
        });

        el.addEventListener("blur", () => {
          disableInlineEditing();
        });

        el.addEventListener("keydown", (e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            el.blur();
          } else if (e.key === "Escape") {
            el.textContent = overlay.text;
            el.blur();
          }
        });

        // Set up position styling
        if (overlay.position && overlay.position.startsWith("custom:")) {
          const parts = overlay.position.substring(7).split(",");
          const x_pct = parseFloat(parts[0]);
          const y_pct = parseFloat(parts[1]);

          const applyPosition = () => {
            const vRect = getVideoRect();
            const t_w = el.offsetWidth || 120;
            const t_h = el.offsetHeight || 36;

            el.style.left = `${vRect.x + (vRect.width - t_w) * (x_pct / 100)}px`;
            el.style.top = `${vRect.y + (vRect.height - t_h) * (y_pct / 100)}px`;
            el.style.transform = "none";
            el.style.margin = "0";
          };

          el.style.position = "absolute";
          container.appendChild(el);
          applyPosition();
          setTimeout(applyPosition, 0); // fallback sync
        } else if (overlay.position === "center") {
          el.style.position = "absolute";
          el.style.left = "50%";
          el.style.top = "50%";
          el.style.transform = "translate(-50%, -50%)";
          container.appendChild(el);
        } else if (overlay.position === "top") {
          el.style.position = "absolute";
          el.style.left = "50%";
          el.style.top = `${videoRect.y + 24}px`;
          el.style.transform = "translateX(-50%)";
          container.appendChild(el);
        } else {
          el.style.position = "absolute";
          el.style.left = "50%";
          el.style.bottom = `${Math.max(20, container.clientHeight - videoRect.y - videoRect.height + 24)}px`;
          el.style.transform = "translateX(-50%)";
          container.appendChild(el);
        }

        // Make it draggable
        let isDragging = false;
        let dragHasMoved = false;
        let startX, startY;
        let startLeft, startTop;

        const onMouseDown = (e) => {
          if (isEditing) return;
          e.stopPropagation();
          isDragging = true;
          dragHasMoved = false;

          const rect = el.getBoundingClientRect();
          const parentRect = container.getBoundingClientRect();

          startLeft = rect.left - parentRect.left;
          startTop = rect.top - parentRect.top;

          startX = e.clientX || (e.touches && e.touches[0].clientX);
          startY = e.clientY || (e.touches && e.touches[0].clientY);

          document.addEventListener("mousemove", onMouseMove);
          document.addEventListener("mouseup", onMouseUp);
          document.addEventListener("touchmove", onMouseMove, {
            passive: false,
          });
          document.addEventListener("touchend", onMouseUp);
        };

        const onMouseMove = (e) => {
          if (!isDragging) return;

          const clientX = e.clientX || (e.touches && e.touches[0].clientX);
          const clientY = e.clientY || (e.touches && e.touches[0].clientY);

          const dx = clientX - startX;
          const dy = clientY - startY;

          if (!dragHasMoved) {
            if (Math.hypot(dx, dy) < 4) return;
            dragHasMoved = true;
          }
          e.preventDefault();

          const videoRect = getVideoRect();
          const t_w = el.offsetWidth;
          const t_h = el.offsetHeight;

          let newLeft = startLeft + dx;
          let newTop = startTop + dy;

          // Constrain to actual visible video rect
          newLeft = Math.max(
            videoRect.x,
            Math.min(videoRect.x + videoRect.width - t_w, newLeft),
          );
          newTop = Math.max(
            videoRect.y,
            Math.min(videoRect.y + videoRect.height - t_h, newTop),
          );

          el.style.left = `${newLeft}px`;
          el.style.top = `${newTop}px`;
          el.style.transform = "none";
          el.style.margin = "0";
          el.style.position = "absolute";
        };

        const onMouseUp = () => {
          if (!isDragging) return;
          isDragging = false;

          document.removeEventListener("mousemove", onMouseMove);
          document.removeEventListener("mouseup", onMouseUp);
          document.removeEventListener("touchmove", onMouseMove);
          document.removeEventListener("touchend", onMouseUp);

          if (!dragHasMoved) return;

          const videoRect = getVideoRect();
          const t_w = el.offsetWidth;
          const t_h = el.offsetHeight;

          const leftPx = parseFloat(el.style.left) || videoRect.x;
          const topPx = parseFloat(el.style.top) || videoRect.y;

          // Calculate position relative to visible video rect
          const relativeLeft = leftPx - videoRect.x;
          const relativeTop = topPx - videoRect.y;

          const denomX = videoRect.width - t_w;
          const denomY = videoRect.height - t_h;

          const x_pct = denomX > 0 ? (relativeLeft / denomX) * 100 : 50;
          const y_pct = denomY > 0 ? (relativeTop / denomY) * 100 : 50;

          const newPosValue = `custom:${x_pct.toFixed(2)},${y_pct.toFixed(2)}`;
          overlay.position = newPosValue;

          let selectedOverlayIndex = -1;
    const textFormEl = document.querySelector('form[action*="/text/"]');
          if (textFormEl) {
            const posInput = textFormEl.querySelector("#id_position");
            if (posInput) {
              let opt = posInput.querySelector('option[value^="custom:"]');
              if (!opt) {
                opt = document.createElement("option");
                posInput.appendChild(opt);
              }
              opt.value = newPosValue;
              opt.textContent = `Custom (${x_pct.toFixed(0)}%, ${y_pct.toFixed(0)}%)`;
              posInput.value = newPosValue;
            }
          }
        };

        el.addEventListener("mousedown", onMouseDown);
        el.addEventListener("touchstart", onMouseDown, { passive: false });
      });
      renderAllTimelineTracks();
    };

    window.renderTextOverlays = renderTextOverlays;

    // --- Real-time sync of Text Overlay Form fields to editorState & preview ---
    let selectedOverlayIndex = -1;
    const textFormEl = document.querySelector('form[action*="/text/"]');
    if (textFormEl) {
      const txtInput = textFormEl.querySelector("#id_text");
      const posInput = textFormEl.querySelector("#id_position");
      const colorInput = textFormEl.querySelector("#id_color");
      const sizeInput = textFormEl.querySelector("#id_font_size");
      const startInput = textFormEl.querySelector("#id_start_seconds");
      const endInput = textFormEl.querySelector("#id_end_seconds");

      const syncFormToOverlay = () => {
        if (!txtInput) return;
        const text = txtInput.value.trim();
        if (!text) {
          editorState.text_overlays = [];
          renderTextOverlays();
          return;
        }

        if (editorState.text_overlays.length === 0) {
          const startVal =
            startInput && startInput.value ? parseFloat(startInput.value) : 0;
          const endVal =
            endInput && endInput.value ? parseFloat(endInput.value) : duration;
          editorState.text_overlays = [
            {
              text: text,
              position: posInput ? posInput.value : "bottom",
              color: colorInput ? colorInput.value : "white",
              font_size: sizeInput ? parseInt(sizeInput.value) || 80 : 80,
              start: startVal,
              end: endVal,
            },
          ];
          selectedOverlayIndex = 0;
        } else {
          const overlay = editorState.text_overlays[0];
          overlay.text = text;
          if (posInput) overlay.position = posInput.value;
          if (colorInput) overlay.color = colorInput.value;
          if (sizeInput) overlay.font_size = parseInt(sizeInput.value) || 80;
          if (startInput && startInput.value !== "")
            overlay.start = parseFloat(startInput.value);
          if (endInput && endInput.value !== "")
            overlay.end = parseFloat(endInput.value);
        }
        renderTextOverlays();
      };

      [txtInput, sizeInput, startInput, endInput].forEach((input) => {
        if (input) input.addEventListener("input", syncFormToOverlay);
      });
      [posInput, colorInput].forEach((input) => {
        if (input) input.addEventListener("change", syncFormToOverlay);
      });
    }

