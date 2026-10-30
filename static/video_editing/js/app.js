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
  let duration = 0;
  let selectedClipIndex = -1;
  let activePlayingClipIndex = 0;
  let timelineCurrentTime = 0;
  let baseVideoOriginalSrc = "";
  let isTransitioningClip = false;

  function syncVideoElementToTimeline(tTimeline, forceSeek = false) {
    const video = document.getElementById("main-video");
    if (!video) return;
    if (!baseVideoOriginalSrc) {
      baseVideoOriginalSrc = video.currentSrc || video.src || "";
    }
    const clips = editorState.video_clips || [];
    if (clips.length === 0) {
      if (forceSeek || Math.abs(video.currentTime - tTimeline) > 0.15) {
        try { video.currentTime = tTimeline; } catch (e) {}
      }
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
        };
        video.addEventListener("seeked", onSeeked, { once: true });
        setTimeout(() => { isTransitioningClip = false; }, 250);
      }
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
    if (editorState.background_audios && editorState.background_audios.length > 0) {
      tracks.push({
        type: 'audio',
        name: 'Audio Track',
        clips: editorState.background_audios.map(audio => ({
          ...audio,
          start: audio.start != null ? audio.start : 0,
          end: audio.end != null ? audio.end : (audio.duration || 0),
          trimStart: audio.trimStart != null ? audio.trimStart : 0,
          trimEnd: audio.trimEnd != null ? audio.trimEnd : (audio.duration || 0)
        }))
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
    
    // Effects track (when effects are applied)
    const hasEffects = editorState.effects && (
      editorState.effects.grayscale || 
      editorState.effects.rotate || 
      editorState.effects.fade
    );
    if (hasEffects || (editorState.active_effects && editorState.active_effects.length > 0)) {
      tracks.push({
        type: 'effect',
        name: 'Effects Track',
        clips: editorState.active_effects || []
      });
    }

    return {
      tracks: tracks,
      clips: editorState.video_clips,
      video_clips: editorState.video_clips,
      background_audios: editorState.background_audios,
      text_overlays: editorState.text_overlays,
      trim: editorState.trim,
      speed: editorState.speed,
      audio: {
        volume: editorState.volume,
        muted: Boolean(editorState.userMuted),
      },
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
            triggerUploadBtn.innerHTML = `<i data-lucide="upload" style="width:16px;height:16px;"></i> <span>Upload files</span>`;
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
          triggerUploadBtn.innerHTML = `<i data-lucide="upload" style="width:16px;height:16px;"></i> <span>Upload files</span>`;
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

  // ---- Canva-Style Media Library Sidebar Controller -------------------------
  const mediaGrid = document.getElementById("assets-grid-container");
  const categoryNav = document.getElementById("sidebar-category-nav");
  const emptyState = document.getElementById("empty-assets-state");
  const timelineContainer = document.getElementById("visual-trim-container");
  const btnUploadMore = document.getElementById("btn-upload-more-menu");
  const uploadDropdown = document.getElementById("upload-dropdown-menu");

  const handleInsertAssetClientSide = (card, currentTime) => {
    if (!card) {
      console.error("handleInsertAssetClientSide: card is null or undefined");
      return;
    }

    const assetId = card.dataset.assetId;
    const assetTitle = card.dataset.assetTitle || "Clip";
    const assetDuration = parseFloat(card.dataset.assetDuration || 0.0) || 5.0;
    const assetUrl = card.dataset.assetUrl || "";
    const assetType = card.dataset.assetType || "video";

    // Validate required data
    if (!assetId || !assetUrl) {
      console.error("Invalid asset data:", { assetId, assetUrl, assetTitle });
      alert("Cannot insert asset: missing required data");
      return;
    }

    if (assetDuration <= 0) {
      console.warn("Asset has invalid duration, using default 5s:", assetDuration);
    }

    console.log(`Inserting ${assetType} asset "${assetTitle}" at ${currentTime.toFixed(2)}s`);

    if (assetType === "audio") {
      editorState.background_audios = editorState.background_audios || [];
      const curDur = duration || 10.0;
      const startT = Math.min(currentTime, curDur);
      const endT = Math.min(startT + assetDuration, curDur);
      editorState.background_audios.push({
        name: assetTitle,
        filename: assetTitle,
        url: assetUrl,
        start: startT,
        end: endT > startT ? endT : startT + assetDuration,
        trimStart: 0,
        trimEnd: assetDuration,
        bg_volume: 1.0,
        video_volume: 1.0
      });
      renderAllTimelineTracks();
      autoSaveTimeline();
      if (window.updateLocalState) {
        window.updateLocalState("Audio", `Inserted audio ${assetTitle}`);
      }
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

      if (accum <= currentTime && currentTime < (accum + clipDur)) {
        const offset = currentTime - accum;
        const originalTrimStart = parseFloat(clip.trimStart || 0.0);

        // Only split if offset is meaningful (not at the very start or end)
        if (offset > 0.1 && offset < clipDur - 0.1) {
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
          if (offset <= 0.1) {
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
          }
          newClips.push(clip);
          if (offset >= clipDur - 0.1) {
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
    renderClipBlocks();
    renderAllTimelineTracks();
    updateRuler();
    renderTrim();
    generateThumbnails();
    autoSaveTimeline();

    if (window.updateLocalState) {
      window.updateLocalState("Video", `Inserted clip ${assetTitle}`);
    }
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
      else if (category === "folder" && type === "folder") match = true;

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
        const catMap = { image: "images", video: "videos", audio: "audio tracks", folder: "folders" };
        const label = catMap[category] || "files";
        if (titleEl) titleEl.textContent = `No ${label} yet`;
        if (descEl) descEl.textContent = `Click "Upload files" to add ${label}.`;
      } else {
        emptyState.style.display = "none";
      }
    }

    try {
      localStorage.setItem("ve_sidebar_active_tab", category);
    } catch (e) {}

    if (assetFileInput) {
      if (category === "image") assetFileInput.accept = "image/*";
      else if (category === "video") assetFileInput.accept = "video/*";
      else if (category === "audio") assetFileInput.accept = "audio/*";
      else assetFileInput.accept = "image/*,video/*,audio/*";
    }
  }

  if (categoryNav) {
    const categoryBtns = categoryNav.querySelectorAll(".ve-category-btn");
    categoryBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        categoryBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        filterMediaByCategory(btn.dataset.category || "image");
      });
    });

    const savedCat = localStorage.getItem("ve_sidebar_active_tab") || "video";
    const targetBtn = Array.from(categoryBtns).find((b) => b.dataset.category === savedCat) || categoryBtns[1] || categoryBtns[0];
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
    card.addEventListener("click", (e) => {
      if (e.target.closest(".ve-grid-menu-btn") || e.target.closest(".ve-grid-context-menu")) {
        return;
      }
      const videoEl = document.getElementById("main-video");
      const currentTime = videoEl ? sourceToTimelineTime(videoEl.currentTime) : 0.0;
      handleInsertAssetClientSide(card, currentTime);
    });

    card.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", card.dataset.assetId);
      e.dataTransfer.effectAllowed = "copy";
      if (timelineContainer) timelineContainer.classList.add("drag-hover-active");
    });

    card.addEventListener("dragend", () => {
      if (timelineContainer) timelineContainer.classList.remove("drag-hover-active");
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

  const gridCards = document.querySelectorAll(".ve-grid-item.asset-card");
  gridCards.forEach(setupMediaCard);

  if (timelineContainer) {
    timelineContainer.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    });

    timelineContainer.addEventListener("dragenter", (e) => {
      e.preventDefault();
      timelineContainer.style.borderColor = "var(--ve-primary)";
      timelineContainer.style.background = "rgba(139, 92, 246, 0.04)";
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
      if (!assetId) {
        console.warn("No asset ID in drag data");
        return;
      }

      const card = Array.from(document.querySelectorAll(".ve-grid-item.asset-card")).find(
        (c) => c.dataset.assetId === assetId
      );
      
      if (!card) {
        console.warn(`Asset card with ID ${assetId} not found`);
        return;
      }

      // Get drop position relative to timeline to insert at specific time
      const rect = timelineContainer.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const pxPerSecond = basePxPerSecond * zoomFactor;
      const dropTime = Math.max(0, Math.min(duration || 0, clickX / pxPerSecond));

      console.log(`Dropping asset at ${dropTime.toFixed(2)}s`);
      handleInsertAssetClientSide(card, dropTime);
    });
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
        const deg = parseInt(form.querySelector("#id_degrees").value) || 0;
        editorState.rotate = deg;
        applyCSSEffects();
        renderAllTimelineTracks();
        autoSaveTimeline();
        if (window.updateLocalState)
          window.updateLocalState("Rotate", `Rotated ${deg} degrees`);
      } else if (action.includes("/resize/")) {
        const w = form.querySelector("#id_width").value;
        const h = form.querySelector("#id_height").value;
        editorState.resize = { width: w, height: h };
        applyCSSEffects();
        renderAllTimelineTracks();
        autoSaveTimeline();
        if (window.updateLocalState)
          window.updateLocalState("Resize", `Resized to ${w}x${h}`);
      } else if (action.includes("/grayscale/")) {
        editorState.grayscale = !editorState.grayscale;
        applyCSSEffects();
        renderAllTimelineTracks();
        autoSaveTimeline();
        if (window.updateLocalState)
          window.updateLocalState("Grayscale", editorState.grayscale ? `Applied Grayscale` : `Removed Grayscale`);
      } else if (action.includes("/fade/")) {
        const fin = parseFloat(form.querySelector("#id_fade_in_seconds").value) || 0;
        const fout = parseFloat(form.querySelector("#id_fade_out_seconds").value) || 0;
        editorState.fade = { in: fin, out: fout };
        applyCSSEffects();
        renderAllTimelineTracks();
        autoSaveTimeline();
        if (window.updateLocalState)
          window.updateLocalState(
            "Fade",
            `Fade in: ${fin}s, Fade out: ${fout}s`,
          );
      } else if (action.includes("/speed/")) {
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
        video.muted = newMuted;
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

  // ---- Visual Trim & Custom Player Controls Implementation -----------
  const video = document.getElementById("main-video");
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

    function snapTimeToPoints(time, thresholdPx = 10) {
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
    }

    function hideSnapGuide() {
      const snapGuide = document.getElementById("timeline-snap-guide");
      if (snapGuide) snapGuide.style.display = "none";
    }

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
        if (editorState.background_audios.length === 0) {
          editorState.background_audios.push({
            name: "Audio Track (A1)",
            filename: "Audio Track (A1)",
            start: 0,
            end: curDur,
            trimStart: 0,
            trimEnd: curDur,
            bg_volume: 1.0,
            video_volume: 1.0,
            is_detached: true
          });
        }
      }
    }

    function recalculateVideoClipsTimeline() {
      let acc = 0.0;
      (editorState.video_clips || []).forEach(clip => {
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
      if (acc > 0) {
        duration = acc;
        window.duration = acc;
      } else if (window.REEL_PROJECT_DURATION && parseFloat(window.REEL_PROJECT_DURATION) > 0) {
        duration = parseFloat(window.REEL_PROJECT_DURATION);
        window.duration = duration;
      }
      startSeconds = 0;
      endSeconds = duration || acc || 0;
      ensureOriginalAudioTrackClip();
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
        if (speedDropdown && Array.from(speedDropdown.options).some((o) => o.value === spdStr)) {
          speedDropdown.value = spdStr;
        }
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
        const videoEl = document.getElementById("main-video") || document.getElementById("video-preview");
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
        const fontSizeVal = overlay.font_size || overlay.fontsize || 48;
        const displayFontSize = Math.max(
          10,
          Math.round(fontSizeVal * scale),
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

    function clearGlobalSelection() {
      globalSelection = { track: null, index: -1 };
      selectedClipIndex = -1;
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
      ensureOriginalAudioTrackClip();
      if (window.dynamicTrackManager) {
        window.dynamicTrackManager.updateTrackVisibilities();
      }
      if (!duration) return;
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

        if (items.length === 0) {
          const placeholderBtn = document.createElement("button");
          placeholderBtn.type = "button";
          placeholderBtn.className = "timeline-empty-track-placeholder";
          const label = trackType === "audio" ? "Add audio" : (trackType === "text" ? "Add text overlay" : "Add effect");
          placeholderBtn.innerHTML = `<i data-lucide="${config.icon}" style="width:13px;height:13px;margin-right:6px;"></i> <span>+ ${label}</span>`;
          placeholderBtn.addEventListener("click", () => {
            const tabName = trackType === "effect" ? "effects" : trackType;
            const tab = document.querySelector(`.tool-tab[data-tab="${tabName}"], .ve-tool-tab[data-tab="${tabName}"]`);
            if (tab) tab.click();
            if (trackType === "text") {
              const inp = document.getElementById("id_text");
              if (inp) inp.focus();
            }
          });
          container.appendChild(placeholderBtn);
          return;
        }

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

          const el = document.createElement("div");
          el.className = `timeline-generic-block${trackType === 'audio' ? ' timeline-audio-block' : ''}${trackType === 'text' ? ' timeline-text-block' : ''}`;
          el.style.position = "absolute";
          el.style.left = `${leftPx}px`;
          el.style.width = `${widthPx}px`;
          el.style.height =
            trackType === "effect" ? "calc(100% - 16px)" : "100%";
          el.style.top = trackType === "effect" ? "8px" : "0";
          el.style.background = trackType === "audio" ? "transparent" : config.color;
          el.style.border = trackType === "audio" ? "1px solid rgba(16, 185, 129, 0.35)" : `1.5px solid ${config.borderColor}`;
          el.style.borderRadius = "6px";
          el.style.display = "flex";
          el.style.alignItems = "center";
          el.style.padding = trackType === "audio" ? "0" : "0 8px";
          el.style.boxSizing = "border-box";
          el.style.color = "white";
          el.style.fontSize = "13px";
          el.style.fontWeight = "bold";
          el.style.overflow = "hidden";
          el.style.zIndex = "3";
          el.style.backdropFilter = trackType === "audio" ? "none" : "blur(4px)";
          el.style.boxShadow = trackType === "audio" ? "none" : "";
          // Unified cursor styles for all track types
          el.style.cursor = "grab";

          if (
            globalSelection.track === trackType &&
            globalSelection.index === index
          ) {
            el.style.outline = "2px solid #8b5cf6";
            el.style.outlineOffset = "0px";
            el.style.boxShadow = "0 0 0 2px rgba(139,92,246,0.4), 0 4px 14px rgba(139,92,246,0.3)";
            if (trackType === "audio") {
              el.style.background = "rgba(139, 92, 246, 0.05)";
            }
          }

          if (trackType === "audio") {
            el.innerHTML = "";
            // Canva style: No text label on audio clips, only pure clean soundwave
          } else {
            let name = item.name || item.text || "Item";
            el.innerHTML = `<i data-lucide="${config.icon}" style="width:14px;height:14px;margin-right:6px;flex-shrink:0;position:relative;z-index:2;"></i> <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;position:relative;z-index:2;text-shadow:0 1px 3px rgba(0,0,0,0.7);">${name}</span>`;
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
            const srcDur = duration || 1;
            const startR = itemTrimStart / srcDur;
            const endR = itemTrimEnd / srcDur;
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
            handle.style.width = "10px";
            handle.style.background = trackType === "audio" ? "rgba(34, 197, 94, 0.75)" : "rgba(255, 255, 255, 0.4)";
            handle.style.borderRadius = side === "left" ? "6px 0 0 6px" : "0 6px 6px 0";
            handle.style.cursor = "ew-resize";
            handle.style.zIndex = "6";
            handle.style.transition = "background 0.15s, width 0.15s";
            
            // Hover effect
            handle.addEventListener("mouseenter", () => {
              handle.style.width = "14px";
              handle.style.background = trackType === "audio" ? "rgba(34, 197, 94, 1)" : "rgba(255, 255, 255, 0.7)";
            });
            handle.addEventListener("mouseleave", () => {
              handle.style.width = "10px";
              handle.style.background = trackType === "audio" ? "rgba(34, 197, 94, 0.75)" : "rgba(255, 255, 255, 0.4)";
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
            dragOffsetSeconds = getSecondsFromX(clientX) - (item.start || 0);
            el.style.cursor = "grabbing";
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
              el.style.cursor = "grab";
              window.removeEventListener("mousemove", move);
              window.removeEventListener("mouseup", stop);
              window.removeEventListener("touchmove", move);
              window.removeEventListener("touchend", stop);
              autoSaveTimeline();
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

      [videoTrackRow, audioTrackRow, textTrackRow, effectTrackRow].forEach((row) => {
        if (row) {
          row.style.setProperty("display", "flex", "important");
        }
      });

      if (window.dynamicTrackManager) {
        window.dynamicTrackManager.updateTrackVisibilities();
      } else {
        const trackBadge = document.getElementById("tb-bottom-track-info");
        if (trackBadge) {
          trackBadge.innerHTML = `<i data-lucide="layers" style="width:13px;height:13px;color:var(--ve-primary);"></i> 4 Tracks`;
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

    function updateRuler() {
      renderRulerTicks();
    }
    // ── End Canva-Style Ruler ────────────────────────────────────
    let _filmstripThumbs = null;
    let _filmstripLoading = false;
    let _clientThumbnailGenerating = false;

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

    let _clipThumbAbortController = null;
    const THUMB_DESIRED_W = 60; // px per visible slot
    let _lastClipRenderKey = "";

    async function renderClipBlocks() {
      const container = document.getElementById("timeline-clip-blocks") || (typeof clipBlocksContainer !== "undefined" ? clipBlocksContainer : null);
      if (!container) return;
      if ((!duration || isNaN(duration)) && window.REEL_PROJECT_DURATION) {
        duration = parseFloat(window.REEL_PROJECT_DURATION);
        window.duration = duration;
      }
      if (!duration || isNaN(duration)) return;

      const clipsData = editorState.video_clips || [];
      const pxPerSecond = basePxPerSecond * zoomFactor;
      const parentWidth = trimTrack?.parentElement ? trimTrack.parentElement.clientWidth : 800;
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

      const domNeedsRebuild = stateKey !== _lastClipRenderKey;

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
      const existingAddBtn = container.querySelector(".timeline-inline-add-clip-btn");
      if (existingAddBtn) existingAddBtn.remove();

      const addClipBtn = document.createElement("button");
      addClipBtn.type = "button";
      addClipBtn.className = "timeline-inline-add-clip-btn";
      addClipBtn.style.cssText = `position:absolute; left:${accumTime * pxPerSecond + 6}px; top:4px; height:calc(100% - 8px); display:inline-flex; align-items:center; gap:6px; padding:0 12px; background:rgba(255,255,255,0.06); border:1px dashed rgba(255,255,255,0.25); border-radius:6px; color:#c4b5fd; font-size:12px; font-weight:600; cursor:pointer; z-index:5; white-space:nowrap; transition:all 0.15s ease;`;
      addClipBtn.innerHTML = `<i data-lucide="plus" style="width:14px;height:14px;"></i> <span>Add Clip</span>`;
      addClipBtn.addEventListener("mouseenter", () => {
        addClipBtn.style.background = "rgba(139, 92, 246, 0.2)";
        addClipBtn.style.borderColor = "rgba(139, 92, 246, 0.6)";
      });
      addClipBtn.addEventListener("mouseleave", () => {
        addClipBtn.style.background = "rgba(255,255,255,0.06)";
        addClipBtn.style.borderColor = "rgba(255,255,255,0.25)";
      });
      addClipBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const videoCatBtn = document.querySelector('.ve-category-btn[data-category="video"]');
        if (videoCatBtn) videoCatBtn.click();
        const uploadTrigger = document.getElementById("trigger-upload-btn");
        if (uploadTrigger) uploadTrigger.click();
      });
      container.appendChild(addClipBtn);

      if (typeof lucide !== "undefined") lucide.createIcons();
      _lastClipRenderKey = stateKey;
    }

    
    // ── Canva-Grade 60fps Playhead Animation Engine ──
    let _playheadRafId = null;
    function updatePlayheadSmooth() {
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
      const playheadPx = timelineTime * pxPerSecond;
      trimPlayhead.style.left = `${playheadPx}px`;

      const timeCurrentEl = document.getElementById("video-time-current");
      if (timeCurrentEl) timeCurrentEl.textContent = formatTime(timelineTime);

      const playheadTooltip = document.getElementById("playhead-tooltip");
      if (playheadTooltip) playheadTooltip.textContent = formatTime(timelineTime);

      if (currentDisplay) currentDisplay.textContent = formatTime(timelineTime);

      // Text overlays visibility during 60fps playhead
      if (editorState.text_overlays && editorState.text_overlays.length > 0) {
        const textContainer = document.getElementById("text-overlay-container");
        if (textContainer && textContainer.children) {
          const textElements = textContainer.children;
          editorState.text_overlays.forEach((overlay, i) => {
            if (textElements[i]) {
              const oStart = parseFloat(overlay.start || 0);
              const oEnd = parseFloat(overlay.end || duration);
              if (timelineTime >= oStart && timelineTime <= oEnd) {
                textElements[i].style.display = "";
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

    function renderTrim() {
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
      const hasClips = editorState.video_clips && editorState.video_clips.length > 0;

      if (deleteBtnEl) {
        if (globalSelection.track !== null || (hasClips && editorState.video_clips.length > 1)) {
          deleteBtnEl.removeAttribute("disabled");
        } else {
          deleteBtnEl.setAttribute("disabled", "true");
        }
      }
      if (duplicateBtnEl) {
        if (globalSelection.track !== null || hasClips) {
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
      if (trimPlayhead.classList.contains("dragging")) return;
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
      });
    }

    if (btnMute) {
      btnMute.addEventListener("click", () => {
        const newMuted = !(editorState.userMuted || editorState.muted);
        editorState.userMuted = newMuted;
        editorState.muted = newMuted;
        video.muted = newMuted;
        syncVolumeUI();
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
      if (Array.from(speedDropdown.options).some((o) => o.value === currentSpd)) {
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
        const p = video.play();
        if (p && typeof p.catch === "function") {
          p.catch((err) => console.warn("Playback prevented:", err));
        }
      } else {
        video.pause();
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
          {
            id: "effect-track-row",
            type: "effect",
            name: "Effects & Filters Track",
            order: 3,
            height: 32,
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
        // All tracks are kept visible in Canva multi-track timeline
        this.tracks.forEach((t) => {
          t.visible = true;
        });
        this.renderAllTracks();
      }

      renderAllTracks() {
        this.tracks.forEach((track) => {
          const trackEl = document.getElementById(track.id) || document.querySelector(`.${track.id}`);
          if (trackEl) {
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
            aItem.trimEnd = aOrigTrimStart + aRel;

            const newAItem = JSON.parse(JSON.stringify(aItem));
            newAItem.start = curT;
            newAItem.end = aOrigEnd;
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
        editorState.video_clips?.splice(globalSelection.index, 1);
        
        if (deletedClip && editorState.background_audios && editorState.background_audios.length > 0) {
          const aIdx = editorState.background_audios.findIndex(
            (a) => a.is_detached && Math.abs((a.start || 0) - (deletedClip.start || 0)) < 0.2
          );
          if (aIdx !== -1) {
            editorState.background_audios.splice(aIdx, 1);
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
        autoSaveTimeline();

        if (window.updateLocalState)
          window.updateLocalState("audio", "Deleted audio clip");
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
        const videoCatBtn = document.querySelector('.ve-category-btn[data-category="video"]');
        if (videoCatBtn) videoCatBtn.click();
        const uploadTrigger = document.getElementById("trigger-upload-btn");
        if (uploadTrigger) uploadTrigger.click();
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

    // Initialization
    extractAudioPeaks();
    loadFilmstripThumbs();
    if (window.REEL_PROJECT_DURATION && parseFloat(window.REEL_PROJECT_DURATION) > 0) {
      initTrim();
    }

    if (video.readyState >= 1) {
      initTrim();
      extractAudioPeaks();
      loadFilmstripThumbs();
    } else {
      video.addEventListener("loadedmetadata", () => {
        initTrim();
        extractAudioPeaks();
        loadFilmstripThumbs();
      });
      video.addEventListener("canplay", () => {
        initTrim();
      });
    }
    video.addEventListener("timeupdate", onTimeUpdate);

    function onTimeUpdate() {
      if (!duration) return;
      const t = video.currentTime;
      const timelineTime = sourceToTimelineTime(t);

      // Multi-clip boundary transition check during timeupdate
      const clips = editorState.video_clips || [];
      if (!video.paused && clips.length > 1 && !isTransitioningClip) {
        const activeClip = clips[activePlayingClipIndex] || clips[0];
        const clipTrimEnd = parseFloat(activeClip.trimEnd !== undefined ? activeClip.trimEnd : ((activeClip.trimStart || 0) + (activeClip.duration || 0)));
        if (t >= clipTrimEnd - 0.05) {
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
            return;
          }
        }
      }

      // Loop or pause only at timeline boundary
      const safeDuration = duration || window.duration || 0;
      if (!video.paused && safeDuration > 0 && timelineTime >= safeDuration - 0.05) {
        video.pause();
        video.currentTime = timelineToSourceTime(0);
        return;
      }

      // If a specific video clip is selected for trimming, only loop if user explicitly selected it
      if (!video.paused && globalSelection.track === "video" && selectedClipIndex !== -1 && endSeconds > startSeconds + 0.1) {
        if (timelineTime >= endSeconds - 0.05) {
          video.currentTime = timelineToSourceTime(startSeconds);
          return;
        }
      }

      // Text overlays visibility
      const textContainer = document.getElementById("text-overlay-container");
      if (textContainer) {
        const textElements = textContainer.children;
        editorState.text_overlays.forEach((overlay, i) => {
          if (textElements[i]) {
            if (timelineTime >= overlay.start && timelineTime <= overlay.end) {
              textElements[i].style.display = "block";
            } else {
              textElements[i].style.display = "none";
            }
          }
        });
      }

      // Background / Detached Audio Track sync
      if (editorState.background_audios) {
        if (editorState.userMuted || editorState.muted) {
          if (!video.muted) video.muted = true;
        } else {
          // Check if there is an active detached audio clip at current timelineTime
          let activeDetachedClip = null;
          let anyDetachedClipsExist = false;

          editorState.background_audios.forEach((bg) => {
            const isDetached = bg.is_detached || (!bg.url && !bg.path);
            if (isDetached) {
              anyDetachedClipsExist = true;
              const bgStart = parseFloat(bg.start !== undefined ? bg.start : 0);
              const bgEnd = parseFloat(bg.end !== undefined ? bg.end : (bgStart + parseFloat(bg.duration || 0)));
              if (timelineTime >= bgStart && timelineTime <= bgEnd) {
                activeDetachedClip = bg;
              }
            }
          });

          // Always resolve mute state fresh every tick:
          // If playhead is over an active audio segment -> unmute video and restore volume!
          // If playhead is in a cut gap between segments -> mute video so cut audio doesn't play!
          if (anyDetachedClipsExist) {
            const shouldMute = !activeDetachedClip;
            if (video.muted !== shouldMute) {
              video.muted = shouldMute;
            }
            if (activeDetachedClip) {
              const clipVol = activeDetachedClip.volume !== undefined ? activeDetachedClip.volume : (editorState.volume !== undefined ? editorState.volume : 1.0);
              if (Number.isFinite(clipVol) && Math.abs(video.volume - clipVol) > 0.01) {
                video.volume = Math.max(0, Math.min(1.0, clipVol));
              }
            }
          } else {
            // No detached audio segments at all — adhere strictly to user mute
            const userMute = Boolean(editorState.userMuted || editorState.muted);
            if (video.muted !== userMute) {
              video.muted = userMute;
            }
          }

          // External music clips sync (e.g. background music MP3s)
          editorState.background_audios.forEach((bg, i) => {
            if (bg.is_detached || (!bg.url && !bg.path)) {
              return;
            }
            let audioEl = document.getElementById(`preview-bg-audio-${i}`);
            const targetSrc = bg.url;
            if (!targetSrc) return;

            if (!audioEl) {
              audioEl = document.createElement("audio");
              audioEl.id = `preview-bg-audio-${i}`;
              audioEl.src = targetSrc;
              document.body.appendChild(audioEl);
            } else if (audioEl.src !== targetSrc && targetSrc) {
              audioEl.src = targetSrc;
            }

            audioEl.volume = bg.bg_volume ?? 1.0;
            const bgStart = parseFloat(bg.start || 0);
            const bgEnd = parseFloat(bg.end || duration);
            const bgTrimStart = parseFloat(bg.trimStart || 0.0);

            if (timelineTime >= bgStart && timelineTime <= bgEnd) {
              const expectedTime = (timelineTime - bgStart) + bgTrimStart;
              if (audioEl.paused && !video.paused) {
                audioEl.currentTime = expectedTime;
                audioEl.play().catch((e) => console.log("Audio play blocked", e));
              } else {
                if (Math.abs(audioEl.currentTime - expectedTime) > 0.3) {
                  audioEl.currentTime = expectedTime;
                }
              }
            } else {
              if (!audioEl.paused) audioEl.pause();
            }

            if (video.paused && !audioEl.paused) {
              audioEl.pause();
            }
          });
        }

        // Clean up surplus audio preview elements if audio clips were deleted
        let surplusIdx = editorState.background_audios.length;
        while (document.getElementById(`preview-bg-audio-${surplusIdx}`)) {
          const surplusEl = document.getElementById(`preview-bg-audio-${surplusIdx}`);
          surplusEl.pause();
          surplusEl.removeAttribute("src");
          if (typeof surplusEl.load === "function") surplusEl.load();
          surplusEl.remove();
          surplusIdx++;
        }
      }
    }

    video.addEventListener("play", () => onTimeUpdate());
    video.addEventListener("pause", () => onTimeUpdate());
    if (video.readyState >= 1) {
      initTrim();
    }

    let currentThumbnailAbortController = null;

    function initTrim() {
      const vidDur = (video && !isNaN(video.duration) && video.duration > 0) ? video.duration : null;
      const projDur = (typeof window.duration !== "undefined" && !isNaN(window.duration) && window.duration > 0)
        ? window.duration
        : (window.REEL_PROJECT_DURATION ? parseFloat(window.REEL_PROJECT_DURATION) : null);

      duration = vidDur || projDur || 0;
      window.duration = duration;
      if (!duration || isNaN(duration)) return;

      // Update video time display
      const timeTotalEl = document.getElementById("video-time-total");
      if (timeTotalEl) {
        timeTotalEl.textContent = formatTime(duration);
      }
      const timeCurrentEl = document.getElementById("video-time-current");
      if (timeCurrentEl) {
        timeCurrentEl.textContent = formatTime(video.currentTime || 0);
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
    async function generateThumbnails() {
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
  }
})();
