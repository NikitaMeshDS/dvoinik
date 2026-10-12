"""Двойник — Streamlit UI.

Запуск без LLM (демо):     DVOINIK_MOCK=1 streamlit run app.py
Запуск с on-prem LLM:      LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=qwen2.5:7b-instruct streamlit run app.py
"""
import os

import pandas as pd
import streamlit as st

from dvoinik.engine import simulate
from dvoinik.population import build_population
from dvoinik.scenarios import SCENARIOS

st.set_page_config(page_title="Двойник", page_icon="👥", layout="wide")
st.title("👥 Двойник — синтетические клиенты для тестирования продуктов")

mock_default = os.getenv("DVOINIK_MOCK", "0") == "1"
with st.sidebar:
    key = st.selectbox("Сценарий", list(SCENARIOS), format_func=lambda k: SCENARIOS[k]["title"])
    sc = SCENARIOS[key]
    n = st.select_slider("Размер популяции", [50, 100, 200, 500, 1000], value=200)
    mock = st.toggle("Демо-режим без LLM", value=mock_default)
    st.caption("LLM: " + ("эвристическая модель" if mock else os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")))
    run = st.button("Запустить симуляцию", type="primary")

st.subheader(sc["title"])
st.info(sc["description"])
st.write(f"**Вопрос двойникам:** {sc['question']}")
for vid, text in sc["variants"].items():
    st.markdown(f"**{vid}.** {text}")

if run:
    twins = build_population(n, sc["population"])
    with st.spinner(f"{n} двойников оценивают {len(sc['variants'])} варианта…"):
        rep = simulate(twins, sc, mock=mock)
    st.session_state.rep = (key, rep)

if st.session_state.get("rep") and st.session_state.rep[0] == key:
    rep = st.session_state.rep[1]
    best = max(rep, key=lambda v: rep[v]["conversion"])
    cols = st.columns(len(rep))
    for c, (vid, r) in zip(cols, rep.items()):
        c.metric(f"Вариант {vid}" + (" 🏆" if vid == best else ""), f"{r['conversion']:.0%}")

    st.markdown("#### Конверсия по сегментам")
    seg = pd.DataFrame({vid: {s["name"]: s["conversion"] for s in r["segments"].values()}
                        for vid, r in rep.items()})
    st.bar_chart(seg)
    st.dataframe(seg.style.format("{:.0%}"), use_container_width=True)

    st.markdown("#### Причины отказа")
    obj = pd.DataFrame({vid: r["objections"] for vid, r in rep.items()}).fillna(0).astype(int)
    st.dataframe(obj, use_container_width=True)

    st.markdown("#### Голоса двойников")
    vid = st.radio("Вариант", list(rep), horizontal=True)
    for q in rep[vid]["quotes"]:
        icon = "✅" if q["decision"] else "❌"
        st.markdown(f"{icon} **{q['who']}** · {q['segment']}  \n> {q['quote']}")
