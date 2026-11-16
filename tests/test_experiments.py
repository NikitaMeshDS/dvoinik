import copy
import io
import json

import pytest

from dvoinik.engine import simulate
from dvoinik.experiments import attach_validation, load_experiment, normalize_scenario, quality_status
from dvoinik.population import build_population
from dvoinik.reporting import export_json, make_record
from dvoinik.scenarios import SCENARIOS
from dvoinik.validate import load_survey


def record():
    scenario = copy.deepcopy(SCENARIOS["senior_deposit"])
    twins = build_population(50, scenario["population"])
    return make_record(
        "senior_deposit", scenario, 50, True, 42, simulate(twins, scenario, mock=True, seed=42), twins
    )


def custom():
    return {
        "title": "Новый тариф",
        "description": "Проверяем платную подписку",
        "question": "Подключите?",
        "variants": {"A": "Без подписки", "B": "Подписка"},
        "population": {"senior": 30, "young_family": 70},
        "objections": ["плата", "не вижу пользы"],
    }


def test_custom_scenario_normalizes_audience_without_changing_offers():
    result = normalize_scenario(custom())
    assert result["population"] == {"senior": 0.3, "young_family": 0.7}
    assert result["variants"] == {"A": "Без подписки", "B": "Подписка"}


@pytest.mark.parametrize(
    "change",
    [
        {"title": ""},
        {"question": ""},
        {"variants": {"A": "Одно предложение"}},
        {"variants": {"A": "", "B": "Второе"}},
        {"objections": []},
        {"population": {"senior": 0}},
        {"population": {"missing": 1}},
        {"population": {"senior": float("nan")}},
        {"population": {"senior": True}},
    ],
)
def test_invalid_scenario_is_rejected(change):
    with pytest.raises(ValueError):
        normalize_scenario({**custom(), **change})


def test_exported_record_can_be_reopened_with_identical_results():
    original = record()
    restored = load_experiment(export_json(original))
    assert restored["report"] == original["report"]
    assert restored["scenario"] == original["scenario"]
    assert restored["id"] == original["id"]


def test_legacy_offer_whitespace_is_preserved_in_snapshot():
    original = record()
    original["schema_version"] = 1
    original["scenario"]["variants"]["A"] = "\n  " + original["scenario"]["variants"]["A"] + "  \n"
    assert load_experiment(export_json(original))["scenario"] == original["scenario"]


@pytest.mark.parametrize("corruption", ["conversion", "counts", "variant", "schema", "profile"])
def test_corrupted_import_is_rejected(corruption):
    data = record()
    if corruption == "conversion":
        data["report"]["A"]["conversion"] = 0.123456789
    elif corruption == "counts":
        data["report"]["A"]["n"] = True
    elif corruption == "variant":
        data["report"]["Z"] = data["report"].pop("A")
    elif corruption == "schema":
        data["schema_version"] = 99
    else:
        data["population_sample"][0]["habits"] = "не список"
    with pytest.raises(ValueError):
        load_experiment(export_json(data))


@pytest.mark.parametrize("text", ['{"id":"one","id":"two"}', '{"n":NaN}', "[]", "{}"])
def test_unsupported_json_has_actionable_error(text):
    with pytest.raises(ValueError):
        load_experiment(text)


def test_validation_is_saved_and_recomputed_on_import():
    original = record()
    survey = load_survey(
        io.StringIO("segment,variant,decision\nsenior,A,0\nsenior,A,1\nsenior,B,1\nsenior,C,1\n")
    )
    validated = attach_validation(original, survey)
    assert "validation" not in original
    # В JSON сохраняется основание расчёта, а не только готовые метрики.
    assert validated["validation"]["result"]["survey_n"] == 4
    validated["validation"]["result"]["mae_conversion"] = -100
    restored = load_experiment(export_json(validated))
    assert restored["validation"]["result"]["mae_conversion"] >= 0
    assert restored["validation"]["cells"][0] == {"variant": "A", "segment": "senior", "n": 2, "yes": 1}


def test_quality_status_does_not_certify_demo_as_validated_forecast():
    original = record()
    assert quality_status(original)["kind"] == "demo"
    survey = load_survey(io.StringIO("segment,variant,decision\nsenior,A,1\n"))
    assert quality_status(attach_validation(original, survey))["kind"] == "demo"
    original["mock"] = False
    assert quality_status(original)["kind"] == "unvalidated"
    assert quality_status(attach_validation(original, survey))["kind"] == "partial_validation"


def test_import_size_is_bounded():
    with pytest.raises(ValueError, match="размер"):
        load_experiment(" " * (5 * 1024 * 1024 + 1))


def test_first_format_version_remains_readable():
    original = record()
    original["schema_version"] = 1
    assert load_experiment(export_json(original))["report"] == original["report"]


