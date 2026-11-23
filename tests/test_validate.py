import io

import pytest

from dvoinik.validate import compare, load_survey

REPORT = {
    "A": {"conversion": 0.8, "segments": {"senior": {"conversion": 0.8}, "teen": {"conversion": 0.2}}},
    "B": {"conversion": 0.2, "segments": {"senior": {"conversion": 0.2}, "teen": {"conversion": 0.8}}},
}


def test_empty_survey_has_actionable_error():
    with pytest.raises(ValueError, match="опрос"):
        compare(REPORT, {})


def test_unknown_variant_has_actionable_error():
    with pytest.raises(ValueError, match="Z"):
        compare(REPORT, {("Z", "senior"): 0.5})


def test_ties_are_not_reported_as_perfect_ranking():
    result = compare(REPORT, {("A", "senior"): 0.5, ("B", "senior"): 0.5})
    assert result["spearman_variants"] is None
    assert result["winner_match"] is None


def test_ranking_compares_same_segments_instead_of_overall_population():
    result = compare(REPORT, {("A", "teen"): 0.2, ("B", "teen"): 0.8})
    assert result["mae_conversion"] == 0
    assert result["spearman_variants"] == pytest.approx(1)
    assert result["winner_match"] is True


def test_csv_preserves_sample_weights():
    survey = load_survey(io.StringIO("segment,variant,decision\nsenior,A,1\nsenior,A,0\nteen,A,1\n"))
    assert survey[("A", "senior")] == 0.5
    assert survey.counts[("A", "senior")] == 2
    result = compare(REPORT, survey)
    assert result["mae_conversion"] == pytest.approx((0.3 * 2 + 0.8) / 3)


@pytest.mark.parametrize(
    "survey, reason",
    [
        ({("A", "senior"): 0.8, ("B", "teen"): 0.2}, "different_mix"),
        ({("A", "senior"): 0.8}, "missing_variants"),
    ],
)
def test_incomparable_surveys_keep_cell_errors_without_a_leader(survey, reason):
    result = compare(REPORT, survey, baseline={"A": 0.8, "B": 0.2})
    assert result["ranking_unavailable"] == reason
    assert result["matched_cells"] == len(survey)
    assert result["mae_conversion"] == sum(c["error"] for c in result["cells"]) / len(survey)
    assert result["actual_winners"] == result["predicted_winners"] == []
    assert result["winner_match"] is result["spearman_variants"] is None
    assert "baseline" not in result


def test_rankings_require_equal_segment_shares_even_if_all_segments_are_covered():
    csv_header = "segment,variant,decision\n"
    balanced = "senior,A,1\nteen,A,1\nsenior,B,0\nsenior,B,0\nteen,B,0\nteen,B,0\n"
    result = compare(REPORT, load_survey(io.StringIO(csv_header + balanced)))
    assert "ranking_unavailable" not in result
    assert result["actual_winners"] == ["A"]
    shifted = compare(REPORT, load_survey(io.StringIO(csv_header + balanced + "teen,B,0\n")))
    assert shifted["ranking_unavailable"] == "different_mix"
    assert shifted["matched_cells"] == 4


@pytest.mark.parametrize(
    "csv",
    [
        "wrong,variant,decision\nsenior,A,1\n",
        "segment,variant,decision\n",
        "segment,variant,decision\nsenior,A,2\n",
        "segment,variant,decision\n,A,1\n",
    ],
)
def test_invalid_csv_is_rejected(csv):
    with pytest.raises(ValueError):
        load_survey(io.StringIO(csv))


def test_survey_contrast_reports_uncertainty_only_with_random_single_offer_assignment():
    from dvoinik.validate import SurveyRates

    report = {
        "A": {"segments": {"senior": {"n": 10, "conversion": 0.6}}},
        "B": {"segments": {"senior": {"n": 10, "conversion": 0.4}}},
    }
    a, b = ("A", "senior"), ("B", "senior")
    tiny = SurveyRates({a: 1, b: 0}, {a: 1, b: 1})
    result = compare(report, tiny, assignment="random_one")
    (contrast,) = result["segment_contrasts"]
    assert contrast["pair"] == ["A", "B"] and contrast["segment"] == "senior"
    low, high = contrast["interval_95_pp"]
    assert low < 0 <= high and contrast["direction"] == "uncertain"
    clear = SurveyRates({a: 0.9, b: 0.3}, {a: 10, b: 10})
    assert compare(report, clear, assignment="random_one")["segment_contrasts"][0]["direction"] == "A"
    for assignment in (None, "all_variants", "one_nonrandom", "unknown"):
        assert "segment_contrasts" not in compare(report, clear, assignment=assignment)


def test_mae_interval_reflects_survey_size_at_same_observed_error():
    header = "segment,variant,decision\n"
    rows = "senior,A,1\nteen,A,0\n"
    small = load_survey(io.StringIO(header + rows))
    large = load_survey(io.StringIO(header + rows * 100))
    first = compare(REPORT, small, assignment="random_one")
    second = compare(REPORT, large, assignment="random_one")
    assert [first["mae_conversion"], second["mae_conversion"]] == pytest.approx([0.2, 0.2])
    low, high = first["mae_interval_95_pp"]
    large_low, large_high = second["mae_interval_95_pp"]
    assert 0 == low < large_low < 20 <= large_high < high <= 100
    assert "mae_interval_95_pp" not in compare(REPORT, large, assignment="all_variants")
    assert "mae_interval_95_pp" not in compare(REPORT, dict(large), assignment="random_one")


def test_baseline_requires_the_audience_declared_in_its_snapshot():
    rates = {"A": 0.4, "B": 0.6}
    subset = {("A", "teen"): 0.2, ("B", "teen"): 0.8}
    result = compare(REPORT, subset, baseline=rates, baseline_population={"senior": 0.5, "teen": 0.5})
    assert "baseline" not in result
    assert result["baseline_unavailable"] == "different_population"
    assert result["mae_conversion"] == 0 and result["winner_match"] is True

    result = compare(REPORT, subset, baseline=rates)
    assert "baseline" not in result and result["baseline_unavailable"] == "unknown_population"

    result = compare(REPORT, subset, baseline=rates, baseline_population={"teen": 1})
    assert result["baseline"]["baseline_mae_variants"] == pytest.approx(0.2)
