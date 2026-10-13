"""Двойник: лаборатория синтетических клиентов. streamlit run app.py"""

from __future__ import annotations

import copy
import os
import time
import uuid
from pathlib import Path

import streamlit as st

from dvoinik.engine import simulate
from dvoinik.experiments import CUSTOM_SCENARIO, format_timestamp, load_experiment, normalize_scenario
from dvoinik.population import SEGMENTS, build_population
from dvoinik.reporting import export_json, make_record, signature
from dvoinik.scenarios import SCENARIOS
from dvoinik.storage import KEEP_VALIDATION, ExperimentStore, StorageError
from dvoinik.ui import comparison_view, escape, markup, methodology, persist_record, section, show_report

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
st.session_state.setdefault("history", [])
st.session_state.setdefault("pending_records", {})
st.session_state.setdefault("pending_validation_bases", {})
st.session_state.experiment_store = ExperimentStore(
    os.getenv("DVOINIK_STORAGE_PATH", str(ROOT / ".data" / "experiments.sqlite3"))
)
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
    st.session_state.history = st.session_state.experiment_store.list_records()
    active = st.session_state.get("active_record")
    if active:
        st.session_state.active_record = next(
            (r for r in st.session_state.history if r["id"] == active["id"]), active
        )
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


@st.cache_data(show_spinner=False)
def sample_record(key):
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


def remember_offer(input_key):
    st.session_state.saved_inputs[input_key] = st.session_state[input_key]


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
        key = st.selectbox(
            "Сценарий", [*SCENARIOS, "custom"], format_func=lambda k: TITLES[k], key="scenario_key"
        )
        sizes = sorted({50, 100, 200, 500, 1000, st.session_state.population_n})
        n = st.select_slider("Размер аудитории", sizes, key="population_n")
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
    st.caption("Запуски и проверки опросом сохраняются на этом сервере и доступны после перезапуска.")
    with st.expander("Сравнить два запуска"):
        comparison_view(st.session_state.history)
    with st.expander("Открыть сохранённый эксперимент"):
        st.caption(
            "Загрузите полный JSON-отчёт Двойника. Настройки и проверка опросом восстановятся вместе с результатами."
        )
        uploaded = st.file_uploader("JSON эксперимента", type=["json"], max_upload_size=5, key="import_file")
        if st.button("Добавить в историю", key="import_record", disabled=uploaded is None):
            try:
                imported = load_experiment(uploaded.getvalue())
                imported["import_origin_id"] = imported["id"]
                imported["id"] = uuid.uuid4().hex[:10]
                saved = persist_record(imported)
                st.session_state.history_view = imported["id"]
                message = "Эксперимент открыт. Числа отчёта проверены."
                if imported.get("validation"):
                    message += " Метрики опроса пересчитаны по сохранённым ответам."
                else:
                    message += " Проверки живым опросом в этом файле нет."
                if saved:
                    st.success(message)
            except ValueError as exc:
                st.error(f"Не удалось открыть эксперимент: {exc}")
    if not st.session_state.history:
        st.info(
            "Здесь появятся запущенные эксперименты. Откройте раздел «Эксперимент» и запустите исследование."
        )
    for record in reversed(st.session_state.history):
        stamp = format_timestamp(record["created_at"])
        with st.expander(
            f"{record['id']} · {record['scenario']['title']} · {stamp} · {record['n']} двойников"
        ):
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
            st.button(
                "Использовать как основу",
                key=f"history_reuse_{record['id']}",
                on_click=reuse_record,
                args=(record,),
            )
    chosen = st.session_state.get("history_view")
    viewed = next((r for r in st.session_state.history if r["id"] == chosen), None)
    if viewed:
        section("Сохранённый эксперимент", viewed["scenario"]["title"])
        show_report(viewed)
else:
    source = CUSTOM_SCENARIO if key == "custom" else SCENARIOS[key]
    st.title(st.session_state.get("title_custom", source["title"]) if key == "custom" else TITLES[key])
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
    with st.expander("Настроить гипотезу, предложения и аудиторию", expanded=key == "custom"):
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
            except (ValueError, OSError) as exc:
                st.error(f"Не удалось запустить эксперимент: {exc}")
            finally:
                bar.empty()
    active = st.session_state.get("active_record")
    if not active or active["scenario_key"] != key:
        active = None if key == "custom" else sample_record(key)
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
