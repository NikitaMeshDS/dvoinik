import json
import sys
from pathlib import Path

import pytest

from benchmarks import deposit_digital_skill

REPORT = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "benchmark-results"
    / "2026-11-20"
    / "deposit-digital-skill-4b.json"
)


def compare_csv(tmp_path, monkeypatch, rows, report_path=REPORT):
    survey = tmp_path / "responses.csv"
    survey.write_text("variant,segment,decision\n" + rows, encoding="utf-8")
    output = tmp_path / "comparison.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deposit_digital_skill",
            "--compare",
            str(report_path),
            "--survey",
            str(survey),
            "--output",
            str(output),
        ],
    )
    assert deposit_digital_skill.main() == 0
    return json.loads(output.read_text(encoding="utf-8"))


def test_partial_survey_discloses_coverage_and_keeps_only_supported_comparisons(
    tmp_path, monkeypatch, capsys
):
    result = compare_csv(
        tmp_path,
        monkeypatch,
        "A,independent,1\nA,independent,0\nB,independent,1\nA,assisted,0\n",
    )
    coverage = result["human_coverage"]
    assert coverage["survey_n"] == 4
    assert coverage["expected_cells"] == 6
    assert coverage["survey_cells"] == coverage["comparable_cells"] == 3
    assert coverage["paired_groups"] == ["independent"]
    assert coverage["missing_survey_cells"] == [
        {"variant": "B", "group": "assisted"},
        {"variant": "A", "group": "offline"},
        {"variant": "B", "group": "offline"},
    ]
    assert coverage["missing_model_cells"] == []
    assert "3/6" in capsys.readouterr().out
    groups = result["human_comparison"]
    assert "offline" not in groups
    assert groups["assisted"]["A"]["yes_share"] == 0
    assert "gap_a_minus_b_pp" not in groups["assisted"]
    gap = groups["independent"]["gap_a_minus_b_pp"]
    assert gap["survey"] == -50
    assert gap["with_skill"] == pytest.approx(24.1666667)
    assert groups["independent"]["gap_a_minus_b_error_pp"]["with_skill"] == pytest.approx(74.1666667)


@pytest.mark.parametrize("missing_group", [False, True])
def test_responses_without_model_estimates_are_visible_but_not_comparable(
    tmp_path, monkeypatch, missing_group
):
    incomplete = json.loads(REPORT.read_text(encoding="utf-8"))
    assisted = incomplete["groups"]["assisted"]
    assisted["n"] = 0
    for levels in assisted["levels"].values():
        levels.update(A=None, B=None)
    if missing_group:
        del incomplete["groups"]["assisted"]
    report_path = tmp_path / "incomplete.json"
    report_path.write_text(json.dumps(incomplete), encoding="utf-8")
    result = compare_csv(tmp_path, monkeypatch, "A,assisted,0\nB,assisted,1\n", report_path)
    coverage = result["human_coverage"]
    assert coverage["survey_cells"] == 2
    assert coverage["comparable_cells"] == 0
    assert coverage["paired_groups"] == []
    assert coverage["missing_model_cells"] == [
        {"variant": "A", "group": "assisted"},
        {"variant": "B", "group": "assisted"},
    ]
    group = result["human_comparison"]["assisted"]
    assert group["A"]["absolute_error_pp"]["with_skill"] is None
    assert group["gap_a_minus_b_pp"] == {"survey": -100, "without_skill": None, "with_skill": None}
