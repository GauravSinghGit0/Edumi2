/* static/js/inbox.js - Client controller for Messaging & Inbox */

function enableMessagesLayout() {
  const hasShell = document.querySelector('.messages-shell');
  if (!hasShell) {
    document.body.classList.remove('messages-layout-active');
    return;
  }
  document.body.classList.add('messages-layout-active');
  scrollToBottom(false);
}

function focusSearch() {
  const field = document.querySelector('.search-field');
  if (field) {
    field.focus();
  }
}

/* ── Interactive Category & Search Filtering ── */
function escapeHTML(str) {
  return str.replace(/[&<>'"]/g, 
    tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag)
  );
}

function highlightText(text, query) {
  if (!query) return escapeHTML(text);
  const escapedQuery = query.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
  const regex = new RegExp(`(${escapedQuery})`, 'gi');
  const parts = text.split(regex);
  return parts.map(part => {
    if (part.toLowerCase() === query.toLowerCase()) {
      return `<span style="color: #25D366; font-weight: 700;">${escapeHTML(part)}</span>`;
    }
    return escapeHTML(part);
  }).join('');
}

function openNewChatModal() {
  const modal = document.getElementById('newChatModal');
  if (modal) {
    modal.style.display = 'flex';
    const input = document.getElementById('newChatSearchInput');
    if (input) {
      input.value = '';
      setTimeout(() => input.focus(), 50);
      filterNewChatModal('');
    }
  }
}

function closeNewChatModal() {
  const modal = document.getElementById('newChatModal');
  if (modal) {
    modal.style.display = 'none';
  }
}

