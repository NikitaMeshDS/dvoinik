"""Bounded in-process runs. Snapshots and progress belong to the creating session."""

from __future__ import annotations

import copy
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .auth import AccessExpired, AuthError
from .experiments import load_experiment
from .reporting import export_json
from .runs import RunSettings, run_experiment
from .storage import StorageError


class JobBusy(ValueError):
    pass


class JobMissing(LookupError):
    pass


class JobInterrupted(RuntimeError):
    pass


@dataclass
class Job:
    id: str
    token: str = field(repr=False)
    owner: str
    total: int
    status: str = "queued"
    done: int = 0
    record: dict | None = None
    error: str | None = None
    saved: bool = False
    released: bool = field(default=False, repr=False)

    def public(self):
        return copy.deepcopy(
            {key: getattr(self, key) for key in ("id", "status", "done", "total", "record", "error", "saved")}
        )


class Jobs:
    def __init__(self, auth, *, workers=2, queue_size=8, retained=128):
        self.auth = auth
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dvoinik-run")
        self.capacity = threading.BoundedSemaphore(workers + queue_size)
        self.lock = threading.RLock()
        self.jobs = OrderedDict()
        self.owners = set()
        self.retained = retained
        self.closed = False

    @property
    def active_count(self):
        with self.lock:
            return len(self.owners)

    def submit(self, token, key, scenario, settings: RunSettings):
        user = self.auth.resolve(token)
        with self.lock:
            if self.closed:
                raise JobBusy("Сервис завершает работу. Повторите запуск позже.")
            if user.id in self.owners:
                raise JobBusy("У вас уже выполняется исследование.")
            if len(self._recovery()) + len(self.owners) >= self.retained:
                for pending in self._recovery():
                    try:
                        self.auth.resolve(pending.token)
                    except AuthError as exc:
                        if not str(exc).startswith("Хранилище доступа недоступно"):
                            self.jobs.pop(pending.id, None)
                if len(self._recovery()) + len(self.owners) >= self.retained:
                    raise JobBusy("Сначала сохраните готовые результаты или завершите текущие исследования.")
            if not self.capacity.acquire(blocking=False):
                raise JobBusy("Очередь исследований заполнена. Повторите позже.")
            job = Job(uuid.uuid4().hex, token, user.id, settings.n * len(scenario["variants"]))
            self.jobs[job.id] = job
            self.owners.add(user.id)
            try:
                future = self.pool.submit(self._execute, job, key, copy.deepcopy(scenario), settings)
                future.add_done_callback(lambda done: self._cancelled(job) if done.cancelled() else None)
            except RuntimeError:
                self.jobs.pop(job.id)
                self.owners.remove(user.id)
                self.capacity.release()
                raise JobBusy("Сервис завершает работу. Повторите запуск позже.") from None
            return job.public()

    def _execute(self, job, key, scenario, settings):
        try:
            store = self.auth.workspace(job.token)
            access_guard = store.guard

            def guard():
                with self.lock:
                    if self.closed:
                        raise JobInterrupted("Сервис остановлен. Исследование прервано.")
                    access_guard()

            store.guard = guard
            with self.lock:
                guard()
                job.status = "running"

            def progress(done, total):
                with self.lock:
                    guard()
                    job.done, job.total = done, total

            record = run_experiment(key, scenario, settings, progress=progress, guard=store.guard)
            # A finished engine still cannot supply unchecked, exportable data.
            record = load_experiment(export_json(record))
            error, saved = None, False
            with self.lock:
                guard()
                try:
                    record = store.save(record)
                    saved = True
                except AccessExpired:
                    raise
                except (StorageError, ValueError) as exc:
                    error = str(exc)
                guard()
                job.record, job.error, job.saved = record, error, saved
                job.status = "completed"
        except JobInterrupted as exc:
            with self.lock:
                job.record, job.saved = None, False
                job.status, job.error = "failed", str(exc)
        except (AccessExpired, AuthError):
            with self.lock:
                job.record, job.saved = None, False
                job.status, job.error = "failed", "Доступ завершён. Войдите снова."
        except Exception:
            # Providers can include credentials in exceptions; do not expose them.
            with self.lock:
                job.status, job.error = (
                    "failed",
                    "Не удалось завершить исследование. Проверьте настройки модели.",
                )
        finally:
            self._finish(job)

    def _cancelled(self, job):
        with self.lock:
            job.status, job.error = "failed", "Сервис остановлен. Исследование прервано."
            self._finish(job)

    def _finish(self, job):
        with self.lock:
            if job.released:
                return
            job.released = True
            self.owners.discard(job.owner)
            self.capacity.release()
            recovery_ids = {item.id for item in self._recovery()}
            disposable = [
                jid
                for jid, item in self.jobs.items()
                if item.status not in {"queued", "running"} and jid not in recovery_ids
            ]
            keep = max(0, self.retained - len(recovery_ids))
            for jid in disposable[:-keep] if keep else disposable:
                self.jobs.pop(jid, None)

    def _recovery(self):
        return [
            job
            for job in self.jobs.values()
            if job.status == "completed" and job.record is not None and not job.saved
        ]

    def _get(self, token, job_id):
        self.auth.resolve(token)
        job = self.jobs.get(job_id)
        if not job or job.token != token:
            raise JobMissing("Исследование недоступно в этой сессии.")
        return job

    def get(self, token, job_id):
        with self.lock:
            job = self._get(token, job_id)
            return job.public()

    def recovery(self, token):
        self.auth.resolve(token)
        with self.lock:
            return [job.public() for job in self._recovery() if job.token == token]

    def reconcile_saved(self, token, record):
        self.auth.resolve(token)
        with self.lock:
            for job in self.jobs.values():
                if (
                    job.token == token
                    and job.status == "completed"
                    and job.record
                    and job.record["id"] == record["id"]
                ):
                    job.record, job.error, job.saved = copy.deepcopy(record), None, True

    def record(self, token, record_id, *, pending_only=False):
        self.auth.resolve(token)
        with self.lock:
            for job in self.jobs.values():
                if (
                    job.token == token
                    and job.status == "completed"
                    and job.record
                    and job.record["id"] == record_id
                    and (not pending_only or not job.saved)
                ):
                    return copy.deepcopy(job.record)
        return None

    def retry(self, token, job_id):
        with self.lock:
            if self.closed:
                raise JobBusy("Сервис завершает работу. Повторите позже.")
            job = self._get(token, job_id)
            if job.status != "completed" or not job.record:
                raise JobBusy("Результат исследования ещё не готов.")
            store = self.auth.workspace(token)
            try:
                record = store.save(job.record)
            except AccessExpired:
                raise
            except (StorageError, ValueError) as exc:
                job.error, job.saved = str(exc), False
            else:
                store.guard()
                job.record, job.error, job.saved = record, None, True
            self.auth.resolve(token)
            return job.public()

    def close(self):
        with self.lock:
            self.closed = True
        self.pool.shutdown(wait=True, cancel_futures=True)
