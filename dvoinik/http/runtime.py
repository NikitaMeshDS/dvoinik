"""Per-app research services over existing auth, jobs and domain modules."""

from __future__ import annotations

import copy
import csv
import io
import threading
import uuid
from collections import OrderedDict

from fastapi import HTTPException, Request

from ..auth import AuthStore, digest
from ..comparison import compare_runs
from ..experiments import MAX_IMPORT_BYTES, attach_validation
from ..jobs import Jobs
from ..reporting import export_csv, export_json
from ..runs import RunSettings, run_experiment
from ..scenarios import SCENARIOS
from ..storage import StorageError
from ..summary import team_summary
from ..survey_materials import survey_kit, survey_template
from ..validate import load_survey


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


class Runtime:
    """Own every mutable service/cache for one factory invocation."""

    def __init__(self, path, mode):
        self.mode = mode
        self.auth = AuthStore(path, allow_demo=mode == "demo")
        self.jobs = Jobs(self.auth)
        self.snapshots = SessionSnapshots()

    def accessible(self, token, record_id):
        self.auth.resolve(token)
        cached_sample = None
        with self.snapshots.lock:
            samples = self.snapshots.state(token)["samples"]
            for record in samples.values():
                if record["id"] == record_id:
                    cached_sample = copy.deepcopy(record)
                    break
        pending = self.jobs.record(token, record_id, pending_only=True)
        if pending is not None:
            return pending
        try:
            return self.auth.workspace(token).get_record(record_id)
        except StorageError as exc:
            if str(exc) == "Эксперимент недоступен в этом рабочем пространстве.":
                if cached_sample is not None:
                    return cached_sample
                pending = self.jobs.record(token, record_id)
                if pending is not None:
                    return pending
                raise HTTPException(404, str(exc)) from exc
            raise

    @staticmethod
    def checked_text(value, label):
        try:
            size = len(value.encode("utf-8"))
        except UnicodeError as exc:
            raise ValueError(f"{label}: требуется корректный UTF-8.") from exc
        if size > MAX_IMPORT_BYTES:
            raise ValueError(f"{label}: максимальный размер — 5 МБ.")
        return value.lstrip("\ufeff")

    def checked_validation(self, token, record_id, content):
        record = self.accessible(token, record_id)
        preview = attach_validation(record, load_survey(io.StringIO(self.checked_text(content, "CSV"))))
        self.auth.resolve(token)
        return {"record": preview, "base_validation": copy.deepcopy(record.get("validation"))}

    def sample(self, token, key):
        if key not in SCENARIOS:
            raise HTTPException(404, "Шаблон исследования не найден.")
        with self.snapshots.lock:
            samples = self.snapshots.state(token)["samples"]
            if key not in samples:
                store = self.auth.workspace(token)
                record = run_experiment(key, SCENARIOS[key], RunSettings(), guard=store.guard)
                record["sample"] = True
                store.guard()
                samples[key] = record
            return copy.deepcopy(samples[key])

    def survey_preview(self, token, record_id, content):
        result = self.checked_validation(token, record_id, content)
        preview_id = uuid.uuid4().hex
        with self.snapshots.lock:
            previews = self.snapshots.state(token)["previews"]
            previews[preview_id] = copy.deepcopy(result["record"])
            while len(previews) > 128:
                previews.popitem(last=False)
        return {"preview_id": preview_id, **result}

    def cached_preview(self, token, record_id, preview_id):
        if preview_id is None:
            raise ValueError("Укажите идентификатор предпросмотра опроса.")
        with self.snapshots.lock:
            preview = self.snapshots.state(token)["previews"].get(preview_id)
            if preview is None:
                raise ValueError("Предпросмотр недоступен или устарел. Подготовьте его заново.")
            if preview["id"] != record_id:
                raise ValueError("Предпросмотр относится к другому исследованию.")
            return copy.deepcopy(preview)

    def save_validation(self, token, record_id, content, base_validation):
        preview = self.checked_validation(token, record_id, content)["record"]
        record = self.auth.workspace(token).save(preview, expected_validation=base_validation)
        self.jobs.reconcile_saved(token, record)
        with self.snapshots.lock:
            samples = self.snapshots.state(token)["samples"]
            for key, sample in samples.items():
                if sample["id"] == record_id:
                    samples[key] = record
        return record

    def issue(self, token, record, options):
        formats = {
            "record": {"json", "csv"},
            "validation": {"json", "csv"},
            "survey-template": {"csv"},
            "survey-kit": {"zip"},
            "summary": {"html"},
            "preview": {"json"},
        }
        if options.format not in formats.get(options.kind, set()):
            raise ValueError(
                "Выберите JSON/CSV для отчёта или проверки, CSV для шаблона, "
                "ZIP для комплекта опроса, HTML для резюме или JSON для предпросмотра."
            )
        if options.kind == "preview":
            if options.format != "json":
                raise ValueError("Предпросмотр проверки доступен в JSON.")
            data = export_json(self.cached_preview(token, record["id"], options.preview_id))
        elif options.kind == "record":
            data = export_json(record) if options.format == "json" else export_csv(record)
        elif options.kind == "survey-template":
            data = survey_template(record)
        elif options.kind == "survey-kit":
            data = survey_kit(record)
        elif options.kind == "summary":
            data = team_summary(record)
        else:
            validation_record = (
                self.cached_preview(token, record["id"], options.preview_id)
                if options.preview_id is not None
                else record
            )
            validation = validation_record.get("validation")
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
        handle = self.auth.issue_export(
            token,
            data,
            {
                "json": "application/json",
                "csv": "text/csv",
                "zip": "application/zip",
                "html": "text/html",
            }[options.format],
            f"dvoinik-{record['id']}-{options.kind}.{options.format}",
        )
        return {"url": f"/download/{handle}"}

    def comparison(self, token, body):
        left, right = self.accessible(token, body.left_id), self.accessible(token, body.right_id)
        result = {"left": left, "right": right, "comparison": compare_runs(left, right)}
        self.auth.resolve(token)
        return result


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime
