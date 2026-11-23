from types import SimpleNamespace

import pytest

from dvoinik.experiments import attach_validation, load_experiment
from dvoinik.report_stats import paired_probabilities
from dvoinik.reporting import export_json
from dvoinik.runs import RunSettings, run_experiment
from dvoinik.scenarios import SCENARIOS
from dvoinik.validate import SurveyRates


def row(profile, p, decision, segment="senior"):
    return SimpleNamespace(id=profile, segment=segment), {"probability": p, "decision": decision}


def test_equal_probabilities_produce_zero_gap_despite_opposite_draws():
    (result,) = paired_probabilities(
        {
            "A": [row(0, 0.5, True), row(1, 0.3, True)],
            "B": [row(0, 0.5, False), row(1, 0.3, False)],
        }
    )
    assert result == {
        "variants": ["A", "B"],
        "matched_n": 2,
        "means": [0.4, 0.4],
        "gap_pp": 0,
        "interval_95_pp": [0, 0],
        "segments": {"senior": {"matched_n": 2, "gap_pp": 0}},
    }


def test_missing_outcomes_do_not_enter_the_matched_denominator():
    (result,) = paired_probabilities(
        {
            "A": [row(0, 1, True), row(1, 0.6, False)],
            "B": [(SimpleNamespace(id=0), {"error": "timeout"}), row(1, 0.2, False)],
        }
    )
    assert result["matched_n"] == 1
    assert result["means"] == [0.6, 0.2]
    assert result["gap_pp"] == pytest.approx(40)
    assert result["interval_95_pp"] is None
    assert result["segments"]["senior"] == {"matched_n": 1, "gap_pp": 40}


def test_snapshot_preserves_pairs_and_rejects_impossible_coverage():
    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=4))
    with_pairs = load_experiment(export_json(record))
    assert len(with_pairs["paired_probabilities"]) == 3
    assert all(pair["matched_n"] == 4 for pair in with_pairs["paired_probabilities"])
    record["paired_probabilities"][0]["matched_n"] = 5
    with pytest.raises(ValueError):
        load_experiment(export_json(record))


def test_field_comparison_uses_the_matching_segment_probability_gap():
    scenario = {**SCENARIOS["senior_deposit"], "population": {"senior": 0.5, "student_msk": 0.5}}
    record = run_experiment("senior_deposit", scenario, RunSettings(n=20))
    rates = {("A", "senior"): 0.6, ("B", "senior"): 0.5}
    survey = SurveyRates(rates, dict.fromkeys(rates, 10))
    expected = record["paired_probabilities"][0]["segments"]["senior"]
    validated = load_experiment(export_json(attach_validation(record, survey)))
    (comparison,) = validated["validation"]["result"]["segment_contrasts"]
    assert comparison["segment"] == "senior"
    assert comparison["model_pair"] == {
        **expected,
        "absolute_error_pp": pytest.approx(abs(expected["gap_pp"] - 10)),
    }
    assert "interval_95_pp" not in comparison
