import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pytest

from dvoinik.auth import AuthError, AuthStore
from dvoinik.downloads import create_download_server


@pytest.fixture
def service(tmp_path):
    auth = AuthStore(tmp_path / "archive.sqlite3")
    user_id = auth.create_user("alice", "Алиса", "test-only-password-2026")
    token = auth.login("alice", "test-only-password-2026")
    server = create_download_server(auth)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield auth, token, user_id, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    worker.join()


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as response:
        return response.code, response.read(), response.headers


def test_export_is_one_time_and_never_public_media(service):
    auth, token, _, base = service
    handle = auth.issue_export(token, b'{"result":42}', "application/json", "report.json")
    status, body, headers = fetch(f"{base}/download/{handle}")
    assert status == 200
    assert body == b'{"result":42}'
    assert headers["Cache-Control"] == "no-store"
    assert "attachment" in headers["Content-Disposition"]
    assert fetch(f"{base}/download/{handle}")[0] == 410
    assert fetch(f"{base}/media/report.json")[0] == 404


@pytest.mark.parametrize("action", ["logout", "disable", "reset"])
def test_old_link_is_denied_after_access_is_revoked(service, action):
    auth, token, user_id, base = service
    handle = auth.issue_export(token, b"private-result", "text/csv", "report.csv")
    if action == "logout":
        auth.logout(token)
    elif action == "disable":
        auth.set_active(user_id, False)
    else:
        auth.reset_password("alice", "new-test-password-2026")
    status, body, _ = fetch(f"{base}/download/{handle}")
    assert status == 410
    assert b"private-result" not in body


def test_concurrent_requests_return_file_once(service):
    auth, token, _, base = service
    handle = auth.issue_export(token, b"once", "application/json", "report.json")
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(fetch, [f"{base}/download/{handle}"] * 2))
    assert sorted(result[0] for result in results) == [200, 410]


def test_link_expiry_and_filename_validation(service):
    auth, token, _, base = service
    now = auth.clock()
    auth.clock = lambda: now
    handle = auth.issue_export(token, b"test", "text/csv", "report.csv")
    auth.clock = lambda: now + 901
    assert fetch(f"{base}/download/{handle}")[0] == 410
    with pytest.raises(AuthError):
        auth.issue_export(token, b"test", "text/csv", "bad\r\nCookie:evil.csv")


def test_launcher_resolves_relative_archive_before_changing_child_directory(tmp_path, monkeypatch):
    from serve import storage_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DVOINIK_STORAGE_PATH", "relative-archive.sqlite3")
    assert storage_path() == tmp_path / "relative-archive.sqlite3"
