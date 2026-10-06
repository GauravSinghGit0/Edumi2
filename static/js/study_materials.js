/* static/js/study_materials.js - Enterprise Controller for Study Materials, Streaming Video & RAG Indexing */

/* ── Toast Notification System ── */
function showToast(message, type = 'success') {
    let container = document.getElementById('matToastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'matToastContainer';
        container.style.cssText = 'position: fixed; bottom: 2rem; right: 2rem; z-index: 2000; display: flex; flex-direction: column; gap: 0.75rem; pointer-events: none;';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.style.cssText = `
        background: ${type === 'success' ? '#000000' : '#991b1b'};
        color: white;
        padding: 0.875rem 1.25rem;
        border-radius: 0.875rem;
        font-size: 0.875rem;
        font-weight: 650;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
        display: flex;
        align-items: center;
        gap: 0.65rem;
        pointer-events: auto;
        animation: toastSlideIn 0.3s ease-out;
        border: 1px solid rgba(255, 255, 255, 0.15);
    `;
    
    const icon = type === 'success' ? '✓' : '⚠';
    toast.innerHTML = `<span style="color: ${type === 'success' ? '#10b981' : '#f87171'}; font-weight: 800;">${icon}</span> <span>${escapeHtml(message)}</span>`;
    
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function openUploadModal() {
    const m = document.getElementById('uploadMaterialModal');
    if (m) {
        m.style.display = 'flex';
        initStudyMaterials();
    }
}

function closeUploadModal() {
    const m = document.getElementById('uploadMaterialModal');
    if (m) m.style.display = 'none';
}

function openCreateUnitModal() {
    const m = document.getElementById('createUnitModal');
    if (m) m.style.display = 'flex';
}

function closeCreateUnitModal() {
    const m = document.getElementById('createUnitModal');
    if (m) m.style.display = 'none';
}

function openMaterialDetailModal(materialId) {
    const m = document.getElementById('materialDetailModal');
    if (!m) return;
    
    m.style.display = 'flex';
    document.getElementById('matDetailTitle').textContent = 'Loading resource...';
    document.getElementById('matDetailAiSummary').textContent = 'Loading summary...';
    const chunksList = document.getElementById('matDetailChunksList');
    if (chunksList) chunksList.innerHTML = '';

    const previewContainer = document.getElementById('matDetailMediaPreview');
    const videoPlayer = document.getElementById('matDetailVideoPlayer');
    const pdfViewer = document.getElementById('matDetailPdfViewer');

    if (previewContainer) previewContainer.style.display = 'none';
    if (videoPlayer) {
        videoPlayer.pause();
        videoPlayer.src = '';
        videoPlayer.style.display = 'none';
    }
    if (pdfViewer) {
        pdfViewer.src = '';
        pdfViewer.style.display = 'none';
    }

    fetch(`/meetings/materials/${materialId}/detail-api/`)
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                document.getElementById('matDetailTitle').textContent = data.title;
                document.getElementById('matDetailType').textContent = data.material_type_display;
                document.getElementById('matDetailAuthor').textContent = data.uploaded_by;
                document.getElementById('matDetailDate').textContent = data.created_at;
                document.getElementById('matDetailSize').textContent = data.file_size || 'N/A';
                document.getElementById('matDetailAiSummary').textContent = data.summary_ai || 'No summary available for this resource.';
                
                // Embedded Video Player Streaming
                if (data.is_video && data.stream_url && videoPlayer && previewContainer) {
                    videoPlayer.src = data.stream_url;
                    videoPlayer.style.display = 'block';
                    previewContainer.style.display = 'block';
                } else if (data.is_pdf && data.file_url && pdfViewer && previewContainer) {
                    pdfViewer.src = data.file_url + '#toolbar=0';
                    pdfViewer.style.display = 'block';
                    previewContainer.style.display = 'block';
                }

                const dlBtn = document.getElementById('matDetailDownloadBtn');
                if (dlBtn) {
                    if (data.file_url) {
                        dlBtn.href = `/meetings/materials/${data.id}/download/`;
                        dlBtn.style.display = 'inline-flex';
                    } else if (data.external_url) {
                        dlBtn.href = data.external_url;
                        dlBtn.style.display = 'inline-flex';
                    } else {
                        dlBtn.style.display = 'none';
                    }
                }

                // Render Chunks if element exists
                const chunksList = document.getElementById('matDetailChunksList');
                if (chunksList) {
                    chunksList.innerHTML = '';
                    if (data.chunks && data.chunks.length > 0) {
                        data.chunks.forEach(c => {
                            const card = document.createElement('div');
                            card.className = 'rag-chunk-card';
                            card.innerHTML = `
                                <div>${escapeHtml(c.text)}</div>
                            `;
                            chunksList.appendChild(card);
                        });
                    }
                }

                if (window.lucide) lucide.createIcons();
            } else {
                document.getElementById('matDetailTitle').textContent = 'Unable to Load Resource';
                document.getElementById('matDetailAiSummary').textContent = data.message || 'Could not fetch metadata for this resource.';
            }
        })
        .catch(err => {
            console.error('Error fetching material details:', err);
            document.getElementById('matDetailTitle').textContent = 'Error Loading Resource';
            document.getElementById('matDetailAiSummary').textContent = 'An error occurred while loading resource details. Please try again.';
        });
}

function closeMaterialDetailModal() {
    const m = document.getElementById('materialDetailModal');
    if (m) m.style.display = 'none';
    const videoPlayer = document.getElementById('matDetailVideoPlayer');
    if (videoPlayer) {
        videoPlayer.pause();
        videoPlayer.src = '';
    }
}

