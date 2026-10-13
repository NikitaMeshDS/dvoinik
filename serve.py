"""Запуск интерфейса и закрытой выдачи отчётов: python serve.py."""

from __future__ import annotations

import os
import subprocess
import sys
import threading

from dvoinik.auth import AuthStore
from dvoinik.downloads import create_download_server
from dvoinik.settings import ROOT, auth_mode, storage_path


def main():
    path = storage_path()
    mode = auth_mode()
    auth = AuthStore(path, allow_demo=mode == "demo")
    server = create_download_server(auth)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    env = {
        **os.environ,
        "DVOINIK_STORAGE_PATH": str(path),
        "DVOINIK_DOWNLOAD_ORIGIN": f"http://127.0.0.1:{server.server_port}",
    }
    process = None
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ROOT / "app.py"),
                "--server.address",
                "127.0.0.1",
                "--server.port",
                os.getenv("DVOINIK_PORT", "8501"),
            ],
            env=env,
            cwd=ROOT,
        )
        return process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
