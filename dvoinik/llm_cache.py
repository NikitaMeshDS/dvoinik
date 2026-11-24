"""Необязательный кэш ответов LLM на диске.

Включается переменной DVOINIK_LLM_CACHE=1. Ключ учитывает модель, адрес API, текст
и настройки запроса. В кэш попадает проверенная оценка до вычисления решения профиля.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

from . import llm_json
from .settings import llm_base_url, storage_path


def enabled() -> bool:
    return os.getenv("DVOINIK_LLM_CACHE", "0") == "1"


def path() -> Path:
    custom = os.getenv("DVOINIK_LLM_CACHE_PATH")
    return Path(custom).expanduser().resolve() if custom else storage_path().with_name("llm_cache.sqlite3")


def key(model: str, messages: list[dict], temperature: float, *, references=None) -> str:
    payload = {
        "schema": 2,
        "model": model,
        "base_url": llm_base_url(),
        "messages": llm_json.prepare_messages(messages),
        "temperature": temperature,
        "json_mode": llm_json.mode(),
        "extra_body": llm_json.extra_body(),
        "references": references,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _connect() -> sqlite3.Connection:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=10)
    connection.execute("CREATE TABLE IF NOT EXISTS answers (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return connection


def get(cache_key: str) -> dict | None:
    if not enabled():
        return None
    with _connect() as connection:
        row = connection.execute("SELECT value FROM answers WHERE key = ?", (cache_key,)).fetchone()
    return json.loads(row[0]) if row else None


def put(cache_key: str, value: dict) -> None:
    if not enabled():
        return
    with _connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO answers (key, value) VALUES (?, ?)",
            (cache_key, json.dumps(value, ensure_ascii=False)),
        )
