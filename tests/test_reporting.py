import csv
import io
import json

from dvoinik import reporting


def test_tied_results_do_not_invent_a_winner():
    report = {"A": {"n": 20, "conversion": 0.5}, "B": {"n": 20, "conversion": 0.5}}
    summary = reporting.summarize(report)
    assert summary["leaders"] == ["A", "B"]
    assert summary["gap_pp"] == 0


def test_export_retains_configuration_and_segment_denominators():
    record = {
        "scenario": {"variants": {"A": "Текст"}},
        "mock": True,
        "report": {
            "A": {
                "n": 10,
                "yes": 5,
                "conversion": 0.5,
                "failed_n": 2,
                "segments": {"senior": {"name": "Пенсионеры", "n": 10, "conversion": 0.5}},
            }
        },
    }
    restored = json.loads(reporting.export_json(record))
    assert restored["scenario"]["variants"]["A"] == "Текст"
    rows = list(csv.DictReader(io.StringIO(reporting.export_csv(record))))
    assert rows[0]["segment"] == "senior"
    assert rows[0]["n"] == "10"
    assert rows[0]["conversion"] == "0.5"


def test_experiment_signature_changes_for_edited_offer_and_audience():
    original = {"variants": {"A": "Бесплатно"}, "population": {"senior": 1}, "question": "Да?"}
    changed = {**original, "variants": {"A": "100 рублей"}}
    assert reporting.signature(original, 50, True, 42) != reporting.signature(changed, 50, True, 42)
    assert reporting.signature(original, 50, True, 42) != reporting.signature(original, 100, True, 42)


def test_csv_export_does_not_execute_spreadsheet_formulas():
    record = {"report": {"=1+1": {"segments": {"senior": {"name": "=1+1", "n": 1, "conversion": 1}}}}}
    rows = list(csv.DictReader(io.StringIO(reporting.export_csv(record))))
    assert rows[0]["variant"].startswith("'")
    assert rows[0]["segment_name"].startswith("'")


def test_demo_snapshots_have_distinct_ids_for_archive():
    scenario = {"title": "Демо", "variants": {"A": "Бесплатно"}, "population": {"senior": 1}}
    first = reporting.make_record("demo", scenario, 1, True, 42, {}, [], sample=True)
    second = reporting.make_record("demo", scenario, 1, True, 42, {}, [], sample=True)
    assert first["id"] != second["id"]
    assert first["sample"] is True
