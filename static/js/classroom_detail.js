/* static/js/classroom_detail.js - Interactive controller for Classroom Hub, Stream, and Roster */

/* ── Tab Switcher Logic ── */
function getClassroomId() {
    const container = document.querySelector('.classroom-detail-container');
    return container ? (container.dataset.classroomId || '') : '';
}

function checkTabBadgesSeen() {
    const classroomId = getClassroomId();
    if (!classroomId) return;

    // Check Study Materials Badge
    const matBadge = document.getElementById('materialsCountBadge');
    if (matBadge) {
        const currentMat = parseInt(matBadge.dataset.count || matBadge.textContent || '0', 10);
        const seenMat = parseInt(localStorage.getItem('materials_seen_' + classroomId) || '0', 10);
        if (seenMat >= currentMat) {
            matBadge.style.display = 'none';
        } else if (seenMat > 0 && currentMat > seenMat) {
            matBadge.textContent = (currentMat - seenMat);
            matBadge.style.display = 'inline-flex';
        }
    }

    // Check Sessions Badge
    const sessBadge = document.getElementById('sessionsCountBadge');
    if (sessBadge) {
        const currentSess = parseInt(sessBadge.dataset.count || sessBadge.textContent || '0', 10);
        const seenSess = parseInt(localStorage.getItem('sessions_seen_' + classroomId) || '0', 10);
        if (seenSess >= currentSess) {
            sessBadge.style.display = 'none';
        } else if (seenSess > 0 && currentSess > seenSess) {
            sessBadge.textContent = (currentSess - seenSess);
            sessBadge.style.display = 'inline-flex';
        }
    }
}

function switchClassroomTab(tabName) {
    document.querySelectorAll('.tab-content-panel').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.classroom-tab-btn').forEach(btn => btn.classList.remove('active'));

    let targetPanel = null;
    let targetBtn = null;

    const classroomId = getClassroomId();

    if (tabName === 'stream') {
        targetPanel = document.getElementById('tabContentStream');
        targetBtn = document.getElementById('tabBtnStream');
        // Clear unread stream badge on open
        const streamBadge = document.getElementById('streamCountBadge');
        if (streamBadge) streamBadge.style.display = 'none';
    } else if (tabName === 'materials') {
        targetPanel = document.getElementById('tabContentMaterials');
        targetBtn = document.getElementById('tabBtnMaterials');
        const matBadge = document.getElementById('materialsCountBadge');
        if (matBadge) {
            matBadge.style.display = 'none';
            if (classroomId) {
                const currentMat = parseInt(matBadge.dataset.count || matBadge.textContent || '0', 10);
                localStorage.setItem('materials_seen_' + classroomId, currentMat.toString());
            }
        }
    } else if (tabName === 'sessions') {
        targetPanel = document.getElementById('tabContentSessions');
        targetBtn = document.getElementById('tabBtnSessions');
        const sessBadge = document.getElementById('sessionsCountBadge');
        if (sessBadge) {
            sessBadge.style.display = 'none';
            if (classroomId) {
                const currentSess = parseInt(sessBadge.dataset.count || sessBadge.textContent || '0', 10);
                localStorage.setItem('sessions_seen_' + classroomId, currentSess.toString());
            }
        }
    } else if (tabName === 'people') {
        targetPanel = document.getElementById('tabContentPeople');
        targetBtn = document.getElementById('tabBtnPeople');
    }

    if (targetPanel) targetPanel.style.display = 'block';
    if (targetBtn) targetBtn.classList.add('active');

    if (window.lucide) lucide.createIcons();
}

document.addEventListener('DOMContentLoaded', checkTabBadgesSeen);
document.addEventListener('turbo:load', checkTabBadgesSeen);
if (document.readyState !== 'loading') {
    checkTabBadgesSeen();
}

/* ── Copy Classroom Code ── */
function copyClassCode(code) {
    navigator.clipboard.writeText(code).then(() => {
        alert('Classroom Code ' + code + ' copied to clipboard!');
    });
}

/* ── Lightbox Controls ── */
function openStreamLightbox(src) {
    const lb = document.getElementById('streamLightbox');
    const img = document.getElementById('streamLightboxImg');
    if (lb && img) {
        img.src = src;
        lb.style.display = 'flex';
    }
}

function closeStreamLightbox() {
    const lb = document.getElementById('streamLightbox');
    if (lb) lb.style.display = 'none';
}

