import io
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

APP = Path(__file__).parents[1] / "app.py"


def launch(monkeypatch):
    monkeypatch.setenv("DVOINIK_MOCK", "1")
    return AppTest.from_file(str(APP), default_timeout=15).run()


def test_startup_shows_explicit_demo_without_adding_to_history(monkeypatch):
    app = launch(monkeypatch)
    assert not app.exception
    assert app.session_state["active_record"]["sample"] is True
    assert app.session_state["history"] == []
    assert len(app.get("download_button")) >= 2


def test_run_keeps_snapshot_and_warns_after_offer_is_edited(monkeypatch):
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    assert not app.exception
    assert len(app.session_state["history"]) == 1
    original = app.session_state["active_record"]["scenario"]["variants"]["A"]
    app.text_area(key="variant_student_card_A").set_value("Совершенно другое предложение").run()
    assert not app.exception
    assert app.session_state["active_record"]["scenario"]["variants"]["A"] == original
    assert app.session_state["results_stale"] is True


def test_all_scenarios_run_and_history_remains_accessible(monkeypatch):
    app = launch(monkeypatch)
    for key in [
        "student_card",
        "family_budget",
        "credit_card",
        "senior_deposit",
        "push_cashback",
        "self_employed",
        "nonresident_transfer",
    ]:
        app.selectbox(key="scenario_key").select(key).run()
        app.button(key="run_experiment").click().run()
        assert not app.exception, key
        assert app.session_state["active_record"]["scenario_key"] == key
    assert len(app.session_state["history"]) == 7
    app.radio(key="navigation").set_value("История").run()
    assert not app.exception
    assert len(app.get("download_button")) >= 7


def test_empty_offer_does_not_create_experiment(monkeypatch):
    app = launch(monkeypatch)
    app.text_area(key="variant_student_card_A").set_value("").run()
    app.button(key="run_experiment").click().run()
    assert not app.exception
    assert app.error
    assert app.session_state["history"] == []


def test_draft_survives_navigation_and_scenario_switch(monkeypatch):
    app = launch(monkeypatch)
    app.selectbox(key="scenario_key").select("family_budget").run()
    app.text_area(key="variant_family_budget_A").set_value("Новое предложение семье").run()
    app.select_slider(key="population_n").set_value(50).run()
    app.slider(key="weight_family_budget_senior").set_value(35).run()
    app.radio(key="navigation").set_value("История").run()
    app.radio(key="navigation").set_value("Эксперимент").run()
    assert not app.exception
    assert app.selectbox(key="scenario_key").value == "family_budget"
    assert app.select_slider(key="population_n").value == 50
    assert app.text_area(key="variant_family_budget_A").value == "Новое предложение семье"

    assert app.slider(key="weight_family_budget_senior").value == 35
    app.selectbox(key="scenario_key").select("student_card").run()
    app.selectbox(key="scenario_key").select("family_budget").run()
    assert app.text_area(key="variant_family_budget_A").value == "Новое предложение семье"


def test_custom_experiment_supports_five_offers_and_all_segments(monkeypatch):
    app = launch(monkeypatch)
    app.selectbox(key="scenario_key").select("custom").run()
    assert not app.exception
    assert app.session_state["active_record"] is None
    app.text_input(key="title_custom").set_value("Подписка для предпринимателей").run()
    app.number_input(key="variant_count_custom").set_value(5).run()
    for vid in "ABCDE":
        app.text_area(key=f"variant_custom_{vid}").set_value(f"Предложение {vid}: бесплатный счёт").run()
    app.number_input(key="weight_custom_self_employed").set_value(100.0).run()
    app.number_input(key="weight_custom_student_msk").set_value(0.0).run()
    app.number_input(key="weight_custom_student_reg").set_value(0.0).run()
    app.button(key="run_experiment").click().run()
    assert not app.exception
    saved = app.session_state["active_record"]
    assert saved["scenario"]["title"] == "Подписка для предпринимателей"
    assert list(saved["report"]) == list("ABCDE")
    assert saved["population_counts"] == {"self_employed": 200}


def test_hidden_custom_offers_survive_count_changes_and_navigation(monkeypatch):
    app = launch(monkeypatch)
    app.selectbox(key="scenario_key").select("custom").run()
    app.number_input(key="variant_count_custom").set_value(5).run()
    app.text_area(key="variant_custom_E").set_value("Сохранить предложение E").run()
    app.number_input(key="variant_count_custom").set_value(2).run()
    app.text_area(key="variant_custom_A").set_value("Новое A, пока E скрыт").run()
    app.radio(key="navigation").set_value("Методология").run()
    app.radio(key="navigation").set_value("Эксперимент").run()
    app.number_input(key="variant_count_custom").set_value(5).run()
    assert not app.exception
    assert app.text_area(key="variant_custom_E").value == "Сохранить предложение E"
    assert app.text_area(key="variant_custom_A").value == "Новое A, пока E скрыт"


def test_saved_record_can_be_used_as_custom_draft(monkeypatch):
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    original = app.session_state["history"][0]
    app.radio(key="navigation").set_value("История").run()
    app.button(key=f"history_reuse_{original['id']}").click().run()
    assert not app.exception
    assert app.radio(key="navigation").value == "Эксперимент"
    assert app.selectbox(key="scenario_key").value == "custom"
    assert app.text_area(key="variant_custom_A").value == original["scenario"]["variants"]["A"]
    assert app.session_state["active_record"] is None


def test_survey_validation_persists_after_upload_widget_is_removed(monkeypatch):
    real_upload = st.file_uploader
    uploaded = {"enabled": True}
    csv = b"segment,variant,decision\nstudent_msk,A,0\nstudent_msk,B,1\nstudent_msk,C,1\n"

    def upload(*args, **kwargs):
        if str(kwargs.get("key", "")).startswith("survey_"):
            return io.BytesIO(csv) if uploaded["enabled"] else None
        return real_upload(*args, **kwargs)

    monkeypatch.setattr(st, "file_uploader", upload)
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    record_id = app.session_state["active_record"]["id"]
    app.button(key=f"save_validation_{record_id}").click().run()
    assert not app.exception
    assert app.session_state["history"][0]["validation"]["result"]["survey_n"] == 3
    uploaded["enabled"] = False
    app.radio(key="navigation").set_value("История").run()
    app.button(key=f"history_open_{record_id}").click().run()
    assert not app.exception
    assert any(m.label == "Средняя абсолютная ошибка" for m in app.metric)


def test_validation_can_be_saved_for_history_record_without_active_experiment(monkeypatch):
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    record_id = app.session_state["active_record"]["id"]
    app.session_state["active_record"] = None
    csv = b"segment,variant,decision\nstudent_msk,A,0\n"
    real_upload = st.file_uploader

    def upload(*args, **kwargs):
        if str(kwargs.get("key", "")).startswith("survey_"):
            return io.BytesIO(csv)
        return real_upload(*args, **kwargs)

    monkeypatch.setattr(st, "file_uploader", upload)
    app.radio(key="navigation").set_value("История").run()
    app.button(key=f"history_open_{record_id}").click().run()
    app.button(key=f"save_validation_{record_id}").click().run()
    assert not app.exception
    assert app.session_state["history"][0]["validation"]["result"]["survey_n"] == 1
