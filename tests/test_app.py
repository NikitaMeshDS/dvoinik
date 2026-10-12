from pathlib import Path

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