function switchNewChatTab(tab, btn) {
  document.querySelectorAll('.new-chat-tab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const peopleSec = document.getElementById('newChatPeopleSection');
  const groupsSec = document.getElementById('newChatGroupsSection');
  if (tab === 'people') {
    if (peopleSec) peopleSec.style.display = 'block';
    if (groupsSec) groupsSec.style.display = 'none';
  } else {
    if (peopleSec) peopleSec.style.display = 'none';
    if (groupsSec) groupsSec.style.display = 'block';
  }
}

function filterNewChatModal(query) {
  const q = query.trim().toLowerCase();
  const items = document.querySelectorAll('.new-chat-contact-item');
  items.forEach(item => {
    const searchText = (item.getAttribute('data-search-text') || '').toLowerCase();
    if (!q || searchText.includes(q)) {
      item.style.display = 'flex';
    } else {
      item.style.display = 'none';
    }
  });
}

function applyFilters() {
  const activeTab = document.querySelector('.sidebar-tab.active');
  const tabFilter = activeTab ? activeTab.getAttribute('data-tab') : 'all';
  
  const searchField = document.querySelector('.search-field');
  const query = searchField ? searchField.value.trim().toLowerCase() : '';
  
  const items = document.querySelectorAll('.conversation-item');
  let visibleCount = 0;

  items.forEach(item => {
    // 1. Check tab match
    let matchesTab = false;
    const isGroup = (item.getAttribute('data-is-group') === 'true');
    if (tabFilter === 'all') {
      matchesTab = true;
    } else if (tabFilter === 'groups') {
      matchesTab = isGroup;
    } else if (tabFilter === 'unread') {
      const badge = item.querySelector('.unread-count-pill');
      matchesTab = (badge && parseInt(badge.textContent.trim()) > 0);
    }

    // 2. Check search match
    let matchesSearch = true;
    if (query) {
      const displayName = (item.getAttribute('data-display-name') || '').toLowerCase();
      const username = (item.getAttribute('data-username') || '').toLowerCase();
      matchesSearch = displayName.includes(query) || username.includes(query);
    }

    // Show/hide based on both
    if (matchesTab && matchesSearch) {
      item.style.display = 'flex';
      visibleCount++;
      
      // Highlight matching text in display name
      const displayNameRaw = item.getAttribute('data-display-name-raw') || '';
      const nameSpan = item.querySelector('.other-username');
      if (nameSpan) {
        if (query) {
          nameSpan.innerHTML = highlightText(displayNameRaw, query);
        } else {
          nameSpan.textContent = displayNameRaw;
        }
      }
    } else {
      item.style.display = 'none';
      
      // Reset display name highlight when hidden
      const displayNameRaw = item.getAttribute('data-display-name-raw') || '';
      const nameSpan = item.querySelector('.other-username');
      if (nameSpan) {
        nameSpan.textContent = displayNameRaw;
      }
    }
  });

  const listWrapper = document.querySelector('.messages-list-wrapper');
  if (listWrapper) {
    let searchNoResults = document.getElementById('searchNoResultsState');
    
    if (visibleCount === 0 && items.length > 0) {
      if (!searchNoResults) {
        searchNoResults = document.createElement('div');
        searchNoResults.id = 'searchNoResultsState';
        searchNoResults.setAttribute('style', 'text-align: center; color: var(--msg-text-muted); font-size: 0.85rem; padding: 40px 20px;');
        searchNoResults.textContent = 'No chats or messages found';
        listWrapper.appendChild(searchNoResults);
      } else {
        searchNoResults.style.display = 'block';
      }
    } else {
      if (searchNoResults) {
        searchNoResults.style.display = 'none';
      }
    }
  }
}

function handleSidebarTabClick() {
  document.querySelectorAll('.sidebar-tab').forEach(t => t.classList.remove('active'));
  this.classList.add('active');
  applyFilters();
}

function initSidebarTabs() {
  document.querySelectorAll('.sidebar-tab').forEach(tab => {
    tab.removeEventListener('click', handleSidebarTabClick);
    tab.addEventListener('click', handleSidebarTabClick);
  });
}

let searchDebounceTimeout = null;

function performGlobalUserSearch(query) {
  const container = document.getElementById('globalSearchResultsContainer');
  const list = document.getElementById('globalSearchResultsList');
  const shell = document.querySelector('.messages-shell');
  if (!container || !list) return;

  if (!query) {
    container.style.display = 'none';
    list.innerHTML = '';
    return;
  }

  const searchUrl = (shell && shell.dataset.searchUrl) || "/inbox/search-users-ajax/";
  fetch(searchUrl + "?q=" + encodeURIComponent(query))
    .then(res => res.json())
    .then(data => {
      list.innerHTML = '';
      if (data.users && data.users.length > 0) {
        data.users.forEach(u => {
          if (u.has_conv) {
            const localItem = document.querySelector(`.conversation-item[data-username="${u.username.toLowerCase()}"]`);
            if (localItem && localItem.style.display !== 'none') {
              return;
            }
          }

          const item = document.createElement('a');
          const startUrlTemplate = (shell && shell.dataset.startConvUrl) || "/inbox/start/PLACEHOLDER/";
          item.href = startUrlTemplate.replace('PLACEHOLDER', encodeURIComponent(u.username));
          item.className = 'conversation-item';
          
          const pfpUrl = u.pfp || `https://ui-avatars.com/api/?name=${encodeURIComponent(u.username)}&background=667eea&color=fff`;
          const typeLabel = u.user_type === 'teacher' ? 'Teacher' : 'Student';
          
          item.innerHTML = `
            <div class="avatar-container">
              <img src="${pfpUrl}" alt="${u.username}" class="conversation-avatar" onerror="this.src='https://ui-avatars.com/api/?name=${encodeURIComponent(u.username)}&background=667eea&color=fff'">
            </div>
            <div class="conversation-details">
              <div class="details-top-row">
                <span class="other-username">${highlightText(u.display_name, query)}</span>
              </div>
              <div class="details-bottom-row">
                <span class="last-message-preview"><em class="start-prompt">Message this ${typeLabel} (@${u.username})</em></span>
              </div>
            </div>
          `;
          list.appendChild(item);
        });

        if (list.children.length > 0) {
          container.style.display = 'block';
        } else {
          container.style.display = 'none';
        }
      } else {
        container.style.display = 'none';
      }
    })
    .catch(err => {
      console.error('Error fetching search suggestions:', err);
    });
}

function initSearchFilter() {
  const searchField = document.querySelector('.search-field');
  const clearBtn = document.querySelector('.clear-search-btn');
  if (!searchField) return;

  searchField.addEventListener('input', () => {
    const query = searchField.value.trim();
    if (clearBtn) {
      clearBtn.style.display = query.length > 0 ? 'flex' : 'none';
    }
    applyFilters();

    clearTimeout(searchDebounceTimeout);
    searchDebounceTimeout = setTimeout(() => {
      performGlobalUserSearch(query);
    }, 250);
  });

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      searchField.value = '';
      clearBtn.style.display = 'none';
      applyFilters();
      performGlobalUserSearch('');
      searchField.focus();
    });
  }

  if (clearBtn) {
    clearBtn.style.display = searchField.value.trim().length > 0 ? 'flex' : 'none';
  }
  applyFilters();
}

