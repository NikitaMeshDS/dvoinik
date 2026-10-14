"""Run control exercises real queues, session boundaries and guarded engine cleanup."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from dvoinik.api import create_app
from dvoinik.auth import IDLE_SECONDS, AuthStore
from dvoinik.jobs import JobBusy, Jobs
from dvoinik.runs import RunSettings
from dvoinik.scenarios import SCENARIOS

PASSWORD = "test-password-long"
KEY = "student_card"


@pytest.fixture
def app(tmp_path):
    auth = AuthStore(tmp_path / "control.sqlite3")
    for name in ("alice", "bob"):
        auth.create_user(name, name.title(), PASSWORD)
    app = create_app(auth.path, mode="local")
    yield app
    app.state.jobs.close()


def login(app, name="alice"):
    client = TestClient(app, base_url="http://127.0.0.1")
    response = client.post("/api/login", json={"username": name, "password": PASSWORD})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


def submit(client):
    response = client.post(
        "/api/runs",
        json={
            "scenario_key": KEY,
            "scenario": SCENARIOS[KEY],
            "n": 10,
            "mock": True,
            "seed": 42,
            "concurrency": 1,
        },
    )
    assert response.status_code == 202
    return response.json()["id"]


def wait_job(jobs, token, jid):
    for _ in range(200):
        result = jobs.get(token, jid)
        if result["status"] not in {"queued", "running", "cancelling"}:
            return result
        time.sleep(0.005)
    pytest.fail("worker did not finish")


def test_running_cancel_keeps_capacity_until_cleanup_and_never_saves(app, monkeypatch):
    import dvoinik.jobs as module

    entered, release = threading.Event(), threading.Event()
    original = module.run_experiment

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "run_experiment", blocked)
    alice, bob = login(app), login(app, "bob")
    jobs = Jobs(app.state.auth, workers=1, queue_size=0)
    a, b = alice.cookies["dvoinik_session"], bob.cookies["dvoinik_session"]
    try:
        jid = jobs.submit(a, KEY, SCENARIOS[KEY], RunSettings(n=10))["id"]
        assert entered.wait(2)
        assert jobs.cancel(a, jid)["status"] == "cancelling"
        assert jobs.cancel(a, jid)["status"] == "cancelling"
        assert jobs.active(a)[0]["id"] == jid
        with pytest.raises(JobBusy):
            jobs.submit(b, KEY, SCENARIOS[KEY], RunSettings(n=10))
    finally:
        release.set()
        jobs.close()
    result = jobs.get(a, jid)
    assert result["status"] == "cancelled" and result["record"] is None
    assert not result["saved"] and result["done"] == 0
    assert jobs.active(a) == [] and jobs.active_count == 0
    assert app.state.auth.workspace(a).list_records() == []
    assert jobs.capacity.acquire(blocking=False)
    assert not jobs.capacity.acquire(blocking=False)
    jobs.capacity.release()


def test_queued_cancel_never_executes_and_returns_its_slot_once(app, monkeypatch):
    import dvoinik.jobs as module

    entered, release = threading.Event(), threading.Event()
    calls = []
    original = module.run_experiment

    def blocked(*args, **kwargs):
        calls.append(args[0])
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "run_experiment", blocked)
    alice, bob = login(app), login(app, "bob")
    a, b = alice.cookies["dvoinik_session"], bob.cookies["dvoinik_session"]
    jobs = Jobs(app.state.auth, workers=1, queue_size=1)
    try:
        jobs.submit(a, KEY, SCENARIOS[KEY], RunSettings(n=10))
        assert entered.wait(2)
        jid = jobs.submit(b, KEY, SCENARIOS[KEY], RunSettings(n=10))["id"]
        assert jobs.cancel(b, jid)["status"] == "cancelled"
        assert jobs.cancel(b, jid)["status"] == "cancelled"
        assert jobs.active_count == 1 and jobs.active(b) == []
        assert jobs.capacity.acquire(blocking=False)
        assert not jobs.capacity.acquire(blocking=False)
        jobs.capacity.release()
    finally:
        release.set()
        jobs.close()
    assert len(calls) == 1
    assert jobs.get(b, jid)["record"] is None


def test_discovery_and_cancel_are_cookie_scoped_and_csrf_protected(app, monkeypatch):
    import dvoinik.jobs as module

    entered, release = threading.Event(), threading.Event()
    original = module.run_experiment

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "run_experiment", blocked)
    alice, bob = login(app), login(app, "bob")
    try:
        jid = submit(alice)
        assert entered.wait(2)
        refreshed = TestClient(app, base_url="http://127.0.0.1")
        refreshed.cookies.update(alice.cookies)
        assert refreshed.get("/api/runs").json()["jobs"][0]["id"] == jid
        assert bob.get("/api/runs").json() == {"jobs": []}
        assert bob.post(f"/api/runs/{jid}/cancel").status_code == 404
        assert refreshed.post(f"/api/runs/{jid}/cancel").status_code == 403
        assert TestClient(app, base_url="http://127.0.0.1").get("/api/runs").status_code == 401
        assert alice.post(f"/api/runs/{jid}/cancel").json()["status"] == "cancelling"
    finally:
        release.set()
    result = wait_job(app.state.jobs, alice.cookies["dvoinik_session"], jid)
    assert result["status"] == "cancelled"
    assert alice.get("/api/experiments").json() == {"records": []}


def test_cancel_after_completion_preserves_saved_result(app):
    client = login(app)
    jid = submit(client)
    finished = wait_job(app.state.jobs, client.cookies["dvoinik_session"], jid)
    assert finished["status"] == "completed" and finished["saved"]
    assert client.post(f"/api/runs/{jid}/cancel").json() == finished
    assert client.get("/api/experiments").json()["records"][0] == finished["record"]
    assert client.get("/api/runs").json() == {"jobs": []}


def test_active_discovery_polling_does_not_keep_session_alive(app):
    now = [1000]
    app.state.auth.clock = lambda: now[0]
    client = login(app)
    now[0] += IDLE_SECONDS - 1
    assert client.get("/api/runs").status_code == 200
    now[0] += 2
    assert client.get("/api/runs").status_code == 401
