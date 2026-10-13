"""Двойник: лаборатория синтетических клиентов. streamlit run app.py"""

from __future__ import annotations

import copy
import os
import time
from pathlib import Path

import streamlit as st

from dvoinik.auth import AccessExpired
from dvoinik.auth_ui import account_sidebar, administration, expire_access, require_access
from dvoinik.engine import simulate
from dvoinik.experiments import CUSTOM_SCENARIO, format_timestamp, normalize_scenario
from dvoinik.library import library_view
from dvoinik.population import SEGMENTS, build_population
from dvoinik.reporting import make_record, signature
from dvoinik.scenarios import SCENARIOS
from dvoinik.storage import KEEP_VALIDATION, StorageError
from dvoinik.ui import comparison_view, escape, markup, methodology, persist_record, section, show_report
from serve import storage_path

ROOT = Path(__file__).parent
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

st.set_page_config(
    page_title="Двойник · лаборатория клиентов",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="auto",
)
markup(f"<style>{(ROOT / 'assets/style.css').read_text()}</style>")
mode = os.getenv("DVOINIK_AUTH_MODE", "local")
if mode not in {"local", "demo"}:
    st.error("Ошибка конфигурации доступа: DVOINIK_AUTH_MODE должен быть local или demo.")
    st.stop()
auth, token, user = require_access(storage_path(), mode)
st.session_state.setdefault("history", [])
st.session_state.setdefault("pending_records", {})
st.session_state.setdefault("pending_validation_bases", {})
st.session_state.experiment_store = auth.workspace(token)
try:
    archived = st.session_state.experiment_store.list_records()
    archived_ids = {r["id"] for r in archived}
    # Подхватываем результаты уже открытой сессии при обновлении приложения.
    pending = {r["id"]: r for r in st.session_state.history if r["id"] not in archived_ids}
    pending.update(st.session_state.pending_records)
    for existing in pending.values():
        st.session_state.experiment_store.save(
            existing,
            expected_validation=st.session_state.pending_validation_bases.get(
                existing["id"], KEEP_VALIDATION
            ),
        )
        st.session_state.pending_records.pop(existing["id"], None)
        st.session_state.pending_validation_bases.pop(existing["id"], None)
    st.session_state.history = st.session_state.experiment_store.list_records() if pending else archived
    active = st.session_state.get("active_record")
    if active:
        st.session_state.active_record = next(
            (r for r in st.session_state.history if r["id"] == active["id"]), active
        )
except AccessExpired:
    expire_access()
except (StorageError, ValueError) as exc:
    st.error(f"История на диске недоступна: {exc} Новые отчёты можно скачать из текущей сессии.")
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
if user.role == "demo":
    st.session_state.saved_inputs["mock_mode"] = True
    st.session_state.mock_mode = True


@st.cache_data(show_spinner=False)
def sample_record(key, owner_id):
    scenario = copy.deepcopy(SCENARIOS[key])
    twins = build_population(200, scenario["population"], seed=42)
    report = simulate(twins, scenario, mock=True, seed=42)
    return make_record(key, scenario, 200, True, 42, report, twins, sample=True)


def reuse_record(record):
    """Копирование снимка в новый черновик; callback выполняется до рендера виджетов."""
    scenario = normalize_scenario(record["scenario"])
    values = {
        "navigation": "Эксперимент",
        "scenario_key": "custom",
        "population_n": record["n"],
        "mock_mode": record["mock"],
        "seed": record["seed"],
        "title_custom": scenario["title"],
        "description_custom": scenario["description"],
        "question_custom": scenario["question"],
        "variant_count_custom": len(scenario["variants"]),
        "objections_custom": "\n".join(scenario["objections"]),
    }
    values.update({f"variant_custom_{vid}": text for vid, text in scenario["variants"].items()})
    values.update({f"weight_custom_{sid}": weight * 100 for sid, weight in scenario["population"].items()})
    for sid in SEGMENTS:
        values.setdefault(f"weight_custom_{sid}", 0.0)
    for input_key, value in values.items():
        st.session_state[input_key] = value
        if input_key != "navigation":
            st.session_state.saved_inputs[input_key] = value
    st.session_state.active_record = None
    st.session_state.history_view = None


def remember_offer(input_key):
    st.session_state.saved_inputs[input_key] = st.session_state[input_key]


def navigate(page):
    st.session_state.navigation = page


NAV_LABELS = {
    "Эксперимент": "Конструктор",
    "История": "Исследования",
    "Сравнение": "Сравнение",
    "Методология": "Методология",
}
if user.role == "admin":
    NAV_LABELS["Доступ"] = "Доступ команды"
st.session_state.setdefault("navigation", "История" if st.session_state.history else "Эксперимент")


with st.sidebar:
    markup(
        '<div class="brand"><span class="brand-mark"></span><span class="brand-name">двойник</span></div>'
        '<p class="brand-sub">Лаборатория клиентов</p>'
    )
    nav = st.radio(
        "Рабочее пространство",
        list(NAV_LABELS),
        format_func=lambda value: NAV_LABELS[value],
        key="navigation",
        label_visibility="collapsed",
    )
    st.divider()
    if nav == "Эксперимент":
        st.caption("Настройки исследования")
        key = st.selectbox(
            "Сценарий", [*SCENARIOS, "custom"], format_func=lambda k: TITLES[k], key="scenario_key"
        )
        sizes = sorted({50, 100, 200, 500, 1000, st.session_state.population_n})
        n = st.select_slider("Размер аудитории", sizes, key="population_n")
        mock = st.toggle("Демо без подключения к LLM", key="mock_mode", disabled=user.role == "demo")
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
    account_sidebar(auth, token, user)

markup(
    '<div class="topline"><span><strong>Рабочее пространство</strong> / '
    + escape(NAV_LABELS[nav])
    + "</span>"
    '<span class="status-pill">Синтетическая аудитория</span></div>'
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
    source = CUSTOM_SCENARIO if key == "custom" else SCENARIOS[key]
    st.title(st.session_state.get("title_custom", source["title"]) if key == "custom" else TITLES[key])
    st.caption(source["description"])
    markup(
        '<div class="experiment-brief"><strong>Гипотеза → предложения → аудитория</strong>'
        "<p>Подготовьте варианты, запустите симуляцию и сохраните результат для проверки опросом.</p></div>"
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
                        scenario["variants"][vid] = st.text_area(
                            f"Вариант {vid}",
                            height=150,
                            max_chars=3000,
                            key=input_key,
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
    left, right = st.columns([2.5, 1], vertical_alignment="center")
    with left:
        st.caption(
            f"{n} двойников · {len(scenario['variants'])} {'варианта' if len(scenario['variants']) < 5 else 'вариантов'} · {n * len(scenario['variants'])} ответов"
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
                scenario = normalize_scenario(scenario)
                twins = build_population(n, scenario["population"], seed=int(seed))

                def progress(done, total):
                    st.session_state.experiment_store.guard()
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
        active = None if key == "custom" else sample_record(key, user.id)
        st.session_state.active_record = active
    if active is None:
        st.info(
            "Заполните предложения, выберите аудиторию и запустите свой первый эксперимент. Результаты появятся здесь."
        )
        st.session_state.results_stale = False
        st.stop()
    config_model = (
        None
        if mock
        else os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
        + "|"
        + os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    )
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

markup(
    '<div class="footer">Двойник · MISIS X · Академия Финтеха 2026<br>Синтетические ответы помогают формулировать гипотезы. Решения о запуске подтверждаются на живой аудитории.</div>'
)
