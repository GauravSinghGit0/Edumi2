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
        background: ${type === 'success' ? '#0f172a' : '#991b1b'};
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
    if (m) m.style.display = 'flex';
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

    const badgeColor = data.badge_color || '#4f46e5';
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
        dropzone.onclick = () => fileInput.click();
        fileInput.onchange = () => {
            if (fileInput.files[0]) {
                const f = fileInput.files[0];
                document.getElementById('matSelectedFileName').textContent = `Selected: ${f.name} (${(f.size / (1024*1024)).toFixed(2)} MB)`;
                if (titleInput && !titleInput.value.trim()) {
                    const cleanName = f.name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " ");
                    titleInput.value = cleanName.charAt(0).toUpperCase() + cleanName.slice(1);
                }
            }
        };
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

document.addEventListener('DOMContentLoaded', initStudyMaterials);
document.addEventListener('turbo:load', initStudyMaterials);
