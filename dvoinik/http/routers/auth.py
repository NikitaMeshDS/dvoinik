"""Auth HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...auth import AuthError
from ..models import Login
from ..runtime import get_runtime
from ..security import COOKIE, get_security, identity

router = APIRouter()


@router.get("/api/session")
def session(
    request: Request, response: Response, runtime=Depends(get_runtime), security=Depends(get_security)
):
    token = request.cookies.get(COOKIE, "")
    try:
        runtime.auth.resolve(token, touch=True)
    except AuthError:
        if runtime.mode != "demo":
            raise
        token = runtime.auth.create_demo_session()
        security.set_cookie(response, token)
    request.state.session_token = token
    return security.session_data(token)


@router.post("/api/login")
def login(
    body: Login,
    request: Request,
    response: Response,
    runtime=Depends(get_runtime),
    security=Depends(get_security),
):
    if runtime.mode == "demo":
        raise HTTPException(403, "Вход в аккаунт доступен в локальном режиме.")
    token = runtime.auth.login(body.username, body.password)
    previous = request.cookies.get(COOKIE)
    if previous:
        runtime.auth.logout(previous)
        runtime.snapshots.forget(previous)
    security.set_cookie(response, token)
    request.state.session_token = token
    return security.session_data(token)


@router.post("/api/logout")
def logout(response: Response, access=Depends(identity), runtime=Depends(get_runtime)):
    token, _ = access
    runtime.auth.logout(token)
    runtime.snapshots.forget(token)
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
    return {"ok": True}
