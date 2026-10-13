import copy
import io
import re
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from dvoinik import ui
from dvoinik.storage import ExperimentStore, StorageError

APP = Path(__file__).parents[1] / "app.py"


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("DVOINIK_STORAGE_PATH", str(tmp_path / "experiments.sqlite3"))
    monkeypatch.setenv("DVOINIK_AUTH_MODE", "demo")
    monkeypatch.setenv("DVOINIK_DOWNLOAD_ORIGIN", "http://127.0.0.1:9000")


def download_keys(app):
    return {key for item in app.markdown for key in re.findall(r'data-download-key="([^" ]+)"', item.value)}


def launch(monkeypatch):
    monkeypatch.setenv("DVOINIK_MOCK", "1")
    return AppTest.from_file(str(APP), default_timeout=15).run()


def test_startup_shows_explicit_demo_without_adding_to_history(monkeypatch):
    app = launch(monkeypatch)
    assert not app.exception
    assert app.session_state["active_record"]["sample"] is True
    assert app.session_state["history"] == []
    assert len(download_keys(app)) >= 2


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
    assert len(download_keys(app)) >= 7


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


def test_history_survives_new_browser_session(monkeypatch):
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    record_id = app.session_state["history"][0]["id"]
    reopened = launch(monkeypatch)
    reopened.radio(key="navigation").set_value("История").run()
    assert not reopened.exception
    assert [r["id"] for r in reopened.session_state["history"]] == [record_id]
    reopened.button(key=f"history_open_{record_id}").click().run()
    assert reopened.session_state["history_view"] == record_id
    assert "json_active" in download_keys(reopened)


def test_storage_failure_preserves_new_report_for_download(monkeypatch, tmp_path):
    def fail_save(self, record, **kwargs):
        raise StorageError("Диск архива недоступен")

    monkeypatch.setattr(ExperimentStore, "save", fail_save)
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    assert not app.exception
    assert len(app.session_state["history"]) == 1
    assert not app.session_state["active_record"]["sample"]
    assert app.error
    assert "json_active" in download_keys(app)


def test_saved_validation_survives_new_session(monkeypatch):
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    record_id = app.session_state["active_record"]["id"]
    real_upload = st.file_uploader

    def upload(*args, **kwargs):
        if str(kwargs.get("key", "")).startswith("survey_"):
            return io.BytesIO(b"segment,variant,decision\nstudent_msk,A,0\n")
        return real_upload(*args, **kwargs)

    monkeypatch.setattr(st, "file_uploader", upload)
    app.run()
    app.button(key=f"save_validation_{record_id}").click().run()
    monkeypatch.setattr(st, "file_uploader", real_upload)
    reopened = launch(monkeypatch)
    reopened.radio(key="navigation").set_value("История").run()
    reopened.button(key=f"history_open_{record_id}").click().run()
    assert not reopened.exception
    assert reopened.session_state["history"][0]["validation"]["result"]["survey_n"] == 1
    assert any(m.label == "Средняя абсолютная ошибка" for m in reopened.metric)


def test_two_runs_can_be_compared_from_history(monkeypatch):
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    app.number_input(key="seed").set_value(51).run()
    app.button(key="run_experiment").click().run()
    app.radio(key="navigation").set_value("История").run()
    app.button(key="library_compare").click().run()
    assert not app.exception
    assert len(app.selectbox(key="compare_left").options) == 2
    assert app.selectbox(key="compare_left").value != app.selectbox(key="compare_right").value
    assert "comparison_export" in download_keys(app)
    assert any("Seed" in frame.value.to_string() for frame in app.dataframe)


def test_unsaved_validation_is_not_replaced_by_old_disk_snapshot(monkeypatch):
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    record_id = app.session_state["active_record"]["id"]
    real_upload = st.file_uploader

    def upload(*args, **kwargs):
        if str(kwargs.get("key", "")).startswith("survey_"):
            return io.BytesIO(b"segment,variant,decision\nstudent_msk,A,0\n")
        return real_upload(*args, **kwargs)

    def fail_save(self, record, **kwargs):
        raise StorageError("Диск недоступен")

    exported = []
    real_export = ui.export_json

    def export(record):
        if record.get("id") == record_id:
            exported.append(record)
        return real_export(record)

    monkeypatch.setattr(st, "file_uploader", upload)
    monkeypatch.setattr(ExperimentStore, "save", fail_save)
    monkeypatch.setattr(ui, "export_json", export)
    app.run()
    app.button(key=f"save_validation_{record_id}").click().run()
    assert app.error
    assert exported[-1]["validation"]["result"]["survey_n"] == 1
    app.radio(key="navigation").set_value("История").run()
    assert not app.exception
    assert app.session_state["history"][0]["validation"]["result"]["survey_n"] == 1


