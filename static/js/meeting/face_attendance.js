        // ── Face Attendance Module (Students Only) ───────────────────────────────────
        if (!isHost) {
            (function () {
                let attWs = null;
                let captureTimer = null;
                let marked = false;

                // Create Badge UI
                const badge = document.createElement('div');
                badge.id = 'face-att-badge';
                badge.className = 'state-active';
                badge.innerHTML = `
        <div class="fa-dot"></div>
        <div style="flex:1">
            <div id="face-att-text">Initializing Face Recognition...</div>
            <div id="face-att-prog-wrap" style="display:none">
                <div id="face-att-progress-bar"><div id="face-att-progress-fill"></div></div>
            </div>
        </div>
        <button class="face-att-close" id="face-att-close-btn" title="Dismiss" aria-label="Dismiss">✕</button>
    `;
                document.body.appendChild(badge);

                const badgeText = badge.querySelector('#face-att-text');
                const progWrap = badge.querySelector('#face-att-prog-wrap');
                const progFill = badge.querySelector('#face-att-progress-fill');
                const closeBtn = badge.querySelector('#face-att-close-btn');

                function scheduleAutoDismiss(ms = 10000) {
                    clearTimeout(window._faceAttDismissTimer);
                    window._faceAttDismissTimer = setTimeout(() => {
                        if (badge && badge.parentElement) {
                            badge.style.opacity = '0';
                            setTimeout(() => badge.remove(), 400);
                        }
                    }, ms);
                }

                if (closeBtn) {
                    closeBtn.onclick = () => {
                        clearTimeout(window._faceAttDismissTimer);
                        badge.style.opacity = '0';
                        setTimeout(() => badge.remove(), 400);
                    };
                }

                // Auto-dismiss initial state after 15s if connection fails or stalls
                scheduleAutoDismiss(15000);

                function connect() {
                    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                    attWs = new WebSocket(`${proto}//${window.location.host}/ws/attendance/${meetingCode}/`);
                    attWs.onmessage = e => {
                        const data = JSON.parse(e.data);
                        switch (data.type) {
                            case 'connected':
                                if (data.has_profile) {
                                    badgeText.textContent = 'Face Recognition Active';
                                    startCapture(data.interval * 1000);
                                    scheduleAutoDismiss(6000);
                                } else {
                                    badge.className = 'state-warning';
                                    badgeText.innerHTML = 'No profile found. <a href="/attendance/face/setup/" style="color:#f87171">Register Now</a>';
                                    scheduleAutoDismiss(12000);
                                }
                                break;
                            case 'verification_progress':
                                clearTimeout(window._faceAttDismissTimer);
                                badge.style.opacity = '1';
                                const pct = Math.round((data.verified_seconds / data.required_seconds) * 100);
                                badge.className = 'state-progress';
                                badgeText.textContent = `Verifying... ${pct}%`;
                                progWrap.style.display = 'block';
                                progFill.style.width = pct + '%';
                                break;
                            case 'attendance_marked':
                                marked = true;
                                badge.className = 'state-success';
                                badgeText.textContent = 'Attendance Recorded!';
                                progWrap.style.display = 'none';
                                stopCapture();
                                scheduleAutoDismiss(5000);
                                break;
                            case 'verification_failed':
                                badge.className = 'state-warning';
                                badgeText.textContent = data.message || 'Face Not Recognized';
                                scheduleAutoDismiss(10000);
                                break;
                        }
                    };
                    attWs.onclose = () => !marked && setTimeout(connect, 5000);
                }

                function captureAndSend() {
                    const video = document.getElementById('localVideo');
                    if (!video || video.readyState < 2 || !attWs || attWs.readyState !== 1) return;
                    const canvas = document.createElement('canvas');
                    canvas.width = 320; canvas.height = 240;
                    const ctx = canvas.getContext('2d');
                    ctx.save(); ctx.scale(-1, 1); ctx.drawImage(video, -320, 0, 320, 240); ctx.restore();
                    attWs.send(JSON.stringify({ type: 'frame', frame: canvas.toDataURL('image/jpeg', 0.8).split(',')[1] }));
                }

                function startCapture(ms) {
                    if (captureTimer) clearInterval(captureTimer);
                    captureTimer = setInterval(captureAndSend, ms || 15000);
                    setTimeout(captureAndSend, 2000);
                }

                function stopCapture() { clearInterval(captureTimer); captureTimer = null; }

                window.addEventListener('load', () => setTimeout(connect, 3000));
            })();
        }

        // ── Face Tracking Module (Host Only) ─────────────────────────────────────────
        if (isHost) {
            (function () {
                let ftWs = null;
                let ftEnabled = false;
                let ftTimer = null;
                const ftCanvas = document.createElement('canvas');

                window.toggleFaceTracking = function () {
                    ftEnabled = !ftEnabled;
                    const btn = document.getElementById('ftToggleBtn');
                    btn.classList.toggle('active', ftEnabled);
                    if (ftEnabled) {
                        btn.style.background = '#10b981';
                        connect();
                        showNotification('Face Tracking Enabled', 'success');
                    } else {
                        btn.style.background = '';
                        stop();
                        showNotification('Face Tracking Disabled', 'info');
                    }
                };

                function connect() {
                    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                    ftWs = new WebSocket(`${proto}//${window.location.host}/ws/face-tracking/${meetingCode}/`);
                    ftWs.onopen = () => { ftTimer = setInterval(captureAll, 5000); captureAll(); };
                    ftWs.onmessage = e => {
                        const data = JSON.parse(e.data);
                        if (data.type === 'bulk_tracking_result') {
                            Object.entries(data.results).forEach(([uid, res]) => drawOverlay(uid, res));
                        }
                    };
                    ftWs.onclose = () => ftEnabled && setTimeout(connect, 5000);
                }

                function stop() {
                    clearInterval(ftTimer); ftTimer = null;
                    if (ftWs) ftWs.close();
                    document.querySelectorAll('.ft-canvas-overlay, .ft-emotion-badge').forEach(el => el.remove());
                }

                function captureAll() {
                    if (!ftWs || ftWs.readyState !== 1) return;
                    const frames = {};
                    document.querySelectorAll('.video-box').forEach(box => {
                        const uid = box.dataset.userId;
                        if (!uid || uid === currentUserId) return;
                        const video = box.querySelector('video');
                        if (!video || video.readyState < 2) return;
                        ftCanvas.width = 320; ftCanvas.height = 240;
                        ftCanvas.getContext('2d').drawImage(video, 0, 0, 320, 240);
                        frames[uid] = ftCanvas.toDataURL('image/jpeg', 0.7).split(',')[1];
                    });
                    if (Object.keys(frames).length > 0) ftWs.send(JSON.stringify({ type: 'bulk_frame', frames }));
                }

                function drawOverlay(uid, res) {
                    const box = document.getElementById(`video-box-${uid}`);
                    if (!box) return;
                    let canvas = box.querySelector('.ft-canvas-overlay');
                    if (!canvas) {
                        canvas = document.createElement('canvas');
                        canvas.className = 'ft-canvas-overlay';
                        box.appendChild(canvas);
                    }
                    canvas.width = box.offsetWidth; canvas.height = box.offsetHeight;
                    const ctx = canvas.getContext('2d');
                    ctx.clearRect(0, 0, canvas.width, canvas.height);

                    if (res.face_visible && res.faces) {
                        res.faces.forEach(face => {
                            const { x, y, w, h } = face.box;
                            ctx.strokeStyle = '#10b981'; ctx.lineWidth = 2;
                            ctx.strokeRect(x * canvas.width, y * canvas.height, w * canvas.width, h * canvas.height);
                            ctx.fillStyle = '#10b981'; ctx.font = 'bold 12px Inter';
                            ctx.fillText(face.name, x * canvas.width, y * canvas.height - 5);
                        });
                        updateEmotion(box, res.emotion_label);
                    } else {
                        updateEmotion(box, null);
                    }
                }

                function updateEmotion(box, label) {
                    let eb = box.querySelector('.ft-emotion-badge');
                    if (!label) { eb?.remove(); return; }
                    if (!eb) { eb = document.createElement('div'); eb.className = 'ft-emotion-badge'; box.appendChild(eb); }
                    eb.textContent = label;
                }
            })();
        }

