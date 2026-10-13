"""Ссылки на закрытый endpoint; отчёты не регистрируются в публичном /media/."""

from __future__ import annotations

import html
import os
from urllib.parse import urlsplit

import streamlit as st

from .auth import AuthError, digest
from .auth_ui import expire_access


def download(label, data, file_name, mime, *, key, width="content", target=st):
    origin = os.getenv("DVOINIK_DOWNLOAD_ORIGIN", "")
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.query
        or parsed.fragment
        or parsed.path
    ):
        target.button(label, key=key, disabled=True, width=width)
        target.caption("Запустите сервис через python serve.py, чтобы включить скачивание.")
        return
    auth, token = st.session_state._auth_store, st.session_state._auth_token
    data = data.encode("utf-8") if isinstance(data, str) else data
    fingerprint = digest(f"{key}|{file_name}|{mime}|{digest(data.hex())}")
    cache = st.session_state.setdefault("_download_cache", {})
    cached = cache.get(fingerprint)
    try:
        auth.resolve(token)
        if cached is None or cached[1] <= auth.clock() or not auth.export_available(cached[0], token):
            cached = (auth.issue_export(token, data, mime, file_name), auth.clock() + 900)
            cache[fingerprint] = cached
    except AuthError:
        expire_access()
    # Здесь только серверный URL, без сырого токена сессии и параметров пользователя.
    href = f"{origin}/download/{cached[0]}"
    target.markdown(
        f'<a class="secure-download {"stretch" if width == "stretch" else ""}" '
        f'data-download-key="{html.escape(key, quote=True)}" href="{html.escape(href, quote=True)}" '
        f'download="{html.escape(file_name, quote=True)}" referrerpolicy="no-referrer">{html.escape(label)}</a>',
        unsafe_allow_html=True,
    )
