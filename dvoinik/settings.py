"""Настройки сервиса без зависимостей от интерфейса и HTTP launcher."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def auth_mode() -> str:
    mode = os.getenv("DVOINIK_AUTH_MODE", "local")
    if mode not in {"local", "demo"}:
        raise ValueError("DVOINIK_AUTH_MODE: допустимы local и demo.")
    return mode


def storage_path() -> Path:
    filename = "demo.sqlite3" if auth_mode() == "demo" else "experiments.sqlite3"
    return Path(os.getenv("DVOINIK_STORAGE_PATH", str(ROOT / ".data" / filename))).expanduser().resolve()


def llm_loopback_only() -> bool:
    value = os.getenv("DVOINIK_LLM_LOOPBACK_ONLY", "0")
    if value not in {"0", "1"}:
        raise ValueError("DVOINIK_LLM_LOOPBACK_ONLY принимает 0 или 1.")
    return value == "1"


def llm_base_url() -> str:
    default = "http://127.0.0.1:11434/v1" if llm_loopback_only() else "http://localhost:11434/v1"
    return os.getenv("LLM_BASE_URL", default)


def model_identity(mock: bool) -> tuple[str, str | None]:
    if mock:
        return "Эвристика", None
    from .ssr import embed_model, mode

    model = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
    config = model + "|" + llm_base_url() + "|respondent-v2"
    if mode() == "ssr":
        return f"{model} · SSR", f"{config}|ssr:{embed_model()}"
    return model, config