function initInboxFeatures() {
  const sidebar = document.querySelector('.messages-sidebar');
  if (!sidebar || sidebar.dataset.inboxFeaturesInitialized === 'true') return;
  sidebar.dataset.inboxFeaturesInitialized = 'true';

  initSidebarTabs();
  initSearchFilter();
}

document.addEventListener('DOMContentLoaded', initInboxFeatures);
document.addEventListener('turbo:load', initInboxFeatures);
document.addEventListener('turbo:load', enableMessagesLayout);

if (document.readyState === 'complete' || document.readyState === 'interactive') {
  enableMessagesLayout();
  initInboxFeatures();
} else {
  document.addEventListener('DOMContentLoaded', enableMessagesLayout);
}

/* ── Active Conversation Handling & Composer ── */
function initMessageComposer() {
  if (document.body.dataset.messageComposerInitialized === 'true') return;
  const msgInput = document.getElementById('msgInput');
  const messageForm = document.getElementById('messageForm');
  if (!msgInput || !messageForm) return;

  document.body.dataset.messageComposerInitialized = 'true';

  /* ── Emoji Selection ── */
  const ALL_EMOJIS = ['😀','😃','😄','😁','😆','😅','🤣','😂','🙂','🙃','😉','😊','😇','🥰','😍','🤩','😘','😚','😋','😛','😜','🤪','😝','🤑','🤗','🤭','🤫','🤔','😐','😑','😶','😏','😒','🙄','😬','🤥','😌','😔','😪','🤤','😴','😷','🤒','🤕','🤢','🤮','🤧','🥵','🥶','🥴','😵','🤯','🤠','🥳','😎','🤓','🧐','😕','😟','🙁','☹️','😮','😯','😲','😳','🥺','😦','😧','😨','😰','😥','😢','😭','😱','😖','😣','😞','😓','😩','😫','🥱','😤','😡','😠','🤬','😈','👿','💀','💩','🤡','👻','👽','🤖','👋','🤚','🖐️','✋','🤝','🙌','👏','👍','👎','✊','💪','🙏','✍️','👌','🤌','✌️','🤞','🤟','🤘','👈','👉','👆','👇','☝️','👐','🤲','❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','💕','💞','💓','💗','💖','💘','💝','💯','💢','💥','💫','💦','💨','🎉','🎊','🎈','🎁','🏆','🥇','⭐','🌟','✨','🔥','💎','🚀','🌈','🎵','🎶','🎮','🏠','🌍','🌙','☀️','⛅','🌊','🌺','🌸','🌹','🍎','🍕','🍔','🎂','🐶','🐱','🐭','🐹','🐰','🦊','🐻','🐼','🐯','🦁','🐮','🐷','🐸','🐙'];

  function buildEmojiGrid(list) {
    const grid = document.getElementById('emojiGrid');
    if (!grid) return;
    grid.innerHTML = '';
    list.forEach(e => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'emoji-picker-btn';
      btn.textContent = e;
      btn.onclick = () => insertEmoji(e);
      grid.appendChild(btn);
    });
  }

  window.filterEmojis = function(q) {
    buildEmojiGrid(q ? ALL_EMOJIS.filter(e => e.includes(q)) : ALL_EMOJIS);
  };

  window.toggleEmojiPicker = function() {
    const p = document.getElementById('emojiPicker');
    if (!p) return;
    p.classList.toggle('open');
    if (p.classList.contains('open')) {
      buildEmojiGrid(ALL_EMOJIS);
      document.getElementById('emojiSearch').value = '';
      document.getElementById('emojiSearch').focus();
    }
  };

  document.addEventListener('click', e => {
    const wrap = document.getElementById('emojiWrap');
    if (wrap && !wrap.contains(e.target)) {
      const picker = document.getElementById('emojiPicker');
      if (picker) picker.classList.remove('open');
    }
  });

  function insertEmoji(emoji) {
    const ta = document.getElementById('msgInput');
    if (!ta) return;
    const s = ta.selectionStart, end = ta.selectionEnd;
    ta.value = ta.value.substring(0, s) + emoji + ta.value.substring(end);
    ta.selectionStart = ta.selectionEnd = s + emoji.length;
    ta.focus();
    updateSendBtn();
  }

  /* ── Textarea Auto-Resizing ── */
  msgInput.addEventListener('input', () => {
    msgInput.style.height = 'auto';
    msgInput.style.height = Math.min(msgInput.scrollHeight, 120) + 'px';
    updateSendBtn();
  });

  msgInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      messageForm.requestSubmit();
    }
  });

  /* ── Send Validation ── */
  const imgInput = document.getElementById('imageInput');
  const fileInput = document.getElementById('fileInput');

  if (imgInput) {
    imgInput.addEventListener('change', function() {
      if (this.files[0]) showAttachmentPreview('image', this.files[0]);
      updateSendBtn();
    });
  }

  if (fileInput) {
    fileInput.addEventListener('change', function() {
      if (this.files[0]) showAttachmentPreview('file', this.files[0]);
      updateSendBtn();
    });
  }

  /* ── AJAX Submission ── */
  messageForm.addEventListener('submit', function(e) {
    e.preventDefault();
    const form = this;
    const fd = new FormData(form);
    const btn = document.getElementById('sendBtn');
    if (btn) btn.disabled = true;

    fetch(form.action, {
      method: 'POST',
      body: fd,
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': fd.get('csrfmiddlewaretoken') }
    })
    .then(r => r.json())
    .then(data => {
      if (data.status === 'success') {
        appendMessage({
          isSent: true,
          content: data.content,
          imageUrl: data.image_url,
          fileUrl: data.file_url,
          fileName: data.file_name || (data.file_url ? data.file_url.split('/').pop() : null),
          time: data.created_at,
        });
        msgInput.value = '';
        msgInput.style.height = 'auto';
        form.reset();
        const strip = document.getElementById('attachmentPreviewStrip');
        if (strip) {
          strip.innerHTML = '';
          strip.style.display = 'none';
        }
      }
    })
    .catch(() => {})
    .finally(() => updateSendBtn());
  });
}