function toggleBookmark(btn, materialId) {
    fetch(`/meetings/materials/${materialId}/bookmark/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            if (data.is_bookmarked) {
                btn.classList.add('bookmarked');
                showToast('Bookmarked resource to your personal library.');
            } else {
                btn.classList.remove('bookmarked');
                showToast('Removed bookmark.');
            }
        }
    })
    .catch(err => console.error('Error toggling bookmark:', err));
}

async function deleteMaterial(materialId) {
    if (window.EdumiPopup) {
        const confirmed = await EdumiPopup.danger({
            title: 'Delete Material',
            message: 'Are you sure you want to remove this study material?',
            confirmText: 'Remove Material'
        });
        if (!confirmed) return;
    } else if (!confirm('Are you sure you want to remove this study material?')) {
        return;
    }
    
    fetch(`/meetings/materials/${materialId}/delete/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            const card = document.getElementById(`mat-card-${materialId}`);
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'scale(0.95)';
                setTimeout(() => card.remove(), 200);
            }
            showToast('Study material removed.');
        }
    })
    .catch(err => console.error('Error deleting material:', err));
}

function insertMaterialCard(data) {
    let targetGrid = document.querySelector('.materials-grid');
    
    const emptyStates = document.querySelectorAll('.stream-post-card, .unit-section-box');
    emptyStates.forEach(el => {
        if (el.textContent.includes('No Study Materials') || el.textContent.includes('No materials found')) {
            el.remove();
        }
    });

    if (!targetGrid) {
        const container = document.getElementById('tabContentMaterials') || document.querySelector('.materials-hub-container');
        if (container) {
            const box = document.createElement('div');
            box.className = 'unit-section-box';
            box.innerHTML = `
                <div class="unit-header">
                    <div class="unit-title-row">
                        <div class="unit-badge-icon" style="background: #f1f5f9; color: #475569;">#</div>
                        <div>
                            <h3 class="unit-title">General Study Resources</h3>
                            <p class="unit-desc">Class notes, reference guides, and supplementary materials.</p>
                        </div>
                    </div>
                </div>
                <div class="materials-grid"></div>
            `;
            container.appendChild(box);
            targetGrid = box.querySelector('.materials-grid');
        }
    }

    if (!targetGrid) {
        location.reload();
        return;
    }

    const card = document.createElement('div');
    card.className = 'material-card';
    card.id = `mat-card-${data.material_id}`;
    card.style.animation = 'fadeInPost 0.3s ease-out';

    const badgeColor = data.badge_color || '#7c3aed';
    const iconName = data.icon_name || 'file-text';

    let actionBtnHtml = '';
    if (data.download_url) {
        actionBtnHtml = `
            <a href="${data.download_url}" class="mat-btn-action" style="background: var(--mat-primary); color: white; border-color: var(--mat-primary);">
                <i data-lucide="download" style="width: 14px; height: 14px;"></i>
                Get
            </a>
        `;
    } else if (data.external_url) {
        actionBtnHtml = `
            <a href="${data.external_url}" target="_blank" rel="noopener" class="mat-btn-action" style="background: #10b981; color: white; border-color: #10b981;">
                <i data-lucide="external-link" style="width: 14px; height: 14px;"></i>
                Visit
            </a>
        `;
    }

    card.innerHTML = `
        <div>
            <div class="mat-card-top">
                <div class="mat-type-icon-box" style="background: ${badgeColor}15; color: ${badgeColor};">
                    <i data-lucide="${iconName}" style="width: 22px; height: 22px;"></i>
                </div>
                <div class="mat-card-meta">
                    <h4 class="mat-title" title="${escapeHtml(data.title)}">${escapeHtml(data.title)}</h4>
                    <div class="mat-subtitle">
                        <span style="text-transform: uppercase; font-weight: 750; font-size: 0.6875rem; color: ${badgeColor};">${data.material_type}</span>
                        ${data.file_size ? `<span>• ${data.file_size}</span>` : ''}
                    </div>
                </div>
            </div>
            ${data.description ? `<p class="mat-desc">${escapeHtml(data.description)}</p>` : ''}
            ${data.rag_indexed ? `
                <div style="margin-bottom: 0.75rem;">
                    <span class="mat-rag-badge">
                        <i data-lucide="sparkles" style="width: 12px; height: 12px;"></i>
                        RAG Ready · ${data.chunks_count || 1} Chunks
                    </span>
                </div>
            ` : ''}
        </div>
        <div class="mat-card-footer">
            <div class="mat-footer-stats">
                <span><i data-lucide="download" style="width: 12px; height: 12px;"></i> 0</span>
                <span><i data-lucide="eye" style="width: 12px; height: 12px;"></i> 0</span>
            </div>
            <div class="mat-card-actions">
                <button onclick="openMaterialDetailModal(${data.material_id})" class="mat-btn-action" title="View details & preview">
                    <i data-lucide="play-circle" style="width: 14px; height: 14px;"></i>
                    View
                </button>
                ${actionBtnHtml}
                <button onclick="deleteMaterial(${data.material_id})" class="mat-btn-action" style="color: #ef4444;" title="Delete">
                    <i data-lucide="trash-2" style="width: 14px; height: 14px;"></i>
                </button>
            </div>
        </div>
    `;

    targetGrid.insertBefore(card, targetGrid.firstChild);
    if (window.lucide) lucide.createIcons();
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function initStudyMaterials() {
    // Drag and drop zone & Auto-fill Title
    const dropzone = document.getElementById('matDropzone');
    const fileInput = document.getElementById('matFileInput');
    const titleInput = document.getElementById('matTitleInput');

    if (dropzone && fileInput) {
        // Prevent binding duplicate event handlers
        if (!dropzone.dataset.bound) {
            dropzone.dataset.bound = "true";

            const handleFiles = (files) => {
                if (files && files.length > 0) {
                    const f = files[0];
                    try {
                        const dataTransfer = new DataTransfer();
                        dataTransfer.items.add(f);
                        fileInput.files = dataTransfer.files;
                    } catch (e) {}

                    const fileNameEl = document.getElementById('matSelectedFileName');
                    if (fileNameEl) {
                        fileNameEl.textContent = `Selected: ${f.name} (${(f.size / (1024*1024)).toFixed(2)} MB)`;
                        fileNameEl.style.color = 'var(--mat-primary)';
                        fileNameEl.style.fontWeight = 'bold';
                    }

                    if (titleInput && !titleInput.value.trim()) {
                        const cleanName = f.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " ");
                        titleInput.value = cleanName.charAt(0).toUpperCase() + cleanName.slice(1);
                    }
                }
            };

            dropzone.onclick = (e) => {
                if (e.target !== fileInput) {
                    fileInput.click();
                }
            };

            fileInput.onchange = () => handleFiles(fileInput.files);

            ['dragenter', 'dragover'].forEach(eventName => {
                dropzone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    dropzone.style.borderColor = 'var(--mat-primary)';
                    dropzone.style.background = 'var(--mat-hover-bg)';
                }, false);
            });

            ['dragleave', 'drop'].forEach(eventName => {
                dropzone.addEventListener(eventName, (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    dropzone.style.borderColor = '';
                    dropzone.style.background = '';
                }, false);
            });

            dropzone.addEventListener('drop', (e) => {
                const dt = e.dataTransfer;
                if (dt && dt.files && dt.files.length > 0) {
                    handleFiles(dt.files);
                }
            }, false);
        }
    }

    // New Unit AJAX Form
    const unitForm = document.getElementById('createUnitForm');
    if (unitForm) {
        unitForm.onsubmit = function(e) {
            e.preventDefault();
            const fd = new FormData(unitForm);
            fetch(unitForm.action, {
                method: 'POST',
                body: fd,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    closeCreateUnitModal();
                    showToast(`Unit "${data.title}" created successfully!`);
                    // Populate into dropdowns
                    const sel = document.getElementById('matUnitSelect');
                    if (sel) {
                        const opt = document.createElement('option');
                        opt.value = data.unit_id;
                        opt.textContent = data.title;
                        sel.appendChild(opt);
                    }
                } else {
                    showToast(data.message || 'Failed to create unit', 'error');
                }
            });
        };
    }

    // Enterprise Chunked / Streaming Upload with Progress Bar
    const uploadForm = document.getElementById('uploadMaterialForm');
    if (uploadForm) {
        uploadForm.onsubmit = function(e) {
            e.preventDefault();
            const btn = document.getElementById('btnSubmitUpload');
            const cancelBtn = document.getElementById('btnCancelUpload');
            const progressBox = document.getElementById('uploadProgressContainer');
            const progressBar = document.getElementById('uploadProgressBar');
            const percentText = document.getElementById('uploadPercentText');
            const stageText = document.getElementById('uploadStageText');
            const rateText = document.getElementById('uploadTransferRate');
            const sizeText = document.getElementById('uploadSizeInfo');

            if (btn) btn.disabled = true;
            if (cancelBtn) cancelBtn.style.display = 'none';
            if (progressBox) progressBox.style.display = 'block';

            const startTime = Date.now();
            const fd = new FormData(uploadForm);
            const xhr = new XMLHttpRequest();

            xhr.open('POST', uploadForm.action, true);
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

            xhr.upload.onprogress = function(evt) {
                if (evt.lengthComputable) {
                    const percent = Math.round((evt.loaded / evt.total) * 100);
                    if (progressBar) progressBar.style.width = percent + '%';
                    if (percentText) percentText.textContent = percent + '%';
                    
                    const elapsed = (Date.now() - startTime) / 1000;
                    if (elapsed > 0.3) {
                        const speedMBps = ((evt.loaded / (1024 * 1024)) / elapsed).toFixed(2);
                        if (rateText) rateText.textContent = `Speed: ${speedMBps} MB/s`;
                    }
                    if (sizeText) {
                        sizeText.textContent = `${(evt.loaded / (1024 * 1024)).toFixed(1)} / ${(evt.total / (1024 * 1024)).toFixed(1)} MB`;
                    }

                    if (percent === 100 && stageText) {
                        stageText.textContent = 'Processing media & segmenting RAG vector chunks...';
                    }
                }
            };

            xhr.onload = function() {
                if (btn) btn.disabled = false;
                if (cancelBtn) cancelBtn.style.display = 'inline-flex';
                if (progressBox) progressBox.style.display = 'none';

                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const data = JSON.parse(xhr.responseText);
                        if (data.status === 'success') {
                            closeUploadModal();
                            uploadForm.reset();
                            const fileNameEl = document.getElementById('matSelectedFileName');
                            if (fileNameEl) fileNameEl.textContent = 'Supports documents, presentations, videos, and books';
                            
                            insertMaterialCard(data);
                            showToast(`"${data.title}" uploaded and indexed for AI search!`);
                        } else {
                            showToast(data.message || 'Upload failed', 'error');
                        }
                    } catch (err) {
                        showToast('Failed to parse server response.', 'error');
                    }
                } else {
                    showToast(`Server returned error ${xhr.status}`, 'error');
                }
            };

            xhr.onerror = function() {
                if (btn) btn.disabled = false;
                if (cancelBtn) cancelBtn.style.display = 'inline-flex';
                if (progressBox) progressBox.style.display = 'none';
                showToast('Network error during file upload.', 'error');
            };

            xhr.send(fd);
        };
    }

    if (window.lucide) lucide.createIcons();
}


