// Reel — small client-side helpers for the editor workbench.
// No build step, no framework: this app is server-rendered and this file
// only adds the interactive touches (tabs, status polling, a couple of
// form conveniences) that don't need a round trip.

(function () {
  "use strict";

  let editorState = {
    video_clips: [],
    speed: 1.0,
    volume: 1.0,
    muted: false,
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
  let duration = 0;

  function timelineToSourceTime(tTimeline) {
    if (!editorState.video_clips || editorState.video_clips.length === 0) {
      return tTimeline;
    }
    let acc = 0;
    for (let i = 0; i < editorState.video_clips.length; i++) {
      const clip = editorState.video_clips[i];
      const dur = parseFloat(clip.duration || 0);
      if (tTimeline >= acc && tTimeline <= acc + dur) {
        const offset = tTimeline - acc;
        const trimStart = parseFloat(clip.trimStart !== undefined ? clip.trimStart : 0);
        return trimStart + offset;
      }
      acc += dur;
    }
    const lastClip = editorState.video_clips[editorState.video_clips.length - 1];
    if (lastClip) {
      const trimEnd = parseFloat(lastClip.trimEnd !== undefined ? lastClip.trimEnd : (lastClip.trimStart + lastClip.duration));
      return trimEnd;
    }
    return tTimeline;
  }

  function sourceToTimelineTime(tSource) {
    if (!editorState.video_clips || editorState.video_clips.length === 0) {
      return tSource;
    }
    let acc = 0;
    for (let i = 0; i < editorState.video_clips.length; i++) {
      const clip = editorState.video_clips[i];
      const trimStart = parseFloat(clip.trimStart !== undefined ? clip.trimStart : 0);
      const trimEnd = parseFloat(clip.trimEnd !== undefined ? clip.trimEnd : (trimStart + clip.duration));
      if (tSource >= trimStart && tSource <= trimEnd) {
        return acc + (tSource - trimStart);
      }
      acc += parseFloat(clip.duration || 0);
    }
    return tSource;
  }

  async function autoSaveTimeline() {
    if (!window.REEL_PROJECT_SAVE_TIMELINE_URL) return;

    const payload = {
      clips: editorState.video_clips,
      trim: editorState.trim,
      speed: editorState.speed,
      audio: {
        volume: editorState.volume,
        muted: editorState.muted,
      },
      text_overlays: editorState.text_overlays,
      background_audios: editorState.background_audios,
      resize: editorState.resize,
      effects: {
        grayscale: editorState.grayscale,
        rotate: editorState.rotate,
        fade: editorState.fade,
      },
    };

    try {
      const csrf = window.REEL_CSRF_TOKEN || document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
      await fetch(window.REEL_PROJECT_SAVE_TIMELINE_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      console.warn("Failed to auto-save timeline:", err);
    }
  }

  // ---- Event Delegation for Tool Tabs & History Drawer -------------------
  document.addEventListener("click", (e) => {
    // 1. Tool Tab Switching
    const tab = e.target.closest(".tool-tab, .ve-tool-tab");
    if (tab) {
      const target = tab.dataset.tab;
      const tabs = document.querySelectorAll(".tool-tab, .ve-tool-tab");
      const panels = document.querySelectorAll(".tool-section, .ve-tool-section");

      tabs.forEach((t) => {
        t.classList.remove("tool-tab--active", "ve-tool-tab--active");
      });
      tab.classList.add("tool-tab--active", "ve-tool-tab--active");

      panels.forEach((p) => {
        const isActive = p.dataset.panel === target;
        p.classList.toggle("tool-section--active", isActive);
        p.classList.toggle("ve-tool-section--active", isActive);
      });
      return;
    }

    // 2. History Drawer Show
    const showHistoryBtn = e.target.closest("#btn-show-history");
    if (showHistoryBtn) {
      e.preventDefault();
      const historyDrawer = document.getElementById("history-drawer");
      if (historyDrawer) {
        historyDrawer.classList.add("open");
      }
      return;
    }

    // 3. History Drawer Close & Backdrop
    const closeHistoryBtn = e.target.closest("#history-drawer-close, #history-drawer-backdrop");
    if (closeHistoryBtn) {
      e.preventDefault();
      const historyDrawer = document.getElementById("history-drawer");
      if (historyDrawer) {
        historyDrawer.classList.remove("open");
      }
      return;
    }
  });

  // Activate tab from URL query parameter if present
  const activateTabFromUrl = () => {
    const urlParams = new URLSearchParams(window.location.search);
    let activeTab = urlParams.get("tab");
    if (activeTab === "fx") activeTab = "effects";
    if (activeTab) {
      const targetTab = document.querySelector(
        `.tool-tab[data-tab="${activeTab}"], .ve-tool-tab[data-tab="${activeTab}"]`,
      );
      if (targetTab) {
        targetTab.click();
      }
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", activateTabFromUrl);
  } else {
    activateTabFromUrl();
  }
  document.addEventListener("turbo:load", activateTabFromUrl);

  // ---- Processing status polling -------------------------------------
  if (window.REEL_STATUS_URL && window.REEL_PROJECT_STATUS === "processing") {
    const poll = setInterval(async () => {
      try {
        const res = await fetch(window.REEL_STATUS_URL);
        const data = await res.json();
        if (data.status && data.status !== "processing") {
          clearInterval(poll);
          window.location.reload();
        }
      } catch (err) {
        clearInterval(poll);
      }
    }, 2500);
  }

  // ---- Proxy status polling -------------------------------------
  if (window.REEL_PROJECT_PROXY_STATUS === "processing") {
    const pollProxy = setInterval(async () => {
      try {
        // We reuse the REEL_STATUS_URL which returns proxy_status as well
        const res = await fetch(window.REEL_STATUS_URL);
        const data = await res.json();
        if (data.proxy_status && data.proxy_status !== "processing") {
          clearInterval(pollProxy);
          window.location.reload();
        }
      } catch (err) {
        clearInterval(pollProxy);
      }
    }, 2500);
  }

  // ---- AJAX Asset Upload (+ Add File) --------------------------------
  // ---- AJAX Asset Upload (+ Add File) --------------------------------
  const triggerUploadBtn = document.getElementById("btn-trigger-upload-asset");
  const assetFileInput = document.getElementById("asset-file-input");

  // Client-side quick duration extractor
  function extractMediaDuration(file) {
    return new Promise((resolve) => {
      const isAudio = file.type.startsWith("audio/");
      const isVideo = file.type.startsWith("video/");
      if (!isAudio && !isVideo) return resolve(0);

      const el = document.createElement(isVideo ? "video" : "audio");
      el.preload = "metadata";
      const blobUrl = URL.createObjectURL(file);
      el.src = blobUrl;
      const t = setTimeout(() => {
        URL.revokeObjectURL(blobUrl);
        resolve(0);
      }, 3000);
      el.onloadedmetadata = () => {
        clearTimeout(t);
        const dur = el.duration || 0;
        URL.revokeObjectURL(blobUrl);
        resolve(dur);
      };
      el.onerror = () => {
        clearTimeout(t);
        URL.revokeObjectURL(blobUrl);
        resolve(0);
      };
    });
  }

  if (triggerUploadBtn && assetFileInput) {
    triggerUploadBtn.addEventListener("click", (e) => {
      e.preventDefault();
      assetFileInput.click();
    });

    assetFileInput.addEventListener("change", async (e) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      const file = files[0];
      const clientDur = await extractMediaDuration(file);

      // Disable Add File button and update its state
      if (triggerUploadBtn) {
        triggerUploadBtn.setAttribute("disabled", "true");
        triggerUploadBtn.innerHTML = `<span style="display:inline-flex; align-items:center; gap:6px;"><i data-lucide="loader" class="animate-spin" style="width:14px;height:14px;"></i> Uploading...</span>`;
        if (typeof lucide !== "undefined") lucide.createIcons();
      }

      // Add temporary upload indicator to assets list
      const assetsGrid = document.getElementById("assets-grid-container");
      let uploadIndicator = null;
      if (assetsGrid) {
        const emptyState = document.getElementById("empty-assets-state");
        if (emptyState) emptyState.style.display = "none";

        uploadIndicator = document.createElement("div");
        uploadIndicator.style.cssText = "display:flex; align-items:center; gap:10px; padding:10px; border:1px dashed var(--ve-border); border-radius:8px; background:var(--ve-bg-sub);";
        uploadIndicator.innerHTML = `
          <i data-lucide="loader" class="animate-spin" style="width:18px;height:18px;color:var(--ve-primary); flex-shrink:0;"></i>
          <div style="flex:1; min-width:0;">
            <p style="margin:0; font-size:12px; font-weight:600; text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">${file.name}</p>
            <p id="asset-upload-status-text" style="margin:0; font-size:10px; color:var(--ve-text-muted);">Uploading asset...</p>
          </div>
        `;
        assetsGrid.insertBefore(uploadIndicator, assetsGrid.firstChild);
        if (typeof lucide !== "undefined") lucide.createIcons();
      }

      try {
        const csrf =
          window.REEL_CSRF_TOKEN ||
          document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
        const uploadUrl =
          window.REEL_UPLOAD_ASSET_URL ||
          window.location.pathname + "upload-asset/";

        let data = null;

        // If file > 10MB and chunked upload URL is available, use fast parallel chunks
        if (file.size > 10 * 1024 * 1024 && window.REEL_CHUNKED_UPLOAD_URL && window.REEL_PROJECT_ID) {
          const chunkSize = 10 * 1024 * 1024;
          const totalChunks = Math.ceil(file.size / chunkSize);
          const uploadId = Date.now().toString() + Math.random().toString(36).substring(7);
          const statusText = document.getElementById("asset-upload-status-text");

          for (let i = 0; i < totalChunks; i++) {
            const start = i * chunkSize;
            const end = Math.min(start + chunkSize, file.size);
            const chunk = file.slice(start, end);

            const formData = new FormData();
            formData.append("chunk", chunk);
            formData.append("filename", file.name);
            formData.append("chunkIndex", i);
            formData.append("totalChunks", totalChunks);
            formData.append("uploadId", uploadId);
            formData.append("targetType", "asset");
            formData.append("projectId", window.REEL_PROJECT_ID);
            formData.append("clientDuration", clientDur);

            const res = await fetch(window.REEL_CHUNKED_UPLOAD_URL, {
              method: "POST",
              headers: { "X-CSRFToken": csrf },
              body: formData,
            });

            if (res.ok) {
              const resData = await res.json();
              if (resData.asset) {
                data = resData;
              }
            }

            const percent = Math.round(((i + 1) / totalChunks) * 100);
            if (statusText) statusText.textContent = `Uploading ${percent}%...`;
          }
        } else {
          // Standard fast upload with client metadata attached
          const formData = new FormData();
          formData.append("video_file", file);
          formData.append("clientDuration", clientDur);

          const response = await fetch(uploadUrl, {
            method: "POST",
            headers: {
              "X-CSRFToken": csrf,
            },
            body: formData,
          });
          if (response.ok) {
            data = await response.json();
          }
        }

        if (data && (data.success || data.status === "success")) {
          await autoSaveTimeline();
          window.location.reload();
        } else {
          alert("Upload failed: " + (data ? (data.error || "unknown error") : "Server error"));
          if (triggerUploadBtn) {
            triggerUploadBtn.removeAttribute("disabled");
            triggerUploadBtn.innerHTML = `<i data-lucide="plus" style="width:14px;height:14px;"></i> Add File`;
            if (typeof lucide !== "undefined") lucide.createIcons();
          }
          if (uploadIndicator) uploadIndicator.remove();
          const emptyState = document.getElementById("empty-assets-state");
          if (emptyState && assetsGrid && assetsGrid.children.length <= 1) {
            emptyState.style.display = "block";
          }
        }
      } catch (err) {
        console.error("Asset upload error:", err);
        alert("Upload failed due to connection error.");
        if (triggerUploadBtn) {
          triggerUploadBtn.removeAttribute("disabled");
          triggerUploadBtn.innerHTML = `<i data-lucide="plus" style="width:14px;height:14px;"></i> Add File`;
          if (typeof lucide !== "undefined") lucide.createIcons();
        }
        if (uploadIndicator) uploadIndicator.remove();
        const emptyState = document.getElementById("empty-assets-state");
        if (emptyState && assetsGrid && assetsGrid.children.length <= 1) {
          emptyState.style.display = "block";
        }
      }
    });
  }

  // ---- Asset Drag-and-Drop & Click to Insert -------------------------
  const assetCards = document.querySelectorAll(".asset-card");
  const timelineContainer = document.getElementById("visual-trim-container");
  const insertForm = document.getElementById("insert-asset-form");
  const insertAssetIdInput = document.getElementById("insert-asset-id");
  const insertAssetTimestampInput = document.getElementById(
    "insert-asset-timestamp",
  );

  if (assetCards.length > 0) {
    const handleInsertAssetClientSide = (card, currentTime) => {
      const assetId = card.dataset.assetId;
      const assetTitle = card.dataset.assetTitle || "Clip";
      const assetDuration = parseFloat(card.dataset.assetDuration || 0.0) || 10.0;
      const assetUrl = card.dataset.assetUrl || "";

      // Insert clip into editorState.video_clips
      const clips = editorState.video_clips || [];
      const newClips = [];
      let accum = 0.0;
      let inserted = false;

      for (let i = 0; i < clips.length; i++) {
        const clip = clips[i];
        const clipDur = parseFloat(clip.duration || 0.0);
        
        if (inserted) {
          newClips.push(clip);
          continue;
        }

        if (accum <= currentTime && currentTime < (accum + clipDur)) {
          // Split and insert
          const offset = currentTime - accum;
          const originalTrimStart = parseFloat(clip.trimStart || 0.0);
          
          const part1 = JSON.parse(JSON.stringify(clip));
          part1.duration = offset;
          part1.trimEnd = originalTrimStart + offset;

          const insertedClip = {
            id: assetId,
            title: assetTitle,
            trimStart: 0,
            trimEnd: assetDuration,
            duration: assetDuration,
            url: assetUrl
          };

          const part2 = JSON.parse(JSON.stringify(clip));
          part2.duration = clipDur - offset;
          part2.trimStart = originalTrimStart + offset;

          newClips.push(part1);
          newClips.push(insertedClip);
          newClips.push(part2);
          inserted = true;
        } else {
          newClips.push(clip);
          accum += clipDur;
        }
      }

      if (!inserted) {
        newClips.push({
          id: assetId,
          title: assetTitle,
          trimStart: 0,
          trimEnd: assetDuration,
          duration: assetDuration,
          url: assetUrl
        });
      }

      editorState.video_clips = newClips;
      
      // Recalculate timeline positions and total duration
      recalculateVideoClipsTimeline();

      // Re-render tracks and clip blocks
      renderClipBlocks();
      renderAllTimelineTracks();
      updateRuler();
      renderTrim();
      generateThumbnails();

      if (window.updateLocalState) {
        window.updateLocalState("Video", `Inserted clip ${assetTitle}`);
      }
    };

    assetCards.forEach((card) => {
      const insertBtn = card.querySelector(".btn-insert-asset");
      if (insertBtn) {
        insertBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const videoEl = document.getElementById("main-video");
          const currentTime = videoEl ? sourceToTimelineTime(videoEl.currentTime) : 0.0;
          handleInsertAssetClientSide(card, currentTime);
        });
      }

      card.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("text/plain", card.dataset.assetId);
        e.dataTransfer.effectAllowed = "copy";
        if (timelineContainer) {
          timelineContainer.classList.add("drag-hover-active");
        }
      });

      card.addEventListener("dragend", () => {
        if (timelineContainer) {
          timelineContainer.classList.remove("drag-hover-active");
        }
      });
    });

    if (timelineContainer) {
      timelineContainer.addEventListener("dragover", (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      });

      timelineContainer.addEventListener("dragenter", (e) => {
        e.preventDefault();
        timelineContainer.style.borderColor = "var(--ve-primary)";
        timelineContainer.style.background = "rgba(102, 126, 234, 0.04)";
      });

      timelineContainer.addEventListener("dragleave", () => {
        timelineContainer.style.borderColor = "";
        timelineContainer.style.background = "";
      });

      timelineContainer.addEventListener("drop", (e) => {
        e.preventDefault();
        timelineContainer.style.borderColor = "";
        timelineContainer.style.background = "";

        const assetId = e.dataTransfer.getData("text/plain");
        if (!assetId) return;

        const card = Array.from(assetCards).find(c => c.dataset.assetId === assetId);
        if (!card) return;

        const videoEl = document.getElementById("main-video");
        const currentTime = videoEl ? sourceToTimelineTime(videoEl.currentTime) : 0.0;
        handleInsertAssetClientSide(card, currentTime);
      });
    }
  }

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

      if (action.includes("/rotate/")) {
        const deg = form.querySelector("#id_degrees").value;
        if (window.updateLocalState)
          window.updateLocalState("Rotate", `Rotated ${deg} degrees`);
      } else if (action.includes("/resize/")) {
        const w = form.querySelector("#id_width").value;
        const h = form.querySelector("#id_height").value;
        if (window.updateLocalState)
          window.updateLocalState("Resize", `Resized to ${w}x${h}`);
      } else if (action.includes("/grayscale/")) {
        if (window.updateLocalState)
          window.updateLocalState("Grayscale", `Applied Grayscale`);
      } else if (action.includes("/fade/")) {
        const fin = form.querySelector("#id_fade_in_seconds").value;
        const fout = form.querySelector("#id_fade_out_seconds").value;
        if (window.updateLocalState)
          window.updateLocalState(
            "Fade",
            `Fade in: ${fin}s, Fade out: ${fout}s`,
          );
      } else if (action.includes("/speed/")) {
        const speed = form.querySelector("#id_speed_factor").value;
        if (window.updateLocalState)
          window.updateLocalState("Speed", `Speed ${speed}x`);
      } else if (action.includes("/volume/")) {
        const vol = form.querySelector("#id_volume_factor").value;
        if (window.updateLocalState)
          window.updateLocalState("Volume", `Volume ${vol}x`);
      } else if (action.includes("/mute/")) {
        if (window.updateLocalState)
          window.updateLocalState("Mute", `Muted video`);
      } else if (action.includes("/text/")) {
        if (window.updateLocalState)
          window.updateLocalState("Text", `Added text overlay`);
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

  // ---- Show processing overlay on background audio submit
  const bgAudioForm = document.getElementById("bg-audio-form");
  if (bgAudioForm) {
    bgAudioForm.addEventListener("submit", () => {
      const overlay = document.getElementById("processing-overlay");
      if (overlay) {
        overlay.style.display = "flex";
        const txt = overlay.querySelector("p");
        if (txt) txt.textContent = "Adding background music...";
      }
    });
  }

  // ---- Visual Trim & Custom Player Controls Implementation -----------
  const video = document.getElementById("main-video");
  const startInput = document.getElementById("id_start_seconds");
  const endInput = document.getElementById("id_end_seconds");
  const trimContainer = document.getElementById("visual-trim-container");

  if (video && trimContainer) {
    const trimRuler = document.getElementById("trim-ruler");
    const trimTrack = document.getElementById("trim-track");
    const trimThumbnails = document.getElementById("trim-thumbnails");
    const trimDimLeft = document.getElementById("trim-dim-left");
    const trimDimRight = document.getElementById("trim-dim-right");
    const trimSelection = document.getElementById("trim-selection");
    const handleLeft = document.getElementById("trim-handle-left");
    const handleRight = document.getElementById("trim-handle-right");
    const trimPlayhead = document.getElementById("trim-playhead");
    const currentDisplay = document.getElementById("time-display-current");
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
    let zoomFactor = 1.0;
    const basePxPerSecond = 15;

    // --- Client-side Accumulative State ---
    editorState = {
      video_clips: [],
      speed: 1.0,
      volume: 1.0,
      muted: false,
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
        if (state.audio.muted !== undefined) editorState.muted = state.audio.muted;
      }
      if (state.text_overlays) editorState.text_overlays = state.text_overlays;
      if (state.background_audios) editorState.background_audios = state.background_audios;
      if (state.resize) editorState.resize = state.resize;
      if (state.effects) {
        if (state.effects.grayscale !== undefined) editorState.grayscale = state.effects.grayscale;
        if (state.effects.rotate !== undefined) editorState.rotate = state.effects.rotate;
        if (state.effects.fade !== undefined) editorState.fade = state.effects.fade;
      }
      if (state.trim) {
        editorState.trim = state.trim;
      }
      if (state.clips) {
        editorState.video_clips = state.clips;
      }
    }

    // Fallback if video_clips not initialized
    if (!editorState.video_clips || editorState.video_clips.length === 0) {
      const clipsData = window.REEL_PROJECT_CLIPS || [];
      editorState.video_clips = JSON.parse(JSON.stringify(clipsData));
    }

    function recalculateVideoClipsTimeline() {
      let acc = 0.0;
      (editorState.video_clips || []).forEach(clip => {
        const dur = parseFloat(clip.duration || 0.0);
        clip.start = acc;
        clip.end = acc + dur;
        if (clip.trimStart === undefined) clip.trimStart = 0;
        if (clip.trimEnd === undefined) clip.trimEnd = dur;
        acc += dur;
      });
      duration = acc;
      window.duration = acc;
      if (typeof endSeconds !== 'undefined') {
        endSeconds = acc;
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
        const speedInput = document.querySelector('form[action*="/speed/"] #id_speed_factor, .timeline-speed-control form select');
        if (speedInput) speedInput.value = editorState.speed;
      }
    };

    // UI helper to update CSS filters on the video player
    const applyCSSEffects = () => {
      let filters = [];
      if (editorState.grayscale) {
        filters.push("grayscale(100%)");
      }
      video.style.filter = filters.join(" ");

      // Rotate transform
      if (editorState.rotate) {
        video.style.transform = `rotate(${editorState.rotate}deg)`;
      } else {
        video.style.transform = "";
      }

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
      if (type === "Grayscale") {
        editorState.grayscale = true;
        applyCSSEffects();
      } else if (type === "Rotate") {
        const form = document.querySelector('form[action*="/rotate/"]');
        if (form) {
          editorState.rotate =
            parseInt(form.querySelector("#id_degrees").value) || 0;
        }
        applyCSSEffects();
      } else if (type === "Resize") {
        const form = document.querySelector('form[action*="/resize/"]');
        if (form) {
          editorState.resize = {
            width: form.querySelector("#id_width").value,
            height: form.querySelector("#id_height").value,
          };
        }
      } else if (type === "Fade") {
        const form = document.querySelector('form[action*="/fade/"]');
        if (form) {
          editorState.fade = {
            in:
              parseFloat(form.querySelector("#id_fade_in_seconds").value) || 0,
            out:
              parseFloat(form.querySelector("#id_fade_out_seconds").value) || 0,
          };
        }
      } else if (type === "Speed") {
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
        editorState.volume = 0;
        applyCSSEffects();
      }
      addHistoryItem(type, description);
      autoSaveTimeline();
    };

    const revertStateChange = (type, description) => {
      if (type === "Grayscale") {
        editorState.grayscale = false;
        applyCSSEffects();
      } else if (type === "Rotate") {
        editorState.rotate = 0;
        applyCSSEffects();
      } else if (type === "Volume") {
        editorState.volume = 1.0;
        video.volume = 1.0;
      } else if (type === "Mute") {
        editorState.muted = false;
        video.muted = false;
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
      } else if (type === "Fade") {
        editorState.fade = null;
      } else if (type === "Resize") {
        editorState.resize = null;
      }
    };

    // --- Live Preview rendering for Text overlays ---
    const renderTextOverlays = () => {
      const container = document.getElementById("text-overlay-container");
      if (!container) return;
      container.innerHTML = "";

      // Helper function to get actual visible video rect inside container
      const getVideoRect = () => {
        const videoEl = document.getElementById("video-preview");
        if (!videoEl || !videoEl.videoWidth || !videoEl.videoHeight) {
          return {
            x: 0,
            y: 0,
            width: container.clientWidth,
            height: container.clientHeight,
          };
        }
        const containerWidth = container.clientWidth;
        const containerHeight = container.clientHeight;
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

      editorState.text_overlays.forEach((overlay) => {
        const el = document.createElement("div");

        // Proportional scaling so the browser preview matches the final export
        const actualHeight = parseFloat(window.REEL_PROJECT_HEIGHT) || 720;
        const playerHeight = video.clientHeight || 400;
        const scale = playerHeight / actualHeight;
        const displayFontSize = Math.max(
          10,
          Math.round(overlay.font_size * scale),
        );

        el.style.fontSize = `${displayFontSize}px`;
        el.style.color = overlay.color;
        el.textContent = overlay.text;
        el.style.pointerEvents = "auto";
        el.style.cursor = "move";
        el.style.userSelect = "none";
        el.style.boxSizing = "border-box";
        el.style.whiteSpace = "pre-wrap";

        // Set up position styling
        if (overlay.position && overlay.position.startsWith("custom:")) {
          const parts = overlay.position.substring(7).split(",");
          const x_pct = parseFloat(parts[0]);
          const y_pct = parseFloat(parts[1]);

          const applyPosition = () => {
            const videoRect = getVideoRect();
            const t_w = el.offsetWidth;
            const t_h = el.offsetHeight;

            el.style.left = `${videoRect.x + (videoRect.width - t_w) * (x_pct / 100)}px`;
            el.style.top = `${videoRect.y + (videoRect.height - t_h) * (y_pct / 100)}px`;
            el.style.transform = "none";
            el.style.margin = "0";
          };

          el.style.position = "absolute";
          container.appendChild(el);
          applyPosition();
          setTimeout(applyPosition, 0); // fallback sync
        } else {
          el.className = `preview-text-overlay pos-${overlay.position}`;
          container.appendChild(el);
        }

        // Make it draggable
        let isDragging = false;
        let startX, startY;
        let startLeft, startTop;

        const onMouseDown = (e) => {
          e.preventDefault();
          e.stopPropagation();
          isDragging = true;

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
          e.preventDefault();

          const clientX = e.clientX || (e.touches && e.touches[0].clientX);
          const clientY = e.clientY || (e.touches && e.touches[0].clientY);

          const dx = clientX - startX;
          const dy = clientY - startY;

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

    // --- Real-time sync of Text Overlay Form fields to editorState & preview ---
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

    // --- Multi-track Timeline Text Row rendering ---
    const textTrackContent = document.getElementById("text-track-content");
    let selectedOverlayIndex = -1;
    // Synchronize Text Overlay Start/End Inputs with Playhead position
    const btnTextSetStart = document.getElementById("btn-text-set-start");
    const btnTextSetEnd = document.getElementById("btn-text-set-end");

    if (btnTextSetStart) {
      btnTextSetStart.addEventListener("click", () => {
        const playheadTime = parseFloat(sourceToTimelineTime(video.currentTime).toFixed(2));
        const textFormEl = document.querySelector('form[action*="/text/"]');
        if (textFormEl) {
          const input = textFormEl.querySelector('input[name="start_seconds"]');
          if (input) input.value = playheadTime;
        }

        if (
          selectedOverlayIndex !== -1 &&
          editorState.text_overlays[selectedOverlayIndex]
        ) {
          const overlay = editorState.text_overlays[selectedOverlayIndex];
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
        const playheadTime = parseFloat(sourceToTimelineTime(video.currentTime).toFixed(2));
        const textFormEl = document.querySelector('form[action*="/text/"]');
        if (textFormEl) {
          const input = textFormEl.querySelector('input[name="end_seconds"]');
          if (input) input.value = playheadTime;
        }

        if (
          selectedOverlayIndex !== -1 &&
          editorState.text_overlays[selectedOverlayIndex]
        ) {
          const overlay = editorState.text_overlays[selectedOverlayIndex];
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
    let globalSelection = { track: null, index: -1 };

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
        color: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
        borderColor: "#34d399",
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

    function clearGlobalSelection() {
      globalSelection = { track: null, index: -1 };
      if (typeof duration !== "undefined" && duration) {
        startSeconds = Math.min(Math.max(startSeconds, 0), duration);
        endSeconds = Math.max(
          startSeconds,
          Math.min(endSeconds || duration, duration),
        );
      }
      if (typeof renderTrim === "function") renderTrim();
    }

    function selectTimelineItem(trackType, index, item, options = {}) {
      globalSelection = { track: trackType, index };

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

      if (options.syncForm !== false && trackType === "text") {
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
    }

    function renderAllTimelineTracks() {
      if (window.dynamicTrackManager) {
        window.dynamicTrackManager.updateTrackVisibilities();
      }
      if (!duration) return;
      const pxPerSecond = basePxPerSecond * zoomFactor;

      syncEffectsToTrack();

      Object.keys(TRACK_CONFIG).forEach((trackType) => {
        const config = TRACK_CONFIG[trackType];
        const container = document.getElementById(config.containerId);
        if (!container) return;

        container.innerHTML = "";
        container.style.width = `${duration * pxPerSecond}px`;

        const items = editorState[config.stateKey] || [];

        items.forEach((item, index) => {
          const startSec = item.start || 0;
          const endSec = item.end || duration;
          const leftPx = startSec * pxPerSecond;
          const widthPx = Math.max(20, (endSec - startSec) * pxPerSecond);

          const el = document.createElement("div");
          el.className = `timeline-generic-block`;
          el.style.position = "absolute";
          el.style.left = `${leftPx}px`;
          el.style.width = `${widthPx}px`;
          el.style.height =
            trackType === "effect" ? "calc(100% - 16px)" : "100%";
          el.style.top = trackType === "effect" ? "8px" : "0";
          el.style.background = config.color;
          el.style.border = `2px solid ${config.borderColor}`;
          el.style.borderRadius = "8px";
          el.style.display = "flex";
          el.style.alignItems = "center";
          el.style.padding = "0 12px";
          el.style.boxSizing = "border-box";
          el.style.color = "white";
          el.style.fontSize = "13px";
          el.style.fontWeight = "bold";
          el.style.overflow = "hidden";
          el.style.zIndex = "3";

          if (
            globalSelection.track === trackType &&
            globalSelection.index === index
          ) {
            el.style.outline = "2px solid #ffffff";
            el.style.outlineOffset = "2px";
            el.style.boxShadow = "0 0 10px rgba(255,255,255,0.5)";
          }

          let name = item.name || item.text || "Item";
          el.innerHTML = `<i data-lucide="${config.icon}" style="width:14px;height:14px;margin-right:6px;flex-shrink:0;"></i> <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${name}</span>`;

          const handleL = document.createElement("div");
          handleL.style.position = "absolute";
          handleL.style.left = "-4px";
          handleL.style.top = "0";
          handleL.style.width = "8px";
          handleL.style.height = "100%";
          handleL.style.cursor = "ew-resize";
          handleL.style.zIndex = "4";

          let dragOffsetSeconds = 0;
          const startBlockDrag = (clientX) => {
            const itemDuration = Math.max(
              0.5,
              (item.end || duration) - (item.start || 0),
            );
            dragOffsetSeconds = getSecondsFromX(clientX) - (item.start || 0);
            const move = (moveEvent) => {
              const moveClientX = moveEvent.touches
                ? moveEvent.touches[0].clientX
                : moveEvent.clientX;
              const newStart = Math.max(
                0,
                Math.min(
                  duration - itemDuration,
                  getSecondsFromX(moveClientX) - dragOffsetSeconds,
                ),
              );
              item.start = parseFloat(newStart.toFixed(2));
              item.end = parseFloat((newStart + itemDuration).toFixed(2));
              el.style.left = `${item.start * pxPerSecond}px`;
              el.style.width = `${Math.max(20, (item.end - item.start) * pxPerSecond)}px`;
              if (typeof renderTrim === "function") renderTrim();
            };
            const stop = () => {
              window.removeEventListener("mousemove", move);
              window.removeEventListener("mouseup", stop);
              window.removeEventListener("touchmove", move);
              window.removeEventListener("touchend", stop);
            };
            window.addEventListener("mousemove", move);
            window.addEventListener("mouseup", stop);
            window.addEventListener("touchmove", move, { passive: false });
            window.addEventListener("touchend", stop);
          };

          el.addEventListener("mousedown", (e) => {
            if (e.target.closest(".trim-handle")) return;
            e.preventDefault();
            e.stopPropagation();
            startBlockDrag(e.clientX);
          });
          el.addEventListener(
            "touchstart",
            (e) => {
              if (e.target.closest(".trim-handle")) return;
              e.preventDefault();
              e.stopPropagation();
              startBlockDrag(e.touches[0].clientX);
            },
            { passive: false },
          );

          const handleR = document.createElement("div");
          handleR.style.position = "absolute";
          handleR.style.right = "-4px";
          handleR.style.top = "0";
          handleR.style.width = "8px";
          handleR.style.height = "100%";
          handleR.style.cursor = "ew-resize";
          handleR.style.zIndex = "4";

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

          if (typeof setupDrag === "function") {
            setupDrag(handleL, (clientX) => {
              let s = getSecondsFromX(clientX);
              if (s < 0) s = 0;
              if (s > endSec - 1.0) s = endSec - 1.0;
              item.start = parseFloat(s.toFixed(2));
              renderAllTimelineTracks();
              if (window.updateLocalState)
                window.updateLocalState("Trim", `Trimmed ${trackType} item`);
            });

            setupDrag(handleR, (clientX) => {
              let e = getSecondsFromX(clientX);
              if (e > duration) e = duration;
              if (e < startSec + 1.0) e = startSec + 1.0;
              item.end = parseFloat(e.toFixed(2));
              renderAllTimelineTracks();
              if (window.updateLocalState)
                window.updateLocalState("Trim", `Trimmed ${trackType} item`);
            });
          }
        });
      });

      if (typeof lucide !== "undefined") lucide.createIcons();
      updateTrackRowVisibility();
    }

    function syncEffectsToTrack() {
      editorState.active_effects = editorState.active_effects || [];
      if (editorState.active_effects.length === 0) {
        if (editorState.speed && editorState.speed !== 1.0)
          editorState.active_effects.push({
            name: `Speed (${editorState.speed}x)`,
            type: "speed",
            start: 0,
            end: duration,
          });
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
      const textTrackRow = document.querySelector(".text-track-row");
      const audioTrackRow = document.querySelector(".audio-track-row");
      const videoTrackRow = document.querySelector(".video-track-row");
      const effectTrackRow = document.querySelector(".effect-track-row");

      let count = 0;

      // Video track is always visible
      if (videoTrackRow) {
        count++;
      }

      let hasEffect = false;
      if (effectTrackRow) {
        const effectContent = document.getElementById("effect-track-content");
        hasEffect =
          effectContent &&
          effectContent.children &&
          effectContent.children.length > 0;
        if (hasEffect) {
          effectTrackRow.style.setProperty("display", "flex", "important");
          count++;
        } else {
          effectTrackRow.style.setProperty("display", "none", "important");
        }
      }

      let hasText = false;
      if (textTrackRow) {
        const textContent = document.getElementById("text-track-content");
        hasText =
          textContent &&
          textContent.children &&
          textContent.children.length > 0;
        if (hasText) {
          textTrackRow.style.setProperty("display", "flex", "important");
          count++;
        } else {
          textTrackRow.style.setProperty("display", "none", "important");
        }
      }

      let hasAudio = false;
      if (audioTrackRow) {
        const audioContent = document.getElementById("audio-track");
        const hasBlocks =
          audioContent &&
          audioContent.querySelector(
            ".audio-block, .timeline-audio-block--saved, .timeline-audio-block, .temp-audio-block",
          );
        const hasOriginalAudio =
          window.REEL_PROJECT_HAS_AUDIO &&
          (window.REEL_PROJECT_HAS_AUDIO === "True" ||
            window.REEL_PROJECT_HAS_AUDIO === "true" ||
            window.REEL_PROJECT_HAS_AUDIO === true);
        hasAudio = !!hasOriginalAudio || !!hasBlocks;
        if (hasAudio) {
          audioTrackRow.style.setProperty("display", "flex", "important");
          count++;
        } else {
          audioTrackRow.style.setProperty("display", "none", "important");
        }
      }

      if (window.dynamicTrackManager) {
        const textTrackModel = window.dynamicTrackManager.tracks.find(
          (t) => t.type === "text",
        );
        const audioTrackModel = window.dynamicTrackManager.tracks.find(
          (t) => t.type === "audio",
        );
        const effectTrackModel = window.dynamicTrackManager.tracks.find(
          (t) => t.type === "effect",
        );
        const videoTrackModel = window.dynamicTrackManager.tracks.find(
          (t) => t.type === "video",
        );
        if (textTrackModel) textTrackModel.visible = !!hasText;
        if (audioTrackModel) audioTrackModel.visible = !!hasAudio;
        if (effectTrackModel) effectTrackModel.visible = !!hasEffect;
        if (videoTrackModel) videoTrackModel.visible = true;
        window.dynamicTrackManager.updateTrackBadge();
      } else {
        const trackBadge = document.getElementById("tb-bottom-track-info");
        if (trackBadge) {
          trackBadge.innerHTML = `<i data-lucide="layers" style="width:13px;height:13px;color:var(--ve-primary);"></i> ${count} Track${count === 1 ? "" : "s"}`;
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

        const payload = {
          clips: editorState.video_clips,
          trim: editorState.trim,
          speed: editorState.speed,
          audio: {
            volume: editorState.volume,
            muted: editorState.muted,
          },
          text_overlays: editorState.text_overlays,
          resize: editorState.resize,
          effects: {
            grayscale: editorState.grayscale,
            rotate: editorState.rotate,
            fade: editorState.fade,
          },
        };

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

    // ---- Timeline Utilities --------------------------------------------
    function formatTime(secs) {
      if (isNaN(secs) || secs < 0) return "00:00:00.000";
      const h = Math.floor(secs / 3600);
      const m = Math.floor((secs % 3600) / 60);
      const s = Math.floor(secs % 60);
      const ms = Math.floor((secs % 1) * 1000);
      return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
    }

    function generateWaveformSvg(width, height, seed = Math.random()) {
      // Generate professional-looking audio waveform with vertical bars
      let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`;
      // Pure white gradient for audio wave pattern
      svg += `<defs><linearGradient id="waveGrad" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" style="stop-color:#ffffff;stop-opacity:1"/><stop offset="50%" style="stop-color:#ffffff;stop-opacity:0.9"/><stop offset="100%" style="stop-color:#ffffff;stop-opacity:0.75"/></linearGradient></defs>`;

      const centerY = height / 2;
      const barWidth = 3;
      const gap = 2;
      const numBars = Math.floor(width / (barWidth + gap));
      const baseline = centerY;

      for (let i = 0; i < numBars; i++) {
        const x = i * (barWidth + gap);
        // Create semi-random but realistic waveform pattern
        const wave1 = Math.sin(i * 0.15 + seed * 20) * 0.35;
        const wave2 = Math.sin(i * 0.06 + seed * 15) * 0.3;
        const wave3 = Math.sin(i * 0.25 + seed * 10) * 0.25;
        const randomFactor = Math.random() * 0.3;
        const amplitude = Math.max(
          0.1,
          Math.abs(wave1 + wave2 + wave3 + randomFactor),
        );
        const barHeight = Math.max(3, amplitude * height * 0.9);

        // Draw bar above and below center for symmetric look
        const topY = centerY - barHeight / 2;

        svg += `<rect x="${x.toFixed(1)}" y="${topY.toFixed(1)}" width="${barWidth}" height="${barHeight.toFixed(1)}" rx="1.5" fill="url(#waveGrad)"/>`;
      }
      svg += `</svg>`;
      return svg;
    }
    window.generateWaveformSvg = generateWaveformSvg;

    // ── Canva-Style Ruler ────────────────────────────────────────────────────
    // Epsilon for floating-point modulo comparisons
    const RULER_EPSILON = 0.0001;
    // Minimum px gap between two adjacent major-tick labels to prevent overlap
    const RULER_MIN_LABEL_GAP_PX = 48;

    /**
     * Returns { major, minor } tick intervals in seconds for the given px/s density.
     * Intervals follow the sequence: 0.1, 0.2, 0.5, 1, 2, 5, 10, 30, 60 …
     * so major is always a "round" multiple that reads cleanly on screen.
     */
    function getRulerIntervals(pxPerSecond) {
      if (pxPerSecond >= 600) return { major: 0.5,  minor: 0.1  };
      if (pxPerSecond >= 240) return { major: 1.0,  minor: 0.2  };
      if (pxPerSecond >= 120) return { major: 2.0,  minor: 0.5  };
      if (pxPerSecond >= 50)  return { major: 5.0,  minor: 1.0  };
      if (pxPerSecond >= 20)  return { major: 10.0, minor: 2.0  };
      if (pxPerSecond >= 8)   return { major: 30.0, minor: 5.0  };
      if (pxPerSecond >= 3)   return { major: 60.0, minor: 10.0 };
      return                         { major: 300.0, minor: 60.0 };
    }

    /**
     * Format a time value into a clean, short ruler label.
     * Examples: 0 → "0", 5 → "5s", 60 → "1:00", 90 → "1:30", 0.5 → "0.5s"
     */
    function formatRulerLabel(seconds, totalDuration) {
      if (seconds === 0) return "0";
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      const s = seconds % 60;

      if (totalDuration >= 3600) {
        // HH:MM:SS for long videos
        return `${h}:${String(m).padStart(2, "0")}:${String(Math.floor(s)).padStart(2, "0")}`;
      }
      if (m > 0) {
        // MM:SS
        return `${m}:${String(Math.floor(s)).padStart(2, "0")}`;
      }
      // Seconds — show decimal only when needed (e.g. 0.5s zoom)
      if (s % 1 !== 0) {
        return `${s.toFixed(1)}s`;
      }
      return `${Math.round(s)}s`;
    }

    /**
     * Returns the visible time range currently in the scroll viewport.
     * We pad by ±2 seconds so ticks appear slightly before entering view.
     */
    function getRulerViewportRange(pxPerSecond) {
      const scrollArea = document.getElementById("timeline-scroll-area");
      const scrollLeft = scrollArea?.scrollLeft || 0;
      const viewportWidth = scrollArea?.clientWidth || 800;
      const trackOffset = (trimTrack?.offsetLeft || 0) + 20;

      const visibleStartTime = Math.max(0, (scrollLeft - trackOffset) / pxPerSecond - 2);
      const visibleEndTime   = (scrollLeft + viewportWidth - trackOffset) / pxPerSecond + 2;

      return { visibleStartTime, visibleEndTime };
    }

    /**
     * Core render — called on every zoom/scroll/resize event.
     * Uses a DocumentFragment for a single DOM flush.
     */
    function renderRulerTicks() {
      if (!duration || !trimRuler) return;

      const pxPerSecond = basePxPerSecond * zoomFactor;
      const trackOffset = (trimTrack?.offsetLeft || 0) + 20;
      const parentWidth = trimTrack?.parentElement
        ? trimTrack.parentElement.clientWidth - 16
        : 800;
      const totalWidth = Math.max(parentWidth, duration * pxPerSecond) + 300;

      // ── Sync track + text/audio lane widths ──────────────────────────────
      const tracksWrapper = document.querySelector(".timeline-tracks-wrapper");
      if (tracksWrapper) {
        trimRuler.style.marginLeft = window.getComputedStyle(tracksWrapper).marginLeft;
      } else {
        trimRuler.style.marginLeft = "16px";
      }
      trimRuler.style.width = `${trackOffset + totalWidth}px`;
      trimTrack.style.width = `${totalWidth}px`;
      const textTrack = document.getElementById("text-track-content");
      const audioTrackEl = document.getElementById("audio-track");
      if (textTrack)    textTrack.style.width    = `${totalWidth}px`;
      if (audioTrackEl) audioTrackEl.style.width = `${totalWidth}px`;

      // ── Tick geometry ─────────────────────────────────────────────────────
      const { major, minor } = getRulerIntervals(pxPerSecond);
      const { visibleStartTime, visibleEndTime } = getRulerViewportRange(pxPerSecond);

      // Clamp end to a safe max (don't render thousands of ticks beyond duration)
      const renderEnd = Math.min(visibleEndTime, duration + major);

      const firstTickTime = Math.max(0, Math.floor(visibleStartTime / minor) * minor);

      const frag = document.createDocumentFragment();
      let lastLabelX = -Infinity; // anti-overlap guard for labels

      for (let t = firstTickTime; t <= renderEnd + RULER_EPSILON; t += minor) {
        // Normalise away float drift
        const time = Math.round(t / RULER_EPSILON) * RULER_EPSILON;
        const roundedTime = parseFloat(time.toFixed(6));

        if (roundedTime < 0) continue;

        const x = trackOffset + roundedTime * pxPerSecond;

        // Is this a major tick?  modulo check with epsilon tolerance
        const modMajor = roundedTime % major;
        const isMajor  = modMajor < RULER_EPSILON || (major - modMajor) < RULER_EPSILON;

        // ── Tick line ──────────────────────────────────────────────────────
        const tick = document.createElement("div");
        tick.className = isMajor ? "trim-tick major" : "trim-tick";
        tick.style.left = `${x}px`;
        frag.appendChild(tick);

        // ── Label (major ticks only, with anti-overlap guard) ──────────────
        if (isMajor) {
          const labelCenterX = roundedTime === 0 ? x : x; // same x, CSS handles centering

          // Only add label if it won't overlap the previous one
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

      // Single DOM write
      trimRuler.innerHTML = "";
      trimRuler.appendChild(frag);
    }

    function updateRuler() {
      renderRulerTicks();
    }
    // ── End Canva-Style Ruler ────────────────────────────────────────────────

    const clipBlocksContainer = document.getElementById("timeline-clip-blocks");

    // ── Canva-style clip thumbnail rendering ───────────────────────────────
    // Thumbnail frame cache: Map<cacheKey, ImageBitmap>
    // Key = `${videoSrc}|${timeRounded}` so frames are reused across renders.
    const _thumbCache = new Map();
    let _clipThumbAbortController = null;

    // Desired thumbnail width — matches Canva's filmstrip density.
    const THUMB_DESIRED_W = 56; // px per visible slot
    const THUMB_RENDER_W = 112; // canvas pixel width (2× retina)
    const THUMB_RENDER_H = 63; // 16:9

    // Round a seek time to 2 decimal places so nearby seeks reuse the same cache entry.
    function _thumbKey(t) {
      return `${Math.round(t * 100) / 100}`;
    }

    // Seek tempVideo and return an ImageBitmap, reading from cache if available.
    async function _getThumbFrame(tempVideo, t, signal) {
      const key = _thumbKey(t);
      if (_thumbCache.has(key)) return _thumbCache.get(key);

      tempVideo.currentTime = t;
      await Promise.race([
        new Promise((r) =>
          tempVideo.addEventListener("seeked", r, { once: true }),
        ),
        new Promise((r) => setTimeout(r, 700)),
      ]);
      if (signal && signal.aborted) return null;

      let bitmap = null;
      try {
        bitmap = await createImageBitmap(tempVideo, {
          resizeWidth: THUMB_RENDER_W,
          resizeHeight: THUMB_RENDER_H,
          resizeQuality: "medium",
        });
      } catch (_) {
        // createImageBitmap not supported — fall back to canvas drawImage
        const c = document.createElement("canvas");
        c.width = THUMB_RENDER_W;
        c.height = THUMB_RENDER_H;
        c.getContext("2d").drawImage(
          tempVideo,
          0,
          0,
          THUMB_RENDER_W,
          THUMB_RENDER_H,
        );
        // Store a fake bitmap-like object with a canvas instead
        _thumbCache.set(key, { _canvas: c });
        return _thumbCache.get(key);
      }

      _thumbCache.set(key, bitmap);
      // Limit cache size to 300 entries to avoid memory bloat
      if (_thumbCache.size > 300) {
        _thumbCache.delete(_thumbCache.keys().next().value);
      }
      return bitmap;
    }

    // Shared offscreen video element — created once, reused every render.
    let _clipThumbVideo = null;
    function _getClipThumbVideo() {
      if (!_clipThumbVideo) {
        _clipThumbVideo = document.createElement("video");
        _clipThumbVideo.muted = true;
        _clipThumbVideo.playsInline = true;
        _clipThumbVideo.preload = "auto";
        _clipThumbVideo.src = video.src;
      }
      return _clipThumbVideo;
    }

    // Track the last rendered state so we can skip redundant passes.
    let _lastClipRenderKey = "";

    async function renderClipBlocks() {
      if (!clipBlocksContainer || !duration) return;

      const clipsData = editorState.video_clips || [];
      const pxPerSecond = basePxPerSecond * zoomFactor;

      // Build a cheap state key — if nothing changed, just reposition blocks
      // without re-generating any thumbnails.
      const stateKey = `${clipsData.map((c) => `${c.start}-${c.end}`).join(",")}|${pxPerSecond.toFixed(3)}`;

      // Abort any in-progress thumbnail pass
      if (_clipThumbAbortController) {
        _clipThumbAbortController.abort();
      }
      const abortController = new AbortController();
      _clipThumbAbortController = abortController;
      const signal = abortController.signal;

      const gapPx = 3;

      // ── Step 1: Create/update DOM blocks synchronously ────────────────
      // If the state hasn't changed, skip the entire DOM rebuild
      // (thumbnails are already painted and cached).
      const domNeedsRebuild = stateKey !== _lastClipRenderKey;

      if (domNeedsRebuild) {
        clipBlocksContainer.innerHTML = "";
      }

      let accumTime = 0.0;
      const blockInfos = [];

      clipsData.forEach((clip, index) => {
        const clipDur = parseFloat(clip.duration || 0.0);
        const isFirst = index === 0;
        const isLast = index === clipsData.length - 1;
        const blockLeft = accumTime * pxPerSecond + (isFirst ? 0 : gapPx);
        const blockWidth = Math.max(
          20,
          clipDur * pxPerSecond - (isFirst ? 0 : gapPx) - (isLast ? 0 : gapPx),
        );

        let block, thumbContainer;

        if (domNeedsRebuild) {
          block = document.createElement("div");
          block.className = "timeline-clip-block";
          block.style.overflow = "hidden";

          thumbContainer = document.createElement("div");
          thumbContainer.className = "timeline-clip-thumb";
          block.appendChild(thumbContainer);

          const clipStart = parseFloat(
            clip.start != null ? clip.start : accumTime,
          );
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
          clipBlocksContainer.appendChild(block);
        } else {
          // Re-use existing block — just reposition it
          block = clipBlocksContainer.children[index];
          thumbContainer = block
            ? block.querySelector(".timeline-clip-thumb")
            : null;
        }

        if (block) {
          block.style.left = `${blockLeft}px`;
          block.style.width = `${blockWidth}px`;
        }

        const clipStart = parseFloat(
          clip.start != null ? clip.start : accumTime,
        );
        const clipEnd = parseFloat(
          clip.end != null ? clip.end : accumTime + clipDur,
        );
        blockInfos.push({
          block,
          thumbContainer,
          clipStart,
          clipEnd,
          blockWidthPx: blockWidth,
        });
        accumTime += clipDur;
      });

      if (!domNeedsRebuild) {
        // Blocks already have their thumbnails — nothing more to do.
        return;
      }

      // ── Step 2: Fill filmstrips from cache or by seeking ──────────────
      await new Promise((r) => requestAnimationFrame(r));
      if (signal.aborted) return;

      const tempVideo = _getClipThumbVideo();
      const metaReady =
        tempVideo.readyState >= 1
          ? Promise.resolve()
          : new Promise((r) =>
              tempVideo.addEventListener("loadedmetadata", r, { once: true }),
            );
      await Promise.race([metaReady, new Promise((r) => setTimeout(r, 3000))]);
      if (signal.aborted) return;

      for (let i = 0; i < blockInfos.length; i++) {
        if (signal.aborted) return;
        const { thumbContainer, clipStart, clipEnd, blockWidthPx } =
          blockInfos[i];
        const clipDuration = clipEnd - clipStart;
        if (clipDuration <= 0 || blockWidthPx <= 0 || !thumbContainer) continue;

        const renderedWidth = blockInfos[i].block.clientWidth || blockWidthPx;
        const count = Math.max(1, Math.floor(renderedWidth / THUMB_DESIRED_W));
        const slotW = renderedWidth / count;

        thumbContainer.innerHTML = "";

        for (let j = 0; j < count; j++) {
          if (signal.aborted) return;

          const t = clipStart + (clipDuration * (j + 0.5)) / count;
          const seekT = Math.max(clipStart, Math.min(clipEnd - 0.001, t));
          const bitmap = await _getThumbFrame(tempVideo, seekT, signal);
          if (signal.aborted) return;

          const isLastSlot = j === count - 1;
          const slotPx = isLastSlot
            ? renderedWidth - Math.round(slotW) * (count - 1)
            : Math.round(slotW);

          const canvas = document.createElement("canvas");
          canvas.width = THUMB_RENDER_W;
          canvas.height = THUMB_RENDER_H;
          canvas.style.cssText = `display:block;width:${slotPx}px;height:100%;flex-shrink:0;object-fit:cover;`;

          try {
            const ctx = canvas.getContext("2d");
            if (bitmap && bitmap._canvas) {
              ctx.drawImage(bitmap._canvas, 0, 0);
            } else if (bitmap) {
              ctx.drawImage(bitmap, 0, 0, THUMB_RENDER_W, THUMB_RENDER_H);
            }
          } catch (err) {
            console.warn("Clip thumbnail draw error:", err);
          }
          thumbContainer.appendChild(canvas);
        }
      }

      _lastClipRenderKey = stateKey;
    }

    function renderTrim() {
      if (!duration) return;

      const pxPerSecond = basePxPerSecond * zoomFactor;
      const leftPx = startSeconds * pxPerSecond;
      const rightPx = endSeconds * pxPerSecond;
      const playheadPx = video.currentTime * pxPerSecond;

      // Position and size trim thumbnails to only cover selected range
      trimThumbnails.style.left = `${leftPx}px`;
      trimThumbnails.style.width = `${rightPx - leftPx}px`;
      trimThumbnails.style.position = "absolute";
      trimThumbnails.style.top = "0";
      trimThumbnails.style.bottom = "0";
      trimThumbnails.style.overflow = "hidden";
      trimThumbnails.style.display = "flex";

      // Highlight selection box
      trimSelection.style.left = `${leftPx}px`;
      trimSelection.style.width = `${rightPx - leftPx}px`;

      // Dim overlays
      trimDimLeft.style.width = `${leftPx}px`;
      trimDimRight.style.left = `${rightPx}px`;
      trimDimRight.style.width = `${duration * pxPerSecond - rightPx}px`;

      // Playhead — offset by track-label-cell width so the line aligns
      // with the content area and spans across ALL tracks (Text, Video, Audio)
      const trackLabelWidth = trimTrack.offsetLeft; // distance from wrapper edge to content area
      trimPlayhead.style.left = `${trackLabelWidth + playheadPx}px`;
      const playheadTooltip = document.getElementById("playhead-tooltip");
      if (playheadTooltip) {
        playheadTooltip.textContent = formatTime(video.currentTime);
      }

      // Time displays
      if (currentDisplay)
        currentDisplay.textContent = formatTime(video.currentTime);
      if (totalDisplay) totalDisplay.textContent = formatTime(duration);

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

      // Render multi-track timeline blocks
      renderAllTimelineTracks();
      renderSplitMarkers();
      renderClipBlocks();
      // Regenerate trim thumbnails only when selection range changes
      generateThumbnails();

      // Toggle selected-delete highlight class and enable/disable delete button
      const deleteBtnEl = document.getElementById("tb-delete");
      if (globalSelection.track !== null) {
        if (deleteBtnEl) deleteBtnEl.removeAttribute("disabled");
      } else {
        if (deleteBtnEl) deleteBtnEl.setAttribute("disabled", "true");
      }

      if (globalSelection.track === "video") {
        trimSelection.classList.add("selected-delete");
      } else {
        trimSelection.classList.remove("selected-delete");
      }

      updateTrackRowVisibility();
    }

    function getSecondsFromX(clientX) {
      const rect = trimTrack.getBoundingClientRect();
      const pxPerSecond = basePxPerSecond * zoomFactor;
      const relativeX = clientX - rect.left;
      const s = relativeX / pxPerSecond;
      return Math.max(0, Math.min(duration, s));
    }

    // Dragging helper
    function setupDrag(element, onDrag, onDragEnd) {
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
        if (s < 0) s = 0;
        if (s > endSeconds - 0.5) s = endSeconds - 0.5;
        startSeconds = s;
        renderTrim();
      },
      autoSubmitTrim,
    );

    // Right handle drag
    setupDrag(
      handleRight,
      (clientX) => {
        let e = getSecondsFromX(clientX);
        if (e > duration) e = duration;
        if (e < startSeconds + 0.5) e = startSeconds + 0.5;
        endSeconds = e;
        renderTrim();
      },
      autoSubmitTrim,
    );

    // Video playback sync
    video.addEventListener("timeupdate", () => {
      if (trimPlayhead.classList.contains("dragging")) return;
      const pxPerSecond = basePxPerSecond * zoomFactor;
      const timelineTime = sourceToTimelineTime(video.currentTime);
      
      // Trim selection loop (if playing within a selection bounds)
      if (!video.paused && timelineTime > endSeconds) {
        video.currentTime = timelineToSourceTime(startSeconds);
        return;
      }

      // Transition between clips during preview
      if (!video.paused && editorState.video_clips && editorState.video_clips.length > 0) {
        const t = video.currentTime;
        let activeClipIndex = -1;
        for (let i = 0; i < editorState.video_clips.length; i++) {
          const clip = editorState.video_clips[i];
          const trimStart = parseFloat(clip.trimStart !== undefined ? clip.trimStart : 0);
          const trimEnd = parseFloat(clip.trimEnd !== undefined ? clip.trimEnd : (trimStart + clip.duration));
          if (t >= trimStart && t <= trimEnd) {
            activeClipIndex = i;
            break;
          }
        }
        
        if (activeClipIndex !== -1) {
          const clip = editorState.video_clips[activeClipIndex];
          const trimEnd = parseFloat(clip.trimEnd !== undefined ? clip.trimEnd : (clip.trimStart + clip.duration));
          if (t >= trimEnd - 0.1) {
            if (activeClipIndex + 1 < editorState.video_clips.length) {
              const nextClip = editorState.video_clips[activeClipIndex + 1];
              video.currentTime = parseFloat(nextClip.trimStart !== undefined ? nextClip.trimStart : 0);
              return;
            } else {
              video.pause();
              video.currentTime = parseFloat(editorState.video_clips[0].trimStart !== undefined ? editorState.video_clips[0].trimStart : 0);
              return;
            }
          }
        }
      }

      const playheadPx = timelineTime * pxPerSecond;
      const trackOffset = trimTrack.offsetLeft;
      trimPlayhead.style.left = `${trackOffset + playheadPx}px`;
      if (currentDisplay) {
        currentDisplay.textContent = formatTime(timelineTime);
      }
      const playheadTooltip = document.getElementById("playhead-tooltip");
      if (playheadTooltip) {
        playheadTooltip.textContent = formatTime(timelineTime);
      }
      // Update video time display
      const timeCurrentEl = document.getElementById("video-time-current");
      if (timeCurrentEl) {
        timeCurrentEl.textContent = formatTime(timelineTime);
      }

      // Re-render text overlays during playback
      renderTextOverlays();

      // Auto-scroll timeline to keep playhead in view
      const scrollArea = trimContainer.querySelector(".timeline-scroll-area");
      if (scrollArea && !video.paused) {
        const playheadLeft = playheadPx;
        const viewportWidth = scrollArea.clientWidth;
        const scrollLeft = scrollArea.scrollLeft;

        // If playhead is near or past the right edge, or behind the left edge, scroll it into view
        if (playheadLeft > scrollLeft + viewportWidth - 150) {
          scrollArea.scrollLeft = playheadLeft - 150;
        } else if (playheadLeft < scrollLeft + 20) {
          scrollArea.scrollLeft = Math.max(0, playheadLeft - 20);
        }
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
      const isMuted = video.muted || video.volume === 0;
      if (volumeSlider) {
        volumeSlider.value = video.muted ? 0 : video.volume;
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
        video.muted = val === 0;
        syncVolumeUI();
      });
    }

    if (btnMute) {
      btnMute.addEventListener("click", () => {
        video.muted = !video.muted;
        syncVolumeUI();
      });
    }

    video.addEventListener("volumechange", syncVolumeUI);

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
      const maxDuration = duration || 0;
      if (video.paused) {
        if (video.ended || sourceToTimelineTime(video.currentTime) >= maxDuration) {
          video.currentTime = timelineToSourceTime(0);
        }
        video.play().catch((err) => console.warn("Playback prevented:", err));
      } else {
        video.pause();
      }
    };

    if (btnPlayPause) {
      btnPlayPause.addEventListener("click", togglePlayPause);
    }

    // Clicking on video toggle play/pause
    video.addEventListener("click", (e) => {
      e.stopPropagation();
      togglePlayPause();
    });

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
        if (btnMute) btnMute.click();
      } else if (e.code === "KeyF") {
        e.preventDefault();
        if (btnFullscreen) btnFullscreen.click();
      } else if (e.code === "KeyS") {
        e.preventDefault();
        const splitBtn = document.getElementById("tb-split");
        if (splitBtn && !splitBtn.hasAttribute("disabled")) {
          splitSelectedTimelineItem();
        }
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
      trimContainer.classList.toggle("fullscreen-mode");
      const isFs = trimContainer.classList.contains("fullscreen-mode");
      if (isFs) {
        document.body.style.overflow = "hidden";
      } else {
        document.body.style.overflow = "";
      }
      updateRuler();
      renderTrim();
    };

    if (tbBottomFullscreen)
      tbBottomFullscreen.addEventListener("click", toggleTimelineFullscreen);
    if (fsTimelineBtn)
      fsTimelineBtn.addEventListener("click", toggleTimelineFullscreen);

    // --- Modular Track Manager & Dynamic Timeline Architecture ---
    class DynamicTrackManager {
      constructor() {
        this.tracks = [];
        this.initDefaultTracks();
      }

      initDefaultTracks() {
        // Generate dynamic track models for Text, Effect, Video, and Audio
        this.tracks = [
          {
            id: "text-track-row",
            type: "text",
            name: "Text Overlay Track",
            order: 0,
            height: 40,
            visible: false,
            locked: false,
            clips: [],
          },
          {
            id: "effect-track-row",
            type: "effect",
            name: "Effects & Filters Track",
            order: 1,
            height: 32,
            visible: false,
            locked: false,
            clips: [],
          },
          {
            id: "video-track-row",
            type: "video",
            name: "Main Video Track",
            order: 2,
            height: 64,
            visible: true,
            locked: false,
            clips: [],
          },
          {
            id: "audio-track-row",
            type: "audio",
            name: "Audio Track",
            order: 3,
            height: 48,
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
        if (trackBadge) {
          const activeCount = this.tracks.filter((t) => t.visible).length;
          trackBadge.innerHTML = `<i data-lucide="layers" style="width:13px;height:13px;color:var(--ve-primary);"></i> ${activeCount} Track${activeCount === 1 ? "" : "s"}`;
          if (typeof lucide !== "undefined") lucide.createIcons();
        }
      }

      updateTrackVisibilities() {
        // Text track: visible if there are text overlays
        const hasText = !!(editorState.text_overlays && editorState.text_overlays.length > 0);
        const textTrack = this.tracks.find((t) => t.type === "text");
        if (textTrack) textTrack.visible = hasText;

        // Effect track: visible if there are active effects
        const hasEffects = !!(
          editorState.grayscale ||
          editorState.rotate ||
          editorState.resize ||
          editorState.fade ||
          (editorState.active_effects && editorState.active_effects.length > 0)
        );
        const effectTrack = this.tracks.find((t) => t.type === "effect");
        if (effectTrack) effectTrack.visible = hasEffects;

        // Audio track: visible if project has original audio OR background audios exist
        const hasAudio = !!(
          window.REEL_PROJECT_HAS_AUDIO === "True" ||
          (editorState.background_audios && editorState.background_audios.length > 0)
        );
        const audioTrack = this.tracks.find((t) => t.type === "audio");
        if (audioTrack) audioTrack.visible = hasAudio;

        // Video track: always visible
        const videoTrack = this.tracks.find((t) => t.type === "video");
        if (videoTrack) videoTrack.visible = true;

        this.renderAllTracks();
      }

      renderAllTracks() {
        // Loop through all track models and update visibility & layout dimensions
        this.tracks.forEach((track) => {
          const trackEl = document.querySelector(`.${track.id}`);
          if (trackEl) {
            if (track.visible) {
              trackEl.style.setProperty("display", "flex", "important");
            } else {
              trackEl.style.setProperty("display", "none", "important");
            }
          }
        });
        this.updateTrackBadge();
      }
    }

    const trackManager = new DynamicTrackManager();
    window.dynamicTrackManager = trackManager;

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
        trimContainer.classList.add("timeline-collapsed");
        trimContainer.style.height = "128px";
        if (collapseText) collapseText.textContent = "Expand";
        if (collapseIcon)
          collapseIcon.setAttribute("data-lucide", "chevron-up");
      } else {
        trimContainer.classList.remove("timeline-collapsed");
        trimContainer.style.height = `${lastExpandedHeight}px`;
        if (collapseText) collapseText.textContent = "Minimize";
        if (collapseIcon)
          collapseIcon.setAttribute("data-lucide", "chevron-down");
      }
      if (typeof lucide !== "undefined") lucide.createIcons();
      localStorage.setItem(
        "ve_timeline_collapsed",
        collapsed ? "true" : "false",
      );
      updateRuler();
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
      video.currentTime = timelineToSourceTime(time);
    }, 100);

    // Drag or click on timeline ruler to seek video
    setupDrag(
      trimRuler,
      (clientX) => {
        let time = getSecondsFromX(clientX);
        if (time < 0) time = 0;
        if (time > duration) time = duration;
        dragLastTime = time;

        if (!video.paused) {
          video.pause();
        }
        seekVideoThrottled(time);

        const pxPerSecond = basePxPerSecond * zoomFactor;
        trimPlayhead.style.left = `${trimTrack.offsetLeft + 20 + time * pxPerSecond}px`;
        currentDisplay.textContent = formatTime(time);
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
        trimPlayhead.classList.remove("dragging");
        video.currentTime = timelineToSourceTime(dragLastTime); // Ensure final seek is exact
      },
    );

    // Grab and drag the playhead needle/cap directly
    setupDrag(
      trimPlayhead,
      (clientX) => {
        let time = getSecondsFromX(clientX);
        if (time < 0) time = 0;
        if (time > duration) time = duration;
        dragLastTime = time;

        if (!video.paused) {
          video.pause();
        }
        seekVideoThrottled(time);

        const pxPerSecond = basePxPerSecond * zoomFactor;
        trimPlayhead.style.left = `${trimTrack.offsetLeft + 20 + time * pxPerSecond}px`;
        currentDisplay.textContent = formatTime(time);
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
        trimPlayhead.classList.remove("dragging");
        video.currentTime = timelineToSourceTime(dragLastTime); // Ensure final seek is exact
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

      const span = document.createElement("span");
      span.style.color = "#fff";
      span.style.fontSize = "11px";
      span.style.overflow = "hidden";
      span.style.textOverflow = "ellipsis";
      span.style.whiteSpace = "nowrap";
      span.style.marginRight = "6px";
      span.style.flexGrow = "1";
      span.style.position = "relative";
      span.style.zIndex = "1";
      span.style.fontWeight = "bold";
      span.style.textShadow = "0 1px 2px rgba(0,0,0,0.5)";
      span.textContent = `🎵 ${audioOverlay.filename}`;

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
      applyBtn.onclick = (e) => {
        e.stopPropagation();
        const bgForm = document.getElementById("bg-audio-form");
        if (bgForm) {
          const overlay = document.getElementById("processing-overlay");
          if (overlay) {
            overlay.style.display = "flex";
            const txt = overlay.querySelector("p");
            if (txt) txt.textContent = "Adding background audio...";
          }
          bgForm.submit();
        }
      };

      el.appendChild(handleL);
      el.appendChild(span);
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
        tooltipL.textContent = formatTime(audioOverlay.start);
        tooltipR.textContent = formatTime(audioOverlay.end);

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
        tooltipL.textContent = formatTime(audioOverlay.start);

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
        tooltipR.textContent = formatTime(audioOverlay.end);

        const bgForm = document.getElementById("bg-audio-form");
        if (bgForm) {
          const endIn = bgForm.querySelector('input[name="end_seconds"]');
          if (endIn) endIn.value = audioOverlay.end;
        }
      });

      audioTrack.appendChild(el);
      updateTrackRowVisibility();
    }

    if (timelineAddAudioBtn && audioFileIn) {
      timelineAddAudioBtn.addEventListener("click", () => {
        audioFileIn.click();
      });
    }
    // --- Zoom Control Listeners ---
    if (btnZoomIn) {
      btnZoomIn.addEventListener("click", () => {
        zoomFactor = Math.min(10.0, zoomFactor * 1.4);
        _lastClipRenderKey = ""; // invalidate clip cache on zoom
        _lastTrimThumbKey = "";
        updateRuler();
        renderTrim();
        generateThumbnails();
        renderAudioOverlay();
      });
    }

    if (btnZoomOut) {
      btnZoomOut.addEventListener("click", () => {
        zoomFactor = Math.max(0.001, zoomFactor / 1.4);
        _lastClipRenderKey = "";
        _lastTrimThumbKey = "";
        updateRuler();
        renderTrim();
        generateThumbnails();
        renderAudioOverlay();
      });
    }

    if (btnZoomFit) {
      btnZoomFit.addEventListener("click", () => {
        const parentWidth = trimTrack.parentElement.clientWidth;
        if (parentWidth && duration) {
          zoomFactor = parentWidth / (duration * basePxPerSecond);
          _lastClipRenderKey = "";
          _lastTrimThumbKey = "";
          updateRuler();
          renderTrim();
          generateThumbnails();
          renderAudioOverlay();
        }
      });
    }

    // --- Clips and Split points logic ---
    let splitPoints = [];
    let selectedClipIndex = -1;

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
      splitPoints.forEach((t) => {
        const el = document.createElement("div");
        el.className = "trim-split-marker";
        el.style.left = `${t * pxPerSecond}px`;
        tracksWrapper.appendChild(el);
      });
    }

    // Click on the video track to select a segment
    if (trimTrack) {
      trimTrack.addEventListener("click", (e) => {
        // If clicking handles, ignore to prevent selection reset during drag
        if (
          e.target.classList.contains("trim-handle") ||
          e.target.closest(".trim-handle")
        ) {
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
      if (!globalSelection.track) return;

      const curT = parseFloat(video.currentTime.toFixed(2));
      if (!Number.isFinite(curT) || curT <= 0 || curT >= duration) return;

      if (globalSelection.track === "video") {
        const index = globalSelection.index;
        const clip = editorState.video_clips?.[index];
        if (
          !clip ||
          curT <= (clip.start || 0) ||
          curT >= (clip.end || duration)
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

        editorState.video_clips.splice(index + 1, 0, newClip);
        
        recalculateVideoClipsTimeline();
        clearGlobalSelection();

        renderClipBlocks();
        renderAllTimelineTracks();
        updateRuler();
        renderTrim();
        generateThumbnails();
        updateVideoProgress();

        if (window.updateLocalState)
          window.updateLocalState("Video", "Split video clip");
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
      updateVideoProgress();

      if (window.updateLocalState)
        window.updateLocalState(globalSelection.track, "Split item");
    }

    function deleteSelectedTimelineItem() {
      if (!globalSelection.track) return;

      if (globalSelection.track === "video") {
        editorState.video_clips?.splice(globalSelection.index, 1);
        
        recalculateVideoClipsTimeline();
        clearGlobalSelection();

        renderClipBlocks();
        renderAllTimelineTracks();
        updateRuler();
        renderTrim();
        generateThumbnails();
        updateVideoProgress();

        if (window.updateLocalState)
          window.updateLocalState("Video", "Deleted video clip");
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
      updateVideoProgress();

      if (window.updateLocalState)
        window.updateLocalState(globalSelection.track, "Deleted item");
    }

    // Split button click
    const splitBtn = document.getElementById("tb-split");
    if (splitBtn) {
      splitBtn.addEventListener("click", splitSelectedTimelineItem);
    }

    const deleteBtn = document.getElementById("tb-delete");
    if (deleteBtn) {
      deleteBtn.addEventListener("click", deleteSelectedTimelineItem);
    }

    // Initialization
    video.addEventListener("loadedmetadata", initTrim);
    video.addEventListener("timeupdate", onTimeUpdate);

    function onTimeUpdate() {
      if (!duration) return;
      const t = video.currentTime;

      // Trim loop
      if (t > endSeconds && !video.paused) {
        video.currentTime = startSeconds;
        video.play();
      }

      // Text overlays visibility
      const textContainer = document.getElementById("text-overlay-container");
      if (textContainer) {
        const textElements = textContainer.children;
        editorState.text_overlays.forEach((overlay, i) => {
          if (textElements[i]) {
            if (t >= overlay.start && t <= overlay.end) {
              textElements[i].style.display = "block";
            } else {
              textElements[i].style.display = "none";
            }
          }
        });
      }

      // Background Audio sync
      if (editorState.background_audios) {
        editorState.background_audios.forEach((bg, i) => {
          let audioEl = document.getElementById(`preview-bg-audio-${i}`);
          if (!audioEl) {
            audioEl = document.createElement("audio");
            audioEl.id = `preview-bg-audio-${i}`;
            audioEl.src = bg.url;
            document.body.appendChild(audioEl);
          }

          audioEl.volume = bg.bg_volume;
          const bgEnd = bg.end || duration;

          if (t >= bg.start && t <= bgEnd) {
            // Need to play it and keep it synced
            if (audioEl.paused) {
              audioEl.currentTime = t - bg.start;
              audioEl.play().catch((e) => console.log("Audio play blocked", e));
            } else {
              // Drift correction
              if (Math.abs(audioEl.currentTime - (t - bg.start)) > 0.3) {
                audioEl.currentTime = t - bg.start;
              }
            }
          } else {
            if (!audioEl.paused) audioEl.pause();
          }

          // Stop audio if video is paused
          if (video.paused && !audioEl.paused) {
            audioEl.pause();
          }
        });
      }
    }

    video.addEventListener("play", () => onTimeUpdate());
    video.addEventListener("pause", () => onTimeUpdate());
    if (video.readyState >= 1) {
      initTrim();
    }

    let currentThumbnailAbortController = null;

    function initTrim() {
      duration = video.duration;
      window.duration = duration;
      if (!duration) return;

      // Update video time display
      const timeTotalEl = document.getElementById("video-time-total");
      if (timeTotalEl) {
        timeTotalEl.textContent = formatTime(video.duration);
      }
      const timeCurrentEl = document.getElementById("video-time-current");
      if (timeCurrentEl) {
        timeCurrentEl.textContent = formatTime(video.currentTime);
      }

      if (editorState.trim && editorState.trim.start !== undefined && editorState.trim.end > 0) {
        startSeconds = editorState.trim.start;
        endSeconds = editorState.trim.end;
      } else {
        startSeconds =
          startInput && startInput.value ? parseFloat(startInput.value) : 0;
        endSeconds =
          endInput && endInput.value ? parseFloat(endInput.value) : duration;
      }

      if (startSeconds < 0) startSeconds = 0;
      if (endSeconds > duration || endSeconds <= startSeconds)
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
            e.target.closest(".timeline-audio-block")
          ) {
            return;
          }
          const newTime = getSecondsFromX(e.clientX);
          video.currentTime = newTime;
          renderTrim();
          // Update time display and progress bar immediately
          const timeCurrentEl = document.getElementById("video-time-current");
          if (timeCurrentEl) {
            timeCurrentEl.textContent = formatTime(newTime);
          }
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
      generateThumbnails();
      renderAudioOverlay();
      updateVideoProgress();

      // Hydrate client history drawer on load
      if (editorState.grayscale) addHistoryItem("Grayscale", "Applied grayscale filter");
      if (editorState.rotate) addHistoryItem("Rotate", `Rotated ${editorState.rotate}°`);
      if (editorState.resize) addHistoryItem("Resize", `Resized to ${editorState.resize.width}x${editorState.resize.height}`);
      if (editorState.fade) addHistoryItem("Fade", `Applied fade in ${editorState.fade.in}s / out ${editorState.fade.out}s`);
      if (editorState.speed && editorState.speed !== 1.0) addHistoryItem("Speed", `Changed speed to ${editorState.speed}x`);
      if (editorState.volume !== 1.0) addHistoryItem("Volume", `Set volume to ${editorState.volume}x`);
      if (editorState.muted) addHistoryItem("Mute", "Muted audio track");
      if (editorState.text_overlays) {
        editorState.text_overlays.forEach(overlay => {
          addHistoryItem("Text", `Added text overlay: "${overlay.text}"`);
        });
      }
      if (editorState.background_audios) {
        editorState.background_audios.forEach(audio => {
          addHistoryItem("Audio", `Added background audio`);
        });
      }
    }

    // Dynamic filmstrip thumbnail generator for the trim-selection area.
    // Uses the shared _thumbCache — frames already loaded by renderClipBlocks
    // are instantly reused without any extra video seeks.
    let _lastTrimThumbKey = "";
    async function generateThumbnails() {
      if (!duration) return;

      if (currentThumbnailAbortController) {
        currentThumbnailAbortController.abort();
      }
      const abortController = new AbortController();
      currentThumbnailAbortController = abortController;
      const signal = abortController.signal;

      const visibleDuration = endSeconds - startSeconds;
      if (visibleDuration <= 0) return;

      const pxPerSecond = basePxPerSecond * zoomFactor;
      const containerW =
        trimThumbnails.clientWidth || Math.round(visibleDuration * pxPerSecond);
      if (containerW <= 0) return;

      const count = Math.max(1, Math.floor(containerW / THUMB_DESIRED_W));

      // Build a state key — skip the whole pass if nothing changed
      const stateKey = `${startSeconds.toFixed(3)}-${endSeconds.toFixed(3)}|${pxPerSecond.toFixed(3)}|${containerW}`;
      if (
        stateKey === _lastTrimThumbKey &&
        trimThumbnails.children.length === count
      )
        return;

      trimThumbnails.innerHTML = "";
      const slotW = containerW / count;

      // Reuse the same shared offscreen video
      const tempVideo = _getClipThumbVideo();
      const metaReady =
        tempVideo.readyState >= 1
          ? Promise.resolve()
          : new Promise((r) =>
              tempVideo.addEventListener("loadedmetadata", r, { once: true }),
            );
      await Promise.race([metaReady, new Promise((r) => setTimeout(r, 3000))]);
      if (signal.aborted) return;

      try {
        for (let i = 0; i < count; i++) {
          if (signal.aborted) return;

          const t = startSeconds + (visibleDuration * (i + 0.5)) / count;
          const seekT = Math.max(startSeconds, Math.min(endSeconds - 0.001, t));
          const bitmap = await _getThumbFrame(tempVideo, seekT, signal);
          if (signal.aborted) return;

          const isLast = i === count - 1;
          const slotPx = isLast
            ? containerW - Math.round(slotW) * (count - 1)
            : Math.round(slotW);

          const canvas = document.createElement("canvas");
          canvas.width = THUMB_RENDER_W;
          canvas.height = THUMB_RENDER_H;
          canvas.style.cssText = `display:block;width:${slotPx}px;height:100%;flex-shrink:0;object-fit:cover;`;

          const ctx = canvas.getContext("2d");
          if (bitmap && bitmap._canvas) {
            ctx.drawImage(bitmap._canvas, 0, 0);
          } else if (bitmap) {
            ctx.drawImage(bitmap, 0, 0, THUMB_RENDER_W, THUMB_RENDER_H);
          }
          trimThumbnails.appendChild(canvas);
        }
        _lastTrimThumbKey = stateKey;
      } catch (err) {
        console.error("Error generating timeline thumbnails:", err);
      }
    }

    // ── ResizeObserver: re-render thumbnails when timeline width changes ──
    if (typeof ResizeObserver !== "undefined" && trimTrack) {
      let _resizeTimer = null;
      const _roClips = new ResizeObserver(() => {
        clearTimeout(_resizeTimer);
        _resizeTimer = setTimeout(() => {
          if (duration) {
            _lastClipRenderKey = ""; // width changed → recount slots
            _lastTrimThumbKey = "";
            renderClipBlocks();
            generateThumbnails();
          }
        }, 120);
      });
      _roClips.observe(trimTrack);
    }
  }
})();
