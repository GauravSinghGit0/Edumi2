/**
 * Video Editor Module — Canva-Style Media Library & UnifiedMediaUploader
 */
  // ---- Event Delegation for Tool Tabs, Canva Dock & History Drawer -------------------
  document.addEventListener("click", (e) => {
    // 0. Drawer Close Button
    const closeDrawerBtn = e.target.closest(".ve-drawer-close-btn");
    if (closeDrawerBtn) {
      const grid = document.querySelector(".ve-editor-grid");
      if (grid) grid.classList.add("sidebar-collapsed");
      document.querySelectorAll(".ve-dock-btn").forEach((b) => b.classList.remove("active"));
      try { localStorage.setItem("ve_sidebar_collapsed", "true"); } catch (err) {}
      setTimeout(() => window.dispatchEvent(new Event("resize")), 240);
      return;
    }

    // 1. Tool Tab & Canva Dock Switching
    const tab = e.target.closest(".tool-tab, .ve-tool-tab, .ve-dock-btn");
    if (tab) {
      const grid = document.querySelector(".ve-editor-grid");
      const isDockBtn = tab.classList.contains("ve-dock-btn");
      const isCollapsed = grid ? grid.classList.contains("sidebar-collapsed") : false;
      const target = tab.dataset.tab;

      // If clicking already-active dock button while open -> collapse it
      if (isDockBtn && tab.classList.contains("active") && !isCollapsed) {
        if (grid) grid.classList.add("sidebar-collapsed");
        tab.classList.remove("active");
        try { localStorage.setItem("ve_sidebar_collapsed", "true"); } catch (err) {}
        setTimeout(() => window.dispatchEvent(new Event("resize")), 240);
        return;
      }

      // Otherwise, open/expand drawer
      if (grid && isCollapsed) {
        grid.classList.remove("sidebar-collapsed");
      }
      try { localStorage.setItem("ve_sidebar_collapsed", "false"); } catch (err) {}

      const tabs = document.querySelectorAll(".tool-tab, .ve-tool-tab, .ve-dock-btn");
      const panels = document.querySelectorAll(".tool-section, .ve-tool-section");

      tabs.forEach((t) => {
        t.classList.remove("tool-tab--active", "ve-tool-tab--active", "active");
      });
      tab.classList.add("active");
      if (tab.classList.contains("tool-tab") || tab.classList.contains("ve-tool-tab")) {
        tab.classList.add("tool-tab--active", "ve-tool-tab--active");
      }

      // Sync any corresponding tab or dock button
      tabs.forEach((t) => {
        if (t.dataset.tab === target) {
          t.classList.add("active");
          if (t.classList.contains("tool-tab") || t.classList.contains("ve-tool-tab")) {
            t.classList.add("tool-tab--active", "ve-tool-tab--active");
          }
        }
      });

      panels.forEach((p) => {
        const isActive = p.dataset.panel === target;
        p.classList.toggle("tool-section--active", isActive);
        p.classList.toggle("ve-tool-section--active", isActive);
      });
      setTimeout(() => window.dispatchEvent(new Event("resize")), 240);
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

  // Close history drawer on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const historyDrawer = document.getElementById("history-drawer");
      if (historyDrawer && historyDrawer.classList.contains("open")) {
        historyDrawer.classList.remove("open");
      }
    }
  });

  // Activate tab from URL query parameter if present, or restore collapse state
  const activateTabFromUrl = () => {
    const urlParams = new URLSearchParams(window.location.search);
    let activeTab = urlParams.get("tab");
    if (activeTab === "fx") activeTab = "effects";
    if (activeTab) {
      const targetTab = document.querySelector(
        `.tool-tab[data-tab="${activeTab}"], .ve-tool-tab[data-tab="${activeTab}"], .ve-dock-btn[data-tab="${activeTab}"]`,
      );
      if (targetTab) {
        targetTab.click();
      }
    } else {
      try {
        if (localStorage.getItem("ve_sidebar_collapsed") === "true") {
          const grid = document.querySelector(".ve-editor-grid");
          if (grid) grid.classList.add("sidebar-collapsed");
          document.querySelectorAll(".ve-dock-btn").forEach((b) => b.classList.remove("active"));
        }
      } catch (err) {}
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
  if (window.REEL_PROJECT_PROXY_STATUS && window.REEL_PROJECT_PROXY_STATUS !== "completed") {
    const pollProxy = setInterval(async () => {
      try {
        const proxyUrlEndpoint = `/video-editing/project/${window.REEL_PROJECT_ID}/proxy-status/`;
        const res = await fetch(proxyUrlEndpoint);
        if (res.ok) {
          const data = await res.json();
          if (data.status === "completed" && data.url) {
            clearInterval(pollProxy);
            const v = document.getElementById("main-video");
            if (v && (!v.src || !v.src.includes(data.url))) {
              const curTime = v.currentTime || 0;
              const wasPlaying = !v.paused;
              v.src = data.url;
              v.currentTime = curTime;
              if (wasPlaying) v.play().catch(() => {});
            }
            const prep = document.getElementById("preview-preparing-overlay");
            if (prep) prep.style.display = "none";
            window.REEL_PROJECT_PROXY_STATUS = "completed";
            window.REEL_PROJECT_PROXY_URL = data.url;
            if (typeof loadFilmstripThumbs === "function") {
              loadFilmstripThumbs();
            }
          }
        }
      } catch (err) {
        clearInterval(pollProxy);
      }
    }, 2000);
  }

  // =========================================================================
  // UNIFIED MODULAR MEDIA UPLOADER (Industry-Grade Multi-Media Pipeline)
  // Handles Audio, Video, and Images through a single, robust, reusable service.
  // =========================================================================
  const UnifiedMediaUploader = (function () {
    const allowedExtensions = {
      video: ["mp4", "mov", "avi", "mkv", "webm", "m4v", "flv", "wmv"],
      audio: ["mp3", "wav", "aac", "ogg", "m4a", "flac", "wma"],
      image: ["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"]
    };

    const maxSizes = {
      video: 500 * 1024 * 1024, // 500MB
      audio: 50 * 1024 * 1024,  // 50MB
      image: 50 * 1024 * 1024   // 50MB
    };

    function detectCategory(file) {
      if (!file) return "video";
      const ext = (file.name || "").split(".").pop().toLowerCase();
      if (allowedExtensions.audio.includes(ext) || (file.type && file.type.startsWith("audio/"))) return "audio";
      if (allowedExtensions.image.includes(ext) || (file.type && file.type.startsWith("image/"))) return "image";
      return "video";
    }

    function validateFile(file) {
      if (!file) return "No file selected.";
      const ext = (file.name || "").split(".").pop().toLowerCase();
      const cat = detectCategory(file);
      const allowed = allowedExtensions[cat] || [];
      if (!allowed.includes(ext)) {
        return `Unsupported format ".${ext}". Allowed: ${allowed.map((e) => "." + e).join(", ")}`;
      }
      const max = maxSizes[cat] || (50 * 1024 * 1024);
      if (file.size > max) {
        const mb = Math.round(max / (1024 * 1024));
        return `File "${file.name}" exceeds maximum allowed size of ${mb}MB.`;
      }
      return null;
    }

    function extractDuration(file) {
      return new Promise((resolve) => {
        const cat = detectCategory(file);
        if (cat === "image") return resolve(5.0);
        const isVideo = cat === "video";
        const el = document.createElement(isVideo ? "video" : "audio");
        el.preload = "metadata";
        const blobUrl = URL.createObjectURL(file);
        el.src = blobUrl;
        const timer = setTimeout(() => {
          URL.revokeObjectURL(blobUrl);
          resolve(0);
        }, 3500);
        el.onloadedmetadata = () => {
          clearTimeout(timer);
          const dur = el.duration || 0;
          URL.revokeObjectURL(blobUrl);
          resolve(dur);
        };
        el.onerror = () => {
          clearTimeout(timer);
          URL.revokeObjectURL(blobUrl);
          resolve(0);
        };
      });
    }

    let activeUploadCount = 0;
    let uploadIndicator = null;

    function showIndicator(filesCount, firstFileName) {
      const assetsGrid = document.getElementById("assets-grid-container");
      const triggerBtn = document.getElementById("btn-trigger-upload-asset");
      if (triggerBtn) {
        triggerBtn.setAttribute("disabled", "true");
        triggerBtn.innerHTML = `<span style="display:inline-flex; align-items:center; gap:6px;"><i data-lucide="loader" class="animate-spin" style="width:14px;height:14px;"></i> Uploading...</span>`;
        if (typeof lucide !== "undefined") lucide.createIcons();
      }
      if (assetsGrid) {
        const emptyState = document.getElementById("empty-assets-state");
        if (emptyState) emptyState.style.display = "none";
        if (!uploadIndicator) {
          uploadIndicator = document.createElement("div");
          uploadIndicator.id = "ve-upload-progress-indicator";
          uploadIndicator.style.cssText = "display:flex; align-items:center; gap:10px; padding:10px; border:1px dashed var(--ve-primary); border-radius:8px; background:var(--ve-bg-sub); margin-bottom:8px;";
          uploadIndicator.innerHTML = `
            <i data-lucide="loader" class="animate-spin" style="width:18px;height:18px;color:var(--ve-primary); flex-shrink:0;"></i>
            <div style="flex:1; min-width:0;">
              <p id="asset-upload-filename-text" style="margin:0; font-size:12px; font-weight:600; text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">${firstFileName}${filesCount > 1 ? ` (+${filesCount - 1} more)` : ""}</p>
              <p id="asset-upload-status-text" style="margin:0; font-size:10px; color:var(--ve-text-muted);">Uploading...</p>
            </div>
          `;
          assetsGrid.insertBefore(uploadIndicator, assetsGrid.firstChild);
          if (typeof lucide !== "undefined") lucide.createIcons();
        }
      }
    }

    function updateStatus(text) {
      const el = document.getElementById("asset-upload-status-text");
      if (el) el.textContent = text;
    }

    function hideIndicator() {
      if (uploadIndicator) {
        uploadIndicator.remove();
        uploadIndicator = null;
      }
      const triggerBtn = document.getElementById("btn-trigger-upload-asset");
      if (triggerBtn) {
        triggerBtn.removeAttribute("disabled");
        triggerBtn.innerHTML = `<i data-lucide="upload" style="width:16px;height:16px;"></i> <span>Upload files</span>`;
        if (typeof lucide !== "undefined") lucide.createIcons();
      }
    }

    async function uploadSingleFile(file) {
      const clientDur = await extractDuration(file);
      const csrf = window.REEL_CSRF_TOKEN || document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";
      const uploadUrl = window.REEL_UPLOAD_ASSET_URL || (window.location.pathname.replace(/\/+$/, "") + "/upload-asset/");

      // Chunked parallel upload for files > 10MB
      if (file.size > 10 * 1024 * 1024 && window.REEL_CHUNKED_UPLOAD_URL && window.REEL_PROJECT_ID) {
        const chunkSize = 10 * 1024 * 1024;
        const totalChunks = Math.ceil(file.size / chunkSize);
        const uploadId = Date.now().toString() + Math.random().toString(36).substring(7);
        let lastResult = null;

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

          const resData = await res.json().catch(() => null);
          if (res.ok && resData && resData.asset) {
            lastResult = resData;
          } else if (!res.ok) {
            throw new Error((resData && resData.error) || `Chunk ${i + 1} upload failed (${res.status})`);
          }
          const percent = Math.round(((i + 1) / totalChunks) * 100);
          updateStatus(`Uploading ${file.name} ${percent}%...`);
        }
        return lastResult;
      }

      // Standard single POST for files <= 10MB
      const formData = new FormData();
      formData.append("file", file);
      formData.append("media_file", file);
      formData.append("video_file", file); // backward compatibility
      formData.append("clientDuration", clientDur);

      const response = await fetch(uploadUrl, {
        method: "POST",
        headers: { "X-CSRFToken": csrf },
        body: formData,
      });

      const data = await response.json().catch(() => null);
      if (!response.ok || !data || (!data.success && data.status !== "success")) {
        throw new Error((data && (data.error || data.message)) || `Server returned ${response.status}: ${response.statusText}`);
      }
      return data;
    }

    async function uploadFiles(files, options = {}) {
      if (!files || files.length === 0) return [];
      const fileList = Array.from(files);

      // Pre-validation across all files before initiating upload
      for (const f of fileList) {
        const err = validateFile(f);
        if (err) {
          alert(err);
          return [];
        }
      }

      activeUploadCount++;
      showIndicator(fileList.length, fileList[0].name);

      const successfulAssets = [];
      let lastType = "video";

      try {
        for (let idx = 0; idx < fileList.length; idx++) {
          const file = fileList[idx];
          updateStatus(`Uploading ${file.name} (${idx + 1}/${fileList.length})...`);
          const data = await uploadSingleFile(file);

          if (data && data.asset) {
            const asset = data.asset;
            successfulAssets.push(asset);
            lastType = asset.asset_type || detectCategory(file);

            // Append card to Media Library in sidebar
            if (typeof createAndAppendAssetCard === "function") {
              createAndAppendAssetCard(asset);
            }

            // Auto-insert to timeline if requested (e.g. from "Add audio" or "Add clip" buttons)
            if (options.autoInsert && typeof handleInsertAssetClientSide === "function") {
              const videoEl = document.getElementById("main-video");
              const targetTime = options.currentTime != null
                ? options.currentTime
                : (videoEl ? sourceToTimelineTime(videoEl.currentTime) : 0);
              handleInsertAssetClientSide(asset, targetTime, options.targetTrack || asset.asset_type);
            }
          }
        }

        if (successfulAssets.length > 0) {
          try {
            localStorage.setItem("ve_sidebar_active_tab", lastType);
          } catch (e) {}
          const catBtn = document.querySelector(`.ve-category-btn[data-category="${lastType}"]`);
          if (catBtn) {
            catBtn.click();
          } else if (typeof filterMediaByCategory === "function") {
            filterMediaByCategory(lastType);
          }
          const emptyState = document.getElementById("empty-assets-state");
          if (emptyState) emptyState.style.display = "none";
        }
      } catch (err) {
        console.error("Unified upload error:", err);
        alert("Upload error: " + (err.message || "Failed to upload file."));
      } finally {
        activeUploadCount--;
        if (activeUploadCount <= 0) {
          hideIndicator();
        }
      }

      return successfulAssets;
    }

    let currentPickerOptions = {};
    const hiddenInput = document.getElementById("asset-file-input");
    if (hiddenInput) {
      hiddenInput.addEventListener("change", (e) => {
        const files = e.target.files;
        if (files && files.length > 0) {
          uploadFiles(files, currentPickerOptions);
        }
        hiddenInput.value = "";
      });
    }

    function openPicker(options = {}) {
      currentPickerOptions = options;
      if (!hiddenInput) return;
      hiddenInput.value = "";
      if (options.accept) {
        hiddenInput.accept = options.accept;
      } else {
        hiddenInput.accept = "image/*,video/*,audio/*";
      }
      hiddenInput.click();
    }

    return {
      uploadFiles,
      openPicker,
      detectCategory,
      validateFile,
      extractDuration,
    };
  })();

  // Global backward-compatible wrapper
  function handleUploadFiles(files, options) {
    return UnifiedMediaUploader.uploadFiles(files, options);
  }

  window.UnifiedMediaUploader = UnifiedMediaUploader;
  window.handleUploadFiles = handleUploadFiles;

  // Sidebar Universal Upload Button trigger
  const triggerUploadBtn = document.getElementById("btn-trigger-upload-asset");
  if (triggerUploadBtn) {
    triggerUploadBtn.addEventListener("click", (e) => {
      e.preventDefault();
      UnifiedMediaUploader.openPicker();
    });
  }

  // Drag & drop file uploads onto media drawer
  const assetsContainer = document.getElementById("assets-grid-container");
  const drawerPanel = document.getElementById("ve-drawer-import") || document.querySelector(".ve-drawer");
  const dropTarget = drawerPanel || assetsContainer;
  if (dropTarget) {
    ["dragenter", "dragover"].forEach((evtName) => {
      dropTarget.addEventListener(evtName, (e) => {
        if (e.dataTransfer && e.dataTransfer.types && Array.from(e.dataTransfer.types).includes("Files")) {
          e.preventDefault();
          e.stopPropagation();
          e.dataTransfer.dropEffect = "copy";
          dropTarget.style.outline = "2px dashed var(--ve-primary, #7c3aed)";
          dropTarget.style.outlineOffset = "-4px";
        }
      });
    });
    ["dragleave", "drop"].forEach((evtName) => {
      dropTarget.addEventListener(evtName, (e) => {
        dropTarget.style.outline = "none";
      });
    });
    dropTarget.addEventListener("drop", (e) => {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        e.preventDefault();
        e.stopPropagation();
        UnifiedMediaUploader.uploadFiles(e.dataTransfer.files);
      }
    });
  }

  // ---- Canva-Style Media Library Sidebar Controller -------------------------
  const mediaGrid = document.getElementById("assets-grid-container");
  const categoryNav = document.getElementById("sidebar-category-nav");
  const emptyState = document.getElementById("empty-assets-state");
  const timelineContainer = document.getElementById("visual-trim-container");
  const btnUploadMore = document.getElementById("btn-upload-more-menu");
  const uploadDropdown = document.getElementById("upload-dropdown-menu");
  const assetFileInput = document.getElementById("asset-file-input");

  const handleInsertAssetClientSide = (card, currentTime, targetTrack = null) => {
    if (!card) {
      console.error("handleInsertAssetClientSide: card is null or undefined");
      return;
    }

    const isDom = !!(card.dataset);
    const assetId = isDom ? card.dataset.assetId : (card.assetId || card.id);
    const assetTitle = (isDom ? card.dataset.assetTitle : (card.assetTitle || card.title)) || "Clip";
    const assetDuration = parseFloat((isDom ? card.dataset.assetDuration : (card.assetDuration || card.duration)) || 0.0) || 5.0;
    const assetUrl = (isDom ? card.dataset.assetUrl : (card.assetUrl || card.url)) || "";
    let assetType = (isDom ? card.dataset.assetType : (card.assetType || card.type)) || "video";

    if (targetTrack === "audio" || assetType === "audio") {
      assetType = "audio";
    }

    currentTime = typeof currentTime === "number" && !isNaN(currentTime) ? currentTime : 0;

    // Validate required data
    if (!assetId || !assetUrl) {
      console.error("Invalid asset data:", { assetId, assetUrl, assetTitle });
      alert("Cannot insert asset: missing required data");
      return;
    }

    if (assetDuration <= 0) {
      console.warn("Asset has invalid duration, using default 5s:", assetDuration);
    }

    console.log(`Inserting ${assetType} asset "${assetTitle}" at ${currentTime.toFixed(2)}s (target track: ${targetTrack || "auto"})`);

    if (assetType === "audio") {
      editorState.background_audios = editorState.background_audios || [];
      const curDur = duration || 10.0;
      const startT = Math.max(0, Math.min(currentTime, curDur));
      const endT = Math.min(startT + assetDuration, curDur);
      
      // Auto-separate audio if we are adding a new track
      if (!editorState.audio_separated) {
        editorState.audio_separated = true;
        if (typeof updateSeparateAudioUI === "function") updateSeparateAudioUI();
        // Mark existing original audio as user_dragged so it stays where it is
        if (editorState.background_audios) {
          editorState.background_audios.forEach(a => {
            if (a.is_detached) a.user_dragged = true;
          });
        }
      }

      editorState.background_audios.push({
        name: assetTitle,
        filename: assetTitle,
        url: assetUrl,
        start: startT,
        end: endT > startT ? endT : startT + assetDuration,
        trimStart: 0,
        trimEnd: assetDuration,
        bg_volume: 1.0,
        video_volume: 1.0,
        user_dragged: true
      });
      renderAllTimelineTracks();
      autoSaveTimeline();
      if (window.updateLocalState) {
        window.updateLocalState("Audio", `Inserted audio ${assetTitle}`);
      }
      syncVideoElementToTimeline(startT, true);
      if (typeof updatePlayheadSmooth === "function") updatePlayheadSmooth();
      console.log("Audio track added successfully");
      return;
    }

    // Video or Image: insert into video_clips
    const clips = editorState.video_clips || [];
    
    // If no clips exist, create the first clip
    if (clips.length === 0) {
      console.log("No existing clips, creating first clip");
      editorState.video_clips = [{
        id: assetId,
        title: assetTitle,
        name: assetTitle,
        trimStart: 0,
        trimEnd: assetDuration,
        duration: assetDuration,
        url: assetUrl,
        start: 0,
        end: assetDuration,
        isImage: assetType === "image"
      }];
      
      recalculateVideoClipsTimeline();
      renderClipBlocks();
      renderAllTimelineTracks();
      updateRuler();
      renderTrim();
      generateThumbnails();
      autoSaveTimeline();
      
      if (window.updateLocalState) {
        window.updateLocalState("Video", `Inserted clip ${assetTitle}`);
      }
      console.log("First video clip created successfully");
      return;
    }

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

      // Check if drop point is within this clip (using inclusive end boundary)
      if (accum <= currentTime && currentTime <= (accum + clipDur)) {
        const offset = currentTime - accum;
        const originalTrimStart = parseFloat(clip.trimStart || 0.0);

        // Only split if offset is meaningful (not at the very start or end)
        if (offset > 0.05 && offset < clipDur - 0.05) {
          const part1 = JSON.parse(JSON.stringify(clip));
          part1.duration = offset;
          part1.trimEnd = originalTrimStart + offset;
          part1.end = accum + offset;

          const insertedClip = {
            id: assetId,
            title: assetTitle,
            name: assetTitle,
            trimStart: 0,
            trimEnd: assetDuration,
            duration: assetDuration,
            url: assetUrl,
            start: accum + offset,
            end: accum + offset + assetDuration,
            isImage: assetType === "image"
          };

          const part2 = JSON.parse(JSON.stringify(clip));
          part2.duration = clipDur - offset;
          part2.trimStart = originalTrimStart + offset;
          part2.start = accum + offset + assetDuration;
          part2.end = part2.start + part2.duration;

          newClips.push(part1);
          newClips.push(insertedClip);
          newClips.push(part2);
        } else {
          // Insert at start or end without splitting
          if (offset <= 0.05) {
            const insertedClip = {
              id: assetId,
              title: assetTitle,
              name: assetTitle,
              trimStart: 0,
              trimEnd: assetDuration,
              duration: assetDuration,
              url: assetUrl,
              start: accum,
              end: accum + assetDuration,
              isImage: assetType === "image"
            };
            newClips.push(insertedClip);
            newClips.push(clip);
          } else {
            newClips.push(clip);
            const insertedClip = {
              id: assetId,
              title: assetTitle,
              name: assetTitle,
              trimStart: 0,
              trimEnd: assetDuration,
              duration: assetDuration,
              url: assetUrl,
              start: accum + clipDur,
              end: accum + clipDur + assetDuration,
              isImage: assetType === "image"
            };
            newClips.push(insertedClip);
          }
        }
        inserted = true;
      } else {
        newClips.push(clip);
        accum += clipDur;
      }
    }

    if (!inserted) {
      // Append at the end
      newClips.push({
        id: assetId,
        title: assetTitle,
        name: assetTitle,
        trimStart: 0,
        trimEnd: assetDuration,
        duration: assetDuration,
        url: assetUrl,
        start: accum,
        end: accum + assetDuration,
        isImage: assetType === "image"
      });
    }

    editorState.video_clips = newClips;
    recalculateVideoClipsTimeline();
    
    // Crucially: In linked audio mode, we must ensure background_audios stays synced 
    // with the new video_clips structure after a split or insert.
    if (!editorState.audio_separated) {
      ensureOriginalAudioTrackClip();
    }
    
    renderClipBlocks();
    renderAllTimelineTracks();
    updateRuler();
    renderTrim();
    generateThumbnails();
    autoSaveTimeline();

    if (window.updateLocalState) {
      window.updateLocalState("Video", `Inserted clip ${assetTitle}`);
    }
    syncVideoElementToTimeline(currentTime, true);
    if (typeof updatePlayheadSmooth === "function") updatePlayheadSmooth();
    console.log("Video clip inserted successfully, total clips:", newClips.length);
  };

  // Category Filtering
  function filterMediaByCategory(category) {
    if (!mediaGrid) return;
    const items = mediaGrid.querySelectorAll(".ve-grid-item");
    let visibleCount = 0;

    items.forEach((item) => {
      const type = item.dataset.assetType || "video";
      let match = false;
      if (category === "image" && type === "image") match = true;
      else if (category === "video" && type === "video") match = true;
      else if (category === "audio" && type === "audio") match = true;

      if (match) {
        item.style.display = "flex";
        visibleCount++;
      } else {
        item.style.display = "none";
      }
    });

    if (emptyState) {
      if (visibleCount === 0) {
        emptyState.style.display = "block";
        const titleEl = emptyState.querySelector(".ve-empty-title");
        const descEl = emptyState.querySelector(".ve-empty-desc");
        if (category === "audio") {
          if (titleEl) titleEl.textContent = "No audio files uploaded yet";
          if (descEl) descEl.textContent = "Click 'Upload files' to add audio.";
        } else {
          const catMap = { image: "images", video: "videos" };
          const label = catMap[category] || "files";
          if (titleEl) titleEl.textContent = `No ${label} yet`;
          if (descEl) descEl.textContent = `Click "Upload files" to add ${label}.`;
        }
      } else {
        emptyState.style.display = "none";
      }
    }

    try {
      localStorage.setItem("ve_sidebar_active_tab", category);
    } catch (e) {}

    if (assetFileInput) {
      assetFileInput.accept = "image/*,video/*,audio/*";
    }
  }

  if (categoryNav) {
    const categoryBtns = categoryNav.querySelectorAll(".ve-category-btn");
    categoryBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        categoryBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        filterMediaByCategory(btn.dataset.category || "video");
      });
    });

    let savedCat = localStorage.getItem("ve_sidebar_active_tab") || "video";
    if (savedCat === "folder" || !["video", "audio", "image"].includes(savedCat)) {
      savedCat = "video";
      try {
        localStorage.setItem("ve_sidebar_active_tab", "video");
      } catch (e) {}
    }
    const targetBtn = Array.from(categoryBtns).find((b) => b.dataset.category === savedCat) ||
                      Array.from(categoryBtns).find((b) => b.dataset.category === "video") ||
                      categoryBtns[0];
    if (targetBtn) {
      categoryBtns.forEach((b) => b.classList.remove("active"));
      targetBtn.classList.add("active");
      filterMediaByCategory(targetBtn.dataset.category || "video");
    }
  }

  // Upload More Options Dropdown
  if (btnUploadMore && uploadDropdown) {
    btnUploadMore.addEventListener("click", (e) => {
      e.stopPropagation();
      const isVisible = uploadDropdown.style.display === "flex";
      uploadDropdown.style.display = isVisible ? "none" : "flex";
    });

    uploadDropdown.querySelectorAll(".ve-dropdown-item[data-upload-type]").forEach((item) => {
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        uploadDropdown.style.display = "none";
        const type = item.dataset.uploadType;
        const navBtn = document.querySelector(`.ve-category-btn[data-category="${type}"]`);
        if (navBtn) navBtn.click();
        if (assetFileInput) {
          assetFileInput.accept = `${type}/*`;
          assetFileInput.click();
        }
      });
    });

    const btnCreateFolder = document.getElementById("btn-create-folder");
    if (btnCreateFolder) {
      btnCreateFolder.addEventListener("click", (e) => {
        e.stopPropagation();
        uploadDropdown.style.display = "none";
        const folderName = prompt("Enter new folder name:", "New Folder");
        if (folderName && folderName.trim()) {
          const navBtn = document.querySelector(`.ve-category-btn[data-category="folder"]`);
          if (navBtn) navBtn.click();
          if (mediaGrid) {
            const folderCard = document.createElement("div");
            folderCard.className = "ve-grid-item ve-folder-item";
            folderCard.dataset.assetType = "folder";
            folderCard.style.display = "flex";
            folderCard.innerHTML = `
              <div class="ve-grid-thumb ve-folder-thumb">
                <i data-lucide="folder" style="width:34px;height:34px;color:var(--ve-primary);"></i>
              </div>
              <div class="ve-grid-footer">
                <span class="ve-grid-title">${folderName.trim()}</span>
              </div>
            `;
            mediaGrid.insertBefore(folderCard, mediaGrid.firstChild);
            if (typeof lucide !== "undefined") lucide.createIcons();
            if (emptyState) emptyState.style.display = "none";
          }
        }
      });
    }

    document.addEventListener("click", (e) => {
      if (!uploadDropdown.contains(e.target) && e.target !== btnUploadMore) {
        uploadDropdown.style.display = "none";
      }
      document.querySelectorAll(".ve-grid-context-menu").forEach((m) => {
        if (!m.contains(e.target) && !e.target.closest(".ve-grid-menu-btn")) {
          m.style.display = "none";
        }
      });
    });
  }

  // Setup Cards (Click to Insert, Drag-and-Drop, Context Menu, Rename, Delete)
  const setupMediaCard = (card) => {
    const quickAddBtn = card.querySelector(".ve-card-quick-add");
    if (quickAddBtn) {
      quickAddBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const videoEl = document.getElementById("main-video");
        const currentTime = videoEl ? sourceToTimelineTime(videoEl.currentTime) : 0.0;
        handleInsertAssetClientSide(card, currentTime);
      });
    }

    card.addEventListener("click", (e) => {
      if (e.target.closest(".ve-grid-menu-btn") || e.target.closest(".ve-grid-context-menu") || e.target.closest(".ve-card-quick-add")) {
        return;
      }
      const videoEl = document.getElementById("main-video");
      const currentTime = videoEl ? sourceToTimelineTime(videoEl.currentTime) : 0.0;
      handleInsertAssetClientSide(card, currentTime);
    });

    card.addEventListener("dragstart", (e) => {
      const payload = {
        assetId: card.dataset.assetId,
        assetType: card.dataset.assetType || "video",
        assetTitle: card.dataset.assetTitle || "Clip",
        assetDuration: parseFloat(card.dataset.assetDuration || 0.0) || 5.0,
        assetUrl: card.dataset.assetUrl || ""
      };
      try {
        e.dataTransfer.setData("application/json", JSON.stringify(payload));
      } catch (err) {}
      e.dataTransfer.setData("text/plain", card.dataset.assetId);
      e.dataTransfer.effectAllowed = "copy";
      if (timelineContainer) timelineContainer.classList.add("drag-hover-active");
    });

    card.addEventListener("dragend", () => {
      if (timelineContainer) {
        timelineContainer.classList.remove("drag-hover-active");
        timelineContainer.style.borderColor = "";
        timelineContainer.style.background = "";
      }
      hideSnapGuide();
      document.querySelectorAll(".timeline-track-row").forEach((r) => r.classList.remove("drag-track-hover"));
    });

    const menuBtn = card.querySelector(".ve-grid-menu-btn");
    const contextMenu = card.querySelector(".ve-grid-context-menu");

    if (menuBtn && contextMenu) {
      menuBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = contextMenu.style.display === "flex";
        document.querySelectorAll(".ve-grid-context-menu").forEach((m) => (m.style.display = "none"));
        contextMenu.style.display = isOpen ? "none" : "flex";
      });

      const actionInsert = contextMenu.querySelector(".action-insert");
      if (actionInsert) {
        actionInsert.addEventListener("click", (e) => {
          e.stopPropagation();
          contextMenu.style.display = "none";
          const videoEl = document.getElementById("main-video");
          const currentTime = videoEl ? sourceToTimelineTime(videoEl.currentTime) : 0.0;
          handleInsertAssetClientSide(card, currentTime);
        });
      }

      const actionRename = contextMenu.querySelector(".action-rename");
      if (actionRename) {
        actionRename.addEventListener("click", async (e) => {
          e.stopPropagation();
          contextMenu.style.display = "none";
          const currentTitle = card.dataset.assetTitle || "";
          const newTitle = prompt("Enter new name for asset:", currentTitle);
          if (!newTitle || !newTitle.trim() || newTitle.trim() === currentTitle) return;

          const renameUrl = card.dataset.renameUrl;
          if (!renameUrl) return;

          try {
            const csrf = window.REEL_CSRF_TOKEN || document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
            const res = await fetch(renameUrl, {
              method: "POST",
              headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
              body: JSON.stringify({ title: newTitle.trim() })
            });
            if (res.ok) {
              const data = await res.json();
              card.dataset.assetTitle = data.title;
              const titleEl = card.querySelector(".ve-grid-title");
              if (titleEl) {
                titleEl.textContent = data.title;
                titleEl.title = data.title;
              }
            }
          } catch (err) {
            console.error("Error renaming asset:", err);
          }
        });
      }

      const actionDelete = contextMenu.querySelector(".action-delete");
      if (actionDelete) {
        actionDelete.addEventListener("click", async (e) => {
          e.stopPropagation();
          contextMenu.style.display = "none";
          const currentTitle = card.dataset.assetTitle || "this file";
          if (!confirm(`Are you sure you want to delete "${currentTitle}"?`)) return;

          const deleteUrl = card.dataset.deleteUrl;
          if (!deleteUrl) return;

          try {
            const csrf = window.REEL_CSRF_TOKEN || document.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
            const res = await fetch(deleteUrl, {
              method: "POST",
              headers: { "X-CSRFToken": csrf }
            });
            if (res.ok) {
              card.style.transition = "all 0.25s ease";
              card.style.opacity = "0";
              card.style.transform = "scale(0.85)";
              setTimeout(() => {
                card.remove();
                const activeBtn = document.querySelector(".ve-category-btn.active");
                if (activeBtn) filterMediaByCategory(activeBtn.dataset.category || "image");
              }, 250);
            }
          } catch (err) {
            console.error("Error deleting asset:", err);
          }
        });
      }
    }
  };

  createAndAppendAssetCard = (asset) => {
    const assetsGrid = document.getElementById("assets-grid-container");
    if (!assetsGrid || !asset) return null;

    const card = document.createElement("div");
    card.className = "ve-grid-item asset-card";
    card.draggable = true;
    card.dataset.assetId = String(asset.id);
    card.dataset.assetType = asset.asset_type || "video";
    card.dataset.assetTitle = asset.title || "Clip";
    card.dataset.assetDuration = asset.duration_seconds || (asset.asset_type === "image" ? 5.0 : 0.0);
    card.dataset.assetUrl = asset.url;
    if (asset.delete_url) card.dataset.deleteUrl = asset.delete_url;
    if (asset.rename_url) card.dataset.renameUrl = asset.rename_url;

    let thumbHtml = "";
    if (asset.asset_type === "image") {
      thumbHtml = `<img src="${asset.url}" alt="${asset.title}" loading="lazy">`;
    } else if (asset.asset_type === "audio") {
      thumbHtml = `<div class="ve-grid-audio-icon"><i data-lucide="music" style="width:24px;height:24px;"></i></div>`;
    } else {
      thumbHtml = `<video src="${asset.url}" preload="metadata" muted playsinline></video>`;
    }

    card.innerHTML = `
      <div class="ve-grid-thumb">
        ${thumbHtml}
        <button type="button" class="ve-card-quick-add" title="Add to timeline">
          <i data-lucide="plus" style="width:14px;height:14px;"></i>
        </button>
        <span class="ve-grid-duration-badge">${asset.duration || "0:00"}</span>
      </div>
      <div class="ve-grid-footer">
        <span class="ve-grid-title" title="${asset.title}">${asset.title}</span>
      </div>
      <button type="button" class="ve-grid-menu-btn" title="Options">
        <i data-lucide="more-horizontal" style="width:14px;height:14px;"></i>
      </button>
      <div class="ve-grid-context-menu" style="display:none;">
        <button type="button" class="ve-context-action action-insert">
          <i data-lucide="plus" style="width:13px;height:13px;"></i> Add to Timeline
        </button>
        <button type="button" class="ve-context-action action-rename">
          <i data-lucide="edit-2" style="width:13px;height:13px;"></i> Rename
        </button>
        <a href="${asset.url}" download class="ve-context-action action-download">
          <i data-lucide="download" style="width:13px;height:13px;"></i> Download
        </a>
        <button type="button" class="ve-context-action action-delete" style="color:#ef4444;">
          <i data-lucide="trash-2" style="width:13px;height:13px;"></i> Delete
        </button>
      </div>
    `;

    const emptyState = document.getElementById("empty-assets-state");
    if (emptyState) {
      assetsGrid.insertBefore(card, emptyState);
    } else {
      assetsGrid.appendChild(card);
    }

    setupMediaCard(card);
    if (typeof lucide !== "undefined") lucide.createIcons();
    return card;
  };

  const gridCards = document.querySelectorAll(".ve-grid-item.asset-card");
  gridCards.forEach(setupMediaCard);

