"""Локальный React/FastAPI сервис; --ui streamlit запускает прежний интерфейс."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading

from dvoinik.auth import AuthStore
from dvoinik.downloads import create_download_server
from dvoinik.settings import ROOT, auth_mode, storage_path


def legacy_main():
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui", choices=["react", "streamlit"], default="react")
    args = parser.parse_args(argv)
    if args.ui == "streamlit":
        return legacy_main()
    static = ROOT / "frontend" / "dist"
    if not (static / "index.html").is_file():
        print(
            "Интерфейс ещё не собран. Выполните npm ci --prefix frontend и npm run build --prefix frontend.",
            file=sys.stderr,
        )
        return 1
    import uvicorn

    from dvoinik.api import create_app

    port = int(os.getenv("DVOINIK_PORT", "8501"))
    print(f"Двойник: http://127.0.0.1:{port}/", flush=True)
    # В контейнере слушаем все интерфейсы контейнера: DVOINIK_HOST=0.0.0.0. Локально — только 127.0.0.1.
    host = os.getenv("DVOINIK_HOST", "127.0.0.1")
    uvicorn.run(create_app(static_dir=static), host=host, port=port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
