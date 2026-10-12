"""Двойник: лаборатория синтетических клиентов. streamlit run app.py"""

from __future__ import annotations

import copy
import os
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from dvoinik.engine import simulate
from dvoinik.population import SEGMENTS, build_population
from dvoinik.reporting import export_json, make_record, signature
from dvoinik.scenarios import SCENARIOS
from dvoinik.ui import escape, markup, methodology, section, show_report

ROOT = Path(__file__).parent
TITLES = {
    "student_card": "Студенческая карта",
    "family_budget": "Семейный счёт",
    "credit_card": "Кредитная карта",
    "senior_deposit": "Вклад для пенсионеров",
    "push_cashback": "Пуш о кэшбэке",
    "self_employed": "Тариф для самозанятых",
    "nonresident_transfer": "Переводы для нерезидентов",
}

st.set_page_config(
    page_title="Двойник · лаборатория клиентов",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="auto",
)
markup(f"<style>{(ROOT / 'assets/style.css').read_text()}</style>")
st.session_state.setdefault("history", [])
st.session_state.setdefault(
    "saved_inputs",
    {
        "scenario_key": "student_card",
        "population_n": 200,
        "mock_mode": os.getenv("DVOINIK_MOCK", "1") == "1",
        "seed": 42,
        "concurrency": 16,
    },
)
# Streamlit удаляет state скрытых виджетов. Черновики живут независимо от виджетов.
for input_key, input_value in st.session_state.saved_inputs.items():
    st.session_state.setdefault(input_key, input_value)


@st.cache_data(show_spinner=False)
def sample_record(key):
    scenario = copy.deepcopy(SCENARIOS[key])
    twins = build_population(200, scenario["population"], seed=42)
    report = simulate(twins, scenario, mock=True, seed=42)
    return make_record(key, scenario, 200, True, 42, report, twins, sample=True)


with st.sidebar:
    markup(
        '<div class="brand"><span class="brand-mark"></span><span class="brand-name">двойник</span></div>'
        '<p class="brand-sub">Лаборатория клиентов</p>'
    )
    nav = st.radio(
        "Рабочее пространство",
        ["Эксперимент", "История", "Методология"],
        key="navigation",
        label_visibility="collapsed",
    )
    st.divider()
    if nav == "Эксперимент":
        st.caption("Настройки исследования")
        key = st.selectbox("Сценарий", list(SCENARIOS), format_func=lambda k: TITLES[k], key="scenario_key")
        n = st.select_slider("Размер аудитории", [50, 100, 200, 500, 1000], key="population_n")
        mock = st.toggle("Демо без подключения к LLM", key="mock_mode")
        if mock:
            st.caption("Эвристические ответы · без внешних запросов")
        else:
            st.caption("Модель: " + os.getenv("LLM_MODEL", "qwen2.5:7b-instruct"))
            st.caption("Подключение задаётся LLM_BASE_URL и LLM_API_KEY в окружении сервера.")
        with st.expander("Параметры запуска"):
            seed = st.number_input("Seed популяции и демо", min_value=0, max_value=999999, step=1, key="seed")
            concurrency = st.number_input(
                "Параллельных запросов LLM", min_value=1, max_value=64, step=1, key="concurrency"
            )
    markup(
        '<div class="sidebar-note">Проверяйте гипотезы до запуска.<br>Синтетическая аудитория помогает подготовить живое исследование.</div>'
    )

markup(
    '<div class="topline"><span><strong>Рабочее пространство</strong> / ' + escape(nav) + "</span>"
    '<span class="status-pill">Синтетическая аудитория</span></div>'
)

if nav == "Методология":
    methodology()
elif nav == "История":
    st.title("История экспериментов")
    st.caption("До 20 последних запусков в текущей сессии. Скачайте отчёт, чтобы сохранить исследование.")
    if not st.session_state.history:
        st.info(
            "Здесь появятся запущенные эксперименты. Откройте раздел «Эксперимент» и запустите исследование."
        )
    for record in reversed(st.session_state.history):
        stamp = datetime.fromisoformat(record["created_at"]).strftime("%d.%m.%Y %H:%M МСК")
        with st.expander(f"{TITLES[record['scenario_key']]} · {stamp} · {record['n']} двойников"):
            st.caption(f"{'Демо' if record['mock'] else 'LLM'} · {record['model']} · Seed {record['seed']}")
            st.download_button(
                "Скачать полный отчёт",
                export_json(record),
                f"dvoinik-{record['id']}.json",
                "application/json",
                key=f"history_export_{record['id']}",
            )
            if st.button("Открыть результаты", key=f"history_open_{record['id']}"):
                st.session_state.history_view = record["id"]
    chosen = st.session_state.get("history_view")
    viewed = next((r for r in st.session_state.history if r["id"] == chosen), None)
    if viewed:
        section("Сохранённый эксперимент", TITLES[viewed["scenario_key"]])
        show_report(viewed)
