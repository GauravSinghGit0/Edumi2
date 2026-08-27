/**
 * static/js/identity_sync.js
 * Centralized Identification System Client — Single Source of Truth (SSOT)
 * Listens for real-time WebSocket identity updates and dynamically updates active DOM components.
 */

(function() {
    'use strict';

    if (window.EdumiIdentity) {
        // Already initialized singleton — just trigger DOM update on current page
        if (window.EdumiIdentity.currentUser) {
            window.EdumiIdentity.updateDOMForUser(window.EdumiIdentity.currentUser);
        }
        return;
    }

    class IdentitySyncManager {
        constructor() {
            this.currentUser = null;
            this.listeners = new Set();
            this.boundSocket = null;
            this._handleMessage = this._handleMessage.bind(this);
            this.init();
        }

        init() {
            // Load initial identity from page meta or API
            this.fetchCurrentIdentity();
            this.bindWebSocketListener();

            // Re-apply DOM updates on Turbo navigation
            document.addEventListener('turbo:load', () => {
                if (this.currentUser) {
                    this.updateDOMForUser(this.currentUser);
                }
            });
            document.addEventListener('turbo:render', () => {
                if (this.currentUser) {
                    this.updateDOMForUser(this.currentUser);
                }
            });
        }

        async fetchCurrentIdentity() {
            try {
                const res = await fetch('/api/identity/me/', {
                    headers: { 'Accept': 'application/json' }
                });
                if (res.ok) {
                    const data = await res.json();
                    if (data.success && data.identity) {
                        this.currentUser = data.identity;
                        this.updateDOMForUser(this.currentUser);
                    }
                }
            } catch (err) {
                // Silently handle fetch error
            }
        }

        _handleMessage(event) {
            try {
                const payload = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
                const eventData = payload.data || payload;
                
                if (payload.type === 'identity_updated' || eventData.type === 'identity_updated') {
                    const updatedIdentity = eventData.identity;
                    if (updatedIdentity) {
                        this.onIdentityUpdated(updatedIdentity);
                    }
                }
            } catch (e) {
                // Non-JSON message, ignore
            }
        }

        bindWebSocketListener() {
            if (window.notificationSocket) {
                if (this.boundSocket !== window.notificationSocket) {
                    if (this.boundSocket) {
                        try { this.boundSocket.removeEventListener('message', this._handleMessage); } catch(_) {}
                    }
                    this.boundSocket = window.notificationSocket;
                    this.boundSocket.addEventListener('message', this._handleMessage);
                }
            } else {
                let attempts = 0;
                const interval = setInterval(() => {
                    attempts++;
                    if (window.notificationSocket) {
                        if (this.boundSocket !== window.notificationSocket) {
                            this.boundSocket = window.notificationSocket;
                            this.boundSocket.addEventListener('message', this._handleMessage);
                        }
                        clearInterval(interval);
                    } else if (attempts > 20) {
                        clearInterval(interval);
                    }
                }, 500);
            }
        }

        onIdentityUpdated(identity) {
            // Update local user if it matches current user
            if (this.currentUser && identity.user_id === this.currentUser.user_id) {
                this.currentUser = identity;
            }

            // Trigger DOM update for matching user elements
            this.updateDOMForUser(identity);

            // Notify custom JS listeners
            this.listeners.forEach(fn => {
                try { fn(identity); } catch(e) {}
            });
        }

        updateDOMForUser(identity) {
            if (!identity || !identity.user_id) return;

            const userId = identity.user_id;

            // Avatars
            document.querySelectorAll(`[data-identity-user="${userId}"][data-identity-field="avatar"], [data-identity-me][data-identity-field="avatar"]`).forEach(el => {
                if (el.tagName === 'IMG') {
                    el.src = identity.avatar_url;
                } else {
                    el.style.backgroundImage = `url('${identity.avatar_url}')`;
                }
            });

            // Display names
            document.querySelectorAll(`[data-identity-user="${userId}"][data-identity-field="display_name"], [data-identity-me][data-identity-field="display_name"]`).forEach(el => {
                el.textContent = identity.display_name;
            });

            // Role badges
            document.querySelectorAll(`[data-identity-user="${userId}"][data-identity-field="role"], [data-identity-me][data-identity-field="role"]`).forEach(el => {
                el.textContent = identity.role ? identity.role.toUpperCase() : '';
            });

            // Face biometric status badges
            document.querySelectorAll(`[data-identity-user="${userId}"][data-identity-field="face_status"], [data-identity-me][data-identity-field="face_status"]`).forEach(el => {
                if (identity.face_registered) {
                    el.classList.remove('status-unverified', 'text-gray-400');
                    el.classList.add('status-verified', 'text-green-500');
                    el.textContent = 'Face Verified';
                } else {
                    el.classList.remove('status-verified', 'text-green-500');
                    el.classList.add('status-unverified', 'text-gray-400');
                    el.textContent = 'Face Pending';
                }
            });
        }

        subscribe(callback) {
            if (typeof callback === 'function') {
                this.listeners.add(callback);
            }
        }
    }

    // Expose global identity manager instance
    window.EdumiIdentity = new IdentitySyncManager();
})();
