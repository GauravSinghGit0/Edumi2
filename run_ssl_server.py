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

# ── Verify cert files exist ──────────────────────────────────────────
if not CERT_FILE.exists():
    print(f"[ERROR] Certificate not found: {CERT_FILE}")
    print("        Run: python scripts/generate_ssl_cert.py")
    sys.exit(1)
if not KEY_FILE.exists():
    print(f"[ERROR] Private key not found: {KEY_FILE}")
    sys.exit(1)

# ── Relative paths (forward slashes) to avoid Twisted endpoint colon conflicts ──
cert_rel = str(CERT_FILE.relative_to(BASE_DIR)).replace("\\", "/")
key_rel  = str(KEY_FILE.relative_to(BASE_DIR)).replace("\\", "/")

# Change working directory so relative paths resolve correctly
os.chdir(BASE_DIR)

# ── Build Twisted SSL endpoint string ────────────────────────────────
# Format: ssl:port=N:interface=ADDR:certKey=PATH:privateKey=PATH
ssl_endpoint = (
    f"ssl:port={PORT}:interface={BIND}"
    f":certKey={cert_rel}:privateKey={key_rel}"
)

# ── Create and run Daphne server ─────────────────────────────────────
# Import order matters: daphne.server installs the Twisted asyncio reactor
from daphne.server import Server  # noqa: E402  (must be before app import)

# Now import the ASGI application (Django + Channels)
from school_project.asgi import application  # noqa: E402

if __name__ == '__main__':
    print(f"Starting HTTPS/WSS on {BIND}:{PORT}")
    print(f"  Endpoint : {ssl_endpoint}")
    print(f"  Cert     : {CERT_FILE}")
    print(f"  Key      : {KEY_FILE}")
    print()

    server = Server(
        application=application,
        endpoints=[ssl_endpoint],
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
