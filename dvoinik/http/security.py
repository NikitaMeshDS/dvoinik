"""Same-origin/session access and uniform HTTP failures."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from dataclasses import asdict
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..auth import AccessExpired, AuthError
from ..jobs import JobBusy, JobMissing
from ..settings import model_identity
from ..storage import StorageConflict, StorageError
from .runtime import Runtime

COOKIE = "dvoinik_session"


class Security:
    """A session binding secret belongs to this app, never to the process."""

    def __init__(self, runtime: Runtime):
        self.runtime = runtime
        self.csrf_secret = secrets.token_bytes(32)

    def csrf(self, token):
        return hmac.new(self.csrf_secret, token.encode(), hashlib.sha256).hexdigest()

    def identity(self, request: Request):
        token = request.cookies.get(COOKIE, "")
        # Polling never prolongs inactivity; all other authenticated interaction does.
        poll = request.method == "GET" and re.fullmatch(r"/api/runs/[^/]+", request.url.path)
        user = self.runtime.auth.resolve(token)
        supplied = request.headers.get("x-csrf-token", "")
        if request.method in {"GET", "HEAD"} and supplied:
            if not supplied.isascii() or not hmac.compare_digest(supplied, self.csrf(token)):
                raise HTTPException(401, "Сессия в браузере изменена. Обновите страницу.")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            supplied = request.headers.get("x-csrf-token", "")
            if not supplied.isascii() or not hmac.compare_digest(supplied, self.csrf(token)):
                raise HTTPException(403, "Защита запроса устарела. Обновите страницу.")
        if not poll:
            user = self.runtime.auth.resolve(token, touch=True)
        request.state.session_token = token
        return token, user

    def session_data(self, token):
        user = self.runtime.auth.resolve(token)
        return {
            "user": asdict(user),
            "csrf_token": self.csrf(token),
            "mode": self.runtime.mode,
            "default_mock": self.runtime.mode == "demo" or os.getenv("DVOINIK_MOCK", "1") == "1",
            "model": model_identity(self.runtime.mode == "demo")[0],
        }

    def set_cookie(self, response, token):
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")


def access_failure(exc):
    status = 503 if str(exc).startswith("Хранилище доступа недоступно") else 401
    payload = {"detail": str(exc)}
    if status == 503:
        payload["code"] = "access_unavailable"
    return JSONResponse(payload, status_code=status)


def get_security(request: Request) -> Security:
    return request.app.state.security


def identity(request: Request):
    return get_security(request).identity(request)


def install_security(app, security: Security):
    @app.middleware("http")
    async def origin_boundary(request, call_next):
        parsed = urlsplit(str(request.url))
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            return JSONResponse({"detail": "Сервис доступен только через локальный адрес."}, status_code=403)
        if request.url.path.startswith("/api"):
            origin = request.headers.get("origin")
            if origin and origin != f"{parsed.scheme}://{parsed.netloc}":
                return JSONResponse({"detail": "Запрос с другого сайта запрещён."}, status_code=403)
            if request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
                return JSONResponse({"detail": "Запрос с другого сайта запрещён."}, status_code=403)
        response = await call_next(request)
        token = getattr(request.state, "session_token", None)
        if token and request.url.path != "/api/logout":
            try:
                security.runtime.auth.resolve(token)
            except AuthError as exc:
                response = access_failure(exc)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse({"detail": "Проверьте поля запроса и типы значений."}, status_code=422)

    @app.exception_handler(AuthError)
    async def auth_error(request, exc):
        return access_failure(exc)

    @app.exception_handler(AccessExpired)
    async def expired(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=401)

    @app.exception_handler(StorageConflict)
    async def conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(StorageError)
    async def storage_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(ValueError)
    async def data_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(JobBusy)
    async def busy(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(JobMissing)
    async def missing(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)
