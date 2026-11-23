import hashlib
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


def compare_csv(tmp_path, monkeypatch, rows, report_path=REPORT, extra_args=()):
    survey = tmp_path / "responses.csv"
    key = "slot" if "--assignments" in extra_args else "variant"
    survey.write_text(f"{key},segment,decision\n" + rows, encoding="utf-8")
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
            *extra_args,
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
    assert "survey_gap_interval_95_pp" not in groups["assisted"]
    assert groups["independent"]["survey_gap_direction"] == "uncertain"
    assert groups["independent"]["model_direction_match"] == {"without_skill": None, "with_skill": None}
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


def test_frozen_baseline_is_compared_on_the_same_survey_cells(tmp_path, monkeypatch):
    baseline = {
        "model": "qwen/qwen3-vl-4b",
        "offers": deposit_digital_skill.OFFERS,
        "question": deposit_digital_skill.QUESTION,
        "groups": deposit_digital_skill.GROUPS,
        "rates": dict.fromkeys(deposit_digital_skill.GROUPS, {"A": 0.75, "B": 0.5}),
    }
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    report = compare_csv(
        tmp_path, monkeypatch, "A,independent,1\nB,independent,0\n", extra_args=("--baseline", str(path))
    )
    cells = report["human_comparison"]["independent"]
    assert report["simple_prompt_baseline"] == baseline
    assert cells["A"]["absolute_error_pp"]["simple_prompt"] == 25
    assert cells["gap_a_minus_b_pp"]["simple_prompt"] == 25
    assert cells["gap_a_minus_b_error_pp"]["simple_prompt"] == 75
    assert report["human_coverage"]["survey_cells"] == 2
    with pytest.raises(ValueError, match="ту же модель"):
        deposit_digital_skill.baseline_rates({**baseline, "question": "Другой вопрос"}, baseline["model"])


def test_survey_gap_matches_newcombe_published_example(tmp_path, monkeypatch):
    # Table II(b), method 10: 9/10 versus 3/10.
    rows = "A,independent,1\n" * 9 + "A,independent,0\n"
    rows += "B,independent,1\n" * 3 + "B,independent,0\n" * 7
    result = compare_csv(tmp_path, monkeypatch, rows)
    cells = result["human_comparison"]["independent"]
    assert cells["A"]["yes"] == 9 and cells["B"]["yes"] == 3
    assert cells["survey_gap_interval_95_pp"] == pytest.approx([17.05, 80.90], abs=0.01)
    assert cells["survey_gap_direction"] == "A"
    assert cells["model_direction_match"]["with_skill"] is True
    assert cells["model_direction_match"]["without_skill"] is False


def test_slot_log_reconciles_variants_and_preserves_missing_answers(tmp_path, monkeypatch):
    assignments = tmp_path / "assignments.csv"
    assignments.write_text("slot,variant\n1,B\n2,A\n3,B\n4,A\n5,A\n6,B\n", encoding="utf-8")
    checksum = hashlib.sha256(assignments.read_bytes()).hexdigest()
    result = compare_csv(
        tmp_path,
        monkeypatch,
        "2,assisted,0\n1,assisted,1\n3,,\n4,,1\n",
        extra_args=("--assignments", str(assignments), "--assignment-sha256", checksum),
    )
    assert result["assignment_reconciliation"]["assignments_sha256"] == checksum
    counts = result["assignment_reconciliation"]["counts"]
    assert counts["A"] == {"planned": 3, "issued": 2, "valid": 1, "missing": 0, "unclassified": 1}
    assert counts["B"] == {"planned": 3, "issued": 2, "valid": 1, "missing": 1, "unclassified": 0}
    assert result["human_coverage"]["survey_n"] == 2
    assert result["human_comparison"]["assisted"]["gap_a_minus_b_pp"]["survey"] == -100


@pytest.mark.parametrize(
    "rows,message",
    [
        ("1,assisted,1\n1,assisted,0\n", "повторяется"),
        ("3,assisted,1\n", "без пропусков позиций"),
        ("5,assisted,1\n", "нет в списке назначений"),
    ],
)
def test_slot_log_rejects_invalid_issued_positions(tmp_path, monkeypatch, capsys, rows, message):
    assignments = tmp_path / "assignments.csv"
    assignments.write_text("slot,variant\n1,B\n2,A\n3,B\n4,A\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        compare_csv(tmp_path, monkeypatch, rows, extra_args=("--assignments", str(assignments)))
    assert exc.value.code == 2
    assert message in capsys.readouterr().err
    assert not (tmp_path / "comparison.json").exists()


def test_slot_log_rejects_checksum_changed_after_approval(tmp_path, monkeypatch, capsys):
    assignments = tmp_path / "assignments.csv"
    assignments.write_text("slot,variant\n1,B\n2,A\n", encoding="utf-8")
    expected = hashlib.sha256(assignments.read_bytes()).hexdigest()
    assignments.write_text("slot,variant\n1,A\n2,B\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        compare_csv(
            tmp_path,
            monkeypatch,
            "1,independent,1\n",
            extra_args=("--assignments", str(assignments), "--assignment-sha256", expected),
        )
    assert exc.value.code == 2
    assert "SHA-256 списка назначений отличается" in capsys.readouterr().err


def test_pilot_summary_marks_rehearsal_and_keeps_missing_groups_visible(tmp_path, monkeypatch):
    assignments = tmp_path / "assignments.csv"
    assignments.write_text("slot,variant\n1,A\n2,B\n3,A\n4,B\n", encoding="utf-8")
    summary = tmp_path / "summary.md"
    result = compare_csv(
        tmp_path,
        monkeypatch,
        "1,assisted,1\n2,assisted,0\n3,,\n",
        extra_args=("--assignments", str(assignments), "--summary", str(summary), "--rehearsal"),
    )

    text = summary.read_text(encoding="utf-8")
    assert result["survey_input_kind"] == "rehearsal"
    assert "Синтетические данные" in text
    assert "| A | 2 | 2 | 1 | 1 | 0 |" in text
    assert "| С помощью | 1/1 (100,0%) | 0/1 (0,0%) |" in text
    assert "Неопределённо" in text
    assert "| Без интернета | — | — |" in text
    assert "slot,segment,decision" not in text


def test_saved_rehearsal_exports_again_without_new_survey_or_losing_label(tmp_path, monkeypatch):
    compare_csv(tmp_path, monkeypatch, "A,assisted,1\nB,assisted,0\n", extra_args=("--rehearsal",))
    source = tmp_path / "comparison.json"
    original = source.read_bytes()
    summary = tmp_path / "exported.md"
    monkeypatch.setattr(
        sys,
        "argv",
        ["deposit_digital_skill", "--summary-from", str(source), "--summary", str(summary)],
    )
    assert deposit_digital_skill.main() == 0
    assert "**Репетиция. Синтетические данные.**" in summary.read_text(encoding="utf-8")
    assert source.read_bytes() == original


def test_reanalysis_cannot_drop_rehearsal_label_from_saved_comparison(tmp_path, monkeypatch, capsys):
    compare_csv(tmp_path, monkeypatch, "A,assisted,1\nB,assisted,0\n", extra_args=("--rehearsal",))
    source = tmp_path / "comparison.json"
    output = tmp_path / "recompared.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deposit_digital_skill",
            "--compare",
            str(source),
            "--survey",
            str(tmp_path / "responses.csv"),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        deposit_digital_skill.main()
    assert exc.value.code == 2
    assert "--rehearsal" in capsys.readouterr().err
    assert not output.exists()