/* ── Emoji Picker Controls ── */
var STREAM_EMOJIS = ['👍','❤️','🎉','👏','🔥','✨','🚀','📚','💡','💯','🙌','😊','🎓','📝','✅','⭐','🤔','👀','💪','🤩'];

function toggleStreamEmojiPicker() {
    const p = document.getElementById('streamEmojiPicker');
    if (!p) return;
    if (p.style.display === 'block') {
        p.style.display = 'none';
    } else {
        renderStreamEmojiGrid();
        p.style.display = 'block';
    }
}

function renderStreamEmojiGrid() {
    const grid = document.getElementById('streamEmojiGrid');
    if (!grid || grid.children.length > 0) return;
    STREAM_EMOJIS.forEach(emoji => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'emoji-btn';
        btn.textContent = emoji;
        btn.onclick = () => {
            insertStreamEmoji(emoji);
            document.getElementById('streamEmojiPicker').style.display = 'none';
        };
        grid.appendChild(btn);
    });
}

function insertStreamEmoji(emoji) {
    const ta = document.getElementById('streamContentInput');
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const text = ta.value;
    ta.value = text.substring(0, start) + emoji + text.substring(end);
    ta.focus();
    ta.selectionStart = ta.selectionEnd = start + emoji.length;
    validateStreamComposer();
}

function validateStreamComposer() {
    const ta = document.getElementById('streamContentInput');
    const img = document.getElementById('streamImageInput');
    const file = document.getElementById('streamFileInput');
    const btn = document.getElementById('btnStreamSubmit');
    if (!btn) return;
    const hasText = ta && ta.value.trim().length > 0;
    const hasImg = img && img.files && img.files.length > 0;
    const hasFile = file && file.files && file.files.length > 0;
    btn.disabled = !(hasText || hasImg || hasFile);
}
window.validateStreamComposer = validateStreamComposer;

/* ── Initialize Stream Composer & Dynamic Handlers ── */
function initClassroomDetail() {
    const ta = document.getElementById('streamContentInput');
    const imgInput = document.getElementById('streamImageInput');
    const fileInput = document.getElementById('streamFileInput');
    const form = document.getElementById('classroomStreamForm');
    const strip = document.getElementById('streamPreviewStrip');

    if (ta) {
        ['input', 'keyup', 'change', 'paste'].forEach(evt => {
            ta.addEventListener(evt, () => {
                ta.style.height = 'auto';
                ta.style.height = Math.min(ta.scrollHeight, 220) + 'px';
                validateStreamComposer();
            });
        });
        validateStreamComposer();
    }

    if (imgInput) {
        imgInput.addEventListener('change', () => {
            if (imgInput.files && imgInput.files[0]) {
                showPreviewStrip('image', imgInput.files[0].name);
            }
            validateStreamComposer();
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files && fileInput.files[0]) {
                showPreviewStrip('file', fileInput.files[0].name);
            }
            validateStreamComposer();
        });
    }

    function showPreviewStrip(type, filename) {
        if (!strip) return;
        strip.innerHTML = '';
        strip.style.display = 'flex';
        const card = document.createElement('div');
        card.className = 'stream-preview-card';
        card.innerHTML = `
            <span>${type === 'image' ? '📷' : '📎'}</span>
            <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${filename}</span>
            <button type="button" class="stream-preview-remove" title="Remove">×</button>
        `;
        card.querySelector('.stream-preview-remove').onclick = () => {
            if (type === 'image' && imgInput) imgInput.value = '';
            else if (fileInput) fileInput.value = '';
            strip.innerHTML = '';
            strip.style.display = 'none';
            validateStreamComposer();
        };
        strip.appendChild(card);
    }

    /* ── AJAX Stream Posting ── */
    if (form && !form.dataset.bound) {
        form.dataset.bound = 'true';
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            const btn = document.getElementById('btnStreamSubmit');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span>Posting...</span>';
            }

            const fd = new FormData(form);

            fetch(form.action, {
                method: 'POST',
                body: fd,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    appendStreamPost(data);
                    form.reset();
                    if (ta) ta.style.height = '60px';
                    if (strip) {
                        strip.innerHTML = '';
                        strip.style.display = 'none';
                    }
                } else {
                    alert(data.message || 'Failed to post message');
                }
            })
            .catch(err => {
                console.error('Error posting stream message:', err);
            })
            .finally(() => {
                if (btn) {
                    btn.innerHTML = '<i data-lucide="send" style="width: 15px; height: 15px;"></i><span>Post Update</span>';
                    validateStreamComposer();
                }
                if (window.lucide) lucide.createIcons();
            });
        });
    }

    validateStreamComposer();
    if (window.lucide) lucide.createIcons();
}

