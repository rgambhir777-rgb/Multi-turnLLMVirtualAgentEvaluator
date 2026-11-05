"""Start AgentProof: one process serving the API and the web UI on http://localhost:8000.

Environment:
    AGENTPROOF_HOST        bind address (default 127.0.0.1)
    AGENTPROOF_PORT        port (default 8000)
    AGENTPROOF_NO_BROWSER  set to 1 to skip opening the browser
"""
from __future__ import annotations

import builtins
import functools
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _open_browser_when_ready(url: str) -> None:
    """Poll the status endpoint and open the browser once the app (and first-run seed) is up."""
    deadline = time.time() + 180
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/status", timeout=2):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.7)


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _agentproof_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2) as resp:
            return b"effective_judge" in resp.read()
    except OSError:
        return False


def main() -> None:
    import uvicorn

    from backend.config import env

    host = env("AGENTPROOF_HOST", "127.0.0.1")
    port = int(env("AGENTPROOF_PORT", "8000"))
    open_browser = env("AGENTPROOF_NO_BROWSER", "0").lower() not in {"1", "true", "yes"}
    print = functools.partial(builtins.print, flush=True)  # show progress even when output is piped
    if not _port_free(host, port):
        if _agentproof_running(port):
            print(f"\n  AgentProof is already running at http://localhost:{port}")
            if open_browser:
                webbrowser.open(f"http://localhost:{port}")
            return
        requested = port
        port = next((p for p in range(port + 1, port + 50) if _port_free(host, p)), 0)
        if not port:
            sys.exit(f"Port {requested} is in use and no free port was found nearby. Set AGENTPROOF_PORT in .env.")
        print(f"\n  Port {requested} is used by another program - using port {port} instead.")
    os.environ["AGENTPROOF_PORT"] = str(port)  # the demo HTTP agent resolves its URL from this
    url = f"http://localhost:{port}"
    print(f"\n  AgentProof is starting on {url}")
    print("  First launch seeds the Northwind demo (takes ~15 seconds). Press Ctrl+C to stop.\n")
    if open_browser:
        threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()

    from backend.main import app

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
