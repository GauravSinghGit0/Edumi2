        // ── Industry-Grade Identity & Avatar Architecture (Google Meet / Zoom pattern) ──
        window.IdentityDirectory = {
            _cache: new Map(),

            init(preloadJson) {
                if (preloadJson) {
                    try {
                        const data = typeof preloadJson === 'string' ? JSON.parse(preloadJson) : preloadJson;
                        Object.values(data).forEach(u => {
                            if (u && u.id) {
                                this.register(u.id, u);
                                if (u.username) this.register(u.username, u);
                            }
                        });
                    } catch (e) {
                        console.warn('Failed to parse preloaded user directory:', e);
                    }
                }
                if (window.meetingConfig.currentUserId) {
                    this.register(window.meetingConfig.currentUserId, {
                        id: String(window.meetingConfig.currentUserId),
                        username: window.meetingConfig.currentUsername,
                        display_name: window.meetingConfig.currentDisplayName,
                        pfp: window.meetingConfig.currentPfpUrl,
                        role: window.meetingConfig.isHost ? 'host' : 'student'
                    });
                }
            },

            getDeterministicColor(str) {
                let hash = 0;
                const clean = String(str || 'User').trim();
                for (let i = 0; i < clean.length; i++) {
                    hash = clean.charCodeAt(i) + ((hash << 5) - hash);
                }
                const h = Math.abs(hash) % 360;
                return `hsl(${h}, 62%, 42%)`;
            },

            register(identity, data = {}) {
                if (!identity) return null;
                const key = String(identity);
                const existing = this._cache.get(key) || {};

                let pfp = data.pfp || data.pfpUrl || data.pfp_url || existing.pfp || null;
                if (pfp && typeof pfp === 'string') {
                    pfp = pfp.trim();
                    if (pfp.startsWith('/')) pfp = window.location.origin + pfp;
                    if (pfp === '' || pfp === 'null' || pfp === 'undefined') pfp = null;
                }

                const displayName = data.displayName || data.display_name || data.name || existing.displayName || existing.username || key;
                const username = data.username || existing.username || key;
                const role = data.role || existing.role || (key === String(window.meetingConfig.hostId) ? 'host' : 'student');
                const color = existing.color || this.getDeterministicColor(username || displayName || key);

                const record = {
                    id: key,
                    username,
                    displayName,
                    pfp,
                    role,
                    color
                };

                this._cache.set(key, record);
                if (username && username !== key) {
                    this._cache.set(username, record);
                }

                return record;
            },

            resolve(identity, fallbackName = null) {
                if (!identity) {
                    return {
                        id: 'unknown',
                        displayName: fallbackName || 'User',
                        pfp: null,
                        color: '#8b5cf6',
                        role: 'student'
                    };
                }

                const key = String(identity);
                let record = this._cache.get(key);

                if ((!record || !record.pfp) && window.room) {
                    const p = (window.room.remoteParticipants ? window.room.remoteParticipants.get(key) : null) ||
                        (window.room.localParticipant && String(window.room.localParticipant.identity) === key ? window.room.localParticipant : null);
                    if (p && p.metadata) {
                        try {
                            const meta = typeof p.metadata === 'string' ? JSON.parse(p.metadata) : p.metadata;
                            if (meta && (meta.pfp || meta.display_name)) {
                                record = this.register(key, meta);
                            }
                        } catch (e) { }
                    }
                }

                if (!record) {
                    record = this.register(key, { displayName: fallbackName || key });
                }

                return record;
            },

            getAvatarSvg(name, bgColor) {
                const cleanName = (name || 'User').trim();
                const parts = cleanName.split(/\s+/).filter(Boolean);
                let initials = '';
                if (parts.length >= 2) {
                    initials = (parts[0][0] + parts[1][0]).toUpperCase();
                } else if (parts.length === 1 && parts[0].length >= 2) {
                    initials = parts[0].substring(0, 2).toUpperCase();
                } else if (parts.length === 1) {
                    initials = parts[0][0].toUpperCase();
                } else {
                    initials = '?';
                }
                const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">` +
                    `<rect width="128" height="128" rx="64" fill="${bgColor || '#8b5cf6'}"/>` +
                    `<text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" fill="#ffffff" ` +
                    `font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" ` +
                    `font-size="52" font-weight="600">${initials}</text>` +
                    `</svg>`;
                return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
            },

            syncCardDOM(identity) {
                if (!identity) return;
                const key = String(identity);
                const user = this.resolve(key);

                const box = document.getElementById(`video-box-${key}`);
                if (box) {
                    const img = box.querySelector('.video-avatar-img');
                    const fallbackSvg = this.getAvatarSvg(user.displayName, user.color);
                    const targetSrc = user.pfp || fallbackSvg;

                    if (img && img.getAttribute('src') !== targetSrc) {
                        if (user.pfp) {
                            const preload = new Image();
                            preload.onload = () => {
                                if (img) {
                                    img.src = user.pfp;
                                    img.onerror = () => { img.onerror = null; img.src = fallbackSvg; };
                                }
                            };
                            preload.onerror = () => {
                                if (img) {
                                    img.src = fallbackSvg;
                                }
                            };
                            preload.src = user.pfp;
                        } else {
                            img.src = fallbackSvg;
                        }
                    }

                    const nameTag = box.querySelector('.video-nametag');
                    if (nameTag && !nameTag.textContent.startsWith('💻')) {
                        const isLocal = window.room?.localParticipant?.identity === key || String(window.meetingConfig.currentUserId) === key;
                        nameTag.textContent = isLocal ? 'You' : user.displayName;
                    }
                }
            }
        };

        // Initialize preloaded user directory
        try {
            const _userDirEl = document.getElementById('user-directory-data');
            if (_userDirEl) {
                window.IdentityDirectory.init(_userDirEl.textContent.trim());
            }
        } catch (e) { }

        // Initialize Unified Quality Control early
        try {
            if (window.VideoQualityManager) {
                const _qContainer = document.getElementById('unifiedQualityControl') || document.getElementById('qualityWidgetContainer');
                if (_qContainer && !_qContainer.children.length) {
                    const _uqcUI = window.VideoQualityManager.createUnifiedQualityControl({
                        onQualityChange: (mode) => {
                            if (window.room) {
                                window.VideoQualityManager.applyQualityToLiveKit(window.room, mode);
                            }
                            showNotification(`Video quality set to ${mode.toUpperCase()}`, 'info');
                        }
                    });
                    _qContainer.appendChild(_uqcUI);
                }
            }
        } catch (e) {
            console.warn('Early quality control init warning:', e);
        }

        // Global shortcuts using window properties to prevent Turbo redeclaration errors
        window.meetingCode = window.meetingConfig.meetingCode;
        window.currentUserId = window.meetingConfig.currentUserId;
        window.currentUsername = window.meetingConfig.currentUsername;
        window.currentDisplayName = window.meetingConfig.currentDisplayName;
        window.currentPfpUrl = window.meetingConfig.currentPfpUrl;
        window.isHost = window.meetingConfig.isHost;
        window.userType = window.meetingConfig.userType;
        window.hostId = window.meetingConfig.hostId;
        window.TOKEN_URL = window.meetingConfig.TOKEN_URL;
        window.LEAVE_URL = window.meetingConfig.LEAVE_URL;
        window.SLEEP_URL = window.meetingConfig.SLEEP_URL;
        window.UNFREEZE_URL = window.meetingConfig.UNFREEZE_URL;
        window.AFTER_LEAVE = window.meetingConfig.AFTER_LEAVE;
        window.CSRF = window.meetingConfig.CSRF;
        window.studentCanViewCamera = window.meetingConfig.studentCanViewCamera;
        window.studentCanViewScreenshare = window.meetingConfig.studentCanViewScreenshare;