document.addEventListener('DOMContentLoaded', initClassroomDetail);
document.addEventListener('turbo:load', initClassroomDetail);
if (document.readyState !== 'loading') {
    initClassroomDetail();
}

/* ── Append New Message / Post to Stream Feed ── */
function appendStreamPost(data) {
    const empty = document.getElementById('streamEmptyBox');
    if (empty) empty.remove();

    const feed = document.getElementById('streamFeedContainer');
    if (!feed) return;

    const card = document.createElement('div');
    card.className = 'stream-post-card';
    card.id = 'post-' + (data.message_id || Date.now());

    const isTeacher = (data.sender_role === 'Teacher' || data.sender_role === 'Instructor');
    const roleClass = isTeacher ? 'role-badge-teacher' : 'role-badge-student';
    const roleLabel = isTeacher ? 'Teacher' : 'Student';

    let imageHtml = '';
    if (data.image_url) {
        imageHtml = `<img src="${data.image_url}" alt="Attachment" class="post-image-attachment" onclick="openStreamLightbox(this.src)">`;
    }

    let fileHtml = '';
    if (data.file_url) {
        fileHtml = `
            <a href="${data.file_url}" download class="post-file-card">
                <div class="post-file-info">
                    <i data-lucide="file-text" style="width: 20px; height: 20px; color: var(--stream-primary); flex-shrink:0;"></i>
                    <span class="post-file-name">${data.file_name || 'Attached File'}</span>
                </div>
                <i data-lucide="download" style="width: 16px; height: 16px; color: var(--stream-text-muted);"></i>
            </a>
        `;
    }

    let contentHtml = '';
    if (data.content) {
        contentHtml = `<div class="post-body-text">${escapeHtml(data.content)}</div>`;
    }

    const avatarUrl = data.sender_pfp || `https://ui-avatars.com/api/?name=${encodeURIComponent(data.sender_name || data.sender || 'User')}&background=6366f1&color=fff`;

    card.innerHTML = `
        <div class="post-header">
            <div class="post-author-meta">
                <img src="${avatarUrl}" 
                     alt="${data.sender}" 
                     class="post-avatar"
                     onerror="this.src='https://ui-avatars.com/api/?name=${encodeURIComponent(data.sender || 'User')}&background=6366f1&color=fff'">
                <div>
                    <div class="post-author-name">
                        <span>${escapeHtml(data.sender_name || data.sender)}</span>
                        <span class="${roleClass}">${roleLabel}</span>
                    </div>
                    <div class="post-time">${data.created_at || 'Just now'} · ${data.created_date || 'Today'}</div>
                </div>
            </div>
        </div>
        ${contentHtml}
        ${imageHtml}
        ${fileHtml}
    `;

    // Prepend new post to the top of the stream
    feed.insertBefore(card, feed.firstChild);

    // If stream is not the currently active tab, show unread indicator
    const streamPanel = document.getElementById('tabContentStream');
    if (streamPanel && streamPanel.style.display === 'none') {
        const badge = document.getElementById('streamCountBadge');
        if (badge) {
            badge.style.display = 'inline-block';
            badge.textContent = 'New';
        }
    }

    if (window.lucide) lucide.createIcons();
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/* ── WebSocket Real-Time Message Listener ── */
window.addEventListener('new_message', function(e) {
    const d = e.detail;
    const container = document.querySelector('.classroom-detail-container');
    const currentConvId = container ? container.dataset.conversationId : null;
    const currentUsername = container ? container.dataset.username : null;

    if (currentConvId && d.conversation_id == currentConvId) {
        // If the message was sent by someone else, append it
        if (d.sender !== currentUsername) {
            appendStreamPost({
                sender: d.sender,
                sender_name: d.sender_name || d.sender,
                sender_role: d.sender_role || 'Student',
                sender_pfp: d.sender_pfp,
                content: d.message,
                image_url: d.image_url,
                file_url: d.file_url,
                file_name: d.file_name,
                created_at: d.created_at || 'Just now',
                created_date: 'Today',
            });
        }
    }
});

/* ── CSRF and Enrollment Action Helpers ── */
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

function approveRequest(membershipId) {
    fetch(`/meetings/classroom/approve/${membershipId}/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken'), 'Content-Type': 'application/json' }
    }).then(res => res.json()).then(data => { if (data.status === 'success') location.reload(); });
}

function approveAllRequests(classroomId) {
    const btn = document.getElementById('btnApproveAll');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="width: 14px; height: 14px;"></span> Approving...';
    }
    fetch(`/meetings/classroom/${classroomId}/approve-all/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken'), 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            location.reload();
        } else {
            alert(data.message || 'Error approving requests');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = 'Approve All';
            }
        }
    })
    .catch(err => {
        console.error('Error approving all requests:', err);
        if (btn) btn.disabled = false;
    });
}

