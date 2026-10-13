"""Локальный архив одного рабочего пространства. SQLite не заменяет контроль доступа."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .experiments import load_experiment
from .reporting import export_json


class StorageError(Exception):
    """Архив недоступен или содержит несовместимые данные."""


class StorageConflict(StorageError):
    """Другая сессия уже обновила проверку опросом."""


KEEP_VALIDATION = object()


class ExperimentStore:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def _connection(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5)
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, created_at REAL NOT NULL, payload TEXT NOT NULL)"
                )
                yield connection
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(
                "Локальный архив недоступен. Проверьте путь и права записи на сервере."
            ) from exc
        finally:
            if connection is not None:
                connection.close()

    def list_records(self):
        with self._connection() as connection:
            rows = connection.execute("SELECT payload FROM experiments ORDER BY created_at, id").fetchall()
        try:
            return [load_experiment(row[0]) for row in rows]
        except ValueError as exc:
            raise StorageError("В локальном архиве есть повреждённый отчёт. Файл архива сохранён.") from exc

    def save(self, record, *, expected_validation=KEEP_VALIDATION):
        # Одинаковая проверка для импорта, сохранения и повторного чтения.
        checked = load_experiment(export_json(record))
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM experiments WHERE id = ?", (checked["id"],)
            ).fetchone()
            if row:
                original = load_experiment(row[0])
                before = {k: v for k, v in original.items() if k != "validation"}
                after = {k: v for k, v in checked.items() if k != "validation"}
                if before != after:
                    raise StorageError("Этот ID уже принадлежит другому снимку эксперимента.")
                saved = original.get("validation")
                if expected_validation is KEEP_VALIDATION:
                    if saved:
                        checked["validation"] = saved
                    else:
                        checked.pop("validation", None)
                elif saved != expected_validation:
                    raise StorageConflict(
                        "Проверка опросом уже изменена в другой сессии. "
                        "Скачайте текущий JSON и откройте новую сессию перед повторным сохранением."
                    )
            connection.execute(
                "INSERT INTO experiments (id, created_at, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
                (
                    checked["id"],
                    datetime.fromisoformat(checked["created_at"]).timestamp(),
                    json.dumps(checked, ensure_ascii=False, allow_nan=False),
                ),
            )
        return checked
