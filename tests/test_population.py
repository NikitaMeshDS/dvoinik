import pytest

from dvoinik.population import build_population


def test_population_preserves_requested_segment_counts():
    twins = build_population(50, {"student_msk": 0.6, "student_reg": 0.4})
    assert sum(t.segment == "student_msk" for t in twins) == 30
    assert sum(t.segment == "student_reg" for t in twins) == 20
    assert len({t.id for t in twins}) == 50
    assert twins == build_population(50, {"student_msk": 0.6, "student_reg": 0.4})


@pytest.mark.parametrize(
    "n,weights",
    [
        (0, {"senior": 1}),
        (-1, {"senior": 1}),
        (5, {}),
        (5, {"senior": 0}),
        (5, {"senior": -1}),
        (5, {"unknown": 1}),
        (5, {"senior": float("nan")}),
    ],
)
def test_invalid_population_is_rejected(n, weights):
    with pytest.raises(ValueError):
        build_population(n, weights)
