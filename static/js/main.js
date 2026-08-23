// Main JavaScript - Common functionality

// Confirm delete actions
function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this?');
}

// Show/hide elements
function toggleElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.style.display = element.style.display === 'none' ? 'block' : 'none';
    }
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

// Format time
function formatTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        alert('Copied to clipboard!');
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

// Show notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#6366f1'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1);
        z-index: 9999;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add CSS animations only if not already added
if (!document.getElementById('edumi-notification-styles')) {
    const style = document.createElement('style');
    style.id = 'edumi-notification-styles';
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        
        @keyframes slideOut {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(100%);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
}

// Auto-dismiss Django alerts system-wide
function initAlertDismissal() {
    const alerts = document.querySelectorAll('.messages-container .alert');
    alerts.forEach(alert => {
        if (alert.dataset.dismissed) return;
        alert.dataset.dismissed = "true";

        setTimeout(() => {
            alert.style.transition = 'opacity 0.6s cubic-bezier(0.4, 0, 0.2, 1), transform 0.6s cubic-bezier(0.4, 0, 0.2, 1), max-height 0.6s cubic-bezier(0.4, 0, 0.2, 1), padding 0.6s cubic-bezier(0.4, 0, 0.2, 1), margin 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-12px)';
            alert.style.maxHeight = '0';
            alert.style.paddingTop = '0';
            alert.style.paddingBottom = '0';
            alert.style.marginTop = '0';
            alert.style.marginBottom = '0';
            alert.style.overflow = 'hidden';
            alert.style.border = 'none';
            setTimeout(() => {
                alert.remove();
            }, 600);
        }, 6000); // Dismiss after 6 seconds as requested
    });
}

// Register event listeners for both classic load and Turbo framework loads
document.addEventListener('DOMContentLoaded', initAlertDismissal);
if (typeof document.addEventListener === 'function') {
    document.addEventListener('turbo:load', initAlertDismissal);
}

// Global Hotwired Turbo resets to prevent scrolling lock-ups, lingering backdrops, and state leaks
function globalTurboReset() {
    document.body.style.overflow = '';
    document.body.classList.remove('modal-open');
    document.body.classList.remove('messages-layout-active');
    
    // Clean up any bootstrap modal backdrops that may linger after navigation
    const backdrops = document.querySelectorAll('.modal-backdrop');
    backdrops.forEach(backdrop => backdrop.remove());
}

if (typeof document.addEventListener === 'function') {
    document.addEventListener('turbo:before-visit', globalTurboReset);
    document.addEventListener('turbo:before-cache', globalTurboReset);
    document.addEventListener('turbo:load', globalTurboReset);
}

