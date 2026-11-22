        // ── Chat Permission & Quick Reactions ─────────────────────────────────────────
        async function toggleChatPermission() {
            if (!isHost) return;
            const newState = !window.allowChat;

            try {
                const res = await fetch(window.meetingConfig.globalControlUrl, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type: 'allow_chat', value: newState })
                });
                if (res.ok) {
                    window.allowChat = newState;
                    updateChatPermissionUI(newState);
                    if (window.room && window.room.localParticipant) {
                        const payload = JSON.stringify({ type: 'chat_permission_update', allow_chat: newState });
                        window.room.localParticipant.publishData(new TextEncoder().encode(payload), { reliable: true });
                    }
                    showNotification(newState ? 'Chat enabled for everyone' : 'Chat limited to host only', 'info');
                }
            } catch (err) {
                showNotification('Failed to update chat permission', 'error');
            }
        }

        function updateChatPermissionUI(allowed) {
            window.allowChat = allowed;

            const toggle = document.getElementById('chatPermSwitch');
            if (toggle) {
                toggle.classList.toggle('active', allowed);
                toggle.setAttribute('aria-checked', allowed ? 'true' : 'false');
            }

            const input = document.getElementById('chatInput');
            const sendBtn = document.getElementById('chatSendBtn');
            const statusBanner = document.getElementById('chatStatusBanner');
            const statusText = document.getElementById('chatStatusBannerText');

            if (!isHost) {
                if (!allowed) {
                    if (input) {
                        input.disabled = true;
                        input.value = '';
                        input.placeholder = 'Only the host can send messages';
                    }
                    if (sendBtn) {
                        sendBtn.disabled = true;
                        sendBtn.classList.remove('active');
                    }
                    if (statusBanner) {
                        statusBanner.style.display = 'flex';
                        if (statusText) statusText.textContent = 'Chat is limited to the host';
                    }
                } else {
                    if (input) {
                        input.disabled = false;
                        input.placeholder = 'Type a message here...';
                    }
                    if (statusBanner) {
                        statusBanner.style.display = 'none';
                    }
                }
            } else {
                if (input) {
                    input.disabled = false;
                    input.placeholder = 'Send a message to everyone...';
                }
                if (statusBanner) {
                    statusBanner.style.display = allowed ? 'none' : 'flex';
                    if (statusText) statusText.textContent = 'Chat is limited to you (Host)';
                }
            }
        }
        window.toggleChatPermission = toggleChatPermission;
        window.updateChatPermissionUI = updateChatPermissionUI;

        async function sendQuickReaction(emoji) {
            if (!window.allowChat && !isHost) {
                showNotification('Chat is limited to host', 'warning');
                return;
            }
            await sendChatMessage(emoji);
        }
        window.sendQuickReaction = sendQuickReaction;

        async function sendChatMessage(overrideText) {
            const input = document.getElementById('chatInput');
            const text = (typeof overrideText === 'string' ? overrideText : (input ? input.value : '')).trim();
            if (!text) return;

            if (!window.allowChat && !isHost) {
                showNotification('Chat is limited to host', 'warning');
                return;
            }

            if (!signalingWs || signalingWs.readyState !== WebSocket.OPEN) {
                showNotification('Chat connection not ready. Please wait.', 'warning');
                return;
            }

            if (input && typeof overrideText !== 'string') {
                input.value = '';
                const sendBtn = document.getElementById('chatSendBtn');
                if (sendBtn) {
                    sendBtn.classList.remove('active');
                    sendBtn.disabled = true;
                }
            }

            const payload = JSON.stringify({
                type: 'chat',
                message: text,
                timestamp: new Date().toISOString()
            });
            signalingWs.send(payload);
        }

        function appendChatMessage(username, text, isOwn, displayName, pfpUrl, userId) {
            const panel = document.getElementById('chatMessages');
            const emptyState = document.getElementById('chatEmptyState');
            if (emptyState) emptyState.remove();

            const uid = userId || username;
            const user = window.IdentityDirectory.resolve(uid, displayName || username);
            const fallbackSvg = window.IdentityDirectory.getAvatarSvg(user.displayName, user.color);
            const finalPfp = pfpUrl || user.pfp || fallbackSvg;
            const senderName = isOwn ? 'You' : user.displayName;
            const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const isParticipantHost = String(uid) === String(hostId) || user.role === 'host';

            // Sanitize and linkify text
            const escapedText = String(text || '')
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");

            // Auto-link URLs
            const urlPattern = /(\b(https?:\/\/|www\.)[^\s<]+)/gi;
            const formattedText = escapedText.replace(urlPattern, (url) => {
                const fullUrl = url.startsWith('http') ? url : 'https://' + url;
                return `<a href="${fullUrl}" target="_blank" rel="noopener noreferrer" class="chat-link">${url}</a>`;
            });

            const isNearBottom = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 70;

            const msgEl = document.createElement('div');
            msgEl.className = 'chat-msg-row' + (isOwn ? ' own' : '');

            if (isOwn) {
                msgEl.innerHTML = `
            <div class="chat-msg-content">
                <div class="chat-msg-meta">
                    <span class="chat-msg-time">${timeStr}</span>
                    <span class="chat-msg-author">You</span>
                </div>
                <div class="chat-msg-bubble">
                    ${formattedText}
                </div>
            </div>
        `;
            } else {
                msgEl.innerHTML = `
            <div class="chat-msg-avatar">
                <img src="${finalPfp}" alt="${senderName}" onerror="this.onerror=null; this.src='${fallbackSvg}';">
            </div>
            <div class="chat-msg-content">
                <div class="chat-msg-meta">
                    <span class="chat-msg-author">${senderName}</span>
                    ${isParticipantHost ? '<span class="chat-msg-role-badge">Host</span>' : ''}
                    <span class="chat-msg-time">${timeStr}</span>
                </div>
                <div class="chat-msg-bubble">
                    ${formattedText}
                </div>
            </div>
        `;
            }

            panel.appendChild(msgEl);

            if (isNearBottom || isOwn) {
                panel.scrollTop = panel.scrollHeight;
            }

            // Badge notification logic
            const sidebar = document.getElementById('meetSidebar');
            const chatPanel = document.getElementById('chatPanel');
            const isSidebarHidden = sidebar.style.display === 'none';
            const isChatPanelHidden = chatPanel.classList.contains('active') === false;

            if (!isOwn && (isSidebarHidden || isChatPanelHidden)) {
                unreadMessages++;
                const badge = document.getElementById('chatBadge');
                if (badge) {
                    badge.textContent = unreadMessages;
                    badge.style.display = 'inline-flex';
                }
                const moreBadge = document.getElementById('moreBadge');
                if (moreBadge) {
                    moreBadge.style.display = 'block';
                }
            }
        }

