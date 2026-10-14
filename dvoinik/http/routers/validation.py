"""Validation HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..models import Survey, Validation
from ..runtime import get_runtime
from ..security import identity

router = APIRouter()


@router.post("/api/experiments/{record_id}/validation/preview")
def preview_validation(record_id: str, body: Survey, access=Depends(identity), runtime=Depends(get_runtime)):
    return runtime.survey_preview(access[0], record_id, body.csv)


@router.put("/api/experiments/{record_id}/validation")
def save_validation(record_id: str, body: Validation, access=Depends(identity), runtime=Depends(get_runtime)):
    return runtime.save_validation(access[0], record_id, body.csv, body.base_validation)
