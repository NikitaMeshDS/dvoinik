"""Редактор предложений и предварительный состав аудитории."""

from __future__ import annotations

import copy
import os

import pandas as pd
import streamlit as st

from .draft_ui import remember_offer
from .experiments import CUSTOM_SCENARIO, normalize_population
from .population import SEGMENTS, allocate_population
from .presentation import markup
from .runs import RunSettings
from .scenarios import SCENARIOS

TITLES = {
    "custom": "Собственный сценарий",
    "student_card": "Студенческая карта",
    "family_budget": "Семейный счёт",
    "credit_card": "Кредитная карта",
    "senior_deposit": "Вклад для пенсионеров",
    "push_cashback": "Пуш о кэшбэке",
    "self_employed": "Тариф для самозанятых",
    "nonresident_transfer": "Переводы для нерезидентов",
}


def workspace_settings(*, demo=False):
    with st.container(border=True, key="research_settings"):
        st.subheader("Настройки исследования")
        scenario_col, audience_col, mode_col = st.columns([1.5, 1.3, 1])
        with scenario_col:
            key = st.selectbox(
                "Сценарий", [*SCENARIOS, "custom"], format_func=lambda k: TITLES[k], key="scenario_key"
            )
        with audience_col:
            sizes = sorted({50, 100, 200, 500, 1000, st.session_state.population_n})
            n = st.select_slider("Размер аудитории", sizes, key="population_n")
        with mode_col:
            mock = st.toggle("Демо без LLM", key="mock_mode", disabled=demo)
            if mock:
                st.caption("Демо включено · без внешних запросов")
            else:
                st.caption("Модель: " + os.getenv("LLM_MODEL", "qwen2.5:7b-instruct"))
                st.caption("Модель и подключение настраивает администратор сервера.")
        with st.expander("Параметры запуска"):
            seed_col, concurrency_col = st.columns(2)
            seed = seed_col.number_input(
                "Seed популяции и демо", min_value=0, max_value=999999, step=1, key="seed"
            )
            concurrency = concurrency_col.number_input(
                "Параллельных запросов LLM", min_value=1, max_value=64, step=1, key="concurrency"
            )
    return key, RunSettings(n=n, mock=mock, seed=int(seed), concurrency=int(concurrency))


def render_editor(key, n):
    source = CUSTOM_SCENARIO if key == "custom" else SCENARIOS[key]
    st.title(st.session_state.get("title_custom", source["title"]) if key == "custom" else TITLES[key])
    st.caption(source["description"])
    markup(
        '<div class="preparation-flow"><span><b>1</b>Сформулируйте гипотезу</span><span><b>2</b>Сравните предложения</span><span><b>3</b>Задайте аудиторию</span></div>'
    )
    scenario = copy.deepcopy(source)
    defaults = {f"question_{key}": source["question"]}
    defaults.update({f"variant_{key}_{vid}": text for vid, text in source["variants"].items()})
    defaults.update(
        {f"weight_{key}_{sid}": round(weight * 100) for sid, weight in source["population"].items()}
    )
    if key == "custom":
        defaults.update(
            {
                "title_custom": source["title"],
                "description_custom": source["description"],
                "variant_count_custom": 2,
                "objections_custom": "\n".join(source["objections"]),
            }
        )
        defaults.update({f"variant_custom_{vid}": "" for vid in "ABCDE"})
        defaults.update(
            {f"weight_custom_{sid}": float(source["population"].get(sid, 0) * 100) for sid in SEGMENTS}
        )
    for input_key, input_value in defaults.items():
        st.session_state.setdefault(input_key, input_value)
    with st.expander("Настроить гипотезу, предложения и аудиторию", expanded=True):
        setup = st.tabs(["Предложения", "Состав аудитории"])
        with setup[0]:
            if key == "custom":
                scenario["title"] = st.text_input("Название эксперимента", max_chars=200, key="title_custom")
                scenario["description"] = st.text_area(
                    "Контекст исследования", max_chars=4000, height=80, key="description_custom"
                )
                count = st.number_input(
                    "Вариантов предложения", min_value=2, max_value=5, step=1, key="variant_count_custom"
                )
                scenario["variants"] = {vid: "" for vid in "ABCDE"[:count]}
            scenario["question"] = st.text_input("Вопрос двойникам", key=f"question_{key}")
            variant_ids = list(scenario["variants"])
            for start in range(0, len(variant_ids), 3):
                for col, vid in zip(
                    st.columns(min(3, len(variant_ids) - start)), variant_ids[start : start + 3]
                ):
                    with col:
                        input_key = f"variant_{key}_{vid}"
                        if key == "custom" and input_key in st.session_state.saved_inputs:
                            st.session_state[input_key] = st.session_state.saved_inputs[input_key]
                        markup(
                            f'<div class="editor-variant variant-{vid}"><span>{vid}</span><strong>Предложение {vid}</strong></div>'
                        )
                        scenario["variants"][vid] = st.text_area(
                            f"Вариант {vid}",
                            height=150,
                            max_chars=3000,
                            key=input_key,
                            label_visibility="collapsed",
                            on_change=remember_offer,
                            args=(input_key,),
                        )
            if key == "custom":
                reasons = st.text_area(
                    "Категории отказа — одна на строку", max_chars=1500, height=120, key="objections_custom"
                )
                scenario["objections"] = [line.strip() for line in reasons.splitlines() if line.strip()]
        with setup[1]:
            st.caption(
                "Измените относительные доли сегментов. Сумма нормируется при запуске; нулевая доля исключает сегмент."
            )
            weights = {}
            for sid in SEGMENTS if key == "custom" else source["population"]:
                if key == "custom":
                    weights[sid] = st.number_input(
                        SEGMENTS[sid]["name"],
                        min_value=0.0,
                        max_value=100.0,
                        step=1.0,
                        format="%.2f",
                        key=f"weight_custom_{sid}",
                    )
                else:
                    weights[sid] = st.slider(SEGMENTS[sid]["name"], 0, 100, key=f"weight_{key}_{sid}")
            scenario["population"] = {sid: value for sid, value in weights.items() if value > 0}
            total_weight = sum(weights.values())
            if total_weight:
                st.caption(
                    "Фактические доли: "
                    + "; ".join(
                        f"{SEGMENTS[s]['name']}: {v / total_weight:.0%}" for s, v in weights.items() if v
                    )
                )

                counts = allocate_population(n, normalize_population(scenario["population"]))
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Сегмент": SEGMENTS[sid]["name"],
                                "Доля аудитории": count / n,
                                "Двойников": count,
                            }
                            for sid, count in counts.items()
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Доля аудитории": st.column_config.ProgressColumn(
                            format="percent", min_value=0, max_value=1
                        )
                    },
                )
                st.caption(
                    "Число двойников учитывает округление долей. Эти профили будут использованы для каждого предложения."
                )
                if any(count == 0 for count in counts.values()):
                    st.warning(
                        "В некоторых выбранных сегментах нет двойников. Увеличьте размер аудитории или долю сегмента."
                    )
            else:
                st.warning("Выберите хотя бы один сегмент с ненулевой долей.")
    for input_key in [*defaults, "scenario_key", "population_n", "mock_mode", "seed", "concurrency"]:
        if (
            key == "custom"
            and input_key.startswith("variant_custom_")
            and input_key[-1] not in scenario["variants"]
        ):
            continue
        st.session_state.saved_inputs[input_key] = st.session_state[input_key]
    return scenario
