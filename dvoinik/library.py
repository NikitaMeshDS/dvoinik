"""Каталог исследований: поиск, просмотр и быстрый переход к повторному запуску."""

from __future__ import annotations

import uuid
from datetime import datetime

import streamlit as st

from .download_ui import download
from .experiments import format_timestamp, load_experiment, quality_status
from .reporting import export_json
from .ui import escape, markup, persist_record, show_report

PAGE_SIZE = 8


def _open(record_id):
    st.session_state.history_view = record_id


def _back():
    st.session_state.history_view = None


def _reset_page():
    st.session_state.library_page = 1


def filter_records(history, query, mode, survey):
    needle = query.strip().casefold()
    selected = []
    for record in history:
        if mode != "all" and record["mock"] != (mode == "demo"):
            continue
        if survey != "all" and bool(record.get("validation")) != (survey == "has"):
            continue
        scenario = record["scenario"]
        haystack = " ".join(
            [
                record["id"],
                record["model"],
                scenario["title"],
                scenario["description"],
                scenario["question"],
                *scenario["variants"].values(),
            ]
        ).casefold()
        if not needle or needle in haystack:
            selected.append(record)
    return sorted(selected, key=lambda r: (datetime.fromisoformat(r["created_at"]), r["id"]), reverse=True)


def _summary(history):
    values = [
        ("Сохранено исследований", len(history)),
        ("Запусков на LLM", sum(not r["mock"] for r in history)),
        ("С загруженным опросом", sum(bool(r.get("validation")) for r in history)),
    ]
    markup(
        '<div class="library-summary">'
        + "".join(
            f"<div><strong>{value}</strong><span>{escape(label)}</span></div>" for label, value in values
        )
        + "</div>"
    )


def _import_view():
    with st.expander("Импорт исследования из JSON", icon=":material/upload_file:"):
        st.caption("Откройте полный отчёт Двойника: предложения, аудитория и сохранённая проверка опросом.")
        uploaded = st.file_uploader("JSON эксперимента", type=["json"], max_upload_size=5, key="import_file")
        if st.button("Импортировать исследование", key="import_record", disabled=uploaded is None):
            try:
                imported = load_experiment(uploaded.getvalue())
                imported["import_origin_id"] = imported["id"]
                imported["id"] = uuid.uuid4().hex[:10]
                persist_record(imported)
                st.session_state.history_view = imported["id"]
                st.rerun()
            except ValueError as exc:
                st.error(f"Не удалось открыть эксперимент: {exc}")


def _record_row(record, reuse_record):
    scenario = record["scenario"]
    validation = record.get("validation")
    count = validation["result"]["survey_n"] if validation else 0
    badge = "Демо" if record["mock"] else "LLM"
    status = quality_status(record)
    with st.container(border=True):
        markup(
            f'<div class="study-head"><h3>{escape(scenario["title"])}</h3>'
            f'<span class="study-mode {"demo" if record["mock"] else "llm"}">{badge}</span></div>'
            f'<p class="study-question">{escape(scenario["question"])}</p>'
            '<div class="study-facts">'
            f"<span><strong>{record['n']}</strong> двойников</span>"
            f"<span><strong>{len(scenario['variants'])}</strong> {'предложения' if len(scenario['variants']) < 5 else 'предложений'}</span>"
            f"<span>{f'Опрос: {count} ответов' if validation else 'Опрос не загружен'}</span>"
            "</div>"
        )
        st.caption(f"{format_timestamp(record['created_at'])} · {record['model']} · {record['id']}")
        if status["kind"] in {"incomplete", "partial_validation"}:
            st.caption(status["title"])
        columns = st.columns([1.2, 1.4, 1])
        columns[0].button(
            "Открыть отчёт",
            key=f"history_open_{record['id']}",
            on_click=_open,
            args=(record["id"],),
            width="stretch",
        )
        columns[1].button(
            "Использовать как основу",
            key=f"history_reuse_{record['id']}",
            on_click=reuse_record,
            args=(record,),
            width="stretch",
        )
        download(
            "JSON отчёта",
            export_json(record),
            f"dvoinik-{record['id']}.json",
            "application/json",
            key=f"history_export_{record['id']}",
            target=columns[2],
            width="stretch",
        )


def library_view(reuse_record, navigate):
    history = st.session_state.history
    chosen = st.session_state.get("history_view")
    viewed = next((r for r in history if r["id"] == chosen), None)
    if viewed:
        st.button(
            "Вернуться к исследованиям", key="library_back", on_click=_back, icon=":material/arrow_back:"
        )
        st.title(viewed["scenario"]["title"])
        st.caption(f"{format_timestamp(viewed['created_at'])} · {viewed['model']} · {viewed['id']}")
        st.button(
            "Использовать как основу",
            key=f"history_reuse_{viewed['id']}",
            on_click=reuse_record,
            args=(viewed,),
        )
        show_report(viewed)
        return
    heading, action = st.columns([2.8, 1], vertical_alignment="center")
    heading.title("Исследования")
    action.button(
        "Открыть конструктор",
        key="library_new",
        type="primary",
        width="stretch",
        on_click=navigate,
        args=("Эксперимент",),
    )
    st.caption("Предложения, результаты и проверки опросом. Ваш архив сохраняется между сессиями.")
    _summary(history)
    st.button(
        "Сравнить запуски",
        key="library_compare",
        on_click=navigate,
        args=("Сравнение",),
        disabled=len(history) < 2,
    )
    _import_view()
    if not history:
        st.info(
            "Пока нет исследований. Откройте конструктор, настройте предложения и запустите эксперимент или импортируйте JSON."
        )
        return
    saved = st.session_state.setdefault("library_filters", {})
    for key, value in saved.items():
        st.session_state.setdefault(key, value)
    columns = st.columns([2, 1, 1])
    query = columns[0].text_input(
        "Найти исследование",
        placeholder="Название, предложение или ID",
        key="library_query",
        on_change=_reset_page,
    )
    mode = columns[1].selectbox(
        "Режим",
        ["all", "llm", "demo"],
        format_func=lambda value: {"all": "Все режимы", "llm": "LLM", "demo": "Демо"}[value],
        key="library_mode",
        on_change=_reset_page,
    )
    survey = columns[2].selectbox(
        "Проверка опросом",
        ["all", "has", "none"],
        format_func=lambda value: {"all": "Все исследования", "has": "Есть опрос", "none": "Нет опроса"}[
            value
        ],
        key="library_survey",
        on_change=_reset_page,
    )
    records = filter_records(history, query, mode, survey)
    pages = max(1, (len(records) + PAGE_SIZE - 1) // PAGE_SIZE)
    if st.session_state.get("library_page", 1) > pages:
        st.session_state.library_page = 1
    count, pagination = st.columns([3, 1], vertical_alignment="center")
    count.caption(f"Найдено {len(records)} из {len(history)}. Сначала последние запуски.")
    page = pagination.selectbox("Страница", list(range(1, pages + 1)), key="library_page")
    for key in ["library_query", "library_mode", "library_survey", "library_page"]:
        saved[key] = st.session_state[key]
    if not records:
        st.info("Нет исследований с такими условиями. Измените запрос или фильтры.")
    for record in records[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]:
        _record_row(record, reuse_record)
