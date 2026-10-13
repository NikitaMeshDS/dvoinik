"""Same-origin HTTP boundary for the local React workspace."""

from __future__ import annotations

import copy
import csv
import hashlib
import hmac
import io
import os
import re
import secrets
import threading
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr

from .auth import AccessExpired, AuthError, AuthStore, digest
from .comparison import compare_runs
from .experiments import (
    CUSTOM_SCENARIO,
    MAX_IMPORT_BYTES,
    attach_validation,
    load_experiment,
    normalize_population,
    normalize_scenario,
    quality_status,
)
from .insights import segment_report
from .jobs import JobBusy, JobMissing, Jobs
from .population import SEGMENTS, allocate_population
from .reporting import export_csv, export_json, summarize
from .runs import RunSettings, run_experiment
from .scenarios import SCENARIOS
from .settings import auth_mode, model_identity, storage_path
from .storage import StorageConflict, StorageError
from .validate import load_survey

COOKIE = "dvoinik_session"


class Body(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Login(Body):
    username: StrictStr
    password: StrictStr


class Preview(Body):
    population: dict
    n: StrictInt


class Run(Body):
    scenario_key: StrictStr
    scenario: dict
    n: StrictInt = 200
    mock: StrictBool = True
    seed: StrictInt = 42
    concurrency: StrictInt = 16


class Import(Body):
    content: StrictStr


class Compare(Body):
    left_id: StrictStr
    right_id: StrictStr


class Survey(Body):
    csv: StrictStr


class Validation(Survey):
    base_validation: dict | None


class Export(Body):
    format: StrictStr = "json"
    kind: StrictStr = "record"


class RecordExport(Export):
    record_id: StrictStr


class Insights(Body):
    record_id: StrictStr
    segment: StrictStr = "all"


class Active(Body):
    active: StrictBool


class SessionSnapshots:
    """Bounded ephemeral samples/previews, scoped by the session digest."""

    def __init__(self):
        self.lock = threading.RLock()
        self.sessions = OrderedDict()

    def state(self, token):
        key = digest(token)
        with self.lock:
            if key not in self.sessions:
                self.sessions[key] = {"samples": {}, "previews": OrderedDict()}
            self.sessions.move_to_end(key)
            while len(self.sessions) > 128:
                self.sessions.popitem(last=False)
            return self.sessions[key]

    def forget(self, token):
        with self.lock:
            self.sessions.pop(digest(token), None)


def create_app(path=None, mode=None, static_dir=None) -> FastAPI:
    mode = auth_mode() if mode is None else mode
    if mode not in {"local", "demo"}:
        raise ValueError("Режим доступа: local или demo.")
    if path is None:
        path = storage_path()
        if not os.getenv("DVOINIK_STORAGE_PATH"):
            path = path.with_name("demo.sqlite3" if mode == "demo" else "experiments.sqlite3")
    auth = AuthStore(path, allow_demo=mode == "demo")
    jobs = Jobs(auth)
    snapshots = SessionSnapshots()
    csrf_secret = secrets.token_bytes(32)

    @asynccontextmanager
    async def lifespan(app):
        yield
        jobs.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.auth, app.state.jobs = auth, jobs

    def access_failure(exc):
        status = 503 if str(exc).startswith("Хранилище доступа недоступно") else 401
        payload = {"detail": str(exc)}
        if status == 503:
            payload["code"] = "access_unavailable"
        return JSONResponse(payload, status_code=status)

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
                auth.resolve(token)
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

    def csrf(token):
        return hmac.new(csrf_secret, token.encode(), hashlib.sha256).hexdigest()

    def identity(request: Request):
        token = request.cookies.get(COOKIE, "")
        # Polling never prolongs inactivity; all other authenticated interaction does.
        poll = request.method == "GET" and re.fullmatch(r"/api/runs/[^/]+", request.url.path)
        user = auth.resolve(token)
        supplied = request.headers.get("x-csrf-token", "")
        if request.method in {"GET", "HEAD"} and supplied:
            if not supplied.isascii() or not hmac.compare_digest(supplied, csrf(token)):
                raise HTTPException(401, "Сессия в браузере изменена. Обновите страницу.")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            supplied = request.headers.get("x-csrf-token", "")
            if not supplied.isascii() or not hmac.compare_digest(supplied, csrf(token)):
                raise HTTPException(403, "Защита запроса устарела. Обновите страницу.")
        if not poll:
            user = auth.resolve(token, touch=True)
        request.state.session_token = token
        return token, user

    def session_data(token):
        user = auth.resolve(token)
        return {
            "user": asdict(user),
            "csrf_token": csrf(token),
            "mode": mode,
            "default_mock": mode == "demo" or os.getenv("DVOINIK_MOCK", "1") == "1",
            "model": model_identity(mode == "demo")[0],
        }

    def set_cookie(response, token):
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")

    def accessible(token, record_id):
        auth.resolve(token)
        cached_sample = None
        with snapshots.lock:
            samples = snapshots.state(token)["samples"]
            for record in samples.values():
                if record["id"] == record_id:
                    cached_sample = copy.deepcopy(record)
                    break
        pending = jobs.record(token, record_id, pending_only=True)
        if pending is not None:
            return pending
        try:
            return auth.workspace(token).get_record(record_id)
        except StorageError as exc:
            if str(exc) == "Эксперимент недоступен в этом рабочем пространстве.":
                if cached_sample is not None:
                    return cached_sample
                pending = jobs.record(token, record_id)
                if pending is not None:
                    return pending
                raise HTTPException(404, str(exc)) from exc
            raise

    def checked_text(value, label):
        try:
            size = len(value.encode("utf-8"))
        except UnicodeError as exc:
            raise ValueError(f"{label}: требуется корректный UTF-8.") from exc
        if size > MAX_IMPORT_BYTES:
            raise ValueError(f"{label}: максимальный размер — 5 МБ.")
        return value.lstrip("\ufeff")

    def survey_preview(token, record_id, content):
        record = accessible(token, record_id)
        preview = attach_validation(record, load_survey(io.StringIO(checked_text(content, "CSV"))))
        auth.resolve(token)
        with snapshots.lock:
            previews = snapshots.state(token)["previews"]
            previews[record_id] = preview
            previews.move_to_end(record_id)
            while len(previews) > 128:
                previews.popitem(last=False)
        return {"record": preview, "base_validation": copy.deepcopy(record.get("validation"))}

    def issue(token, record, options):
        if options.format not in {"json", "csv"} or options.kind not in {
            "record",
            "validation",
            "survey-template",
            "preview",
        }:
            raise ValueError(
                "Выберите формат json/csv и вид выгрузки record/validation/survey-template/preview."
            )
        if options.kind == "preview":
            if options.format != "json":
                raise ValueError("Предпросмотр проверки доступен в JSON.")
            with snapshots.lock:
                preview = snapshots.state(token)["previews"].get(record["id"])
                if preview is None:
                    raise ValueError("Сначала подготовьте предпросмотр опроса.")
                data = export_json(preview)
        elif options.kind == "record":
            data = export_json(record) if options.format == "json" else export_csv(record)
        elif options.kind == "survey-template":
            if options.format != "csv":
                raise ValueError("Шаблон опроса доступен в CSV.")
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(["segment", "variant", "decision"])
            for vid in record["report"]:
                for sid in record["scenario"]["population"]:
                    writer.writerow([sid, vid, 0])
            data = stream.getvalue()
        else:
            with snapshots.lock:
                preview = snapshots.state(token)["previews"].get(record["id"])
                validation = (preview or record).get("validation")
            if validation is None:
                raise ValueError("Сначала загрузите опрос.")
            result = validation["result"]
            if options.format == "json":
                data = export_json(result)
            else:
                stream = io.StringIO()
                writer = csv.DictWriter(
                    stream, fieldnames=["variant", "segment", "survey_n", "actual", "predicted", "error"]
                )
                writer.writeheader()
                writer.writerows(result["cells"])
                data = stream.getvalue()
        handle = auth.issue_export(
            token,
            data,
            "application/json" if options.format == "json" else "text/csv",
            f"dvoinik-{record['id']}-{options.kind}.{options.format}",
        )
        return {"url": f"/download/{handle}"}

    def comparison(token, body):
        left, right = accessible(token, body.left_id), accessible(token, body.right_id)
        result = {"left": left, "right": right, "comparison": compare_runs(left, right)}
        auth.resolve(token)
        return result

    @app.get("/api/session")
    def session(request: Request, response: Response):
        token = request.cookies.get(COOKIE, "")
        try:
            auth.resolve(token, touch=True)
        except AuthError:
            if mode != "demo":
                raise
            token = auth.create_demo_session()
            set_cookie(response, token)
        request.state.session_token = token
        return session_data(token)

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        if mode == "demo":
            raise HTTPException(403, "Вход в аккаунт доступен в локальном режиме.")
        token = auth.login(body.username, body.password)
        previous = request.cookies.get(COOKIE)
        if previous:
            auth.logout(previous)
            snapshots.forget(previous)
        set_cookie(response, token)
        request.state.session_token = token
        return session_data(token)

    @app.post("/api/logout")
    def logout(response: Response, access=Depends(identity)):
        token, _ = access
        auth.logout(token)
        snapshots.forget(token)
        response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
        return {"ok": True}

    @app.get("/api/catalog")
    def catalog(access=Depends(identity)):
        return {"scenarios": {**SCENARIOS, "custom": CUSTOM_SCENARIO}, "segments": SEGMENTS}

    @app.post("/api/preview")
    def preview(body: Preview, access=Depends(identity)):
        RunSettings(n=body.n)
        shares = normalize_population(body.population)
        return {"counts": allocate_population(body.n, shares), "shares": shares}

    @app.get("/api/experiments")
    def experiments(access=Depends(identity)):
        return {"records": auth.workspace(access[0]).list_records()}

    @app.get("/api/experiments/{record_id}")
    def experiment(record_id: str, access=Depends(identity)):
        return accessible(access[0], record_id)

    @app.post("/api/import")
    def import_record(body: Import, access=Depends(identity)):
        record = load_experiment(checked_text(body.content, "JSON"))
        record["import_origin_id"] = record["id"]
        record["id"] = uuid.uuid4().hex[:10]
        return auth.workspace(access[0]).save(record)

    @app.get("/api/sample/{key}")
    def sample(key: str, access=Depends(identity)):
        if key not in SCENARIOS:
            raise HTTPException(404, "Шаблон исследования не найден.")
        token = access[0]
        with snapshots.lock:
            samples = snapshots.state(token)["samples"]
            if key not in samples:
                store = auth.workspace(token)
                record = run_experiment(key, SCENARIOS[key], RunSettings(), guard=store.guard)
                record["sample"] = True
                store.guard()
                samples[key] = record
            return copy.deepcopy(samples[key])

    @app.post("/api/runs", status_code=202)
    def run(body: Run, access=Depends(identity)):
        if body.scenario_key not in {*SCENARIOS, "custom"}:
            raise ValueError("Неизвестный сценарий исследования.")
        scenario = normalize_scenario(body.scenario)
        settings = RunSettings(body.n, True if mode == "demo" else body.mock, body.seed, body.concurrency)
        result = jobs.submit(access[0], body.scenario_key, scenario, settings)
        return {key: result[key] for key in ("id", "status", "done", "total")}

    @app.get("/api/runs/{job_id}")
    def job(job_id: str, access=Depends(identity)):
        return jobs.get(access[0], job_id)

    @app.post("/api/runs/{job_id}/retry")
    def retry(job_id: str, access=Depends(identity)):
        return jobs.retry(access[0], job_id)

    @app.post("/api/compare")
    def compare(body: Compare, access=Depends(identity)):
        return comparison(access[0], body)

    @app.post("/api/insights")
    def insights(body: Insights, access=Depends(identity)):
        record = accessible(access[0], body.record_id)
        report = record["report"] if body.segment == "all" else segment_report(record, body.segment)
        return {"report": report, "summary": summarize(report), "quality": quality_status(record)}

    @app.post("/api/experiments/{record_id}/validation/preview")
    def preview_validation(record_id: str, body: Survey, access=Depends(identity)):
        return survey_preview(access[0], record_id, body.csv)

    @app.put("/api/experiments/{record_id}/validation")
    def save_validation(record_id: str, body: Validation, access=Depends(identity)):
        preview = survey_preview(access[0], record_id, body.csv)["record"]
        record = auth.workspace(access[0]).save(preview, expected_validation=body.base_validation)
        with snapshots.lock:
            snapshots.state(access[0])["previews"].pop(record_id, None)
            samples = snapshots.state(access[0])["samples"]
            for key, sample in samples.items():
                if sample["id"] == record_id:
                    samples[key] = record
        return record

    @app.post("/api/export")
    def export(body: RecordExport, access=Depends(identity)):
        return issue(access[0], accessible(access[0], body.record_id), body)

    @app.post("/api/runs/{job_id}/export")
    def export_job(job_id: str, body: Export, access=Depends(identity)):
        record = jobs.get(access[0], job_id)["record"]
        if record is None:
            raise HTTPException(409, "Результат исследования ещё не готов.")
        return issue(access[0], record, body)

    @app.post("/api/compare/export")
    def export_comparison(body: Compare, access=Depends(identity)):
        result = comparison(access[0], body)
        handle = auth.issue_export(
            access[0], export_json(result), "application/json", "dvoinik-comparison.json"
        )
        return {"url": f"/download/{handle}"}

    @app.get("/api/users")
    def users(access=Depends(identity)):
        if access[1].role != "admin":
            raise HTTPException(403, "Управление доступом доступно администратору.")
        return {"users": auth.users()}

    @app.put("/api/users/{user_id}/active")
    def user_active(user_id: str, body: Active, access=Depends(identity)):
        if access[1].role != "admin":
            raise HTTPException(403, "Управление доступом доступно администратору.")
        try:
            auth.set_active(user_id, body.active)
        except AuthError as exc:
            if str(exc) == "Учётная запись не найдена.":
                raise HTTPException(404, str(exc)) from exc
            if str(exc).startswith("Хранилище доступа недоступно"):
                raise
            raise ValueError(str(exc)) from exc
        return {"users": auth.users()}

    @app.api_route("/download/{handle}", methods=["GET", "HEAD"])
    def download(handle: str, request: Request):
        try:
            token = request.cookies.get(COOKIE, "")
            if not auth.export_available(handle, token):
                raise AuthError("Ссылка недоступна.")
            data, mime, filename = auth.consume_export(handle, head=request.method == "HEAD")
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

    if static_dir is not None:
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

    return app