/* ── RAG AI Study Workspace & Material Selection Controller ── */
if (typeof window.selectedMaterialIds === 'undefined') window.selectedMaterialIds = new Set();
if (typeof window.selectedMaterialsMap === 'undefined') window.selectedMaterialsMap = new Map();
if (typeof window.currentWorkspaceMode === 'undefined') window.currentWorkspaceMode = 'ask';
if (typeof window.currentExplainLevel === 'undefined') window.currentExplainLevel = 'detailed';
if (typeof window.strictMaterialMode === 'undefined') window.strictMaterialMode = true;
if (typeof window.currentQuizData === 'undefined') window.currentQuizData = null;
if (typeof window.currentQuizIndex === 'undefined') window.currentQuizIndex = 0;
if (typeof window.quizScore === 'undefined') window.quizScore = 0;

var selectedMaterialIds = window.selectedMaterialIds;
var selectedMaterialsMap = window.selectedMaterialsMap;
var currentWorkspaceMode = window.currentWorkspaceMode;
var currentExplainLevel = window.currentExplainLevel;
var strictMaterialMode = window.strictMaterialMode;
var currentQuizData = window.currentQuizData;
var currentQuizIndex = window.currentQuizIndex;
var quizScore = window.quizScore;

function getChatHistoryContainer() {
    return document.getElementById('chatCanvasStream') || document.getElementById('workspaceChatHistory') || document.getElementById('awChatStream');
}

