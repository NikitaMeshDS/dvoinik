"""Оболочка приложения: вход, синхронизация рабочего пространства и маршрутизация."""

from __future__ import annotations

import streamlit as st

from .auth import AccessExpired, AuthError
from .auth_ui import account_sidebar, administration, expire_access, require_access
from .comparison_ui import comparison_view
from .constructor_ui import render_constructor
from .draft_ui import initialize_drafts, navigate, reuse_record
from .editor_ui import sidebar_settings
from .library import library_view
from .methodology_ui import methodology
from .presentation import escape, markup
from .settings import ROOT, auth_mode, storage_path
from .storage import StorageError
from .workspace import Workspace

NAV_LABELS = {
    "Эксперимент": "Конструктор",
    "История": "Исследования",
    "Сравнение": "Сравнение",
    "Методология": "Методология",
}


def _refresh_workspace(auth, token):
    try:
        store = auth.workspace(token)
        st.session_state.experiment_store = store
        errors = Workspace(st.session_state, store).refresh()
    except (AccessExpired, AuthError):
        expire_access()
    except (StorageError, ValueError) as exc:
        st.error(f"История на диске недоступна: {exc} Новые отчёты можно скачать из текущей сессии.")
    else:
        for record_id, message in errors:
            st.error(
                f"Не удалось сохранить исследование {record_id}: {message} Локальный отчёт сохранён в сессии для скачивания."
            )


def main():
    st.set_page_config(
        page_title="Двойник · лаборатория клиентов",
        page_icon="◉",
        layout="wide",
        initial_sidebar_state="auto",
    )
    markup(f"<style>{(ROOT / 'assets/style.css').read_text()}</style>")
    try:
        mode, path = auth_mode(), storage_path()
    except ValueError as exc:
        st.error(f"Ошибка конфигурации доступа: {exc}")
        st.stop()
    auth, token, user = require_access(path, mode)
    _refresh_workspace(auth, token)
    initialize_drafts(demo=user.role == "demo")
    labels = {**NAV_LABELS, **({"Доступ": "Доступ команды"} if user.role == "admin" else {})}
    st.session_state.setdefault("navigation", "История" if st.session_state.history else "Эксперимент")
    with st.sidebar:
        markup(
            '<div class="brand"><span class="brand-mark"></span><span class="brand-name">двойник</span></div><p class="brand-sub">Лаборатория клиентов</p>'
        )
        nav = st.radio(
            "Рабочее пространство",
            list(labels),
            format_func=labels.get,
            key="navigation",
            label_visibility="collapsed",
        )
        st.divider()
        if nav == "Эксперимент":
            key, settings = sidebar_settings(demo=user.role == "demo")
        markup(
            '<div class="sidebar-note">Проверяйте гипотезы до запуска.<br>Синтетическая аудитория помогает подготовить живое исследование.</div>'
        )
        account_sidebar(auth, token, user)
    markup(
        '<div class="topline"><span><strong>Рабочее пространство</strong> / '
        + escape(labels[nav])
        + '</span><span class="status-pill">Синтетическая аудитория</span></div>'
    )
    if nav == "Методология":
        methodology()
    elif nav == "Доступ":
        administration(auth, token)
    elif nav == "История":
        library_view(reuse_record, navigate)
    elif nav == "Сравнение":
        st.title("Сравнение запусков")
        st.caption("Сопоставьте два исследования: предложения, условия, результаты и покрытие сегментов.")
        comparison_view(st.session_state.history)
    else:
        render_constructor(key, settings, user.id)
    markup(
        '<div class="footer">Двойник · MISIS X · Академия Финтеха 2026<br>Синтетические ответы помогают формулировать гипотезы. Решения о запуске подтверждаются на живой аудитории.</div>'
    )
