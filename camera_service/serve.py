"""
Camera Service ASGI/SSL entry point using Daphne.
"""
import os
import sys
from pathlib import Path

# Add project root and camera_service directory to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parent))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'camera_service.settings')

import django
django.setup()

from daphne.server import Server
from camera_service.asgi import application

if __name__ == '__main__':
    port = int(os.environ.get('CAMERA_SERVICE_PORT', 8003))
    bind = "0.0.0.0"
    
    use_ssl = os.environ.get('CAMERA_SERVICE_SSL', 'false').lower() == 'true'
    
    cert_file = BASE_DIR.parent / "certs" / "edumi.crt"
    key_file  = BASE_DIR.parent / "certs" / "edumi.key"
    
    if use_ssl and cert_file.exists() and key_file.exists():
        cert_rel = str(cert_file.relative_to(BASE_DIR.parent)).replace("\\", "/")
        key_rel  = str(key_file.relative_to(BASE_DIR.parent)).replace("\\", "/")
        os.chdir(str(BASE_DIR.parent))
        
        endpoint = f"ssl:port={port}:interface={bind}:certKey={cert_rel}:privateKey={key_rel}"
        print(f"Camera Service starting on HTTPS/WSS 0.0.0.0:{port} (daphne, SSL enabled)")
    else:
        endpoint = f"tcp:port={port}:interface={bind}"
        print(f"Camera Service starting on http://0.0.0.0:{port} (daphne, HTTP)")

    server = Server(
        application=application,
        endpoints=[endpoint],
        signal_handlers=True,
        http_timeout=86400,
        websocket_timeout=86400,
        verbosity=0,
    )
    server.run()