function handleMaterialSelectionChange(elem) {
    const checkboxes = document.querySelectorAll('.mat-card-select-check, .workspace-mat-check');
    selectedMaterialIds.clear();
    selectedMaterialsMap.clear();

    checkboxes.forEach(cb => {
        const id = parseInt(cb.dataset.id);
        if (!id) return;
        const card = document.getElementById(`mat-card-${id}`) || document.getElementById(`mat-item-${id}`);

        if (cb.checked) {
            selectedMaterialIds.add(id);
            selectedMaterialsMap.set(id, {
                id: id,
                title: cb.dataset.title || 'Untitled Resource',
                unit: cb.dataset.unit || 'General',
                type: cb.dataset.type || 'document',
                rag: cb.dataset.rag === 'true'
            });
            if (card) card.classList.add('selected');
        } else {
            if (card) card.classList.remove('selected');
        }
    });

    // Save selection to localStorage so cross-page redirects preserve context
    localStorage.setItem('edumi_selected_rag_materials', JSON.stringify(Array.from(selectedMaterialIds)));

    updateSelectionHeaderUI();
}

function handleRagSelectionChange() {
    handleMaterialSelectionChange();
}

function updateSelectionHeaderUI() {
    const count = selectedMaterialIds.size;
    const countText = document.getElementById('selectedCountText');
    if (countText) {
        countText.textContent = `${count} Resource${count === 1 ? '' : 's'} Selected`;
    }

    const selectChip = document.getElementById('workspaceSelectCountChip');
    if (selectChip) {
        selectChip.textContent = `${count} selected`;
    }

    const scopeCount = document.getElementById('ragScopeCount');
    if (scopeCount) {
        scopeCount.textContent = count;
    }

    const ctaHeader = document.getElementById('btnStartAiChatHeader');
    if (ctaHeader) {
        ctaHeader.disabled = (count === 0);
    }

    if (typeof renderWorkspaceScopePills === 'function') {
        renderWorkspaceScopePills();
    }
}

function selectAllMaterials() {
    const checkboxes = document.querySelectorAll('.mat-card-select-check, .workspace-mat-check');
    checkboxes.forEach(cb => cb.checked = true);
    handleMaterialSelectionChange();
    showToast(`Selected all ${selectedMaterialIds.size} study resources.`);
}

function clearMaterialSelection() {
    const checkboxes = document.querySelectorAll('.mat-card-select-check, .workspace-mat-check');
    checkboxes.forEach(cb => cb.checked = false);
    handleMaterialSelectionChange();
    showToast('Cleared material selection.');
}

function toggleSelectAllWorkspaceMaterials(checked) {
    const checkboxes = document.querySelectorAll('.workspace-mat-check, .mat-card-select-check');
    checkboxes.forEach(cb => cb.checked = checked);
    handleMaterialSelectionChange();
}

function clearWorkspaceMaterialSelection() {
    toggleSelectAllWorkspaceMaterials(false);
}

