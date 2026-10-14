"""Compatible app factory for the local same-origin React workspace."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .http.routers import admin, auth, downloads, research, validation
from .http.runtime import Runtime
from .http.security import COOKIE as COOKIE
from .http.security import Security, install_security
from .http.static import install_static
from .settings import auth_mode, storage_path


def create_app(path=None, mode=None, static_dir=None) -> FastAPI:
    mode = auth_mode() if mode is None else mode
    if mode not in {"local", "demo"}:
        raise ValueError("Режим доступа: local или demo.")
    if path is None:
        path = storage_path()
        if not os.getenv("DVOINIK_STORAGE_PATH"):
            path = path.with_name("demo.sqlite3" if mode == "demo" else "experiments.sqlite3")
    runtime = Runtime(path, mode)
    security = Security(runtime)

    @asynccontextmanager
    async def lifespan(app):
        yield
        runtime.jobs.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime, app.state.security = runtime, security
    app.state.auth, app.state.jobs = runtime.auth, runtime.jobs
    install_security(app, security)
    for router in (auth.router, research.router, validation.router, downloads.router, admin.router):
        app.include_router(router)
    if static_dir is not None:
        install_static(app, static_dir)
    return app
