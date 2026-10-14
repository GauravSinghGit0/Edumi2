/**
 * ==========================================================================
 * FaceSetupManager — EduMi Face Registration & AI Live Condition Engine
 * Modular JS for camera states, real-time face condition checks,
 * red/yellow/green HUD feedback, 3-2-1 auto-capture, burst selection,
 * anti-spoof liveness, and multi-angle guided registration.
 * Using Lucide Icons across all UI states.
 * ==========================================================================
 */
(function() {
    'use strict';

    var FaceSetupManager = {
        config: {
            infoComplete: true,
            urls: {
                updateProfile: '/attendance/profile/info/update/',
                detectFace: '/attendance/detect/',
                captureFace: '/attendance/capture/',
                localModels: '/static/vendor/face-api/models',
                cdnModels: 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model'
            }
        },

        // State
        cameraStream: null,
        animFrameId: null,
        modelReady: false,
        modelLoading: false,
        isCapturing: false,
        captureMode: 'standard', // 'standard' | 'liveness' | 'multiangle'

        // Liveness State
        livenessVerified: false,
        eyeBlinkDetected: false,
        previousEAR: 0.3,

        // Multi-Angle State
        multiAngleStep: 0, // 0: front, 1: left, 2: right
        capturedAngleFrames: [],

        // Auto-Capture Countdown
        countdownTimer: null,
        countdownValue: 3,
        greenStableFrames: 0,
        isCountingDown: false,

        // Burst Capture Frames
        bestCapturedData: null,
        burstFrames: [],

        // Motion Tracking for Blur Detection
        lastNosePos: null,
        lastCheckTime: 0,
        checkThrottleMs: 120,

        // ── Initialization ────────────────────────────────────
        init: function(options) {
            if (options) {
                if (typeof options.infoComplete !== 'undefined') {
                    this.config.infoComplete = options.infoComplete;
                }
                if (options.urls) {
                    this.config.urls = Object.assign(this.config.urls, options.urls);
                }
            }

            this.checkInfoModal();
            this.setupDragAndDrop();
            this.setupTurboHandlers();
            this.refreshIcons();
        },

        refreshIcons: function(root) {
            if (typeof lucide !== 'undefined' && lucide.createIcons) {
                try {
                    lucide.createIcons(root ? { root: root } : undefined);
                } catch(e) {
                    // Ignore lucide re-render errors
                }
            }
        },

        // ── Profile Modal Logic ───────────────────────────────
        checkInfoModal: function() {
            var modal = document.getElementById('infoModal');
            if (modal && !this.config.infoComplete) {
                modal.classList.add('active');
            }
        },

        closeInfoModal: function() {
            var modal = document.getElementById('infoModal');
            if (modal) modal.classList.remove('active');
        },

        saveProfileInfo: async function() {
            var self = this;
            var roll = (document.getElementById('modal_roll')?.value || '').trim();
            var branch = (document.getElementById('modal_branch')?.value || '').trim();
            var errorEl = document.getElementById('infoModalError');

            if (!roll || !branch) {
                if (errorEl) {
                    errorEl.textContent = "Please fill in all required fields (Roll Number and Branch).";
                    errorEl.style.display = "block";
                }
                return;
            }

            try {
                var resp = await fetch(self.config.urls.updateProfile, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': self.getCsrf() },
                    body: JSON.stringify({ roll_number: roll, branch: branch })
                });
                var data = await resp.json();

                if (data.status === 'success') {
                    self.closeInfoModal();
                    self.config.infoComplete = true;
                    window.location.reload();
                } else if (errorEl) {
                    errorEl.textContent = data.message || "Failed to update profile.";
                    errorEl.style.display = "block";
                }
            } catch(e) {
                if (errorEl) {
                    errorEl.textContent = "Failed to update profile. Please try again.";
                    errorEl.style.display = "block";
                }
            }
        },

        // ── Tab & Mode Switching ──────────────────────────────
        switchTab: function(tab) {
            document.querySelectorAll('.face-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.face-panel').forEach(p => p.classList.remove('active'));

            var tabEl = document.getElementById('tab' + tab.charAt(0).toUpperCase() + tab.slice(1));
            var panelEl = document.getElementById('panel' + tab.charAt(0).toUpperCase() + tab.slice(1));
            if (tabEl) tabEl.classList.add('active');
            if (panelEl) panelEl.classList.add('active');

            var modeSel = document.getElementById('modeSelectors');
            if (modeSel) modeSel.style.display = (tab === 'camera') ? 'flex' : 'none';

            this.refreshIcons();

            if (tab !== 'camera' && this.cameraStream) {
                this.stopCamera();
            }
        },

        setCaptureMode: function(mode) {
            this.captureMode = mode;
            document.querySelectorAll('.mode-pill').forEach(p => p.classList.remove('active'));
            var pill = document.getElementById('mode' + mode.charAt(0).toUpperCase() + mode.slice(1));
            if (pill) pill.classList.add('active');

            var tracker = document.getElementById('angleTracker');
            if (tracker) {
                tracker.classList.toggle('active', mode === 'multiangle');
            }
            this.resetCaptureState();
            this.refreshIcons();
        },

        resetCaptureState: function() {
            this.cancelCountdown();
            this.livenessVerified = (this.captureMode !== 'liveness');
            this.eyeBlinkDetected = false;
            this.multiAngleStep = 0;
            this.capturedAngleFrames = [];
            this.burstFrames = [];
            this.updateAngleChips();
            this.hidePreview();
        },

        updateAngleChips: function() {
            var self = this;
            var chips = ['angleFrontChip', 'angleLeftChip', 'angleRightChip'];
            chips.forEach(function(id, idx) {
                var chip = document.getElementById(id);
                if (!chip) return;
                chip.className = 'angle-chip';
                if (idx < self.multiAngleStep) chip.classList.add('done');
                else if (idx === self.multiAngleStep) chip.classList.add('current');
            });
        },

        // ── Drag & Drop Upload ────────────────────────────────
        setupDragAndDrop: function() {
            var self = this;
            var zone = document.getElementById('uploadZone');
            if (!zone || zone._dragInitialized) return;
            zone._dragInitialized = true;

            zone.addEventListener('dragover', function(e) {
                e.preventDefault();
                zone.classList.add('drag-over');
            });
            zone.addEventListener('dragleave', function() {
                zone.classList.remove('drag-over');
            });
            zone.addEventListener('drop', function(e) {
                e.preventDefault();
                zone.classList.remove('drag-over');
                var file = e.dataTransfer.files[0];
                if (file && file.type.startsWith('image/')) {
                    var input = document.getElementById('photoInput');
                    if (input) {
                        var dt = new DataTransfer();
                        dt.items.add(file);
                        input.files = dt.files;
                        self.previewImage(input);
                    }
                }
            });
        },

        previewImage: function(input) {
            var file = input.files[0];
            if (!file) return;
            var preview = document.getElementById('previewImg');
            if (preview) {
                preview.src = URL.createObjectURL(file);
                preview.style.display = 'block';
            }
            var upBtn = document.getElementById('uploadBtn');
            if (upBtn) upBtn.disabled = false;
        },

        // ── Model Loader ──────────────────────────────────────
        ensureModelLoaded: async function() {
            if (this.modelReady) return true;
            if (this.modelLoading) return false;
            this.modelLoading = true;

            this.showModelLoading(true, "Loading face detection model...");
            var self = this;

            try {
                if (typeof faceapi === 'undefined') {
                    throw new Error("faceapi script not yet initialized");
                }
                await Promise.all([
                    faceapi.nets.tinyFaceDetector.loadFromUri(self.config.urls.localModels),
                    faceapi.nets.faceLandmark68Net.loadFromUri(self.config.urls.localModels)
                ]);
                self.modelReady = true;
                self.showModelLoading(false, "Face model ready");
                return true;
            } catch(e) {
                console.warn("Local model loading failed, trying fallback CDN...", e);
                try {
                    await Promise.all([
                        faceapi.nets.tinyFaceDetector.loadFromUri(self.config.urls.cdnModels),
                        faceapi.nets.faceLandmark68Net.loadFromUri(self.config.urls.cdnModels)
                    ]);
                    self.modelReady = true;
                    self.showModelLoading(false, "Face model ready");
                    return true;
                } catch(cdnErr) {
                    console.warn("Client faceapi unavailable, using server CV fallback:", cdnErr);
                    self.showModelLoading(false, "Server AI mode active");
                    return false;
                }
            } finally {
                self.modelLoading = false;
            }
        },

        showModelLoading: function(show, text) {
            var badge = document.getElementById('modelLoadingBadge');
            var textEl = document.getElementById('modelLoadingText');
            if (badge) badge.style.display = show ? 'inline-flex' : 'none';
            if (textEl && text) textEl.textContent = text;
        },

        // ── Camera Start / Stop / Errors ──────────────────────
        startCamera: async function() {
            var self = this;
            self.hideCameraError();
            self.hidePreview();
            self.resetCaptureState();

            var video = document.getElementById('cameraFeed');
            var placeholder = document.getElementById('cameraPlaceholder');
            var startBtn = document.getElementById('startCamBtn');
            var capBtn = document.getElementById('captureBtn');
            var stopBtn = document.getElementById('stopCamBtn');

            self.ensureModelLoaded();

            try {
                var constraints = {
                    video: {
                        facingMode: 'user',
                        width: { ideal: 1280, min: 640 },
                        height: { ideal: 720, min: 480 }
                    }
                };
                self.cameraStream = await navigator.mediaDevices.getUserMedia(constraints);
                if (video) {
                    video.srcObject = self.cameraStream;
                    video.style.display = 'block';
                    await video.play();
                }
                if (placeholder) placeholder.style.display = 'none';
                if (startBtn) startBtn.style.display = 'none';
                if (capBtn) { capBtn.style.display = 'inline-flex'; capBtn.disabled = true; }
                if (stopBtn) stopBtn.style.display = 'inline-flex';

                self.setCircleState('red');
                self.setInstruction('red', 'Position your face inside the circle', 'search');
                self.refreshIcons();

                self.runDetectionLoop();

            } catch(err) {
                self.handleCameraError(err);
            }
        },

        handleCameraError: function(err) {
            var errorBanner = document.getElementById('cameraErrorBanner');
            var errorTitle = document.getElementById('cameraErrorTitle');
            var errorMsg = document.getElementById('cameraErrorMessage');
            var placeholder = document.getElementById('cameraPlaceholder');

            if (placeholder) placeholder.style.display = 'none';
            if (!errorBanner) return;
            errorBanner.style.display = 'flex';

            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                errorTitle.textContent = "Camera Access Denied";
                errorMsg.textContent = "Please allow camera access in browser settings (look for the lock or camera icon in your address bar) and refresh.";
            } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                errorTitle.textContent = "No Camera Found";
                errorMsg.textContent = "We could not detect any camera connected to your device. Please connect a webcam or enable your camera.";
            } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
                errorTitle.textContent = "Camera in Use by Another App";
                errorMsg.textContent = "Your camera is currently being used by another application (Zoom, Teams, etc.). Please close other apps and try again.";
            } else {
                errorTitle.textContent = "Camera Error";
                errorMsg.textContent = err.message || "Failed to initialize camera. Please check permissions.";
            }
            this.refreshIcons(errorBanner);
        },

        hideCameraError: function() {
            var errorBanner = document.getElementById('cameraErrorBanner');
            if (errorBanner) errorBanner.style.display = 'none';
        },

        stopCamera: function() {
            this.cancelCountdown();
            if (this.animFrameId) {
                cancelAnimationFrame(this.animFrameId);
                this.animFrameId = null;
            }
            if (this.cameraStream) {
                this.cameraStream.getTracks().forEach(t => t.stop());
                this.cameraStream = null;
            }
            var video = document.getElementById('cameraFeed');
            if (video) video.style.display = 'none';
            var placeholder = document.getElementById('cameraPlaceholder');
            if (placeholder) placeholder.style.display = 'flex';
            var startBtn = document.getElementById('startCamBtn');
            if (startBtn) startBtn.style.display = 'inline-flex';
            var capBtn = document.getElementById('captureBtn');
            if (capBtn) capBtn.style.display = 'none';
            var stopBtn = document.getElementById('stopCamBtn');
            if (stopBtn) stopBtn.style.display = 'none';

            this.setCircleState('red');
            this.setInstruction('idle', 'Click "Start Camera" to begin', 'info');
            this.resetChecklist();
            this.refreshIcons();
        },

        // ── Real-Time Detection Loop ──────────────────────────
        runDetectionLoop: function(timestamp) {
            var self = this;
            if (!self.cameraStream || self.isCapturing) return;

            if (!timestamp || (timestamp - self.lastCheckTime > self.checkThrottleMs)) {
                self.lastCheckTime = timestamp || 0;
                self.processCurrentFrame();
            }

            self.animFrameId = requestAnimationFrame(function(t) {
                self.runDetectionLoop(t);
            });
        },

        processCurrentFrame: async function() {
            var video = document.getElementById('cameraFeed');
            var canvas = document.getElementById('analysisCanvas');
            if (!video || !canvas || video.readyState < 2) return;

            var vw = video.videoWidth || 640;
            var vh = video.videoHeight || 480;
            canvas.width = 320;
            canvas.height = Math.round(320 * (vh / vw));

            var ctx = canvas.getContext('2d', { willReadFrequently: true });
            ctx.save();
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            ctx.restore();

            var brightness = this.calculateCanvasBrightness(ctx, canvas.width, canvas.height);
            var lightingOk = brightness >= 52;

            if (this.modelReady && typeof faceapi !== 'undefined') {
                await this.runClientDetection(video, canvas, ctx, lightingOk, brightness);
            } else {
                await this.runBackendFallbackDetection(canvas, lightingOk);
            }
        },

        calculateCanvasBrightness: function(ctx, w, h) {
            try {
                var imgData = ctx.getImageData(0, 0, w, h);
                var data = imgData.data;
                var sum = 0;
                var step = 4 * 4;
                var count = 0;
                for (var i = 0; i < data.length; i += step) {
                    sum += (0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]);
                    count++;
                }
                return count > 0 ? (sum / count) : 100;
            } catch(e) {
                return 100;
            }
        },

        // ── Client-Side Face Condition Engine ─────────────────
        runClientDetection: async function(video, canvas, ctx, lightingOk, brightness) {
            var self = this;
            var options = new faceapi.TinyFaceDetectorOptions({ inputSize: 224, scoreThreshold: 0.45 });
            var detections = await faceapi.detectAllFaces(video, options).withFaceLandmarks(true);

            var checks = {
                face: false,
                center: false,
                lighting: lightingOk,
                straight: false,
                eyes: false
            };

            // 1. No face found
            if (!detections || detections.length === 0) {
                self.updateChecklist(checks);
                self.setCircleState('red');
                self.setInstruction('red', 'Position your face inside the circle', 'search');
                self.handleCheckFailure();
                return;
            }

            // 2. More than one face
            if (detections.length > 1) {
                checks.face = false;
                self.updateChecklist(checks);
                self.setCircleState('red');
                self.setInstruction('red', 'Only one person should be visible', 'users');
                self.handleCheckFailure();
                return;
            }

            checks.face = true;
            var face = detections[0];
            var box = face.detection.box;
            var landmarks = face.landmarks;

            // 3. Lighting check
            if (!lightingOk) {
                self.updateChecklist(checks);
                self.setCircleState('red');
                self.setInstruction('red', 'Find better lighting', 'sun');
                self.handleCheckFailure();
                return;
            }

            var vw = video.videoWidth;
            var vh = video.videoHeight;
            var faceCenterX = box.x + box.width / 2;
            var faceCenterY = box.y + box.height / 2;

            var guideCenterX = vw / 2;
            var guideCenterY = vh * 0.48;
            var guideRadius = Math.min(vw, vh) * 0.28;

            var offsetDist = Math.hypot(faceCenterX - guideCenterX, faceCenterY - guideCenterY);
            var faceWidth = box.width;
            var sizeRatio = faceWidth / (guideRadius * 2);

            // 4. Face too small / far
            if (sizeRatio < 0.58) {
                checks.center = false;
                self.updateChecklist(checks);
                self.setCircleState('yellow');
                self.setInstruction('yellow', 'Move closer', 'zoom-in');
                self.handleCheckFailure();
                return;
            }

            // 5. Face too big / close
            if (sizeRatio > 1.25) {
                checks.center = false;
                self.updateChecklist(checks);
                self.setCircleState('yellow');
                self.setInstruction('yellow', 'Move back a little', 'zoom-out');
                self.handleCheckFailure();
                return;
            }

            // 6. Not centered
            if (offsetDist > guideRadius * 0.32) {
                checks.center = false;
                self.updateChecklist(checks);
                self.setCircleState('yellow');
                self.setInstruction('yellow', 'Center your face in the circle', 'crosshair');
                self.handleCheckFailure();
                return;
            }

            checks.center = true;

            // 7. Blurry / Moving check
            var nose = landmarks.getNose();
            var noseTip = nose[3] || nose[0];
            var motionDiff = 0;
            if (self.lastNosePos) {
                motionDiff = Math.hypot(noseTip.x - self.lastNosePos.x, noseTip.y - self.lastNosePos.y);
            }
            self.lastNosePos = { x: noseTip.x, y: noseTip.y };

            if (motionDiff > 16) {
                checks.eyes = false;
                self.updateChecklist(checks);
                self.setCircleState('yellow');
                self.setInstruction('yellow', 'Hold still', 'hand');
                self.handleCheckFailure();
                return;
            }

            // 8. Head turned or tilted
            var jaw = landmarks.getJawOutline();
            var leftJaw = jaw[2];
            var rightJaw = jaw[14];
            var distLeft = Math.hypot(noseTip.x - leftJaw.x, noseTip.y - leftJaw.y);
            var distRight = Math.hypot(noseTip.x - rightJaw.x, noseTip.y - rightJaw.y);
            var yawRatio = distLeft / (distRight + 0.001);

            var leftEye = landmarks.getLeftEye();
            var rightEye = landmarks.getRightEye();
            var eyeAngle = Math.atan2(rightEye[3].y - leftEye[0].y, rightEye[3].x - leftEye[0].x) * (180 / Math.PI);

            var isTilted = Math.abs(eyeAngle) > 13;
            var isTurned = (yawRatio < 0.52 || yawRatio > 1.9);

            if (self.captureMode === 'multiangle') {
                if (self.multiAngleStep === 1) {
                    if (yawRatio < 1.3) {
                        self.setCircleState('yellow');
                        self.setInstruction('yellow', 'Turn head slightly to the left', 'arrow-left');
                        self.handleCheckFailure();
                        return;
                    }
                } else if (self.multiAngleStep === 2) {
                    if (yawRatio > 0.75) {
                        self.setCircleState('yellow');
                        self.setInstruction('yellow', 'Turn head slightly to the right', 'arrow-right');
                        self.handleCheckFailure();
                        return;
                    }
                } else if (isTurned || isTilted) {
                    checks.straight = false;
                    self.updateChecklist(checks);
                    self.setCircleState('yellow');
                    self.setInstruction('yellow', 'Look straight at the camera', 'user');
                    self.handleCheckFailure();
                    return;
                }
            } else if (isTurned || isTilted) {
                checks.straight = false;
                self.updateChecklist(checks);
                self.setCircleState('yellow');
                self.setInstruction('yellow', 'Look straight at the camera', 'user');
                self.handleCheckFailure();
                return;
            }

            checks.straight = true;

            // 9. Eyes closed (EAR)
            var leftEAR = self.calculateEAR(leftEye);
            var rightEAR = self.calculateEAR(rightEye);
            var avgEAR = (leftEAR + rightEAR) / 2.0;
            var eyesClosed = (avgEAR < 0.17);

            // 10. Mask / Sunglasses / Hand obstruction
            var mouth = landmarks.getMouth();
            var mouthHeight = Math.hypot(mouth[14].x - mouth[18].x, mouth[14].y - mouth[18].y);
            var mouthWidth = Math.hypot(mouth[0].x - mouth[6].x, mouth[0].y - mouth[6].y);
            var mouthRatio = mouthHeight / (mouthWidth + 0.001);
            var maskSuspected = (mouthRatio < 0.04 || mouthWidth < box.width * 0.18);

            if (maskSuspected) {
                self.updateChecklist(checks);
                self.setCircleState('red');
                self.setInstruction('red', 'Remove mask or glasses', 'shield-alert');
                self.handleCheckFailure();
                return;
            }

            if (eyesClosed) {
                if (self.captureMode === 'liveness' && !self.eyeBlinkDetected) {
                    self.eyeBlinkDetected = true;
                }
                checks.eyes = false;
                self.updateChecklist(checks);
                self.setCircleState('yellow');
                self.setInstruction('yellow', 'Open your eyes', 'eye');
                self.handleCheckFailure();
                return;
            }

            if (self.captureMode === 'liveness' && !self.livenessVerified) {
                if (self.eyeBlinkDetected && avgEAR > 0.22) {
                    self.livenessVerified = true;
                } else {
                    checks.eyes = false;
                    self.updateChecklist(checks);
                    self.setCircleState('yellow');
                    self.setInstruction('yellow', 'Please blink your eyes to verify liveness', 'eye');
                    self.handleCheckFailure();
                    return;
                }
            }

            checks.eyes = true;
            self.updateChecklist(checks);
            self.handleCheckSuccess();
        },

        calculateEAR: function(eye) {
            var p1 = eye[0], p2 = eye[1], p3 = eye[2], p4 = eye[3], p5 = eye[4], p6 = eye[5];
            var v1 = Math.hypot(p2.x - p6.x, p2.y - p6.y);
            var v2 = Math.hypot(p3.x - p5.x, p3.y - p5.y);
            var h = Math.hypot(p1.x - p4.x, p1.y - p4.y);
            return (v1 + v2) / (2.0 * h + 0.001);
        },

        // ── Backend CV Fallback ───────────────────────────────
        runBackendFallbackDetection: async function(canvas, lightingOk) {
            var self = this;
            var frameB64 = canvas.toDataURL('image/jpeg', 0.55);
            try {
                var resp = await fetch(self.config.urls.detectFace, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': self.getCsrf() },
                    body: JSON.stringify({ frame_b64: frameB64 })
                });
                var data = await resp.json();
                var checks = data.checks || { face: false, center: false, lighting: lightingOk, straight: false, eyes: false };
                self.updateChecklist(checks);

                if (data.status === 'success' && data.state === 'green') {
                    self.handleCheckSuccess();
                } else {
                    self.setCircleState(data.state || 'yellow');
                    self.setInstruction(data.state || 'yellow', data.message || 'Position your face inside the circle', 'search');
                    self.handleCheckFailure();
                }
            } catch(e) {
                console.error("Backend detect error:", e);
            }
        },

        // ── Visual Feedback (Lucide Icons) ────────────────────
        setCircleState: function(state) {
            var guide = document.getElementById('faceGuide');
            if (guide) guide.className = 'face-guide-circle state-' + state;
        },

        setInstruction: function(state, message, iconType) {
            var banner = document.getElementById('instructionBanner');
            var textEl = document.getElementById('instructionText');
            var iconWrap = document.getElementById('instructionIconWrap');
            if (!banner || !textEl) return;

            banner.className = 'instruction-banner state-' + state;
            textEl.textContent = message;

            if (iconWrap) {
                var lucideName = 'info';
                if (state === 'green') lucideName = 'check-circle-2';
                else if (state === 'red') lucideName = 'alert-circle';
                else if (state === 'yellow') lucideName = 'alert-triangle';

                if (iconType === 'search') lucideName = 'search';
                else if (iconType === 'users') lucideName = 'users';
                else if (iconType === 'sun') lucideName = 'sun';
                else if (iconType === 'zoom-in') lucideName = 'zoom-in';
                else if (iconType === 'zoom-out') lucideName = 'zoom-out';
                else if (iconType === 'crosshair') lucideName = 'crosshair';
                else if (iconType === 'hand') lucideName = 'hand';
                else if (iconType === 'arrow-left') lucideName = 'arrow-left';
                else if (iconType === 'arrow-right') lucideName = 'arrow-right';
                else if (iconType === 'eye') lucideName = 'eye';
                else if (iconType === 'shield-alert') lucideName = 'shield-alert';
                else if (iconType === 'check') lucideName = 'check-circle-2';

                iconWrap.innerHTML = '<i data-lucide="' + lucideName + '" style="width:20px; height:20px;"></i>';
                this.refreshIcons(iconWrap);
            }
        },

        updateChecklist: function(checks) {
            this.updateCheckItem('checkFace', 'iconFace', checks.face);
            this.updateCheckItem('checkCenter', 'iconCenter', checks.center);
            this.updateCheckItem('checkLighting', 'iconLighting', checks.lighting);
            this.updateCheckItem('checkStraight', 'iconStraight', checks.straight !== undefined ? checks.straight : checks.pose);
            this.updateCheckItem('checkEyes', 'iconEyes', checks.eyes);
        },

        updateCheckItem: function(itemId, iconId, isPassed) {
            var item = document.getElementById(itemId);
            var icon = document.getElementById(iconId);
            if (!item || !icon) return;
            if (isPassed) {
                item.className = 'check-item passed';
                icon.innerHTML = '<i data-lucide="check-circle-2" style="width:16px; height:16px; color:#10b981;"></i>';
            } else {
                item.className = 'check-item failed';
                icon.innerHTML = '<i data-lucide="x-circle" style="width:16px; height:16px; color:#ef4444;"></i>';
            }
            this.refreshIcons(icon);
        },

        resetChecklist: function() {
            var self = this;
            ['checkFace', 'checkCenter', 'checkLighting', 'checkStraight', 'checkEyes'].forEach(function(id) {
                var item = document.getElementById(id);
                if (item) item.className = 'check-item';
            });
            ['iconFace', 'iconCenter', 'iconLighting', 'iconStraight', 'iconEyes'].forEach(function(id) {
                var icon = document.getElementById(id);
                if (icon) {
                    icon.innerHTML = '<i data-lucide="circle" style="width:16px; height:16px; color:var(--text-muted);"></i>';
                    self.refreshIcons(icon);
                }
            });
        },

        // ── Auto-Capture & Burst Selection ────────────────────
        handleCheckSuccess: function() {
            this.setCircleState('green');
            this.setInstruction('green', 'Perfect! Hold still...', 'check');

            var capBtn = document.getElementById('captureBtn');
            if (capBtn) capBtn.disabled = false;

            this.greenStableFrames++;
            if (this.greenStableFrames >= 3 && !this.isCountingDown && !this.isCapturing) {
                this.startCountdown();
            }
        },

        handleCheckFailure: function() {
            this.greenStableFrames = 0;
            this.cancelCountdown();
            var capBtn = document.getElementById('captureBtn');
            if (capBtn) capBtn.disabled = true;
        },

        startCountdown: function() {
            var self = this;
            self.isCountingDown = true;
            self.countdownValue = 3;
            var overlay = document.getElementById('countdownOverlay');
            var numberEl = document.getElementById('countdownNumber');
            if (overlay) overlay.classList.add('active');
            if (numberEl) numberEl.textContent = '3';

            self.countdownTimer = setInterval(function() {
                self.countdownValue--;
                if (self.countdownValue > 0) {
                    if (numberEl) {
                        numberEl.textContent = self.countdownValue;
                        numberEl.style.animation = 'none';
                        numberEl.offsetHeight; // Reflow
                        numberEl.style.animation = 'countPulse 0.9s cubic-bezier(0.34, 1.56, 0.64, 1) infinite';
                    }
                } else {
                    clearInterval(self.countdownTimer);
                    self.countdownTimer = null;
                    self.isCountingDown = false;
                    if (overlay) overlay.classList.remove('active');
                    self.executeBurstCapture();
                }
            }, 900);
        },

        cancelCountdown: function() {
            if (this.countdownTimer) {
                clearInterval(this.countdownTimer);
                this.countdownTimer = null;
            }
            this.isCountingDown = false;
            var overlay = document.getElementById('countdownOverlay');
            if (overlay) overlay.classList.remove('active');
        },

        manualCapture: function() {
            this.cancelCountdown();
            this.executeBurstCapture();
        },

        executeBurstCapture: async function() {
            var self = this;
            if (self.isCapturing) return;
            self.isCapturing = true;

            var video = document.getElementById('cameraFeed');
            var canvas = document.getElementById('captureCanvas');
            var flash = document.getElementById('cameraFlash');
            if (!video || !canvas) return;

            if (flash) {
                flash.classList.add('flash');
                setTimeout(() => flash.classList.remove('flash'), 160);
            }

            canvas.width = 640;
            canvas.height = 480;
            var ctx = canvas.getContext('2d');

            var framesCollected = [];

            for (var f = 0; f < 5; f++) {
                ctx.save();
                ctx.translate(640, 0);
                ctx.scale(-1, 1);
                ctx.drawImage(video, 0, 0, 640, 480);
                ctx.restore();

                var b64 = canvas.toDataURL('image/jpeg', 0.92);
                var score = self.scoreFrameQuality(ctx, 640, 480);
                framesCollected.push({ b64: b64, score: score });

                await new Promise(r => setTimeout(r, 60));
            }

            framesCollected.sort((a, b) => b.score - a.score);
            var best = framesCollected[0];
            self.bestCapturedData = best;
            self.burstFrames = framesCollected.map(f => f.b64);

            if (self.captureMode === 'multiangle') {
                self.capturedAngleFrames.push(best.b64);
                self.multiAngleStep++;
                self.updateAngleChips();

                if (self.multiAngleStep < 3) {
                    self.isCapturing = false;
                    if (self.multiAngleStep === 1) {
                        self.setInstruction('yellow', 'Now turn your head slightly Left (~15°)', 'arrow-left');
                    } else if (self.multiAngleStep === 2) {
                        self.setInstruction('yellow', 'Now turn your head slightly Right (~15°)', 'arrow-right');
                    }
                    return;
                }
            }

            self.showPreview(best);
        },

        scoreFrameQuality: function(ctx, w, h) {
            try {
                var imgData = ctx.getImageData(0, 0, w, h);
                var d = imgData.data;
                var laplacian = 0;
                for (var i = 0; i < d.length - 16; i += 16) {
                    var diff = Math.abs(d[i] - d[i + 4]);
                    laplacian += diff;
                }
                return laplacian;
            } catch(e) {
                return 1000;
            }
        },

        // ── Preview & Confirmation ────────────────────────────
        showPreview: function(bestFrame) {
            var card = document.getElementById('capturePreviewCard');
            var img = document.getElementById('previewCapturedImg');
            var badge = document.getElementById('previewQualityBadge');
            var gallery = document.getElementById('previewAnglesGallery');

            if (img) img.src = bestFrame.b64;
            if (badge) badge.textContent = "Quality: High (Burst 5x selected)";

            if (gallery) {
                gallery.innerHTML = '';
                if (this.captureMode === 'multiangle' && this.capturedAngleFrames.length > 0) {
                    this.capturedAngleFrames.forEach(function(b64) {
                        var thumb = document.createElement('img');
                        thumb.src = b64;
                        thumb.className = 'preview-angle-thumb';
                        gallery.appendChild(thumb);
                    });
                }
            }

            if (card) card.classList.add('active');
            this.setInstruction('green', 'Photo captured! Review below and confirm registration.', 'check');
            this.refreshIcons(card);
        },

        hidePreview: function() {
            var card = document.getElementById('capturePreviewCard');
            if (card) card.classList.remove('active');
        },

        retakePhoto: function() {
            this.hidePreview();
            this.isCapturing = false;
            this.resetCaptureState();
            this.setInstruction('yellow', 'Position your face inside the circle', 'search');
        },

        confirmAndRegister: async function() {
            var self = this;
            if (!self.bestCapturedData) return;

            var confirmBtn = document.getElementById('confirmRegisterBtn');
            var retakeBtn = document.getElementById('retakeBtn');
            if (confirmBtn) {
                confirmBtn.disabled = true;
                confirmBtn.innerHTML = '<span class="model-spinner"></span> Securing Face Profile...';
            }
            if (retakeBtn) retakeBtn.disabled = true;

            self.showCaptureResult('processing', 'Encrypting biometric facial vectors and registering profile...');

            try {
                var payload = {
                    frame_b64: self.bestCapturedData.b64,
                    frames_b64: (self.captureMode === 'multiangle' && self.capturedAngleFrames.length) ? self.capturedAngleFrames : self.burstFrames
                };

                var resp = await fetch(self.config.urls.captureFace, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': self.getCsrf() },
                    body: JSON.stringify(payload)
                });
                var data = await resp.json();

                if (data.status === 'success') {
                    self.showCaptureResult('success', data.message || 'Face registered successfully!');
                    self.setInstruction('green', 'Face profile active & registered!', 'check');
                    self.stopCamera();

                    var topBanner = document.getElementById('topStatusBanner');
                    if (topBanner) {
                        topBanner.className = 'face-status-banner registered';
                        topBanner.innerHTML = `
                            <div class="banner-icon">
                                <i data-lucide="check-circle-2" style="width:24px; height:24px; color:#10b981;"></i>
                            </div>
                            <div class="banner-text">
                                <h3>Face Registered & Active</h3>
                                <p>Your facial profile is active for automatic attendance.</p>
                            </div>
                        `;
                        self.refreshIcons(topBanner);
                    }
                    setTimeout(() => window.location.reload(), 2200);
                } else {
                    self.showCaptureResult('error', data.message || 'Registration failed. Click Retake to try again.');
                    if (confirmBtn) {
                        confirmBtn.disabled = false;
                        confirmBtn.innerHTML = '<i data-lucide="check" style="width:18px; height:18px;"></i> Confirm & Register';
                        self.refreshIcons(confirmBtn);
                    }
                    if (retakeBtn) retakeBtn.disabled = false;
                }
            } catch(e) {
                self.showCaptureResult('error', 'Network error during face registration. Please check your connection and try again.');
                if (confirmBtn) {
                    confirmBtn.disabled = false;
                    confirmBtn.innerHTML = '<i data-lucide="check" style="width:18px; height:18px;"></i> Confirm & Register';
                    self.refreshIcons(confirmBtn);
                }
                if (retakeBtn) retakeBtn.disabled = false;
            }
        },

        showCaptureResult: function(type, msg) {
            var el = document.getElementById('captureResult');
            if (!el) return;
            el.className = type;
            el.innerHTML = msg;
            el.style.display = type === 'processing' ? 'flex' : 'block';
        },

        getCsrf: function() {
            var c = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
            return c ? c.split('=')[1] : '';
        },

        setupTurboHandlers: function() {
            var self = this;
            document.addEventListener('turbo:before-render', function() {
                if (self.cameraStream) self.stopCamera();
            });
            document.addEventListener('turbo:load', function() {
                self.refreshIcons();
            });
        }
    };

    // Expose to window
    window.FaceSetupManager = FaceSetupManager;

    // Backward-compatible global wrappers for inline HTML handlers
    window.startCamera = function() { FaceSetupManager.startCamera(); };
    window.stopCamera = function() { FaceSetupManager.stopCamera(); };
    window.manualCapture = function() { FaceSetupManager.manualCapture(); };
    window.retakePhoto = function() { FaceSetupManager.retakePhoto(); };
    window.confirmAndRegister = function() { FaceSetupManager.confirmAndRegister(); };
    window.switchTab = function(t) { FaceSetupManager.switchTab(t); };
    window.setCaptureMode = function(m) { FaceSetupManager.setCaptureMode(m); };
    window.previewImage = function(i) { FaceSetupManager.previewImage(i); };
    window.saveProfileInfo = function() { FaceSetupManager.saveProfileInfo(); };
    window.closeInfoModal = function() { FaceSetupManager.closeInfoModal(); };

})();
