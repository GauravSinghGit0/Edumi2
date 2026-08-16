"""
Inline HTML for the architecture visualization page.
Extracted from the original accounts/views.py architecture_view function.
"""

ARCHITECTURE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>System Architecture - EduMi</title>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); font-family: Arial, sans-serif; padding: 20px; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .header h1 { color: white; font-size: 2.5em; margin-bottom: 5px; }
        .header p { color: rgba(255,255,255,0.9); font-size: 1.1em; }
        .back-btn { position: fixed; top: 20px; left: 20px; background: rgba(255,255,255,0.2); backdrop-filter: blur(10px); color: white; padding: 10px 20px; text-decoration: none; border-radius: 25px; z-index: 1000; transition: all 0.3s; box-shadow: 0 2px 10px rgba(0,0,0,0.3); }
        .back-btn:hover { background: rgba(255,255,255,0.3); transform: translateX(-5px); }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; justify-content: center; }
        .tab-btn { background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); color: white; border: 2px solid rgba(255,255,255,0.2); padding: 15px 30px; border-radius: 10px; cursor: pointer; font-size: 1.1em; transition: all 0.3s; }
        .tab-btn:hover { background: rgba(255,255,255,0.2); transform: translateY(-2px); }
        .tab-btn.active { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-color: #667eea; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .legend { position: fixed; bottom: 20px; right: 20px; background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); padding: 15px; border-radius: 10px; z-index: 1000; box-shadow: 0 4px 6px rgba(0,0,0,0.3); max-width: 300px; }
        .legend h3 { color: white; margin-bottom: 10px; font-size: 1.1em; }
        .legend-item { display: flex; align-items: center; margin: 8px 0; color: white; font-size: 0.9em; }
        .legend-dot { width: 12px; height: 12px; border-radius: 50%; margin-right: 10px; box-shadow: 0 0 10px currentColor; }
        .container { max-width: 1850px; margin: 0 auto; background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); padding: 20px; border-radius: 10px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }
        .svg-wrapper { background: white; border-radius: 10px; padding: 10px; overflow: auto; max-height: 85vh; }
        svg { max-width: 100%; height: auto; display: block; }
        object { width: 100%; min-height: 2600px; }
        .info-box { background: rgba(52,152,219,0.2); border-left: 4px solid #3498db; padding: 15px; margin: 20px 0; border-radius: 5px; color: white; }
        .info-box h3 { margin-bottom: 10px; color: #3498db; }
    </style>
</head>
<body>
    <a href="/admin-panel/" class="back-btn">\u2190 Back to Admin Panel</a>
    <div class="header">
        <h1>\U0001f3d7\ufe0f EduMi Platform - System Architecture</h1>
        <p>Complete Backend Architecture Visualization</p>
    </div>
    <div class="tabs">
        <button class="tab-btn active" onclick="showTab('full')">\U0001f310 Full System Architecture</button>
        <button class="tab-btn" onclick="showTab('backend')">\u2699\ufe0f Django Backend Flow</button>
    </div>
    <div id="legend-full" class="legend">
        <h3>\U0001f3af Live Data Flow</h3>
        <div class="legend-item"><div class="legend-dot" style="background:#3498db;"></div><span>HTTP Request/Response</span></div>
        <div class="legend-item"><div class="legend-dot" style="background:#e74c3c;"></div><span>Video Stream (RTSP/MJPEG)</span></div>
        <div class="legend-item"><div class="legend-dot" style="background:#2ecc71;"></div><span>Database Query/Response</span></div>
        <div class="legend-item"><div class="legend-dot" style="background:#9b59b6;"></div><span>WebSocket Message</span></div>
        <div class="legend-item"><div class="legend-dot" style="background:#f39c12;"></div><span>WebRTC P2P (Direct)</span></div>
    </div>
    <div id="legend-backend" class="legend" style="display:none;">
        <h3>\U0001f4cb Request Flow</h3>
        <div class="legend-item"><div class="legend-dot" style="background:#3498db;"></div><span>HTTP Request</span></div>
        <div class="legend-item"><div class="legend-dot" style="background:#e74c3c;"></div><span>Middleware Processing</span></div>
        <div class="legend-item"><div class="legend-dot" style="background:#f39c12;"></div><span>URL Routing</span></div>
        <div class="legend-item"><div class="legend-dot" style="background:#2ecc71;"></div><span>View &amp; ORM</span></div>
        <div class="legend-item"><div class="legend-dot" style="background:#9b59b6;"></div><span>Models &amp; Database</span></div>
    </div>
    <div class="container">
        <div id="tab-full" class="tab-content active">
            <div class="info-box">
                <h3>\U0001f4e1 Watch the packets flow in real-time!</h3>
                <p>Blue circles = HTTP &bull; Red = Video streams &bull; Green = DB queries &bull; Purple = WebSocket &bull; Orange = WebRTC P2P</p>
            </div>
            <div class="svg-wrapper">
                <object data="/static/architecture_diagram.svg" type="image/svg+xml" style="width:100%;height:auto;">
                    <img src="/static/architecture_diagram.svg" alt="System Architecture Diagram">
                </object>
            </div>
        </div>
        <div id="tab-backend" class="tab-content">
            <div class="info-box">
                <h3>\u2699\ufe0f Django Backend Request-Response Cycle</h3>
                <p>Middleware \u2192 URL routing \u2192 Views \u2192 ORM \u2192 Models &amp; DB \u2192 Template rendering</p>
            </div>
            <div class="svg-wrapper">
                <object data="/static/backend_architecture.svg" type="image/svg+xml" style="width:100%;height:auto;">
                    <img src="/static/backend_architecture.svg" alt="Backend Architecture Diagram">
                </object>
            </div>
        </div>
    </div>
    <script>
        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-' + tabName).classList.add('active');
            event.target.classList.add('active');
            document.getElementById('legend-full').style.display = tabName === 'full' ? 'block' : 'none';
            document.getElementById('legend-backend').style.display = tabName === 'backend' ? 'block' : 'none';
        }
    </script>
</body>
</html>
"""