function filterWorkspaceMaterialsList(query) {
    const q = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('.workspace-mat-item, .rag-material-card');
    items.forEach(item => {
        const title = (item.innerText || item.textContent || '').toLowerCase();
        if (!q || title.includes(q)) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

function focusMaterialsSelection() {
    const list = document.getElementById('workspaceMaterialsList') || document.getElementById('workspaceMaterialsChecklist');
    if (list) {
        list.scrollTop = 0;
        list.style.transition = 'box-shadow 0.3s ease';
        list.style.boxShadow = '0 0 0 3px #6366f1';
        setTimeout(() => { list.style.boxShadow = ''; }, 1500);
    }
}

function handleAttachmentClip() {
    showToast('AI responses are strictly grounded in your selected course materials.', 'info');
}

function filterMaterialsByRagStatus(status) {
    const cards = document.querySelectorAll('.material-card');
    cards.forEach(card => {
        const cb = card.querySelector('.mat-card-select-check');
        if (!cb) return;
        const isRagReady = (cb.dataset.rag === 'true');
        
        if (status === 'all') {
            card.style.display = 'flex';
        } else if (status === 'ready') {
            card.style.display = isRagReady ? 'flex' : 'none';
        } else if (status === 'processing') {
            card.style.display = !isRagReady ? 'flex' : 'none';
        }
    });
}

function redirectToWorkspaceWithSelection(e) {
    if (selectedMaterialIds.size === 0) {
        e.preventDefault();
        showToast('Please select at least one resource to start AI Study Chat.', 'error');
        return;
    }
    const ids = Array.from(selectedMaterialIds).join(',');
    e.preventDefault();
    window.location.href = `/meetings/library/rag/?materials=${encodeURIComponent(ids)}`;
}

/* ── Workspace Scope & Mode Selectors ── */
function renderWorkspaceScopePills() {
    const pillsList = document.getElementById('chatScopePillsList') || document.getElementById('workspaceScopePillsList');
    const checklistBox = document.getElementById('workspaceMaterialsChecklist');
    
    if (pillsList) pillsList.innerHTML = '';
    if (checklistBox) checklistBox.innerHTML = '';

    if (selectedMaterialIds.size === 0) {
        if (pillsList) pillsList.innerHTML = '<span class="workspace-scope-pill" style="background: #ef4444; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem;">No materials selected</span>';
        if (checklistBox) checklistBox.innerHTML = '<div style="font-size: 0.75rem; color: var(--mat-text-muted);">No materials selected yet. Return to catalog to select resources.</div>';
        return;
    }

    selectedMaterialsMap.forEach((mat, id) => {
        if (pillsList) {
            const pill = document.createElement('span');
            pill.className = 'workspace-scope-pill';
            pill.style.cssText = 'background: #e0e7ff; color: #3730a3; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; margin-right: 4px; display: inline-flex; align-items: center;';
            pill.textContent = mat.title.length > 18 ? mat.title.substring(0, 18) + '...' : mat.title;
            pillsList.appendChild(pill);
        }

        if (checklistBox) {
            const item = document.createElement('label');
            item.className = 'checklist-item';
            item.innerHTML = `
                <input type="checkbox" checked onchange="toggleWorkspaceMaterialSelection(${id}, this.checked)">
                <span title="${escapeHtml(mat.title)}">${escapeHtml(mat.title)}</span>
            `;
            checklistBox.appendChild(item);
        }
    });
}

function toggleWorkspaceMaterialSelection(id, isChecked) {
    const cbOnCard = document.querySelector(`.mat-card-select-check[data-id="${id}"], .workspace-mat-check[data-id="${id}"]`);
    if (cbOnCard) cbOnCard.checked = isChecked;

    if (isChecked) {
        selectedMaterialIds.add(id);
    } else {
        selectedMaterialIds.delete(id);
        selectedMaterialsMap.delete(id);
    }

    localStorage.setItem('edumi_selected_rag_materials', JSON.stringify(Array.from(selectedMaterialIds)));
    updateSelectionHeaderUI();
    showToast(`Updated active AI context (${selectedMaterialIds.size} materials).`);
}

function selectWorkspaceMode(mode) {
    currentWorkspaceMode = mode;
    
    const modeBtns = document.querySelectorAll('.mode-btn');
    modeBtns.forEach(btn => {
        if (btn.dataset.mode === mode) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    const levelSel = document.getElementById('explainLevelSelector');
    if (levelSel) {
        levelSel.style.display = (mode === 'explain') ? 'flex' : 'none';
    }

    const badge = document.getElementById('activeModeBadge');
    const input = document.getElementById('chatPromptInput') || document.getElementById('aiWorkspacePromptInput');
    
    const modeNames = {
        'ask': 'Mode 1: Ask (Q&A)',
        'explain': `Mode 2: Explain (${currentExplainLevel.toUpperCase()})`,
        'summarize': 'Mode 3: Summarize',
        'quiz': 'Mode 4: Practice Quiz',
        'revision': 'Mode 5: Study & Revision'
    };

    const placeholders = {
        'ask': 'Ask anything about your study materials...',
        'explain': `Enter a topic to explain at ${currentExplainLevel} level...`,
        'summarize': 'Press Enter to generate a structured summary of selected materials...',
        'quiz': 'Press Enter to generate a practice quiz from selected materials...',
        'revision': 'Press Enter to generate revision flashcards & key points...'
    };

    if (badge) badge.textContent = modeNames[mode] || 'Mode: Ask';
    if (input) input.placeholder = placeholders[mode] || 'Ask anything...';
}

function setExplainLevel(level, elem) {
    currentExplainLevel = level;
    const chips = document.querySelectorAll('.level-chip');
    chips.forEach(c => c.classList.remove('active'));
    if (elem) elem.classList.add('active');
    selectWorkspaceMode('explain');
}

function toggleStrictMaterialMode(enabled) {
    strictMaterialMode = enabled;
    showToast(enabled ? 'Strict Material Mode ENABLED: Answers strictly grounded in selected materials.' : 'Strict Material Mode DISABLED: Allows general knowledge fallback.');
}

function runSuggestedPrompt(txt) {
    const input = document.getElementById('chatPromptInput') || document.getElementById('aiWorkspacePromptInput');
    if (input) {
        input.value = txt;
        handleWorkspaceSubmit();
    }
}

/* ── Workspace RAG Execution & Rendering ── */
function handleChatInputSubmit() {
    handleWorkspaceSubmit();
}

function handleWorkspaceSubmit() {
    const input = document.getElementById('chatPromptInput') || document.getElementById('aiWorkspacePromptInput');
    if (!input) return;
    const prompt = input.value.trim();

    if (selectedMaterialIds.size === 0) {
        showToast('Please select at least one study material before launching an AI query.', 'error');
        return;
    }

    if (!prompt && ['ask', 'explain'].includes(currentWorkspaceMode)) {
        showToast('Please type a prompt or topic to explore.', 'error');
        return;
    }

    input.value = '';

    // Append User Prompt to Chat
    if (prompt) {
        appendChatMessage('user', prompt);
    }

    // Append AI Loading Indicator
    const loadingId = 'loading-' + Date.now();
    appendLoadingBubble(loadingId, `AI is searching ${selectedMaterialIds.size} selected study materials...`);

    executeRagApiCall(prompt, loadingId, false);
}

function executeRagApiCall(prompt, loadingId, allowExternal = false) {
    fetch('/meetings/library/rag/api/chat/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken'),
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({
            material_ids: Array.from(selectedMaterialIds),
            prompt: prompt,
            mode: currentWorkspaceMode,
            explain_level: currentExplainLevel,
            strict_mode: strictMaterialMode,
            allow_external: allowExternal
        })
    })
    .then(res => res.json())
    .then(data => {
        removeLoadingBubble(loadingId);

        if (data.status === 'success') {
            if (data.not_found) {
                renderNotFoundBubble(data, prompt);
            } else if (data.mode === 'quiz') {
                renderQuizRunner(data.quiz);
            } else if (data.mode === 'revision') {
                renderRevisionRunner(data.revision);
            } else {
                appendChatMessage('ai', data.answer, data.sources);
            }
        } else {
            appendChatMessage('ai', `⚠️ ${data.message || 'An error occurred while generating the answer.'}`);
        }
    })
    .catch(err => {
        console.error('RAG Error:', err);
        removeLoadingBubble(loadingId);
        appendChatMessage('ai', '⚠️ Connection error while reaching AI Study Workspace. Please try again.');
    });
}

function appendChatMessage(role, text, sources = []) {
    const history = getChatHistoryContainer();
    if (!history) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message ${role}`;

    const avatarHtml = role === 'user' 
        ? `<div class="chat-avatar user">U</div>`
        : `<div class="chat-avatar ai">AI</div>`;

    let sourcesHtml = '';
    if (sources && sources.length > 0) {
        sourcesHtml = `
            <div class="citations-box">
                <div class="citations-title">
                    <i data-lucide="book-marked" style="width: 13px; height: 13px;"></i> Sources
                </div>
                <div class="citation-pill-list">
                    ${sources.map(s => `
                        <button type="button" class="citation-pill" onclick="openCitationDocViewer(${s.material_id}, ${s.page_number}, '${escapeHtml(s.title)}', '${escapeHtml(s.snippet)}')">
                            📚 ${escapeHtml(s.title)} (Page ${s.page_number})
                        </button>
                    `).join('')}
                </div>
            </div>
        `;
    }

    const formattedText = formatMarkdown(text);

    msgDiv.innerHTML = `
        ${avatarHtml}
        <div class="chat-bubble">
            <div>${formattedText}</div>
            ${sourcesHtml}
        </div>
    `;

    history.appendChild(msgDiv);
    history.scrollTop = history.scrollHeight;

    if (window.lucide) lucide.createIcons();
}

function renderNotFoundBubble(data, originalPrompt) {
    const history = getChatHistoryContainer();
    if (!history) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-message ai';

    let fallbackBtnHtml = '';
    if (data.can_fallback_external) {
        fallbackBtnHtml = `
            <div style="margin-top: 1rem;">
                <button type="button" class="btn-add-material" onclick="executeRagApiCall('${escapeHtml(originalPrompt)}', 'load-ext-${Date.now()}', true)" style="background: #6366f1; font-size: 0.8125rem;">
                    <i data-lucide="globe" style="width: 14px; height: 14px;"></i> [ Answer using general knowledge ]
                </button>
            </div>
        `;
    }

    msgDiv.innerHTML = `
        <div class="chat-avatar ai">AI</div>
        <div class="chat-bubble" style="border-color: #f59e0b; background: rgba(245, 158, 11, 0.05);">
            <p style="margin: 0; font-weight: 700; color: #b45309;">
                I couldn't find this information in your selected study materials.
            </p>
            <p style="margin: 0.5rem 0 0 0; font-size: 0.84375rem; color: var(--mat-text-muted);">
                Strict Material Mode is enabled, preventing unverified external answers.
            </p>
            ${fallbackBtnHtml}
        </div>
    `;

    history.appendChild(msgDiv);
    history.scrollTop = history.scrollHeight;
    if (window.lucide) lucide.createIcons();
}

/* ── Interactive Practice Quiz Runner ── */
function renderQuizRunner(quizItems) {
    if (!quizItems || quizItems.length === 0) {
        appendChatMessage('ai', 'No quiz questions could be generated from the selected materials.');
        return;
    }

    currentQuizData = quizItems;
    currentQuizIndex = 0;
    quizScore = 0;

    renderCurrentQuizQuestion();
}

function renderCurrentQuizQuestion() {
    const history = getChatHistoryContainer();
    if (!history || !currentQuizData) return;

    const item = currentQuizData[currentQuizIndex];
    const total = currentQuizData.length;

    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-message ai';
    msgDiv.id = `quiz-card-${currentQuizIndex}`;

    msgDiv.innerHTML = `
        <div class="chat-avatar ai">AI</div>
        <div class="chat-bubble quiz-runner-card" style="width: 100%; max-width: 600px;">
            <div class="quiz-score-bar">
                <span style="font-weight: 800; font-size: 0.875rem; color: #6366f1;">
                    Question ${currentQuizIndex + 1} / ${total}
                </span>
                <span style="font-weight: 700; font-size: 0.8125rem; color: var(--mat-text-muted);">
                    Score: ${quizScore} / ${currentQuizIndex} (${currentQuizIndex > 0 ? Math.round((quizScore/currentQuizIndex)*100) : 100}%)
                </span>
            </div>

            <h4 style="margin: 0; font-size: 1rem; font-weight: 800; line-height: 1.5; color: var(--mat-text-main);">
                ${escapeHtml(item.question)}
            </h4>

            <div style="display: flex; flex-direction: column; gap: 0.65rem;" id="quizOptionsContainer">
                ${item.options.map((opt, idx) => `
                    <div class="quiz-option-item" onclick="selectQuizOption(this, ${idx})">
                        <span style="width: 24px; height: 24px; border-radius: 50%; background: var(--mat-border); display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 800;">${String.fromCharCode(65 + idx)}</span>
                        <span>${escapeHtml(opt)}</span>
                    </div>
                `).join('')}
            </div>

            <div id="quizFeedbackBox" style="display: none; padding: 1rem; border-radius: 0.875rem; font-size: 0.875rem; line-height: 1.5;"></div>

            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem;">
                <span style="font-size: 0.75rem; color: var(--mat-text-muted);">${item.source}</span>
                <button type="button" id="btnSubmitQuizAns" onclick="submitQuizAnswer(${item.correct_index})" class="btn-start-ai-chat" style="padding: 0.5rem 1rem; font-size: 0.8125rem;">
                    Submit Answer
                </button>
            </div>
        </div>
    `;

    history.appendChild(msgDiv);
    history.scrollTop = history.scrollHeight;
    if (window.lucide) lucide.createIcons();
}

if (typeof window.selectedQuizOptIndex === 'undefined') window.selectedQuizOptIndex = null;
var selectedQuizOptIndex = window.selectedQuizOptIndex;
function selectQuizOption(elem, idx) {
    selectedQuizOptIndex = idx;
    const options = elem.parentElement.querySelectorAll('.quiz-option-item');
    options.forEach(o => o.classList.remove('selected'));
    elem.classList.add('selected');
}

function submitQuizAnswer(correctIndex) {
    if (selectedQuizOptIndex === null) {
        showToast('Please select an option before submitting.', 'error');
        return;
    }

    const item = currentQuizData[currentQuizIndex];
    const feedbackBox = document.getElementById('quizFeedbackBox');
    const submitBtn = document.getElementById('btnSubmitQuizAns');
    const options = document.querySelectorAll('.quiz-option-item');

    options.forEach((opt, idx) => {
        opt.onclick = null;
        if (idx === correctIndex) {
            opt.classList.add('correct');
        } else if (idx === selectedQuizOptIndex && idx !== correctIndex) {
            opt.classList.add('incorrect');
        }
    });

    const isCorrect = (selectedQuizOptIndex === correctIndex);
    if (isCorrect) quizScore++;

    if (feedbackBox) {
        feedbackBox.style.display = 'block';
        feedbackBox.style.background = isCorrect ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)';
        feedbackBox.style.color = isCorrect ? '#065f46' : '#991b1b';
        feedbackBox.style.border = `1px solid ${isCorrect ? '#10b981' : '#ef4444'}`;
        feedbackBox.innerHTML = `
            <strong>${isCorrect ? '✓ Correct Answer!' : '❌ Incorrect'}</strong>
            <p style="margin: 0.35rem 0 0 0;">${escapeHtml(item.explanation)}</p>
            <div style="margin-top: 0.5rem; font-weight: 700; font-size: 0.75rem;">Source: ${item.source}</div>
        `;
    }

    if (submitBtn) {
        if (currentQuizIndex + 1 < currentQuizData.length) {
            submitBtn.textContent = 'Next Question →';
            submitBtn.onclick = function() {
                currentQuizIndex++;
                selectedQuizOptIndex = null;
                renderCurrentQuizQuestion();
            };
        } else {
            submitBtn.textContent = 'Finish Quiz';
            submitBtn.onclick = function() {
                appendChatMessage('ai', `🎉 **Quiz Complete!**\n\nFinal Score: **${quizScore} / ${currentQuizData.length}** (${Math.round((quizScore/currentQuizData.length)*100)}% Accuracy).`);
            };
        }
    }
}

/* ── Interactive Revision Flashcards Runner ── */
function renderRevisionRunner(revisionData) {
    if (!revisionData || !revisionData.flashcards) {
        appendChatMessage('ai', 'No revision flashcards generated.');
        return;
    }

    const cards = revisionData.flashcards;
    let cardIdx = 0;

    const history = getChatHistoryContainer();
    if (!history) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-message ai';

    msgDiv.innerHTML = `
        <div class="chat-avatar ai">AI</div>
        <div class="chat-bubble" style="width: 100%; max-width: 600px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                <span style="font-weight: 800; font-size: 0.875rem; color: #6366f1;">
                    <i data-lucide="layers" style="width: 16px; height: 16px;"></i> Revision Flashcards
                </span>
                <span id="flashcardCounterText" style="font-weight: 700; font-size: 0.8125rem; color: var(--mat-text-muted);">
                    Card 1 of ${cards.length}
                </span>
            </div>

            <div class="flashcard-container" id="flashcardBox" onclick="this.classList.toggle('flipped')">
                <div class="flashcard-inner">
                    <div class="flashcard-front">
                        <div style="font-size: 0.75rem; font-weight: 800; text-transform: uppercase; color: #6366f1; margin-bottom: 0.5rem;">Front · Question / Prompt</div>
                        <h3 id="flashcardFrontText" style="margin: 0; font-size: 1.125rem; font-weight: 800; color: var(--mat-text-main);">
                            ${escapeHtml(cards[0].front)}
                        </h3>
                        <div style="font-size: 0.75rem; color: var(--mat-text-muted); margin-top: 1rem;">(Click card to flip)</div>
                    </div>
                    <div class="flashcard-back">
                        <div style="font-size: 0.75rem; font-weight: 800; text-transform: uppercase; color: #a5b4fc; margin-bottom: 0.5rem;">Back · Answer / Explanation</div>
                        <p id="flashcardBackText" style="margin: 0; font-size: 0.9375rem; line-height: 1.5; color: white;">
                            ${escapeHtml(cards[0].back)}
                        </p>
                        <div id="flashcardSourceText" style="font-size: 0.75rem; color: #cbd5e1; margin-top: 1rem;">
                            ${cards[0].source}
                        </div>
                    </div>
                </div>
            </div>

            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 1rem;">
                <button type="button" class="btn-add-unit" onclick="prevFlashcard()">← Prev</button>
                <button type="button" class="btn-add-unit" onclick="nextFlashcard()">Next →</button>
            </div>
        </div>
    `;

    window.prevFlashcard = function() {
        if (cardIdx > 0) {
            cardIdx--;
            updateFlashcardView();
        }
    };

    window.nextFlashcard = function() {
        if (cardIdx + 1 < cards.length) {
            cardIdx++;
            updateFlashcardView();
        }
    };

    function updateFlashcardView() {
        const box = document.getElementById('flashcardBox');
        if (box) box.classList.remove('flipped');
        
        setTimeout(() => {
            document.getElementById('flashcardCounterText').textContent = `Card ${cardIdx + 1} of ${cards.length}`;
            document.getElementById('flashcardFrontText').textContent = cards[cardIdx].front;
            document.getElementById('flashcardBackText').textContent = cards[cardIdx].back;
            document.getElementById('flashcardSourceText').textContent = cards[cardIdx].source;
        }, 150);
    }

    history.appendChild(msgDiv);
    history.scrollTop = history.scrollHeight;
    if (window.lucide) lucide.createIcons();
}

/* ── Document Viewer Citation Modal ── */
function openCitationDocViewer(materialId, pageNum, title, snippet) {
    const modal = document.getElementById('citationDocViewerModal');
    if (!modal) return;

    modal.style.display = 'flex';
    document.getElementById('citationDocTitle').textContent = title;
    document.getElementById('citationPageBadge').textContent = `Page ${pageNum}`;

    const iframe = document.getElementById('citationIframe');
    const snippetBox = document.getElementById('citationSnippetBox');
    const snippetText = document.getElementById('citationSnippetText');

    fetch(`/meetings/materials/${materialId}/detail-api/`)
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success' && data.file_url) {
                iframe.src = `${data.file_url}#page=${pageNum}&toolbar=0`;
                iframe.style.display = 'block';
                snippetBox.style.display = 'none';
            } else {
                iframe.style.display = 'none';
                snippetBox.style.display = 'block';
                snippetText.innerHTML = `<strong>Passage Excerpt (Page ${pageNum}):</strong><br><br>${escapeHtml(snippet)}`;
            }
        })
        .catch(() => {
            iframe.style.display = 'none';
            snippetBox.style.display = 'block';
            snippetText.textContent = snippet;
        });

    if (window.lucide) lucide.createIcons();
}

