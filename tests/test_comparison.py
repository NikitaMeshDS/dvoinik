import copy

import pytest

from dvoinik.comparison import compare_runs
from dvoinik.engine import simulate
from dvoinik.population import build_population
from dvoinik.reporting import make_record
from dvoinik.scenarios import SCENARIOS


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