def test_two_pending_survey_updates_recover_when_disk_returns(monkeypatch):
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    record_id = app.session_state["active_record"]["id"]
    real_upload, real_save = st.file_uploader, ExperimentStore.save
    answer = {"decision": 0}

    def upload(*args, **kwargs):
        if str(kwargs.get("key", "")).startswith("survey_"):
            return io.BytesIO(f"segment,variant,decision\nstudent_msk,A,{answer['decision']}\n".encode())
        return real_upload(*args, **kwargs)

    def fail_save(self, record, **kwargs):
        raise StorageError("Диск недоступен")

    monkeypatch.setattr(st, "file_uploader", upload)
    monkeypatch.setattr(ExperimentStore, "save", fail_save)
    app.run()
    app.button(key=f"save_validation_{record_id}").click().run()
    answer["decision"] = 1
    app.run()
    app.button(key=f"save_validation_{record_id}").click().run()
    monkeypatch.setattr(ExperimentStore, "save", real_save)
    app.run()
    assert not app.error
    assert app.session_state["pending_records"] == {}
    assert app.session_state["experiment_store"].list_records()[0]["validation"]["cells"][0]["yes"] == 1


def test_library_filters_records_and_returns_from_report_to_catalog(monkeypatch):
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    student_id = app.session_state["active_record"]["id"]
    app.selectbox(key="scenario_key").select("senior_deposit").run()
    app.button(key="run_experiment").click().run()
    senior_id = app.session_state["active_record"]["id"]
    app.radio(key="navigation").set_value("История").run()
    app.text_input(key="library_query").set_value("пенсионер").run()
    assert not app.exception
    assert any(b.key == f"history_open_{senior_id}" for b in app.button)
    assert not any(b.key == f"history_open_{student_id}" for b in app.button)
    app.selectbox(key="library_mode").select("llm").run()
    assert not any(b.key.startswith("history_open_") for b in app.button)
    app.selectbox(key="library_mode").select("all").run()
    app.button(key=f"history_open_{senior_id}").click().run()
    assert "json_active" in download_keys(app)
    assert not any(b.key.startswith("history_open_") for b in app.button)
    app.button(key="library_back").click().run()
    assert app.text_input(key="library_query").value == "пенсионер"
    assert any(b.key == f"history_open_{senior_id}" for b in app.button)


def test_open_constructor_from_library_keeps_current_draft(monkeypatch):
    app = launch(monkeypatch)
    app.text_area(key="variant_student_card_A").set_value("Мой незапущенный вариант").run()
    app.radio(key="navigation").set_value("История").run()
    app.button(key="library_new").click().run()
    assert not app.exception
    assert app.text_area(key="variant_student_card_A").value == "Мой незапущенный вариант"


def test_catalog_pagination_keeps_page_after_viewing_report(monkeypatch):
    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    original = app.session_state["active_record"]
    store = app.session_state["experiment_store"]
    for index in range(8):
        record = copy.deepcopy(original)
        record["id"] = f"page-run-{index}"
        store.save(record)
    app.radio(key="navigation").set_value("История").run()
    open_buttons = [b for b in app.button if b.key.startswith("history_open_")]
    assert len(open_buttons) == 8
    app.selectbox(key="library_page").select(2).run()
    open_buttons = [b for b in app.button if b.key.startswith("history_open_")]
    assert len(open_buttons) == 1
    open_buttons[0].click().run()
    app.button(key="library_back").click().run()
    assert not app.exception
    assert app.selectbox(key="library_page").value == 2


def test_constructor_previews_exact_segment_counts_before_running(monkeypatch):
    app = launch(monkeypatch)
    app.select_slider(key="population_n").set_value(50).run()
    tables = [frame.value for frame in app.dataframe if "Двойников" in frame.value.columns]
    assert tables, "Constructor needs an audience preview before simulation"
    counts = dict(zip(tables[0]["Сегмент"], tables[0]["Двойников"]))
    assert counts == {
        "Студенты 18–22, Москва": 18,
        "Студенты регионов": 18,
        "Подростки 14–17 (решение с родителем)": 7,
        "Иностранные студенты и мигранты": 7,
    }
    app.button(key="run_experiment").click().run()
    assert not app.exception
    assert app.session_state["active_record"]["population_counts"] == {
        "student_msk": 18,
        "student_reg": 18,
        "teen": 7,
        "nonresident": 7,
    }


def test_conflicted_pending_validation_does_not_block_another_pending_validation(monkeypatch):
    from dvoinik.experiments import attach_validation
    from dvoinik.validate import load_survey

    app = launch(monkeypatch)
    app.button(key="run_experiment").click().run()
    original = app.session_state["active_record"]
    store = app.session_state["experiment_store"]
    remote = attach_validation(
        original, load_survey(io.StringIO("segment,variant,decision\nstudent_msk,A,1\n"))
    )
    store.save(remote, expected_validation=None)
    local = attach_validation(
        original, load_survey(io.StringIO("segment,variant,decision\nstudent_msk,A,0\n"))
    )
    second = copy.deepcopy(original)
    second["id"] = "independent-pending-run"
    store.save(second)
    second = attach_validation(
        second, load_survey(io.StringIO("segment,variant,decision\nstudent_msk,B,0\n"))
    )
    app.session_state["active_record"] = local
    app.session_state["history"] = [local, second]
    app.session_state["pending_records"] = {local["id"]: local, second["id"]: second}
    app.session_state["pending_validation_bases"] = {local["id"]: None, second["id"]: None}
    app.run()
    assert not app.exception
    assert store.get_record(second["id"])["validation"]["cells"][0]["yes"] == 0
    assert list(app.session_state["pending_records"]) == [local["id"]]
    assert store.get_record(local["id"])["validation"]["cells"][0]["yes"] == 1
    assert app.session_state["active_record"]["validation"]["cells"][0]["yes"] == 0
