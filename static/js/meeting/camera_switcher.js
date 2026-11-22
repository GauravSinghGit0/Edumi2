        // ── Teacher Camera Switching & Permission Controls ───────────────────────────
        function toggleCameraModal() {
            const modal = document.getElementById('cameraModal');
            if (!modal) return;
            modal.style.display = modal.style.display === 'none' ? 'flex' : 'none';
        }

        function updateTeacherTrackSubscription() {
            if (isHost || userType !== 'student') return;

            if (!window.room) return;
            let hostParticipant = null;
            getRemoteParticipants().forEach(p => {
                if (p.identity === hostId) {
                    hostParticipant = p;
                }
            });

            if (!hostParticipant) return;

            const pubs = hostParticipant.videoTrackPublications || hostParticipant.trackPublications || hostParticipant.tracks;
            if (pubs) {
                const pubList = (typeof pubs.values === 'function') ? Array.from(pubs.values()) :
                    (typeof pubs.forEach === 'function' || Array.isArray(pubs)) ? Array.from(pubs) :
                        (typeof pubs === 'object') ? Object.values(pubs) : [];

                pubList.forEach(pub => {
                    if (!pub) return;
                    const tr = pub.track || pub;
                    if (!tr) return;

                    const source = pub.source || tr.source || '';
                    const isScreenSrc = source === Track?.Source?.ScreenShare || source === 'screen_share' || String(source).includes('screen');
                    const isCamSrc = source === Track?.Source?.Camera || source === 'camera' || (!isScreenSrc && tr.kind === 'video');

                    if (isCamSrc) {
                        if (window.studentCanViewCamera) {
                            window.TrackManager.attach(tr, pub, hostParticipant);
                        } else {
                            window.TrackManager.detach(tr, pub, hostParticipant);
                        }
                    } else if (isScreenSrc) {
                        if (window.studentCanViewScreenshare) {
                            window.TrackManager.attach(tr, pub, hostParticipant);
                        } else {
                            window.TrackManager.detach(tr, pub, hostParticipant);
                        }
                    }
                });
            }
        }

        async function toggleStudentViewPermission(type) {
            let currentVal = false;
            if (type === 'student_can_view_camera') {
                currentVal = window.studentCanViewCamera;
            } else if (type === 'student_can_view_screenshare') {
                currentVal = window.studentCanViewScreenshare;
            }
            const newVal = !currentVal;

            try {
                const res = await fetch(window.meetingConfig.globalControlUrl, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type, value: newVal })
                });

                if (res.ok) {
                    if (type === 'student_can_view_camera') {
                        window.studentCanViewCamera = newVal;
                        const el = document.getElementById('studentCameraStatusText');
                        if (el) el.textContent = newVal ? 'Block Student Cam View' : 'Allow Student Cam View';
                    } else if (type === 'student_can_view_screenshare') {
                        window.studentCanViewScreenshare = newVal;
                        const el = document.getElementById('studentScreenshareStatusText');
                        if (el) el.textContent = newVal ? 'Block Student Screen View' : 'Allow Student Screen View';
                    }

                    // Real-time broadcast to student participants over LiveKit Data Channel
                    if (window.room && window.room.localParticipant && typeof window.room.localParticipant.publishData === 'function') {
                        try {
                            const payload = JSON.stringify({
                                type: 'global_control_update',
                                control_type: type,
                                value: newVal,
                                message: `Teacher updated ${type === 'student_can_view_camera' ? 'camera' : 'screenshare'} view permission`
                            });
                            const encoder = new TextEncoder();
                            window.room.localParticipant.publishData(encoder.encode(payload), 1); // 1 = RELIABLE
                        } catch (err) {
                            console.warn('Failed to publish data channel update:', err);
                        }
                    }

                    showNotification(`Permission updated successfully`, 'success');
                } else {
                    showNotification(`Failed to update permission`, 'error');
                }
            } catch (e) {
                console.error('Permission update error:', e);
                showNotification(`Error updating permission`, 'error');
            }
        }

        async function switchCameraSource(type, id, name) {
            if (type === currentVideoSource && (type === 'webcam' || id === currentIpCamId)) {
                toggleCameraModal();
                return;
            }

            currentVideoSource = type;

            try {
                if (type === 'ip') {
                    await startIpCameraStream(id, name);
                    currentIpCamId = id;
                } else {
                    await stopIpCameraStream();
                    currentIpCamId = null;
                    if (window.room && window.room.localParticipant) {
                        isCameraOn = true;
                        await window.room.localParticipant.setCameraEnabled(true);
                        document.getElementById('camBtn')?.classList.remove('off');
                        renderLocalParticipant();
                    }
                }

                // Update UI
                document.querySelectorAll('.camera-option').forEach(opt => opt.classList.remove('active'));
                if (type === 'webcam') {
                    const webcamOpt = document.getElementById('webcamOption');
                    if (webcamOpt) webcamOpt.classList.add('active');
                } else {
                    const opt = document.getElementById(`ipOption-${id}`);
                    if (opt) opt.classList.add('active');
                }

                toggleCameraModal();
                showNotification(`Camera switched to ${type === 'webcam' ? 'Default Webcam' : name}`, 'success');
            } catch (err) {
                console.error('Failed to switch camera:', err);
                showNotification('Failed to switch camera: ' + (err.message || err), 'error');
                currentVideoSource = (type === 'ip') ? 'webcam' : 'ip';
            }
        }

        async function startIpCameraStream(id, name) {
            showNotification(`Connecting to ${name} classroom camera...`, 'info');

            const overlay = document.getElementById('monitoringOverlay');
            const container = document.getElementById('monitoringVideoContainer');

            // 1. Setup Canvas and Image
            if (!ipCamCanvas) {
                ipCamCanvas = document.getElementById('ipCamCanvas') || document.createElement('canvas');
                ipCamCanvas.id = 'ipCamCanvas';
                ipCamCanvas.width = 1920;
                ipCamCanvas.height = 1080;
                ipCamCtx = ipCamCanvas.getContext('2d');
            }
            if (!ipCamImg) {
                ipCamImg = document.getElementById('ipCamImg') || new Image();
                ipCamImg.id = 'ipCamImg';
                ipCamImg.crossOrigin = 'anonymous';
            }

            ipCamImg.src = "";
            const feedUrl = `/cameras/${id}/feed/?q=high&t=${Date.now()}`;
            ipCamImg.src = feedUrl;

            // Teacher webcam video element for Picture-in-Picture
            let teacherPipVideo = window._teacherPipVideo;
            if (!teacherPipVideo) {
                teacherPipVideo = document.createElement('video');
                teacherPipVideo.autoplay = true;
                teacherPipVideo.muted = true;
                teacherPipVideo.playsInline = true;
                window._teacherPipVideo = teacherPipVideo;
            }

            // Capture local webcam track if available
            if (window.room && window.room.localParticipant) {
                const lp = window.room.localParticipant;
                const pubs = lp.videoTrackPublications || lp.tracks;
                if (pubs) {
                    pubs.forEach(pub => {
                        const tr = pub.track || pub.videoTrack;
                        if (tr && tr.mediaStreamTrack && tr !== ipCamTrackPub?.track) {
                            if (!teacherPipVideo.srcObject || teacherPipVideo.srcObject.getVideoTracks()[0] !== tr.mediaStreamTrack) {
                                teacherPipVideo.srcObject = new MediaStream([tr.mediaStreamTrack]);
                            }
                        }
                    });
                }
            }

            window._studioLayoutMode = window._studioLayoutMode || 'board'; // 'board' or 'pip'

            // 2. Start Animation loop
            const drawFrame = () => {
                if (currentVideoSource !== 'ip') return;

                const cw = ipCamCanvas.width;
                const ch = ipCamCanvas.height;

                if (ipCamImg.naturalWidth > 0) {
                    const canvasAspect = cw / ch;
                    const imgAspect = ipCamImg.naturalWidth / ipCamImg.naturalHeight;

                    let drawWidth, drawHeight, offsetX, offsetY;
                    if (imgAspect > canvasAspect) {
                        drawWidth = cw;
                        drawHeight = cw / imgAspect;
                        offsetX = 0;
                        offsetY = (ch - drawHeight) / 2;
                    } else {
                        drawHeight = ch;
                        drawWidth = ch * imgAspect;
                        offsetY = 0;
                        offsetX = (cw - drawWidth) / 2;
                    }

                    ipCamCtx.fillStyle = '#0a0f1d';
                    ipCamCtx.fillRect(0, 0, cw, ch);
                    ipCamCtx.drawImage(ipCamImg, offsetX, offsetY, drawWidth, drawHeight);

                    // If Picture-in-Picture mode and teacher webcam video is active
                    if (window._studioLayoutMode === 'pip' && teacherPipVideo && teacherPipVideo.readyState >= 2) {
                        const pipW = 420;
                        const pipH = 236;
                        const pipX = cw - pipW - 36;
                        const pipY = ch - pipH - 36;

                        // Backdrop border & shadow
                        ipCamCtx.save();
                        ipCamCtx.shadowColor = 'rgba(0, 0, 0, 0.7)';
                        ipCamCtx.shadowBlur = 24;
                        ipCamCtx.fillStyle = '#1e293b';
                        if (typeof ipCamCtx.roundRect === 'function') {
                            ipCamCtx.beginPath();
                            ipCamCtx.roundRect(pipX - 4, pipY - 4, pipW + 8, pipH + 8, 16);
                            ipCamCtx.fill();
                        } else {
                            ipCamCtx.fillRect(pipX - 4, pipY - 4, pipW + 8, pipH + 8);
                        }
                        ipCamCtx.restore();

                        // Clip rounded webcam video
                        ipCamCtx.save();
                        if (typeof ipCamCtx.roundRect === 'function') {
                            ipCamCtx.beginPath();
                            ipCamCtx.roundRect(pipX, pipY, pipW, pipH, 12);
                            ipCamCtx.clip();
                        }
                        ipCamCtx.drawImage(teacherPipVideo, pipX, pipY, pipW, pipH);
                        ipCamCtx.restore();

                        // PiP Label
                        ipCamCtx.fillStyle = 'rgba(15, 23, 42, 0.85)';
                        if (typeof ipCamCtx.roundRect === 'function') {
                            ipCamCtx.beginPath();
                            ipCamCtx.roundRect(pipX + 12, pipY + 12, 120, 26, 6);
                            ipCamCtx.fill();
                        }
                        ipCamCtx.fillStyle = '#38bdf8';
                        ipCamCtx.font = 'bold 12px Inter, sans-serif';
                        ipCamCtx.textAlign = 'left';
                        ipCamCtx.fillText('TEACHER LIVE', pipX + 20, pipY + 29);
                    }

                    // Watermark badge: STUDIO • BOARD VIEW
                    ipCamCtx.fillStyle = 'rgba(15, 23, 42, 0.75)';
                    if (typeof ipCamCtx.roundRect === 'function') {
                        ipCamCtx.beginPath();
                        ipCamCtx.roundRect(24, 24, 190, 32, 8);
                        ipCamCtx.fill();
                    }
                    ipCamCtx.fillStyle = '#10b981';
                    ipCamCtx.beginPath();
                    ipCamCtx.arc(42, 40, 5, 0, Math.PI * 2);
                    ipCamCtx.fill();
                    ipCamCtx.fillStyle = '#ffffff';
                    ipCamCtx.font = '600 13px Inter, sans-serif';
                    ipCamCtx.textAlign = 'left';
                    ipCamCtx.fillText(`${name} LIVE`, 56, 45);
                } else {
                    ipCamCtx.fillStyle = '#0b0f19';
                    ipCamCtx.fillRect(0, 0, cw, ch);
                    ipCamCtx.fillStyle = '#38bdf8';
                    ipCamCtx.beginPath();
                    ipCamCtx.arc(cw / 2, ch / 2 - 30, 24, 0, Math.PI * 2);
                    ipCamCtx.fill();
                    ipCamCtx.fillStyle = '#ffffff';
                    ipCamCtx.font = 'bold 26px Inter, sans-serif';
                    ipCamCtx.textAlign = 'center';
                    ipCamCtx.fillText(`Connecting to ${name}...`, cw / 2, ch / 2 + 30);
                    ipCamCtx.fillStyle = '#94a3b8';
                    ipCamCtx.font = '14px Inter, sans-serif';
                    ipCamCtx.fillText('Smart Classroom RTSP Live Feed', cw / 2, ch / 2 + 65);
                }
                ipCamAnimationId = requestAnimationFrame(drawFrame);
            };

            if (ipCamAnimationId) cancelAnimationFrame(ipCamAnimationId);
            ipCamAnimationId = requestAnimationFrame(drawFrame);

            const stream = ipCamCanvas.captureStream(20);

            // 3. Attach directly to Teacher's main video box so teacher sees the board!
            isCameraOn = true;
            window.isCameraOn = true;
            const myId = String(window.currentUserId || '');
            const localBox = (myId ? document.getElementById(`participant-${myId}`) : null) || 
                             document.querySelector('.video-box[data-local="true"]') || 
                             document.querySelector('.video-box');
            if (localBox) {
                localBox.classList.remove('cam-off');
                let vid = localBox.querySelector('video#localVideo') || localBox.querySelector('video');
                if (!vid) {
                    vid = document.createElement('video');
                    vid.id = 'localVideo';
                    vid.dataset.local = 'true';
                    vid.autoplay = true;
                    vid.muted = true;
                    vid.playsInline = true;
                    vid.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
                    localBox.insertBefore(vid, localBox.querySelector('.video-nametag'));
                }
                vid.srcObject = stream;
                vid.play().catch(e => console.debug('local video play:', e));
            }

            // 4. Update Studio Director Overlay
            if (overlay && container) {
                overlay.style.display = 'block';
                container.innerHTML = `
                    <div style="position:relative; width:100%; height:100%;">
                        <video autoplay muted playsinline style="width:100%;height:100%;object-fit:cover;border-radius:10px;"></video>
                        <div style="position:absolute;bottom:6px;left:6px;right:6px;display:flex;gap:4px;justify-content:center;background:rgba(15,23,42,0.85);backdrop-filter:blur(8px);padding:4px;border-radius:8px;">
                            <button id="studioBtnBoard" onclick="window._studioLayoutMode='board'; showNotification('Studio: Board Full View', 'info');" style="background:#6366f1;color:#fff;border:none;padding:4px 8px;border-radius:5px;font-size:11px;font-weight:600;cursor:pointer;">Board</button>
                            <button id="studioBtnPip" onclick="window._studioLayoutMode='pip'; showNotification('Studio: Board + Face PiP', 'info');" style="background:#334155;color:#fff;border:none;padding:4px 8px;border-radius:5px;font-size:11px;font-weight:600;cursor:pointer;">Board+Face</button>
                            <button onclick="switchCameraSource('webcam');" style="background:#ef4444;color:#fff;border:none;padding:4px 8px;border-radius:5px;font-size:11px;font-weight:600;cursor:pointer;">Webcam</button>
                        </div>
                    </div>
                `;
                const previewVid = container.querySelector('video');
                if (previewVid) previewVid.srcObject = stream;
            }

            // 5. Publish to LiveKit for students
            if (window.room && window.room.localParticipant) {
                try {
                    if (ipCamTrackPub) {
                        await window.room.localParticipant.unpublishTrack(ipCamTrackPub.track);
                        if (ipCamTrackPub.track) ipCamTrackPub.track.stop();
                        ipCamTrackPub = null;
                    }

                    const videoTrack = stream.getVideoTracks()[0];
                    if (videoTrack) {
                        ipCamTrackPub = await window.room.localParticipant.publishTrack(videoTrack, {
                            name: 'camera',
                            source: Track.Source.Camera,
                            simulcast: true,
                        });
                        console.log('Classroom Studio track published to LiveKit');
                    }
                } catch (err) {
                    console.error('Failed to publish Classroom Studio track:', err);
                }
            }

            showNotification(`${name} classroom studio feed active`, 'success');
        }

        async function stopIpCameraStream() {
            const overlay = document.getElementById('monitoringOverlay');
            const container = document.getElementById('monitoringVideoContainer');

            if (overlay) overlay.style.display = 'none';
            if (container) container.innerHTML = '';

            if (ipCamAnimationId) {
                cancelAnimationFrame(ipCamAnimationId);
                ipCamAnimationId = null;
            }

            if (ipCamTrackPub && window.room && window.room.localParticipant) {
                try {
                    await window.room.localParticipant.unpublishTrack(ipCamTrackPub.track);
                    if (ipCamTrackPub.track) ipCamTrackPub.track.stop();
                    ipCamTrackPub = null;
                } catch (err) {
                    console.warn('Error unpublishing IP camera track:', err);
                }
            }

            if (ipCamImg) {
                ipCamImg.onload = null;
                ipCamImg.onerror = null;
                ipCamImg.src = "";
            }

            currentVideoSource = 'webcam';
            currentIpCamId = null;

            // Restore webcam
            if (isCameraOn && window.room && window.room.localParticipant) {
                try {
                    await window.room.localParticipant.setCameraEnabled(true);
                    renderLocalParticipant();
                } catch (err) {
                    console.warn('Failed to restore webcam:', err);
                }
            }

            document.querySelectorAll('.camera-option').forEach(opt => opt.classList.remove('active'));
            const webcamOpt = document.getElementById('webcamOption');
            if (webcamOpt) webcamOpt.classList.add('active');

            showNotification('Classroom camera disconnected', 'info');
        }

