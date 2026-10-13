"""Представление отчёта: графики, отзывы, валидация и методология."""

from __future__ import annotations

import html
import io

import altair as alt
import pandas as pd
import streamlit as st

from .experiments import attach_validation, format_timestamp, quality_status
from .population import SEGMENTS
from .reporting import export_csv, export_json, summarize
from .validate import load_survey

COLORS = ["#295BDE", "#36A28F", "#9980D8", "#D28B46", "#BB6092"]


def markup(text):
    st.markdown(text, unsafe_allow_html=True)


def escape(text):
    return html.escape(str(text))


def section(title, note=""):
    markup(f'<div class="section-line"><h2>{escape(title)}</h2><span>{escape(note)}</span></div>')


def offers(scenario):
    variants = list(scenario["variants"].items())
    for start in range(0, len(variants), 3):
        row = variants[start : start + 3]
        for col, (vid, text) in zip(st.columns(len(row)), row):
            with col:
                markup(
                    f'<div class="offer"><div class="offer-head"><span class="variant-letter">{escape(vid)}</span>'
                    f"Вариант {escape(vid)}</div><p>{escape(text)}</p></div>"
                )


def export_buttons(record, prefix="active"):
    name = f"dvoinik-{record['scenario_key']}-{record['id']}"
    cols = st.columns(2)
    cols[0].download_button(
        "Скачать отчёт JSON",
        export_json(record),
        name + ".json",
        mime="application/json",
        key=f"json_{prefix}",
        width="stretch",
    )
    cols[1].download_button(
        "Скачать сегменты CSV",
        "\ufeff" + export_csv(record),
        name + ".csv",
        mime="text/csv",
        key=f"csv_{prefix}",
        width="stretch",
    )


def overview(record):
    rep = record["report"]
    summary = summarize(rep)
    leaders = " / ".join(summary["leaders"])
    best_label = "Лидер симуляции" if len(summary["leaders"]) == 1 else "Равный результат"
    stats = [
        (best_label, f"{summary['best']:.0%}", f"Вариант {leaders}" if leaders else "Нет валидных ответов"),
        ("Отрыв от следующего", f"{summary['gap_pp']:.1f} п.п.", "Разница долей согласившихся"),
        (
            "Цифровых двойников",
            f"{record['n']:,}".replace(",", " "),
            f"{len(record['scenario']['population'])} сегм. в целевой аудитории",
        ),
        (
            "Вариантов предложения",
            str(len(rep)),
            f"{sum(r.get('n', 0) for r in rep.values())} валидных ответов",
        ),
    ]
    markup(
        '<div class="stat-grid">'
        + "".join(
            f'<div class="stat"><label>{escape(label)}</label><div class="value">{escape(value)}</div>'
            f"<small>{escape(note)}</small></div>"
            for label, value, note in stats
        )
        + "</div>"
    )
    if summary["failed_n"]:
        st.warning(
            f"{summary['failed_n']} запросов к модели не дали валидного ответа. Они исключены из конверсии; проверьте покрытие сегментов перед сравнением."
        )
        with st.expander("Ошибки модели и покрытие"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Вариант": v,
                            "Валидных": r["n"],
                            "Ошибок": r["failed_n"],
                            "Запрошено": r["requested_n"],
                        }
                        for v, r in rep.items()
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
            for message in dict.fromkeys(m for r in rep.values() for m in r.get("failure_examples", [])):
                st.write(message)
    return summary


