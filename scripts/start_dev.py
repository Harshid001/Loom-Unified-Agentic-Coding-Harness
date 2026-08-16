#!/usr/bin/env python3
"""Loom Full-Stack Development Launcher.

Runs the FastAPI backend and Next.js dashboard concurrently with unified logging
and graceful termination.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"


def main() -> int:
    # Ensure env files exist
    env_file = REPO_ROOT / ".env"
    web_env_file = WEB_DIR / ".env.local"
    if not env_file.exists() or not web_env_file.exists():
        print("🔧 Running preflight environment configuration...")
        subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "configure_real_api.py")], check=True)

    print("🚀 Starting Loom Full-Stack Development Server...")
    print("   Backend API: http://127.0.0.1:8000")
    print("   Web Dashboard: http://localhost:3000")
    print("   Press Ctrl+C to terminate both servers.\n")

    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "loom.api.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--reload",
    ]

    is_windows = sys.platform == "win32"
    npm_cmd = "npm.cmd" if is_windows else "npm"
    frontend_cmd = [npm_cmd, "run", "dev"]

    backend_proc = subprocess.Popen(backend_cmd, cwd=str(REPO_ROOT))
    time.sleep(1.5)
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=str(WEB_DIR))

    def handle_sigint(signum, frame):
        print("\n🛑 Shutting down Loom servers...")
        try:
            backend_proc.terminate()
            frontend_proc.terminate()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    try:
        while True:
            time.sleep(0.5)
            if backend_proc.poll() is not None:
                print("❌ Backend server exited unexpectedly.")
                frontend_proc.terminate()
                return backend_proc.returncode or 1
            if frontend_proc.poll() is not None:
                print("❌ Frontend server exited unexpectedly.")
                backend_proc.terminate()
                return frontend_proc.returncode or 1
    except KeyboardInterrupt:
        handle_sigint(None, None)

    return 0


if __name__ == "__main__":
    sys.exit(main())
