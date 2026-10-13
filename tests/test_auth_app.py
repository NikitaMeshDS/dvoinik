import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dvoinik.auth import AuthError, AuthStore
from dvoinik.storage import ExperimentStore

APP = Path(__file__).parents[1] / "app.py"
PASSWORD = "test-only-password-2026"


@pytest.fixture
def auth(monkeypatch, tmp_path):
    path = tmp_path / "archive.sqlite3"
    monkeypatch.setenv("DVOINIK_AUTH_MODE", "local")
    monkeypatch.setenv("DVOINIK_STORAGE_PATH", str(path))
    monkeypatch.setenv("DVOINIK_DOWNLOAD_ORIGIN", "http://127.0.0.1:9000")
    monkeypatch.setenv("DVOINIK_MOCK", "1")
    store = AuthStore(path)
    store.create_user("alice", "Алиса", PASSWORD)
    store.create_user("bob", "Боб", PASSWORD)
    return store


def launch():
    return AppTest.from_file(str(APP), default_timeout=20).run()


def login(app, username):
    app.text_input(key="login_username").set_value(username)
    app.text_input(key="login_password").set_value(PASSWORD)
    app.button(key="login_submit").click().run()
    assert not app.exception
    return app


def test_guest_does_not_read_archive_or_get_simulation_controls(auth, monkeypatch):
    def forbidden(self):
        raise AssertionError("Guest read archive")

    monkeypatch.setattr(ExperimentStore, "list_records", forbidden)
    app = launch()
    assert not app.exception
    assert not any(b.key == "run_experiment" for b in app.button)
    assert app.text_input(key="login_password").proto.type == 1


def test_logout_and_second_user_do_not_inherit_reports_or_drafts(auth):
    app = login(launch(), "alice")
    app.text_area(key="variant_student_card_A").set_value("Только для Алисы").run()
    app.button(key="run_experiment").click().run()
    alice_id = app.session_state["active_record"]["id"]
    app.button(key="logout").click().run()
    app = login(app, "bob")
    assert app.session_state["history"] == []
    assert app.text_area(key="variant_student_card_A").value != "Только для Алисы"
    app.button(key="logout").click().run()
    app = login(app, "alice")
    assert [r["id"] for r in app.session_state["history"]] == [alice_id]


def test_revocation_clears_pending_data_before_any_retry(auth):
    app = login(launch(), "alice")
    app.button(key="run_experiment").click().run()
    record = app.session_state["active_record"]
    app.session_state["pending_records"] = {record["id"]: record}
    auth.logout(app.session_state["_auth_token"])
    app.run()
    assert not app.exception
    assert not any(b.key == "run_experiment" for b in app.button)
    assert "pending_records" not in app.session_state


def test_invalid_auth_mode_does_not_fall_back_to_shared_archive(auth, monkeypatch):
    monkeypatch.setenv("DVOINIK_AUTH_MODE", "invalid")
    app = launch()
    assert not app.exception
    assert app.error
    assert not any(b.key == "run_experiment" for b in app.button)


def test_failed_revocation_does_not_report_logout_or_allow_another_login(auth, monkeypatch):
    app = login(launch(), "alice")
    token = app.session_state["_auth_token"]
    handle = auth.issue_export(token, b"private", "application/json", "report.json")
    original = AuthStore.logout

    def unavailable(self, token):
        raise AuthError("База временно недоступна")

    monkeypatch.setattr(AuthStore, "logout", unavailable)
    app.button(key="logout").click().run()
    assert not app.exception
    assert app.error
    assert not any(t.key == "login_password" for t in app.text_input)
    monkeypatch.setattr(AuthStore, "logout", original)
    app.run()
    assert app.text_input(key="login_password")
    with pytest.raises(AuthError):
        auth.resolve(token)
    with pytest.raises(AuthError):
        auth.consume_export(handle)


def test_consumed_export_is_reprepared_when_report_rerenders(auth):
    app = login(launch(), "alice")

    def handle():
        markup = next(item.value for item in app.markdown if 'data-download-key="json_active"' in item.value)
        return re.search(r"/download/([A-Za-z0-9_-]{43})", markup).group(1)

    first = handle()
    auth.consume_export(first)
    app.run()
    second = handle()
    assert first != second
    assert auth.consume_export(second)[1] == "application/json"


def test_unavailable_access_store_closes_workspace(auth, monkeypatch, tmp_path):
    occupied = tmp_path / "occupied"
    occupied.write_text("not a directory")
    monkeypatch.setenv("DVOINIK_STORAGE_PATH", str(occupied / "archive.sqlite3"))
    app = launch()
    assert not app.exception
    assert app.error
    assert not any(b.key == "run_experiment" for b in app.button)
    assert "history" not in app.session_state
