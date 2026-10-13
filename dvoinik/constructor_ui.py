"""Страница конструктора: редактор, запуск и отображение снимка результата."""

from __future__ import annotations

import streamlit as st

from .auth import AccessExpired
from .auth_ui import expire_access
from .editor_ui import render_editor
from .experiments import format_timestamp, normalize_scenario
from .presentation import escape, markup, section
from .reporting import signature
from .runs import RunSettings, run_experiment
from .scenarios import SCENARIOS
from .settings import model_identity
from .ui import persist_record, show_report


@st.cache_data(show_spinner=False)
def sample_record(key, owner_id):
    record = run_experiment(key, SCENARIOS[key], RunSettings())
    record["sample"] = True
    return record


def render_constructor(key: str, settings: RunSettings, owner_id: str):
    n, mock, seed = settings.n, settings.mock, settings.seed
    scenario = render_editor(key, n)
    error = None
    try:
        normalize_scenario(scenario)
    except ValueError as exc:
        error = str(exc)
    left, right = st.columns([2.5, 1], vertical_alignment="center")
    with left:
        markup(
            '<div class="launch-readiness"><strong>'
            + ("Проверьте настройки" if error else "Готово к запуску")
            + "</strong><span>"
            + escape(
                f"{n} двойников · {len(scenario['variants'])} {'предложения' if len(scenario['variants']) < 5 else 'предложений'} · {n * len(scenario['variants'])} оценок"
            )
            + "</span></div>"
        )
    run = right.button("Запустить эксперимент", type="primary", key="run_experiment", width="stretch")
    if error:
        st.warning(error)
    if run and error:
        st.error("Не удалось запустить эксперимент: " + error)
    elif run:
        bar = st.progress(0, text="Готовим цифровых двойников…")
        try:
            record = run_experiment(
                key,
                scenario,
                settings,
                guard=st.session_state.experiment_store.guard,
                progress=lambda done, total: bar.progress(
                    done / total, text=f"Оценено {done} из {total} предложений"
                ),
            )
            st.session_state.active_record = record
            if persist_record(record):
                st.success("Эксперимент завершён. Настройки и результаты сохранены в локальном архиве.")
        except AccessExpired:
            expire_access()
        except (ValueError, OSError) as exc:
            st.error(f"Не удалось запустить эксперимент: {exc}")
        finally:
            bar.empty()
    active = st.session_state.get("active_record")
    if not active or active["scenario_key"] != key:
        active = None if key == "custom" else sample_record(key, owner_id)
        st.session_state.active_record = active
    if active is None:
        st.info(
            "Заполните предложения, выберите аудиторию и запустите свой первый эксперимент. Результаты появятся здесь."
        )
        st.session_state.results_stale = False
        return
    _, config_model = model_identity(mock)
    try:
        current_scenario = normalize_scenario(scenario)
    except ValueError:
        current_scenario = scenario
    stale = active["signature"] != signature(current_scenario, n, mock, int(seed), config_model)
    st.session_state.results_stale = stale
    if active["sample"]:
        st.info(
            "Ниже — демонстрационный отчёт: 200 двойников, исходные предложения, эвристическая модель. Запустите эксперимент, чтобы получить результат с вашими настройками."
        )
    elif stale:
        st.warning(
            "Настройки изменились. Ниже сохранён результат предыдущего запуска; запустите эксперимент заново, чтобы проверить новое предложение."
        )
    stamp = format_timestamp(active["created_at"])
    section(
        "Результаты эксперимента",
        ("Демонстрационный пример" if active["sample"] else stamp) + " · " + active["model"],
    )
    show_report(active)
