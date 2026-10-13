"""Состояние редактора и callback переходов между страницами."""

from __future__ import annotations

import os

import streamlit as st

from .experiments import normalize_scenario
from .population import SEGMENTS


def initialize_drafts(*, demo=False):
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
    for key, value in st.session_state.saved_inputs.items():
        st.session_state.setdefault(key, value)
    if demo:
        st.session_state.saved_inputs["mock_mode"] = True
        st.session_state.mock_mode = True


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
