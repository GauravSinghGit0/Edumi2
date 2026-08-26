/* static/js/classroom-card.js - Interactive features for Google Classroom Cards */

// Copy class code to clipboard with toast notification
function copyClassCode(code, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    if (!code) return;

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(code).then(() => {
            showClassroomToast(`Class code "${code}" copied to clipboard!`);
        }).catch(() => {
            fallbackCopy(code);
        });
    } else {
        fallbackCopy(code);
    }

    // Close any open dropdown menus
    closeAllGClassMenus();
}

function fallbackCopy(text) {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    textArea.style.top = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
        document.execCommand('copy');
        showClassroomToast(`Class code "${text}" copied to clipboard!`);
    } catch (err) {
        console.error('Fallback copy failed', err);
    }
    document.body.removeChild(textArea);
}

// Show a temporary floating toast
function showClassroomToast(message) {
    let toast = document.getElementById('gclass-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'gclass-toast';
        toast.className = 'gclass-toast';
        document.body.appendChild(toast);
    }
    toast.innerHTML = `<i data-lucide="check-circle" style="width: 18px; height: 18px; color: #10b981;"></i> <span>${message}</span>`;
    if (window.lucide) {
        window.lucide.createIcons({ root: toast });
    }
    toast.classList.add('show');
    clearTimeout(window.__gclassToastTimer);
    window.__gclassToastTimer = setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Toggle 3-dots dropdown menu
function toggleGClassMenu(btn, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const wrap = btn.closest('.gclass-dropdown-wrap');
    if (!wrap) return;
    const menu = wrap.querySelector('.gclass-dropdown-menu');
    if (!menu) return;

    const isOpen = menu.classList.contains('active');
    closeAllGClassMenus();

    if (!isOpen) {
        menu.classList.add('active');
    }
}

function closeAllGClassMenus() {
    document.querySelectorAll('.gclass-dropdown-menu.active').forEach(menu => {
        menu.classList.remove('active');
    });
}

// Auto close dropdown when clicking outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('.gclass-dropdown-wrap')) {
        closeAllGClassMenus();
    }
});

// Auto re-render Lucide icons on Turbo page render
document.addEventListener('turbo:load', () => {
    if (window.lucide) {
        window.lucide.createIcons();
    }
});