document.addEventListener('turbo:load', initMessageComposer);
document.addEventListener('DOMContentLoaded', initMessageComposer);

function updateSendBtn() {
  const ta = document.getElementById('msgInput');
  const img = document.getElementById('imageInput');
  const file = document.getElementById('fileInput');
  const send = document.getElementById('sendBtn');
  if (!ta || !send) return;

  const hasText = ta.value.trim().length > 0;
  const hasImage = img && img.files.length > 0;
  const hasFile = file && file.files.length > 0;
  send.disabled = !(hasText || hasImage || hasFile);
}

function showAttachmentPreview(type, file) {
  const strip = document.getElementById('attachmentPreviewStrip');
  if (!strip) return;
  strip.style.display = 'flex';
  const thumb = document.createElement('div');
  
  if (type === 'image') {
    thumb.className = 'preview-thumb-card';
    const img = document.createElement('img');
    img.src = URL.createObjectURL(file);
    const rm = document.createElement('button');
    rm.type = 'button';
    rm.className = 'preview-card-remove-btn';
    rm.textContent = '×';
    rm.onclick = () => {
      document.getElementById('imageInput').value = '';
      strip.removeChild(thumb);
      if (!strip.children.length) strip.style.display = 'none';
      updateSendBtn();
    };
    thumb.appendChild(img);
    thumb.appendChild(rm);
  } else {
    thumb.className = 'preview-file-card';
    thumb.innerHTML = `<span>📎</span><span style="font-size:.58rem;text-align:center;width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${file.name.slice(-10)}</span>`;
    const rm = document.createElement('button');
    rm.type = 'button';
    rm.className = 'preview-card-remove-btn';
    rm.textContent = '×';
    rm.onclick = () => {
      document.getElementById('fileInput').value = '';
      strip.removeChild(thumb);
      if (!strip.children.length) strip.style.display = 'none';
      updateSendBtn();
    };
    thumb.appendChild(rm);
  }
  strip.appendChild(thumb);
}

