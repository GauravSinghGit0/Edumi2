"""
run_ssl_server.py — Launch Daphne (ASGI) with SSL/TLS.

Daphne's CLI has no --ssl flags, but its Server class accepts Twisted
endpoint strings via the `endpoints` parameter. We pass an ssl: endpoint
with relative paths to avoid Windows drive-letter colon conflicts.

Usage:  python run_ssl_server.py
  OR:   venv/bin/python run_ssl_server.py
"""

import os
import sys
from pathlib import Path

BASE_DIR  = Path(__file__).resolve().parent
CERT_FILE = BASE_DIR / "certs" / "edumi.crt"
KEY_FILE  = BASE_DIR / "certs" / "edumi.key"
PORT      = int(os.environ.get("PORT", "8002"))
BIND      = "0.0.0.0"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school_project.settings")

# ── Build Twisted endpoint string ────────────────────────────────
USE_SSL = os.environ.get("USE_SSL", "False").lower() in ["true", "1", "yes"]

if USE_SSL:
    # Verify cert files exist
    if not CERT_FILE.exists() or not KEY_FILE.exists():
        print(f"[INFO] SSL Certificate not found at {CERT_FILE}. Auto-generating self-signed certificates...")
        try:
            from scripts import generate_ssl_cert
            generate_ssl_cert.main()
        except Exception as e:
            print(f"[ERROR] Failed to auto-generate SSL certificate: {e}")
            sys.exit(1)

    cert_rel = str(CERT_FILE.relative_to(BASE_DIR)).replace("\\", "/")
    key_rel  = str(KEY_FILE.relative_to(BASE_DIR)).replace("\\", "/")
    endpoint = f"ssl:port={PORT}:interface={BIND}:certKey={cert_rel}:privateKey={key_rel}"
    server_proto = "HTTPS/WSS"
else:
    endpoint = f"tcp:port={PORT}:interface={BIND}"
    server_proto = "HTTP/WS"

# Change working directory so relative paths resolve correctly
os.chdir(BASE_DIR)

# ── Create and run Daphne server ─────────────────────────────────────
# Import order matters: daphne.server installs the Twisted asyncio reactor
from daphne.server import Server  # noqa: E402  (must be before app import)

# Now import the ASGI application (Django + Channels)
from school_project.asgi import application  # noqa: E402

import socket
import subprocess

_lk_process_handles = []

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def ensure_livekit_running():
    # Check if port 7880 is already listening
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(('127.0.0.1', 7880))
    sock.close()
    if result == 0:
        print("[INFO] LiveKit SFU server is already running on port 7880.")
        return

    lk_exe = BASE_DIR / "livekit-bin" / "livekit-server.exe"
    config_path = BASE_DIR / "config" / "livekit.yaml"

    if lk_exe.exists() and config_path.exists():
        lan_ip = get_lan_ip()
        print(f"[INFO] Auto-starting LiveKit SFU server on port 7880 (Dynamic Node IP: {lan_ip})...")
        try:
            log_dir = BASE_DIR / "logs"
            log_dir.mkdir(exist_ok=True)
            out_file = open(log_dir / "livekit.stdout.log", "a", encoding="utf-8")
            err_file = open(log_dir / "livekit.stderr.log", "a", encoding="utf-8")
            global _lk_process_handles
            _lk_process_handles = [out_file, err_file]

            creation_flag = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
            cmd = [str(lk_exe), "--config", str(config_path)]
            if lan_ip and lan_ip != '127.0.0.1':
                cmd.extend(["--node-ip", lan_ip])

            proc = subprocess.Popen(
                cmd,
                stdout=out_file,
                stderr=err_file,
                creationflags=creation_flag
            )
            _lk_process_handles.append(proc)
            print("[SUCCESS] LiveKit SFU server launched in background on port 7880.")
        except Exception as e:
            print(f"[WARN] Failed to auto-start LiveKit server: {e}")
    else:
        print(f"[WARN] LiveKit server binary or config not found at {lk_exe}.")

if __name__ == '__main__':
    ensure_livekit_running()
    print(f"Starting {server_proto} on http://{BIND}:{PORT}")
    print(f"  Endpoint : {endpoint}")
    print()

    server = Server(
        application=application,
        endpoints=[endpoint],
        signal_handlers=True,
        http_timeout=86400,  # 24 hours for long streaming
        websocket_timeout=86400,
        websocket_connect_timeout=20,
        ping_interval=20,
        ping_timeout=30,
        application_close_timeout=86400,
        root_path="",
        verbosity=0,  # Only warnings/errors
    )

    server.run()
