import copy

import pytest

from dvoinik.comparison import compare_runs
from dvoinik.engine import simulate
from dvoinik.experiments import load_experiment
from dvoinik.population import build_population
from dvoinik.reporting import export_json, make_record
from dvoinik.runs import RunSettings, run_experiment
from dvoinik.scenarios import SCENARIOS
from dvoinik.summary import team_summary


def record(seed=42, n=50):
    scenario = copy.deepcopy(SCENARIOS["student_card"])
    twins = build_population(n, scenario["population"], seed=seed)
    return make_record(
        "student_card", scenario, n, True, seed, simulate(twins, scenario, mock=True, seed=seed), twins
    )


def test_repeat_run_delta_uses_valid_answers_and_discloses_seed():
    left, right = record(), record(seed=51)
    result = compare_runs(left, right)
    assert [row["variant"] for row in result["variants"]] == ["A", "B", "C"]
    for row in result["variants"]:
        assert row["delta_pp"] == pytest.approx(
            (right["report"][row["variant"]]["conversion"] - left["report"][row["variant"]]["conversion"])
            * 100
        )
        assert row["left_n"] == left["report"][row["variant"]]["n"]
    assert any(change["field"] == "seed" for change in result["changes"])
    assert len(result["segments"]) == 3 * len(left["population_counts"])


def test_changed_offer_audience_and_mode_are_explicit():
    left, right = record(), record(n=100)
    right["scenario"]["variants"]["A"] = "Новая цена"
    right["scenario"]["population"] = {"senior": 1}
    right["mock"] = False
    right["model"] = "local-model"
    fields = {change["field"] for change in compare_runs(left, right)["changes"]}
    assert {"variant_A", "population", "n", "mode", "model"} <= fields


def test_missing_variant_and_missing_segment_are_not_zero_conversion():
    left, right = record(), record()
    del right["report"]["C"]
    del right["scenario"]["variants"]["C"]
    del right["report"]["A"]["segments"]["student_msk"]
    result = compare_runs(left, right)
    c = next(row for row in result["variants"] if row["variant"] == "C")
    assert c["right"] is None
    assert c["delta_pp"] is None
    segment = next(
        row for row in result["segments"] if row["variant"] == "A" and row["segment"] == "student_msk"
    )
    assert segment["right"] is None
    assert segment["delta_pp"] is None


def test_no_valid_answers_has_no_rate_or_delta():
    left, right = record(), record()
    right["report"]["A"]["n"] = 0
    right["report"]["A"]["conversion"] = 0
    row = compare_runs(left, right)["variants"][0]
    assert row["right"] is None
    assert row["delta_pp"] is None


def test_different_configuration_signatures_are_disclosed_even_with_same_model_name():
    left, right = record(), record()
    right["signature"] = "different-endpoint"
    assert any(change["field"] == "configuration" for change in compare_runs(left, right)["changes"])


def test_deposit_comparison_discloses_profile_rule_missing_from_an_older_snapshot():
    scenario = SCENARIOS["senior_deposit"]
    right = load_experiment(export_json(run_experiment("senior_deposit", scenario, RunSettings(n=24))))
    left = copy.deepcopy(right)
    left.pop("profile_policy", None)
    left["population_sample"][0]["attitude"] = "предпочитает отделение"
    left = load_experiment(export_json(left))

    result = compare_runs(left, right)
    (change,) = result["changes"]
    assert change["field"] == "profile_policy" and change["before"] == "Не сохранена"
    assert "предпочтения отделения" in change["after"]
    assert [warning["code"] for warning in result["warnings"]] == ["profile_policy"]
    assert compare_runs(right, right)["warnings"] == []
    assert "<th>Версия анкеты вклада</th><td>Без готового предпочтения отделения</td>" in team_summary(right)
    assert "<th>Версия анкеты вклада</th><td>Не сохранена</td>" in team_summary(left)
    left["profile_policy"] = right["profile_policy"]
    with pytest.raises(ValueError, match="анкеты"):
        load_experiment(export_json(left))


@pytest.mark.parametrize("previous_minimum", [None, 50_000])
def test_compare_shows_changed_deposit_minimum(previous_minimum):
    previous = {**SCENARIOS["senior_deposit"]}
    previous.pop("deposit_minimum_rub")
    if previous_minimum is not None:
        previous["deposit_minimum_rub"] = previous_minimum
    current = {**previous, "deposit_minimum_rub": 75_000}
    settings = RunSettings(n=12, mock=True)
    left = run_experiment("senior_deposit", previous, settings)
    right = run_experiment("senior_deposit", current, settings)
    result = compare_runs(left, right)
    assert result["changes"] == [
        {
            "field": "deposit_minimum_rub",
            "label": "Минимальный взнос, ₽",
            "before": previous_minimum,
            "after": 75_000,
        }
    ]
    assert [warning["code"] for warning in result["warnings"]] == ["deposit_minimum"]


def test_comparison_warnings_explain_multiple_changed_factors_in_stable_order():
    left, right = record(), record(seed=99, n=100)
    right["mock"] = False
    right["model"] = "another-model"
    right["scenario"]["question"] = "Новый вопрос?"
    right["scenario"]["population"] = {"senior": 1}
    right["scenario"]["variants"]["A"] = "Новый текст"
    warnings = compare_runs(left, right)["warnings"]
    assert [item["code"] for item in warnings] == [
        "mode",
        "model",
        "question_context",
        "population",
        "profile_sample",
        "variant_text",
        "missing_data",
    ]
    assert all(isinstance(item["text"], str) and item["text"] for item in warnings)


def test_equal_conditions_and_proportional_weights_do_not_warn_about_audience():
    left, right = record(), record()
    right["scenario"]["population"] = {
        sid: weight * 100 for sid, weight in left["scenario"]["population"].items()
    }
    assert compare_runs(left, right)["warnings"] == []


def test_missing_data_and_changed_variant_set_are_warned_without_zero_rates():
    left, right = record(), record()
    del right["report"]["C"]
    del right["scenario"]["variants"]["C"]
    del right["report"]["A"]["segments"]["student_msk"]
    result = compare_runs(left, right)
    codes = [warning["code"] for warning in result["warnings"]]
    assert "variant_set" in codes and "missing_data" in codes
    assert next(row for row in result["variants"] if row["variant"] == "C")["delta_pp"] is None


def test_selected_segment_missing_from_both_reports_is_still_incomplete():
    left, right = record(), record()
    for current in (left, right):
        for result in current["report"].values():
            del result["segments"]["student_msk"]
    assert "missing_data" in {warning["code"] for warning in compare_runs(left, right)["warnings"]}


@pytest.mark.parametrize("quality_field", ["failed_n", "inconsistent_n"])
def test_partial_failures_or_corrected_probabilities_warn_with_all_cells_present(quality_field):
    left, right = record(), record()
    # Every comparison still has a valid rate; a quality warning cannot rely on
    # missing cells or null conversion alone.
    right["report"]["A"][quality_field] = 1
    before = copy.deepcopy(right["report"])
    result = compare_runs(left, right)
    assert "response_quality" in {warning["code"] for warning in result["warnings"]}
    assert "missing_data" not in {warning["code"] for warning in result["warnings"]}
    assert all(row["delta_pp"] == 0 for row in result["variants"])
    assert right["report"] == before
