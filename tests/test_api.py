"""HTTP boundary checks use isolated accounts, real SQLite, and real mock runs."""

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from dvoinik.api import create_app
from dvoinik.auth import IDLE_SECONDS, AuthStore
from dvoinik.scenarios import SCENARIOS
from dvoinik.storage import ExperimentStore, StorageError

PASSWORD = "test-password-long"
KEY = next(iter(SCENARIOS))


@pytest.fixture
def app(tmp_path):
    path = tmp_path / "api.sqlite3"
    auth = AuthStore(path)
    auth.create_user("admin", "Admin", PASSWORD, "admin")
    auth.create_user("alice", "Alice", PASSWORD)
    auth.create_user("bob", "Bob", PASSWORD)
    app = create_app(path, mode="local")
    yield app
    app.state.jobs.close()


def login(app, username="alice"):
    client = TestClient(app, base_url="http://127.0.0.1")
    response = client.post("/api/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


def start(client, **changes):
    payload = {
        "scenario_key": KEY,
        "scenario": SCENARIOS[KEY],
        "n": 10,
        "mock": True,
        "seed": 42,
        "concurrency": 2,
    }
    payload.update(changes)
    return client.post("/api/runs", json=payload)


def completed(client, job_id):
    for _ in range(150):
        result = client.get(f"/api/runs/{job_id}")
        assert result.status_code == 200, result.text
        if result.json()["status"] not in {"queued", "running"}:
            return result.json()
        time.sleep(0.01)
    pytest.fail("run did not complete")


def run(client):
    response = start(client)
    assert response.status_code == 202, response.text
    result = completed(client, response.json()["id"])
    assert result["status"] == "completed" and result["saved"]
    assert result["done"] == result["total"] == 10 * len(SCENARIOS[KEY]["variants"])
    return result


def csv_for(record, decision=1):
    sid = next(iter(record["report"]["A"]["segments"]))
    return f"segment,variant,decision\n{sid},A,{decision}\n"


def test_session_boundary_and_csrf(app):
    public = TestClient(app, base_url="http://127.0.0.1")
    assert public.get("/api/experiments").status_code == 401
    assert public.get("/api/session").status_code == 401
    assert (
        public.post(
            "/api/login",
            headers={"Origin": "https://evil.example"},
            json={"username": "alice", "password": PASSWORD},
        ).status_code
        == 403
    )
    client = login(app)
    session = client.get("/api/session")
    assert set(session.json()) == {"user", "csrf_token", "mode", "model", "default_mock"}
    assert "token" not in session.json()
    cookie = (
        client.post("/api/login", json={"username": "alice", "password": PASSWORD})
        .headers["set-cookie"]
        .lower()
    )
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    client.headers.pop("X-CSRF-Token")
    assert start(client).status_code == 403
    client.headers["X-CSRF-Token"] = client.get("/api/session").json()["csrf_token"]
    assert (
        client.post(
            "/api/preview",
            headers={"Origin": "http://evil.example"},
            json={"n": 10, "population": SCENARIOS[KEY]["population"]},
        ).status_code
        == 403
    )
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/session").status_code == 401


def test_catalog_and_population_are_server_validated(app):
    client = login(app)
    catalog = client.get("/api/catalog").json()
    assert set(catalog["scenarios"]) == set(SCENARIOS) | {"custom"}
    assert set(catalog["sources"]["segments"]) <= set(catalog["segments"])
    assert catalog["sources"]["gaps"]
    preview = client.post("/api/preview", json={"n": 7, "population": {"student_msk": 1, "student_reg": 2}})
    assert sum(preview.json()["counts"].values()) == 7
    assert preview.json()["shares"]["student_reg"] == pytest.approx(2 / 3)
    for value in [True, -1, 1.5, 10001]:
        response = start(client, n=value)
        assert response.status_code == 422 and isinstance(response.json()["detail"], str)
    assert client.post("/api/import", json={"content": "not JSON"}).status_code == 422


def test_owner_and_session_isolation_and_admin(app):
    alice, bob, admin = login(app), login(app, "bob"), login(app, "admin")
    result = run(alice)
    rid, jid = result["record"]["id"], result["id"]
    assert alice.get(f"/api/experiments/{rid}").json()["id"] == rid
    for other in [bob, admin, login(app)]:
        assert other.get(f"/api/runs/{jid}").status_code == 404
    for other in [bob, admin]:
        assert other.get(f"/api/experiments/{rid}").status_code == 404
        assert (
            other.post("/api/export", json={"record_id": rid, "format": "json", "kind": "record"}).status_code
            == 404
        )
    assert bob.get("/api/users").status_code == 403
    users = admin.get("/api/users").json()["users"]
    assert all("password_hash" not in user for user in users)
    alice_id = next(user["id"] for user in users if user["username"] == "alice")
    assert admin.put(f"/api/users/{alice_id}/active", json={"active": False}).status_code == 200
    assert alice.get("/api/experiments").status_code == 401


def test_sample_cache_import_compare_and_private_download(app):
    client = login(app)
    sample = client.get(f"/api/sample/{KEY}").json()
    assert sample["sample"]
    assert client.get(f"/api/sample/{KEY}").json()["id"] == sample["id"]
    assert client.get("/api/experiments").json() == {"records": []}
    exported = client.post(
        "/api/export", json={"record_id": sample["id"], "format": "json", "kind": "record"}
    ).json()["url"]
    assert client.head(exported).status_code == 200
    assert client.get(exported).json()["id"] == sample["id"]
    assert client.get(exported).status_code == 410
    imported = client.post("/api/import", json={"content": json.dumps(sample)}).json()
    assert imported["id"] != sample["id"] and imported["import_origin_id"] == sample["id"]
    comparison = client.post("/api/compare", json={"left_id": sample["id"], "right_id": imported["id"]})
    assert set(comparison.json()) == {"left", "right", "comparison"}
    link = client.post(
        "/api/compare/export", json={"left_id": sample["id"], "right_id": imported["id"]}
    ).json()["url"]
    assert client.get(link).json()["left"]["id"] == sample["id"]
    link = client.post(
        "/api/export", json={"record_id": imported["id"], "format": "csv", "kind": "record"}
    ).json()["url"]
    client.post("/api/logout")
    assert client.get(link).status_code == 410


def test_validation_cas_conflict_preserves_exportable_preview(app):
    client, second = login(app), login(app)
    record = run(client)["record"]
    endpoint = f"/api/experiments/{record['id']}/validation"
    first = client.post(endpoint + "/preview", json={"csv": csv_for(record)}).json()
    other = second.post(endpoint + "/preview", json={"csv": csv_for(record, 0)}).json()
    assert first["base_validation"] is None
    assert client.get(f"/api/experiments/{record['id']}").json().get("validation") is None
    saved = client.put(endpoint, json={"csv": csv_for(record), "base_validation": None})
    assert saved.status_code == 200 and saved.json()["validation"]["cells"][0]["yes"] == 1
    conflict = second.put(
        endpoint, json={"csv": csv_for(record, 0), "base_validation": other["base_validation"]}
    )
    assert conflict.status_code == 409
    link = second.post(
        "/api/export",
        json={
            "record_id": record["id"],
            "kind": "validation",
            "format": "json",
            "preview_id": other["preview_id"],
        },
    ).json()["url"]
    assert second.get(link).json()["cells"][0]["actual"] == 0
    assert client.get(f"/api/experiments/{record['id']}").json()["validation"]["cells"][0]["yes"] == 1


def test_save_failure_retains_original_session_retry_and_export(app, monkeypatch):
    client = login(app)
    original = ExperimentStore.save
    monkeypatch.setattr(
        ExperimentStore, "save", lambda *a, **k: (_ for _ in ()).throw(StorageError("disk unavailable"))
    )
    response = start(client)
    result = completed(client, response.json()["id"])
    assert result["status"] == "completed" and not result["saved"] and result["error"] == "disk unavailable"
    endpoint = f"/api/runs/{result['id']}"
    assert login(app).post(endpoint + "/export", json={"format": "json", "kind": "record"}).status_code == 404
    link = client.post(endpoint + "/export", json={"format": "json", "kind": "record"}).json()["url"]
    assert client.get(link).json()["id"] == result["record"]["id"]
    monkeypatch.setattr(ExperimentStore, "save", original)
    assert client.post(endpoint + "/retry").json()["saved"]
    assert len(client.get("/api/experiments").json()["records"]) == 1


def test_revoke_during_engine_prevents_persist(app, monkeypatch):
    import dvoinik.jobs as jobs

    original = jobs.run_experiment
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(jobs, "run_experiment", blocked)
    client = login(app)
    jid = start(client).json()["id"]
    assert entered.wait(2)
    client.post("/api/logout")
    release.set()
    for _ in range(100):
        if not app.state.jobs.active_count:
            break
        time.sleep(0.01)
    fresh = login(app)
    assert fresh.get(f"/api/runs/{jid}").status_code == 404
    assert fresh.get("/api/experiments").json() == {"records": []}


def test_demo_forces_mock_and_poll_does_not_touch_idle(tmp_path):
    app = create_app(tmp_path / "demo.sqlite3", mode="demo")
    client = TestClient(app, base_url="http://127.0.0.1")
    assert client.get("/api/session", headers={"Origin": "http://foreign.example"}).status_code == 403
    now = [1000]
    app.state.auth.clock = lambda: now[0]
    session = client.get("/api/session")
    client.headers["X-CSRF-Token"] = session.json()["csrf_token"]
    jid = start(client, mock=False).json()["id"]
    assert completed(client, jid)["record"]["mock"]
    now[0] += IDLE_SECONDS - 1
    assert client.get(f"/api/runs/{jid}").status_code == 200
    now[0] += 2
    assert client.get(f"/api/runs/{jid}").status_code == 401
    app.state.jobs.close()


def test_queue_is_bounded_and_only_two_workers_execute(app, monkeypatch):
    import dvoinik.jobs as jobs

    original = jobs.run_experiment
    release, two_entered = threading.Event(), threading.Event()
    running, peak = [0], [0]
    lock = threading.Lock()

    def blocked(*args, **kwargs):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
            if running[0] == 2:
                two_entered.set()
        try:
            assert release.wait(5)
            return original(*args, **kwargs)
        finally:
            with lock:
                running[0] -= 1

    monkeypatch.setattr(jobs, "run_experiment", blocked)
    clients = [login(app), login(app, "bob"), login(app, "admin")]
    for index in range(8):
        name = f"user{index}"
        app.state.auth.create_user(name, name, PASSWORD)
        clients.append(login(app, name))
    try:
        responses = [start(client) for client in clients]
        assert [response.status_code for response in responses] == [202] * 10 + [409]
        assert two_entered.wait(2) and peak[0] == 2
        assert start(clients[0]).status_code == 409
    finally:
        release.set()
    for client, response in zip(clients[:10], responses[:10]):
        assert completed(client, response.json()["id"])["saved"]
    assert peak[0] == 2


def test_exports_require_same_cookie_and_expire(app):
    client, other = login(app), login(app)
    record = run(client)["record"]

    def issue(kind="record", format="json"):
        response = client.post(
            "/api/export", json={"record_id": record["id"], "kind": kind, "format": format}
        )
        assert response.status_code == 200, response.text
        return response.json()["url"]

    link = issue()
    assert other.get(link).status_code == 410
    assert TestClient(app, base_url="http://127.0.0.1").get(link).status_code == 410
    assert client.get(link).status_code == 200
    assert "decision" in client.get(issue("survey-template", "csv")).text
    now = app.state.auth.clock()
    link = issue()
    app.state.auth.clock = lambda: now + 901
    assert client.get(link).status_code == 410


def test_unavailable_storage_logout_and_invalid_payloads_are_errors(app, monkeypatch):
    client = login(app)
    original = app.state.auth.logout

    def fail_logout(token):
        from dvoinik.auth import AuthError

        raise AuthError("Хранилище доступа недоступно.")

    monkeypatch.setattr(app.state.auth, "logout", fail_logout)
    response = client.post("/api/logout")
    assert response.status_code >= 400
    assert "set-cookie" not in response.headers
    assert client.get("/api/session").status_code == 200
    monkeypatch.setattr(app.state.auth, "logout", original)
    monkeypatch.setattr(
        ExperimentStore, "list_records", lambda *a: (_ for _ in ()).throw(StorageError("archive unavailable"))
    )
    response = client.get("/api/experiments")
    assert response.status_code == 503 and response.json()["detail"] == "archive unavailable"
    assert start(client, owner_id="bob").status_code == 422
    assert client.post("/api/import", json={"content": "x" * (5 * 1024 * 1024 + 1)}).status_code == 422
    assert client.post("/api/preview", json={"population": {"student_msk": -1}, "n": 10}).status_code == 422
    assert client.get("/api/missing").json()["detail"] == "Not Found"


def test_static_spa_does_not_expose_private_routes(tmp_path):
    root = tmp_path / "static"
    root.mkdir()
    (root / "index.html").write_text("<h1>Workspace</h1>")
    (root / "app.js").write_text("console.log('local')")
    app = create_app(tmp_path / "static.sqlite3", mode="local", static_dir=root)
    client = TestClient(app, base_url="http://127.0.0.1")
    assert "Workspace" in client.get("/").text
    assert "Workspace" in client.get("/experiments/record").text
    assert "local" in client.get("/app.js").text
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/api/experiments").status_code == 401
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 403
    app.state.jobs.close()


def test_insights_use_server_segment_metrics_and_owner_access(app):
    from dvoinik.insights import segment_report

    client, foreign = login(app), login(app, "bob")
    record = client.get(f"/api/sample/{KEY}").json()
    sid = next(iter(record["scenario"]["population"]))
    response = client.post("/api/insights", json={"record_id": record["id"], "segment": sid})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["report"] == segment_report(record, sid)
    assert data["quality"]["kind"] == "demo"
    assert all(
        variant["objections"] == record["report"][vid]["segments"].get(sid, {}).get("objections", {})
        for vid, variant in data["report"].items()
    )
    assert (
        client.post("/api/insights", json={"record_id": record["id"], "segment": "all"}).json()["report"]
        == record["report"]
    )
    assert (
        client.post("/api/insights", json={"record_id": record["id"], "segment": "foreign"}).status_code
        == 422
    )
    assert (
        foreign.post("/api/insights", json={"record_id": record["id"], "segment": "all"}).status_code == 404
    )


def test_pending_record_supports_insights_and_regular_export(app, monkeypatch):
    client = login(app)
    monkeypatch.setattr(ExperimentStore, "save", lambda *a, **k: (_ for _ in ()).throw(StorageError("full")))
    response = start(client)
    record = completed(client, response.json()["id"])["record"]
    assert client.post("/api/insights", json={"record_id": record["id"], "segment": "all"}).status_code == 200
    link = client.post("/api/export", json={"record_id": record["id"], "kind": "record", "format": "json"})
    assert link.status_code == 200
    assert client.get(link.json()["url"]).json()["id"] == record["id"]
    assert (
        login(app).post("/api/insights", json={"record_id": record["id"], "segment": "all"}).status_code
        == 404
    )


def test_revocation_before_response_withholds_private_payload(app, monkeypatch):
    client = login(app)
    record = run(client)["record"]
    original = ExperimentStore.get_record

    def revoke_after_read(store, rid):
        result = original(store, rid)
        app.state.auth.logout(client.cookies["dvoinik_session"])
        return result

    monkeypatch.setattr(ExperimentStore, "get_record", revoke_after_read)
    response = client.get(f"/api/experiments/{record['id']}")
    assert response.status_code == 401
    assert "scenario" not in response.json()


def test_pending_export_works_when_archive_cannot_be_read(app, monkeypatch):
    client = login(app)
    monkeypatch.setattr(
        ExperimentStore, "save", lambda *a, **k: (_ for _ in ()).throw(StorageError("offline"))
    )
    result = completed(client, start(client).json()["id"])
    monkeypatch.setattr(
        ExperimentStore, "get_record", lambda *a, **k: (_ for _ in ()).throw(StorageError("offline"))
    )
    response = client.post(
        "/api/export", json={"record_id": result["record"]["id"], "kind": "record", "format": "json"}
    )
    assert response.status_code == 200, response.text
    assert client.get(response.json()["url"]).json()["id"] == result["record"]["id"]


def test_conflict_preview_download_contains_full_server_snapshot(app):
    client, second = login(app), login(app)
    record = run(client)["record"]
    endpoint = f"/api/experiments/{record['id']}/validation"
    preview = second.post(endpoint + "/preview", json={"csv": csv_for(record, 0)})
    assert preview.status_code == 200
    assert client.put(endpoint, json={"csv": csv_for(record, 1), "base_validation": None}).status_code == 200
    assert second.put(endpoint, json={"csv": csv_for(record, 0), "base_validation": None}).status_code == 409
    body = {
        "record_id": record["id"],
        "format": "json",
        "kind": "preview",
        "preview_id": preview.json()["preview_id"],
    }
    exported = second.post("/api/export", json=body)
    assert exported.status_code == 200, exported.text
    snapshot = second.get(exported.json()["url"]).json()
    assert snapshot["id"] == record["id"] and snapshot["validation"]["cells"][0]["yes"] == 0
    body["kind"] = "record"
    saved = second.post("/api/export", json=body)
    assert second.get(saved.json()["url"]).json()["validation"]["cells"][0]["yes"] == 1


def test_cached_sample_reads_latest_saved_validation(app):
    client, second = login(app), login(app)
    record = client.get(f"/api/sample/{KEY}").json()
    endpoint = f"/api/experiments/{record['id']}/validation"
    first = client.put(endpoint, json={"csv": csv_for(record, 1), "base_validation": None}).json()
    updated = second.put(endpoint, json={"csv": csv_for(record, 0), "base_validation": first["validation"]})
    assert updated.status_code == 200
    assert client.get(f"/api/experiments/{record['id']}").json()["validation"]["cells"][0]["yes"] == 0


def test_admin_user_data_errors_do_not_end_session(app):
    client = login(app, "admin")
    admin_id = client.get("/api/session").json()["user"]["id"]
    assert client.put(f"/api/users/{admin_id}/active", json={"active": False}).status_code == 422
    assert client.put("/api/users/unknown/active", json={"active": False}).status_code == 404
    assert client.get("/api/session").status_code == 200


def test_unsaved_recovery_records_are_not_evicted_by_new_runs(app, monkeypatch):
    client, other = login(app), login(app, "bob")
    app.state.jobs.retained = 1
    original = ExperimentStore.save
    monkeypatch.setattr(
        ExperimentStore, "save", lambda *a, **k: (_ for _ in ()).throw(StorageError("offline"))
    )
    result = completed(client, start(client).json()["id"])
    assert not result["saved"]
    assert start(other).status_code == 409
    assert client.get(f"/api/runs/{result['id']}").json()["record"]["id"] == result["record"]["id"]
    monkeypatch.setattr(ExperimentStore, "save", original)
    assert client.post(f"/api/runs/{result['id']}/retry").json()["saved"]
    assert completed(other, start(other).json()["id"])["saved"]


def test_explicit_demo_mode_selects_separate_default_database(tmp_path, monkeypatch):
    import dvoinik.api as api

    monkeypatch.delenv("DVOINIK_STORAGE_PATH", raising=False)
    monkeypatch.setenv("DVOINIK_AUTH_MODE", "local")
    monkeypatch.setattr(api, "storage_path", lambda: tmp_path / "experiments.sqlite3")
    app = create_app(mode="demo")
    assert app.state.auth.path == tmp_path / "demo.sqlite3"
    assert not (tmp_path / "experiments.sqlite3").exists()
    app.state.jobs.close()


def test_access_guard_failure_uses_supported_failed_job_status(app, monkeypatch):
    import dvoinik.jobs as jobs
    from dvoinik.auth import AuthError

    monkeypatch.setattr(
        jobs, "run_experiment", lambda *a, **k: (_ for _ in ()).throw(AuthError("access unavailable"))
    )
    client = login(app)
    result = completed(client, start(client).json()["id"])
    assert result["status"] == "failed"
    assert result["record"] is None and not result["saved"]


def test_react_shell_rejects_framing_and_limits_scripts_to_local_assets(tmp_path):
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text('<html><body><div id="root"></div></body></html>')
    app = create_app(tmp_path / "shell.sqlite3", mode="local", static_dir=static)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        shell = client.get("/")
        assert shell.status_code == 200
        assert shell.headers.get("x-frame-options") == "DENY"
        policy = shell.headers.get("content-security-policy", "")
        assert "frame-ancestors 'none'" in policy
        assert "script-src 'self'" in policy
        assert "script-src 'self' 'unsafe-inline'" not in policy
        assert client.get("/api/session").headers.get("x-frame-options") == "DENY"


def test_session_default_mock_follows_configuration_but_demo_stays_mock(app, tmp_path, monkeypatch):
    monkeypatch.setenv("DVOINIK_MOCK", "0")
    client = login(app)
    assert client.get("/api/session").json()["default_mock"] is False
    demo = create_app(tmp_path / "demo-default.sqlite3", mode="demo")
    with TestClient(demo, base_url="http://127.0.0.1") as client:
        assert client.get("/api/session").json()["default_mock"] is True


def test_access_store_outage_is_distinguishable_from_failed_report_storage(app, monkeypatch):
    from dvoinik.auth import AuthError

    client = login(app)

    def unavailable(*args, **kwargs):
        raise AuthError("Хранилище доступа недоступно. Обратитесь к администратору.")

    monkeypatch.setattr(app.state.auth, "resolve", unavailable)
    response = client.get("/api/experiments")
    assert response.status_code == 503
    assert response.json().get("code") == "access_unavailable"


def test_old_tab_read_is_rejected_after_browser_cookie_switches_account(app):
    old_tab = login(app, "alice")
    new_tab = login(app, "bob")
    old_tab.cookies.update(new_tab.cookies)
    response = old_tab.get("/api/experiments")
    assert response.status_code == 401
    assert "records" not in response.json()


def test_recovery_discovery_survives_refresh_and_is_cookie_scoped(app, monkeypatch):
    original = ExperimentStore.save
    monkeypatch.setattr(
        ExperimentStore, "save", lambda *a, **k: (_ for _ in ()).throw(StorageError("offline"))
    )
    client, other = login(app), login(app, "bob")
    result = completed(client, start(client).json()["id"])
    refreshed = TestClient(app, base_url="http://127.0.0.1")
    refreshed.cookies.update(client.cookies)
    refreshed.headers.update(client.headers)
    response = refreshed.get("/api/recovery")
    assert response.status_code == 200, response.text
    assert response.json() == {"jobs": [result]}
    assert TestClient(app, base_url="http://127.0.0.1").get("/api/recovery").status_code == 401
    assert client.get(f"/api/experiments/{result['record']['id']}").json() == result["record"]
    assert other.get("/api/recovery").json() == {"jobs": []}
    assert login(app).get("/api/recovery").json() == {"jobs": []}
    monkeypatch.setattr(ExperimentStore, "save", original)
    assert refreshed.post(f"/api/runs/{result['id']}/retry").json()["saved"]
    assert refreshed.get("/api/recovery").json() == {"jobs": []}


def test_preview_ids_keep_same_cookie_tabs_independent_and_survive_saves(app):
    client = login(app)
    second_tab = TestClient(app, base_url="http://127.0.0.1")
    second_tab.cookies.update(client.cookies)
    second_tab.headers.update(client.headers)
    record = run(client)["record"]
    endpoint = f"/api/experiments/{record['id']}/validation"
    first = client.post(endpoint + "/preview", json={"csv": csv_for(record, 0)}).json()
    second = second_tab.post(endpoint + "/preview", json={"csv": csv_for(record, 1)}).json()
    assert "preview_id" in first and "preview_id" in second
    assert first["preview_id"] != second["preview_id"]
    assert (
        second_tab.put(endpoint, json={"csv": csv_for(record, 1), "base_validation": None}).status_code == 200
    )
    assert client.put(endpoint, json={"csv": csv_for(record, 0), "base_validation": None}).status_code == 409
    for preview, yes in [(first, 0), (second, 1)]:
        body = {
            "record_id": record["id"],
            "kind": "preview",
            "format": "json",
            "preview_id": preview["preview_id"],
        }
        exported = client.post("/api/export", json=body)
        assert exported.status_code == 200, exported.text
        assert client.get(exported.json()["url"]).json()["validation"]["cells"][0]["yes"] == yes
    exported = client.post(
        "/api/export", json={"record_id": record["id"], "kind": "validation", "format": "json"}
    )
    assert client.get(exported.json()["url"]).json()["cells"][0]["actual"] == 1
    exported = client.post(
        "/api/export",
        json={
            "record_id": record["id"],
            "kind": "validation",
            "format": "json",
            "preview_id": first["preview_id"],
        },
    )
    assert client.get(exported.json()["url"]).json()["cells"][0]["actual"] == 0
    foreign_record = run(client)["record"]
    for kind in ["preview", "validation"]:
        assert (
            client.post(
                "/api/export",
                json={
                    "record_id": foreign_record["id"],
                    "kind": kind,
                    "format": "json",
                    "preview_id": first["preview_id"],
                },
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/api/export", json={"record_id": record["id"], "kind": "preview", "format": "json"}
        ).status_code
        == 422
    )
    assert (
        login(app)
        .post(
            "/api/export",
            json={
                "record_id": record["id"],
                "kind": "preview",
                "format": "json",
                "preview_id": first["preview_id"],
            },
        )
        .status_code
        == 422
    )


def test_preview_capacity_reports_expired_identifier_instead_of_latest(app):
    client = login(app)
    record = run(client)["record"]
    endpoint = f"/api/experiments/{record['id']}/validation/preview"
    first = client.post(endpoint, json={"csv": csv_for(record, 0)}).json()
    assert "preview_id" in first
    for _ in range(128):
        latest = client.post(endpoint, json={"csv": csv_for(record, 1)}).json()
    body = {"record_id": record["id"], "kind": "preview", "format": "json", "preview_id": first["preview_id"]}
    expired = client.post("/api/export", json=body)
    assert expired.status_code == 422 and "detail" in expired.json()
    body["preview_id"] = latest["preview_id"]
    assert client.post("/api/export", json=body).status_code == 200


def test_validation_save_reconciles_original_session_pending_job(app, monkeypatch):
    client = login(app)
    original = ExperimentStore.save
    monkeypatch.setattr(
        ExperimentStore, "save", lambda *a, **k: (_ for _ in ()).throw(StorageError("offline"))
    )
    result = completed(client, start(client).json()["id"])
    record = result["record"]
    monkeypatch.setattr(ExperimentStore, "save", original)
    response = client.put(
        f"/api/experiments/{record['id']}/validation",
        json={"csv": csv_for(record, 1), "base_validation": None},
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/api/experiments/{record['id']}").json() == response.json()
    job = client.get(f"/api/runs/{result['id']}").json()
    assert job["saved"] and job["error"] is None and job["record"] == response.json()
    assert client.get("/api/recovery").json() == {"jobs": []}


def test_close_cancels_queued_job_and_interrupts_running_guard(app, monkeypatch):
    import dvoinik.jobs as module
    from dvoinik.jobs import JobBusy, Jobs
    from dvoinik.runs import RunSettings

    original = module.run_experiment
    entered, release = threading.Event(), threading.Event()
    calls = []

    def blocked(*args, **kwargs):
        calls.append(args[0])
        entered.set()
        assert release.wait(3)
        kwargs["progress"](1, 20)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "run_experiment", blocked)
    alice, bob = login(app), login(app, "bob")
    jobs = Jobs(app.state.auth, workers=1, queue_size=1)
    alice_token, bob_token = alice.cookies["dvoinik_session"], bob.cookies["dvoinik_session"]
    first = jobs.submit(alice_token, KEY, SCENARIOS[KEY], RunSettings(n=10))
    assert entered.wait(2)
    second = jobs.submit(bob_token, KEY, SCENARIOS[KEY], RunSettings(n=10))
    stopped = threading.Event()
    closer = threading.Thread(target=lambda: (jobs.close(), stopped.set()))
    closer.start()
    try:
        for _ in range(100):
            if jobs.closed:
                break
            time.sleep(0.01)
        assert jobs.closed
        for _ in range(100):
            if jobs.get(bob_token, second["id"])["status"] == "failed":
                break
            time.sleep(0.01)
        assert jobs.get(bob_token, second["id"])["status"] == "failed"
        assert jobs.active_count == 1 and not stopped.is_set()
    finally:
        release.set()
        closer.join(3)
    assert stopped.is_set() and len(calls) == 1
    assert jobs.get(alice_token, first["id"])["status"] == "failed"
    queued = jobs.get(bob_token, second["id"])
    assert queued["status"] == "failed" and queued["record"] is None
    assert jobs.get(alice_token, first["id"])["done"] == 0
    assert jobs.active_count == 0
    assert (
        len(
            ExperimentStore(
                app.state.auth.path, owner_id=app.state.auth.resolve(alice_token).id
            ).list_records()
        )
        == 0
    )
    assert jobs.capacity.acquire(blocking=False) and jobs.capacity.acquire(blocking=False)
    assert not jobs.capacity.acquire(blocking=False)
    jobs.capacity.release()
    jobs.capacity.release()
    with pytest.raises(JobBusy):
        jobs.submit(alice_token, KEY, SCENARIOS[KEY], RunSettings(n=10))


def test_app_factories_keep_session_caches_secrets_and_job_owners_independent(app, monkeypatch):
    import dvoinik.jobs as jobs

    # Sharing a database intentionally shares accounts, never ephemeral HTTP state.
    other_app = create_app(app.state.auth.path, mode="local")
    client = login(app)
    other = TestClient(other_app, base_url="http://127.0.0.1")
    other.cookies.update(client.cookies)
    other.headers["X-CSRF-Token"] = client.headers["X-CSRF-Token"]
    release = threading.Event()
    original = jobs.run_experiment

    def blocked(*args, **kwargs):
        assert release.wait(3)
        return original(*args, **kwargs)

    try:
        assert other.get("/api/catalog").status_code == 401
        other.headers["X-CSRF-Token"] = other.get("/api/session").json()["csrf_token"]
        sample = client.get(f"/api/sample/{KEY}").json()
        assert other.get(f"/api/experiments/{sample['id']}").status_code == 404
        own_sample = other.get(f"/api/sample/{KEY}").json()
        assert own_sample["id"] != sample["id"]
        record = client.post("/api/import", json={"content": json.dumps(sample)}).json()
        assert other.get(f"/api/experiments/{record['id']}").status_code == 200
        preview = client.post(
            f"/api/experiments/{record['id']}/validation/preview", json={"csv": csv_for(record)}
        ).json()
        assert (
            other.post(
                "/api/export",
                json={
                    "record_id": record["id"],
                    "kind": "preview",
                    "preview_id": preview["preview_id"],
                },
            ).status_code
            == 422
        )
        monkeypatch.setattr(jobs, "run_experiment", blocked)
        first = start(client)
        assert first.status_code == 202
        assert other.get(f"/api/runs/{first.json()['id']}").status_code == 404
        second = start(other)
        assert second.status_code == 202
        release.set()
        assert completed(client, first.json()["id"])["saved"]
        assert completed(other, second.json()["id"])["saved"]
    finally:
        release.set()
        other_app.state.jobs.close()


def test_insights_include_plan_stability_and_baseline_agreement(app):
    client = login(app)
    record = run(client)["record"]
    data = client.post("/api/insights", json={"record_id": record["id"], "segment": "all"}).json()
    assert data["plan"]["questions"] and data["plan"]["exploratory_n"] == 30
    assert data["stability"]["leader"] in record["report"]
    assert data["baseline"]["method"] == "demo_rule"
    sid = next(iter(record["scenario"]["population"]))
    focused = client.post("/api/insights", json={"record_id": record["id"], "segment": sid}).json()
    assert "plan" not in focused and "stability" in focused


def test_estimate_validates_scenario_and_counts_requests(app):
    client = login(app)
    response = client.post("/api/estimate", json={"scenario": SCENARIOS[KEY], "n": 100, "concurrency": 8})
    assert response.status_code == 200, response.text
    assert response.json()["requests"] == 100 * len(SCENARIOS[KEY]["variants"]) + 1
    bad = client.post("/api/estimate", json={"scenario": {"title": ""}, "n": 100})
    assert bad.status_code == 422
    assert client.post("/api/estimate", json={"scenario": SCENARIOS[KEY], "n": 0}).status_code == 422


def test_team_summary_export_is_html_attachment(app):
    client = login(app)
    record = run(client)["record"]
    link = client.post("/api/export", json={"record_id": record["id"], "kind": "summary", "format": "html"})
    assert link.status_code == 200, link.text
    response = client.get(link.json()["url"])
    assert response.headers["content-type"].startswith("text/html")
    assert "attachment" in response.headers["content-disposition"]
    assert record["scenario"]["title"] in response.text
    bad = client.post("/api/export", json={"record_id": record["id"], "kind": "summary", "format": "json"})
    assert bad.status_code == 422
