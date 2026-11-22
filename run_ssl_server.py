#!/usr/bin/env python
"""
Runner shim redirecting to scripts/run_ssl_server.py.
"""
import runpy
from pathlib import Path

script_path = Path(__file__).resolve().parent / "scripts" / "run_ssl_server.py"
runpy.run_path(str(script_path), run_name="__main__")
