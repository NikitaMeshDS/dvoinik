import subprocess
import sys
from pathlib import Path

from dvoinik.auth import AuthStore

ROOT = Path(__file__).parents[1]


def run(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "manage.py"), *args], text=True, capture_output=True, timeout=15
    )


def test_create_and_reset_account_without_password_in_output(tmp_path):
    path, password_file = tmp_path / "archive.sqlite3", tmp_path / "password.txt"
    password_file.write_text("test-only-password-2026")
    result = run(
        "--path",
        str(path),
        "create-user",
        "--username",
        "alice",
        "--name",
        "Алиса",
        "--admin",
        "--password-file",
        str(password_file),
    )
    assert result.returncode == 0, result.stderr
    assert "test-only-password" not in result.stdout + result.stderr
    auth = AuthStore(path)
    token = auth.login("alice", password_file.read_text())
    assert auth.resolve(token).role == "admin"
    password_file.write_text("changed-test-password-2026")
    result = run(
        "--path", str(path), "reset-password", "--username", "alice", "--password-file", str(password_file)
    )
    assert result.returncode == 0
    auth.login("alice", password_file.read_text())


def test_cli_does_not_accept_password_as_argument(tmp_path):
    result = run(
        "--path",
        str(tmp_path / "archive.sqlite3"),
        "create-user",
        "--username",
        "alice",
        "--name",
        "Алиса",
        "--password",
        "secret",
    )
    assert result.returncode != 0


def test_legacy_assignment_preserves_validation_and_never_moves_owned_records(tmp_path):
    import copy
    import io

    from dvoinik.engine import simulate
    from dvoinik.experiments import attach_validation
    from dvoinik.population import build_population
    from dvoinik.reporting import make_record
    from dvoinik.scenarios import SCENARIOS
    from dvoinik.storage import ExperimentStore
    from dvoinik.validate import load_survey
    from manage import assign_legacy

    auth = AuthStore(tmp_path / "archive.sqlite3")
    alice = auth.create_user("alice", "Алиса", "test-only-password-2026")
    bob = auth.create_user("bob", "Боб", "test-only-password-2026")
    scenario = copy.deepcopy(SCENARIOS["student_card"])
    twins = build_population(50, scenario["population"], seed=42)
    record = make_record("student_card", scenario, 50, True, 42, simulate(twins, scenario, mock=True), twins)
    record = attach_validation(
        record, load_survey(io.StringIO("segment,variant,decision\nstudent_msk,A,1\n"))
    )
    ExperimentStore(auth.path).save(record)
    owned = copy.deepcopy(record)
    owned["id"] = "owned-by-bob"
    ExperimentStore(auth.path, owner_id=bob).save(owned)
    assert assign_legacy(auth, alice, record["id"]) == 1
    assert ExperimentStore(auth.path, owner_id=alice).list_records() == [record]
    assert assign_legacy(auth, alice, owned["id"]) == 0
    assert ExperimentStore(auth.path, owner_id=bob).list_records() == [owned]
    assert list(tmp_path.glob("*.legacy-assign-*.sqlite3"))


def test_purge_expired_exports_previews_without_writing_and_keeps_live_links(tmp_path):
    from dvoinik.auth import digest

    path = tmp_path / "archive with spaces.sqlite3"
    auth = AuthStore(path)
    auth.create_user("alice", "Алиса", "test-only-password-2026")
    token = auth.login("alice", "test-only-password-2026")
    expired = auth.issue_export(token, b"expired-test-content", "application/json", "old.json")
    live = auth.issue_export(token, b"live-test-content", "application/json", "live.json")
    with auth.connection() as db:
        db.execute("UPDATE export_links SET expires_at = 0 WHERE handle_hash = ?", (digest(expired),))
    original = path.read_bytes()

    args = ("--path", str(path), "purge-expired-exports")
    preview = run(*args)
    assert preview.returncode == 0 and "Найдено просроченных выгрузок — 1." in preview.stdout
    assert path.read_bytes() == original

    applied = run(*args, "--apply")
    assert applied.returncode == 0 and "Удалено просроченных выгрузок — 1." in applied.stdout
    for result in (preview, applied):
        assert all(value not in result.stdout + result.stderr for value in (expired, live, "test-content"))
    with auth.connection() as db:
        assert [row[0] for row in db.execute("SELECT handle_hash FROM export_links")] == [digest(live)]
    assert auth.consume_export(live)[0] == b"live-test-content"
    assert "Удалено просроченных выгрузок — 0." in run(*args, "--apply").stdout


def test_purge_expired_exports_does_not_create_missing_archive(tmp_path):
    path = tmp_path / "missing.sqlite3"
    for flags in ((), ("--apply",)):
        result = run("--path", str(path), "purge-expired-exports", *flags)
        assert result.returncode == 1
        assert "Traceback" not in result.stderr
        assert not path.exists()
