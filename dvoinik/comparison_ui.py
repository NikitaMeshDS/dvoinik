"""Представление сравнения двух сохранённых запусков."""

from __future__ import annotations

import json

import altair as alt
import pandas as pd
import streamlit as st

from .comparison import compare_runs
from .download_ui import download
from .experiments import format_timestamp
from .population import SEGMENTS
from .presentation import COLORS
from .reporting import export_json


def comparison_view(history):
    if len(history) < 2:
        st.info("Для сравнения нужны два сохранённых запуска. Повторите эксперимент или откройте JSON-отчёт.")
        return
    records = {r["id"]: r for r in history}
    ids = list(reversed(records))

    def label(record_id):
        record = records[record_id]
        return f"{record_id} · {record['scenario']['title']}"

    cols = st.columns(2)
    first = cols[0].selectbox("Исходный запуск", ids, index=1, format_func=label, key="compare_left")
    second = cols[1].selectbox("Новый запуск", ids, index=0, format_func=label, key="compare_right")
    if first == second:
        st.info("Выберите два разных эксперимента.")
        return
    left, right = records[first], records[second]
    for col, record in zip(cols, (left, right)):
        col.caption(
            f"{format_timestamp(record['created_at'])} · {record['n']} двойников · Seed {record['seed']} · {record['model']}"
        )
    result = compare_runs(left, right)
    st.caption(
        "Дельта = новый запуск − исходный. Сопоставление идёт по буквам вариантов; тексты показаны ниже."
    )
    if result["changes"]:
        st.warning(
            "Условия запусков различаются. Разницу результатов нельзя приписать только изменению предложения."
        )

        def display(value):
            if value is None:
                return "Нет варианта"
            return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Изменение": c["label"],
                        "Исходный запуск": display(c["before"]),
                        "Новый запуск": display(c["after"]),
                    }
                    for c in result["changes"]
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info(
            "Сохранённые условия совпадают. Повтор LLM может дать другие ответы; демо с тем же seed воспроизводится."
        )
    st.caption("Сравнение описательное: оно не доказывает значимость разницы или изменение реального спроса.")
    if left["mock"] or right["mock"]:
        st.caption("В сравнении есть демо: его проценты получены по эвристическим правилам.")
    if any(r["failed_n"] for rec in (left, right) for r in rec["report"].values()):
        st.warning("Есть ошибки ответов модели. Разное покрытие сегментов может сместить сравнение.")
    with st.expander("Тексты сравниваемых предложений"):
        for col, record in zip(st.columns(2), (left, right)):
            with col:
                st.markdown(f"**{record['scenario']['title']}**")
                for vid, text in record["scenario"]["variants"].items():
                    st.write(f"{vid}: {text}")
    chart_rows = [
        {"Вариант": row["variant"], "Запуск": label, "Конверсия": row[side], "Ответов": row[f"{side}_n"]}
        for row in result["variants"]
        for side, label in [("left", "Исходный"), ("right", "Новый")]
        if row[side] is not None
    ]
    if chart_rows:
        chart = (
            alt.Chart(pd.DataFrame(chart_rows))
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                y=alt.Y("Вариант:N", title=None),
                yOffset="Запуск:N",
                x=alt.X("Конверсия:Q", title=None, scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")),
                color=alt.Color(
                    "Запуск:N",
                    scale=alt.Scale(domain=["Исходный", "Новый"], range=COLORS[:2]),
                    legend=alt.Legend(orient="top"),
                ),
                tooltip=["Вариант:N", "Запуск:N", alt.Tooltip("Конверсия:Q", format=".1%"), "Ответов:Q"],
            )
            .properties(height=80 * len(result["variants"]))
            .configure_view(stroke=None)
        )
        st.altair_chart(chart, width="stretch")

    def table(rows):
        return pd.DataFrame(
            [
                {
                    "Вариант": row["variant"],
                    **({"Сегмент": SEGMENTS[row["segment"]]["name"]} if "segment" in row else {}),
                    "Исходный": "—" if row["left"] is None else f"{row['left']:.1%}",
                    "Новый": "—" if row["right"] is None else f"{row['right']:.1%}",
                    "Дельта, п.п.": "—" if row["delta_pp"] is None else f"{row['delta_pp']:+.1f}",
                    "Ответов: исходный": row["left_n"],
                    "Ответов: новый": row["right_n"],
                }
                for row in rows
            ]
        )

    st.dataframe(table(result["variants"]), hide_index=True, width="stretch")
    st.caption("«—» означает отсутствие варианта или валидных ответов, а не нулевую конверсию.")
    with st.expander("Разница по сегментам"):
        st.dataframe(table(result["segments"]), hide_index=True, width="stretch")
    download(
        "Скачать сравнение JSON",
        export_json({"comparison_version": 1, "left": left, "right": right, "comparison": result}),
        f"dvoinik-comparison-{first}-{second}.json",
        "application/json",
        key="comparison_export",
    )
