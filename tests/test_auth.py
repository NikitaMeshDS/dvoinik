import sqlite3

import pytest

from dvoinik.auth import AuthError, AuthStore

PASSWORD = "test-only-password-2026"


@pytest.fixture
def auth(tmp_path):
    return AuthStore(tmp_path / "archive.sqlite3")


def test_password_is_hashed_and_username_is_normalized(auth):
    user_id = auth.create_user("Alice", "Алиса", PASSWORD)
    token = auth.login("ALICE", PASSWORD)
    user = auth.resolve(token)
    assert user.id == user_id
    assert user.username == "alice"
    with sqlite3.connect(auth.path) as db:
        stored = db.execute("SELECT password_hash FROM users").fetchone()[0]
        session_hash = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored
    assert token != session_hash


def test_unknown_user_and_wrong_password_have_same_error(auth):
    auth.create_user("alice", "Алиса", PASSWORD)
    messages = []
    for username in ["alice", "missing"]:
        with pytest.raises(AuthError) as caught:
            auth.login(username, "wrong-password")
        messages.append(str(caught.value))
    assert messages[0] == messages[1]


def test_rate_limit_survives_new_store_and_browser_session(auth):
    auth.create_user("alice", "Алиса", PASSWORD)
    for _ in range(5):
        with pytest.raises(AuthError):
            auth.login("alice", "wrong-password")
    with pytest.raises(AuthError, match="попыток"):
        AuthStore(auth.path).login("alice", PASSWORD)


def test_logout_disable_and_reset_revoke_existing_tokens(auth):
    user_id = auth.create_user("alice", "Алиса", PASSWORD)
    token = auth.login("alice", PASSWORD)
    auth.logout(token)
    with pytest.raises(AuthError):
        auth.resolve(token)
    token = auth.login("alice", PASSWORD)
    auth.set_active(user_id, False)
    with pytest.raises(AuthError):
        auth.resolve(token)
    auth.set_active(user_id, True)
    token = auth.login("alice", PASSWORD)
    auth.reset_password("alice", "another-test-password-2026")
    with pytest.raises(AuthError):
        auth.resolve(token)


def test_idle_and_absolute_deadline_are_checked_on_server(tmp_path):
    now = {"value": 1000.0}
    auth = AuthStore(tmp_path / "archive.sqlite3", clock=lambda: now["value"])
    auth.create_user("alice", "Алиса", PASSWORD)
    token = auth.login("alice", PASSWORD)
    now["value"] += 1801
    with pytest.raises(AuthError):
        auth.resolve(token)
    token = auth.login("alice", PASSWORD)
    for _ in range(17):
        now["value"] += 1700
        if _ < 16:
            auth.resolve(token, touch=True)
    with pytest.raises(AuthError):
        auth.resolve(token)


def test_local_mode_cannot_create_anonymous_session(auth):
    with pytest.raises(AuthError):
        auth.create_demo_session()


def test_last_admin_cannot_be_disabled(auth):
    user_id = auth.create_user("admin", "Администратор", PASSWORD, role="admin")
    with pytest.raises(AuthError, match="последнего"):
        auth.set_active(user_id, False)


@pytest.mark.parametrize("field", ["name", "password", "login_password"])
def test_invalid_unicode_is_rejected_without_uncaught_error(auth, field):
    malformed = "invalid-surrogate-\ud800"
    with pytest.raises(AuthError):
        if field == "login_password":
            auth.login("missing", malformed)
        else:
            auth.create_user(
                "alice",
                malformed if field == "name" else "Алиса",
                malformed if field == "password" else PASSWORD,
            )


@pytest.mark.parametrize("suffix", ["x", "\ud800"])
def test_login_never_accepts_invalid_username_as_existing_prefix(auth, suffix):
    username = "a" * 80
    auth.create_user(username, "Алиса", PASSWORD)
    with pytest.raises(AuthError, match="Логин или пароль неверны"):
        auth.login(username + suffix, PASSWORD)