function closeCitationDocViewer() {
    const modal = document.getElementById('citationDocViewerModal');
    if (modal) modal.style.display = 'none';
    const iframe = document.getElementById('citationIframe');
    if (iframe) iframe.src = '';
}

/* ── Instructor AI Settings ── */
function openInstructorSettingsModal() {
    const modal = document.getElementById('instructorSettingsModal');
    if (modal) modal.style.display = 'flex';
}

function closeInstructorSettingsModal() {
    const modal = document.getElementById('instructorSettingsModal');
    if (modal) modal.style.display = 'none';
}

function saveInstructorSettings(e) {
    e.preventDefault();
    const form = document.getElementById('instructorSettingsForm');
    const fd = new FormData(form);
    const data = {};
    fd.forEach((val, key) => data[key] = true);

    fetch('/meetings/library/rag/api/instructor-settings/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(res => {
        closeInstructorSettingsModal();
        showToast('Instructor AI controls saved successfully!');
    });
}

/* ── Utilities ── */
function appendLoadingBubble(id, text) {
    const history = getChatHistoryContainer();
    if (!history) return;

    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-message ai';
    msgDiv.id = id;
    msgDiv.innerHTML = `
        <div class="chat-avatar ai">AI</div>
        <div class="chat-bubble" style="display: flex; align-items: center; gap: 0.65rem; color: var(--mat-text-muted);">
            <span class="ai-pulse-dot"></span>
            <span>${escapeHtml(text)}</span>
        </div>
    `;

    history.appendChild(msgDiv);
    history.scrollTop = history.scrollHeight;
}

function removeLoadingBubble(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function formatMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italics
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    // Newlines
    html = html.replace(/\n/g, '<br>');
    return html;
}

// Restore saved selection on load & auto-initialize UI handlers
function bootstrapStudyMaterials() {
    initStudyMaterials();
    const saved = localStorage.getItem('edumi_selected_rag_materials');
    if (saved) {
        try {
            const ids = JSON.parse(saved);
            ids.forEach(id => {
                const cb = document.querySelector(`.mat-card-select-check[data-id="${id}"]`);
                if (cb) cb.checked = true;
            });
            handleMaterialSelectionChange();
        } catch(e) {}
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrapStudyMaterials);
} else {
    bootstrapStudyMaterials();
}
document.addEventListener('turbo:load', bootstrapStudyMaterials);
document.addEventListener('turbo:render', bootstrapStudyMaterials);
