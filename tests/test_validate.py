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
