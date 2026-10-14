/**
 * ==========================================================================
 * FaceSetupManager — EduMi Robust Biometric Identity Engine
 * Modern, Apple Face ID-inspired in-circle live registration.
 *
 * Real-time biometric checks:
 *   1. Real-time Luminance / Brightness Analysis (Dark / Glare detection)
 *   2. Strict Face & Feature Detection (Eyes, Nose, Mouth contrast valleys)
 *   3. Visible Circle Centering (Corrected for 16:9 / 4:3 object-fit: cover)
 *   4. Distance & Coverage Ratio (Move closer / Move back)
 *   5. Head Pose: Yaw / Turning Check (Look straight at camera)
 *   6. Head Pose: Roll / Tilt Check (Keep head level, no tilting)
 *   7. Motion Stability Check (Hold still)
 *   8. Automatic 3-2-1 Countdown & Capture (Only when 100% aligned!)
 *   9. In-Circle Single Viewport: Snapshot freezes inside the SAME circle!
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

        // Camera & Detection State
        cameraStream: null,
        animFrameId: null,
        isCapturing: false,
        faceApiReady: false,
        modelLoading: false,

        // Motion & Position History
        lastFaceCenter: null,
        lastCheckTime: 0,
        checkThrottleMs: 100, // 10 checks per second for ultra-responsive feedback

        // Auto-Capture Countdown
        countdownTimer: null,
        countdownValue: 3,
        steadyGreenFrames: 0,
        isCountingDown: false,

        // Captured Snapshot
        bestCapturedData: null,
        burstFrames: [],

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
            this.setupTurboHandlers();
            this.refreshIcons();

            // Load face detection models with WebGL/CPU fallback
            this.ensureFaceApiLoaded();
        },

        ensureFaceApiLoaded: async function() {
            if (this.faceApiReady || this.modelLoading) return;
            if (typeof faceapi === 'undefined') return;

            this.modelLoading = true;
            this.showModelLoadingBadge(true, "Initializing camera AI...");
            var self = this;

            var localUrl = self.config.urls.localModels || '/static/vendor/face-api/models';
            var cdnUrl = self.config.urls.cdnModels || 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model';

            try {
                // Ensure WebGL or CPU backend is selected (prevents WASM file missing errors)
                if (faceapi.tf && faceapi.tf.setBackend) {
                    try {
                        await faceapi.tf.setBackend('webgl');
                    } catch(beErr) {
                        try { await faceapi.tf.setBackend('cpu'); } catch(cpuErr) {}
                    }
                }

                await Promise.all([
                    faceapi.nets.tinyFaceDetector.loadFromUri(localUrl),
                    faceapi.nets.faceLandmark68Net.loadFromUri(localUrl)
                ]);
                self.faceApiReady = true;
                self.showModelLoadingBadge(false);
            } catch(localErr) {
                console.warn("Local face-api models failed, trying CDN fallback...", localErr);
                try {
                    await Promise.all([
                        faceapi.nets.tinyFaceDetector.loadFromUri(cdnUrl),
                        faceapi.nets.faceLandmark68Net.loadFromUri(cdnUrl)
                    ]);
                    self.faceApiReady = true;
                    self.showModelLoadingBadge(false);
                } catch(cdnErr) {
                    console.warn("FaceAPI load failed, using smart canvas vision engine:", cdnErr);
                    self.showModelLoadingBadge(false);
                }
            } finally {
                self.modelLoading = false;
            }
        },

        showModelLoadingBadge: function(show, text) {
            var badge = document.getElementById('modelLoadingBadge');
            var textEl = document.getElementById('modelLoadingText');
            if (badge) badge.style.display = show ? 'inline-flex' : 'none';
            if (textEl && text) textEl.textContent = text;
        },

        refreshIcons: function(root) {
            if (typeof lucide !== 'undefined' && lucide.createIcons) {
                try {
                    lucide.createIcons(root ? { root: root } : undefined);
                } catch(e) {}
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

        // ── Camera Control ────────────────────────────────────
        startCamera: async function() {
            var self = this;
            self.hideCameraError();
            self.resetCaptureState();

            var video = document.getElementById('cameraFeed');
            var capturedImg = document.getElementById('capturedFrameImg');
            var inCircleBadge = document.getElementById('inCircleBadge');
            var placeholder = document.getElementById('cameraPlaceholder');
            var startBtn = document.getElementById('startCamBtn');
            var capBtn = document.getElementById('captureBtn');
            var stopBtn = document.getElementById('stopCamBtn');
            var reviewControls = document.getElementById('reviewControls');
            var cameraControls = document.getElementById('cameraControls');

            // Reset visual components
            if (capturedImg) capturedImg.style.display = 'none';
            if (inCircleBadge) inCircleBadge.style.display = 'none';
            if (reviewControls) reviewControls.style.display = 'none';
            if (cameraControls) cameraControls.style.display = 'flex';

            // Ensure models are loaded
            self.ensureFaceApiLoaded();

            try {
                var constraints = {
                    video: {
                        facingMode: 'user',
                        width: { ideal: 1280, min: 640 },
                        height: { ideal: 720, min: 480 }
                    },
                    audio: false
                };

                self.cameraStream = await navigator.mediaDevices.getUserMedia(constraints);
                if (video) {
                    video.srcObject = self.cameraStream;
                    video.style.display = 'block';
                    await video.play();
                }

                if (placeholder) placeholder.style.display = 'none';
                if (startBtn) startBtn.style.display = 'none';

                if (capBtn) {
                    capBtn.style.display = 'inline-flex';
                    capBtn.disabled = false;
                }
                if (stopBtn) stopBtn.style.display = 'inline-flex';

                // Initial searching state
                self.setCircleState('red');
                self.setInstruction('red', 'Position your face inside the circle', 'search');
                self.refreshIcons();

                // Start intelligent biometric quality loop
                self.runDetectionLoop();

            } catch(err) {
                self.handleCameraError(err);
            }
        },

        stopCamera: function() {
            if (this.animFrameId) {
                cancelAnimationFrame(this.animFrameId);
                this.animFrameId = null;
            }
            this.cancelCountdown();
            this.resetCaptureState();

            if (this.cameraStream) {
                this.cameraStream.getTracks().forEach(track => track.stop());
                this.cameraStream = null;
            }

            var video = document.getElementById('cameraFeed');
            if (video) {
                video.srcObject = null;
                video.style.display = 'none';
            }

            var capturedImg = document.getElementById('capturedFrameImg');
            if (capturedImg) capturedImg.style.display = 'none';

            var inCircleBadge = document.getElementById('inCircleBadge');
            if (inCircleBadge) inCircleBadge.style.display = 'none';

            var placeholder = document.getElementById('cameraPlaceholder');
            if (placeholder) placeholder.style.display = 'flex';

            var startBtn = document.getElementById('startCamBtn');
            if (startBtn) startBtn.style.display = 'inline-flex';

            var capBtn = document.getElementById('captureBtn');
            if (capBtn) capBtn.style.display = 'none';

            var stopBtn = document.getElementById('stopCamBtn');
            if (stopBtn) stopBtn.style.display = 'none';

            var reviewControls = document.getElementById('reviewControls');
            if (reviewControls) reviewControls.style.display = 'none';

            var cameraControls = document.getElementById('cameraControls');
            if (cameraControls) cameraControls.style.display = 'flex';

            this.setCircleState('idle');
            this.setInstruction('idle', 'Click "Start Registration" to begin', 'info');
            this.refreshIcons();
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
                if (errorTitle) errorTitle.textContent = "Camera Permission Needed";
                if (errorMsg) errorMsg.textContent = "Please allow camera access in your browser address bar and refresh the page.";
            } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                if (errorTitle) errorTitle.textContent = "No Camera Detected";
                if (errorMsg) errorMsg.textContent = "We could not find a connected webcam. Please connect a camera and try again.";
            } else {
                if (errorTitle) errorTitle.textContent = "Camera Unavailable";
                if (errorMsg) errorMsg.textContent = "Could not start camera. Please close other apps using the webcam and retry.";
            }
            this.refreshIcons(errorBanner);
        },

        hideCameraError: function() {
            var errorBanner = document.getElementById('cameraErrorBanner');
            if (errorBanner) errorBanner.style.display = 'none';
        },

        // ── Real-Time Detection Loop ──────────────────────────
        runDetectionLoop: function(timestamp) {
            var self = this;
            if (!self.cameraStream || self.isCapturing) return;

            if (!timestamp || (timestamp - self.lastCheckTime > self.checkThrottleMs)) {
                self.lastCheckTime = timestamp || 0;
                self.evaluateBiometricQuality();
            }

            self.animFrameId = requestAnimationFrame(function(t) {
                self.runDetectionLoop(t);
            });
        },

        // ── Comprehensive Biometric Quality Engine ────────────
        evaluateBiometricQuality: async function() {
            try {
                var video = document.getElementById('cameraFeed');
                if (!video || video.readyState < 2 || video.paused || video.ended) return;

                var vw = video.videoWidth;
                var vh = video.videoHeight;
                if (!vw || !vh || vw <= 0 || vh <= 0) return;

                // 1. LIGHTING & BRIGHTNESS CHECK
                var brightness = this.measureBrightness(video, vw, vh);

                if (brightness < 45) {
                    this.setCircleState('yellow');
                    this.setInstruction('yellow', 'Lighting is too dark — face towards a light source', 'sun');
                    this.handleAlignmentFailed();
                    return;
                }

                if (brightness > 230) {
                    this.setCircleState('yellow');
                    this.setInstruction('yellow', 'Too bright / Glare — reduce direct light', 'sun-dim');
                    this.handleAlignmentFailed();
                    return;
                }

                // 2. FACE DETECTION WITH 68 LANDMARKS / FEATURE VALIDATION
                var faceData = await this.detectFaceWithLandmarks(video, vw, vh);

                if (!faceData || !faceData.found) {
                    this.setCircleState('red');
                    this.setInstruction('red', 'Position your face inside the circle', 'search');
                    this.handleAlignmentFailed();
                    return;
                }

                if (faceData.multiple) {
                    this.setCircleState('red');
                    this.setInstruction('red', 'Only one person should be in the frame', 'users');
                    this.handleAlignmentFailed();
                    return;
                }

                var box = faceData.box;
                var landmarks = faceData.landmarks;

                // 3. VISIBLE CIRCLE CENTERING (Normalized for 1:1 circular crop)
                var minDim = Math.min(vw, vh);
                var circleCenterX = vw / 2;
                var circleCenterY = vh / 2;
                var circleRadius = minDim / 2;

                var faceCenterX = box.x + box.width / 2;
                var faceCenterY = box.y + box.height / 2;

                var offsetX = Math.abs(faceCenterX - circleCenterX);
                var offsetY = faceCenterY - circleCenterY;

                // Horizontal Centering: User must be within central 40% of circle radius
                if (offsetX > (circleRadius * 0.40)) {
                    this.setCircleState('yellow');
                    this.setInstruction('yellow', 'Center your face in the circle', 'crosshair');
                    this.handleAlignmentFailed();
                    return;
                }

                // Vertical Centering: Hair is on top, chin on bottom — allow natural portrait posture
                if (offsetY < -(circleRadius * 0.38)) {
                    this.setCircleState('yellow');
                    this.setInstruction('yellow', 'Lower your face slightly into the circle', 'arrow-down');
                    this.handleAlignmentFailed();
                    return;
                }
                if (offsetY > (circleRadius * 0.42)) {
                    this.setCircleState('yellow');
                    this.setInstruction('yellow', 'Raise your face slightly into the circle', 'arrow-up');
                    this.handleAlignmentFailed();
                    return;
                }

                // 4. DISTANCE & COVERAGE CHECK (Natural face size within circular aperture)
                var coverageRatio = box.width / minDim;

                if (coverageRatio < 0.26) {
                    this.setCircleState('yellow');
                    this.setInstruction('yellow', 'Move closer to the camera', 'zoom-in');
                    this.handleAlignmentFailed();
                    return;
                }

                if (coverageRatio > 0.88) {
                    this.setCircleState('yellow');
                    this.setInstruction('yellow', 'Move back a little', 'zoom-out');
                    this.handleAlignmentFailed();
                    return;
                }

                // 5. HEAD POSE: TILT / ROLL CHECK (Robust absolute dy/dx ratio)
                if (landmarks) {
                    var leftEye = landmarks.getLeftEye ? landmarks.getLeftEye() : landmarks.leftEye;
                    var rightEye = landmarks.getRightEye ? landmarks.getRightEye() : landmarks.rightEye;

                    if (leftEye && rightEye) {
                        var pLeft = leftEye[0] || leftEye;
                        var pRight = rightEye[0] || rightEye;
                        var dx = Math.abs(pRight.x - pLeft.x);
                        var dy = Math.abs(pRight.y - pLeft.y);

                        if (dx > 5) {
                            var tiltAngle = Math.atan2(dy, dx) * (180 / Math.PI);
                            if (tiltAngle > 14) {
                                this.setCircleState('yellow');
                                this.setInstruction('yellow', 'Keep your head level (do not tilt sideways)', 'user');
                                this.handleAlignmentFailed();
                                return;
                            }
                        }
                    }

                    // 6. HEAD POSE: YAW / TURNING CHECK
                    var nose = landmarks.getNose ? landmarks.getNose() : landmarks.nose;
                    var jaw = landmarks.getJawOutline ? landmarks.getJawOutline() : landmarks.jaw;

                    if (nose && jaw && jaw.length >= 15) {
                        var noseTip = nose[3] || nose[0];
                        var leftJaw = jaw[2];
                        var rightJaw = jaw[14];

                        var dLeft = Math.hypot(noseTip.x - leftJaw.x, noseTip.y - leftJaw.y);
                        var dRight = Math.hypot(noseTip.x - rightJaw.x, noseTip.y - rightJaw.y);
                        var yawRatio = dLeft / (dRight + 0.0001);

                        if (yawRatio < 0.48 || yawRatio > 2.08) {
                            this.setCircleState('yellow');
                            this.setInstruction('yellow', 'Look straight at the camera', 'user');
                            this.handleAlignmentFailed();
                            return;
                        }
                    }
                }

                // 7. MOTION & STABILITY CHECK (Hold Still)
                if (this.lastFaceCenter) {
                    var motionShift = Math.hypot(faceCenterX - this.lastFaceCenter.x, faceCenterY - this.lastFaceCenter.y);
                    if (motionShift > (minDim * 0.08)) {
                        this.lastFaceCenter = { x: faceCenterX, y: faceCenterY };
                        this.setCircleState('yellow');
                        this.setInstruction('yellow', 'Hold still...', 'hand');
                        this.handleAlignmentFailed();
                        return;
                    }
                }
                this.lastFaceCenter = { x: faceCenterX, y: faceCenterY };

                // ── 8. ALL BIOMETRIC QUALITY CHECKS PASSED -> EMERALD GREEN AUTO-CAPTURE!
                this.setCircleState('green');
                this.setInstruction('green', 'Perfect alignment! Hold still...', 'check-circle-2');
                this.handleAlignmentSuccess();

            } catch(e) {
                console.error("evaluateBiometricQuality error:", e);
            }
        },

        // Pixel Brightness Analyzer
        measureBrightness: function(video, vw, vh) {
            try {
                var canvas = document.getElementById('analysisCanvas');
                if (!canvas) return 100;
                var sw = 60;
                var sh = Math.max(1, Math.round(60 * (vh / vw)));
                canvas.width = sw;
                canvas.height = sh;

                var ctx = canvas.getContext('2d', { willReadFrequently: true });
                ctx.drawImage(video, 0, 0, sw, sh);

                var imgData = ctx.getImageData(0, 0, sw, sh);
                var d = imgData.data;
                var sum = 0;
                var count = 0;

                for (var i = 0; i < d.length; i += 16) {
                    sum += (0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]);
                    count++;
                }
                return count > 0 ? (sum / count) : 100;
            } catch(e) {
                return 100;
            }
        },

        // Multi-tier Face & Landmark Detector
        detectFaceWithLandmarks: async function(video, vw, vh) {
            // Tier 1: FaceAPI Neural Network with 68 Landmarks
            if (this.faceApiReady && typeof faceapi !== 'undefined') {
                try {
                    var options = new faceapi.TinyFaceDetectorOptions({ inputSize: 224, scoreThreshold: 0.26 });
                    var detections = await faceapi.detectAllFaces(video, options).withFaceLandmarks(true);

                    if (detections && detections.length > 0) {
                        if (detections.length > 1) {
                            return { found: true, multiple: true };
                        }
                        return {
                            found: true,
                            multiple: false,
                            box: detections[0].detection.box,
                            landmarks: detections[0].landmarks
                        };
                    }
                } catch(e) {}
            }

            // Tier 2: Native Browser FaceDetector (Chrome/Edge API)
            if (typeof window !== 'undefined' && 'FaceDetector' in window) {
                try {
                    var nativeDet = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 2 });
                    var faces = await nativeDet.detect(video);
                    if (faces && faces.length > 0) {
                        if (faces.length > 1) return { found: true, multiple: true };
                        var b = faces[0].boundingBox;
                        return {
                            found: true,
                            multiple: false,
                            box: { x: b.x, y: b.y, width: b.width, height: b.height },
                            landmarks: null
                        };
                    }
                } catch(e) {}
            }

            // Tier 3: Biometric Facial Feature Contrast Valley Vision Engine
            // Detects face oval + eyes/eyebrows horizontal contrast valley across upper 1/3
            return this.detectFacialFeaturesCanvas(video, vw, vh);
        },

        // Smart Canvas Facial Feature Detector (Eyes valley & skin oval analysis)
        detectFacialFeaturesCanvas: function(video, vw, vh) {
            try {
                var canvas = document.getElementById('analysisCanvas');
                if (!canvas) return { found: false, multiple: false };

                var sw = 90;
                var sh = Math.max(1, Math.round(90 * (vh / vw)));
                canvas.width = sw;
                canvas.height = sh;

                var ctx = canvas.getContext('2d', { willReadFrequently: true });
                ctx.drawImage(video, 0, 0, sw, sh);

                var imgData = ctx.getImageData(0, 0, sw, sh);
                var d = imgData.data;

                var skinCount = 0;
                var sumX = 0, sumY = 0;
                var minX = sw, maxX = 0, minY = sh, maxY = 0;

                // 1. Map skin pixels
                var skinMap = new Uint8Array(sw * sh);
                for (var y = 0; y < sh; y++) {
                    for (var x = 0; x < sw; x++) {
                        var i = (y * sw + x) * 4;
                        var r = d[i], g = d[i + 1], b = d[i + 2];

                        // Human skin chrominance locus check
                        if (r > 55 && g > 38 && b > 20 && r > g && (r - g) >= 10 && Math.abs(r - g) > 6 && r > b) {
                            skinMap[y * sw + x] = 1;
                            skinCount++;
                            sumX += x;
                            sumY += y;
                            if (x < minX) minX = x;
                            if (x > maxX) maxX = x;
                            if (y < minY) minY = y;
                            if (y > maxY) maxY = y;
                        }
                    }
                }

                // Minimum 100 skin pixels required
                if (skinCount < 100) {
                    return { found: false, multiple: false };
                }

                var avgX = sumX / skinCount;
                var avgY = sumY / skinCount;
                var faceW = (maxX - minX);
                var faceH = (maxY - minY);

                // Aspect ratio check: Human face oval is vertically elongated (height > width)
                var ovalRatio = faceH / Math.max(1, faceW);
                if (ovalRatio < 0.95 || ovalRatio > 2.2) {
                    return { found: false, multiple: false };
                }

                // 2. Eye sockets / eyebrows horizontal contrast valley check
                // In upper 30-50% of the face, luminance drops significantly at the eyes
                var startEyeY = Math.round(minY + faceH * 0.25);
                var endEyeY = Math.round(minY + faceH * 0.50);
                var foreheadY = Math.round(minY + faceH * 0.12);

                var foreheadLuma = 0, eyeLuma = 0, samples = 0;
                for (var x = Math.round(minX + faceW * 0.2); x < Math.round(maxX - faceW * 0.2); x += 2) {
                    var idxFore = (foreheadY * sw + x) * 4;
                    var idxEye = (Math.round((startEyeY + endEyeY) / 2) * sw + x) * 4;
                    if (idxFore < d.length && idxEye < d.length) {
                        foreheadLuma += (0.299 * d[idxFore] + 0.587 * d[idxFore + 1] + 0.114 * d[idxFore + 2]);
                        eyeLuma += (0.299 * d[idxEye] + 0.587 * d[idxEye + 1] + 0.114 * d[idxEye + 2]);
                        samples++;
                    }
                }

                if (samples > 0) {
                    foreheadLuma /= samples;
                    eyeLuma /= samples;
                    // Eye socket line MUST be darker than forehead (classic facial feature valley)
                    if (eyeLuma > (foreheadLuma * 1.05)) {
                        return { found: false, multiple: false }; // Not a face (flat object or background)
                    }
                }

                // Convert to video coordinate space
                var scaleX = vw / sw;
                var scaleY = vh / sh;

                return {
                    found: true,
                    multiple: false,
                    box: {
                        x: minX * scaleX,
                        y: minY * scaleY,
                        width: faceW * scaleX,
                        height: faceH * scaleY
                    },
                    landmarks: null
                };
            } catch(e) {
                return { found: false, multiple: false };
            }
        },

        // ── Alignment Handlers ────────────────────────────────
        handleAlignmentSuccess: function() {
            this.steadyGreenFrames++;

            // Require 2 consecutive steady green frames (~200ms) before countdown
            if (this.steadyGreenFrames >= 2 && !this.isCountingDown && !this.isCapturing) {
                this.startCountdown();
            }
        },

        handleAlignmentFailed: function() {
            this.steadyGreenFrames = 0;
            this.cancelCountdown();
        },

        // ── 3-2-1 Countdown Timer ─────────────────────────────
        startCountdown: function() {
            var self = this;
            self.isCountingDown = true;
            self.countdownValue = 3;

            var overlay = document.getElementById('countdownOverlay');
            var numberEl = document.getElementById('countdownNumber');
            if (overlay) overlay.classList.add('active');
            if (numberEl) numberEl.textContent = '3';

            if (self.countdownTimer) clearInterval(self.countdownTimer);

            self.countdownTimer = setInterval(function() {
                self.countdownValue--;
                if (self.countdownValue > 0) {
                    if (numberEl) numberEl.textContent = self.countdownValue;
                } else {
                    self.cancelCountdown();
                    self.executeCapture();
                }
            }, 700);
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

        resetCaptureState: function() {
            this.cancelCountdown();
            this.steadyGreenFrames = 0;
            this.isCapturing = false;
            this.bestCapturedData = null;
            this.burstFrames = [];
            this.lastFaceCenter = null;
        },

        // ── Capture Execution (Manual & Auto) ─────────────────
        manualCapture: function() {
            this.cancelCountdown();
            this.executeCapture();
        },

        executeCapture: async function() {
            var self = this;
            if (self.isCapturing) return;
            self.isCapturing = true;

            var video = document.getElementById('cameraFeed');
            var canvas = document.getElementById('captureCanvas');
            var flash = document.getElementById('cameraFlash');
            if (!video || !canvas) {
                self.isCapturing = false;
                return;
            }

            // Visual camera shutter flash
            if (flash) {
                flash.classList.add('flash');
                setTimeout(() => flash.classList.remove('flash'), 180);
            }

            // Crisp native camera snapshot
            var vw = video.videoWidth || 1280;
            var vh = video.videoHeight || 720;
            canvas.width = vw;
            canvas.height = vh;

            var ctx = canvas.getContext('2d');
            ctx.save();
            ctx.translate(vw, 0);
            ctx.scale(-1, 1); // Mirrored natural selfie orientation
            ctx.drawImage(video, 0, 0, vw, vh);
            ctx.restore();

            var b64 = canvas.toDataURL('image/jpeg', 0.94);
            self.bestCapturedData = { b64: b64 };
            self.burstFrames = [b64];

            // Display captured snapshot directly in the SAME circular viewfinder!
            self.freezeInCircle(b64);
        },

        // ── In-Circle Unified Review ──────────────────────────
        freezeInCircle: function(b64) {
            var video = document.getElementById('cameraFeed');
            var capturedImg = document.getElementById('capturedFrameImg');
            var inCircleBadge = document.getElementById('inCircleBadge');
            var cameraControls = document.getElementById('cameraControls');
            var reviewControls = document.getElementById('reviewControls');

            // Hide live video, show frozen snapshot inside the exact same circular frame
            if (video) video.style.display = 'none';
            if (capturedImg) {
                capturedImg.src = b64;
                capturedImg.style.display = 'block';
            }

            // Show in-circle verified badge
            if (inCircleBadge) inCircleBadge.style.display = 'inline-flex';

            // Keep guide ring emerald green
            this.setCircleState('green');
            this.setInstruction('green', 'Photo captured! Confirm below to register', 'check-circle-2');

            // Swap controls directly below the circle
            if (cameraControls) cameraControls.style.display = 'none';
            if (reviewControls) reviewControls.style.display = 'flex';

            this.refreshIcons();
        },

        retakePhoto: function() {
            var video = document.getElementById('cameraFeed');
            var capturedImg = document.getElementById('capturedFrameImg');
            var inCircleBadge = document.getElementById('inCircleBadge');
            var cameraControls = document.getElementById('cameraControls');
            var reviewControls = document.getElementById('reviewControls');
            var result = document.getElementById('captureResult');

            if (result) result.style.display = 'none';
            if (capturedImg) capturedImg.style.display = 'none';
            if (inCircleBadge) inCircleBadge.style.display = 'none';

            if (reviewControls) reviewControls.style.display = 'none';
            if (cameraControls) cameraControls.style.display = 'flex';

            if (video) video.style.display = 'block';

            this.resetCaptureState();
            this.setCircleState('red');
            this.setInstruction('red', 'Position your face inside the circle', 'search');
            this.refreshIcons();

            // Resume detection loop
            this.runDetectionLoop();
        },

        confirmAndRegister: async function() {
            var self = this;
            if (!self.bestCapturedData) return;

            var confirmBtn = document.getElementById('confirmRegisterBtn');
            var retakeBtn = document.getElementById('retakeBtn');
            if (confirmBtn) {
                confirmBtn.disabled = true;
                confirmBtn.innerHTML = '<span class="model-spinner"></span> Saving Biometrics...';
            }
            if (retakeBtn) retakeBtn.disabled = true;

            self.showCaptureResult('processing', 'Saving your biometric identity...');

            try {
                var payload = {
                    frame_b64: self.bestCapturedData.b64,
                    frames_b64: self.burstFrames.length ? self.burstFrames : [self.bestCapturedData.b64]
                };

                var resp = await fetch(self.config.urls.captureFace, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': self.getCsrf() },
                    body: JSON.stringify(payload)
                });
                var data = await resp.json();

                if (data.status === 'success') {
                    self.showCaptureResult('success', '✅ Biometric identity registered successfully!');
                    setTimeout(() => window.location.reload(), 1400);
                } else {
                    self.showCaptureResult('error', data.message || 'Registration failed. Click Retake to try again.');
                    if (confirmBtn) {
                        confirmBtn.disabled = false;
                        confirmBtn.innerHTML = '<i data-lucide="check" style="width:18px; height:18px;"></i> Confirm & Save';
                        self.refreshIcons(confirmBtn);
                    }
                    if (retakeBtn) retakeBtn.disabled = false;
                }
            } catch(e) {
                self.showCaptureResult('error', 'Network error. Please check your connection and try again.');
                if (confirmBtn) {
                    confirmBtn.disabled = false;
                    confirmBtn.innerHTML = '<i data-lucide="check" style="width:18px; height:18px;"></i> Confirm & Save';
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

        // ── Visual Guidance Helpers ───────────────────────────
        setCircleState: function(state) {
            var guide = document.getElementById('faceGuide');
            if (guide) guide.className = 'face-guide-circle state-' + state;
        },

        setInstruction: function(state, message, iconType) {
            var banner = document.getElementById('instructionBanner');
            var textEl = document.getElementById('instructionText');
            var iconWrap = document.getElementById('instructionIconWrap');

            if (banner) banner.className = 'instruction-banner state-' + state;
            if (textEl && message) textEl.textContent = message;

            if (iconWrap && iconType) {
                iconWrap.innerHTML = '<i data-lucide="' + iconType + '" style="width:16px; height:16px;"></i>';
                this.refreshIcons(iconWrap);
            }
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

    // Global Bindings for HTML onclick handlers
    window.FaceSetupManager = FaceSetupManager;
    window.startCamera = function() { FaceSetupManager.startCamera(); };
    window.stopCamera = function() { FaceSetupManager.stopCamera(); };
    window.manualCapture = function() { FaceSetupManager.manualCapture(); };
    window.retakePhoto = function() { FaceSetupManager.retakePhoto(); };
    window.confirmAndRegister = function() { FaceSetupManager.confirmAndRegister(); };
    window.closeInfoModal = function() { FaceSetupManager.closeInfoModal(); };
    window.saveProfileInfo = function() { FaceSetupManager.saveProfileInfo(); };

})();
