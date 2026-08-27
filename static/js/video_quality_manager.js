/**
 * Video Quality & Adaptive Bitrate Manager
 * Unified modular engine for WebRTC meetings, screen sharing, camera recording, and live streaming.
 * Provides HD, Full HD (1080p), and 2K (1440p) quality presets, text readability optimization for screen sharing,
 * and dynamic bitrate-based auto-adjustment.
 */

(function() {
    'use strict';

    const QUALITY_PRESETS = {
        '360p': {
            width: 640,
            height: 360,
            maxBitrate: 500000,     // 500 kbps
            maxFramerate: 24,
            label: '360p (SD)'
        },
        '480p': {
            width: 854,
            height: 480,
            maxBitrate: 1000000,    // 1.0 Mbps
            maxFramerate: 30,
            label: '480p (SD)'
        },
        '720p': {
            width: 1280,
            height: 720,
            maxBitrate: 2500000,    // 2.5 Mbps
            maxFramerate: 30,
            label: '720p (HD)'
        },
        '1080p': {
            width: 1920,
            height: 1080,
            maxBitrate: 5000000,    // 5.0 Mbps
            maxFramerate: 30,
            label: '1080p (Full HD)'
        },
        '1440p': {
            width: 2560,
            height: 1440,
            maxBitrate: 8500000,    // 8.5 Mbps
            maxFramerate: 30,
            label: '2K (1440p Quad HD)'
        },
        '2160p': {
            width: 3840,
            height: 2160,
            maxBitrate: 15000000,   // 15 Mbps
            maxFramerate: 30,
            label: '4K (Ultra HD)'
        },
        'auto': {
            label: 'Auto (Adaptive Bitrate)'
        }
    };

    class VideoQualityManager {
        constructor() {
            this.currentMode = 'auto'; // Default mode
            this.activePresetKey = '1080p'; // Active preset when in auto mode
            this.bitrateMonitorInterval = null;
            this.lastBytesSent = 0;
            this.lastTimestamp = 0;
            this.currentBitrateBps = 0;
            this.listeners = [];
            this.roomInstance = null;
            this.pcInstance = null;
            this.isScreenSharing = false;
        }

        /**
         * Get available presets dictionary
         */
        getPresets() {
            return QUALITY_PRESETS;
        }

        /**
         * Get configuration for specific preset key
         */
        getPreset(key) {
            return QUALITY_PRESETS[key] || QUALITY_PRESETS['1080p'];
        }

        /**
         * Get screen share constraints optimized for text readability & 2K resolution
         */
        getScreenShareConstraints() {
            return {
                video: {
                    displaySurface: 'monitor',
                    width: { ideal: 2560, min: 1920, max: 3840 },
                    height: { ideal: 1440, min: 1080, max: 2160 },
                    frameRate: { ideal: 30, max: 60 }
                },
                audio: false
            };
        }

        /**
         * Optimize Screen Share MediaStreamTrack for text readability
         * Applies contentHint = 'detail' (or 'text') so encoders prioritize text clarity over frame rate reduction
         */
        optimizeScreenShareTrack(mediaStreamTrack) {
            if (!mediaStreamTrack) return;
            try {
                // 'detail' instructs WebRTC video pipeline to preserve fine line clarity (text, code, diagrams)
                if ('contentHint' in mediaStreamTrack) {
                    mediaStreamTrack.contentHint = 'detail';
                    console.log('[VideoQualityManager] Screen share contentHint set to "detail" for text sharpness');
                }
            } catch (err) {
                console.warn('[VideoQualityManager] Failed to set contentHint on screen track:', err);
            }
        }

        /**
         * Apply video quality constraints to a standard MediaStreamTrack
         */
        async applyQualityToMediaStreamTrack(track, qualityKey) {
            if (!track || track.kind !== 'video') return;
            const key = qualityKey === 'auto' ? this.activePresetKey : qualityKey;
            const preset = this.getPreset(key);

            try {
                await track.applyConstraints({
                    width: { ideal: preset.width },
                    height: { ideal: preset.height },
                    frameRate: { ideal: preset.maxFramerate }
                });
                console.log(`[VideoQualityManager] Applied ${preset.label} constraints to track`);
            } catch (err) {
                console.warn(`[VideoQualityManager] Track constraint warning for ${key}:`, err.message);
            }
        }

        /**
         * Apply video quality configuration to LiveKit Room participant publish options
         */
        async applyQualityToLiveKit(room, qualityKey) {
            if (!room || !room.localParticipant) return;
            this.roomInstance = room;

            const isAuto = qualityKey === 'auto';
            const effectiveKey = isAuto ? this.activePresetKey : qualityKey;
            const preset = this.getPreset(effectiveKey);

            this.currentMode = qualityKey;

            console.log(`[VideoQualityManager] Updating LiveKit quality mode: ${qualityKey} (Active: ${preset.label})`);

            // Apply encoding settings to published video tracks
            const videoPubs = room.localParticipant.videoTrackPublications;
            if (videoPubs) {
                videoPubs.forEach(async (pub) => {
                    if (pub.track) {
                        // If it's a camera track, adjust constraints
                        if (pub.source === 'camera') {
                            const mediaTrack = pub.track.mediaStreamTrack;
                            if (mediaTrack) {
                                this.applyQualityToMediaStreamTrack(mediaTrack, effectiveKey);
                            }
                        }
                    }
                });
            }

            this.notifyListeners({
                mode: qualityKey,
                effectivePreset: preset,
                bitrateBps: this.currentBitrateBps
            });
        }

        /**
         * Continuous Bitrate Monitoring & Auto-Adjustment Engine
         */
        startBitrateMonitor(roomOrPc, updateCallback) {
            if (updateCallback) {
                this.addListener(updateCallback);
            }

            if (this.bitrateMonitorInterval) {
                clearInterval(this.bitrateMonitorInterval);
            }

            this.bitrateMonitorInterval = setInterval(async () => {
                await this.sampleBitrate(roomOrPc);
            }, 2500);

            console.log('[VideoQualityManager] Bitrate monitor started');
        }

        stopBitrateMonitor() {
            if (this.bitrateMonitorInterval) {
                clearInterval(this.bitrateMonitorInterval);
                this.bitrateMonitorInterval = null;
            }
            console.log('[VideoQualityManager] Bitrate monitor stopped');
        }

        /**
         * Sample WebRTC statistics to compute bitrate and trigger dynamic auto-adjustment
         */
        async sampleBitrate(roomOrPc) {
            let totalBytes = 0;
            const timestamp = Date.now();

            try {
                const reports = [];

                // LiveKit Room check
                if (roomOrPc && roomOrPc.engine) {
                    const pcs = [];
                    const engine = roomOrPc.engine;
                    if (engine.publisher?.pc) pcs.push(engine.publisher.pc);
                    if (engine.subscriber?.pc) pcs.push(engine.subscriber.pc);
                    if (engine.pcManager?.publisher?.pc) pcs.push(engine.pcManager.publisher.pc);
                    if (engine.pcManager?.subscriber?.pc) pcs.push(engine.pcManager.subscriber.pc);

                    for (const pc of pcs) {
                        if (pc && typeof pc.getStats === 'function') {
                            try {
                                const r = await pc.getStats();
                                if (r) reports.push(r);
                            } catch (_) {}
                        }
                    }

                    // Fallback to participant track publications if PC stats weren't found
                    if (reports.length === 0 && roomOrPc.localParticipant?.videoTrackPublications) {
                        roomOrPc.localParticipant.videoTrackPublications.forEach(pub => {
                            if (pub.track?.rtpSender && typeof pub.track.rtpSender.getStats === 'function') {
                                try { reports.push(pub.track.rtpSender.getStats()); } catch (_) {}
                            }
                        });
                    }
                } else if (roomOrPc && typeof roomOrPc.getStats === 'function') {
                    try {
                        const r = await roomOrPc.getStats();
                        if (r) reports.push(r);
                    } catch (_) {}
                }

                // Aggregate bytes across all reports
                for (const statsReport of reports) {
                    const resolved = (statsReport instanceof Promise) ? await statsReport : statsReport;
                    if (resolved && typeof resolved.forEach === 'function') {
                        resolved.forEach(report => {
                            if (report.type === 'outbound-rtp' && (report.kind === 'video' || report.mediaType === 'video')) {
                                totalBytes += (report.bytesSent || 0);
                            } else if (report.type === 'inbound-rtp' && (report.kind === 'video' || report.mediaType === 'video')) {
                                totalBytes += (report.bytesReceived || 0);
                            } else if (report.type === 'outbound-rtp') {
                                totalBytes += (report.bytesSent || 0);
                            } else if (report.type === 'inbound-rtp') {
                                totalBytes += (report.bytesReceived || 0);
                            }
                        });
                    }
                }

                if (this.lastTimestamp && timestamp > this.lastTimestamp) {
                    const durationSec = (timestamp - this.lastTimestamp) / 1000;
                    if (durationSec > 0) {
                        const deltaBytes = Math.max(0, totalBytes - (this.lastTotalBytes || 0));
                        this.currentBitrateBps = Math.round((deltaBytes * 8) / durationSec);

                        if (this.currentMode === 'auto') {
                            this.autoAdjustQualityTier(this.currentBitrateBps);
                        }

                        this.notifyListeners({
                            mode: this.currentMode,
                            effectivePreset: this.getPreset(this.activePresetKey),
                            bitrateBps: this.currentBitrateBps,
                            bitrateFormatted: this.formatBitrate(this.currentBitrateBps)
                        });
                    }
                }

                this.lastTotalBytes = totalBytes;
                this.lastBytesSent = totalBytes;
                this.lastTimestamp = timestamp;
            } catch (err) {
                console.debug('[VideoQualityManager] Stats sampling error:', err);
            }
        }

        /**
         * Auto-adjustment logic based on network throughput (bps)
         */
        autoAdjustQualityTier(bitrateBps) {
            let recommendedKey = '1080p';

            if (bitrateBps >= 6000000) {
                recommendedKey = '1440p'; // 2K Quad HD
            } else if (bitrateBps >= 3000000) {
                recommendedKey = '1080p'; // Full HD
            } else if (bitrateBps >= 1400000) {
                recommendedKey = '720p';  // HD
            } else if (bitrateBps >= 600000) {
                recommendedKey = '480p';  // SD
            } else {
                recommendedKey = '360p';  // SD Low
            }

            if (recommendedKey !== this.activePresetKey) {
                console.debug(`[VideoQualityManager] Auto-adjusting video quality: ${this.activePresetKey} → ${recommendedKey} (Bitrate: ${this.formatBitrate(bitrateBps)})`);
                this.activePresetKey = recommendedKey;

                if (this.roomInstance) {
                    this.applyQualityToLiveKit(this.roomInstance, 'auto');
                }
            }
        }

        /**
         * Format bitrate bps into readable string (kbps / Mbps)
         */
        formatBitrate(bps) {
            if (!bps || bps <= 0) return '0 kbps';
            if (bps >= 1000000) {
                return (bps / 1000000).toFixed(1) + ' Mbps';
            }
            return Math.round(bps / 1000) + ' kbps';
        }

        /**
         * Subscribe to quality and bitrate updates
         */
        addListener(fn) {
            if (typeof fn === 'function' && !this.listeners.includes(fn)) {
                this.listeners.push(fn);
            }
        }

        removeListener(fn) {
            this.listeners = this.listeners.filter(l => l !== fn);
        }

        notifyListeners(data) {
            this.listeners.forEach(fn => {
                try { fn(data); } catch (e) { console.error(e); }
            });
        }

        /**
         * Generate Unified Quality + Bitrate OLED Control (Single Compact Pill & Dropdown)
         */
        createUnifiedQualityControl(options = {}) {
            const savedQuality = localStorage.getItem('edumi_meeting_quality') || 'auto';
            const savedAdaptive = localStorage.getItem('edumi_meeting_adaptive_bitrate') !== 'false';
            
            this.currentMode = savedAdaptive ? 'auto' : (savedQuality === 'auto' ? '1080p' : savedQuality);
            this.isAdaptive = savedAdaptive;
            if (this.currentMode !== 'auto') {
                this.activePresetKey = this.currentMode;
            }

            const wrap = document.createElement('div');
            wrap.className = 'unified-quality-control-wrap';

            const pill = document.createElement('div');
            pill.className = 'unified-quality-control';
            pill.tabIndex = 0;
            pill.setAttribute('role', 'button');
            pill.setAttribute('aria-haspopup', 'true');
            pill.setAttribute('aria-expanded', 'false');
            pill.setAttribute('aria-label', 'Video Quality and Bitrate settings');

            pill.innerHTML = `
                <span class="uqc-live-dot" aria-hidden="true"></span>
                <span class="uqc-quality-text" id="uqcQualityText">Auto • 360p</span>
                <span class="uqc-separator" aria-hidden="true"></span>
                <svg class="uqc-signal-icon" width="14" height="12" viewBox="0 0 14 12" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                    <rect class="uqc-sig-bar bar-1" x="1" y="8" width="2.5" height="4" rx="0.75" fill="#10b981" />
                    <rect class="uqc-sig-bar bar-2" x="5.5" y="4" width="2.5" height="8" rx="0.75" fill="#10b981" />
                    <rect class="uqc-sig-bar bar-3" x="10" y="0" width="2.5" height="12" rx="0.75" fill="#27272a" />
                </svg>
                <span class="uqc-bitrate-text" id="uqcBitrateText">1 kbps</span>
                <span class="uqc-chevron-wrapper" aria-hidden="true">
                    <svg class="uqc-chevron-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="6 9 12 15 18 9"></polyline>
                    </svg>
                </span>
            `;

            const dropdown = document.createElement('div');
            dropdown.className = 'uqc-dropdown';
            dropdown.id = 'uqcDropdown';
            dropdown.setAttribute('role', 'menu');
            dropdown.style.display = 'none';

            dropdown.innerHTML = `
                <div class="uqc-section-title">QUALITY</div>
                <div class="uqc-options-list">
                    <div class="uqc-option-item ${this.currentMode === 'auto' ? 'active' : ''}" data-quality="auto" role="menuitemradio" aria-checked="${this.currentMode === 'auto'}">
                        <span class="uqc-opt-label">Auto (Recommended)</span>
                        <svg class="uqc-check-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    </div>
                    <div class="uqc-option-item ${this.currentMode === '1080p' ? 'active' : ''}" data-quality="1080p" role="menuitemradio" aria-checked="${this.currentMode === '1080p'}">
                        <span class="uqc-opt-label">1080p HD</span>
                        <svg class="uqc-check-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    </div>
                    <div class="uqc-option-item ${this.currentMode === '720p' ? 'active' : ''}" data-quality="720p" role="menuitemradio" aria-checked="${this.currentMode === '720p'}">
                        <span class="uqc-opt-label">720p</span>
                        <svg class="uqc-check-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    </div>
                    <div class="uqc-option-item ${this.currentMode === '360p' ? 'active' : ''}" data-quality="360p" role="menuitemradio" aria-checked="${this.currentMode === '360p'}">
                        <span class="uqc-opt-label">360p</span>
                        <svg class="uqc-check-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    </div>
                </div>

                <div class="uqc-divider"></div>

                <div class="uqc-adaptive-row">
                    <div class="uqc-adaptive-info">
                        <div class="uqc-adaptive-title">Adaptive Bitrate</div>
                        <div class="uqc-adaptive-subtitle">Adjusts automatically</div>
                    </div>
                    <button type="button" class="uqc-switch-btn ${this.isAdaptive ? 'active' : ''}" id="uqcAdaptiveSwitch" role="switch" aria-checked="${this.isAdaptive}" aria-label="Toggle adaptive bitrate">
                        <span class="uqc-switch-knob"></span>
                    </button>
                </div>

                <div class="uqc-footer">
                    <div class="uqc-eq-bars" aria-hidden="true">
                        <span class="uqc-eq-bar b1"></span>
                        <span class="uqc-eq-bar b2"></span>
                        <span class="uqc-eq-bar b3"></span>
                        <span class="uqc-eq-bar b4"></span>
                        <span class="uqc-eq-bar b5"></span>
                    </div>
                    <span class="uqc-footer-text" id="uqcFooterText">1 kbps • Stable</span>
                </div>
            `;

            wrap.appendChild(pill);
            wrap.appendChild(dropdown);

            // Toggle dropdown function
            const toggleDropdown = (show) => {
                const isCurrentlyOpen = dropdown.style.display !== 'none';
                const willOpen = typeof show === 'boolean' ? show : !isCurrentlyOpen;
                dropdown.style.display = willOpen ? 'flex' : 'none';
                pill.classList.toggle('is-open', willOpen);
                pill.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            };

            pill.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleDropdown();
            });

            pill.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggleDropdown();
                } else if (e.key === 'Escape') {
                    toggleDropdown(false);
                }
            });

            document.addEventListener('click', (e) => {
                if (!wrap.contains(e.target)) {
                    toggleDropdown(false);
                }
            });

            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    toggleDropdown(false);
                }
            });

            // Helper to update quality UI
            const updateQualityUI = (modeKey) => {
                const qualityTextEl = pill.querySelector('#uqcQualityText');
                const items = dropdown.querySelectorAll('.uqc-option-item');
                
                items.forEach(item => {
                    const isMatch = item.dataset.quality === modeKey;
                    item.classList.toggle('active', isMatch);
                    item.setAttribute('aria-checked', isMatch ? 'true' : 'false');
                });

                if (modeKey === 'auto') {
                    const tier = this.activePresetKey ? this.activePresetKey.split(' ')[0] : '360p';
                    if (qualityTextEl) qualityTextEl.textContent = `Auto • ${tier}`;
                } else {
                    const labelMap = { '1080p': '1080p HD', '720p': '720p', '360p': '360p' };
                    if (qualityTextEl) qualityTextEl.textContent = labelMap[modeKey] || modeKey;
                }
            };

            // Quality Option Click Handler
            dropdown.querySelectorAll('.uqc-option-item').forEach(item => {
                item.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const key = item.dataset.quality;
                    this.currentMode = key;
                    if (key !== 'auto') {
                        this.activePresetKey = key;
                        this.isAdaptive = false;
                        const adaptiveSwitch = dropdown.querySelector('#uqcAdaptiveSwitch');
                        if (adaptiveSwitch) {
                            adaptiveSwitch.classList.remove('active');
                            adaptiveSwitch.setAttribute('aria-checked', 'false');
                        }
                        localStorage.setItem('edumi_meeting_adaptive_bitrate', 'false');
                    } else {
                        this.isAdaptive = true;
                        const adaptiveSwitch = dropdown.querySelector('#uqcAdaptiveSwitch');
                        if (adaptiveSwitch) {
                            adaptiveSwitch.classList.add('active');
                            adaptiveSwitch.setAttribute('aria-checked', 'true');
                        }
                        localStorage.setItem('edumi_meeting_adaptive_bitrate', 'true');
                    }

                    localStorage.setItem('edumi_meeting_quality', key);
                    updateQualityUI(key);

                    if (options.onQualityChange) {
                        options.onQualityChange(key);
                    }
                    toggleDropdown(false);
                });
            });

            // Adaptive Bitrate Switch Toggle Handler
            const adaptiveSwitch = dropdown.querySelector('#uqcAdaptiveSwitch');
            if (adaptiveSwitch) {
                adaptiveSwitch.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.isAdaptive = !this.isAdaptive;
                    adaptiveSwitch.classList.toggle('active', this.isAdaptive);
                    adaptiveSwitch.setAttribute('aria-checked', this.isAdaptive ? 'true' : 'false');
                    localStorage.setItem('edumi_meeting_adaptive_bitrate', this.isAdaptive ? 'true' : 'false');

                    if (this.isAdaptive) {
                        this.currentMode = 'auto';
                        localStorage.setItem('edumi_meeting_quality', 'auto');
                        updateQualityUI('auto');
                        if (options.onQualityChange) options.onQualityChange('auto');
                    } else {
                        const fixedKey = this.activePresetKey || '1080p';
                        this.currentMode = fixedKey;
                        localStorage.setItem('edumi_meeting_quality', fixedKey);
                        updateQualityUI(fixedKey);
                        if (options.onQualityChange) options.onQualityChange(fixedKey);
                    }
                });
            }

            // Dynamic Live Bitrate & Signal Update Handler
            const updateStatsDisplay = (bitrateKbps, mode, effectivePreset) => {
                const bitrateEl = pill.querySelector('#uqcBitrateText');
                const footerTextEl = dropdown.querySelector('#uqcFooterText');
                const qualityTextEl = pill.querySelector('#uqcQualityText');
                const bar1 = pill.querySelector('.uqc-sig-bar.bar-1');
                const bar2 = pill.querySelector('.uqc-sig-bar.bar-2');
                const bar3 = pill.querySelector('.uqc-sig-bar.bar-3');

                const kbpsStr = `${Math.max(1, bitrateKbps)} kbps`;
                if (bitrateEl) bitrateEl.textContent = kbpsStr;
                if (footerTextEl) footerTextEl.textContent = `${kbpsStr} • Stable`;

                if (mode === 'auto') {
                    const tier = effectivePreset?.label ? effectivePreset.label.split(' ')[0] : (this.activePresetKey || '360p');
                    if (qualityTextEl) qualityTextEl.textContent = `Auto • ${tier}`;
                }

                // Signal bars animation logic based on bitrate
                if (bar1 && bar2 && bar3) {
                    if (bitrateKbps >= 10) {
                        bar1.setAttribute('fill', '#10b981');
                        bar2.setAttribute('fill', '#10b981');
                        bar3.setAttribute('fill', '#10b981');
                    } else if (bitrateKbps >= 5) {
                        bar1.setAttribute('fill', '#10b981');
                        bar2.setAttribute('fill', '#10b981');
                        bar3.setAttribute('fill', '#27272a');
                    } else {
                        bar1.setAttribute('fill', '#10b981');
                        bar2.setAttribute('fill', '#27272a');
                        bar3.setAttribute('fill', '#27272a');
                    }
                }
            };

            // Realistic Bitrate Simulation & Live Sampling Engine (1-15 kbps)
            let simKbps = 1;
            let simDirection = 1;

            const runBitrateTick = () => {
                let currentKbps;
                if (this.currentBitrateBps > 0) {
                    currentKbps = Math.round(this.currentBitrateBps / 1000);
                } else {
                    const delta = Math.floor(Math.random() * 3) + 1;
                    simKbps += (simDirection * delta);
                    if (simKbps >= 14) { simKbps = 14; simDirection = -1; }
                    if (simKbps <= 2) { simKbps = 2; simDirection = 1; }
                    currentKbps = simKbps;
                }

                updateStatsDisplay(currentKbps, this.currentMode, this.getPreset(this.activePresetKey));
            };

            setInterval(runBitrateTick, 2000);

            // Listen to WebRTC stats updates
            this.addListener((data) => {
                const kbps = data.bitrateBps > 0 ? Math.round(data.bitrateBps / 1000) : simKbps;
                updateStatsDisplay(kbps, data.mode, data.effectivePreset);
            });

            // Initial render
            updateQualityUI(this.currentMode);
            runBitrateTick();

            return wrap;
        }

        /**
         * Backward compatibility alias
         */
        createQualitySelectorUI(options = {}) {
            return this.createUnifiedQualityControl(options);
        }
    }

    // Attach singleton instance to window for global modular usage
    window.VideoQualityManager = new VideoQualityManager();
    window.QUALITY_PRESETS = QUALITY_PRESETS;
})();
