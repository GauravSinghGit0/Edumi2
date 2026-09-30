/**
 * Edumi Enterprise Telemetry & Clickstream Tracker
 * Inspired by Google Analytics, Meta Pixel, and Instagram client event pipelines.
 * Non-blocking, privacy-conscious, batched event streaming.
 */
(function(window, document) {
    'use strict';

    // Singleton check
    if (window.EdumiTelemetry) {
        return;
    }

    const TELEMETRY_ENDPOINT = '/api/telemetry/events/';
    const BATCH_INTERVAL_MS = 5000;
    const MAX_QUEUE_SIZE = 10;

    // Helper: generate UUID v4
    function generateUUID() {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    // Helper: get cookie for CSRF token
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

    // Helper: build CSS path of element
    function getElementCssPath(el) {
        if (!(el instanceof Element)) return '';
        const path = [];
        let current = el;
        while (current && current.nodeType === Node.ELEMENT_NODE && path.length < 5) {
            let selector = current.nodeName.toLowerCase();
            if (current.id) {
                selector += '#' + current.id;
                path.unshift(selector);
                break;
            } else {
                let sibling = current;
                let nth = 1;
                while (sibling = sibling.previousElementSibling) {
                    if (sibling.nodeName.toLowerCase() === selector) nth++;
                }
                if (nth > 1) selector += ':nth-of-type(' + nth + ')';
            }
            path.unshift(selector);
            current = current.parentElement;
        }
        return path.join(' > ');
    }

    // Initialize or load session / device IDs
    let deviceId = '';
    try {
        deviceId = localStorage.getItem('_edumi_did');
        if (!deviceId) {
            deviceId = generateUUID();
            localStorage.setItem('_edumi_did', deviceId);
        }
    } catch (e) {
        deviceId = generateUUID();
    }

    let sessionId = '';
    try {
        sessionId = sessionStorage.getItem('_edumi_sid');
        if (!sessionId) {
            sessionId = generateUUID();
            sessionStorage.setItem('_edumi_sid', sessionId);
        }
    } catch (e) {
        sessionId = generateUUID();
    }

    const pageStartTime = Date.now();
    let eventQueue = [];
    let flushTimer = null;

    // Core dispatcher
    function flush(isSync) {
        if (eventQueue.length === 0) return;

        const eventsToSend = eventQueue.slice();
        eventQueue = [];

        const payload = {
            device_id: deviceId,
            session_id: sessionId,
            sent_at: new Date().toISOString(),
            events: eventsToSend
        };

        const jsonStr = JSON.stringify(payload);
        const csrfToken = getCookie('csrftoken') || '';

        // Use Beacon on page unload or sync mode if available
        if (isSync && navigator.sendBeacon) {
            try {
                const blob = new Blob([jsonStr], { type: 'application/json' });
                const success = navigator.sendBeacon(TELEMETRY_ENDPOINT, blob);
                if (success) return;
            } catch (e) {}
        }

        // Standard fetch fallback with keepalive
        try {
            fetch(TELEMETRY_ENDPOINT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: jsonStr,
                keepalive: true
            }).catch(function() {
                // Failsafe: silently ignore network errors so user never notices
            });
        } catch (e) {}
    }

    // Schedule flush timer
    function scheduleFlush() {
        if (!flushTimer) {
            flushTimer = setInterval(function() {
                flush(false);
            }, BATCH_INTERVAL_MS);
        }
    }

    // Push event into queue
    function pushEvent(evt) {
        try {
            if (!evt.timestamp) {
                evt.timestamp = new Date().toISOString();
            }
            if (!evt.url) {
                evt.url = window.location.href;
            }
            if (!evt.title) {
                evt.title = document.title;
            }

            eventQueue.push(evt);

            if (eventQueue.length >= MAX_QUEUE_SIZE) {
                flush(false);
            }
        } catch (e) {}
    }

    // 1. Capture Page View
    function trackPageView() {
        const viewport = {
            width: window.innerWidth,
            height: window.innerHeight,
            screen_width: window.screen ? window.screen.width : 0,
            screen_height: window.screen ? window.screen.height : 0,
            dpr: window.devicePixelRatio || 1
        };

        pushEvent({
            type: 'page_view',
            name: 'view_page',
            url: window.location.href,
            title: document.title,
            viewport: viewport,
            metadata: {
                referrer: document.referrer || '',
                theme: localStorage.getItem('theme') || 'light',
                language: navigator.language || ''
            }
        });
    }

    // 2. Capture Clickstream (Instagram & Google style)
    function initClickTracking() {
        document.addEventListener('click', function(e) {
            try {
                const target = e.target;
                if (!target || target.nodeType !== Node.ELEMENT_NODE) return;

                // Find clickable ancestor or the element itself
                const clickable = target.closest('button, a, input, select, textarea, [role="button"], [data-action], .btn, .card, .nav-link, .dropdown-item') || target;

                // Extract text label cleanly
                let text = '';
                if (clickable.innerText) {
                    text = clickable.innerText.trim().replace(/\s+/g, ' ').substring(0, 80);
                } else if (clickable.value) {
                    text = String(clickable.value).substring(0, 80);
                } else if (clickable.getAttribute('aria-label')) {
                    text = clickable.getAttribute('aria-label').substring(0, 80);
                } else if (clickable.getAttribute('title')) {
                    text = clickable.getAttribute('title').substring(0, 80);
                }

                // Element identifier
                let tag = clickable.tagName.toLowerCase();
                let identifier = tag;
                if (clickable.id) {
                    identifier += '#' + clickable.id;
                } else if (clickable.className && typeof clickable.className === 'string') {
                    const firstClass = clickable.className.trim().split(/\s+/)[0];
                    if (firstClass) identifier += '.' + firstClass;
                }

                // Attributes
                const meta = {
                    href: clickable.getAttribute('href') || undefined,
                    action: clickable.getAttribute('data-action') || undefined,
                    id: clickable.id || undefined,
                    class: clickable.className || undefined,
                    css_path: getElementCssPath(clickable)
                };

                pushEvent({
                    type: 'click',
                    name: 'element_click',
                    target: identifier,
                    text: text,
                    coordinates: {
                        x: Math.round(e.clientX),
                        y: Math.round(e.clientY),
                        page_x: Math.round(e.pageX),
                        page_y: Math.round(e.pageY)
                    },
                    metadata: meta
                });
            } catch (err) {}
        }, true);
    }

    // 3. Capture Form Submissions (safe - no passwords)
    function initFormTracking() {
        document.addEventListener('submit', function(e) {
            try {
                const form = e.target;
                if (!form || form.tagName !== 'FORM') return;

                const formId = form.id || form.getAttribute('name') || 'form';
                const action = form.getAttribute('action') || window.location.pathname;

                pushEvent({
                    type: 'form_submit',
                    name: 'form_submitted',
                    target: 'form#' + formId,
                    metadata: {
                        action: action,
                        method: (form.method || 'GET').toUpperCase()
                    }
                });
            } catch (err) {}
        }, true);
    }

    // 4. Track Page Leave / Visibility change for active time tracking
    function initVisibilityTracking() {
        function handleExit() {
            const timeSpent = Date.now() - pageStartTime;
            pushEvent({
                type: 'page_exit',
                name: 'session_leave',
                time_on_page: timeSpent,
                metadata: {
                    active_duration_sec: Math.round(timeSpent / 1000)
                }
            });
            flush(true);
        }

        window.addEventListener('beforeunload', handleExit);
        window.addEventListener('pagehide', handleExit);

        document.addEventListener('visibilitychange', function() {
            if (document.visibilityState === 'hidden') {
                handleExit();
            } else if (document.visibilityState === 'visible') {
                pushEvent({
                    type: 'page_focus',
                    name: 'tab_returned'
                });
            }
        });
    }

    // Public API
    window.EdumiTelemetry = {
        track: function(eventName, customData) {
            pushEvent({
                type: 'custom',
                name: eventName,
                metadata: customData || {}
            });
        },
        trackAction: function(actionName, details) {
            pushEvent({
                type: 'user_action',
                name: actionName,
                metadata: details || {}
            });
        },
        flush: function() {
            flush(false);
        },
        getSessionId: function() {
            return sessionId;
        },
        getDeviceId: function() {
            return deviceId;
        }
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            trackPageView();
            initClickTracking();
            initFormTracking();
            initVisibilityTracking();
            scheduleFlush();
        });
    } else {
        trackPageView();
        initClickTracking();
        initFormTracking();
        initVisibilityTracking();
        scheduleFlush();
    }

})(window, document);
