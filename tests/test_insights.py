import copy

import pytest


@pytest.fixture
def report():
    return {
        "scenario": {
            "population": {"senior": 0.6, "young_family": 0.4},
            "variants": {"A": "One", "B": "Two"},
        },
        "population_counts": {"senior": 6, "young_family": 4},
        "report": {
            "A": {
                "n": 6,
                "yes": 3,
                "conversion": 0.5,
                "requested_n": 10,
                "failed_n": 4,
                "confidence_interval": [0.2, 0.8],
                "segments": {"senior": {"name": "Пенсионеры 60+", "n": 6, "yes": 3, "conversion": 0.5}},
                "objections": {"дорого": 3},
                "failure_examples": [],
                "quotes": [
                    {
                        "segment_id": "senior",
                        "segment": "Пенсионеры 60+",
                        "who": "Ольга, 65, Москва",
                        "decision": False,
                        "quote": "Неясные условия",
                    }
                ],
            },
            "B": {
                "n": 10,
                "yes": 2,
                "conversion": 0.2,
                "requested_n": 10,
                "failed_n": 0,
                "confidence_interval": [0.1, 0.5],
                "segments": {
                    "senior": {"name": "Пенсионеры 60+", "n": 6, "yes": 0, "conversion": 0.0},
                    "young_family": {"name": "Молодые семьи с детьми", "n": 4, "yes": 2, "conversion": 0.5},
                },
                "objections": {"дорого": 8},
                "failure_examples": [],
                "quotes": [
                    {
                        "segment_id": "young_family",
                        "segment": "Молодые семьи с детьми",
                        "who": "Ольга, 30, Москва",
                        "decision": True,
                        "quote": "Подходит семье",
                    }
                ],
            },
        },
    }


def test_matrix_distinguishes_zero_agreement_from_missing_answers(report):
    from dvoinik.insights import matrix_rows

    rows = matrix_rows(report)
    assert [(cell["conversion"], cell["n"], cell["leading"]) for cell in rows[0]["cells"]] == [
        (0.5, 6, True),
        (0.0, 6, False),
    ]
    assert [(cell["conversion"], cell["n"], cell["leading"]) for cell in rows[1]["cells"]] == [
        (None, 0, False),
        (0.5, 4, True),
    ]
    assert rows[1]["requested_n"] == 4


def test_segment_focus_uses_own_denominator_and_quotes_without_global_objections(report):
    from dvoinik.insights import segment_report

    original = copy.deepcopy(report)
    focused = segment_report(report, "young_family")
    assert focused["A"]["n"] == 0 and focused["A"]["failed_n"] == 4
    assert focused["A"]["conversion"] is None
    assert focused["A"]["quotes"] == []
    assert focused["B"]["conversion"] == 0.5 and focused["B"]["yes"] == 2 and focused["B"]["n"] == 4
    assert focused["B"]["objections"] == {}
    assert focused["B"]["quotes"][0]["quote"] == "Подходит семье"
    assert report == original


def test_segment_focus_rejects_segment_outside_saved_audience(report):
    from dvoinik.insights import segment_report

    with pytest.raises(ValueError):
        segment_report(report, "student_msk")
