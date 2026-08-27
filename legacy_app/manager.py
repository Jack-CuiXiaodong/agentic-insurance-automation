"""Start / health-check the legacy Flask app as a background process.

Lets the UI (and tests) spin up the legacy claim system on demand so the RPA /
recovery demo works from a single ``streamlit run`` with no extra terminal.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import requests

from config import settings

_PROC: subprocess.Popen | None = None


def is_running(base_url: str | None = None, timeout: float = 1.0) -> bool:
    base_url = base_url or settings.legacy_base_url
    try:
        r = requests.get(f"{base_url}/health", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def ensure_running(wait_seconds: float = 10.0) -> bool:
    """Ensure the legacy app is reachable; start it if necessary."""
    global _PROC
    if is_running():
        return True

    app_path = os.path.join(os.path.dirname(__file__), "app.py")
    _PROC = subprocess.Popen(
        [sys.executable, app_path, "--host", settings.legacy_host,
         "--port", str(settings.legacy_port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if is_running():
            return True
        time.sleep(0.3)
    return is_running()


def stop() -> None:  # pragma: no cover - convenience
    global _PROC
    if _PROC is not None:
        _PROC.terminate()
        _PROC = None
