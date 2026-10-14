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


def test_custom_demo_with_one_objection_does_not_crash():
    scenario = {
        "question": "Подключите?",
        "variants": {"A": "Всегда бесплатно", "B": "Без комиссии"},
        "objections": ["плата"],
    }
    report = simulate(build_population(50, {"student_reg": 1}), scenario, mock=True)
    assert report["A"]["n"] == report["B"]["n"] == 50


@pytest.mark.parametrize("blocked_call", [1, 2])
@pytest.mark.parametrize("control", ["shutdown", "cancel"])
def test_job_control_stops_real_engine_before_next_provider_request(
    tmp_path, monkeypatch, blocked_call, control
):
    import copy
    import threading
    import time

    import dvoinik.engine as engine
    from dvoinik.auth import AuthStore
    from dvoinik.jobs import Jobs
    from dvoinik.runs import RunSettings

    auth = AuthStore(tmp_path / "shutdown.sqlite3")
    owner = auth.create_user("analyst", "Analyst", "test-password-long")
    token = auth.login("analyst", "test-password-long")
    jobs = Jobs(auth, workers=1, queue_size=1)
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
    calls, calls_after_close = [], []

    class Completions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if jobs.closed:
                calls_after_close.append(kwargs)
            if len(calls) == blocked_call:
                entered.set()
                while not release.is_set():
                    await asyncio.sleep(0.001)
            else:
                await asyncio.sleep(0.001)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"decision":true,"probability":1,"objection":null,"quote":"example"}'
                        )
                    )
                ]
            )

    class Client:
        chat = SimpleNamespace(completions=Completions())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(engine, "_client", Client)
    scenario = copy.deepcopy(SCENARIOS["student_card"])
    scenario["variants"].update({"D": "Предложение D", "E": "Предложение E"})
    submitted = jobs.submit(token, "student_card", scenario, RunSettings(n=1000, mock=False, concurrency=1))
    assert entered.wait(3)

    def stop():
        if control == "cancel":
            assert jobs.cancel(token, submitted["id"])["status"] == "cancelling"
            stopped.set()
        else:
            jobs.close()
            stopped.set()

    closer = threading.Thread(target=stop)
    closer.start()
    try:
        for _ in range(100):
            if jobs.closed or jobs.get(token, submitted["id"])["status"] == "cancelling":
                break
            time.sleep(0.01)
        assert jobs.closed or jobs.get(token, submitted["id"])["status"] == "cancelling"
    finally:
        release.set()
        closer.join(5)
        jobs.close()
    assert stopped.is_set()
    assert calls_after_close == []
    assert len(calls) == blocked_call
    result = jobs.get(token, submitted["id"])
    assert result["status"] == ("cancelled" if control == "cancel" else "failed")
    assert result["record"] is None and not result["saved"]
    assert jobs.active_count == 0
    assert auth.workspace(token).list_records() == []
    assert auth.resolve(token).id == owner


def test_mock_access_guard_is_independent_of_ui_progress_throttle(monkeypatch):
    import dvoinik.engine as engine
    from dvoinik.auth import AccessExpired

    original = engine._ask_mock
    revoked, calls, progress = [], [], []

    def guard():
        if revoked:
            raise AccessExpired("Сессия завершена")

    def answer(*args):
        calls.append(1)
        result = original(*args)
        revoked.append(True)
        return result

    monkeypatch.setattr(engine, "_ask_mock", answer)
    scenario = SCENARIOS["student_card"]
    with pytest.raises(AccessExpired):
        engine.simulate(
            build_population(1000, scenario["population"]),
            scenario,
            mock=True,
            guard=guard,
            progress=lambda done, total: progress.append(done),
        )
    assert calls == [1] and progress == []
