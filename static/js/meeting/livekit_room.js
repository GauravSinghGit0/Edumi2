// VERSION: TrackManager-v3 (2026-08-09) — if you don't see this in console, browser has cached old code
        console.log('%c[EduMi Meeting] JS Version: TrackManager-v3 loaded ✅', 'background:#8b5cf6;color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;');
        let room = null;
        // ── Config ────────────────────────────────────────────────────────────────────
        // Global scope variables for access across functions
        var _d = document.getElementById('meeting-data').dataset;
        var meetingCode = _d.meetingCode;
        var currentUserId = _d.userId;
        var currentUsername = _d.username;
        var isHost = _d.isHost === 'true';

        // Assign to window for Turbo Drive compatibility
        window.meetingConfig = {
            meetingCode: _d.meetingCode,
            currentUserId: _d.userId,
            currentUsername: _d.username,
            currentDisplayName: _d.displayName || _d.username,
            currentPfpUrl: _d.pfpUrl || '',
            isHost: _d.isHost === 'true',
            userType: _d.userType,
            hostId: _d.hostId,
            TOKEN_URL: _d.tokenUrl,
            LEAVE_URL: _d.leaveUrl,
            SLEEP_URL: _d.sleepUrl,
            UNFREEZE_URL: _d.unfreezeUrl,
            AFTER_LEAVE: _d.afterLeaveUrl,
            CSRF: _d.csrf,
            kickUrl: _d.kickUrl,
            bannedUsersUrl: _d.bannedUsersUrl,
            revokeBanUrl: _d.revokeBanUrl,
            globalControlUrl: _d.globalControlUrl,
            studentCanViewCamera: _d.studentCanViewCamera === 'true',
            studentCanViewScreenshare: _d.studentCanViewScreenshare === 'true',
            allowChat: _d.allowChat !== 'false',
            hostJoinedAtMs: parseInt(_d.hostJoinedAtMs || "0"),
            meetingId: _d.meetingId,
            recordingUploadUrl: _d.recordingUploadUrl,
            faceNotRegistered: _d.faceNotRegistered === 'true'
        };

        window.allowChat = window.meetingConfig.allowChat;

        // ── LiveKit SDK Initialization ────────────────────────────────────────────────
        var Room, RoomEvent, Track, TrackEvent, LocalTrack, createLocalTracks,
            createLocalScreenTracks, VideoPresets, ScreenSharePresets, ConnectionState;

        function extractLiveKitSymbols() {
            if (!window.LiveKitBundle) return false;
            try {
                const bundle = window.LiveKitBundle;
                Room = bundle.Room;
                RoomEvent = bundle.RoomEvent;
                Track = bundle.Track;
                TrackEvent = bundle.TrackEvent;
                LocalTrack = bundle.LocalTrack;
                createLocalTracks = bundle.createLocalTracks;
                createLocalScreenTracks = bundle.createLocalScreenTracks;
                VideoPresets = bundle.VideoPresets;
                ScreenSharePresets = bundle.ScreenSharePresets;
                ConnectionState = bundle.ConnectionState;
                return !!Room;
            } catch (e) {
                console.error("SDK symbol extraction failed:", e);
                return false;
            }
        }

        // ── State ─────────────────────────────────────────────────────────────────────
        Object.defineProperty(window, 'room', {
            get: function () { return window._livekitRoomInstance; },
            set: function (val) {
                window._livekitRoomInstance = val;
                room = val;
            },
            configurable: true
        });
        window.room = null;
        window.isMicOn = true;
        window.isCameraOn = true;
        window.isScreenSharing = false;
        window.screenTrackPub = null;
        window.isSleeping = false;
        window.unreadMessages = 0;
        window.timerInterval = null;
        window.timerSeconds = 0;
        window.signalingWs = null;

        // IP Camera State
        window.currentVideoSource = 'webcam'; // 'webcam' or 'ip'
        window.currentIpCamId = null;

        // ── Manual participant registry ────────────────────────────────────────────────
        // Key: identity string → participant object or plain info object.
        // This is more reliable than room.remoteParticipants across proxy/SDK versions.
        window._remoteParticipantsRegistry = new Map();

        function getRemoteParticipants() {
            // Merge manual registry with LiveKit SDK map so we never miss anyone.
            const combined = new Map(window._remoteParticipantsRegistry);
            if (window.room) {
                const pMap = window.room.remoteParticipants || window.room.participants;
                if (pMap && typeof pMap.forEach === 'function') {
                    pMap.forEach((p, key) => {
                        if (p && p.identity) combined.set(String(p.identity), p);
                    });
                }
            }
            return Array.from(combined.values());
        }

        function getRemoteParticipant(identity) {
            if (!identity) return null;
            const strId = String(identity);
            if (window.room) {
                const pMap = window.room.remoteParticipants || window.room.participants;
                if (pMap) {
                    const p = pMap.get(strId) || pMap.get(identity);
                    if (p) return p;
                }
            }
            return window._remoteParticipantsRegistry.get(strId) || window._remoteParticipantsRegistry.get(identity) || null;
        }
        window.ipCamImg = null;
        window.ipCamAnimationId = null;
        window.ipCamTrackPub = null;
        window.ipCamCanvas = null;
        window.ipCamCtx = null;

        // Permission State (Always allowed as per teacher request)
        window.canSpeak = true;
        window.canVideo = true;
        window.canShare = true;

        // ── TrackManager: Industry-standard, crash-proof track lifecycle ──────────────
        // Google Meet / Zoom pattern:
        //   - One source of truth: Map<trackSid → {el, boxId}>
        //   - Dedup guard: skip if already attached (uses publication.trackSid as key,
        //     because track.sid may be empty at TrackSubscribed time in LiveKit v1.x)
        //   - Screen share always gets its own dedicated DOM box
        //   - Never calls .play() manually — LiveKit SDK + autoplay handles it
        window.TrackManager = {
            /** @type {Map<string, {el: HTMLElement, boxId: string}>} */
            _attached: new Map(),

            // Use string literals only — Track.Source constants are set later during init()
            _isScreen(source) {
                if (!source) return false;
                const str = String(source).toLowerCase();
                return str.includes('screen') || (typeof Track !== 'undefined' && source === Track.Source.ScreenShare);
            },

            /** Stable unique key: prefers publication.trackSid, falls back to track.sid or element key */
            _key(track, publication) {
                return publication?.trackSid || track?.sid || publication?.sid || (track?.mediaStreamTrack && track.mediaStreamTrack.id) || `track-${Math.random().toString(36).substr(2, 9)}`;
            },

            /** Returns the correct box — camera box or dedicated per-participant screen box */
            _getBox(source, participant) {
                if (this._isScreen(source)) {
                    return this._getOrCreateScreenBox(participant);
                }
                return getOrCreateBox(participant.identity, participant.name || participant.identity, false);
            },

            _getOrCreateScreenBox(participant) {
                const id = `screen-box-${participant.identity}`;
                let box = document.getElementById(id);
                const screenLabel = getScreenShareLabel(participant.identity, participant.name || participant.identity);
                if (!box) {
                    box = document.createElement('div');
                    box.id = id;
                    box.className = 'video-box screen-share-active sharing-screen';
                    box.dataset.identity = `screen-${participant.identity}`;

                    // Screen share primary stage badge (Single Top-Left Badge)
                    const shareBadge = document.createElement('div');
                    shareBadge.className = 'screen-share-indicator-badge';
                    shareBadge.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg> ${screenLabel}`;
                    box.appendChild(shareBadge);

                    const sidebar = document.getElementById('sidebarVideoArea');
                    if (sidebar) sidebar.appendChild(box);
                } else {
                    const badge = box.querySelector('.screen-share-indicator-badge');
                    if (badge) {
                        badge.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg> ${screenLabel}`;
                    }
                }
                return box;
            },

            /**
             * Attach a remote track to its correct box.
             * Safe to call multiple times — deduplication via trackSid.
             */
            attach(track, publication, participant) {
                if (!track || !participant?.identity) return;

                const key = this._key(track, publication);
                if (!key) {
                    console.warn('TrackManager: no trackSid available, skipping attach');
                    return;
                }

                // Dedup guard — already attached, bail out
                if (this._attached.has(key)) {
                    console.debug(`TrackManager: skip duplicate attach for ${key}`);
                    return;
                }

                const source = publication?.source || track?.source || '';
                const box = this._getBox(source, participant);
                if (!box) return;

                // Remove any stale element of this track kind in this box
                box.querySelectorAll(`[data-track-key]`).forEach(old => {
                    if (old.dataset.kind === track.kind) old.remove();
                });

                // LiveKit attach() returns a fully configured <video> or <audio> element
                const el = track.attach();
                el.dataset.trackKey = key;
                el.dataset.kind = track.kind;
                el.dataset.source = source;

                const isScreen = this._isScreen(source);

                if (track.kind === 'video') {
                    el.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
                    if (isScreen) el.style.objectFit = 'contain';
                    el.muted = true;
                    el.autoplay = true;
                    el.playsInline = true;
                    box.insertBefore(el, box.querySelector('.video-nametag'));

                    if (isScreen) {
                        const screenLabel = getScreenShareLabel(participant.identity, participant.name || participant.identity);
                        console.log(`TrackManager: enlarging screen share for [${screenLabel}]`);
                        moveToMain(box, screenLabel, true);

                        // Add presenting visual indicator to presenter's camera tile
                        const camBox = document.getElementById(`video-box-${participant.identity}`);
                        if (camBox) {
                            camBox.classList.add('is-presenting');
                            if (!camBox.querySelector('.presenting-badge')) {
                                const pb = document.createElement('div');
                                pb.className = 'presenting-badge';
                                pb.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg> Presenting`;
                                camBox.appendChild(pb);
                            }
                        }
                    }
                } else if (track.kind === 'audio') {
                    // Audio elements live on <body>, hidden, not inside video boxes
                    el.id = `audio-${participant.identity}-${key}`;
                    el.style.display = 'none';
                    el.autoplay = true;
                    el.muted = false;
                    el.volume = 1.0;
                    document.body.appendChild(el);
                    el.play().catch(err => {
                        console.warn('Audio play notice (awaiting user gesture):', err);
                        const banner = document.getElementById('audioAutoplayBanner');
                        if (banner) banner.style.display = 'flex';
                    });
                }

                this._attached.set(key, { el, boxId: box.id, isScreen, identity: participant.identity });

                if (track.kind === 'video' && !isScreen) {
                    box.classList.remove('cam-off');
                }

                // Register with LipSyncManager to pair audio and video tracks and unpack/synchronize them
                if (window.LipSyncManager && participant?.identity) {
                    window.LipSyncManager.registerRemoteTrack(participant.identity, track, publication);
                }

                console.log(`TrackManager: attached ${track.kind} [${source}] from ${participant.identity} key=${key}`);
            },

            /**
             * Detach a remote track and clean up DOM.
             * Safe to call even if the track was never attached.
             */
            detach(track, publication, participant) {
                const key = this._key(track, publication);
                const entry = key ? this._attached.get(key) : null;
                const source = publication?.source || track?.source || '';
                const isScreen = this._isScreen(source);

                // Unregister from LipSyncManager
                if (window.LipSyncManager && participant?.identity) {
                    window.LipSyncManager.unregisterRemoteTrack(participant.identity, track, publication);
                }

                // Detach all elements this track was attached to via LiveKit SDK
                try { track.detach().forEach(el => el.remove()); } catch (_) { }

                // Also remove the element we tracked
                if (entry) {
                    try { entry.el.remove(); } catch (_) { }
                    if (key) this._attached.delete(key);
                }

                // Audio cleanup by ID
                if (track.kind === 'audio' && participant?.identity && key) {
                    const audioEl = document.getElementById(`audio-${participant.identity}-${key}`);
                    if (audioEl) audioEl.remove();
                }

                if (track.kind === 'video' && !isScreen && participant?.identity) {
                    const camBox = document.getElementById(`video-box-${participant.identity}`);
                    if (camBox) camBox.classList.add('cam-off');
                }

                // Remove dedicated screen share box + restore main area + remove presenting indicator
                if (isScreen && participant?.identity) {
                    const screenBox = document.getElementById(`screen-box-${participant.identity}`);
                    if (screenBox) screenBox.remove();

                    const camBox = document.getElementById(`video-box-${participant.identity}`);
                    if (camBox) {
                        camBox.classList.remove('is-presenting');
                        camBox.querySelector('.presenting-badge')?.remove();
                    }

                    clearMain();
                    updateLayout();
                }

                console.log(`TrackManager: detached ${track.kind} [${source}] from ${participant?.identity}`);
            },

            /** Full reset on room disconnect */
            clear() {
                if (window.LipSyncManager) {
                    window.LipSyncManager.stop();
                }
                this._attached.forEach(({ el }) => { try { el.remove(); } catch (_) { } });
                this._attached.clear();
                document.querySelectorAll('[id^="screen-box-"]').forEach(b => b.remove());
            }
        };

        // ── Init ──────────────────────────────────────────────────────────────────────
        async function init() {
            if (!extractLiveKitSymbols()) {
                console.warn('LiveKit SDK missing or incomplete! Retrying init in 1s...');
                setTimeout(init, 1000);
                return;
            }

            // ── Signaling WebSocket ──────────────────────────────────────────────────
            try {
                const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                window.signalingWs = new WebSocket(`${proto}//${window.location.host}/ws/meeting/${window.meetingCode}/`);
                window.signalingWs.onerror = (e) => {
                    console.warn('Signaling WebSocket error (non-fatal):', e);
                };
                window.signalingWs.onmessage = (e) => {
                    try {
                        const data = JSON.parse(e.data);
                        handleSignalingMessage(data);
                    } catch (err) {
                        console.error('Signaling parse error:', err);
                    }
                };
            } catch (wsErr) {
                console.warn('Signaling WebSocket creation failed:', wsErr);
            }

            // Render local box immediately while connecting
            renderLocalParticipant();

            // Fetch token from Django
            try {
                const res = await fetch(window.TOKEN_URL);
                const data = await res.json();
                if (data.error) {
                    showNotification('Access denied: ' + data.error, 'error');
                    return;
                }

                const { token, url } = data;

                // Show registration warning for students if not registered
                if (!window.meetingConfig?.isHost && (data.face_not_registered || window.meetingConfig.faceNotRegistered)) {
                    showNotification('Face not registered! Please register in Attendance Settings.', 'warning');
                }

                window.room = new Room({
                    adaptiveStream: true,
                    dynacast: true,
                    publishDefaults: {
                        simulcast: true,
                        videoCodec: 'vp8',
                        // M5 Winner: SVC 3-layer bitrate envelope (250k - 1200k) for zero-freeze rural streaming
                        videoEncoding: {
                            maxBitrate: 1200000,
                            maxFramerate: 30,
                        },
                    },
                    rtcConfig: {
                        iceServers: [
                            { urls: 'stun:stun.l.google.com:19302' },
                            { urls: 'stun:stun1.l.google.com:19302' }
                        ]
                    }
                });

                // ── Room events ───────────────────────────────────────────────────────────
                window.room
                    .on(RoomEvent.ParticipantConnected, onParticipantConnected)
                    .on(RoomEvent.ParticipantDisconnected, onParticipantDisconnected)
                    .on(RoomEvent.ParticipantMetadataChanged, (arg1, arg2) => {
                        updateParticipantMetadataUI(arg1, arg2);
                        updateParticipantsList();
                    })
                    .on(RoomEvent.TrackSubscribed, onTrackSubscribed)
                    .on(RoomEvent.TrackUnsubscribed, onTrackUnsubscribed)
                    .on(RoomEvent.TrackPublished, (pub, participant) => {
                        // Track announced — media not yet ready.
                        // TrackSubscribed fires exactly when media arrives; handle it there.
                        console.log(`Track published: ${pub.source} from ${participant.identity} (waiting for subscription)`);
                    })
                    .on(RoomEvent.TrackMuted, onTrackMuted)
                    .on(RoomEvent.TrackUnmuted, onTrackUnmuted)
                    .on(RoomEvent.ActiveSpeakersChanged, onActiveSpeakersChanged)
                    .on(RoomEvent.DataReceived, onDataReceived)
                    .on(RoomEvent.Disconnected, onDisconnected)
                    .on(RoomEvent.ConnectionStateChanged, onConnectionStateChanged);

                await window.room.connect(url, token);
                console.log('Connected to LiveKit room:', window.room.name);

                // Auto-resume AudioContext or bind user gesture unlock
                try {
                    await window.room.startAudio();
                } catch (audioContextErr) {
                    console.warn('AudioContext autoplay restricted by browser, listening for user gesture to activate audio.');
                    const banner = document.getElementById('audioAutoplayBanner');
                    if (banner) banner.style.display = 'flex';
                }

                const resumeAudioOnGesture = async () => {
                    if (window.room) {
                        try {
                            await window.room.startAudio();
                            console.log('LiveKit AudioContext activated via user gesture.');
                        } catch (e) {
                            console.warn('startAudio attempt on gesture:', e);
                        }
                    }
                    document.querySelectorAll('audio').forEach(a => {
                        if (a.paused) {
                            a.play().catch(_ => { });
                        }
                    });
                    const banner = document.getElementById('audioAutoplayBanner');
                    if (banner) banner.style.display = 'none';
                };
                ['click', 'touchstart', 'keydown'].forEach(evtType => {
                    document.addEventListener(evtType, resumeAudioOnGesture, { passive: true });
                });

                // Initialize Video Quality Manager & Auto Bitrate Monitor
                if (window.VideoQualityManager) {
                    const container = document.getElementById('unifiedQualityControl') || document.getElementById('qualityWidgetContainer');
                    if (container && !container.children.length) {
                        const ui = window.VideoQualityManager.createUnifiedQualityControl({
                            onQualityChange: (mode) => {
                                window.VideoQualityManager.applyQualityToLiveKit(window.room, mode);
                                showNotification(`Video quality set to ${mode.toUpperCase()}`, 'info');
                            }
                        });
                        container.appendChild(ui);
                    }
                    window.VideoQualityManager.startBitrateMonitor(window.room);
                }

                // Initialize Lip-Sync Manager (audio-video synchronization package engine)
                if (window.LipSyncManager) {
                    window.LipSyncManager.start(window.room, window.signalingWs);
                }

                // Initial desired media state
                window.isMicOn = window.isHost ? true : window.canSpeak;
                window.isCameraOn = window.isHost ? true : window.canVideo;

                // Check for secure context and mediaDevices availability
                const isSecureMediaContext = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

                if (!isSecureMediaContext) {
                    console.warn('WebRTC media devices disabled due to non-secure HTTP context or browser restriction');
                    window.isMicOn = false;
                    window.isCameraOn = false;
                    if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
                        showNotification('Camera & Microphone disabled: HTTPS connection required by browser.', 'warning');
                    }
                } else {
                    // Attempt Microphone (Official LiveKit API sets localParticipant.isMicrophoneEnabled = true)
                    if (window.isMicOn) {
                        try {
                            await window.room.localParticipant.setMicrophoneEnabled(true, {
                                echoCancellation: true,
                                noiseSuppression: true,
                                autoGainControl: true
                            });
                        } catch (micErr) {
                            console.warn('Microphone initialization failed:', micErr);
                            window.isMicOn = false;
                            let msg = 'Microphone access failed. Joined in listen-only mode.';
                            if (micErr.name === 'NotFoundError' || micErr.name === 'DevicesNotFoundError') {
                                msg = 'No microphone found on this device.';
                            } else if (micErr.name === 'NotAllowedError' || micErr.name === 'PermissionDeniedError') {
                                msg = 'Microphone permission denied.';
                            } else if (micErr.name === 'NotReadableError' || micErr.name === 'TrackStartError') {
                                msg = 'Microphone is currently in use by another app.';
                            }
                            showNotification(msg, 'warning');
                        }
                    }

                    // Attempt Camera (Official LiveKit API sets localParticipant.isCameraEnabled = true)
                    if (window.isCameraOn) {
                        try {
                            await window.room.localParticipant.setCameraEnabled(true);
                        } catch (camErr) {
                            console.warn('Camera initialization failed:', camErr);
                            window.isCameraOn = false;
                            let msg = 'Camera access failed. Joined without video.';
                            if (camErr.name === 'NotFoundError' || camErr.name === 'DevicesNotFoundError') {
                                msg = 'No camera found on this device.';
                            } else if (camErr.name === 'NotAllowedError' || camErr.name === 'PermissionDeniedError') {
                                msg = 'Camera permission denied.';
                            } else if (camErr.name === 'NotReadableError' || camErr.name === 'TrackStartError') {
                                msg = 'Camera is currently in use by another app.';
                            }
                            showNotification(msg, 'warning');
                        }
                    }
                }

                // Update UI buttons and permissions
                updateControlButtons();
                renderLocalParticipant();
                updateChatPermissionUI(window.allowChat);

                // Bind composer input listener for active send button state
                const chatInp = document.getElementById('chatInput');
                if (chatInp) {
                    chatInp.addEventListener('input', () => {
                        const sendBtn = document.getElementById('chatSendBtn');
                        const hasText = chatInp.value.trim().length > 0;
                        if (sendBtn) {
                            sendBtn.classList.toggle('active', hasText);
                            sendBtn.disabled = !hasText || (!window.allowChat && !window.isHost);
                        }
                    });
                }

                // Seed manual registry from SDK's remoteParticipants map (already connected peers)
                if (window.room && window.room.remoteParticipants && typeof window.room.remoteParticipants.forEach === 'function') {
                    window.room.remoteParticipants.forEach((p, identity) => {
                        if (p && p.identity) {
                            window._remoteParticipantsRegistry.set(p.identity, p);
                        }
                    });
                }

                getRemoteParticipants().forEach(p => onParticipantConnected(p));

                updateParticipantCount();
                // Immediately show correct elapsed time before first tick fires
                if (window.meetingConfig.hostJoinedAtMs > 0) {
                    timerSeconds = Math.max(0, Math.floor((Date.now() - window.meetingConfig.hostJoinedAtMs) / 1000));
                    const _m0 = String(Math.floor(timerSeconds / 60)).padStart(2, '0');
                    const _s0 = String(timerSeconds % 60).padStart(2, '0');
                    const _el = document.getElementById('meetTimer');
                    if (_el) _el.textContent = `${_m0}:${_s0}`;
                }
                startTimer();

                // Periodically refresh the participants list and video card avatars to prevent out-of-sync states
                setInterval(() => {
                    getRemoteParticipants().forEach(p => {
                        if (p && p.identity) {
                            updateParticipantMetadataUI(p);
                        }
                    });
                    updateParticipantsList();
                    updateParticipantCount();
                }, 2000);
            } catch (err) {
                console.error('Init failed:', err);
                showNotification('Failed to initialize meeting: ' + err.message, 'error');
            }
        }

        function updateControlButtons() {
            const micBtn = document.getElementById('micBtn');
            const camBtn = document.getElementById('camBtn');
            const micLabel = document.getElementById('micLabel');
            const camLabel = document.getElementById('camLabel');

            micBtn.classList.toggle('off', !isMicOn);
            camBtn.classList.toggle('off', !isCameraOn);

            const micOnIcon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>';
            const micOffIcon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"/><path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>';
            const camOnIcon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>';
            const camOffIcon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="1" y1="1" x2="23" y2="23"/><path d="M16 16v1a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2m5.66 0H14a2 2 0 0 1 2 2v3.34l1 1L23 7v10"/></svg>';

            micBtn.innerHTML = isMicOn ? micOnIcon : micOffIcon;
            camBtn.innerHTML = isCameraOn ? camOnIcon : camOffIcon;

            const micTip = (isMicOn ? 'Turn off microphone' : 'Turn on microphone') + ' (Ctrl+D)';
            const camTip = (isCameraOn ? 'Turn off camera' : 'Turn on camera') + ' (Ctrl+E)';

            micBtn.setAttribute('title', micTip);
            micBtn.setAttribute('data-tooltip', micTip);
            camBtn.setAttribute('title', camTip);
            camBtn.setAttribute('data-tooltip', camTip);

            // Update labels if present
            if (micLabel) micLabel.textContent = isMicOn ? 'Mute' : 'Unmute';
            if (camLabel) camLabel.textContent = isCameraOn ? 'Camera' : 'Start video';
        }

        // ── Shared Avatar Generation (Routes through IdentityDirectory) ────────────
        function getLocalInitialsAvatar(name, bgColor = '#8b5cf6') {
            return window.IdentityDirectory.getAvatarSvg(name, bgColor);
        }

        function getAvatarUrl(name, pfpUrl, bgColor = '#8b5cf6') {
            if (pfpUrl && typeof pfpUrl === 'string' && pfpUrl.trim() !== '' && pfpUrl !== 'null' && pfpUrl !== 'undefined') {
                if (pfpUrl.startsWith('/')) {
                    return window.location.origin + pfpUrl;
                }
                return pfpUrl;
            }
            return window.IdentityDirectory.getAvatarSvg(name, bgColor);
        }
        window.getLocalInitialsAvatar = getLocalInitialsAvatar;
        window.getAvatarUrl = getAvatarUrl;

        // ── Render helpers ────────────────────────────────────────────────────────────
        function getScreenShareLabel(identity, name) {
            const localId = window.room?.localParticipant?.identity
                ? String(window.room.localParticipant.identity)
                : String(window.meetingConfig?.currentUserId || window.currentUserId || '');
            const cleanId = String(identity || '').replace(/^(screen|video-box)-/, '');
            const isSelf = (cleanId === localId) || (cleanId === 'local-screen') || (cleanId === 'local') || (window.room && cleanId === String(window.room.localParticipant.identity));
            return isSelf ? 'Your Screen' : `${name || cleanId}'s Screen`;
        }

        function getOrCreateBox(identity, displayName, isLocal) {
            const key = String(identity);
            let box = document.getElementById(`video-box-${key}`);
            if (box) {
                window.IdentityDirectory.syncCardDOM(key);
                return box;
            }

            const user = window.IdentityDirectory.resolve(key, displayName);

            box = document.createElement('div');
            box.id = `video-box-${key}`;
            box.className = 'video-box cam-off';
            box.dataset.identity = key;
            box.dataset.userId = key;
            box.style.cursor = 'pointer';

            box.onclick = () => {
                if (box.parentElement.id !== 'mainVideoArea') {
                    const mainArea = document.getElementById('mainVideoArea');
                    if (mainArea.children.length > 0) {
                        const currentMain = mainArea.children[0];
                        currentMain.classList.remove('main-presents');
                        const v = currentMain.querySelector('video');
                        if (v) {
                            v.style.objectFit = 'cover';
                            v.style.transform = (window.room && currentMain.dataset.identity === window.room.localParticipant.identity) ? 'scaleX(-1)' : 'none';
                        }
                        document.getElementById('sidebarVideoArea').appendChild(currentMain);
                    }
                    moveToMain(box, user.displayName, key === 'local-screen');
                }
            };

            const nameTag = document.createElement('div');
            nameTag.className = 'video-nametag';
            nameTag.textContent = isLocal ? 'You' : user.displayName;
            box.appendChild(nameTag);

            const overlay = document.createElement('div');
            overlay.className = 'video-avatar-overlay';
            overlay.id = `avatar-overlay-${key}`;

            const fallbackSvg = window.IdentityDirectory.getAvatarSvg(user.displayName, user.color);
            const initialSrc = user.pfp || fallbackSvg;

            overlay.innerHTML = `
        <div class="video-avatar-wrapper">
            <img class="video-avatar-img" src="${initialSrc}" alt="${user.displayName}" onerror="this.onerror=null; this.src='${fallbackSvg}';">
        </div>
    `;
            box.appendChild(overlay);

            if (isLocal) {
                box.classList.toggle('cam-off', !window.isCameraOn);
            }

            const micBadge = document.createElement('div');
            micBadge.className = 'video-card-status-badge';
            micBadge.id = `mic-badge-${key}`;
            micBadge.title = 'Microphone muted';
            micBadge.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"/><path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`;
            box.appendChild(micBadge);

            document.getElementById('sidebarVideoArea').appendChild(box);
            updateLayout();
            updateParticipantsList();

            // Trigger preload sync
            window.IdentityDirectory.syncCardDOM(key);

            return box;
        }

        function updateParticipantMetadataUI(participant, metadata) {
            let pObj = null;
            let metaStr = null;

            if (participant && typeof participant === 'object' && participant.identity) {
                pObj = participant;
                metaStr = metadata || participant.metadata;
            } else if (metadata && typeof metadata === 'object' && metadata.identity) {
                pObj = metadata;
                metaStr = typeof participant === 'string' ? participant : pObj.metadata;
            } else if (typeof participant === 'string' || typeof participant === 'number') {
                pObj = getRemoteParticipant(participant);
                metaStr = pObj?.metadata;
            }

            const identity = pObj ? String(pObj.identity) : String(participant);
            if (!identity || identity === 'undefined') return;

            if (pObj) {
                window._remoteParticipantsRegistry.set(identity, pObj);
            }

            const rawMeta = metaStr || pObj?.metadata;
            if (rawMeta) {
                try {
                    const meta = typeof rawMeta === 'string' ? JSON.parse(rawMeta) : rawMeta;
                    window.IdentityDirectory.register(identity, meta);
                } catch (e) { }
            }

            window.IdentityDirectory.syncCardDOM(identity);
        }

        function renderLocalParticipant() {
            const lp = window.room ? window.room.localParticipant : null;
            const identity = lp ? String(lp.identity) : String(currentUserId);
            if (!identity || identity === 'undefined') return;

            // Clean up pre-connect stale box if identity transitioned
            if (lp && String(currentUserId) !== String(lp.identity)) {
                const staleBox = document.getElementById(`video-box-${currentUserId}`);
                if (staleBox && staleBox.id !== `video-box-${identity}`) {
                    staleBox.remove();
                }
            }

            const box = getOrCreateBox(identity, window.meetingConfig?.currentDisplayName || currentUsername, true);

            if (box) {
                box.classList.toggle('cam-off', !window.isCameraOn);
                box.classList.toggle('muted', !window.isMicOn);
            }
            if (!lp) return;

            // Attach camera track if already published
            const pubs = lp.videoTrackPublications || lp.tracks;
            if (pubs) {
                pubs.forEach(pub => {
                    const isCam = pub.source === 'camera' || (typeof Track !== 'undefined' && pub.source === Track?.Source?.Camera);
                    if (isCam) {
                        const targetTrack = pub.track || pub.videoTrack;
                        if (targetTrack) {
                            attachTrackToBox(targetTrack, box, true);
                            box.classList.remove('cam-off');
                        } else if (pub.setSubscribed) {
                            const checkInitialTrack = setInterval(() => {
                                if (pub.track) {
                                    attachTrackToBox(pub.track, box, true);
                                    box.classList.remove('cam-off');
                                    clearInterval(checkInitialTrack);
                                }
                            }, 200);
                            setTimeout(() => clearInterval(checkInitialTrack), 10000);
                        }
                    }
                });
            }

            // Listen for future local track publications
            if (!lp._customTrackSubscribed) {
                lp._customTrackSubscribed = true;
                lp.on(window.LiveKitBundle.ParticipantEvent.LocalTrackPublished || 'localTrackPublished', pub => {
                    console.log('Local track published:', pub.source, pub.trackSid);
                    const liveIdentity = window.room?.localParticipant?.identity ? String(window.room.localParticipant.identity) : String(currentUserId);
                    const currentBox = getOrCreateBox(liveIdentity, window.meetingConfig?.currentDisplayName || currentUsername, true);

                    const isScreen = pub.source === 'screen_share' || pub.source === 'screen-share' || (typeof Track !== 'undefined' && pub.source === Track?.Source?.ScreenShare);
                    const isCam = pub.source === 'camera' || (typeof Track !== 'undefined' && pub.source === Track?.Source?.Camera);

                    if (isScreen) {
                        if (pub.track) showLocalScreenShare(pub.track);
                    } else if (isCam) {
                        if (pub.track) {
                            attachTrackToBox(pub.track, currentBox, true);
                            currentBox.classList.remove('cam-off');
                        } else {
                            const checkTrack = setInterval(() => {
                                if (pub.track) {
                                    attachTrackToBox(pub.track, currentBox, true);
                                    currentBox.classList.remove('cam-off');
                                    clearInterval(checkTrack);
                                }
                            }, 100);
                            setTimeout(() => clearInterval(checkTrack), 5000);
                        }
                    }

                    // Package and send A/V sync metadata to peers
                    if (window.LipSyncManager) {
                        window.LipSyncManager.makePackageAndSend();
                    }
                });
            }
        }

        function attachTrackToBox(track, box, isLocal) {
            if (!track || !box) return;
            console.log(`Attaching ${track.kind} track to ${box.id} (Local: ${isLocal}, Source: ${track.source})`);

            const existing = box.querySelector(`[data-kind="${track.kind}"], video, audio`);
            if (existing) {
                try {
                    track.detach(existing);
                } catch (e) { }
                existing.remove();
            }

            const el = track.attach();
            el.dataset.kind = track.kind;
            el.dataset.source = track.source;

            const isVideo = track.kind === 'video' || (typeof Track !== 'undefined' && track.kind === Track?.Kind?.Video);
            const isScreen = track.source === 'screen_share' || track.source === 'screen-share' || (typeof Track !== 'undefined' && track.source === Track?.Source?.ScreenShare);

            if (isVideo) {
                el.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';

                const isIpCam = track.name === 'camera' && currentVideoSource === 'ip';
                if (isLocal && !isIpCam && !isScreen) {
                    el.style.transform = 'scaleX(-1)';
                }

                el.muted = true;
                el.autoplay = true;
                el.playsInline = true;

                if (isLocal) {
                    el.id = 'localVideo';
                    el.dataset.local = 'true';
                }

                if (track.mediaStreamTrack && !el.srcObject) {
                    el.srcObject = new MediaStream([track.mediaStreamTrack]);
                }

                box.insertBefore(el, box.querySelector('.video-nametag'));

                if (!isScreen) {
                    box.classList.remove('cam-off');
                }

                // Force playback on local media stream element to prevent WebRTC black frame zero freeze
                try {
                    const playPromise = el.play();
                    if (playPromise !== undefined) {
                        playPromise.catch(err => {
                            console.debug('Local video autoplay play catch:', err);
                        });
                    }
                } catch (err) { }
            }
        }

        function detachTrackFromBox(track, box) {
            track.detach().forEach(el => el.remove());
        }

        // ── Local screen share preview ────────────────────────────────────────────────
        function showLocalScreenShare(track) {
            console.log('Rendering local screen share UI...');
            // Create a dedicated screen-share box for the presenter
            let box = document.getElementById('local-screen-box');
            if (!box) {
                box = document.createElement('div');
                box.id = 'local-screen-box';
                box.className = 'video-box screen-share-active sharing-screen';
                box.dataset.identity = 'local-screen';

                // Screen share primary stage badge (Single Top-Left Badge)
                const shareBadge = document.createElement('div');
                shareBadge.className = 'screen-share-indicator-badge';
                shareBadge.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg> Your Screen`;
                box.appendChild(shareBadge);

                document.getElementById('sidebarVideoArea').appendChild(box);
            }

            // Clear existing video elements in the box
            box.querySelectorAll('video').forEach(v => v.remove());

            const el = track.attach();
            el.dataset.kind = 'video';
            el.style.cssText = 'width:100%;height:100%;object-fit:contain;display:block;background:#000;';
            el.muted = true;
            el.autoplay = true;
            el.playsInline = true;
            box.insertBefore(el, box.querySelector('.video-nametag'));

            // Add stop button overlay (Zoom-style top floating banner pill)
            let stopBtn = box.querySelector('.screen-stop-btn');
            if (!stopBtn) {
                stopBtn = document.createElement('button');
                stopBtn.className = 'screen-stop-btn';
                stopBtn.textContent = 'Stop Sharing';
                stopBtn.style.cssText = `position:absolute;top:8px;left:50%;transform:translateX(-50%);
            background:rgba(239,68,68,0.85);color:#fff;border:1px solid rgba(255,255,255,0.2);border-radius:12px;
            padding:3px 12px;font-size:11px;font-weight:600;cursor:pointer;z-index:30;
            box-shadow:0 2px 10px rgba(0,0,0,0.4);backdrop-filter:blur(8px);letter-spacing:0.3px;`;
                stopBtn.onclick = stopScreenShare;
                box.appendChild(stopBtn);
            }

            // Add presenting indicator to local camera card
            const localIdentity = window.room?.localParticipant?.identity ? String(window.room.localParticipant.identity) : String(currentUserId);
            const localCamBox = document.getElementById(`video-box-${localIdentity}`);
            if (localCamBox) {
                localCamBox.classList.add('is-presenting');
                if (!localCamBox.querySelector('.presenting-badge')) {
                    const pb = document.createElement('div');
                    pb.className = 'presenting-badge';
                    pb.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg> Presenting`;
                    localCamBox.appendChild(pb);
                }
            }

            moveToMain(box, 'Your Screen', true);
        }

        function hideLocalScreenShare() {
            const box = document.getElementById('local-screen-box');
            if (box) box.remove();
            clearMain();

            const localIdentity = window.room ? String(window.room.localParticipant.identity) : String(currentUserId);
            let camBox = document.getElementById(`video-box-${localIdentity}`);

            if (!camBox) {
                console.warn('hideLocalScreenShare: camera box missing, recreating via renderLocalParticipant');
                renderLocalParticipant();
                camBox = document.getElementById(`video-box-${localIdentity}`);
            }

            if (camBox) {
                camBox.classList.remove('main-presents');
                camBox.classList.remove('is-presenting');
                camBox.querySelector('.presenting-badge')?.remove();
                const sidebar = document.getElementById('sidebarVideoArea');
                if (sidebar && camBox.parentElement !== sidebar) {
                    sidebar.appendChild(camBox);
                }
                const v = camBox.querySelector('video');
                if (v) { v.style.objectFit = 'cover'; v.style.transform = 'scaleX(-1)'; }
                camBox.classList.toggle('cam-off', !window.isCameraOn);
            }
            updateLayout();
        }

        // ── Participant events ────────────────────────────────────────────────────────
        function onParticipantConnected(participant) {
            if (!participant || !participant.identity) return;

            console.log('Participant joined:', participant.identity);
            // Register in our manual registry
            window._remoteParticipantsRegistry.set(String(participant.identity), participant);
            getOrCreateBox(participant.identity, participant.name || participant.identity, false);
            updateParticipantMetadataUI(participant);
            updateParticipantsList();
            updateParticipantCount();

            // Listen for metadata changes directly on participant instance
            if (typeof participant.on === 'function') {
                participant.on('participantMetadataChanged', () => {
                    updateParticipantMetadataUI(participant);
                    updateParticipantsList();
                });
            }

            // Subscribe to any already-published tracks
            if (participant && participant.trackPublications && typeof participant.trackPublications.forEach === 'function') {
                participant.trackPublications.forEach(pub => {
                    if (pub.isSubscribed && pub.track) {
                        onTrackSubscribed(pub.track, pub, participant);
                    }
                });
            }

            // Transmit A/V sync package to newly joined peer and attempt early sync
            if (window.LipSyncManager) {
                window.LipSyncManager.makePackageAndSend();
                window.LipSyncManager.synchronizeParticipant(participant.identity);
            }
        }

        function onParticipantDisconnected(participant) {
            if (!participant || !participant.identity) return;
            console.log('Participant left:', participant.identity);
            // Remove from manual registry
            window._remoteParticipantsRegistry.delete(participant.identity);
            const box = document.getElementById(`video-box-${participant.identity}`);
            if (box) box.remove();
            const audioEl = document.querySelectorAll(`[id^="audio-${participant.identity}"]`);
            audioEl.forEach(el => el.remove());
            updateParticipantsList();
            updateParticipantCount();
            updateLayout();
        }

        function onTrackSubscribed(track, publication, participant) {
            if (!participant?.identity) return;

            // Never process our own tracks — handled by renderLocalParticipant
            if (window.room?.localParticipant?.identity === participant.identity) return;

            // ── Visibility permission check (teacher controls what students can see) ────
            const source = publication?.source || track?.source || '';
            if (!isHost && userType === 'student' && participant.identity === hostId) {
                if (track.kind === 'video') {
                    const isScreenSrc = source === 'screen_share' || source === 'screen-share'
                        || (typeof Track !== 'undefined' && source === Track.Source.ScreenShare);
                    if (!isScreenSrc && window.studentCanViewCamera === false) {
                        console.log('Permission: skipping host camera (studentCanViewCamera=false)');
                        return;
                    }
                    if (isScreenSrc && window.studentCanViewScreenshare === false) {
                        console.log('Permission: skipping host screenshare (studentCanViewScreenshare=false)');
                        return;
                    }
                }
            }

            // ── Delegate to TrackManager (handles dedup + correct box selection) ────────
            window.TrackManager.attach(track, publication, participant);
        }

        function onTrackUnsubscribed(track, publication, participant) {
            if (!participant?.identity) return;
            // Delegate to TrackManager — it knows which box to remove and cleans up correctly
            window.TrackManager.detach(track, publication, participant);
        }

        function onTrackMuted(publication, participant) {
            const box = document.getElementById(`video-box-${participant.identity}`);
            if (!box) return;
            if (publication.kind === Track.Kind.Video) box.classList.add('cam-off');
            if (publication.kind === Track.Kind.Audio) box.classList.add('muted');
        }

        function onTrackUnmuted(publication, participant) {
            const box = document.getElementById(`video-box-${participant.identity}`);
            if (!box) return;
            if (publication.kind === Track.Kind.Video) box.classList.remove('cam-off');
            if (publication.kind === Track.Kind.Audio) box.classList.remove('muted');
        }

        function onActiveSpeakersChanged(speakers) {
            // Clear all speaking indicators
            document.querySelectorAll('.video-box.speaking').forEach(b => b.classList.remove('speaking'));
            speakers.forEach(p => {
                const box = document.getElementById(`video-box-${p.identity}`);
                if (box) box.classList.add('speaking');
            });
        }

        function onDataReceived(payload, participant) {
            try {
                const msg = JSON.parse(new TextDecoder().decode(payload));
                if (msg.type === 'meeting_sleeping') {
                    isSleeping = true;
                    showNotification('Meeting has been put to sleep by the host', 'warning');
                } else if (msg.type === 'meeting_unfrozen') {
                    isSleeping = false;
                    showNotification('Meeting is now active', 'success');
                } else if (msg.type === 'chat_permission_update') {
                    window.allowChat = msg.allow_chat;
                    updateChatPermissionUI(msg.allow_chat);
                } else if (msg.type === 'start_meeting_quiz' || msg.type === 'quiz_started') {
                    if (msg.quiz) {
                        try { sessionStorage.setItem(`active_live_quiz_${meetingCode}`, JSON.stringify(msg.quiz)); } catch (e) { }
                        if (typeof showQuizToggleButton === 'function') showQuizToggleButton(true);
                        if (!isHost) {
                            showNotification('⚡ Live Classroom Quiz Started: ' + msg.quiz.title, 'warning');
                            startLiveMeetingQuiz(msg.quiz);
                        } else {
                            openTeacherQuizMonitor(msg.quiz);
                        }
                    }
                } else if (msg.type === 'teacher_ended_quiz' || msg.type === 'teacher_left_quiz_ended') {
                    try { sessionStorage.removeItem(`active_live_quiz_${meetingCode}`); } catch (e) { }
                    if (typeof showQuizToggleButton === 'function') showQuizToggleButton(false);
                    if (!isHost) {
                        showNotification('🛑 Teacher ended the quiz. Your quiz progress has been automatically saved and submitted.', 'warning');
                        if (isQuizActive) submitQuizAnswers(false);
                    }
                } else if (msg.type === 'quiz_tab_switch_warning' || msg.type === 'quiz_copy_warning' || msg.type === 'quiz_submitted' || msg.type === 'quiz_student_started') {
                    if (participant && participant.identity) {
                        if (!msg.student_id) msg.student_id = String(participant.identity);
                        if (!msg.student_name && participant.name) msg.student_name = participant.name;
                    }
                    if (isHost && typeof handleTeacherQuizEvent === 'function') {
                        handleTeacherQuizEvent(msg);
                    }
                } else if (msg.type === 'av_sync_package') {
                    if (window.LipSyncManager) {
                        window.LipSyncManager.unpackPackage(msg.package || msg);
                    }
                }
            } catch (e) { console.warn('Data parse error:', e); }
        }

        function onDisconnected() {
            showNotification('Disconnected from meeting', 'error');
            if (window.TrackManager) {
                window.TrackManager.clear();
            }
            if (window.LipSyncManager) {
                window.LipSyncManager.stop();
            }
        }

        function onConnectionStateChanged(state) {
            console.log('Connection state:', state);
        }

        // ── Signaling Handlers ────────────────────────────────────────────────────────
        function handleSignalingMessage(data) {
            switch (data.type) {
                case 'av_sync_package':
                    if (window.LipSyncManager && (data.package || data)) {
                        window.LipSyncManager.unpackPackage(data.package || data);
                    }
                    break;
                case 'chat':
                    appendChatMessage(data.username, data.message, data.user_id == currentUserId, data.display_name, data.pfp_url);
                    break;
                case 'quiz_started':
                case 'start_meeting_quiz':
                    if (data.quiz) {
                        try { sessionStorage.setItem(`active_live_quiz_${meetingCode}`, JSON.stringify(data.quiz)); } catch (e) { }
                        if (typeof showQuizToggleButton === 'function') showQuizToggleButton(true);
                        if (!isHost) {
                            showNotification('⚡ Live Classroom Quiz Started: ' + data.quiz.title, 'warning');
                            startLiveMeetingQuiz(data.quiz);
                        } else {
                            openTeacherQuizMonitor(data.quiz);
                        }
                    }
                    break;
                case 'quiz_submitted':
                case 'quiz_tab_switch_warning':
                case 'quiz_copy_warning':
                case 'quiz_student_started':
                    if (isHost && typeof handleTeacherQuizEvent === 'function') {
                        handleTeacherQuizEvent(data);
                    }
                    break;
                case 'teacher_ended_quiz':
                case 'teacher_left_quiz_ended':
                    try { sessionStorage.removeItem(`active_live_quiz_${meetingCode}`); } catch (e) { }
                    if (typeof showQuizToggleButton === 'function') showQuizToggleButton(false);
                    if (!isHost) {
                        showNotification('🛑 Teacher ended the quiz. Your quiz progress has been automatically saved and submitted.', 'warning');
                        if (isQuizActive) submitQuizAnswers(false);
                    }
                    break;
                case 'kick_user':
                    if (data.user_id == currentUserId) {
                        alert(data.message);
                        leaveMeeting();
                    } else {
                        showNotification(`User kicked: ${data.user_id}`, 'info');
                    }
                    break;
                case 'time_limit_expired_prompt':
                    if (window.isHost && !window.isExtended) {
                        showTimeLimitModal();
                    }
                    break;
                case 'meeting_continued':
                    window.isExtended = true;
                    hideTimeLimitModal();
                    showNotification(data.message || 'Meeting extended by host.', 'info');
                    break;
                case 'meeting_ended':
                    hideTimeLimitModal();
                    showNotification(data.message || 'The meeting has ended.', 'warning');
                    setTimeout(() => {
                        leaveMeeting();
                    }, 1200);
                    break;
                case 'recording_started':
                    {
                        const badge = document.getElementById('recordingIndicator');
                        if (badge) badge.style.display = 'flex';
                        showNotification(data.message || 'Meeting is being recorded by host.', 'info');
                    }
                    break;
                case 'recording_stopped':
                    {
                        const badge = document.getElementById('recordingIndicator');
                        if (badge) badge.style.display = 'none';
                        showNotification(data.message || 'Meeting recording stopped.', 'info');
                    }
                    break;
                case 'global_control_update':
                    if (data.control_type === 'student_can_view_camera') {
                        window.studentCanViewCamera = data.value;
                        showNotification(data.message, 'info');
                        updateTeacherTrackSubscription();
                    } else if (data.control_type === 'student_can_view_screenshare') {
                        window.studentCanViewScreenshare = data.value;
                        showNotification(data.message, 'info');
                        updateTeacherTrackSubscription();
                    } else if (data.control_type === 'allow_chat') {
                        window.allowChat = data.value;
                        updateChatPermissionUI(data.value);
                        showNotification(data.message || (data.value ? 'Chat enabled for everyone' : 'Chat limited to host only'), 'info');
                    }
                    break;
                case 'start_meeting_quiz':
                    if (data.quiz) {
                        startLiveMeetingQuiz(data.quiz);
                        showNotification('Teacher started a live meeting quiz!', 'info');
                    }
                    break;
                case 'quiz_tab_switch_warning':
                    if (isHost) {
                        displayTeacherQuizTabAlert(data);
                    }
                    break;
            }
        }

        // ── Layout ────────────────────────────────────────────────────────────────────
        function moveToMain(box, label, isScreenShare) {
            const mainArea = document.getElementById('mainVideoArea');
            const sidebarArea = document.getElementById('sidebarVideoArea');
            const container = document.getElementById('videoGridContainer');
            container.className = 'video-grid-container sidebar-view';

            if (mainArea.children.length > 0) {
                const currentMain = mainArea.children[0];
                currentMain.classList.remove('main-presents');
                const v = currentMain.querySelector('video');
                if (v) {
                    const isScreen = currentMain.dataset.identity === 'local-screen' || String(currentMain.dataset.identity).startsWith('screen-');
                    v.style.objectFit = isScreen ? 'contain' : 'cover';
                    v.style.objectPosition = isScreen ? 'center' : 'center 35%';
                    const isLocalCamera = window.room && currentMain.dataset.identity === String(window.room.localParticipant.identity);
                    if (isLocalCamera && !isScreen) {
                        v.style.transform = 'scaleX(-1)';
                    } else {
                        v.style.transform = 'none';
                    }
                }
                if (sidebarArea && currentMain.parentElement !== sidebarArea) {
                    sidebarArea.appendChild(currentMain);
                }
            }

            box.classList.add('main-presents');
            mainArea.innerHTML = '';
            mainArea.appendChild(box);

            const tag = box.querySelector('.video-nametag');
            if (tag && label && !box.id.includes('screen')) {
                tag.textContent = label;
            }

            const v = box.querySelector('video');
            if (v) {
                if (isScreenShare) {
                    v.style.objectFit = 'contain';
                    v.style.objectPosition = 'center';
                    v.style.transform = 'none';
                } else {
                    v.style.objectFit = 'cover';
                    v.style.objectPosition = 'center 35%';
                }
            }
        }

        function clearMain() {
            const mainArea = document.getElementById('mainVideoArea');
            const sidebarArea = document.getElementById('sidebarVideoArea');
            const container = document.getElementById('videoGridContainer');

            while (mainArea.children.length > 0) {
                const child = mainArea.children[0];
                child.classList.remove('main-presents');
                const v = child.querySelector('video');
                if (v) {
                    v.style.objectFit = 'cover';
                    const isLocalCamera = window.room && child.dataset.identity === String(window.room.localParticipant.identity);
                    const isLocalScreen = child.dataset.identity === 'local-screen';
                    if (isLocalCamera && !isLocalScreen) {
                        v.style.transform = 'scaleX(-1)';
                    } else {
                        v.style.transform = 'none';
                    }
                }
                if (sidebarArea) sidebarArea.appendChild(child);
            }

            container.className = 'video-grid-container grid-view count-' + getAllBoxes().length;
        }

        function getAllBoxes() {
            return Array.from(document.querySelectorAll('.video-box'));
        }

        window.currentGridPage = 1;
        window.gridPageSize = 25;

        function changeGridPage(direction) {
            window.currentGridPage += direction;
            updateLayout();
        }

        function updateGridPagination() {
            const paginationWidget = document.getElementById('gridPaginationControls');
            const prevBtn = document.getElementById('prevPageBtn');
            const nextBtn = document.getElementById('nextPageBtn');
            const indicator = document.getElementById('pageIndicator');
            if (!paginationWidget) return;

            const sidebar = document.getElementById('sidebarVideoArea');
            if (!sidebar) return;
            const boxes = Array.from(sidebar.children).filter(el => el.classList.contains('video-box'));
            const totalBoxes = boxes.length;
            const pageSize = window.gridPageSize || 25;
            const totalPages = Math.max(1, Math.ceil(totalBoxes / pageSize));

            if (window.currentGridPage > totalPages) window.currentGridPage = totalPages;
            if (window.currentGridPage < 1) window.currentGridPage = 1;

            if (totalBoxes > pageSize) {
                paginationWidget.style.display = 'flex';
                if (indicator) indicator.textContent = `${window.currentGridPage} / ${totalPages}`;
                if (prevBtn) prevBtn.disabled = (window.currentGridPage <= 1);
                if (nextBtn) nextBtn.disabled = (window.currentGridPage >= totalPages);

                const startIndex = (window.currentGridPage - 1) * pageSize;
                const endIndex = startIndex + pageSize;

                boxes.forEach((box, index) => {
                    if (index >= startIndex && index < endIndex) {
                        box.style.display = '';
                    } else {
                        box.style.display = 'none';
                    }
                });
            } else {
                paginationWidget.style.display = 'none';
                boxes.forEach(box => {
                    box.style.display = '';
                });
            }
        }

        function updateLayout() {
            const boxes = getAllBoxes();
            const container = document.getElementById('videoGridContainer');
            const mainArea = document.getElementById('mainVideoArea');
            const sidebarArea = document.getElementById('sidebarVideoArea');
            if (!container || !mainArea) return;

            // Force sidebar view
            container.className = 'video-grid-container sidebar-view';

            // Content-aware: tag sidebar with participant count
            if (sidebarArea) {
                sidebarArea.dataset.count = sidebarArea.children.length;
            }

            // If main area is empty, pick a video to enlarge
            if (mainArea.children.length === 0 && boxes.length > 0) {
                // Prioritize remote participants over local camera
                const localIdentity = window.room?.localParticipant?.identity ? String(window.room.localParticipant.identity) : String(currentUserId);
                const remoteBox = boxes.find(b => String(b.dataset.identity) !== localIdentity && b.dataset.identity !== 'local-screen');
                const targetBox = remoteBox || boxes[0];
                const isScreenShare = targetBox.dataset.identity === 'local-screen';
                const label = targetBox.querySelector('.video-nametag') ? targetBox.querySelector('.video-nametag').textContent : '';
                moveToMain(targetBox, label, isScreenShare);
            }

            updateParticipantCount();
            updateGridPagination();
        }

        // ── Controls ──────────────────────────────────────────────────────────────────
        async function toggleMic() {
            try {
                isMicOn = !isMicOn;
                if (window.room && window.room.localParticipant) {
                    await window.room.localParticipant.setMicrophoneEnabled(isMicOn, {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    });
                }
                const btn = document.getElementById('micBtn');
                const label = document.getElementById('micLabel');
                if (btn) {
                    btn.classList.toggle('off', !isMicOn);
                    const micOnIcon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>';
                    const micOffIcon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"/><path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>';
                    btn.innerHTML = isMicOn ? micOnIcon : micOffIcon;
                }
                if (label) label.textContent = isMicOn ? 'Unmuted' : 'Muted';
                showNotification(isMicOn ? 'Microphone unmuted.' : 'Microphone muted.', 'info');
                if (window.LipSyncManager) {
                    window.LipSyncManager.makePackageAndSend();
                }
            } catch (e) {
                console.error('Mic toggle error:', e);
                isMicOn = !isMicOn; // Revert state
                if (e.name === 'NotFoundError' || e.name === 'DevicesNotFoundError') {
                    showNotification('No microphone found on this device.', 'warning');
                } else if (e.name === 'NotAllowedError' || e.name === 'PermissionDeniedError') {
                    showNotification('Microphone access denied by browser permissions.', 'error');
                } else {
                    showNotification('Could not access microphone: ' + (e.message || e.name), 'error');
                }
            }
        }

        async function toggleCamera() {
            try {
                isCameraOn = !isCameraOn;

                // Handle IP camera source
                if (currentVideoSource === 'ip' && !isCameraOn) {
                    await stopIpCameraStream();
                } else {
                    if (window.room) await window.room.localParticipant.setCameraEnabled(isCameraOn);
                }

                const btn = document.getElementById('camBtn');
                const label = document.getElementById('camLabel');
                btn.classList.toggle('off', !isCameraOn);
                const camOnIcon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>';
                const camOffIcon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="1" y1="1" x2="23" y2="23"/><path d="M16 16v1a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2m5.66 0H14a2 2 0 0 1 2 2v3.34l1 1L23 7v10"/></svg>';
                btn.innerHTML = isCameraOn ? camOnIcon : camOffIcon;
                if (label) label.textContent = isCameraOn ? 'Cam On' : 'Cam Off';

                // Update UI
                const localBox = (window.room) ? document.getElementById(`video-box-${window.room.localParticipant.identity}`) : null;
                if (localBox) localBox.classList.toggle('cam-off', !isCameraOn);
                if (isCameraOn) renderLocalParticipant();
                if (window.LipSyncManager) {
                    window.LipSyncManager.makePackageAndSend();
                }
            } catch (e) {
                console.error('Camera toggle error:', e);
                isCameraOn = !isCameraOn; // Revert state
                if (e.name === 'NotFoundError' || e.name === 'DevicesNotFoundError') {
                    showNotification('No camera found on this device.', 'warning');
                } else if (e.name === 'NotAllowedError' || e.name === 'PermissionDeniedError') {
                    showNotification('Camera access denied.', 'error');
                } else {
                    showNotification('Could not access camera.', 'error');
                }
            }
        }

        async function toggleScreenShare() {
            if (!isScreenSharing) {
                try {
                    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
                        throw new Error("Screen sharing is not supported or blocked (check HTTPS/localhost).");
                    }

                    if (!window.room || !window.room.localParticipant) {
                        throw new Error("Not connected to meeting room.");
                    }

                    // Official LiveKit SDK method for screen sharing (with screen sound / audio support)
                    if (typeof window.room.localParticipant.setScreenShareEnabled === 'function') {
                        screenTrackPub = await window.room.localParticipant.setScreenShareEnabled(true, {
                            audio: true,
                            selfBrowserSurface: 'include',
                            surfaceSwitching: 'include',
                            systemAudio: 'include'
                        });
                    } else {
                        const createScreen = createLocalScreenTracks || (window.LiveKitBundle && window.LiveKitBundle.createLocalScreenTracks) || (window.LivekitClient && window.LivekitClient.createLocalScreenTracks);
                        if (typeof createScreen !== 'function') {
                            throw new Error("Screen share function not found in LiveKit SDK.");
                        }
                        const tracks = await createScreen({ audio: true });
                        const trackList = Array.isArray(tracks) ? tracks : [tracks];
                        for (const tr of trackList) {
                            const isAudio = tr.kind === 'audio';
                            const pub = await window.room.localParticipant.publishTrack(tr, {
                                name: isAudio ? 'screen_share_audio' : 'screen_share',
                                source: isAudio ? (Track?.Source?.ScreenShareAudio || 'screen_share_audio') : (Track?.Source?.ScreenShare || 'screen_share')
                            });
                            if (!isAudio) screenTrackPub = pub;
                        }
                    }

                    isScreenSharing = true;
                    document.getElementById('screenBtn').classList.add('active');

                    if (screenTrackPub && screenTrackPub.track) {
                        showLocalScreenShare(screenTrackPub.track);
                        const mediaTrack = screenTrackPub.track.mediaStreamTrack || screenTrackPub.track;
                        if (window.VideoQualityManager && mediaTrack) {
                            window.VideoQualityManager.optimizeScreenShareTrack(mediaTrack);
                        }
                        if (mediaTrack && mediaTrack.addEventListener) {
                            mediaTrack.addEventListener('ended', stopScreenShare);
                        }
                    }

                    showNotification('Screen sharing started with audio', 'info');
                } catch (e) {
                    console.error('Screen share error:', e);
                    let msg = e.message || 'Unknown error';
                    if (e.name === 'NotAllowedError') msg = "Permission denied by user.";
                    showNotification('Screen share failed: ' + msg, 'error');
                }
            } else {
                stopScreenShare();
            }
        }

        async function stopScreenShare() {
            if (!isScreenSharing) return;
            isScreenSharing = false;
            document.getElementById('screenBtn').classList.remove('active');
            if (window.room && window.room.localParticipant) {
                try {
                    await window.room.localParticipant.setScreenShareEnabled(false);
                } catch (err) {
                    console.warn('Error stopping screen share track:', err);
                }
                screenTrackPub = null;
            }

            // --- RESTORE CAMERA AFTER SCREENSHARE FOR HOST ---
            if (isHost && isCameraOn && window.room) {
                try {
                    await window.room.localParticipant.setCameraEnabled(true);
                    document.getElementById('camBtn').classList.remove('off');
                } catch (err) {
                    console.warn('Failed to restore camera after screenshare:', err);
                }
            }

            hideLocalScreenShare();
            showNotification('Screen sharing stopped', 'info');
        }
