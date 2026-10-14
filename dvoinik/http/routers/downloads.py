"""Downloads HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...auth import AuthError
from ...reporting import export_json
from ..models import Compare, Export, RecordExport
from ..runtime import get_runtime
from ..security import COOKIE, identity

router = APIRouter()


@router.post("/api/export")
def export(body: RecordExport, access=Depends(identity), runtime=Depends(get_runtime)):
    return runtime.issue(access[0], runtime.accessible(access[0], body.record_id), body)


@router.post("/api/runs/{job_id}/export")
def export_job(job_id: str, body: Export, access=Depends(identity), runtime=Depends(get_runtime)):
    record = runtime.jobs.get(access[0], job_id)["record"]
    if record is None:
        raise HTTPException(409, "Результат исследования ещё не готов.")
    return runtime.issue(access[0], record, body)


@router.post("/api/compare/export")
def export_comparison(body: Compare, access=Depends(identity), runtime=Depends(get_runtime)):
    result = runtime.comparison(access[0], body)
    handle = runtime.auth.issue_export(
        access[0], export_json(result), "application/json", "dvoinik-comparison.json"
    )
    return {"url": f"/download/{handle}"}


@router.api_route("/download/{handle}", methods=["GET", "HEAD"])
def download(handle: str, request: Request, runtime=Depends(get_runtime)):
    try:
        token = request.cookies.get(COOKIE, "")
        if not runtime.auth.export_available(handle, token):
            raise AuthError("Ссылка недоступна.")
        data, mime, filename = runtime.auth.consume_export(handle, head=request.method == "HEAD")
    except AuthError as exc:
        raise HTTPException(410, "Ссылка недоступна. Подготовьте скачивание заново.") from exc
    return Response(
        content=b"" if request.method == "HEAD" else data,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data)),
        },
    )
