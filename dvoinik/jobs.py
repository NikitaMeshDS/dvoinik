"""Bounded in-process runs. Snapshots and progress belong to the creating session."""

from __future__ import annotations

import copy
import logging
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

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


class JobCancelled(JobInterrupted):
    pass


ACTIVE_STATUSES = {"queued", "running", "cancelling"}
LOGGER = logging.getLogger(__name__)


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
    request: dict | None = field(default=None, repr=False)
    released: bool = field(default=False, repr=False)
    cancel_requested: bool = field(default=False, repr=False)
    future: Future | None = field(default=None, repr=False)
    deploy_lease: BinaryIO | None = field(default=None, repr=False)

    def public(self):
        return copy.deepcopy(
            {
                key: getattr(self, key)
                for key in ("id", "status", "done", "total", "record", "error", "saved", "request")
            }
        )


class Jobs:
    def __init__(self, auth, *, workers=2, queue_size=8, retained=128, deploy_lock=None, journal=None):
        self.auth = auth
        self.journal = journal
        self.deploy_lock = Path(deploy_lock) if deploy_lock else None
        if self.deploy_lock is not None:
            self.deploy_lock.touch()
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

    def _acquire_deploy_lease(self):
        if self.deploy_lock is None:
            return None

        import fcntl

        lease = self.deploy_lock.open("rb")
        try:
            fcntl.flock(lease, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as exc:
            lease.close()
            if isinstance(exc, BlockingIOError):
                raise JobBusy("Сервис обновляется. Повторите запуск позже.") from None
            raise
        return lease

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
            # Retain only application inputs: provider settings and credentials are
            # deliberately absent. Workers/public responses receive separate copies.
            request = {
                "scenario_key": key,
                "scenario": copy.deepcopy(scenario),
                "n": settings.n,
                "mock": settings.mock,
                "seed": settings.seed,
                "concurrency": settings.concurrency,
            }
            job = Job(
                uuid.uuid4().hex,
                token,
                user.id,
                settings.n * len(request["scenario"]["variants"]),
                request=request,
            )
            if not self.capacity.acquire(blocking=False):
                raise JobBusy("Очередь исследований заполнена. Повторите позже.")
            try:
                job.deploy_lease = self._acquire_deploy_lease()
                if self.journal is not None:
                    self.journal.add(job)
            except JobBusy:
                self.capacity.release()
                raise
            except AuthError:
                self._release_deploy_lease(job)
                self.capacity.release()
                raise
            except OSError as exc:
                self.capacity.release()
                raise StorageError("Не удалось проверить доступность запуска. Повторите позже.") from exc
            self.jobs[job.id] = job
            self.owners.add(user.id)
            try:
                future = self.pool.submit(
                    self._execute, job, key, copy.deepcopy(request["scenario"]), settings
                )
                job.future = future
                future.add_done_callback(lambda done: self._cancelled(job) if done.cancelled() else None)
            except RuntimeError:
                self.jobs.pop(job.id)
                job.status = "failed"
                self._finish(job)
                raise JobBusy("Сервис завершает работу. Повторите запуск позже.") from None
            return job.public()

    def _execute(self, job, key, scenario, settings):
        try:
            store = self.auth.workspace(job.token)
            access_guard = store.guard

            def guard():
                with self.lock:
                    if job.cancel_requested:
                        raise JobCancelled("Исследование остановлено. Частичный результат не сохранён.")
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
            if self.journal is not None:
                record["id"] = job.id
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
        except JobCancelled as exc:
            with self.lock:
                job.record, job.saved = None, False
                job.status, job.error = "cancelled", str(exc)
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
                job.record, job.saved = None, False
                job.status, job.error = (
                    ("cancelled", "Исследование остановлено. Частичный результат не сохранён.")
                    if job.cancel_requested
                    else ("failed", "Не удалось завершить исследование. Проверьте настройки модели.")
                )
        finally:
            self._finish(job)

    def _cancelled(self, job):
        with self.lock:
            job.status, job.error = (
                ("cancelled", "Исследование остановлено до начала выполнения.")
                if job.cancel_requested
                else ("failed", "Сервис остановлен. Исследование прервано.")
            )
            self._finish(job)

    def _finish(self, job):
        with self.lock:
            if job.released:
                return
            job.released = True
            if self.journal is not None and job.status == "failed" and not self.closed:
                try:
                    self.journal.remove(job.owner, job.id)
                except AuthError:
                    LOGGER.warning("Could not remove the snapshot of a failed research run.")
            job.future = None
            self.owners.discard(job.owner)
            self.capacity.release()
            recovery_ids = {item.id for item in self._recovery()}
            disposable = [
                jid
                for jid, item in self.jobs.items()
                if item.status not in ACTIVE_STATUSES and jid not in recovery_ids
            ]
            keep = max(0, self.retained - len(recovery_ids))
            for jid in disposable[:-keep] if keep else disposable:
                self.jobs.pop(jid, None)
            self._release_deploy_lease(job)

    @staticmethod
    def _release_deploy_lease(job):
        if job.deploy_lease is not None:
            job.deploy_lease.close()
            job.deploy_lease = None

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
        owner = self.auth.resolve(token).id
        with self.lock:
            job = self.jobs.get(job_id)
            if job and job.token == token:
                return job.public()
            if self.journal is not None:
                interrupted = self.journal.interrupted(owner, job_id)
                if interrupted:
                    return interrupted[0]
            raise JobMissing("Исследование недоступно в этой сессии.")

    def active(self, token):
        self.auth.resolve(token)
        with self.lock:
            return [
                job.public()
                for job in self.jobs.values()
                if job.token == token and job.status in ACTIVE_STATUSES
            ]

    def cancel(self, token, job_id):
        with self.lock:
            job = self._get(token, job_id)
            if job.status not in ACTIVE_STATUSES:
                return job.public()
            if self.journal is not None and not job.cancel_requested:
                self.journal.remove(job.owner, job.id)
            job.cancel_requested = True
            job.status = "cancelling"
            # A running worker keeps its capacity until guard/cleanup finishes.
            # A queued future invokes _cancelled synchronously under the RLock.
            if job.future:
                job.future.cancel()
            return job.public()

    def recovery(self, token):
        owner = self.auth.resolve(token).id
        with self.lock:
            pending = [job.public() for job in self._recovery() if job.token == token]
            if self.journal is not None:
                pending += self.journal.interrupted(owner)
            return pending

    def dismiss_interrupted(self, token, job_id):
        owner = self.auth.resolve(token).id
        if self.journal is None or not self.journal.remove(owner, job_id, interrupted_only=True):
            raise JobMissing("Прерванное исследование недоступно.")

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
