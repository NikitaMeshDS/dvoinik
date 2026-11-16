"""Recovery settings are immutable, session-scoped snapshots of submitted work."""

import copy
import threading
import time

import pytest

from dvoinik.auth import AuthStore
from dvoinik.jobs import JobMissing, Jobs
from dvoinik.runs import RunSettings
from dvoinik.scenarios import SCENARIOS


def wait_finished(jobs, token, jid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = jobs.get(token, jid)
        if value["status"] not in {"queued", "running", "cancelling"}:
            return value
        time.sleep(0.005)
    pytest.fail("Job did not finish")


@pytest.mark.parametrize("cancel", [False, True])
def test_failure_and_cancellation_retain_private_immutable_request(tmp_path, monkeypatch, cancel):
    import dvoinik.jobs as module

    auth = AuthStore(tmp_path / "recovery.sqlite3")
    for name in ("alice", "bob"):
        auth.create_user(name, name.title(), "test-password-long")
    alice, bob = auth.login("alice", "test-password-long"), auth.login("bob", "test-password-long")
    entered, release = threading.Event(), threading.Event()
    received = []

    def fail(key, scenario, settings, **kwargs):
        received.append(copy.deepcopy(scenario))
        entered.set()
        assert release.wait(5)
        kwargs["guard"]()
        raise RuntimeError("Provider credentials should never be exposed")

    monkeypatch.setattr(module, "run_experiment", fail)
    scenario = copy.deepcopy(SCENARIOS["senior_deposit"])
    scenario["origin"] = {
        "kind": "hypothesis",
        "record_id": "parent",
        "title": "Source",
        "lever": "Цена",
        "change": "Убрать плату",
        "variant": "B",
        "hypothesis_id": "a" * 64,
    }
    original = copy.deepcopy(scenario)
    settings = RunSettings(n=50, mock=True, seed=123, concurrency=3)
    jobs = Jobs(auth, workers=1, queue_size=0)
    try:
        submitted = jobs.submit(alice, "custom", scenario, settings)
        assert entered.wait(2)
        expected = {
            "scenario_key": "custom",
            "scenario": original,
            "n": 50,
            "mock": True,
            "seed": 123,
            "concurrency": 3,
        }
        assert submitted["request"] == expected
        assert set(submitted["request"]) == {"scenario_key", "scenario", "n", "mock", "seed", "concurrency"}
        scenario["variants"]["A"] = "caller mutation"
        submitted["request"]["scenario"]["variants"]["B"] = "public mutation"
        submitted["request"]["seed"] = 0
        assert jobs.get(alice, submitted["id"])["request"] == expected
        assert received == [original]
        with pytest.raises(JobMissing):
            jobs.get(bob, submitted["id"])
        assert jobs.active(bob) == []
        if cancel:
            jobs.cancel(alice, submitted["id"])
        release.set()
        result = wait_finished(jobs, alice, submitted["id"])
        assert result["status"] == ("cancelled" if cancel else "failed")
        assert result["record"] is None and not result["saved"]
        assert result["request"] == expected
        assert "credentials" not in result["error"]
        assert "token" not in result and "owner" not in result
        result["request"]["scenario"]["origin"]["hypothesis_id"] = "b" * 64
        assert jobs.get(alice, submitted["id"])["request"] == expected
    finally:
        release.set()
        jobs.close()
