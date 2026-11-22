        // ── Industry-Grade Live Meeting Room Recorder Engine (MKV Format) ────────────
        window.MeetingRecorder = {
            recorder: null,
            uploadId: null,
            chunkIndex: 0,
            timerInterval: null,
            secondsElapsed: 0,
            isRecording: false,

            async start() {
                if (this.isRecording) return;
                try {
                    this.uploadId = 'rec_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                    this.chunkIndex = 0;
                    this.secondsElapsed = 0;

                    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    if (audioCtx.state === 'suspended') {
                        await audioCtx.resume();
                    }
                    const audioDestination = audioCtx.createMediaStreamDestination();

                    const safeGetTracks = (pubs) => {
                        if (!pubs) return [];
                        const pubList = (typeof pubs.values === 'function') ? Array.from(pubs.values()) :
                            (typeof pubs.forEach === 'function' || Array.isArray(pubs)) ? Array.from(pubs) :
                                (typeof pubs === 'object') ? Object.values(pubs) : [];
                        const tracks = [];
                        pubList.forEach(pub => {
                            if (!pub) return;
                            const tr = pub.track || pub.audioTrack || pub.videoTrack || pub;
                            if (tr) {
                                const mst = tr.mediaStreamTrack || (tr instanceof MediaStreamTrack ? tr : null);
                                if (mst && mst.readyState === 'live') {
                                    tracks.push(mst);
                                }
                            }
                        });
                        return tracks;
                    };

                    // Audio mixing: Combine local microphone + all remote participant audio tracks
                    if (window.room && window.room.localParticipant) {
                        const lp = window.room.localParticipant;
                        const localAudioPubs = lp.audioTrackPublications || lp.audioTracks || lp.trackPublications;
                        safeGetTracks(localAudioPubs).forEach(mst => {
                            try {
                                const src = audioCtx.createMediaStreamSource(new MediaStream([mst]));
                                src.connect(audioDestination);
                            } catch (_) { }
                        });
                    }

                    const remotes = typeof getRemoteParticipants === 'function' ? getRemoteParticipants() : [];
                    remotes.forEach(p => {
                        if (!p) return;
                        const rAudioPubs = p.audioTrackPublications || p.audioTracks || p.trackPublications;
                        safeGetTracks(rAudioPubs).forEach(mst => {
                            try {
                                const src = audioCtx.createMediaStreamSource(new MediaStream([mst]));
                                src.connect(audioDestination);
                            } catch (_) { }
                        });
                    });

                    // Also check any HTML <audio> or <video> elements on page playing audio
                    document.querySelectorAll('audio, video').forEach(mediaEl => {
                        if (mediaEl.srcObject && mediaEl.srcObject instanceof MediaStream) {
                            mediaEl.srcObject.getAudioTracks().forEach(mst => {
                                if (mst && mst.readyState === 'live') {
                                    try {
                                        const src = audioCtx.createMediaStreamSource(new MediaStream([mst]));
                                        src.connect(audioDestination);
                                    } catch (_) { }
                                }
                            });
                        }
                    });

                    // Video Capture: Capture Full Browser Tab / Meeting Screen (Teacher View)
                    let videoTrack = null;

                    // 1. Primary: Prompt teacher to capture Full Browser Tab / Meeting Screen via getDisplayMedia
                    if (navigator.mediaDevices && typeof navigator.mediaDevices.getDisplayMedia === 'function') {
                        try {
                            const displayStream = await navigator.mediaDevices.getDisplayMedia({
                                video: {
                                    displaySurface: 'browser',
                                    width: { ideal: 1920 },
                                    height: { ideal: 1080 },
                                    frameRate: { ideal: 30 }
                                },
                                audio: true
                            });
                            const dTracks = displayStream.getVideoTracks();
                            if (dTracks.length > 0) {
                                videoTrack = dTracks[0];
                                videoTrack.onended = () => {
                                    if (this.isRecording) this.stop();
                                };
                            }
                            const dAudio = displayStream.getAudioTracks();
                            if (dAudio.length > 0) {
                                dAudio.forEach(at => {
                                    try {
                                        const src = audioCtx.createMediaStreamSource(new MediaStream([at]));
                                        src.connect(audioDestination);
                                    } catch (_) { }
                                });
                            }
                        } catch (displayErr) {
                            console.info('Full browser tab capture prompt skipped/canceled, proceeding with active room layout fallback:', displayErr);
                        }
                    }

                    // 2. Fallback: Use active screen share or local video publication
                    if (!videoTrack && window.room && window.room.localParticipant) {
                        const lp = window.room.localParticipant;
                        const localVideoPubs = lp.videoTrackPublications || lp.videoTracks || lp.trackPublications;
                        const localVids = safeGetTracks(localVideoPubs);
                        if (localVids.length > 0) videoTrack = localVids[0];
                    }

                    // 3. Fallback: Search remote participant video tracks
                    if (!videoTrack) {
                        for (const p of remotes) {
                            const rVidPubs = p ? (p.videoTrackPublications || p.videoTracks || p.trackPublications) : null;
                            const rVids = safeGetTracks(rVidPubs);
                            if (rVids.length > 0) {
                                videoTrack = rVids[0];
                                break;
                            }
                        }
                    }

                    // 4. Fallback: Capture active meeting video DOM elements
                    if (!videoTrack) {
                        const videoEls = document.querySelectorAll('#mainVideoArea video, #sidebarVideoArea video, video');
                        for (const v of videoEls) {
                            if (v.srcObject && v.srcObject instanceof MediaStream) {
                                const vTracks = v.srcObject.getVideoTracks();
                                if (vTracks.length > 0 && vTracks[0].readyState === 'live') {
                                    videoTrack = vTracks[0];
                                    break;
                                }
                            } else if (typeof v.captureStream === 'function') {
                                try {
                                    const capStream = v.captureStream();
                                    const vTracks = capStream.getVideoTracks();
                                    if (vTracks.length > 0 && vTracks[0].readyState === 'live') {
                                        videoTrack = vTracks[0];
                                        break;
                                    }
                                } catch (_) { }
                            }
                        }
                    }

                    // 5. Fallback: Standby Canvas Stream if no video source is active
                    if (!videoTrack) {
                        try {
                            const fallbackCanvas = document.createElement('canvas');
                            fallbackCanvas.width = 1280;
                            fallbackCanvas.height = 720;
                            const fCtx = fallbackCanvas.getContext('2d');
                            if (fCtx) {
                                fCtx.fillStyle = '#000000';
                                fCtx.fillRect(0, 0, 1280, 720);
                                fCtx.fillStyle = '#38bdf8';
                                fCtx.font = 'bold 36px sans-serif';
                                fCtx.textAlign = 'center';
                                fCtx.fillText((window.meetingConfig && window.meetingConfig.meetingTitle) || 'Live Meeting', 640, 340);
                                fCtx.fillStyle = '#94a3b8';
                                fCtx.font = '22px sans-serif';
                                fCtx.fillText('Full Meeting Recording Active', 640, 390);

                                const canvasStream = fallbackCanvas.captureStream(10);
                                const cVid = canvasStream.getVideoTracks();
                                if (cVid.length > 0) videoTrack = cVid[0];
                            }
                        } catch (_) { }
                    }

                    const combinedStream = new MediaStream();
                    if (videoTrack) combinedStream.addTrack(videoTrack);
                    audioDestination.stream.getAudioTracks().forEach(t => combinedStream.addTrack(t));

                    const mimeTypes = [
                        'video/x-matroska;codecs=avc1,opus',
                        'video/x-matroska',
                        'video/webm;codecs=vp9,opus',
                        'video/webm;codecs=vp8,opus',
                        'video/webm',
                        'audio/webm'
                    ];
                    let selectedMime = '';
                    for (const mime of mimeTypes) {
                        if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(mime)) {
                            selectedMime = mime;
                            break;
                        }
                    }

                    this.recorder = new MediaRecorder(combinedStream, selectedMime ? {
                        mimeType: selectedMime,
                        videoBitsPerSecond: 3000000
                    } : undefined);

                    this.recorder.ondataavailable = (evt) => {
                        if (evt.data && evt.data.size > 0) {
                            this.lastChunkBlob = evt.data;
                            this.uploadChunk(evt.data, false);
                        }
                    };

                    this.recorder.onstop = () => {
                        this.finalizeUpload();
                    };

                    this.recorder.start(5000);
                    this.isRecording = true;

                    if (window.signalingWs && window.signalingWs.readyState === WebSocket.OPEN) {
                        window.signalingWs.send(JSON.stringify({ type: 'start_recording' }));
                    }

                    this.updateUI(true);
                    this.startTimer();
                    showNotification('Meeting recording started.', 'success');
                } catch (err) {
                    console.error('Failed to start recording:', err);
                    showNotification('Failed to start meeting recording: ' + err.message, 'error');
                }
            },

            async stop() {
                if (!this.isRecording || !this.recorder) return;
                this.isRecording = false;
                try {
                    this.recorder.stop();
                } catch (_) { }

                if (window.signalingWs && window.signalingWs.readyState === WebSocket.OPEN) {
                    window.signalingWs.send(JSON.stringify({ type: 'stop_recording' }));
                }

                this.updateUI(false);
                this.stopTimer();
                showNotification('Recording stopped. Processing MKV video on server...', 'info');
            },

            async uploadChunk(blobData, isFinal = false) {
                const cIndex = this.chunkIndex++;
                const formData = new FormData();
                formData.append('chunk', blobData, `chunk_${cIndex}.tmp`);
                formData.append('uploadId', this.uploadId);
                formData.append('chunkIndex', cIndex);
                formData.append('totalChunks', isFinal ? cIndex + 1 : cIndex + 100);
                formData.append('filename', `recording_${window.meetingConfig.meetingCode}.mkv`);
                formData.append('meeting_id', window.meetingConfig.meetingId || '');

                try {
                    const url = window.meetingConfig.recordingUploadUrl || '/meetings/recording/upload/';
                    const res = await fetch(url, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': window.CSRF },
                        body: formData
                    });
                    const data = await res.json();
                    if (data.status === 'success' && data.redirect_url) {
                        showNotification('Recording saved in MKV format!', 'success');
                    }
                } catch (err) {
                    console.warn(`Chunk ${cIndex} upload notice:`, err);
                }
            },

            async finalizeUpload() {
                if (this.lastChunkBlob) {
                    await this.uploadChunk(this.lastChunkBlob, true);
                    this.lastChunkBlob = null;
                }
            },

            startTimer() {
                this.stopTimer();
                this.secondsElapsed = 0;
                this.timerInterval = setInterval(() => {
                    this.secondsElapsed++;
                    const m = String(Math.floor(this.secondsElapsed / 60)).padStart(2, '0');
                    const s = String(this.secondsElapsed % 60).padStart(2, '0');
                    const timerEl = document.getElementById('recordingTimer');
                    if (timerEl) timerEl.textContent = `${m}:${s}`;
                }, 1000);
            },

            stopTimer() {
                if (this.timerInterval) clearInterval(this.timerInterval);
                this.timerInterval = null;
            },

            updateUI(isRecording) {
                const badge = document.getElementById('recordingIndicator');
                if (badge) badge.style.display = isRecording ? 'flex' : 'none';
                const txt = document.getElementById('recordToggleBtnText');
                if (txt) txt.textContent = isRecording ? 'Stop Recording' : 'Start Recording (MKV)';
                const mainRecBtn = document.getElementById('mainRecordBtn');
                if (mainRecBtn) {
                    if (isRecording) {
                        mainRecBtn.classList.add('recording-active');
                        mainRecBtn.title = 'Stop Recording';
                        mainRecBtn.setAttribute('data-tooltip', 'Stop Recording');
                        mainRecBtn.style.background = '#ef4444';
                        mainRecBtn.style.color = '#fff';
                    } else {
                        mainRecBtn.classList.remove('recording-active');
                        mainRecBtn.title = 'Start Recording';
                        mainRecBtn.setAttribute('data-tooltip', 'Start Recording');
                        mainRecBtn.style.background = '';
                        mainRecBtn.style.color = '';
                    }
                }
            }
        };

        window.addEventListener('beforeunload', () => {
            if (window.MeetingRecorder && window.MeetingRecorder.isRecording) {
                try { window.MeetingRecorder.stop(); } catch (_) { }
            }
        });

        function toggleMeetingRecording() {
            if (window.MeetingRecorder.isRecording) {
                window.MeetingRecorder.stop();
            } else {
                window.MeetingRecorder.start();
            }
        }

        function showTimeLimitModal() {
            if (!window.isHost || window.isExtended) return;
            const modal = document.getElementById('timeLimitModal');
            if (modal) modal.style.display = 'flex';
        }

        function hideTimeLimitModal() {
            const modal = document.getElementById('timeLimitModal');
            if (modal) modal.style.display = 'none';
        }

        async function handleTimeLimitChoice(choice) {
            hideTimeLimitModal();
            if (choice === 'continue') {
                window.isExtended = true;
                if (window.signalingWs && window.signalingWs.readyState === WebSocket.OPEN) {
                    window.signalingWs.send(JSON.stringify({ type: 'continue_meeting' }));
                }
                try {
                    await fetch(window.meetingConfig.continueUrl, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': window.CSRF,
                            'Content-Type': 'application/json'
                        }
                    });
                } catch (e) {
                    console.warn('Continue meeting HTTP fallback error:', e);
                }
                showNotification('Meeting extended successfully. You can continue class.', 'success');
            } else if (choice === 'end') {
                try {
                    await fetch(window.meetingConfig.endUrl, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': window.CSRF,
                            'Content-Type': 'application/json'
                        }
                    });
                } catch (e) {
                    console.warn('End meeting HTTP fallback error:', e);
                }
                leaveMeeting();
            }
        }

