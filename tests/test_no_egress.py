"""Контур банка: сервис не обращается никуда, кроме настроенной модели, а браузер — никуда, кроме сервиса."""

import socket

import pytest
from fastapi.testclient import TestClient

from dvoinik import engine
from dvoinik.api import create_app
from dvoinik.auth import AuthStore
from dvoinik.population import build_population
from dvoinik.scenarios import SCENARIOS


@pytest.fixture
def connections(monkeypatch):
    seen = []
    original = socket.socket.connect

    def record(sock, address):
        seen.append(address)
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", record)
    return seen


def test_demo_run_and_report_make_no_network_connections(tmp_path, connections):
    path = tmp_path / "a.sqlite3"
    AuthStore(path).create_user("alice", "Alice", "test-password-long")
    app = create_app(path, mode="local")
    try:
        client = TestClient(app, base_url="http://127.0.0.1")
        token = client.post("/api/login", json={"username": "alice", "password": "test-password-long"})
        client.headers["X-CSRF-Token"] = token.json()["csrf_token"]
        record = client.get("/api/sample/senior_deposit").json()
        assert (
            client.post("/api/insights", json={"record_id": record["id"], "segment": "all"}).status_code
            == 200
        )
        response = client.get("/api/catalog")
        policy = response.headers["Content-Security-Policy"]
        assert "connect-src 'self'" in policy and "default-src 'self'" in policy
        assert "script-src 'self'" in policy and "https:" not in policy
    finally:
        app.state.jobs.close()
    assert connections == []


def test_llm_mode_connects_only_to_the_configured_model(monkeypatch, connections):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    with pytest.raises(ValueError, match="LLM недоступна"):
        engine.simulate(build_population(2, {"senior": 1}), SCENARIOS["senior_deposit"], mock=False)
    hosts = {address[0] for address in connections}
    assert connections and hosts == {"127.0.0.1"}
    assert {address[1] for address in connections} == {9}
