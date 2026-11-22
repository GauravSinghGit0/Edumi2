        // ── Sleep mode (host only) ────────────────────────────────────────────────────
        async function toggleSleepMode() {
            const url = isSleeping ? UNFREEZE_URL : SLEEP_URL;
            await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': CSRF } });

            // Broadcast to all via data channel
            const type = isSleeping ? 'meeting_unfrozen' : 'meeting_sleeping';
            const payload = JSON.stringify({ type });
            if (window.room && window.room.localParticipant) {
                await window.room.localParticipant.publishData(new TextEncoder().encode(payload), { reliable: true });
            }

            isSleeping = !isSleeping;
            const btn = document.getElementById('sleepBtn');
            if (btn) btn.classList.toggle('active', isSleeping);
        }

        // ── Teacher Controls ──────────────────────────────────────────────────────────
        async function toggleGlobalControl(type) {
            const btn = type === 'mute_all' ? document.getElementById('muteAllBtn') : document.getElementById('camOffAllBtn');
            const currentState = btn.classList.contains('active');
            const newState = !currentState;

            const res = await fetch(window.meetingConfig.globalControlUrl, {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
                body: JSON.stringify({ type, value: newState })
            });

            if (res.ok) {
                btn.classList.toggle('active', newState);
                showNotification(`Global ${type.replace('_', ' ')} ${newState ? 'Enabled' : 'Disabled'}`, 'success');
            }
        }

        async function kickUser(userId) {
            const confirmed = await EdumiPopup.danger({
                title: 'Kick Student',
                message: 'Are you sure you want to kick this student for 1 hour?',
                confirmText: 'Kick Student'
            });
            if (!confirmed) return;

            const url = window.meetingConfig.kickUrl.replace('0', userId);
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF }
            });

            if (res.ok) showNotification('Student kicked successfully', 'success');
        }

        async function unbanUser(userId) {
            const url = window.meetingConfig.revokeBanUrl.replace('0', userId);
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF }
            });

            if (res.ok) {
                showNotification('Student unbanned successfully', 'success');
                fetchBannedUsers();
            }
        }

        async function fetchBannedUsers() {
            if (!isHost) return;
            const res = await fetch(window.meetingConfig.bannedUsersUrl);
            const data = await res.json();
            const list = document.getElementById('bannedList');
            if (!list) return;

            list.innerHTML = '';
            if (data.banned && data.banned.length > 0) {
                data.banned.forEach(u => {
                    const pfp = getAvatarUrl(u.username, null, '#ef4444');
                    const fallback = getLocalInitialsAvatar(u.username, '#ef4444');
                    const item = document.createElement('div');
                    item.className = 'participant-item';
                    item.innerHTML = `
                <div class="participant-avatar"><img src="${pfp}" alt="${u.username}" onerror="this.onerror=null; this.src='${fallback}';"></div>
                <div class="participant-info">
                    <div class="participant-name"><span>${u.username}</span></div>
                    <div style="font-size:10px; color:#f87171; line-height: 1.2;">Banned until ${new Date(u.banned_until).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                </div>
                <div class="participant-actions">
                    <button class="participant-action-btn success" onclick="window.unbanUser('${u.id}')" title="Unban student" aria-label="Unban student">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                            <circle cx="8.5" cy="7" r="4"/>
                            <polyline points="17 11 19 13 23 9"/>
                        </svg>
                    </button>
                </div>`;
                    list.appendChild(item);
                });
            } else {
                list.innerHTML = '<p style="text-align:center; color:#64748b; font-size:11px; padding:12px; font-style:italic;">No banned students</p>';
            }
        }

        // Attach to window for Turbo/Inline events
        window.toggleMic = toggleMic;
        window.toggleCamera = toggleCamera;
        window.toggleScreenShare = toggleScreenShare;
        window.stopScreenShare = stopScreenShare;
        window.toggleCameraModal = toggleCameraModal;
        window.switchCameraSource = switchCameraSource;
        window.stopIpCameraStream = stopIpCameraStream;
        window.sendChatMessage = sendChatMessage;
        window.sendQuickReaction = sendQuickReaction;
        window.toggleChatPermission = toggleChatPermission;
        window.updateChatPermissionUI = updateChatPermissionUI;
        window.openKickModal = openKickModal;
        window.closeKickModal = closeKickModal;
        window.executeKickUser = executeKickUser;
        window.toggleSleepMode = toggleSleepMode;
        window.toggleGlobalControl = toggleGlobalControl;
        window.toggleStudentViewPermission = toggleStudentViewPermission;
        window.kickUser = kickUser;
        window.unbanUser = unbanUser;
        window.fetchBannedUsers = fetchBannedUsers;
        window.leaveMeeting = leaveMeeting;
        window.openSidebar = openSidebar;
        window.toggleSidebar = toggleSidebar;
        window.toggleMoreOptions = toggleMoreOptions;
        window.switchSidebarTab = switchSidebarTab;

        // ── Leave ─────────────────────────────────────────────────────────────────────
        async function leaveMeeting() {
            if (isHost && activeLiveQuiz && activeLiveQuiz.id) {
                broadcastQuizEvent({
                    type: 'teacher_left_quiz_ended',
                    quiz_id: activeLiveQuiz.id
                });
                if (window.signalingWs && window.signalingWs.readyState === WebSocket.OPEN) {
                    try {
                        window.signalingWs.send(JSON.stringify({
                            type: 'teacher_left_quiz_ended',
                            quiz_id: activeLiveQuiz.id
                        }));
                    } catch (_) { }
                }
                try { sessionStorage.removeItem(`active_live_quiz_${meetingCode}`); } catch (_) { }
            }
            if (room) await room.disconnect();
            await fetch(LEAVE_URL, { method: 'POST', headers: { 'X-CSRFToken': CSRF } });
            window.location.href = AFTER_LEAVE;
        }

        // ── Sidebar helpers & Draggable Resizer ───────────────────────────────────────
        function getSidebarWidth() {
            const s = document.getElementById('meetSidebar');
            if (!s) return 350;
            const w = parseFloat(s.style.width || window.getComputedStyle(s).width);
            return isNaN(w) || w <= 0 ? 350 : w;
        }

        function openSidebar(tab) {
            const s = document.getElementById('meetSidebar');
            if (s) s.style.display = 'flex';
            document.getElementById('meetMain').classList.add('sidebar-open');
            document.documentElement.style.setProperty('--face-badge-offset', (getSidebarWidth() + 24) + 'px');
            switchSidebarTab(tab);
            if (typeof updateLayout === 'function') updateLayout();
        }

        function toggleSidebar() {
            const s = document.getElementById('meetSidebar');
            const isOpen = s && s.style.display !== 'none';
            if (s) s.style.display = isOpen ? 'none' : 'flex';
            document.getElementById('meetMain').classList.toggle('sidebar-open', !isOpen);
            document.documentElement.style.setProperty('--face-badge-offset', !isOpen ? (getSidebarWidth() + 24) + 'px' : '24px');
            if (typeof updateLayout === 'function') updateLayout();
        }

        (function initSidebarResizer() {
            function setupResizer() {
                const resizer = document.getElementById('sidebarResizer');
                const sidebar = document.getElementById('meetSidebar');
                if (!resizer || !sidebar) return;

                let isResizing = false;
                let startX = 0;
                let startWidth = 0;

                resizer.addEventListener('mousedown', function (e) {
                    e.preventDefault();
                    isResizing = true;
                    startX = e.clientX;
                    startWidth = parseFloat(sidebar.style.width || window.getComputedStyle(sidebar).width) || 350;

                    resizer.classList.add('is-resizing');
                    document.body.classList.add('sidebar-resizing');

                    document.addEventListener('mousemove', handleMouseMove);
                    document.addEventListener('mouseup', handleMouseUp);
                });

                function handleMouseMove(e) {
                    if (!isResizing) return;
                    // Dragging left increases width, dragging right decreases width
                    const dx = startX - e.clientX;
                    let newWidth = startWidth + dx;

                    // Bounds constraints: min 260px, max 700px (or 60% of viewport width)
                    const minWidth = 260;
                    const maxWidth = Math.min(700, window.innerWidth * 0.6);
                    newWidth = Math.max(minWidth, Math.min(maxWidth, newWidth));

                    sidebar.style.width = newWidth + 'px';
                    document.documentElement.style.setProperty('--face-badge-offset', (newWidth + 24) + 'px');

                    if (typeof updateLayout === 'function') {
                        updateLayout();
                    }
                }

                function handleMouseUp() {
                    if (!isResizing) return;
                    isResizing = false;
                    resizer.classList.remove('is-resizing');
                    document.body.classList.remove('sidebar-resizing');

                    document.removeEventListener('mousemove', handleMouseMove);
                    document.removeEventListener('mouseup', handleMouseUp);

                    try {
                        sessionStorage.setItem('meet_sidebar_width', sidebar.style.width);
                    } catch (_) { }
                }

                // Restore saved width if available
                try {
                    const savedWidth = sessionStorage.getItem('meet_sidebar_width');
                    if (savedWidth) {
                        sidebar.style.width = savedWidth;
                        const numericWidth = parseFloat(savedWidth);
                        if (!isNaN(numericWidth)) {
                            document.documentElement.style.setProperty('--face-badge-offset', (numericWidth + 24) + 'px');
                        }
                    }
                } catch (_) { }
            }

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', setupResizer);
            } else {
                setupResizer();
            }
        })();

        // ── More Options ──────────────────────────────────────────────────────────────
        function toggleMoreOptions() {
            const menu = document.getElementById('moreOptionsMenu');
            const btn = document.getElementById('moreBtn');
            menu.classList.toggle('open');
            btn.classList.toggle('active', menu.classList.contains('open'));
        }

        // Close menu when clicking outside
        document.addEventListener('click', function (e) {
            const container = document.querySelector('.more-options-container');
            const menu = document.getElementById('moreOptionsMenu');
            const btn = document.getElementById('moreBtn');
            if (menu && container && !container.contains(e.target)) {
                menu.classList.remove('open');
                if (btn) btn.classList.remove('active');
            }
        });

        // ── Keyboard Shortcuts ───────────────────────────────────────────────────────
        // Ctrl + D  → Microphone mute/unmute
        // Ctrl + E  → Camera on/off
        // Esc       → Close menu / dialog / popup / sidebar
        // Ctrl+Alt+S → Screen sharing start/stop
        document.addEventListener('keydown', function (e) {
            const isTyping = ['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable;

            // Esc: Close open popups, modals, or sidebars (active regardless of typing state)
            if (e.key === 'Escape') {
                let handled = false;

                // 1. Close camera modal if present & open
                const camModal = document.getElementById('cameraModal');
                if (camModal && camModal.style.display !== 'none') {
                    if (typeof toggleCameraModal === 'function') toggleCameraModal();
                    handled = true;
                }

                // 2. Close options menu if open
                const menu = document.getElementById('moreOptionsMenu');
                if (menu && menu.classList.contains('open')) {
                    if (typeof toggleMoreOptions === 'function') toggleMoreOptions();
                    handled = true;
                }

                // 3. Close sidebar if open
                const sidebar = document.getElementById('meetSidebar');
                if (sidebar && sidebar.style.display !== 'none') {
                    if (typeof toggleSidebar === 'function') toggleSidebar();
                    handled = true;
                }

                if (handled) {
                    e.preventDefault();
                    return;
                }
            }

            // Do not trigger media shortcuts when user is typing text in inputs or textareas
            if (isTyping) return;

            const isCtrlOrCmd = e.ctrlKey || e.metaKey;
            const key = e.key.toLowerCase();

            // Ctrl + D: Microphone mute/unmute
            if (isCtrlOrCmd && !e.altKey && !e.shiftKey && key === 'd') {
                e.preventDefault();
                if (typeof toggleMic === 'function') toggleMic();
                return;
            }

            // Ctrl + E: Camera on/off
            if (isCtrlOrCmd && !e.altKey && !e.shiftKey && key === 'e') {
                e.preventDefault();
                if (typeof toggleCamera === 'function') toggleCamera();
                return;
            }

            // Ctrl + Alt + S: Screen sharing start/stop
            if (isCtrlOrCmd && e.altKey && !e.shiftKey && key === 's') {
                e.preventDefault();
                if (typeof toggleScreenShare === 'function') toggleScreenShare();
                return;
            }
        });

        function switchSidebarTab(tab) {
            document.querySelectorAll('.sidebar-tab').forEach(b => {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            document.querySelectorAll('.sidebar-panel').forEach(p => p.classList.remove('active'));

            const targetBtn = document.getElementById(tab + 'TabBtn') || document.querySelector(`.sidebar-tab[onclick*="${tab}"]`);
            if (targetBtn) {
                targetBtn.classList.add('active');
                targetBtn.setAttribute('aria-selected', 'true');
            }

            let targetPanel = document.getElementById(tab + 'Panel');
            if (!targetPanel && tab === 'quiz') {
                targetPanel = isHost ? document.getElementById('teacherQuizMonitorPanel') : document.getElementById('meetingQuizSidePanel');
            }

            if (targetPanel) {
                targetPanel.classList.add('active');
                targetPanel.style.removeProperty('display');
            }

            if (tab === 'chat') {
                unreadMessages = 0;
                const badge = document.getElementById('chatBadge');
                if (badge) badge.style.display = 'none';
                const moreBadge = document.getElementById('moreBadge');
                if (moreBadge) moreBadge.style.display = 'none';
                const chatMessages = document.getElementById('chatMessages');
                if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
            } else if (tab === 'people') {
                updateParticipantsList();
                if (isHost) fetchBannedUsers();
            } else if (tab === 'quiz') {
                const quizBadge = document.getElementById('quizTabBadge');
                if (quizBadge) quizBadge.style.display = 'none';
                if (isHost) {
                    updateTeacherMonitorStudentList();
                }
            }
        }

        // ── Participants list ─────────────────────────────────────────────────────────
        function updateParticipantsList() {
            const list = document.getElementById('participantsList');
            if (!list) return;

            const myId = String(window.meetingConfig?.currentUserId || window.currentUserId);
            const myUser = window.IdentityDirectory.resolve(myId, window.meetingConfig?.currentDisplayName || currentUsername);
            const myFallback = window.IdentityDirectory.getAvatarSvg(myUser.displayName, myUser.color);
            const myPfp = myUser.pfp || myFallback;

            let html = `
        <div class="participant-item" data-identity="${myId}">
            <div class="participant-avatar"><img src="${myPfp}" alt="${myUser.displayName}" onerror="this.onerror=null; this.src='${myFallback}';"></div>
            <div class="participant-info">
                <div class="participant-name">
                    <span>${myUser.displayName} (You)</span>
                    ${isHost ? '<span class="host-label">Host</span>' : ''}
                </div>
            </div>
        </div>`;

            const remotes = getRemoteParticipants();
            if (remotes.length === 0) {
                html += `
            <div class="people-empty-state" id="peopleEmptyState">
                <div class="people-empty-icon">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                </div>
                <div class="people-empty-title">You're the only one here</div>
                <div class="people-empty-subtitle">Waiting for students to join...</div>
            </div>`;
            }

            list.innerHTML = html;

            remotes.forEach(p => {
                if (!p) return;
                const identity = String(p.identity);
                if (p.metadata) {
                    try {
                        const meta = typeof p.metadata === 'string' ? JSON.parse(p.metadata) : p.metadata;
                        window.IdentityDirectory.register(identity, meta);
                    } catch (e) { }
                }
                const user = window.IdentityDirectory.resolve(identity, p.name || identity);
                const fallback = window.IdentityDirectory.getAvatarSvg(user.displayName, user.color);
                const pfp = user.pfp || fallback;
                const isParticipantHost = identity === String(hostId);
                const safeName = (user.displayName || identity).replace(/'/g, "\\'");

                const item = document.createElement('div');
                item.className = 'participant-item';
                item.dataset.identity = identity;
                item.innerHTML = `
            <div class="participant-avatar"><img src="${pfp}" alt="${user.displayName}" onerror="this.onerror=null; this.src='${fallback}';"></div>
            <div class="participant-info">
                <div class="participant-name">
                    <span>${user.displayName}</span>
                    ${isParticipantHost ? '<span class="host-label">Host</span>' : ''}
                </div>
            </div>
            ${isHost && !isParticipantHost ? `
            <div class="participant-actions">
                <button class="participant-action-btn danger" onclick="openKickModal('${identity}', '${safeName}')" title="Remove student from meeting" aria-label="Remove ${user.displayName} from meeting">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                        <circle cx="8.5" cy="7" r="4"/>
                        <line x1="18" y1="8" x2="23" y2="13"/>
                        <line x1="23" y1="8" x2="18" y2="13"/>
                    </svg>
                </button>
            </div>
            ` : ''}`;
                list.appendChild(item);

                // Also sync the video card for this participant
                window.IdentityDirectory.syncCardDOM(identity);
            });
            // Note: fetchBannedUsers is called separately (when People tab is opened)
            // to avoid excessive API polling every 2s.
        }

        function updateParticipantCount() {
            try {
                const remoteCount = getRemoteParticipants().length;
                document.getElementById('participantCount').textContent = remoteCount + 1;
            } catch (e) {
                document.getElementById('participantCount').textContent = '1';
            }
        }

        // ── Timer ─────────────────────────────────────────────────────────────────────
        function startTimer() {
            timerInterval = setInterval(() => {
                if (window.meetingConfig.hostJoinedAtMs > 0) {
                    timerSeconds = Math.max(0, Math.floor((Date.now() - window.meetingConfig.hostJoinedAtMs) / 1000));
                } else {
                    timerSeconds++;
                }
                const m = String(Math.floor(timerSeconds / 60)).padStart(2, '0');
                const s = String(timerSeconds % 60).padStart(2, '0');
                document.getElementById('meetTimer').textContent = `${m}:${s}`;
            }, 1000);
        }

        // ── Notification ──────────────────────────────────────────────────────────────
        function showNotification(msg, type = 'info') {
            const colors = { info: '#8b5cf6', success: '#10b981', warning: '#f59e0b', error: '#ef4444' };
            const n = document.createElement('div');
            n.style.cssText = `position:fixed;bottom:100px;left:50%;transform:translateX(-50%);
        background:${colors[type]};color:#fff;padding:10px 20px;border-radius:8px;
        font-size:13px;font-weight:600;z-index:9999;pointer-events:none;
        box-shadow:0 4px 16px rgba(0,0,0,0.3);`;
            n.textContent = msg;
            document.body.appendChild(n);
            setTimeout(() => n.remove(), 3000);
        }

        // ── Start ─────────────────────────────────────────────────────────────────────
        window.addEventListener('beforeunload', () => { if (room) room.disconnect(); });
        init().catch(e => { console.error('Init error:', e); showNotification('Failed to connect: ' + e.message, 'error'); });



        // ── Kick Confirmation Modal Flow ─────────────────────────────────────────────
        window._pendingKickUser = null;

        function openKickModal(userId, displayName) {
            window._pendingKickUser = { id: userId, name: displayName || userId };
            const desc = document.getElementById('kickModalDesc');
            if (desc) {
                desc.textContent = `Are you sure you want to remove ${displayName || 'this student'}? They will be temporarily banned from this meeting for 1 hour.`;
            }
            const modal = document.getElementById('kickConfirmModal');
            if (modal) modal.style.display = 'flex';
        }

        function closeKickModal() {
            window._pendingKickUser = null;
            const modal = document.getElementById('kickConfirmModal');
            if (modal) modal.style.display = 'none';
        }

        async function executeKickUser() {
            if (!window._pendingKickUser || !isHost) return;
            const { id, name } = window._pendingKickUser;
            closeKickModal();

            const targetUrl = window.meetingConfig.kickUrl.replace('/0/', `/${id}/`);
            try {
                const res = await fetch(targetUrl, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': CSRF }
                });
                const data = await res.json();
                if (data.status === 'success') {
                    showNotification(`${name} has been removed`, 'info');
                    const row = document.querySelector(`.participant-item[data-identity="${id}"]`);
                    if (row) {
                        row.classList.add('removing');
                        setTimeout(() => {
                            row.remove();
                            updateParticipantCount();
                        }, 280);
                    }
                } else {
                    showNotification(data.message || 'Failed to remove student', 'error');
                }
            } catch (err) {
                showNotification('Error removing student: ' + err.message, 'error');
            }
        }
        window.openKickModal = openKickModal;
        window.closeKickModal = closeKickModal;
        window.executeKickUser = executeKickUser;

