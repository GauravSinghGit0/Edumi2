/**
 * Lip-Sync (Audio/Video Synchronization) Manager for Meetings
 * 
 * Solves audio-video lip-sync mismatch in WebRTC meetings:
 * 1. Client-side Sender: Packages local audio (mic) and video (camera) track metadata,
 *    high-precision timestamps, stream IDs, and playout delay calibration into an A/V sync package.
 *    Transmits the package across both LiveKit DataChannel and Django Channels WebSocket signaling.
 * 2. Client-side Receiver: Unpacks the A/V sync package, pairs matching audio and video tracks,
 *    unifies them into a single MediaStream([videoTrack, audioTrack]) bound to the participant's video player,
 *    enforces matching RTP jitter buffer playout delays, and eliminates un-synced standalone audio tags.
 */

(function () {
    'use strict';

    class LipSyncManager {
        constructor() {
            this.room = null;
            this.signalingWs = null;
            this.heartbeatInterval = null;
            this.remotePackages = new Map(); // participantId -> package
            this.remoteTracks = new Map();   // participantId -> { video, audio, videoPub, audioPub, screen }
            this.syncedStreams = new Map(); // participantId -> MediaStream
            this.targetPlayoutDelay = 0.12;  // 120ms WebRTC playout delay hint for jitter buffer alignment
            this.isStarted = false;
        }

        /**
         * Initialize and start the Lip-Sync manager
         */
        start(room, signalingWs) {
            this.room = room || window.room;
            this.signalingWs = signalingWs || window.signalingWs;
            this.isStarted = true;

            console.log('[LipSyncManager] Starting Lip-Sync Packaging & Unpacking Engine');

            // Send initial sync package
            this.makePackageAndSend();

            // Setup periodic heartbeat to keep all peers (including late joiners) synchronized
            if (this.heartbeatInterval) {
                clearInterval(this.heartbeatInterval);
            }
            this.heartbeatInterval = setInterval(() => {
                if (this.isStarted) {
                    this.makePackageAndSend();
                }
            }, 3000);
        }

        /**
         * Stop the Lip-Sync manager and clean up
         */
        stop() {
            this.isStarted = false;
            if (this.heartbeatInterval) {
                clearInterval(this.heartbeatInterval);
                this.heartbeatInterval = null;
            }
            this.syncedStreams.clear();
            this.remotePackages.clear();
            this.remoteTracks.clear();
            console.log('[LipSyncManager] Stopped');
        }

        /**
         * Make an A/V sync package on client side
         */
        makePackage() {
            const lp = this.room?.localParticipant || window.room?.localParticipant;
            const participantId = lp?.identity ? String(lp.identity) : String(window.currentUserId || 'local');
            const displayName = window.meetingConfig?.currentDisplayName || window.currentDisplayName || window.currentUsername || 'Participant';

            let videoTrackSid = null;
            let videoMediaId = null;
            let isVideoActive = !!window.isCameraOn;

            let audioTrackSid = null;
            let audioMediaId = null;
            let isAudioActive = !!window.isMicOn;

            if (lp) {
                // Find camera track publication
                const vPubs = lp.videoTrackPublications || lp.tracks;
                if (vPubs) {
                    vPubs.forEach(pub => {
                        const tr = pub.track || pub.videoTrack;
                        const src = pub.source || tr?.source || '';
                        const isCam = src === 'camera' || String(src).includes('cam') || (!String(src).includes('screen') && tr?.kind === 'video');
                        if (isCam && tr) {
                            videoTrackSid = pub.trackSid || tr.sid || null;
                            const mst = tr.mediaStreamTrack || (tr instanceof MediaStreamTrack ? tr : null);
                            if (mst) videoMediaId = mst.id;
                            isVideoActive = !pub.isMuted && !tr.isMuted;
                        }
                    });
                }

                // Find microphone track publication
                const aPubs = lp.audioTrackPublications || lp.tracks;
                if (aPubs) {
                    aPubs.forEach(pub => {
                        const tr = pub.track || pub.audioTrack;
                        const src = pub.source || tr?.source || '';
                        const isMic = src === 'microphone' || String(src).includes('mic') || tr?.kind === 'audio';
                        if (isMic && tr) {
                            audioTrackSid = pub.trackSid || tr.sid || null;
                            const mst = tr.mediaStreamTrack || (tr instanceof MediaStreamTrack ? tr : null);
                            if (mst) audioMediaId = mst.id;
                            isAudioActive = !pub.isMuted && !tr.isMuted;
                        }
                    });
                }
            }

            const pkg = {
                type: 'av_sync_package',
                action: 'sync_package',
                version: '1.0',
                participantId: participantId,
                displayName: displayName,
                timestamp: Date.now(),
                perfTime: performance.now(),
                syncStreamId: `sync-stream-${participantId}`,
                tracks: {
                    video: {
                        trackSid: videoTrackSid,
                        mediaTrackId: videoMediaId,
                        source: 'camera',
                        enabled: isVideoActive
                    },
                    audio: {
                        trackSid: audioTrackSid,
                        mediaTrackId: audioMediaId,
                        source: 'microphone',
                        enabled: isAudioActive
                    }
                },
                targetPlayoutDelay: this.targetPlayoutDelay
            };

            return pkg;
        }

        /**
         * Send the A/V sync package across LiveKit DataChannel and WebSocket signaling
         */
        sendPackage(pkg) {
            if (!pkg) return;
            const payload = JSON.stringify(pkg);

            // 1. Send via LiveKit Data Channel (Reliable mode)
            const lp = this.room?.localParticipant || window.room?.localParticipant;
            if (lp && typeof lp.publishData === 'function') {
                try {
                    const encoded = new TextEncoder().encode(payload);
                    lp.publishData(encoded, { reliable: true }).catch(err => {
                        console.debug('[LipSyncManager] publishData catch (non-fatal):', err);
                    });
                } catch (e) {
                    console.debug('[LipSyncManager] publishData error:', e);
                }
            }

            // 2. Send via Django Channels Signaling WebSocket
            const ws = this.signalingWs || window.signalingWs;
            if (ws && ws.readyState === WebSocket.OPEN) {
                try {
                    ws.send(JSON.stringify({
                        type: 'av_sync_package',
                        package: pkg
                    }));
                } catch (e) {
                    console.debug('[LipSyncManager] Signaling WS send error:', e);
                }
            }
        }

        /**
         * Make package and send helper
         */
        makePackageAndSend() {
            try {
                const pkg = this.makePackage();
                this.sendPackage(pkg);
            } catch (err) {
                console.debug('[LipSyncManager] makePackageAndSend error:', err);
            }
        }

        /**
         * Receiver: Unpack an A/V sync package from remote peer
         */
        unpackPackage(rawPackage) {
            try {
                let pkg = rawPackage;
                if (typeof rawPackage === 'string') {
                    pkg = JSON.parse(rawPackage);
                } else if (rawPackage instanceof Uint8Array || rawPackage instanceof ArrayBuffer) {
                    pkg = JSON.parse(new TextDecoder().decode(rawPackage));
                }

                if (!pkg || pkg.type !== 'av_sync_package' || !pkg.participantId) {
                    return;
                }

                // Ignore our own package echo
                const myId = this.room?.localParticipant?.identity || window.room?.localParticipant?.identity || String(window.currentUserId);
                if (String(pkg.participantId) === String(myId)) {
                    return;
                }

                const participantId = String(pkg.participantId);
                this.remotePackages.set(participantId, pkg);

                console.log(`[LipSyncManager] Unpacked A/V sync package from ${participantId}:`, {
                    video: pkg.tracks?.video?.trackSid,
                    audio: pkg.tracks?.audio?.trackSid,
                    perfTime: pkg.perfTime
                });

                // Apply synchronization immediately with unpacked package info
                this.synchronizeParticipant(participantId);
            } catch (err) {
                console.warn('[LipSyncManager] Error unpacking package:', err);
            }
        }

        /**
         * Register remote track arrived via LiveKit TrackSubscribed
         */
        registerRemoteTrack(participantId, track, publication) {
            if (!participantId || !track) return;
            const strId = String(participantId);

            let entry = this.remoteTracks.get(strId);
            if (!entry) {
                entry = { video: null, audio: null, videoPub: null, audioPub: null, screen: null };
                this.remoteTracks.set(strId, entry);
            }

            const source = publication?.source || track?.source || '';
            const isScreen = String(source).includes('screen');

            if (isScreen) {
                entry.screen = track;
            } else if (track.kind === 'video') {
                entry.video = track;
                entry.videoPub = publication;
            } else if (track.kind === 'audio') {
                entry.audio = track;
                entry.audioPub = publication;
            }

            // Trigger synchronization
            this.synchronizeParticipant(strId);
        }

        /**
         * Unregister remote track on TrackUnsubscribed
         */
        unregisterRemoteTrack(participantId, track, publication) {
            if (!participantId || !track) return;
            const strId = String(participantId);
            const entry = this.remoteTracks.get(strId);
            if (!entry) return;

            if (track.kind === 'video') {
                if (entry.video === track) {
                    entry.video = null;
                    entry.videoPub = null;
                }
            } else if (track.kind === 'audio') {
                if (entry.audio === track) {
                    entry.audio = null;
                    entry.audioPub = null;
                }
            }

            this.synchronizeParticipant(strId);
        }

        /**
         * Synchronize audio and video for a participant:
         * Unpacks matching tracks into a single unified MediaStream on the <video> element.
         * Browser HTMLMediaElement media clock locks video frames to the audio PTS.
         */
        synchronizeParticipant(participantId) {
            const strId = String(participantId);
            const box = document.getElementById(`video-box-${strId}`);
            if (!box) {
                // Video box not in DOM yet; will synchronize when created
                return;
            }

            const entry = this.remoteTracks.get(strId);
            const pkg = this.remotePackages.get(strId);

            // Attempt to discover tracks from LiveKit participant object if not explicitly cached
            let vTrack = entry?.video;
            let aTrack = entry?.audio;

            if (!vTrack || !aTrack) {
                const p = this.getParticipantById(strId);
                if (p) {
                    const pubs = p.trackPublications || p.tracks;
                    if (pubs) {
                        pubs.forEach(pub => {
                            const tr = pub.track || pub.videoTrack || pub.audioTrack;
                            if (!tr) return;
                            const src = pub.source || tr.source || '';
                            const isScreen = String(src).includes('screen');
                            if (!isScreen) {
                                if (tr.kind === 'video' && !vTrack) vTrack = tr;
                                if (tr.kind === 'audio' && !aTrack) aTrack = tr;
                            }
                        });
                    }
                }
            }

            const vMst = vTrack?.mediaStreamTrack || (vTrack instanceof MediaStreamTrack ? vTrack : null);
            const aMst = aTrack?.mediaStreamTrack || (aTrack instanceof MediaStreamTrack ? aTrack : null);

            const videoEl = box.querySelector('video');

            // 1. Perfect Match: Both video and audio tracks exist!
            if (vMst && aMst && videoEl) {
                const isVideoLive = vMst.readyState === 'live';
                const isAudioLive = aMst.readyState === 'live';

                if (isVideoLive && isAudioLive) {
                    let syncStream = this.syncedStreams.get(strId);
                    const currentTracks = syncStream ? syncStream.getTracks() : [];
                    const hasBoth = currentTracks.includes(vMst) && currentTracks.includes(aMst);

                    if (!hasBoth) {
                        console.log(`[LipSyncManager] Binding matched Audio+Video package into synchronized stream for ${strId}`);
                        syncStream = new MediaStream([vMst, aMst]);
                        this.syncedStreams.set(strId, syncStream);

                        videoEl.srcObject = syncStream;
                        videoEl.muted = false; // Audio plays through video element!
                        videoEl.volume = 1.0;
                        videoEl.autoplay = true;
                        videoEl.playsInline = true;

                        videoEl.play().catch(err => {
                            console.debug('[LipSyncManager] Video/Audio play blocked by browser policy:', err);
                            const banner = document.getElementById('audioAutoplayBanner');
                            if (banner) banner.style.display = 'flex';
                        });

                        // Set A/V synchronization indicator
                        box.dataset.lipSynced = 'true';
                        box.classList.add('av-synced');

                        // Remove redundant standalone audio tags to prevent echo
                        const standaloneAudio = document.querySelectorAll(`[id^="audio-${strId}"]`);
                        standaloneAudio.forEach(el => {
                            el.pause();
                            el.srcObject = null;
                            el.remove();
                        });

                        // Apply WebRTC RTP playout delay hint to balance jitter buffers
                        const delay = pkg?.targetPlayoutDelay || this.targetPlayoutDelay;
                        this.applyPlayoutDelayHint(vTrack, delay);
                        this.applyPlayoutDelayHint(aTrack, delay);
                    }
                    return;
                }
            }

            // 2. Video only (mic muted or no audio)
            if (vMst && videoEl && (!aMst || aMst.readyState !== 'live')) {
                let syncStream = this.syncedStreams.get(strId);
                const currentTracks = syncStream ? syncStream.getTracks() : [];
                if (!currentTracks.includes(vMst) || currentTracks.length > 1) {
                    syncStream = new MediaStream([vMst]);
                    this.syncedStreams.set(strId, syncStream);
                    videoEl.srcObject = syncStream;
                    videoEl.muted = true;
                    videoEl.play().catch(() => {});
                }
                return;
            }

            // 3. Audio only (camera off)
            if (aMst && aMst.readyState === 'live' && (!vMst || vMst.readyState !== 'live')) {
                // Ensure audio is playing via fallback audio element if video element is unattached
                let audioEl = document.getElementById(`audio-${strId}-lip`);
                if (!audioEl) {
                    audioEl = document.createElement('audio');
                    audioEl.id = `audio-${strId}-lip`;
                    audioEl.style.display = 'none';
                    audioEl.autoplay = true;
                    audioEl.muted = false;
                    audioEl.volume = 1.0;
                    document.body.appendChild(audioEl);
                }
                if (audioEl.srcObject !== aMst) {
                    audioEl.srcObject = new MediaStream([aMst]);
                    audioEl.play().catch(() => {});
                }
            }
        }

        /**
         * Set WebRTC RTP receiver playout delay hint to equalize jitter buffer latency
         */
        applyPlayoutDelayHint(track, delaySeconds) {
            if (!track) return;
            try {
                // Check receiver on Track
                const receiver = track.receiver || track.rtpReceiver;
                if (receiver) {
                    if ('playoutDelayHint' in receiver) {
                        receiver.playoutDelayHint = delaySeconds;
                    }
                    if ('jitterBufferTarget' in receiver) {
                        receiver.jitterBufferTarget = delaySeconds * 1000;
                    }
                }
            } catch (err) {
                console.debug('[LipSyncManager] playoutDelayHint warning:', err);
            }
        }

        /**
         * Participant lookup helper
         */
        getParticipantById(identity) {
            if (!identity) return null;
            if (typeof window.getRemoteParticipant === 'function') {
                const p = window.getRemoteParticipant(identity);
                if (p) return p;
            }
            if (this.room?.remoteParticipants) {
                return this.room.remoteParticipants.get(String(identity));
            }
            return null;
        }
    }

    // Export singleton instance to window
    window.LipSyncManager = new LipSyncManager();
})();
