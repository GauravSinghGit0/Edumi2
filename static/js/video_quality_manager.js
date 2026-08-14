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

            console.log('%c[VideoQualityManager] Initialized ✅', 'background:#10b981;color:#fff;padding:2px 6px;border-radius:3px;font-weight:bold;');
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
            let bytesSent = 0;
            let timestamp = Date.now();

            try {
                let statsReport = null;

                // LiveKit Room check
                if (roomOrPc && roomOrPc.engine && roomOrPc.engine.client) {
                    const pc = roomOrPc.engine.publisher ? roomOrPc.engine.publisher.pc : null;
                    if (pc && typeof pc.getStats === 'function') {
                        statsReport = await pc.getStats();
                    }
                } else if (roomOrPc && typeof roomOrPc.getStats === 'function') {
                    statsReport = await roomOrPc.getStats();
                }

                if (statsReport) {
                    statsReport.forEach(report => {
                        if (report.type === 'outbound-rtp' && report.kind === 'video') {
                            bytesSent += (report.bytesSent || 0);
                        }
                    });

                    if (this.lastBytesSent > 0 && timestamp > this.lastTimestamp) {
                        const durationSec = (timestamp - this.lastTimestamp) / 1000;
                        const deltaBytes = Math.max(0, bytesSent - this.lastBytesSent);
                        this.currentBitrateBps = Math.round((deltaBytes * 8) / durationSec);

                        // Auto-adjust resolution tier if mode is set to 'auto'
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

                    this.lastBytesSent = bytesSent;
                    this.lastTimestamp = timestamp;
                }
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
                console.log(`[VideoQualityManager] Auto-adjusting video quality: ${this.activePresetKey} → ${recommendedKey} (Bitrate: ${this.formatBitrate(bitrateBps)})`);
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
         * Generate Quality Selector HTML Element & Badge UI
         */
        createQualitySelectorUI(options = {}) {
            const container = document.createElement('div');
            container.className = 'video-quality-control-wrap';
            container.style.cssText = 'display:inline-flex;align-items:center;gap:8px;background:rgba(15,23,42,0.8);backdrop-filter:blur(8px);padding:4px 10px;border-radius:10px;border:1px solid rgba(255,255,255,0.12);font-family:Inter,sans-serif;font-size:12px;color:#fff;';

            const badge = document.createElement('span');
            badge.className = 'video-bitrate-badge';
            badge.style.cssText = 'font-weight:600;color:#10b981;white-space:nowrap;font-size:11px;';
            badge.textContent = 'Auto | 0 kbps';

            const select = document.createElement('select');
            select.className = 'video-quality-select';
            select.style.cssText = 'background:rgba(255,255,255,0.1);color:#fff;border:none;border-radius:6px;padding:3px 8px;font-size:11px;font-weight:600;outline:none;cursor:pointer;';

            Object.keys(QUALITY_PRESETS).forEach(key => {
                const opt = document.createElement('option');
                opt.value = key;
                opt.textContent = QUALITY_PRESETS[key].label;
                opt.style.cssText = 'background:#1e293b;color:#fff;';
                if (key === this.currentMode) opt.selected = true;
                select.appendChild(opt);
            });

            select.addEventListener('change', (e) => {
                const selectedKey = e.target.value;
                this.currentMode = selectedKey;
                if (options.onQualityChange) {
                    options.onQualityChange(selectedKey);
                }
            });

            // Update badge when stats update
            this.addListener((data) => {
                const modeText = data.mode === 'auto' ? `Auto (${data.effectivePreset ? data.effectivePreset.label.split(' ')[0] : '1080p'})` : data.mode.toUpperCase();
                const bitrateText = data.bitrateFormatted || '0 kbps';
                badge.textContent = `${modeText} | ${bitrateText}`;
            });

            container.appendChild(badge);
            container.appendChild(select);
            return container;
        }
    }

    // Attach singleton instance to window for global modular usage
    window.VideoQualityManager = new VideoQualityManager();
    window.QUALITY_PRESETS = QUALITY_PRESETS;
})();
