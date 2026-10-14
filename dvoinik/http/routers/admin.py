"""Admin HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...auth import AuthError
from ..models import Active
from ..runtime import get_runtime
from ..security import identity

router = APIRouter()


@router.get("/api/users")
def users(access=Depends(identity), runtime=Depends(get_runtime)):
    if access[1].role != "admin":
        raise HTTPException(403, "Управление доступом доступно администратору.")
    return {"users": runtime.auth.users()}


@router.put("/api/users/{user_id}/active")
def user_active(user_id: str, body: Active, access=Depends(identity), runtime=Depends(get_runtime)):
    if access[1].role != "admin":
        raise HTTPException(403, "Управление доступом доступно администратору.")
    try:
        runtime.auth.set_active(user_id, body.active)
    except AuthError as exc:
        if str(exc) == "Учётная запись не найдена.":
            raise HTTPException(404, str(exc)) from exc
        if str(exc).startswith("Хранилище доступа недоступно"):
            raise
        raise ValueError(str(exc)) from exc
    return {"users": runtime.auth.users()}
