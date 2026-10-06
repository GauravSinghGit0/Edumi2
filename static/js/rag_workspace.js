/* ===========================================================
 * AI Workspace Controller (AW)
 * Modular, namespace-isolated, no globals leaked except AW
 * =========================================================== */
(function (global) {
    'use strict';

    const AW = {
        _config: {
            apiChatUrl: '/meetings/library/rag/api/chat/',
            apiSessionsUrl: '/meetings/library/rag/api/sessions/',
            csrfToken: '',
            storageKey: 'edumi_aw_selected_ids_v1',
            stream: true,
            streamIdleMs: 15000
        },

        state: {
            selectedIds: new Set(),
            materials: new Map(),
            activeMode: 'ask',
            currentSessionId: null,
            filters: {
                query: '',
                type: 'all',
                classroom: 'all'
            },
            activeController: null,
            userIsScrolledUp: false
        },

        /* ── Init ─────────────────────────────────────────────── */
        init: function (config) {
            if (config) Object.assign(this._config, config);
            this._hydrateFromStorage();
            this.updateSelection();
            this._bindEscapeKey();
            this._setupScrollListener();
            this._initAutoScrollObserver();
            this._initSessionPersistence();
            this._refreshLucideIcons();
        },

        _refreshLucideIcons: function () {
            if (typeof lucide !== 'undefined' && lucide.createIcons) {
                try {
                    lucide.createIcons();
                } catch (_) {}
            }
        },

        _initAutoScrollObserver: function () {
            const stream = document.getElementById('awChatStream');
            const self = this;
            if (!stream || typeof MutationObserver === 'undefined') return;

            const observer = new MutationObserver(function () {
                if (!self.state.userIsScrolledUp) {
                    stream.scrollTop = stream.scrollHeight;
                }
            });

            observer.observe(stream, {
                childList: true,
                subtree: true,
                characterData: true
            });
        },

        _initSessionPersistence: function () {
            const self = this;
            let savedSessionId = null;
            try {
                savedSessionId = localStorage.getItem('edumi_aw_session_id_v1');
            } catch (_) {}

            if (savedSessionId && !isNaN(parseInt(savedSessionId, 10))) {
                this.loadSessionDetail(parseInt(savedSessionId, 10), true);
            } else {
                fetch(this._config.apiSessionsUrl, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data.status === 'success' && Array.isArray(data.sessions) && data.sessions.length > 0) {
                        self.loadSessionDetail(data.sessions[0].id, true);
                    }
                })
                .catch(function () {});
            }
        },

        /* ── Mode Selection ───────────────────────────────────── */
        setMode: function (mode, btn) {
            this.state.activeMode = mode || 'ask';
            const pills = document.querySelectorAll('.aw-mode-pill');
            pills.forEach(function (p) { p.classList.remove('active'); });
            if (btn) btn.classList.add('active');
            else {
                const targetBtn = document.querySelector('.aw-mode-pill[data-mode="' + this.state.activeMode + '"]');
                if (targetBtn) targetBtn.classList.add('active');
            }

            const placeholders = {
                ask: 'Ask anything about your selected documents...',
                explain: 'Enter topic or concept to explain...',
                summarize: 'Request specific summary or press Send for full summary...',
                quiz: 'Click Send to generate interactive practice quiz questions...',
                revision: 'Click Send to generate study revision flashcards...'
            };

            const inp = document.getElementById('awPromptInput');
            if (inp) {
                inp.placeholder = placeholders[mode] || placeholders.ask;
            }
        },

        /* ── Selection Logic ──────────────────────────────────── */
        updateSelection: function () {
            const checkboxes = document.querySelectorAll('.aw-doc-check');
            const state = this.state;

            state.selectedIds.clear();
            state.materials.clear();

            let totalReady = 0;
            let selectedReady = 0;

            checkboxes.forEach(function (cb) {
                const isReady = cb.dataset.rag === 'true';
                const id = parseInt(cb.dataset.id, 10);
                if (!id) return;

                if (isReady) {
                    totalReady++;
                    if (cb.checked) {
                        selectedReady++;
                        state.selectedIds.add(id);
                        state.materials.set(id, {
                            id: id,
                            title: cb.dataset.title || 'Untitled',
                            unit: cb.dataset.unit || 'General',
                            type: cb.dataset.type || 'document',
                            classroom: cb.dataset.classroom || ''
                        });
                    }
                } else {
                    if (cb.checked) cb.checked = false;
                }
            });

            const selectAll = document.getElementById('awSelectAll');
            if (selectAll) {
                selectAll.checked = totalReady > 0 && selectedReady === totalReady;
            }

            this._persist();
            this._renderSelectionUI();
        },

        toggleSelectAll: function (checked) {
            const boxes = document.querySelectorAll('.aw-doc-check');
            boxes.forEach(function (cb) {
                if (!cb.disabled && cb.dataset.rag === 'true') {
                    cb.checked = checked;
                }
            });
            this.updateSelection();
        },

        clearSelection: function () {
            this.toggleSelectAll(false);
        },

        /* ── Filters ──────────────────────────────────────────── */
        filterDocuments: function (query) {
            this.state.filters.query = (query || '').toLowerCase().trim();
            this._applyFilters();
        },

        filterByType: function (type) {
            this.state.filters.type = type || 'all';
            this._applyFilters();
        },

        filterByClassroom: function (crId) {
            this.state.filters.classroom = crId || 'all';
            this._applyFilters();
        },

        toggleClassroomFilter: function () {
            const el = document.getElementById('awClassroomFilter');
            if (!el) return;
            el.style.display = (el.style.display === 'none') ? 'flex' : 'none';
        },

        resetFilters: function () {
            this.state.filters = { query: '', type: 'all', classroom: 'all' };
            const search = document.getElementById('awSearchInput');
            const typeSel = document.getElementById('awTypeSelect');
            const crSel = document.getElementById('awClassroomSelect');
            if (search) search.value = '';
            if (typeSel) typeSel.value = 'all';
            if (crSel) crSel.value = 'all';
            this._applyFilters();
        },

        focusDocList: function () {
            const list = document.getElementById('awDocList');
            if (!list) return;
            list.scrollTop = 0;
            list.style.transition = 'box-shadow 0.2s';
            list.style.boxShadow = 'inset 0 0 0 2px var(--color-primary, #7c3aed)';
            setTimeout(function () {
                list.style.boxShadow = '';
            }, 1400);
        },

        /* ── Auto-Scroll & Scroll Listener ────────────────────── */
        _setupScrollListener: function () {
            const stream = document.getElementById('awChatStream');
            const btn = document.getElementById('awScrollBottomBtn');
            const self = this;
            if (!stream) return;

            stream.addEventListener('scroll', function () {
                const distanceToBottom = stream.scrollHeight - stream.scrollTop - stream.clientHeight;
                self.state.userIsScrolledUp = distanceToBottom > 120;
                if (btn) {
                    btn.style.display = self.state.userIsScrolledUp ? 'flex' : 'none';
                }
            });
        },

        scrollToBottom: function (force) {
            const stream = document.getElementById('awChatStream');
            if (!stream) return;
            if (force || !this.state.userIsScrolledUp) {
                stream.scrollTop = stream.scrollHeight;
            }
        },

        /* ── Session History Drawer (ChatGPT style) ────────────── */
        toggleHistoryDrawer: function () {
            const drawer = document.getElementById('awHistoryDrawer');
            if (!drawer) return;
            const isHidden = drawer.style.display === 'none';
            drawer.style.display = isHidden ? 'flex' : 'none';
            if (isHidden) {
                this.loadHistorySessions();
            }
        },

        loadHistorySessions: function () {
            const list = document.getElementById('awHistoryList');
            const self = this;
            if (!list) return;
            list.innerHTML = '<p class="aw-modal-note">Loading history sessions...</p>';

            fetch(this._config.apiSessionsUrl, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.status === 'success' && Array.isArray(data.sessions) && data.sessions.length > 0) {
                    list.innerHTML = '';
                    data.sessions.forEach(function (sess) {
                        const isCurrent = self.state.currentSessionId == sess.id;
                        const item = document.createElement('div');
                        item.className = 'aw-history-item' + (isCurrent ? ' aw-history-item--active' : '');
                        item.innerHTML = `
                            <div class="aw-history-info">
                                <span class="aw-history-title">${self._escapeHtml(sess.title)}</span>
                                <span class="aw-history-meta">Mode: ${sess.active_mode.toUpperCase()} · ${sess.updated_at}</span>
                            </div>
                            <button type="button" class="aw-icon-btn" title="Delete Session" onclick="event.stopPropagation(); AW.deleteSession(${sess.id})">
                                <i data-lucide="trash-2" style="width:14px; height:14px;"></i>
                            </button>
                        `;
                        item.addEventListener('click', function () {
                            self.loadSessionDetail(sess.id);
                            self.toggleHistoryDrawer();
                        });
                        list.appendChild(item);
                    });
                    self._refreshLucideIcons();
                } else {
                    list.innerHTML = '<p class="aw-modal-note">No previous chat sessions found.</p>';
                }
            })
            .catch(function () {
                list.innerHTML = '<p class="aw-modal-note">Error loading chat sessions.</p>';
            });
        },

        loadSessionDetail: function (sessionId, silent) {
            const self = this;
            fetch(this._config.apiSessionsUrl + sessionId + '/', {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.status === 'success' && data.messages) {
                    self.state.currentSessionId = sessionId;
                    try {
                        localStorage.setItem('edumi_aw_session_id_v1', sessionId);
                    } catch (_) {}

                    if (data.session) {
                        if (data.session.active_mode) {
                            self.setMode(data.session.active_mode);
                        }
                        if (Array.isArray(data.session.selected_ids) && data.session.selected_ids.length > 0) {
                            const idSet = new Set(data.session.selected_ids.map(Number));
                            document.querySelectorAll('.aw-doc-check').forEach(function (cb) {
                                if (cb.dataset.rag === 'true' && !cb.disabled) {
                                    cb.checked = idSet.has(parseInt(cb.dataset.id, 10));
                                }
                            });
                            self.updateSelection();
                        }
                    }

                    const stream = document.getElementById('awChatStream');
                    if (!stream) return;
                    stream.innerHTML = '';

                    if (data.messages.length === 0) {
                        self.newChat();
                        return;
                    }

                    data.messages.forEach(function (msg) {
                        self._appendMessage(msg.role === 'user' ? 'user' : 'ai', msg.content, msg.sources || []);
                    });
                    self.scrollToBottom(true);
                    if (!silent) self._toast('Loaded session history', 'success');
                }
            })
            .catch(function () {
                if (!silent) self._toast('Could not load session detail', 'warning');
            });
        },

        deleteSession: function (sessionId) {
            const self = this;
            fetch(this._config.apiSessionsUrl, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this._config.csrfToken || this._readCookie('csrftoken'),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ id: sessionId })
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.status === 'success') {
                    if (self.state.currentSessionId == sessionId) {
                        self.newChat();
                    }
                    self._toast('Session deleted', 'success');
                    self.loadHistorySessions();
                }
            });
        },

        /* ── Chat Messaging ─────────────────────────────────────── */
        handleKeydown: function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        },

        resizeTextarea: function (ta) {
            if (!ta) return;
            ta.style.height = 'auto';
            ta.style.height = Math.min(ta.scrollHeight, 140) + 'px';
        },

        newChat: function () {
            this.state.currentSessionId = null;
            try {
                localStorage.removeItem('edumi_aw_session_id_v1');
            } catch (_) {}
            const stream = document.getElementById('awChatStream');
            if (!stream) return;
            stream.innerHTML = `
                <div class="aw-chat-welcome-container" id="awWelcomeRow">
                    <div class="aw-chat-welcome-pill">
                        <i data-lucide="lock" style="width:14px; height:14px;"></i>
                        <span>🔒 Grounded AI Study Workspace &nbsp;·&nbsp; Select documents on the left to start chat</span>
                    </div>
                </div>
            `;
            this._refreshLucideIcons();
            this._toast('New chat started', 'success');
        },

        sendMessage: function (regenPayload) {
            const input = document.getElementById('awPromptInput');
            const self = this;

            if (this.state.activeController) {
                try { this.state.activeController.abort(); } catch (_) {}
                this.state.activeController = null;
            }

            let prompt;
            if (regenPayload && typeof regenPayload === 'string') {
                prompt = regenPayload;
            } else if (input) {
                prompt = input.value.trim();
            } else {
                prompt = '';
            }

            if (this.state.selectedIds.size === 0) {
                this._toast('Select at least one RAG Ready document first', 'warning');
                return;
            }

            // For non-ask modes (summarize/quiz/revision), allow empty prompt to generate automatically
            if (!prompt && this.state.activeMode === 'ask') return;
            if (!prompt) prompt = 'Generate ' + this.state.activeMode + ' for selected study materials.';

            if (input) {
                input.value = '';
                this.resizeTextarea(input);
            }

            this._appendMessage('user', prompt);
            const loadingId = 'aw-ld-' + Date.now();
            this._appendLoading(loadingId, 'Processing ' + this.state.selectedIds.size + ' document' + (this.state.selectedIds.size === 1 ? '' : 's') + '…');

            const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
            this.state.activeController = controller;
            const idleMs = this._config.streamIdleMs || 15000;
            let idleTimer = null;
            let idleTimerSet = false;
            const bumpIdle = function () {
                if (!idleTimerSet) return;
                if (idleTimer) clearTimeout(idleTimer);
                idleTimer = setTimeout(function () {
                    if (self.state.activeController === controller && controller) {
                        try { controller.abort('idle'); } catch (_) {}
                    }
                }, idleMs);
            };

            const useStream = !!this._config.stream;

            const buildBody = {
                material_ids: Array.from(this.state.selectedIds),
                prompt: prompt,
                mode: this.state.activeMode,
                strict_mode: true,
                allow_external: false,
                session_id: this.state.currentSessionId,
                stream: useStream
            };

            let finished = false;
            let aiRowId = null;
            let answerBuffer = '';
            let lastDoneFrame = null;
            let contentLength = 0;

            function finishWithResult(fullResult) {
                if (finished) return;
                finished = true;
                self._removeElement(loadingId);
                if (idleTimer) clearTimeout(idleTimer);
                if (self.state.activeController === controller) self.state.activeController = null;

                if (fullResult && fullResult.session_id) {
                    self.state.currentSessionId = fullResult.session_id;
                    try {
                        localStorage.setItem('edumi_aw_session_id_v1', fullResult.session_id);
                    } catch (_) {}
                }

                const status = (fullResult && fullResult.status) || 'success';
                let answer = (fullResult && fullResult.answer) || answerBuffer;
                const sources = (fullResult && fullResult.sources) || [];
                const notFound = !!(fullResult && fullResult.not_found);

                if (aiRowId) {
                    const existing = document.getElementById(aiRowId);
                    if (existing) existing.remove();
                }

                if (status === 'success') {
                    if (notFound && !answer) {
                        answer = 'I could not find information about "' + self._escapeHtml(prompt) + '" in your selected materials. Strict mode is enabled.';
                    }

                    if (fullResult.mode === 'quiz' && Array.isArray(fullResult.quiz)) {
                        self._renderQuizBlock(fullResult.quiz, sources);
                    } else if (fullResult.mode === 'revision' && fullResult.revision) {
                        self._renderFlashcardsBlock(fullResult.revision, sources);
                    } else {
                        self._appendMessage('ai', answer, sources);
                    }
                } else {
                    self._appendMessage('ai', '⚠️ ' + ((fullResult && fullResult.message) || 'Error generating response.'));
                }
            }

            fetch(this._config.apiChatUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this._config.csrfToken || this._readCookie('csrftoken'),
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': useStream ? 'text/event-stream, application/json' : 'application/json'
                },
                body: JSON.stringify(buildBody),
                signal: controller ? controller.signal : undefined
            })
            .then(function (response) {
                if (!response || !response.ok) {
                    throw new Error('HTTP ' + (response ? response.status : 'no response'));
                }

                const ct = (response.headers.get('content-type') || '').toLowerCase();
                const isStream = useStream && (ct.indexOf('text/event-stream') !== -1 || ct.indexOf('application/x-ndjson') !== -1);

                if (!isStream) {
                    return response.json().then(function (data) {
                        finishWithResult(data);
                    });
                }

                idleTimerSet = true;
                bumpIdle();
                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let carry = '';

                function processLine(line) {
                    if (!line) return;
                    let raw = line;
                    if (raw.slice(0, 5) === 'data:') {
                        raw = raw.slice(5).trim();
                    }
                    if (!raw) return;
                    if (raw === '[DONE]') return;
                    let frame = null;
                    try {
                        frame = JSON.parse(raw);
                    } catch (_) {
                        return;
                    }
                    if (!frame || typeof frame !== 'object') return;

                    if (frame.session_id) {
                        self.state.currentSessionId = frame.session_id;
                        try {
                            localStorage.setItem('edumi_aw_session_id_v1', frame.session_id);
                        } catch (_) {}
                    }

                    const type = frame.type || 'done';
                    bumpIdle();

                    if (type === 'error') {
                        if (!finished) {
                            finishWithResult({ status: 'error', answer: frame.message || '', message: frame.message || 'Server error' });
                        }
                        return;
                    }
                    if (type === 'meta') {
                        if (frame.status === 'success' && frame.not_found && !aiRowId) {
                            answerBuffer = frame.answer || answerBuffer;
                        }
                        if (frame.mode === 'quiz' && frame.quiz) {
                            lastDoneFrame = frame;
                            finishWithResult(frame);
                        } else if (frame.mode === 'revision' && frame.revision) {
                            lastDoneFrame = frame;
                            finishWithResult(frame);
                        }
                        return;
                    }
                    if (type === 'token') {
                        const delta = (typeof frame.delta === 'string') ? frame.delta : '';
                        if (!delta) return;
                        answerBuffer += delta;
                        contentLength += delta.length;
                        if (!aiRowId) {
                            self._removeElement(loadingId);
                            aiRowId = 'aw-ai-' + Date.now();
                            self._appendStreamingMessage(aiRowId, answerBuffer);
                        } else {
                            self._updateStreamingMessage(aiRowId, answerBuffer);
                        }
                        return;
                    }
                    if (type === 'done') {
                        lastDoneFrame = frame;
                        if (aiRowId) {
                            const existing = document.getElementById(aiRowId);
                            if (existing) existing.remove();
                            aiRowId = null;
                        }
                        finishWithResult(frame);
                        return;
                    }
                    if (type === 'eos') {
                        if (!finished) {
                            finishWithResult(lastDoneFrame || { status: 'success', answer: answerBuffer });
                        }
                    }
                }

                return reader.read().then(function processChunk(result) {
                    if (finished) return;
                    if (result.done) {
                        if (carry) processLine(carry);
                        if (!finished) {
                            finishWithResult(lastDoneFrame || { status: 'success', answer: answerBuffer });
                        }
                        return;
                    }
                    const chunk = decoder.decode(result.value || new Uint8Array(), { stream: true });
                    carry += chunk;
                    let idx;
                    while ((idx = carry.indexOf('\n')) !== -1) {
                        const line = carry.slice(0, idx).replace(/\r$/, '').trim();
                        carry = carry.slice(idx + 1);
                        if (line) processLine(line);
                    }
                    if (finished) return;
                    return reader.read().then(processChunk);
                });
            })
            .catch(function (err) {
                if (idleTimer) clearTimeout(idleTimer);
                if (self.state.activeController === controller) self.state.activeController = null;
                if (finished) return;
                finished = true;
                self._removeElement(loadingId);
                if (aiRowId) {
                    const existing = document.getElementById(aiRowId);
                    if (existing) existing.remove();
                }
                const aborted = err && (err.name === 'AbortError' || err === 'idle' || (err.message && err.message.toLowerCase().indexOf('abort') !== -1));
                if (aborted && answerBuffer && contentLength > 0) {
                    self._appendMessage('ai', answerBuffer + '\n\n_(stream interrupted — partial answer)_', (lastDoneFrame && lastDoneFrame.sources) || []);
                } else {
                    self._appendMessage('ai', '⚠️ Network error reaching the AI engine. Please try again.');
                }
            });
        },

        attachFile: function () {
            this._toast('AI responses are grounded in your selected course documents', 'info');
        },

        /* ── Quiz & Flashcards Renderers ───────────────────────── */
        _renderQuizBlock: function (quizItems, sources) {
            const self = this;
            let html = '<div class="aw-quiz-container" style="display:flex; flex-direction:column; gap:1rem;">';
            html += '<h3 style="margin:0; font-size:15px; font-weight:700; color:var(--color-primary, #7c3aed);">🎯 Interactive Practice Quiz</h3>';

            quizItems.forEach(function (q, idx) {
                html += '<div class="aw-quiz-card" style="background:#f8fafc; border:1px solid #e2e8f0; padding:0.9rem; border-radius:10px; display:flex; flex-direction:column; gap:0.5rem;">';
                html += '<strong style="font-size:13.5px;">Q' + (idx + 1) + ': ' + self._escapeHtml(q.question) + '</strong>';

                if (Array.isArray(q.options)) {
                    q.options.forEach(function (opt, oIdx) {
                        const isCorrect = oIdx === q.correct_index;
                        html += '<label style="display:flex; align-items:center; gap:0.5rem; font-size:12.5px; padding:0.4rem 0.6rem; background:#ffffff; border:1px solid #cbd5e1; border-radius:6px; cursor:pointer;" onclick="this.style.borderColor = \'' + (isCorrect ? '#10b981' : '#ef4444') + '\'; this.style.background = \'' + (isCorrect ? '#ecfdf5' : '#fef2f2') + '\';">';
                        html += '<input type="radio" name="quiz_q_' + q.id + '" value="' + oIdx + '"> ' + self._escapeHtml(opt);
                        html += '</label>';
                    });
                }
                html += '<div style="font-size:11.5px; color:#64748b;"><em>Explanation: ' + self._escapeHtml(q.explanation || '') + '</em></div>';
                html += '</div>';
            });
            html += '</div>';

            this._appendMessage('ai', html, sources);
        },

        _renderFlashcardsBlock: function (revisionData, sources) {
            const self = this;
            const cards = revisionData.flashcards || [];
            let html = '<div class="aw-flashcards-container" style="display:flex; flex-direction:column; gap:0.75rem;">';
            html += '<h3 style="margin:0; font-size:15px; font-weight:700; color:var(--color-primary, #7c3aed);">🃏 Revision Flashcards</h3>';

            cards.forEach(function (c, idx) {
                html += '<div style="background:#f8fafc; border:1px solid #e2e8f0; padding:0.85rem; border-radius:10px;">';
                html += '<div style="font-size:12px; font-weight:700; color:#7c3aed; margin-bottom:0.25rem;">CARD #' + (idx + 1) + '</div>';
                html += '<div style="font-size:13.5px; font-weight:600; margin-bottom:0.4rem;">❓ ' + self._escapeHtml(c.front) + '</div>';
                html += '<div style="font-size:13px; color:#334155; padding:0.5rem; background:#ffffff; border-radius:6px; border-left:3px solid #7c3aed;">💡 ' + self._formatMarkdown(c.back) + '</div>';
                html += '</div>';
            });
            html += '</div>';

            this._appendMessage('ai', html, sources);
        },

        /* ── Preview Modal ────────────────────────────────────── */
        openPreview: function (id, title) {
            const modal = document.getElementById('awDocModal');
            const titleEl = document.getElementById('awDocModalTitle');
            if (!modal) return;
            if (titleEl) titleEl.textContent = title || 'Document Preview';
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
        },

        closePreview: function () {
            const modal = document.getElementById('awDocModal');
            if (modal) modal.style.display = 'none';
            document.body.style.overflow = '';
        },

        /* ── Rendering helpers (private-ish) ──────────────────── */
        _renderSelectionUI: function () {
            const count = this.state.selectedIds.size;

            const chip = document.getElementById('awSelectedChip');
            if (chip) chip.textContent = count + ' selected';

            const scopeCount = document.getElementById('awScopeCount');
            const scopePlural = document.getElementById('awScopePlural');
            if (scopeCount) scopeCount.textContent = count;
            if (scopePlural) scopePlural.textContent = (count === 1 ? '' : 's');

            this._renderScopePills();
            this._renderSuggestedPrompts();
            this._toggleInputEnabled(count > 0);
        },

        _renderScopePills: function () {
            const wrap = document.getElementById('awScopePills');
            if (!wrap) return;
            wrap.innerHTML = '';

            const size = this.state.selectedIds.size;
            if (size === 0) {
                wrap.innerHTML = '<span class="aw-scope-pill aw-scope-pill--muted">None selected</span>';
                return;
            }

            const items = Array.from(this.state.materials.values());
            const max = 3;
            items.slice(0, max).forEach(function (m) {
                const pill = document.createElement('span');
                pill.className = 'aw-scope-pill';
                pill.title = m.title;
                pill.textContent = m.title.length > 18 ? m.title.slice(0, 18) + '…' : m.title;
                wrap.appendChild(pill);
            });
            if (size > max) {
                const extra = document.createElement('span');
                extra.className = 'aw-scope-pill';
                extra.style.fontWeight = '700';
                extra.textContent = '+' + (size - max) + ' more';
                wrap.appendChild(extra);
            }
        },

        _renderSuggestedPrompts: function () {
            const wrap = document.getElementById('awSuggestedPrompts');
            if (!wrap) return;
            wrap.innerHTML = '';

            const mats = Array.from(this.state.materials.values());
            const self = this;

            function makePill(iconSvg, text, promptText) {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'aw-suggest-pill';
                b.innerHTML = (iconSvg ? '<span class="aw-suggest-ico">' + iconSvg + '</span> ' : '') + '<span>' + self._escapeHtml(text) + '</span>';
                b.addEventListener('click', function () {
                    const inp = document.getElementById('awPromptInput');
                    if (inp) {
                        inp.value = promptText;
                        self.resizeTextarea(inp);
                    }
                    self.sendMessage();
                });
                wrap.appendChild(b);
            }

            if (mats.length === 0) {
                const docIconSvg = '<i data-lucide="book-open" style="width:14px; height:14px;"></i>';
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'aw-suggest-pill';
                b.innerHTML = '<span class="aw-suggest-ico">' + docIconSvg + '</span> <span>Pick a document to begin</span>';
                b.addEventListener('click', function () { self.focusDocList(); });
                wrap.appendChild(b);
                self._refreshLucideIcons();
                return;
            }

            const first = mats[0];
            const t = (first.title.length > 24) ? first.title.slice(0, 24) + '…' : first.title;
            const sumIcon = '<i data-lucide="file-text" style="width:14px; height:14px;"></i>';
            const keyIcon = '<i data-lucide="sparkles" style="width:14px; height:14px;"></i>';
            const bookIcon = '<i data-lucide="book-open" style="width:14px; height:14px;"></i>';

            makePill(sumIcon, 'Summarize "' + t + '"', 'Summarize ' + first.title + ' in simple terms');
            makePill(keyIcon, 'Key concepts in "' + t + '"', 'What are the key concepts in ' + first.title + '?');
            makePill(bookIcon, 'Explain important definitions', 'Explain the most important definitions in the selected study materials');
            this._refreshLucideIcons();
        },

        _toggleInputEnabled: function (enabled) {
            const input = document.getElementById('awPromptInput');
            const send = document.getElementById('awSendBtn');
            const warn = document.getElementById('awWarningBar');
            if (input) {
                input.disabled = !enabled;
                input.placeholder = enabled
                    ? 'Ask anything about your selected documents...'
                    : 'Select at least one RAG Ready document to start...';
            }
            if (send) send.disabled = !enabled;
            if (warn) warn.style.display = enabled ? 'none' : 'flex';
        },

        _clearWelcome: function () {
            const welcome = document.getElementById('awWelcomeRow');
            if (welcome) welcome.remove();
        },

        _appendStreamingMessage: function (rowId, initialText) {
            this._clearWelcome();
            const stream = document.getElementById('awChatStream');
            if (!stream) return;

            const aiIcon = '<i data-lucide="bot" style="width:16px; height:16px;"></i>';
            const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            const row = document.createElement('div');
            row.id = rowId;
            row.className = 'aw-chat-row aw-chat-row--ai';
            row.innerHTML =
                '<div class="aw-avatar aw-avatar--ai">' + aiIcon + '</div>' +
                '<div class="aw-msg-wrap">' +
                    '<div class="aw-msg-meta">AI <span class="aw-msg-time">' + time + '</span></div>' +
                    '<div class="aw-bubble aw-bubble--ai">' +
                        '<div class="aw-streaming-content">' + this._formatMarkdown(initialText) + '</div>' +
                        '<span class="aw-streaming-caret" aria-hidden="true">▍</span>' +
                    '</div>' +
                '</div>';

            stream.appendChild(row);
            this._refreshLucideIcons();
            this.scrollToBottom(false);
        },

        _updateStreamingMessage: function (rowId, text) {
            const row = document.getElementById(rowId);
            if (!row) return;
            const content = row.querySelector('.aw-streaming-content');
            if (content) content.innerHTML = this._formatMarkdown(text);
            this.scrollToBottom(false);
        },

        _appendMessage: function (role, text, sources) {
            this._clearWelcome();
            const stream = document.getElementById('awChatStream');
            if (!stream) return;

            const row = document.createElement('div');
            row.className = 'aw-chat-row ' + (role === 'user' ? 'aw-chat-row--user' : 'aw-chat-row--ai');

            const aiIcon = '<i data-lucide="bot" style="width:16px; height:16px;"></i>';
            const userAvatarUrl = (this._config.currentUser && this._config.currentUser.avatarUrl) || '';
            const userDisplayName = (this._config.currentUser && this._config.currentUser.displayName) || 'YOU';
            const userUsername = (this._config.currentUser && this._config.currentUser.username) || 'User';

            const userAvatarHtml = userAvatarUrl
                ? '<img src="' + this._escapeHtml(userAvatarUrl) + '" alt="' + this._escapeHtml(userDisplayName) + '" class="aw-user-avatar-img" onerror="this.style.display=\'none\'; if(this.nextElementSibling) this.nextElementSibling.style.display=\'inline-block\';"><i data-lucide="user" style="width:16px; height:16px; display:none;"></i>'
                : '<i data-lucide="user" style="width:16px; height:16px;"></i>';

            const avatar = role === 'user'
                ? '<div class="aw-avatar aw-avatar--user">' + userAvatarHtml + '</div>'
                : '<div class="aw-avatar aw-avatar--ai">' + aiIcon + '</div>';

            const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            let sourcesHtml = '';
            if (Array.isArray(sources) && sources.length > 0) {
                const self = this;
                const items = sources.map(function (s) {
                    const docIcon = '<i data-lucide="file-text" style="width:13px; height:13px;"></i>';
                    const title = self._escapeHtml(s.title || 'Source');
                    const label = title + ' (Page ' + (s.page_number || 1) + ')';
                    return '<button type="button" class="aw-suggest-pill" onclick="AW.openPreview(' + (s.material_id || 0) + ', \'' + title.replace(/'/g, "\\'") + '\')">' + docIcon + ' ' + self._escapeHtml(label) + '</button>';
                }).join('');

                const bookIcon = '<i data-lucide="book-open" style="width:13px; height:13px;"></i>';
                sourcesHtml = '<div class="aw-sources"><div class="aw-sources-title">' + bookIcon + ' Sources</div><div class="aw-sources-list">' + items + '</div></div>';
            }

            let actionsHtml = '';
            if (role === 'ai') {
                const copyIcon = '<i data-lucide="copy" style="width:12px; height:12px;"></i>';
                const regenIcon = '<i data-lucide="rotate-ccw" style="width:12px; height:12px;"></i>';
                const thumbIcon = '<i data-lucide="thumbs-up" style="width:12px; height:12px;"></i>';
                actionsHtml = '<div class="aw-actions">' +
                    '<button type="button" class="aw-act-btn" onclick="AW._copyBubble(this)">' + copyIcon + ' Copy</button>' +
                    '<button type="button" class="aw-act-btn" onclick="AW.sendMessage()">' + regenIcon + ' Regenerate</button>' +
                    '<button type="button" class="aw-act-btn">' + thumbIcon + ' Feedback</button>' +
                '</div>';
            }

            const bubbleClass = role === 'user' ? 'aw-bubble--user' : 'aw-bubble--ai';
            const roleLabel = role === 'user' ? this._escapeHtml(userDisplayName.toUpperCase()) : 'AI';

            row.innerHTML = avatar +
                '<div class="aw-msg-wrap">' +
                    '<div class="aw-msg-meta">' + roleLabel + ' <span class="aw-msg-time">' + time + '</span></div>' +
                    '<div class="aw-bubble ' + bubbleClass + '">' +
                        '<div>' + this._formatMarkdown(text) + '</div>' +
                        sourcesHtml +
                        actionsHtml +
                    '</div>' +
                '</div>';

            stream.appendChild(row);
            this._refreshLucideIcons();
            this.scrollToBottom(false);
        },

        _appendLoading: function (id, text) {
            this._clearWelcome();
            const stream = document.getElementById('awChatStream');
            if (!stream) return;
            const aiIcon = '<i data-lucide="bot" style="width:16px; height:16px;"></i>';

            const row = document.createElement('div');
            row.className = 'aw-chat-row aw-chat-row--ai';
            row.id = id;
            row.innerHTML =
                '<div class="aw-avatar aw-avatar--ai">' + aiIcon + '</div>' +
                '<div class="aw-msg-wrap">' +
                    '<div class="aw-msg-meta">AI <span class="aw-msg-time">Thinking…</span></div>' +
                    '<div class="aw-bubble aw-bubble--ai"><div class="aw-thinking"><span class="aw-think-dots"><span></span><span></span><span></span></span><span>' + this._escapeHtml(text) + '</span></div></div>' +
                '</div>';
            stream.appendChild(row);
            this._refreshLucideIcons();
            this.scrollToBottom(false);
        },

        _copyBubble: function (btn) {
            const bubble = btn.closest('.aw-bubble');
            if (!bubble) return;
            const text = bubble.innerText || bubble.textContent || '';
            const self = this;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(function () {
                    self._toast('✓ Response copied to clipboard', 'success');
                }).catch(function () {
                    self._toast('Copied', 'success');
                });
            } else {
                self._toast('Copied', 'success');
            }
        },

        _applyFilters: function () {
            const items = document.querySelectorAll('.aw-doc-item');
            const f = this.state.filters;
            let visible = 0;

            items.forEach(function (el) {
                const title = (el.dataset.title || '').toLowerCase();
                const type = el.dataset.type || '';
                const cr = (el.dataset.classroom || '').toString();
                const matchQ = title.includes(f.query);
                const matchT = (f.type === 'all') || (f.type === type);
                const matchC = (f.classroom === 'all') || (f.classroom === cr);
                const show = matchQ && matchT && matchC;
                el.style.display = show ? 'flex' : 'none';
                if (show) visible++;
            });

            const empty = document.getElementById('awEmptyFilter');
            if (empty) {
                empty.style.display = (visible === 0 && (f.query || f.type !== 'all' || f.classroom !== 'all')) ? 'flex' : 'none';
            }
        },

        /* ── Storage ──────────────────────────────────────────── */
        _persist: function () {
            try {
                localStorage.setItem(
                    this._config.storageKey,
                    JSON.stringify(Array.from(this.state.selectedIds))
                );
            } catch (_) { /* noop */ }
        },

        _hydrateFromStorage: function () {
            let ids = [];
            try {
                const raw = localStorage.getItem(this._config.storageKey);
                if (raw) ids = JSON.parse(raw) || [];
            } catch (_) { ids = []; }

            if (Array.isArray(this._config.initialIds) && this._config.initialIds.length) {
                ids = ids.concat(this._config.initialIds);
            }

            if (!ids.length) return;

            const checkboxes = document.querySelectorAll('.aw-doc-check');
            const idSet = new Set(ids.map(function (x) { return parseInt(x, 10); }).filter(function (x) { return !isNaN(x); }));
            checkboxes.forEach(function (cb) {
                if (cb.dataset.rag === 'true' && !cb.disabled) {
                    const id = parseInt(cb.dataset.id, 10);
                    if (idSet.has(id)) cb.checked = true;
                }
            });
        },

        _removeElement: function (id) {
            const el = document.getElementById(id);
            if (el) el.remove();
        },

        _bindEscapeKey: function () {
            const self = this;
            document.addEventListener('keydown', function (e) {
                if (e.key === 'Escape') {
                    self.closePreview();
                    const drawer = document.getElementById('awHistoryDrawer');
                    if (drawer) drawer.style.display = 'none';
                }
            });
        },

        _toast: function (msg, type) {
            if (typeof global.showToast === 'function') {
                global.showToast(msg, '', type || 'info');
            }
        },

        _escapeHtml: function (s) {
            if (!s) return '';
            return String(s)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        },

        _formatMarkdown: function (text) {
            if (!text) return '';
            let out = String(text)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            out = out.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            out = out.replace(/\*(.+?)\*/g, '<em>$1</em>');
            out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
            out = out.replace(/\n\n/g, '<br><br>');
            out = out.replace(/\n/g, '<br>');
            return out;
        },

        _readCookie: function (name) {
            if (!document.cookie) return '';
            const parts = document.cookie.split(';');
            for (let i = 0; i < parts.length; i++) {
                const c = parts[i].trim();
                if (c.indexOf(name + '=') === 0) {
                    return decodeURIComponent(c.substring(name.length + 1));
                }
            }
            return '';
        }
    };

    global.AW = AW;
})(typeof window !== 'undefined' ? window : this);