/* ── Lightbox Image Modal ── */
window.openImageModal = function(src) {
  const lb = document.getElementById('imgLightbox');
  const img = document.getElementById('imgLightboxImg');
  if (lb && img) {
    img.src = src;
    lb.style.display = 'flex';
  }
};

window.closeImageModal = function() {
  const lb = document.getElementById('imgLightbox');
  if (lb) lb.style.display = 'none';
};

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeImageModal();
});

/* ── Scroll Message Container ── */
function scrollToBottom(smooth = false) {
  const c = document.getElementById('messagesContainer');
  if (c) {
    c.scrollTo({ top: c.scrollHeight, behavior: smooth ? 'smooth' : 'instant' });
  }
}

/* ── Append Message ── */
function appendMessage({ isSent, content, imageUrl, fileUrl, fileName, time }) {
  const container = document.getElementById('messagesContainer');
  if (!container) return;
  
  const empty = container.querySelector('.chat-empty-box');
  if (empty) empty.remove();

  const row = document.createElement('div');
  row.className = `chat-msg-row ${isSent ? 'sent' : 'recv'}`;

  const wrap = document.createElement('div');
  wrap.className = 'chat-msg-bubble-wrap';

  const bubble = document.createElement('div');
  bubble.className = 'chat-msg-bubble';

  if (imageUrl) {
    const img = document.createElement('img');
    img.className = 'chat-msg-attachment-image';
    img.src = imageUrl;
    img.onclick = () => openImageModal(imageUrl);
    bubble.appendChild(img);
  }

  if (fileUrl) {
    const link = document.createElement('a');
    link.className = 'chat-msg-attachment-file';
    link.href = fileUrl;
    link.download = true;
    link.innerHTML = `<span class="attachment-file-icon">📎</span><span class="attachment-file-name">${fileName || 'File'}</span><svg class="attachment-download-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3"/></svg>`;
    bubble.appendChild(link);
  }

  if (content) {
    const txt = document.createElement('span');
    txt.textContent = content;
    bubble.appendChild(txt);
  }

  const ts = document.createElement('span');
  ts.className = 'chat-msg-time';
  ts.textContent = time || new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  bubble.appendChild(ts);

  wrap.appendChild(bubble);
  row.appendChild(wrap);

  const indicator = document.getElementById('typingIndicator');
  if (indicator && indicator.classList.contains('show')) {
    container.insertBefore(row, indicator);
  } else {
    container.appendChild(row);
  }
  
  scrollToBottom(true);
}

/* ── WebSocket Event Listener ── */
window.addEventListener('new_message', function(e) {
  const d = e.detail;
  const shell = document.querySelector('.messages-shell');
  const activeConvId = shell ? shell.dataset.conversationId : null;
  if (activeConvId && d.conversation_id == activeConvId) {
    appendMessage({ isSent: false, content: d.message, time: d.created_at || null });
  }
});
