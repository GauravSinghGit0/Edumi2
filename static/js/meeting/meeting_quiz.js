        // ── Live Meeting Quiz Engine & Anti-Cheating System ──────────────────────────
        let activeLiveQuiz = null;
        let currentQuizQuestionIndex = 0;
        let studentQuizAnswers = {};
        let studentTabSwitchCount = 0;
        let quizStartTime = null;
        let isQuizActive = false;

        // Teacher Live Quiz State Tracking
        let teacherLiveQuizSubmissions = new Map();
        let lastWarningTimestamp = 0;

        // Single Source of Truth for Student User Profile
        function getLocalStudentIdentity() {
            return String(window.meetingConfig?.currentUserId || _d.userId || '0');
        }

        function getLocalStudentName() {
            return String(window.meetingConfig?.currentDisplayName || window.meetingConfig?.currentUsername || _d.displayName || _d.username || 'Student');
        }

        function toggleQuizPanel() {
            const sidebar = document.getElementById('meetSidebar');
            const isSidebarOpen = sidebar && sidebar.style.display !== 'none';
            const quizTab = document.getElementById('quizTabBtn');
            const isQuizActiveTab = quizTab && quizTab.classList.contains('active');

            if (isSidebarOpen && isQuizActiveTab) {
                toggleSidebar();
            } else {
                openSidebar('quiz');
            }
        }

        function showQuizTabButton(show) {
            const btn = document.getElementById('quizTabBtn');
            if (!btn) return;
            if (show) {
                btn.style.display = 'inline-flex';
            } else {
                btn.style.display = 'none';
                if (btn.classList.contains('active')) {
                    switchSidebarTab('people');
                }
            }
        }

        function showQuizToggleButton(show) {
            const btn = document.getElementById('activeQuizToggleBtn');
            if (btn) btn.style.display = show ? 'flex' : 'none';
            showQuizTabButton(show);
        }

        let teacherQuizStartTimestamp = null;
        let teacherQuizTimerInterval = null;

        function startTeacherQuizTimer() {
            if (teacherQuizTimerInterval) clearInterval(teacherQuizTimerInterval);
            teacherQuizStartTimestamp = Date.now();

            const timerEl = document.getElementById('teacherQuizTimerText');
            if (timerEl) timerEl.textContent = '00:00';

            teacherQuizTimerInterval = setInterval(() => {
                if (!teacherQuizStartTimestamp) return;
                const elapsedSec = Math.floor((Date.now() - teacherQuizStartTimestamp) / 1000);
                const mins = String(Math.floor(elapsedSec / 60)).padStart(2, '0');
                const secs = String(elapsedSec % 60).padStart(2, '0');
                if (timerEl) timerEl.textContent = `${mins}:${secs}`;
            }, 1000);
        }

        function stopTeacherQuizTimer() {
            if (teacherQuizTimerInterval) {
                clearInterval(teacherQuizTimerInterval);
                teacherQuizTimerInterval = null;
            }
        }

        function confirmAndEndQuiz() {
            if (!isHost) return;
            if (!confirm('Are you sure you want to end the live quiz for all students?\n\nAll students currently taking the quiz will have their answers automatically saved and submitted immediately.')) {
                return;
            }

            const payload = {
                type: 'teacher_ended_quiz',
                quiz_id: activeLiveQuiz ? activeLiveQuiz.id : null,
                timestamp: new Date().toLocaleTimeString()
            };

            broadcastQuizEvent(payload);

            if (window.signalingWs && window.signalingWs.readyState === WebSocket.OPEN) {
                try { window.signalingWs.send(JSON.stringify(payload)); } catch (_) { }
            }

            stopTeacherQuizTimer();
            activeLiveQuiz = null;
            isQuizActive = false;

            const btn = document.getElementById('endQuizBtn');
            if (btn) {
                btn.disabled = true;
                btn.style.background = '#475569';
                btn.style.cursor = 'not-allowed';
                btn.innerHTML = '<span>Quiz Ended for Everyone</span>';
            }

            const subCount = document.getElementById('teacherMonitorSubCount');
            if (subCount) {
                subCount.textContent = 'Quiz Ended';
                subCount.style.background = '#64748b';
            }

            showNotification('🛑 Live Quiz has been ended for all students. Current progress submitted.', 'info');
            showQuizToggleButton(false);
            try { sessionStorage.removeItem(`active_live_quiz_${meetingCode}`); } catch (_) { }

            if (typeof switchSidebarTab === 'function') {
                switchSidebarTab('people');
            }
        }

        function openTeacherQuizMonitor(quiz) {
            const quizNameEl = document.getElementById('teacherMonitorQuizName');
            if (quizNameEl && quiz) quizNameEl.textContent = quiz.title;

            teacherLiveQuizSubmissions.clear();

            let participants = typeof getRemoteParticipants === 'function' ? getRemoteParticipants() : [];
            participants.forEach(p => {
                if (!p || !p.identity) return;
                const uid = String(p.identity);
                const myId = String(window.meetingConfig?.currentUserId || currentUserId || '');
                const hId = String(window.meetingConfig?.hostId || hostId || '');
                if (uid === myId || uid === hId) return;

                let name = p.name;
                if (window.IdentityDirectory) {
                    const userRec = window.IdentityDirectory.resolve(uid, name);
                    if (userRec && userRec.displayName) name = userRec.displayName;
                }
                if (!name) name = uid;

                teacherLiveQuizSubmissions.set(uid, {
                    student_name: name,
                    student_id: uid,
                    tab_switch_count: 0,
                    copy_attempts: 0,
                    in_progress: false,
                    submitted: false
                });
            });

            const btn = document.getElementById('endQuizBtn');
            if (btn) {
                btn.disabled = false;
                btn.style.background = 'linear-gradient(135deg, #ff4b6e, #ef4444)';
                btn.style.cursor = 'pointer';
                btn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="4" y="4" width="16" height="16" rx="3" ry="3"/></svg>
            <span>End Quiz</span>`;
            }

            showQuizToggleButton(true);
            startTeacherQuizTimer();
            updateTeacherMonitorStudentList();
            openSidebar('quiz');
        }

        function closeTeacherQuizMonitor() {
            toggleSidebar();
        }

        function handleTeacherQuizEvent(msg) {
            if (!isHost) return;

            const studentId = String(msg.student_id || '');
            const studentName = String(msg.student_name || 'Student');

            let targetKey = studentId || studentName;
            let sub = teacherLiveQuizSubmissions.get(targetKey) || {
                student_name: studentName,
                student_id: studentId,
                tab_switch_count: 0,
                copy_attempts: 0,
                in_progress: false,
                submitted: false
            };

            sub.student_name = studentName;
            if (studentId) sub.student_id = studentId;

            if (msg.type === 'quiz_student_started') {
                sub.in_progress = true;
                sub.started_at = msg.timestamp || new Date().toLocaleTimeString();
            } else if (msg.type === 'quiz_submitted') {
                sub.submitted = true;
                sub.in_progress = false;
                sub.marks_obtained = msg.marks_obtained;
                sub.total_marks = msg.total_marks;
                sub.tab_switch_count = msg.tab_switch_count !== undefined ? msg.tab_switch_count : sub.tab_switch_count;
                sub.is_auto_submitted = msg.is_auto_submitted || sub.is_auto_submitted || false;
                sub.submitted_at = new Date().toLocaleTimeString();
                showNotification(`📝 ${sub.student_name} submitted quiz! (${msg.marks_obtained}/${msg.total_marks} marks)`, 'info');
            } else if (msg.type === 'quiz_tab_switch_warning') {
                sub.in_progress = true;
                sub.tab_switch_count = Math.max(sub.tab_switch_count || 0, msg.tab_switch_count || 1);
                if (msg.is_auto_submitted) sub.is_auto_submitted = true;
                displayTeacherQuizTabAlert(msg);
            } else if (msg.type === 'quiz_copy_warning') {
                sub.in_progress = true;
                sub.copy_attempts = (sub.copy_attempts || 0) + 1;
                displayTeacherQuizTabAlert({
                    student_name: sub.student_name,
                    tab_switch_count: 'Copy Attempt',
                    timestamp: msg.timestamp,
                    is_copy: true
                });
            }

            teacherLiveQuizSubmissions.set(targetKey, sub);
            if (studentId) teacherLiveQuizSubmissions.set(studentId, sub);
            if (studentName) teacherLiveQuizSubmissions.set(studentName.toLowerCase().trim(), sub);

            updateTeacherMonitorStudentList();
        }

        let currentTeacherQuizTab = 'completed';

        function switchTeacherQuizTab(tabName) {
            currentTeacherQuizTab = tabName || 'completed';
            const tabs = [
                { id: 'quizTabCompleted', name: 'completed' },
                { id: 'quizTabInProgress', name: 'in_progress' },
                { id: 'quizTabNotStarted', name: 'not_started' },
                { id: 'quizTabFlagged', name: 'flagged' }
            ];

            tabs.forEach(t => {
                const btn = document.getElementById(t.id);
                if (!btn) return;
                if (t.name === currentTeacherQuizTab) {
                    btn.classList.add('active');
                    if (t.name === 'flagged') {
                        btn.style.background = '#ef4444';
                    } else {
                        btn.style.background = '#7c3aed';
                    }
                    btn.style.color = '#ffffff';
                } else {
                    btn.classList.remove('active');
                    btn.style.background = 'transparent';
                    btn.style.color = '#94a3b8';
                }
            });

            updateTeacherMonitorStudentList();
        }

        function updateTeacherMonitorStudentList() {
            if (!isHost) return;

            let studentMap = new Map();
            const myId = String(window.meetingConfig?.currentUserId || currentUserId || '');
            const hId = String(window.meetingConfig?.hostId || hostId || '');

            // 1. Gather connected remote participants (students only)
            let participants = typeof getRemoteParticipants === 'function' ? getRemoteParticipants() : [];
            participants.forEach(p => {
                if (!p || !p.identity) return;
                const uid = String(p.identity);
                if (uid === myId || uid === hId) return;

                let name = p.name;
                if (window.IdentityDirectory) {
                    const userRec = window.IdentityDirectory.resolve(uid, name);
                    if (userRec && userRec.displayName) name = userRec.displayName;
                }
                if (!name) name = uid;

                studentMap.set(uid, { identity: uid, name: name });
            });

            // 2. Gather entries from teacherLiveQuizSubmissions
            teacherLiveQuizSubmissions.forEach((sub, key) => {
                if (!sub) return;
                const sid = String(sub.student_id || key);
                if (sid === myId || sid === hId) return;

                if (!studentMap.has(sid) && sub.student_name) {
                    studentMap.set(sid, { identity: sid, name: sub.student_name });
                }
            });

            let completedArr = [];
            let inProgressArr = [];
            let notStartedArr = [];
            let cheatingArr = [];

            studentMap.forEach((student, uid) => {
                let subInfo = teacherLiveQuizSubmissions.get(String(uid)) ||
                    teacherLiveQuizSubmissions.get(String(student.name).toLowerCase().trim()) ||
                    teacherLiveQuizSubmissions.get(String(student.identity));

                if (!subInfo) {
                    for (let [k, v] of teacherLiveQuizSubmissions.entries()) {
                        if (String(v.student_id) === String(uid) ||
                            (v.student_name && v.student_name.toLowerCase().trim() === String(student.name).toLowerCase().trim())) {
                            subInfo = v;
                            break;
                        }
                    }
                }

                const studentData = {
                    id: uid,
                    name: student.name,
                    subInfo: subInfo
                };

                if (subInfo && (subInfo.submitted || subInfo.is_auto_submitted)) {
                    completedArr.push(studentData);
                    if (subInfo.tab_switch_count > 0 || subInfo.copy_attempts > 0 || subInfo.is_auto_submitted) {
                        cheatingArr.push(studentData);
                    }
                } else if (subInfo && (subInfo.in_progress || subInfo.tab_switch_count > 0 || subInfo.copy_attempts > 0)) {
                    inProgressArr.push(studentData);
                    if (subInfo.tab_switch_count > 0 || subInfo.copy_attempts > 0) {
                        cheatingArr.push(studentData);
                    }
                } else {
                    notStartedArr.push(studentData);
                }
            });

            // Update live count badges on horizontal status tabs
            const bCompleted = document.getElementById('badgeCatCompleted');
            if (bCompleted) bCompleted.textContent = completedArr.length;

            const bInProgress = document.getElementById('badgeCatInProgress');
            if (bInProgress) bInProgress.textContent = inProgressArr.length;

            const bNotStarted = document.getElementById('badgeCatNotStarted');
            if (bNotStarted) bNotStarted.textContent = notStartedArr.length;

            const bFlagged = document.getElementById('badgeCatFlagged');
            if (bFlagged) bFlagged.textContent = cheatingArr.length;

            // Flagged tab red accent & subtle pulse when count > 0
            const flaggedBtn = document.getElementById('quizTabFlagged');
            if (flaggedBtn) {
                if (cheatingArr.length > 0) {
                    flaggedBtn.classList.add('flagged-pulsing');
                } else {
                    flaggedBtn.classList.remove('flagged-pulsing');
                }
            }

            // Populate active tab content container (#teacherQuizTabContent)
            const container = document.getElementById('teacherQuizTabContent');
            if (!container) return;

            let targetArray = completedArr;
            let currentTab = currentTeacherQuizTab || 'completed';

            if (currentTab === 'in_progress') targetArray = inProgressArr;
            else if (currentTab === 'not_started') targetArray = notStartedArr;
            else if (currentTab === 'flagged') targetArray = cheatingArr;

            if (targetArray.length === 0) {
                let emptyMsg = 'No students in this category';
                if (currentTab === 'completed') emptyMsg = 'No students completed yet';
                else if (currentTab === 'in_progress') emptyMsg = 'No students currently answering';
                else if (currentTab === 'not_started') emptyMsg = 'All students have started';
                if (currentTab === 'completed') emptyMsg = 'No students completed yet';
                else if (currentTab === 'in_progress') emptyMsg = 'No students currently answering';
                else if (currentTab === 'not_started') emptyMsg = 'All students have started';
                else if (currentTab === 'flagged') emptyMsg = 'No suspicious activity detected';

                container.innerHTML = `<div style="text-align: center; color: #64748b; font-size: 11px; font-style: italic; padding: 24px 10px;">${emptyMsg}</div>`;
                return;
            }

            container.innerHTML = targetArray.map(s => {
                const uid = String(s.id);
                const sub = s.subInfo || {};

                // Resolve profile & avatar from IdentityDirectory
                let user = { displayName: s.name, color: '#8b5cf6' };
                let fallbackSvg = '';
                if (window.IdentityDirectory) {
                    user = window.IdentityDirectory.resolve(uid, s.name);
                    fallbackSvg = window.IdentityDirectory.getAvatarSvg(user.displayName, user.color);
                }
                const pfpSrc = user.pfp || fallbackSvg;
                const avatarHtml = `<div style="width: 32px; height: 32px; border-radius: 50%; overflow: hidden; flex-shrink: 0; background: ${user.color || '#222222'}; display: flex; align-items: center; justify-content: center;">
            <img src="${pfpSrc}" alt="${user.displayName}" onerror="this.onerror=null; this.src='${fallbackSvg}';" style="width: 100%; height: 100%; object-fit: cover;" />
        </div>`;

                if (currentTab === 'completed') {
                    const isAuto = sub.is_auto_submitted || (sub.tab_switch_count >= 3);
                    const badgeBg = isAuto ? '#ef4444' : '#10b981';
                    const statusLabel = isAuto ? 'Auto-Submitted' : `Score: ${sub.marks_obtained !== undefined ? sub.marks_obtained + '/' + sub.total_marks : 'Submitted'}`;
                    const timeText = sub.submitted_at ? `At ${sub.submitted_at}` : (isAuto ? 'Auto-Submitted (3 Violations)' : 'Submitted');

                    return `
                <div class="teacher-student-row completed-row">
                    <div style="display: flex; align-items: center; gap: 8px; overflow: hidden;">
                        ${avatarHtml}
                        <div style="min-width: 0;">
                            <div style="font-size: 12px; font-weight: 600; color: #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${user.displayName}</div>
                            <div style="font-size: 10px; color: #94a3b8; margin-top: 1px;">${timeText} • ${sub.tab_switch_count || 0} Warnings</div>
                        </div>
                    </div>
                    <span style="background: ${badgeBg}; color: #fff; font-size: 10px; padding: 2px 7px; border-radius: 10px; font-weight: 600; white-space: nowrap; flex-shrink: 0;">${statusLabel}</span>
                </div>`;
                } else if (currentTab === 'in_progress') {
                    const warnings = sub.tab_switch_count || 0;
                    const startTimeText = sub.started_at ? `Started at ${sub.started_at}` : 'Answering questions...';
                    const warningBadge = warnings ? ` • <span style="color:#f43f5e; font-weight:600;"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px;"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> ${warnings} warning(s)</span>` : '';

                    return `
                <div class="teacher-student-row in-progress-row">
                    <div style="display: flex; align-items: center; gap: 8px; overflow: hidden;">
                        ${avatarHtml}
                        <div style="min-width: 0;">
                            <div style="font-size: 12px; font-weight: 600; color: #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${user.displayName}</div>
                            <div style="font-size: 10px; color: #94a3b8; margin-top: 1px;">${startTimeText}${warningBadge}</div>
                        </div>
                    </div>
                    <span style="background: #0284c7; color: #fff; font-size: 10px; padding: 2px 7px; border-radius: 10px; font-weight: 600; white-space: nowrap; flex-shrink: 0;">Answering</span>
                </div>`;
                } else if (currentTab === 'not_started') {
                    return `
                <div class="teacher-student-row">
                    <div style="display: flex; align-items: center; gap: 8px; overflow: hidden;">
                        ${avatarHtml}
                        <div style="min-width: 0;">
                            <div style="font-size: 12px; font-weight: 500; color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${user.displayName}</div>
                            <div style="font-size: 10px; color: #64748b; margin-top: 1px;">Awaiting student start</div>
                        </div>
                    </div>
                    <span style="background: #475569; color: #cbd5e1; font-size: 10px; padding: 2px 7px; border-radius: 10px; font-weight: 500; white-space: nowrap; flex-shrink: 0;">Not Started</span>
                </div>`;
                } else if (currentTab === 'flagged') {
                    let details = [];
                    if (sub.tab_switch_count > 0) details.push(`Tab Switches: ${sub.tab_switch_count}/2`);
                    if (sub.copy_attempts > 0) details.push(`Copy Attempts: ${sub.copy_attempts}`);
                    if (sub.is_auto_submitted) details.push(`Auto-Submitted (Violation Limit)`);

                    const detailsStr = details.length > 0 ? details.join(' • ') : 'Suspicious behavior detected';

                    return `
                <div class="teacher-student-row flagged-row">
                    <div style="display: flex; align-items: center; gap: 8px; overflow: hidden;">
                        ${avatarHtml}
                        <div style="min-width: 0;">
                            <div style="font-size: 12px; font-weight: 700; color: #fca5a5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 4px;">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2.5"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                                <span>${user.displayName}</span>
                            </div>
                            <div style="font-size: 10px; color: #f87171; margin-top: 1px;">${detailsStr}</div>
                        </div>
                    </div>
                    <span style="background: #ef4444; color: #fff; font-size: 9px; padding: 2px 6px; border-radius: 8px; font-weight: 700; white-space: nowrap; flex-shrink: 0;">Alert</span>
                </div>`;
                }
            }).join('');

            const subCount = document.getElementById('teacherMonitorSubCount');
            if (subCount) subCount.textContent = `${completedArr.length} Submitted`;
        }

        function openStartQuizModal() {
            const modal = document.getElementById('meetingQuizSelectModal');
            const container = document.getElementById('quizSelectListContainer');
            if (!modal || !container) return;

            modal.style.display = 'flex';
            container.innerHTML = '<p style="color:#94a3b8; font-size:14px; text-align:center; padding: 20px 0;">Loading available quizzes...</p>';

            fetch(`/meetings/available-quizzes/${meetingCode}/`)
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'success' && data.quizzes && data.quizzes.length > 0) {
                        let html = '';
                        data.quizzes.forEach(q => {
                            const hasQuestions = q.question_count > 0;
                            const statusBadge = q.status === 'draft'
                                ? `<span style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; font-size: 11px; padding: 2px 7px; border-radius: 6px; font-weight: 600; margin-left: 6px; border: 1px solid rgba(245, 158, 11, 0.3);">Draft (Private)</span>`
                                : `<span style="background: rgba(16, 185, 129, 0.15); color: #10b981; font-size: 11px; padding: 2px 7px; border-radius: 6px; font-weight: 600; margin-left: 6px; border: 1px solid rgba(16, 185, 129, 0.3);">Published</span>`;

                            html += `
                        <div class="quiz-card-select-item">
                            <div class="quiz-card-select-info">
                                <h4 style="display: flex; align-items: center; flex-wrap: wrap; gap: 4px;">${q.title} ${statusBadge}</h4>
                                <p>${q.question_count} Question${q.question_count === 1 ? '' : 's'} • ${q.total_marks} Marks ${q.time_limit ? '• ' + q.time_limit + ' mins' : ''}</p>
                            </div>
                            ${hasQuestions
                                    ? `<button class="btn btn-primary-quiz" onclick="launchSelectedQuiz(${q.id})">Launch Quiz</button>`
                                    : `<button class="btn btn-secondary-quiz" disabled style="opacity: 0.5; cursor: not-allowed;" title="Add questions in Classroom first">No Questions</button>`
                                }
                        </div>`;
                        });
                        container.innerHTML = html;
                    } else {
                        container.innerHTML = `<div style="text-align:center; padding: 20px 0;">
                    <p style="color:#94a3b8; font-size:14px;">No quizzes found for classroom <strong>${data.classroom_title || ''}</strong>.</p>
                    <p style="color:#64748b; font-size:12px;">Create a quiz in the Classroom before launching it in a meeting.</p>
                </div>`;
                    }
                })
                .catch(err => {
                    console.error('Failed to fetch quizzes:', err);
                    container.innerHTML = '<p style="color:#ef4444; font-size:14px; text-align:center; padding: 20px 0;">Error loading classroom quizzes.</p>';
                });
        }

        function closeStartQuizModal() {
            const modal = document.getElementById('meetingQuizSelectModal');
            if (modal) modal.style.display = 'none';
        }

        function launchSelectedQuiz(quizId) {
            fetch(`/meetings/start-quiz/${meetingCode}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
                body: JSON.stringify({ quiz_id: quizId })
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'success' && data.quiz) {
                        closeStartQuizModal();
                        showNotification(`Launched quiz: ${data.quiz.title}`, 'success');

                        try { sessionStorage.setItem(`active_live_quiz_${meetingCode}`, JSON.stringify(data.quiz)); } catch (e) { }

                        broadcastQuizEvent({
                            type: 'start_meeting_quiz',
                            quiz: data.quiz
                        });

                        startLiveMeetingQuiz(data.quiz);
                    } else {
                        showNotification(data.message || 'Failed to start quiz', 'error');
                    }
                })
                .catch(err => {
                    console.error('Launch quiz error:', err);
                    showNotification('Error starting quiz', 'error');
                });
        }

        function startLiveMeetingQuiz(quiz) {
            activeLiveQuiz = quiz;
            showQuizToggleButton(true);

            if (isHost) {
                openTeacherQuizMonitor(quiz);
                return;
            }

            currentQuizQuestionIndex = 0;
            studentQuizAnswers = {};
            studentTabSwitchCount = 0;
            quizStartTime = Date.now();
            isQuizActive = true;

            const panel = document.getElementById('meetingQuizSidePanel');
            if (!panel) return;

            document.getElementById('liveQuizPanelTitle').textContent = quiz.title;
            openSidebar('quiz');

            // Notify teacher that student has started the quiz
            broadcastQuizEvent({
                type: 'quiz_student_started',
                student_id: getLocalStudentIdentity(),
                student_name: getLocalStudentName(),
                timestamp: new Date().toLocaleTimeString()
            });

            // Reset student warning badge
            const badge = document.getElementById('studentWarningCountBadge');
            if (badge) {
                badge.textContent = '⚠️ Warnings: 0/2';
                badge.style.background = 'rgba(245, 158, 11, 0.2)';
                badge.style.color = '#f59e0b';
                badge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
            }

            renderQuizQuestion(0);

            // Anti-cheating event listeners
            window.addEventListener('blur', handleQuizTabSwitch);
            document.addEventListener('visibilitychange', handleQuizVisibilityChange);

            // Copy and text selection protection
            panel.addEventListener('copy', preventQuizCopy);
            panel.addEventListener('contextmenu', preventQuizCopy);
            panel.addEventListener('selectstart', preventQuizCopy);
        }

        function preventQuizCopy(e) {
            if (!isQuizActive || isHost) return;
            e.preventDefault();
            showNotification('⚠️ Copying or selecting quiz questions is strictly prohibited!', 'warning');

            broadcastQuizEvent({
                type: 'quiz_copy_warning',
                student_id: getLocalStudentIdentity(),
                student_name: getLocalStudentName(),
                timestamp: new Date().toLocaleTimeString()
            });

            return false;
        }

        function handleQuizTabSwitch(e) {
            if (!isQuizActive || isHost) return;
            const now = Date.now();
            if (now - lastWarningTimestamp < 1200) return;
            lastWarningTimestamp = now;

            triggerAntiCheatingWarning();
        }

        function handleQuizVisibilityChange() {
            if (!isQuizActive || isHost) return;
            if (document.hidden || document.visibilityState === 'hidden') {
                const now = Date.now();
                if (now - lastWarningTimestamp < 1200) return;
                lastWarningTimestamp = now;

                triggerAntiCheatingWarning();
            }
        }

        function triggerAntiCheatingWarning() {
            if (!isQuizActive || isHost) return;
            studentTabSwitchCount++;

            const isAutoSubmitted = (studentTabSwitchCount >= 3);

            // 1. Update Warning Badge on Student Quiz Panel
            const badge = document.getElementById('studentWarningCountBadge');
            if (badge) {
                if (isAutoSubmitted) {
                    badge.textContent = '🚨 AUTO-SUBMITTED (3/3)';
                    badge.style.background = 'rgba(239, 68, 68, 0.2)';
                    badge.style.color = '#ef4444';
                    badge.style.borderColor = 'rgba(239, 68, 68, 0.4)';
                } else {
                    badge.textContent = `⚠️ Warnings: ${studentTabSwitchCount}/2`;
                    badge.style.background = 'rgba(245, 158, 11, 0.2)';
                    badge.style.color = '#f59e0b';
                    badge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
                }
            }

            // 2. Show In-Panel Warning Box
            const warnBox = document.getElementById('studentQuizWarningBox');
            const boxTitle = document.getElementById('studentWarningBoxTitle');
            const boxDesc = document.getElementById('studentWarningBoxDesc');
            if (warnBox && boxTitle && boxDesc) {
                warnBox.style.display = 'block';
                if (isAutoSubmitted) {
                    boxTitle.textContent = `🚨 3rd VIOLATION: TEST AUTO-SUBMITTED!`;
                    boxDesc.textContent = `You exceeded the maximum 2 warning limit. Your answers have been automatically submitted.`;
                } else {
                    boxTitle.textContent = `⚠️ WARNING (${studentTabSwitchCount}/2): Window / Tab Switch Detected!`;
                    boxDesc.textContent = `Switching windows or tabs is strictly prohibited. Warning ${studentTabSwitchCount} of 2. Next violation auto-submits your test!`;
                }
            }

            // 3. Show Full Side Panel Warning Overlay Modal
            const modal = document.getElementById('studentQuizWarningModal');
            const modalTitle = document.getElementById('quizWarningModalTitle');
            const modalText = document.getElementById('quizWarningModalText');
            if (modal && modalTitle && modalText) {
                modal.style.display = 'flex';
                if (isAutoSubmitted) {
                    modalTitle.textContent = '🚨 TEST AUTO-SUBMITTED';
                    modalTitle.style.color = '#ef4444';
                    modalText.innerHTML = 'You committed 3 window/tab switch violations!<br><strong style="color:#ef4444;">Your quiz answers have been automatically submitted.</strong>';
                } else {
                    modalTitle.textContent = `⚠️ WARNING ${studentTabSwitchCount} / 2`;
                    modalTitle.style.color = '#f59e0b';
                    modalText.innerHTML = `You switched tabs or window apps!<br>Switching windows during a live test is strictly prohibited.<br><strong style="color:#f87171;">Warning ${studentTabSwitchCount} of 2. 3rd violation will AUTO-SUBMIT your test!</strong>`;
                }
            }

            showNotification(isAutoSubmitted ? '🚨 3rd Violation! Test AUTO-SUBMITTED!' : `⚠️ WARNING (${studentTabSwitchCount}/2): Window/Tab switch detected!`, isAutoSubmitted ? 'error' : 'warning');

            const alertPayload = {
                type: 'quiz_tab_switch_warning',
                student_id: getLocalStudentIdentity(),
                student_name: getLocalStudentName(),
                tab_switch_count: studentTabSwitchCount,
                is_auto_submitted: isAutoSubmitted,
                timestamp: new Date().toLocaleTimeString()
            };

            broadcastQuizEvent(alertPayload);

            if (isAutoSubmitted) {
                submitQuizAnswers(true);
            }
        }

        function acknowledgeStudentQuizWarning() {
            const modal = document.getElementById('studentQuizWarningModal');
            if (modal) modal.style.display = 'none';
        }

        function broadcastQuizEvent(payload) {
            const jsonStr = JSON.stringify(payload);

            // 1. LiveKit DataChannel
            if (window.room && window.room.localParticipant) {
                try {
                    const encoder = new TextEncoder();
                    const data = encoder.encode(jsonStr);
                    if (typeof window.room.localParticipant.publishData === 'function') {
                        window.room.localParticipant.publishData(data, { reliable: true }).catch(err => {
                            console.warn('LiveKit publishData async error:', err);
                        });
                    }
                } catch (e) {
                    console.warn('LiveKit publishData error:', e);
                }
            }

            // 2. WebSocket Signaling
            if (window.signalingWs && window.signalingWs.readyState === WebSocket.OPEN) {
                try {
                    window.signalingWs.send(jsonStr);
                } catch (e) {
                    console.warn('WebSocket send error:', e);
                }
            }
        }

        function displayTeacherQuizTabAlert(data) {
            const container = document.getElementById('teacherMonitorAlertsBox');
            const isAuto = data.is_auto_submitted;
            const isCopy = data.is_copy;

            let alertBg = isAuto ? '#ef4444' : (isCopy ? '#dc2626' : '#f59e0b');
            let alertMsg = isAuto ? `AUTO-SUBMITTED (3 Violations!)` : (isCopy ? `Attempted to Copy Question Text` : `Switched Window/Tab (${data.tab_switch_count}/2)`);

            // High Priority Notification Toast for Teacher
            showNotification(`⚠️ ${data.student_name}: ${alertMsg}`, isAuto ? 'error' : 'warning');

            if (!container) return;

            const alertEl = document.createElement('div');
            alertEl.style.cssText = `background:${alertBg}; color:#ffffff; padding:8px 12px; border-radius:6px; font-weight:600; font-size:12px; display:flex; align-items:center; justify-content:space-between; animation: slideDown 0.3s ease; margin-bottom:4px;`;
            alertEl.innerHTML = `<span>⚠️ <strong>${data.student_name}</strong> ${alertMsg}</span> <span style="font-size:10px; opacity:0.8; margin-left:6px;">${data.timestamp}</span>`;

            container.prepend(alertEl);

            setTimeout(() => {
                alertEl.style.opacity = '0';
                alertEl.style.transition = 'opacity 0.5s ease';
                setTimeout(() => alertEl.remove(), 500);
            }, 8000);
        }

        function renderQuizQuestion(idx) {
            if (!activeLiveQuiz || !activeLiveQuiz.questions || idx < 0 || idx >= activeLiveQuiz.questions.length) return;

            currentQuizQuestionIndex = idx;
            const q = activeLiveQuiz.questions[idx];

            document.getElementById('liveQuizProgressText').textContent = `Question ${idx + 1} of ${activeLiveQuiz.questions.length}`;
            document.getElementById('liveQuizQuestionMarks').textContent = `${q.marks} ${q.marks === 1 ? 'Mark' : 'Marks'}`;
            document.getElementById('liveQuizQuestionText').textContent = q.question_text;

            const mcqContainer = document.getElementById('liveQuizMcqContainer');
            const writtenContainer = document.getElementById('liveQuizWrittenContainer');

            if (q.question_type === 'mcq') {
                writtenContainer.style.display = 'none';
                mcqContainer.style.display = 'flex';

                const existingAns = studentQuizAnswers[q.id]?.selected_choice;
                let html = '';
                (q.choices || []).forEach(choice => {
                    const isChecked = String(existingAns) === String(choice.id);
                    html += `
                <label class="quiz-option-item ${isChecked ? 'selected' : ''}" onclick="selectQuizMcqOption(${q.id}, ${choice.id}, this)">
                    <input type="radio" name="quiz_q_${q.id}" value="${choice.id}" ${isChecked ? 'checked' : ''}>
                    <span class="quiz-option-text quiz-copy-protected">${choice.choice_text}</span>
                </label>`;
                });
                mcqContainer.innerHTML = html;
            } else {
                mcqContainer.style.display = 'none';
                writtenContainer.style.display = 'block';

                const textarea = document.getElementById('liveQuizWrittenText');
                textarea.value = studentQuizAnswers[q.id]?.text_answer || '';
            }

            const nextBtn = document.getElementById('liveQuizNextBtn');
            const submitBtn = document.getElementById('liveQuizSubmitBtn');
            const isLast = (idx === activeLiveQuiz.questions.length - 1);

            if (isLast) {
                nextBtn.style.display = 'none';
                submitBtn.style.display = 'inline-block';
            } else {
                nextBtn.style.display = 'inline-block';
                submitBtn.style.display = 'none';
            }
        }

        function selectQuizMcqOption(questionId, choiceId, el) {
            if (!isQuizActive) return;
            document.querySelectorAll('#liveQuizMcqContainer .quiz-option-item').forEach(item => item.classList.remove('selected'));
            el.classList.add('selected');
            const radio = el.querySelector('input[type="radio"]');
            if (radio) radio.checked = true;

            if (!studentQuizAnswers[questionId]) studentQuizAnswers[questionId] = {};
            studentQuizAnswers[questionId].selected_choice = choiceId;
        }

        function saveCurrentQuestionAnswer() {
            if (!activeLiveQuiz || !activeLiveQuiz.questions) return;
            const q = activeLiveQuiz.questions[currentQuizQuestionIndex];
            if (!q) return;

            if (!studentQuizAnswers[q.id]) studentQuizAnswers[q.id] = {};

            if (q.question_type === 'text') {
                const textVal = document.getElementById('liveQuizWrittenText')?.value || '';
                studentQuizAnswers[q.id].text_answer = textVal;
            }
        }

        function nextQuizQuestion() {
            if (!isQuizActive) return;
            saveCurrentQuestionAnswer();
            if (currentQuizQuestionIndex < activeLiveQuiz.questions.length - 1) {
                renderQuizQuestion(currentQuizQuestionIndex + 1);
            }
        }

        function skipQuizQuestion() {
            if (!isQuizActive) return;
            saveCurrentQuestionAnswer();
            if (currentQuizQuestionIndex < activeLiveQuiz.questions.length - 1) {
                renderQuizQuestion(currentQuizQuestionIndex + 1);
            } else {
                submitQuizAnswers();
            }
        }

        function submitQuizAnswers(isAutoSubmit = false) {
            saveCurrentQuestionAnswer();
            isQuizActive = false;

            // Remove anti-cheating listeners
            window.removeEventListener('blur', handleQuizTabSwitch);
            document.removeEventListener('visibilitychange', handleQuizVisibilityChange);

            // Remove active quiz from sessionStorage immediately
            try { sessionStorage.removeItem(`active_live_quiz_${meetingCode}`); } catch (e) { }

            // Lock student side panel immediately
            const panelBody = document.getElementById('liveQuizPanelBody');
            const skipBtn = document.getElementById('liveQuizSkipBtn');
            const nextBtn = document.getElementById('liveQuizNextBtn');
            const submitBtn = document.getElementById('liveQuizSubmitBtn');

            if (skipBtn) skipBtn.style.display = 'none';
            if (nextBtn) nextBtn.style.display = 'none';
            if (submitBtn) submitBtn.style.display = 'none';

            if (panelBody) {
                const statusColor = isAutoSubmit ? '#ef4444' : '#10b981';
                const statusIcon = isAutoSubmit ? '🚨' : '✅';
                const statusTitle = isAutoSubmit ? 'TEST AUTO-SUBMITTED' : 'QUIZ SUBMITTED';
                const statusMsg = isAutoSubmit
                    ? 'Your test was automatically submitted because you exceeded 2 window/tab switch warnings.'
                    : 'Your quiz responses have been recorded successfully.';

                panelBody.innerHTML = `
            <div style="text-align: center; padding: 32px 16px; animation: fadeIn 0.4s ease;">
                <div style="font-size: 48px; margin-bottom: 12px;">${statusIcon}</div>
                <h3 style="color: ${statusColor}; font-weight: 800; font-size: 20px; margin: 0 0 10px 0;">
                    ${statusTitle}
                </h3>
                <p style="color: #94a3b8; font-size: 13px; line-height: 1.6; margin: 0 0 18px 0;">
                    ${statusMsg}
                </p>
                <div style="margin-bottom: 20px; padding: 12px 16px; background: rgba(255,255,255,0.04); border-radius: 12px; border: 1px solid rgba(255,255,255,0.08); color: #e2e8f0; font-size: 13px;">
                    Status: <strong style="color: ${statusColor}">${isAutoSubmit ? 'Auto-Submitted (Limit Exceeded)' : 'Completed'}</strong>
                </div>
                <div style="font-size: 12px; color: #64748b; margin-bottom: 14px;">
                    Closing popup automatically in <span id="autoCloseCountdown" style="color: #f1f5f9; font-weight: 700;">4</span>s...
                </div>
                <button class="btn btn-primary-quiz" onclick="closeLiveQuizSidePanel()" style="width: 100%; padding: 10px; font-weight: 700; border-radius: 10px; background: ${isAutoSubmit ? '#ef4444' : '#7c3aed'}; border: none; cursor: pointer; color: #fff;">
                    Return to Meeting Screen
                </button>
            </div>`;
            }

            const modal = document.getElementById('studentQuizWarningModal');
            if (modal) {
                if (isAutoSubmit) {
                    modal.style.display = 'flex';
                    const mTitle = document.getElementById('quizWarningModalTitle');
                    const mText = document.getElementById('quizWarningModalText');
                    if (mTitle) {
                        mTitle.textContent = '🚨 TEST AUTO-SUBMITTED';
                        mTitle.style.color = '#ef4444';
                    }
                    if (mText) {
                        mText.innerHTML = 'Your test has been AUTO-SUBMITTED due to 3 window/tab switch violations!<br><strong style="color:#ef4444;">Closing popup automatically...</strong>';
                    }
                } else {
                    modal.style.display = 'none';
                }
            }

            // Auto-dismiss countdown timer (4 seconds)
            let secondsLeft = 4;
            const autoCloseTimer = setInterval(() => {
                secondsLeft--;
                const timerEl = document.getElementById('autoCloseCountdown');
                if (timerEl) timerEl.textContent = secondsLeft;
                if (secondsLeft <= 0) {
                    clearInterval(autoCloseTimer);
                    closeLiveQuizSidePanel();
                }
            }, 1000);

            const timeTaken = Math.round((Date.now() - (quizStartTime || Date.now())) / 1000);

            fetch(`/meetings/submit-quiz/${meetingCode}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    quiz_id: activeLiveQuiz ? activeLiveQuiz.id : null,
                    answers: studentQuizAnswers,
                    time_taken_seconds: timeTaken,
                    tab_switch_count: studentTabSwitchCount,
                    is_auto_submitted: isAutoSubmit
                })
            })
                .then(res => res.json())
                .then(data => {
                    showNotification(isAutoSubmit ? 'Test auto-submitted due to 3 violations!' : 'Quiz submitted successfully!', isAutoSubmit ? 'error' : 'success');
                })
                .catch(err => {
                    console.error('Submit quiz error:', err);
                });
        }

        function closeLiveQuizSidePanel() {
            isQuizActive = false;
            const modal = document.getElementById('studentQuizWarningModal');
            if (modal) modal.style.display = 'none';
            const sidebar = document.getElementById('meetSidebar');
            if (sidebar && sidebar.style.display !== 'none') {
                toggleSidebar();
            }
        }

        function restoreActiveQuizState() {
            try {
                const stored = sessionStorage.getItem(`active_live_quiz_${meetingCode}`);
                if (stored) {
                    const quiz = JSON.parse(stored);
                    if (quiz && quiz.id) {
                        activeLiveQuiz = quiz;
                        showQuizToggleButton(true);
                        if (!isHost) {
                            const localSub = sessionStorage.getItem(`quiz_submitted_${meetingCode}_${quiz.id}`);
                            if (!localSub) {
                                startLiveMeetingQuiz(quiz);
                            }
                        }
                        // For Host: keep quiz state ready in memory, do NOT auto-open monitor panel on join
                    }
                }
            } catch (e) {
                console.warn('Failed to restore quiz state:', e);
            }
        }
        setTimeout(restoreActiveQuizState, 1200);

        window.openStartQuizModal = openStartQuizModal;
        window.closeStartQuizModal = closeStartQuizModal;
        window.launchSelectedQuiz = launchSelectedQuiz;
        window.startLiveMeetingQuiz = startLiveMeetingQuiz;
        window.nextQuizQuestion = nextQuizQuestion;
        window.skipQuizQuestion = skipQuizQuestion;
        window.submitQuizAnswers = submitQuizAnswers;
        window.closeLiveQuizSidePanel = closeLiveQuizSidePanel;
        window.selectQuizMcqOption = selectQuizMcqOption;
        window.closeTeacherQuizMonitor = closeTeacherQuizMonitor;
        window.toggleQuizPanel = toggleQuizPanel;
        window.handleTeacherQuizEvent = handleTeacherQuizEvent;
        window.acknowledgeStudentQuizWarning = acknowledgeStudentQuizWarning;
        window.switchTeacherQuizTab = switchTeacherQuizTab;
        window.updateTeacherMonitorStudentList = updateTeacherMonitorStudentList;
        window.confirmAndEndQuiz = confirmAndEndQuiz;
