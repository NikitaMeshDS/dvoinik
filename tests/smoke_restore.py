"""Exercise SQLite restore through the packaged service in an isolated container."""

import http.cookiejar
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from dvoinik.auth import AuthStore
from dvoinik.experiments import load_experiment
from dvoinik.storage import ExperimentStore

ORIGIN = "http://127.0.0.1:8501"


def wait_for_ui(service, client):
    deadline = time.monotonic() + 15
    while service.poll() is None and time.monotonic() < deadline:
        try:
            with client.open(ORIGIN, timeout=2) as response:
                assert response.status == 200 and b'id="root"' in response.read()
                return
        except URLError:
            time.sleep(0.25)
    raise AssertionError("Restored service did not start")


def check_archive(record, password, client):
    archive = ORIGIN + "/api/experiments"
    try:
        with client.open(archive, timeout=2):
            raise AssertionError("Restored archive is accessible without signing in")
    except HTTPError as error:
        assert error.code == 401

    login = Request(
        ORIGIN + "/api/login",
        data=json.dumps({"username": "owner", "password": password}).encode(),
        headers={"Content-Type": "application/json", "Origin": ORIGIN},
    )
    with client.open(login, timeout=5) as response:
        assert response.status == 200
    with client.open(archive, timeout=5) as response:
        assert [item["id"] for item in json.load(response)["records"]] == [record["id"]]
    with client.open(f"{archive}/{record['id']}", timeout=5) as response:
        assert json.load(response) == record


def main():
    password = secrets.token_urlsafe(24)
    fixture = load_experiment(Path("examples/senior-deposit.demo.json").read_bytes())
    with tempfile.TemporaryDirectory(prefix="restore-", dir="/data") as directory:
        source = Path(directory) / "source.sqlite3"
        restored = Path(directory) / "restored.sqlite3"
        owner = AuthStore(source).create_user("owner", "Restore smoke test", password)
        with closing(sqlite3.connect(source)) as live, closing(sqlite3.connect(restored)) as snapshot:
            assert live.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
            live.execute("SELECT count(*) FROM users").fetchone()
            record = ExperimentStore(source, owner_id=owner).save(fixture)
            assert source.with_name("source.sqlite3-wal").stat().st_size > 0
            live.backup(snapshot)
            assert snapshot.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        source.unlink()

        client = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))
        env = {**os.environ, "DVOINIK_STORAGE_PATH": str(restored)}
        with subprocess.Popen([sys.executable, "serve.py"], env=env) as service:
            try:
                wait_for_ui(service, client)
                check_archive(record, password, client)
            finally:
                service.terminate()
                try:
                    service.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    service.kill()

    print("Restored SQLite snapshot: UI, private archive and report contents verified.")


if __name__ == "__main__":
    main()