def conversion_chart(rep):
    data = pd.DataFrame(
        [
            {
                "Вариант": f"Вариант {v}",
                "Конверсия": r["conversion"],
                "Ответов": r["n"],
                "Нижняя": r["confidence_interval"][0],
                "Верхняя": r["confidence_interval"][1],
            }
            for v, r in rep.items()
            if r["n"]
        ]
    )
    if data.empty:
        st.error("Нет валидных ответов. Проверьте подключение к модели и повторите эксперимент.")
        return
    base = alt.Chart(data).encode(
        y=alt.Y("Вариант:N", sort=None, title=None, axis=alt.Axis(labelFontSize=13))
    )
    bars = base.mark_bar(size=30, cornerRadiusEnd=5).encode(
        x=alt.X("Конверсия:Q", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%"), title=None),
        color=alt.Color(
            "Вариант:N", scale=alt.Scale(domain=[f"Вариант {v}" for v in "ABCDE"], range=COLORS), legend=None
        ),
        tooltip=[
            "Вариант:N",
            alt.Tooltip("Конверсия:Q", format=".1%"),
            "Ответов:Q",
            alt.Tooltip("Нижняя:Q", format=".1%"),
            alt.Tooltip("Верхняя:Q", format=".1%"),
        ],
    )
    rules = base.mark_rule(color="#18243e", strokeWidth=2).encode(x="Нижняя:Q", x2="Верхняя:Q")
    text = base.mark_text(align="left", dx=8, color="#18243e", fontWeight=600).encode(
        x="Верхняя:Q", text=alt.Text("Конверсия:Q", format=".0%")
    )
    chart = (
        (bars + rules + text)
        .properties(height=max(180, len(rep) * 60))
        .configure_view(stroke=None)
        .configure_axis(gridColor="#edf0f5", domain=False, tickColor="#e2e7f0", labelColor="#69758b")
    )
    st.altair_chart(chart, width="stretch")


def results_view(record, summary):
    rep, scenario = record["report"], record["scenario"]
    left, right = st.columns([1.45, 1], gap="large")
    with left:
        with st.container(border=True):
            st.subheader("Готовность подключить продукт")
            st.caption("Доля двойников, ответивших «да»")
            conversion_chart(rep)
            st.caption(
                "Линии — 95% интервалы Wilson для ответов симуляции. Они не измеряют точность прогноза реального спроса."
            )
    with right:
        with st.container(border=True):
            st.subheader("Что проверить дальше")
            if summary["leaders"]:
                leader = summary["leaders"][0]
                objections = rep[leader]["objections"]
                main = max(objections, key=objections.get) if objections else None
                if len(summary["leaders"]) > 1:
                    st.write(
                        "Несколько вариантов получили одинаковую долю согласий. Уточните различия на живой аудитории."
                    )
                else:
                    st.write(
                        f"Вариант {leader} получил больше согласий в этой симуляции. Возьмите его как кандидата для следующего исследования."
                    )
                if main:
                    st.markdown(f"**Основной барьер:** {main}.")
                    st.caption("Проверьте эту причину в интервью и уточните предложение перед A/B-тестом.")
                st.caption(
                    "Демо основано на правилах и ключевых словах. Это иллюстрация процесса исследования."
                    if record["mock"]
                    else "LLM-ответы — гипотезы о поведении. Сопоставьте результат с живым опросом."
                )
            else:
                st.write("Сначала получите валидные ответы модели.")
    section("Предложения в этом эксперименте", "Сохранённый снимок")
    offers(scenario)
    section("Различия по сегментам", "Наведение показывает число ответов")
    rows = [
        {"Сегмент": s["name"], "Вариант": v, "Конверсия": s["conversion"], "Ответов": s["n"]}
        for v, r in rep.items()
        for s in r["segments"].values()
    ]
    if rows:
        data = pd.DataFrame(rows)
        chart = (
            alt.Chart(data)
            .mark_bar(cornerRadiusEnd=3)
            .encode(
                y=alt.Y("Сегмент:N", title=None, sort=None, axis=alt.Axis(labelLimit=280)),
                x=alt.X("Конверсия:Q", title=None, scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
                yOffset="Вариант:N",
                color=alt.Color(
                    "Вариант:N",
                    scale=alt.Scale(domain=list("ABCDE"), range=COLORS),
                    legend=alt.Legend(orient="top"),
                ),
                tooltip=["Сегмент:N", "Вариант:N", alt.Tooltip("Конверсия:Q", format=".1%"), "Ответов:Q"],
            )
            .properties(height=max(180, len(scenario["population"]) * 90))
            .configure_view(stroke=None)
        )
        st.altair_chart(chart, width="stretch")
        with st.expander("Таблица конверсии и размеров выборок"):
            table = data.copy()
            table["Конверсия"] = table["Конверсия"].map(lambda x: f"{x:.1%}")
            st.dataframe(table, hide_index=True, width="stretch")
    section("Причины отказа", "Доля среди отказавшихся в каждом варианте")
    objection_rows = []
    for v, r in rep.items():
        no = r["n"] - r["yes"]
        for reason, count in r["objections"].items():
            objection_rows.append(
                {"Причина": reason, "Вариант": v, "Ответов": count, "Доля отказов": count / no if no else 0}
            )
    if objection_rows:
        st.dataframe(
            pd.DataFrame(objection_rows),
            hide_index=True,
            width="stretch",
            column_config={
                "Доля отказов": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)
            },
        )
    else:
        st.info("В этом эксперименте причины отказа не зарегистрированы.")
    export_buttons(record)


def audience_view(record):
    section("Кого представляет популяция", "Синтетические профили, без клиентских данных")
    st.caption(
        "Доли заданы для этого эксперимента. Атрибуты сегментов — экспертные предположения; подтверждённой калибровки на данных банка пока нет."
    )
    counts = record["population_counts"]
    segments = list(counts.items())
    for start in range(0, len(segments), 3):
        row = segments[start : start + 3]
        for col, (sid, count) in zip(st.columns(len(row)), row):
            with col:
                st.metric(
                    SEGMENTS[sid]["name"], count, f"{count / record['n']:.0%} аудитории", delta_color="off"
                )
    st.subheader("Примеры профилей")
    for twin in record["population_sample"]:
        with st.container(border=True):
            st.markdown(f"**{twin['name']}, {twin['age']} лет · {twin['region']}**")
            st.caption(SEGMENTS[twin["segment"]]["name"])
            st.write(f"Доход: {twin['income']}. Привычки: {', '.join(twin['habits'])}.")
            st.caption(f"Отношение к банкам: {twin['attitude']}.")


def voices_view(record):
    st.caption(
        "Синтетические высказывания, а не отзывы реальных клиентов. Демо-реплики составляются по шаблонам."
        if record["mock"]
        else "Эти высказывания сгенерированы моделью и не являются отзывами реальных клиентов."
    )
    first, second = st.columns(2)
    vid = first.selectbox(
        "Предложение",
        list(record["report"]),
        key=f"voice_variant_{record['id']}",
        format_func=lambda v: f"Вариант {v}",
    )
    decision = second.selectbox(
        "Ответ", ["Все ответы", "Готовы подключить", "Отказались"], key=f"voice_filter_{record['id']}"
    )
    quotes = [
        q
        for q in record["report"][vid]["quotes"]
        if decision == "Все ответы" or q["decision"] == (decision == "Готовы подключить")
    ]
    if not quotes:
        st.info("В сохранённой подборке нет таких ответов. Попробуйте другой фильтр.")
    cols = st.columns(2)
    for index, quote in enumerate(quotes):
        with cols[index % 2]:
            tag = "Готовы подключить" if quote["decision"] else "Отказались"
            markup(
                f'<div class="quote"><span class="quote-tag {"" if quote["decision"] else "no"}">{tag}</span>'
                f"<p>«{escape(quote['quote'])}»</p><small>{escape(quote['who'])}<br>{escape(quote['segment'])}</small></div>"
            )


def validation_view(record):
    st.subheader("Сравните симуляцию с живым опросом")
    st.write(
        "Загрузите отдельные ответы респондентов: один человек и один вариант на строку. decision: 1 — согласие, 0 — отказ."
    )
    st.caption(
        "Для сравнения используются те же сегменты и их доли, что в загруженном опросе. Ошибка взвешивается по числу ответов. Для содержательного ранжирования опрашивайте сопоставимые аудитории по всем вариантам."
    )
    example = "segment,variant,decision\n" + "".join(
        f"{sid},{vid},0\n" for vid in record["report"] for sid in record["scenario"]["population"]
    )
    st.download_button(
        "Скачать шаблон опроса",
        example,
        "survey-template.csv",
        "text/csv",
        key=f"survey_template_{record['id']}",
    )
    st.caption("Нули в шаблоне — примеры формата. Замените их реальными ответами.")
    uploaded = st.file_uploader(
        "CSV живого опроса", type=["csv"], max_upload_size=5, key=f"survey_{record['id']}"
    )
    saved = record.get("validation")
    result = saved["result"] if saved else None
    if saved:
        st.caption(
            f"Сохранённая проверка: {format_timestamp(saved['created_at'])}. Опрос предоставлен пользователем."
        )
    if uploaded is not None:
        try:
            survey = load_survey(io.StringIO(uploaded.getvalue().decode("utf-8-sig")))
            preview = attach_validation(record, survey)
            result = preview["validation"]["result"]
        except (ValueError, UnicodeError) as exc:
            st.error(f"Не удалось сравнить опрос: {exc}")
        else:
            st.caption(
                "Предпросмотр нового опроса. Сохраните проверку, чтобы включить её в историю и полный отчёт."
            )
            if st.button(
                "Сохранить проверку в эксперименте", type="primary", key=f"save_validation_{record['id']}"
            ):
                if (st.session_state.get("active_record") or {}).get("id") == record["id"]:
                    st.session_state.active_record = preview
                history = [
                    preview if r["id"] == record["id"] else r for r in st.session_state.get("history", [])
                ]
                if not any(r["id"] == record["id"] for r in history):
                    history.append(preview)
                st.session_state.history = history[-20:]
                st.rerun()
    if result is None:
        st.info(
            "Валидация ещё не проведена. Добавьте ответы живых респондентов, чтобы измерить ошибку симуляции."
        )
        return
    cols = st.columns(3)
    cols[0].metric("Средняя абсолютная ошибка", f"{result['mae_conversion'] * 100:.1f} п.п.")
    cols[1].metric(
        "Корреляция рангов",
        "Не определена" if result["spearman_variants"] is None else f"{result['spearman_variants']:.2f}",
    )
    cols[2].metric(
        "Совпадение лидера",
        {True: "Да", False: "Нет", None: "Нет единственного лидера"}[result["winner_match"]],
    )
    st.caption(
        f"{result['survey_n']} живых ответов; {result['matched_cells']} сопоставленных пар «вариант — сегмент»."
    )
    table = pd.DataFrame(result["cells"]).rename(
        columns={
            "variant": "Вариант",
            "segment": "Сегмент",
            "survey_n": "Респондентов",
            "actual": "Опрос",
            "predicted": "Симуляция",
            "error": "Ошибка",
        }
    )
    for col in ["Опрос", "Симуляция", "Ошибка"]:
        table[col] = table[col].map(lambda x: f"{100 * x:.1f}%")
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button(
        "Скачать валидацию JSON",
        export_json(result),
        "validation.json",
        "application/json",
        key=f"validation_{record['id']}",
    )


def show_report(record):
    status = quality_status(record)
    markup(
        f'<div class="quality-panel {escape(status["kind"])}"><strong>{escape(status["title"])}</strong><p>{escape(status["detail"])}</p></div>'
    )
    summary = overview(record)
    tabs = st.tabs(
        ["Обзор результатов", "Аудитория", "Голоса двойников", "Валидация"], key=f"report_tabs_{record['id']}"
    )
    with tabs[0]:
        results_view(record, summary)
    with tabs[1]:
        audience_view(record)
    with tabs[2]:
        voices_view(record)
    with tabs[3]:
        validation_view(record)


def methodology():
    st.title("Как устроен Двойник")
    st.write("Инструмент для предварительной проверки продуктовых гипотез на синтетической аудитории.")
    items = [
        (
            "Одна аудитория для всех вариантов",
            "Профили распределяются по заданным долям методом наибольших остатков. Все варианты оценивают одни и те же двойники. Seed фиксирует профили и ответы в демо-режиме; LLM-ответы могут меняться между запусками.",
        ),
        (
            "Два режима исследования",
            "Демо использует правила и ключевые слова; численные результаты служат для знакомства с интерфейсом. LLM оценивает предложение от лица заданного профиля через OpenAI-совместимый API. Поддерживается локальное развёртывание через Ollama или vLLM.",
        ),
        (
            "Что означает конверсия",
            "Число валидных ответов «да», делённое на число валидных ответов. Это заявленная готовность синтетических клиентов, а не прогноз фактических открытий счетов. Ошибки API и некорректный JSON исключаются и показываются отдельно.",
        ),
        (
            "Интервалы и выбор лидера",
            "95% интервалы Wilson показывают разброс бинарных ответов внутри симуляции. Они не учитывают смещение модели или качество профилей. Ничьи показываются явно; выбор кандидата для пилота нужно подтвердить живым исследованием.",
        ),
        (
            "Проверка на живом опросе",
            "CSV сохраняет число респондентов в каждой паре «вариант — сегмент». MAE взвешивается по этим числам. Ранжирование сравнивается на составе загруженного опроса; совпадающим значениям присваиваются средние ранги. При отсутствии разброса корреляция не определена.",
        ),
        (
            "История и воспроизводимость",
            "История содержит до 20 последних запусков в текущей сессии браузера. Она исчезает при потере сессии или перезапуске сервера. Скачайте JSON, чтобы сохранить настройки, результаты и проверку опросом. В истории можно открыть этот файл снова или использовать эксперимент как основу; CSV содержит агрегаты по сегментам.",
        ),
        (
            "Что ещё нужно для банковского пилота",
            "Профили пока основаны на экспертных предположениях. Нужны калибровка на целевой аудитории, ретро-тесты и живые интервью. Внешнюю модель подключают в соответствии с правилами организации; в профили не следует загружать персональные данные клиентов.",
        ),
    ]
    for title, text in items:
        markup(f'<div class="method"><h3>{escape(title)}</h3><p>{escape(text)}</p></div>')
