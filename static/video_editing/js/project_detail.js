/**
 * static/video_editing/js/project_detail.js
 * Controller for Video Editing project workbench:
 * - Bootstraps project settings & timeline state into REEL globals
 * - HLS & Preview proxy playback management
 * - Editable auto-saving project name
 * - History drawer slide-out interactions
 * - Audio waveform generation & rendering
 * - Volume controls synchronization
 */

(function () {
    "use strict";

    function getBootstrapConfig() {
        var el = document.getElementById("reel-project-data");
        if (!el) return null;
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            console.error("Failed to parse project bootstrap JSON:", e);
            return null;
        }
    }

    // 1. Initialize Global State for app.js compatibility
    function initReelGlobals(cfg) {
        if (!cfg) return;
        window.REEL_PROJECT_ID = cfg.projectId || "";
        window.REEL_CHUNKED_UPLOAD_URL = cfg.chunkedUploadUrl || "";
        window.REEL_STATUS_URL = cfg.statusUrl || "";
        window.REEL_PROJECT_FILMSTRIP_URL = cfg.filmstripUrl || "";
        window.REEL_PROJECT_WAVEFORM_URL = cfg.waveformUrl || "";
        window.REEL_PROJECT_SAVE_TIMELINE_URL = cfg.saveTimelineUrl || "";
        window.REEL_PROJECT_STATUS = cfg.status || "ready";
        window.REEL_UPLOAD_ASSET_URL = cfg.uploadAssetUrl || "";
        window.REEL_CSRF_TOKEN = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";
        window.REEL_PROJECT_HAS_AUDIO = String(cfg.hasAudio);
        window.REEL_PROJECT_TRIM_START = Number(cfg.trimStart || 0);
        window.REEL_PROJECT_TRIM_END = cfg.trimEnd;
        window.REEL_PROJECT_HEIGHT = Number(cfg.height || 720);
        window.REEL_PROJECT_TIMELINE_STATE = cfg.timelineState;
        window.REEL_PROJECT_CLIPS = cfg.clips || [];
        window.REEL_PROJECT_DURATION = Number(cfg.duration || 0);
        window.REEL_PROJECT_PROXY_STATUS = cfg.proxyStatus || "none";
        window.REEL_PROJECT_PROXY_URL = cfg.proxyUrl || "";
        window.REEL_PROJECT_OPERATIONS = cfg.operations || [];
    }

    // 2. SVG Waveform Generator
    window.generateWaveformSvg = function (width, height, seed, clipStartRatio, clipEndRatio) {
        var centerY = height / 2;
        var peaks = window.audioPeaksCache;
        if (!peaks || peaks.length === 0) {
            return '<svg width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '" xmlns="http://www.w3.org/2000/svg" style="display:block;width:100%;height:100%;"><line x1="0" y1="' + centerY + '" x2="' + width + '" y2="' + centerY + '" stroke="rgba(255,255,255,0.15)" stroke-width="1"/></svg>';
        }
        var barWidth = 2.0;
        var barGap = 1.0;
        var totalBars = Math.max(10, Math.floor(width / (barWidth + barGap)));
        var maxBarHeight = height - 6;
        var paths = [];
        var len = peaks.length;
        var startR = clipStartRatio != null ? clipStartRatio : 0.0;
        var endR = clipEndRatio != null ? clipEndRatio : 1.0;
        for (var i = 0; i < totalBars; i++) {
            var x = i * (barWidth + barGap);
            var ratio = startR + (i / totalBars) * (endR - startR);
            var idx = Math.min(len - 1, Math.max(0, Math.floor(ratio * len)));
            var amp = Math.max(0.04, peaks[idx] || 0.04);
            var barH = Math.max(2, amp * maxBarHeight);
            var topY = centerY - (barH / 2);
            paths.push('<rect x="' + x.toFixed(1) + '" y="' + topY.toFixed(1) + '" width="' + barWidth + '" height="' + barH.toFixed(1) + '" rx="1" fill="#34d399" opacity="0.9"/>');
        }
        return '<svg width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '" xmlns="http://www.w3.org/2000/svg" style="display:block;width:100%;height:100%;"><line x1="0" y1="' + centerY + '" x2="' + width + '" y2="' + centerY + '" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>' + paths.join('') + '</svg>';
    };

    // 3. Proxy Video Source Handler (with HLS Support)
    function initProxySource(cfg) {
        var video = document.getElementById("main-video");
        var prepOverlay = document.getElementById("preview-preparing-overlay");
        var proxyUrl = cfg ? cfg.proxyUrl : "";
        var proxyStatus = cfg ? cfg.proxyStatus : "none";
        var proxyStatusUrl = cfg ? cfg.proxyStatusUrl : "";

        function applyProxySource(url) {
            if (!video || !url) return;
            if (url.endsWith(".m3u8")) {
                if (typeof Hls !== "undefined" && Hls.isSupported()) {
                    var hls = new Hls();
                    hls.loadSource(url);
                    hls.attachMedia(video);
                } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
                    video.src = url;
                }
            } else {
                if (!video.src || !video.src.includes(url)) {
                    video.src = url;
                    video.load();
                }
            }
            if (prepOverlay) prepOverlay.style.display = "none";
        }

        if (video) {
            video.addEventListener("loadeddata", function () {
                if (prepOverlay) prepOverlay.style.display = "none";
            });
            video.addEventListener("canplay", function () {
                if (prepOverlay) prepOverlay.style.display = "none";
            });
            setTimeout(function () {
                if (video.readyState >= 1 && prepOverlay) {
                    prepOverlay.style.display = "none";
                }
            }, 1500);
        }

        if (proxyStatus === "completed" && proxyUrl) {
            applyProxySource(proxyUrl);
        } else if (proxyStatusUrl) {
            var proxyPollInterval = setInterval(async function () {
                try {
                    var resp = await fetch(proxyStatusUrl);
                    if (resp.ok) {
                        var pdata = await resp.json();
                        if (pdata.status === "completed" && pdata.url) {
                            clearInterval(proxyPollInterval);
                            applyProxySource(pdata.url);
                        }
                    }
                } catch (e) {}
            }, 1500);
        }
    }

    // 4. Editable Project Name with Auto-Save
    function initProjectRename() {
        var nameInput = document.getElementById("project-name-input");
        var nameEditBtn = document.getElementById("project-name-edit-btn");
        var savingEl = document.getElementById("save-status-saving");
        var savedEl = document.getElementById("save-status-saved");
        var savedTimeout = null;

        if (!nameInput || nameInput._init) return;
        nameInput._init = true;

        var autoSizeInput = function () {
            var valLen = (nameInput.value || nameInput.placeholder || "").length;
            nameInput.style.width = Math.min(420, Math.max(130, (valLen + 2) * 9.5)) + "px";
        };
        autoSizeInput();
        nameInput.addEventListener("input", autoSizeInput);

        if (nameEditBtn) {
            nameEditBtn.addEventListener("click", function (e) {
                e.preventDefault();
                nameInput.focus();
                nameInput.select();
            });
        }

        nameInput.addEventListener("focus", function () {
            nameInput.select();
        });

        nameInput.addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                nameInput.blur();
            } else if (e.key === "Escape") {
                e.preventDefault();
                nameInput.value = nameInput.dataset.originalVal || "Untitled Project";
                autoSizeInput();
                nameInput.blur();
            }
        });

        nameInput.addEventListener("blur", function () {
            var currentVal = nameInput.value.trim();
            if (!currentVal) {
                currentVal = "Untitled Project";
                nameInput.value = currentVal;
                autoSizeInput();
            }

            var originalVal = nameInput.dataset.originalVal || "";
            if (currentVal === originalVal) return;

            var renameUrl = nameInput.dataset.renameUrl;
            if (!renameUrl) return;

            if (savingEl) savingEl.style.display = "inline-flex";
            if (savedEl) savedEl.style.display = "none";
            if (savedTimeout) clearTimeout(savedTimeout);
            if (typeof lucide !== "undefined") lucide.createIcons();

            var csrfToken = window.REEL_CSRF_TOKEN ||
                document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";

            fetch(renameUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken
                },
                body: JSON.stringify({ title: currentVal })
            })
            .then(function (res) {
                if (!res.ok) throw new Error("Rename failed");
                return res.json();
            })
            .then(function (data) {
                var savedTitle = data.title || currentVal;
                nameInput.dataset.originalVal = savedTitle;
                document.title = savedTitle + " — Video Editor";
                nameInput.title = "Click to rename project (" + savedTitle + ")";
                if (savingEl) savingEl.style.display = "none";
                if (savedEl) {
                    savedEl.style.display = "inline-flex";
                    if (typeof lucide !== "undefined") lucide.createIcons();
                    savedTimeout = setTimeout(function () {
                        savedEl.style.display = "none";
                    }, 2500);
                }
            })
            .catch(function (err) {
                console.error("Error saving project name:", err);
                if (savingEl) savingEl.style.display = "none";
                nameInput.value = originalVal;
                autoSizeInput();
            });
        });
    }

    // 5. History Drawer
    function initHistoryDrawer() {
        var showHistoryBtn = document.getElementById("btn-show-history");
        var historyDrawer = document.getElementById("history-drawer");
        var historyDrawerClose = document.getElementById("history-drawer-close");
        var historyDrawerBackdrop = document.getElementById("history-drawer-backdrop");

        if (showHistoryBtn && historyDrawer && !showHistoryBtn._init) {
            showHistoryBtn._init = true;
            showHistoryBtn.addEventListener("click", function (e) {
                e.preventDefault();
                historyDrawer.classList.add("open");
            });
        }
        if (historyDrawerClose && historyDrawer && !historyDrawerClose._init) {
            historyDrawerClose._init = true;
            historyDrawerClose.addEventListener("click", function (e) {
                e.preventDefault();
                historyDrawer.classList.remove("open");
            });
        }
        if (historyDrawerBackdrop && historyDrawer && !historyDrawerBackdrop._init) {
            historyDrawerBackdrop._init = true;
            historyDrawerBackdrop.addEventListener("click", function (e) {
                e.preventDefault();
                historyDrawer.classList.remove("open");
            });
        }

        // Close on Escape key
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && historyDrawer && historyDrawer.classList.contains("open")) {
                historyDrawer.classList.remove("open");
            }
        });
    }

    // 6. Audio Waveform Display Poller
    function tryAddOriginalWaveform() {
        var timelineBlock = document.getElementById("visual-trim-container");
        if (timelineBlock && typeof window.duration !== "undefined" && window.duration > 0) {
            var basePxPerSecond = 15;
            var zoomFactor = typeof window.zoomFactor !== "undefined" ? window.zoomFactor : 1.0;
            var audioBlock = document.getElementById("audio-block");
            var totalWidth = (audioBlock && audioBlock.clientWidth > 50)
                ? audioBlock.clientWidth
                : Math.max(800, window.duration * basePxPerSecond * zoomFactor);
            var waveformContainer = document.getElementById("original-audio-waveform");
            if (waveformContainer && typeof window.generateWaveformSvg === "function") {
                waveformContainer.innerHTML = window.generateWaveformSvg(totalWidth, 36, 0);
            }
        } else {
            setTimeout(tryAddOriginalWaveform, 100);
        }
    }
    window.tryAddOriginalWaveform = tryAddOriginalWaveform;

    // 7. Volume Sliders Sync
    function initVolumeSliders() {
        var timelineVideoVol = document.getElementById("timeline-video-volume");
        var timelineVideoVolVal = document.getElementById("timeline-video-volume-val");
        var formVideoVol = document.getElementById("id_video_volume");

        if (timelineVideoVol && formVideoVol && !timelineVideoVol._init) {
            timelineVideoVol._init = true;
            timelineVideoVol.value = formVideoVol.value;
            if (timelineVideoVolVal) timelineVideoVolVal.textContent = parseFloat(formVideoVol.value).toFixed(1);

            timelineVideoVol.addEventListener("input", function (e) {
                var val = e.target.value;
                formVideoVol.value = val;
                if (timelineVideoVolVal) timelineVideoVolVal.textContent = parseFloat(val).toFixed(1);
                var mainVid = document.getElementById("main-video");
                if (mainVid) {
                    mainVid.volume = Math.min(1.0, parseFloat(val));
                    if (parseFloat(val) > 0) mainVid.muted = false;
                }
            });

            formVideoVol.addEventListener("input", function (e) {
                var val = e.target.value;
                timelineVideoVol.value = val;
                if (timelineVideoVolVal) timelineVideoVolVal.textContent = parseFloat(val).toFixed(1);
                var mainVid = document.getElementById("main-video");
                if (mainVid) {
                    mainVid.volume = Math.min(1.0, parseFloat(val));
                    if (parseFloat(val) > 0) mainVid.muted = false;
                }
            });
        }

        var timelineBgVol = document.getElementById("timeline-bg-volume");
        var timelineBgVolVal = document.getElementById("timeline-bg-volume-val");
        var formBgVol = document.getElementById("id_bg_volume");

        if (timelineBgVol && formBgVol && !timelineBgVol._init) {
            timelineBgVol._init = true;
            timelineBgVol.value = formBgVol.value;
            if (timelineBgVolVal) timelineBgVolVal.textContent = parseFloat(formBgVol.value).toFixed(1);

            timelineBgVol.addEventListener("input", function (e) {
                formBgVol.value = e.target.value;
                if (timelineBgVolVal) timelineBgVolVal.textContent = parseFloat(e.target.value).toFixed(1);
            });

            formBgVol.addEventListener("input", function (e) {
                timelineBgVol.value = e.target.value;
                if (timelineBgVolVal) timelineBgVolVal.textContent = parseFloat(e.target.value).toFixed(1);
            });
        }

        // Topbar Undo button forwarding
        var undoBtn = document.getElementById("tb-undo");
        if (undoBtn && !undoBtn._init) {
            undoBtn._init = true;
            undoBtn.addEventListener("click", function () {
                var firstHistoryUndo = document.querySelector(".history-list li:first-child .history-revert-btn");
                if (firstHistoryUndo) {
                    firstHistoryUndo.click();
                }
            });
        }
    }

    // 8. Main Initialization Controller
    function initProjectDetail() {
        var cfg = getBootstrapConfig();
        initReelGlobals(cfg);
        initProxySource(cfg);
        initProjectRename();
        initHistoryDrawer();
        initVolumeSliders();
        tryAddOriginalWaveform();

        if (typeof lucide !== "undefined") {
            lucide.createIcons();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initProjectDetail);
    } else {
        initProjectDetail();
    }
    document.addEventListener("turbo:load", initProjectDetail);
})();