function denyAllRequests(classroomId) {
    if (!confirm('Are you sure you want to deny ALL pending student requests?')) return;
    const btn = document.getElementById('btnDenyAll');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true" style="width: 14px; height: 14px;"></span> Denying...';
    }
    fetch(`/meetings/classroom/${classroomId}/deny-all/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken'), 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            location.reload();
        } else {
            alert(data.message || 'Error denying requests');
            if (btn) btn.disabled = false;
        }
    })
    .catch(err => {
        console.error('Error denying all requests:', err);
        if (btn) btn.disabled = false;
    });
}

function toggleAutoApprove(classroomId) {
    const toggle = document.getElementById('autoApproveToggle');
    const slider = document.getElementById('autoApproveSlider');
    const knob = document.getElementById('autoApproveKnob');
    
    fetch(`/meetings/classroom/${classroomId}/toggle-auto-approve/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken'), 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            const isEnabled = data.auto_approve;
            if (toggle) toggle.checked = isEnabled;
            if (slider) slider.style.backgroundColor = isEnabled ? '#10b981' : '#cbd5e1';
            if (knob) knob.style.left = isEnabled ? '17px' : '3px';
        } else {
            alert(data.message || 'Failed to update auto-approve setting');
            if (toggle) toggle.checked = !toggle.checked;
        }
    })
    .catch(err => {
        console.error('Error updating auto-approve:', err);
        if (toggle) toggle.checked = !toggle.checked;
    });
}

function filterPendingList(query) {
    const q = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('.pending-item');
    items.forEach(item => {
        const text = (item.dataset.search || item.textContent || '').toLowerCase();
        item.style.display = text.includes(q) ? 'flex' : 'none';
    });
}

function filterEnrolledList(query) {
    const q = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('.enrolled-item');
    items.forEach(item => {
        const text = (item.dataset.search || item.textContent || '').toLowerCase();
        item.style.display = text.includes(q) ? 'flex' : 'none';
    });
}

function denyRequest(membershipId) {
    if (confirm('Deny this request?')) {
        fetch(`/meetings/classroom/deny/${membershipId}/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken'), 'Content-Type': 'application/json' }
        }).then(res => res.json()).then(data => { if (data.status === 'success') location.reload(); });
    }
}

function removeStudent(membershipId) {
    if (confirm('Remove student from class?')) {
        fetch(`/meetings/classroom/remove/${membershipId}/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken'), 'Content-Type': 'application/json' }
        }).then(res => res.json()).then(data => { if (data.status === 'success') location.reload(); });
    }
}

/* ── Meeting Controls ── */
function deleteClassroomMeeting(meetingId) {
    if (!confirm('Are you sure you want to permanently delete this meeting session?')) return;
    fetch(`/meetings/delete/${meetingId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            const el = document.getElementById(`meeting-item-${meetingId}`);
            if (el) {
                el.style.opacity = '0';
                el.style.transform = 'translateY(-10px)';
                setTimeout(() => el.remove(), 250);
            }
        } else {
            alert(data.message || 'Failed to delete meeting');
        }
    })
    .catch(err => console.error('Error deleting meeting:', err));
}

function endClassroomMeeting(meetingId) {
    if (!confirm('End this live meeting session for everyone now?')) return;
    fetch(`/meetings/end/${meetingId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            location.reload();
        } else {
            alert(data.message || 'Failed to end meeting');
        }
    })
    .catch(err => console.error('Error ending meeting:', err));
}

