"""Optional built React assets with private-route and path traversal guards."""

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse


def install_static(app, static_dir):
    root = Path(static_dir).resolve()

    @app.get("/{asset:path}")
    def static(asset: str):
        if asset == "api" or asset.startswith(("api/", "download/")):
            raise HTTPException(404, "Маршрут не найден.")
        target = (root / asset).resolve()
        if not target.is_relative_to(root):
            raise HTTPException(404, "Файл не найден.")
        if not target.is_file():
            target = root / "index.html"
        if not target.is_file():
            raise HTTPException(404, "Интерфейс ещё не собран.")
        return FileResponse(target)
