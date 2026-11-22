/**
 * static/js/video_editing/app.js
 * Master Video Editor Orchestrator & Lifecycle Coordinator
 * Cohesively binds the modular Video Editor subsystems.
 */

(function () {
  "use strict";

  console.log("EduMi Video Editor — Modular Workbench Loaded v3.2");

  function bootWorkbench() {
    try {
      if (typeof window.recalculateVideoClipsTimeline === "function") {
        window.recalculateVideoClipsTimeline();
      }
      if (typeof window.updateRuler === "function") {
        window.updateRuler();
      }
      if (typeof window.renderClipBlocks === "function") {
        window.renderClipBlocks();
      }
      if (typeof window.renderAllTimelineTracks === "function") {
        window.renderAllTimelineTracks();
      }
      if (typeof window.renderTrim === "function") {
        window.renderTrim();
      }
      if (typeof window.renderTextOverlays === "function") {
        window.renderTextOverlays();
      }
      if (typeof window.updatePlayheadSmooth === "function") {
        window.updatePlayheadSmooth();
      }
      if (typeof lucide !== "undefined") {
        lucide.createIcons();
      }
    } catch (err) {
      console.warn("Video Editor boot sequence note:", err);
    }
  }

  window.VideoEditor = {
    version: "3.2",
    get state() { return typeof window.editorState !== "undefined" ? window.editorState : null; },
    get duration() { return typeof window.duration !== "undefined" ? window.duration : 0; },
    get currentTime() { return typeof window.timelineCurrentTime !== "undefined" ? window.timelineCurrentTime : 0; },
    boot: bootWorkbench,
    save: function () {
      if (typeof window.autoSaveTimeline === "function") {
        return window.autoSaveTimeline();
      }
    }
  };

  // Ensure DOM components initialize smoothly
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootWorkbench);
  } else {
    // If DOM is already parsed (or Turbo reloaded), boot immediately
    setTimeout(bootWorkbench, 50);
  }
  document.addEventListener("turbo:load", bootWorkbench);
})();
