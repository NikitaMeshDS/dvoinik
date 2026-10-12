import asyncio
from types import SimpleNamespace

import pytest

from dvoinik.engine import aggregate, simulate
from dvoinik.population import build_population
from dvoinik.scenarios import SCENARIOS


def test_failed_model_responses_do_not_become_rejections():
    twins = build_population(3, {"senior": 1})
    report = aggregate(
        [
            (twins[0], {"decision": True, "probability": 0.8, "objection": None, "quote": "Да"}),
            (twins[1], {"decision": False, "probability": 0.1, "objection": "плата", "quote": "Нет"}),
            (twins[2], {"error": "Invalid JSON"}),
        ]
    )
    assert report["conversion"] == 0.5
    assert report["n"] == 2
    assert report["failed_n"] == 1
    assert report["requested_n"] == 3
    assert report["objections"] == {"плата": 1}
    assert report["confidence_interval"][0] < 0.5 < report["confidence_interval"][1]


@pytest.mark.parametrize(
    "content",
    [
        '{"decision":"false","probability":0.5,"quote":"Нет"}',
        '{"decision":true,"probability":2,"quote":"Да"}',
        '{"decision":true,"probability":true,"quote":"Да"}',
        '{"decision":true,"probability":NaN,"quote":"Да"}',
        "[]",
        "null",
        "not json",
    ],
)
def test_malformed_llm_answer_is_recorded_as_failure(content):
    from dvoinik.engine import _ask_llm

    class Completions:
        async def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    twin = build_population(1, {"senior": 1})[0]
    result = asyncio.run(
        _ask_llm(client, "test", twin, SCENARIOS["senior_deposit"], "test", asyncio.Semaphore(1))
    )
    assert result.get("error")
    assert "decision" not in result


def test_mock_is_reproducible_and_reports_progress():
    scenario = SCENARIOS["student_card"]
    twins = build_population(50, scenario["population"])
    progress = []
    report = simulate(
        twins, scenario, mock=True, seed=7, progress=lambda done, total: progress.append((done, total))
    )
    assert report == simulate(twins, scenario, mock=True, seed=7)
    assert progress[-1] == (150, 150)
    assert all(r["n"] == 50 and r["failed_n"] == 0 for r in report.values())


def test_quotes_include_acceptance_and_rejection():
    twins = build_population(20, {"senior": 1})
    rows = [
        (t, {"decision": t.id >= 10, "objection": "плата" if t.id < 10 else None, "quote": str(t.id)})
        for t in twins
    ]
    assert {q["decision"] for q in aggregate(rows)["quotes"]} == {True, False}


@pytest.mark.parametrize("variant", ["B", "C"])
def test_mock_does_not_assign_fee_objection_to_unconditionally_free_offer(variant):
    import random

    from dvoinik.engine import _ask_mock

    scenario = SCENARIOS["student_card"]
    twin = build_population(1, {"student_reg": 1})[0]
    rng = random.Random(9)
    answers = [_ask_mock(rng, twin, scenario, scenario["variants"][variant]) for _ in range(200)]
    assert any(not a["decision"] for a in answers)
    assert all(a["objection"] != "плата и условия" for a in answers)


def test_mock_does_not_reject_cashback_categories_when_no_cashback_is_offered():
    import random

    from dvoinik.engine import _ask_mock

    scenario = SCENARIOS["student_card"]
    twin = build_population(1, {"student_reg": 1})[0]
    rng = random.Random(9)
    answers = [_ask_mock(rng, twin, scenario, scenario["variants"]["C"]) for _ in range(200)]
    assert all(a["objection"] != "кэшбэк не на мои траты" for a in answers)