def test_non_finite_extension_values_are_rejected_before_export():
    text = export_json(record())
    text = text[:-1] + ', "extension": 1e10000}'
    with pytest.raises(ValueError):
        load_experiment(text)


def test_unsafe_scenario_id_is_not_used_in_download_filename():
    original = record()
    original["scenario_key"] = "../../report"
    with pytest.raises(ValueError):
        load_experiment(export_json(original))


def test_legacy_cli_validation_is_restored_without_trusting_metrics():
    from dvoinik.validate import compare

    original = record()
    original["schema_version"] = 1
    survey = load_survey(io.StringIO("segment,variant,decision\nsenior,A,0\nsenior,A,1\nsenior,B,1\n"))
    original["validation"] = compare(original["report"], survey)
    original["validation"]["mae_conversion"] = -100
    restored = load_experiment(export_json(original))
    assert restored["validation"]["result"]["survey_n"] == 3
    assert restored["validation"]["result"]["mae_conversion"] >= 0


@pytest.mark.parametrize("field", ["title", "extension", "extension_key"])
def test_lone_unicode_surrogates_are_rejected_before_inserting_history(field):
    original = record()
    if field == "title":
        original["scenario"]["title"] = "\ud800"
    elif field == "extension":
        original["extension"] = {"text": "\ud800"}
    else:
        original["\ud800"] = "text"
    text = json.dumps(original, ensure_ascii=True)
    with pytest.raises(ValueError):
        load_experiment(text.encode())


@pytest.mark.parametrize("stamp", ["0001-01-01T00:00:00+23:59", "9999-12-31T23:59:59-23:59"])
def test_timestamp_must_be_displayable_in_moscow(stamp):
    original = record()
    original["created_at"] = stamp
    with pytest.raises(ValueError):
        load_experiment(export_json(original))


def test_duplicate_key_error_can_be_rendered_as_utf8():
    with pytest.raises(ValueError) as error:
        load_experiment(b'{"\\ud800":1,"\\ud800":2}')
    assert str(error.value).encode("utf-8")


@pytest.mark.parametrize("count", [-1, 51, True, "7", 1.5])
def test_import_rejects_invalid_probability_correction_count(count):
    data = record()
    data["report"]["A"]["inconsistent_n"] = count
    with pytest.raises(ValueError):
        load_experiment(export_json(data))


def test_import_preserves_probability_correction_count():
    data = record()
    data["report"]["A"]["inconsistent_n"] = 7
    assert load_experiment(export_json(data))["report"]["A"]["inconsistent_n"] == 7


def test_raw_probability_survives_json_export_and_import():
    data = record()
    data["report"]["A"].update(inconsistent_n=7, raw_probability={"mean": 0.8, "sd": 0.1, "n": 50})
    restored = load_experiment(export_json(data))
    assert restored["report"]["A"]["raw_probability"] == {"mean": 0.8, "sd": 0.1, "n": 50}
    legacy = record()
    legacy["report"]["A"]["inconsistent_n"] = 7
    assert "raw_probability" not in load_experiment(export_json(legacy))["report"]["A"]


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        "0.8",
        {},
        {"mean": True, "sd": 0.1, "n": 50},
        {"mean": -0.1, "sd": 0.1, "n": 50},
        {"mean": 1.1, "sd": 0.1, "n": 50},
        {"mean": float("inf"), "sd": 0.1, "n": 50},
        {"mean": 0.8, "sd": float("nan"), "n": 50},
        {"mean": 0.8, "sd": -0.1, "n": 50},
        {"mean": 0.8, "sd": 0.6, "n": 50},
        {"mean": 0.8, "sd": True, "n": 50},
        *[{"mean": 0.8, "sd": 0.1, "n": n} for n in [True, 0, -1, 49, 51, 50.0, "50"]],
    ],
)
def test_import_rejects_invalid_raw_probability(raw):
    data = record()
    data["report"]["A"]["raw_probability"] = raw
    # Go through the public importer, including its non-finite JSON checks.
    with pytest.raises(ValueError):
        load_experiment(json.dumps(data))


@pytest.mark.parametrize("mean,sd", [(0, 0), (1, 0), (0.5, 0.5)])
def test_import_accepts_raw_probability_boundaries(mean, sd):
    data = record()
    raw = {"mean": mean, "sd": sd, "n": 50}
    data["report"]["A"]["raw_probability"] = raw
    assert load_experiment(export_json(data))["report"]["A"]["raw_probability"] == raw


def test_import_rejects_raw_probability_without_observations():
    from dvoinik.engine import aggregate

    data = record()
    twins = build_population(50, {"senior": 1})
    data["report"]["A"] = aggregate((twin, {"error": "failed"}) for twin in twins)
    data["report"]["A"]["raw_probability"] = {"mean": 0, "sd": 0, "n": 0}
    with pytest.raises(ValueError):
        load_experiment(export_json(data))
