"""Согласование сессионных снимков с архивом; интерфейс только показывает исходы."""

from __future__ import annotations

import copy
from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .auth import AccessExpired
from .experiments import load_experiment
from .reporting import export_json
from .storage import KEEP_VALIDATION, ExperimentStore, StorageError


@dataclass(frozen=True)
class WriteResult:
    record: dict
    error: str | None = None

    @property
    def saved(self) -> bool:
        return self.error is None


class Workspace:
    def __init__(self, state: MutableMapping[str, Any], store: ExperimentStore):
        self.state = state
        self.store = store
        for key, default in [("history", []), ("pending_records", {}), ("pending_validation_bases", {})]:
            state.setdefault(key, default)

    def persist(self, record: dict, *, expected_validation=KEEP_VALIDATION) -> WriteResult:
        # Непригодный JSON не попадает в очередь повторной записи или скачивания.
        record = load_experiment(export_json(record))
        pending = self.state["pending_records"]
        bases = self.state["pending_validation_bases"]
        if record["id"] in bases:
            expected_validation = bases[record["id"]]
        error = None
        try:
            record = self.store.save(record, expected_validation=expected_validation)
        except AccessExpired:
            raise
        except (StorageError, ValueError) as exc:
            error = str(exc)
            pending[record["id"]] = record
            if expected_validation is not KEEP_VALIDATION:
                bases[record["id"]] = copy.deepcopy(expected_validation)
        else:
            pending.pop(record["id"], None)
            bases.pop(record["id"], None)
        self.state["history"] = [r for r in self.state["history"] if r["id"] != record["id"]] + [record]
        if (self.state.get("active_record") or {}).get("id") == record["id"]:
            self.state["active_record"] = record
        return WriteResult(record, error)

    def refresh(self) -> list[tuple[str, str]]:
        """Повторяем независимые записи; конфликт одной не останавливает остальные."""
        archived = self.store.list_records()
        archived_ids = {record["id"] for record in archived}
        retry = {r["id"]: r for r in self.state["history"] if r["id"] not in archived_ids}
        retry.update(self.state["pending_records"])
        errors = []
        for record_id, record in retry.items():
            outcome = self.persist(record)
            if not outcome.saved:
                errors.append((record_id, outcome.error))
        if retry:
            archived = self.store.list_records()
        merged = {r["id"]: r for r in archived}
        merged.update(self.state["pending_records"])
        self.state["history"] = sorted(
            merged.values(), key=lambda r: (datetime.fromisoformat(r["created_at"]).timestamp(), r["id"])
        )
        active = self.state.get("active_record")
        if active and active["id"] in merged:
            self.state["active_record"] = merged[active["id"]]
        return errors