else:
    source = SCENARIOS[key]
    st.title(TITLES[key])
    st.caption(source["description"])
    markup(
        '<div class="hero"><h2>Узнайте, что откликается вашей аудитории</h2>'
        "<p>Сравните предложения на цифровых двойниках клиентов. Найдите различия между сегментами и барьеры, которые стоит проверить до пилота.</p>"
        '<svg viewBox="0 0 260 190" aria-hidden="true"><g stroke="#aec3ec" stroke-width="1.2" fill="none">'
        '<path d="M38 93L97 48L157 87L220 48M38 93L98 137L157 87L218 141M97 48L98 137M220 48L218 141M98 137L218 141"/>'
        '</g><g fill="#d5e1f7"><circle cx="38" cy="93" r="20"/><circle cx="97" cy="48" r="20"/>'
        '<circle cx="98" cy="137" r="20"/><circle cx="220" cy="48" r="20"/><circle cx="218" cy="141" r="20"/></g>'
        '<circle cx="157" cy="87" r="29" fill="#295bde"/><g fill="#7d9cd7"><circle cx="38" cy="87" r="5"/>'
        '<path d="M28 101Q38 88 48 101"/><circle cx="97" cy="42" r="5"/><path d="M87 56Q97 43 107 56"/>'
        '<circle cx="98" cy="131" r="5"/><path d="M88 145Q98 132 108 145"/><circle cx="220" cy="42" r="5"/>'
        '<path d="M210 56Q220 43 230 56"/><circle cx="218" cy="135" r="5"/><path d="M208 149Q218 136 228 149"/></g>'
        '<g fill="#fff"><circle cx="157" cy="78" r="7"/><path d="M143 99Q157 79 171 99"/></g></svg></div>'
    )
    scenario = copy.deepcopy(source)
    defaults = {f"question_{key}": source["question"]}
    defaults.update({f"variant_{key}_{vid}": text for vid, text in source["variants"].items()})
    defaults.update(
        {f"weight_{key}_{sid}": round(weight * 100) for sid, weight in source["population"].items()}
    )
    for input_key, input_value in defaults.items():
        st.session_state.setdefault(input_key, input_value)
    with st.expander("Настроить гипотезу, предложения и аудиторию"):
        setup = st.tabs(["Предложения", "Состав аудитории"])
        with setup[0]:
            scenario["question"] = st.text_input("Вопрос двойникам", key=f"question_{key}")
            for col, (vid, text) in zip(st.columns(len(source["variants"])), source["variants"].items()):
                with col:
                    scenario["variants"][vid] = st.text_area(
                        f"Вариант {vid}", height=150, max_chars=3000, key=f"variant_{key}_{vid}"
                    )
        with setup[1]:
            st.caption(
                "Измените относительные доли сегментов. Сумма нормируется при запуске; нулевая доля исключает сегмент."
            )
            weights = {}
            for sid, weight in source["population"].items():
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
            else:
                st.warning("Выберите хотя бы один сегмент с ненулевой долей.")
    for input_key in [*defaults, "scenario_key", "population_n", "mock_mode", "seed", "concurrency"]:
        st.session_state.saved_inputs[input_key] = st.session_state[input_key]
    left, right = st.columns([2.5, 1], vertical_alignment="center")
    with left:
        st.caption(
            f"{n} двойников · {len(scenario['variants'])} варианта · {n * len(scenario['variants'])} ответов"
        )
    run = right.button("Запустить эксперимент", type="primary", key="run_experiment", width="stretch")
    if run:
        if not scenario["question"].strip() or any(
            not text.strip() for text in scenario["variants"].values()
        ):
            st.error("Заполните вопрос и текст каждого предложения перед запуском.")
        elif not scenario["population"]:
            st.error("Выберите хотя бы один сегмент аудитории.")
        else:
            bar = st.progress(0, text="Готовим цифровых двойников…")
            started = time.perf_counter()
            try:
                twins = build_population(n, scenario["population"], seed=int(seed))

                def progress(done, total):
                    bar.progress(done / total, text=f"Оценено {done} из {total} предложений")

                report = simulate(
                    twins,
                    scenario,
                    mock=mock,
                    seed=int(seed),
                    concurrency=int(concurrency),
                    progress=progress,
                )
                record = make_record(
                    key, scenario, n, mock, int(seed), report, twins, time.perf_counter() - started
                )
                st.session_state.active_record = record
                st.session_state.history = (st.session_state.history + [record])[-20:]
                st.success("Эксперимент завершён. Настройки и результаты сохранены в истории сессии.")
            except (ValueError, OSError) as exc:
                st.error(f"Не удалось запустить эксперимент: {exc}")
            finally:
                bar.empty()
    active = st.session_state.get("active_record")
    if not active or active["scenario_key"] != key:
        active = sample_record(key)
        st.session_state.active_record = active
    config_model = (
        None
        if mock
        else os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
        + "|"
        + os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    )
    stale = active["signature"] != signature(scenario, n, mock, int(seed), config_model)
    st.session_state.results_stale = stale
    if active["sample"]:
        st.info(
            "Ниже — демонстрационный отчёт: 200 двойников, исходные предложения, эвристическая модель. Запустите эксперимент, чтобы получить результат с вашими настройками."
        )
    elif stale:
        st.warning(
            "Настройки изменились. Ниже сохранён результат предыдущего запуска; запустите эксперимент заново, чтобы проверить новое предложение."
        )
    stamp = datetime.fromisoformat(active["created_at"]).strftime("%d.%m.%Y %H:%M МСК")
    section(
        "Результаты эксперимента",
        ("Демонстрационный пример" if active["sample"] else stamp) + " · " + active["model"],
    )
    show_report(active)

markup(
    '<div class="footer">Двойник · MISIS X · Академия Финтеха 2026<br>Синтетические ответы помогают формулировать гипотезы. Решения о запуске подтверждаются на живой аудитории.</div>'
)
