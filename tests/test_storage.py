import copy
import io

import pytest

from dvoinik.engine import simulate
from dvoinik.experiments import attach_validation
from dvoinik.population import build_population
from dvoinik.reporting import make_record
from dvoinik.scenarios import SCENARIOS
from dvoinik.storage import ExperimentStore, StorageConflict, StorageError
from dvoinik.validate import load_survey


@pytest.fixture
def record():
    scenario = copy.deepcopy(SCENARIOS["student_card"])
    twins = build_population(50, scenario["population"], seed=42)
    return make_record("student_card", scenario, 50, True, 42, simulate(twins, scenario, mock=True), twins)


def test_record_and_validation_survive_reopening_database(tmp_path, record):
    path = tmp_path / "nested" / "experiments.sqlite3"
    ExperimentStore(path).save(record)
    survey = load_survey(io.StringIO("segment,variant,decision\nstudent_msk,A,1\n"))
    updated = attach_validation(record, survey)
    ExperimentStore(path).save(updated, expected_validation=None)
    loaded = ExperimentStore(path).list_records()
    assert len(loaded) == 1
    assert loaded[0]["scenario"] == record["scenario"]
    assert loaded[0]["report"]["A"]["yes"] == record["report"]["A"]["yes"]
    assert loaded[0]["validation"]["result"]["survey_n"] == 1


def test_stale_session_cannot_remove_validation(tmp_path, record):
    store = ExperimentStore(tmp_path / "experiments.sqlite3")
    updated = attach_validation(
        record, load_survey(io.StringIO("segment,variant,decision\nstudent_msk,A,1\n"))
    )
    store.save(updated)
    store.save(record)
    assert store.list_records()[0]["validation"]["result"]["survey_n"] == 1


def test_history_keeps_more_than_twenty_and_orders_by_time(tmp_path, record):
    store = ExperimentStore(tmp_path / "experiments.sqlite3")
    for index in reversed(range(25)):
        item = copy.deepcopy(record)
        item["id"] = f"run-{index}"
        item["created_at"] = f"2026-10-13T00:{index:02d}:00+03:00"
        store.save(item)
    assert [r["id"] for r in store.list_records()] == [f"run-{i}" for i in range(25)]


def test_invalid_record_does_not_overwrite_existing_snapshot(tmp_path, record):
    store = ExperimentStore(tmp_path / "experiments.sqlite3")
    store.save(record)
    invalid = copy.deepcopy(record)
    invalid["report"]["A"]["conversion"] = -1
    with pytest.raises(ValueError):
        store.save(invalid)
    changed = copy.deepcopy(record)
    changed["scenario"]["variants"]["A"] = "Другое предложение"
    with pytest.raises(StorageError, match="ID"):
        store.save(changed)
    assert store.list_records()[0]["scenario"] == record["scenario"]


def test_unavailable_storage_has_clear_error(tmp_path):
    path = tmp_path / "not-a-directory"
    path.write_text("occupied")
    with pytest.raises(StorageError):
        ExperimentStore(path / "experiments.sqlite3").list_records()


def test_concurrent_survey_updates_use_saved_version_not_clock(tmp_path, record):
    store = ExperimentStore(tmp_path / "experiments.sqlite3")
    first = attach_validation(record, load_survey(io.StringIO("segment,variant,decision\nstudent_msk,A,0\n")))
    second = attach_validation(
        record, load_survey(io.StringIO("segment,variant,decision\nstudent_msk,A,1\n"))
    )
    second["validation"]["created_at"] = first["validation"]["created_at"]
    store.save(first)
    store.save(second, expected_validation=first["validation"])
    with pytest.raises(StorageConflict):
        store.save(first, expected_validation=first["validation"])
    store.save(first)
    assert store.list_records()[0]["validation"]["cells"][0]["yes"] == 1


def test_future_imported_time_does_not_block_explicit_new_survey(tmp_path, record):
    store = ExperimentStore(tmp_path / "experiments.sqlite3")
    first = attach_validation(record, load_survey(io.StringIO("segment,variant,decision\nstudent_msk,A,0\n")))
    first["validation"]["created_at"] = "2099-01-01T00:00:00+03:00"
    store.save(first)
    second = attach_validation(
        record, load_survey(io.StringIO("segment,variant,decision\nstudent_msk,A,1\n"))
    )
    store.save(second, expected_validation=first["validation"])
    assert store.list_records()[0]["validation"]["cells"][0]["yes"] == 1


def test_archives_are_isolated_and_other_owner_cannot_overwrite(tmp_path, record):
    path = tmp_path / "archive.sqlite3"
    alice = ExperimentStore(path, owner_id="alice")
    bob = ExperimentStore(path, owner_id="bob")
    alice.save(record)
    assert bob.list_records() == []
    with pytest.raises(StorageError):
        bob.save(record)
    with pytest.raises(StorageError):
        bob.get_record(record["id"])
    assert alice.get_record(record["id"])["id"] == record["id"]


def test_legacy_records_are_quarantined_with_backup(tmp_path, record):
    import sqlite3

    from dvoinik.reporting import export_json

    path = tmp_path / "archive.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE experiments (id TEXT PRIMARY KEY, created_at REAL, payload TEXT)")
        db.execute("INSERT INTO experiments VALUES (?, ?, ?)", (record["id"], 0, export_json(record)))
    assert ExperimentStore(path, owner_id="first-user").list_records() == []
    assert ExperimentStore(path).list_records()[0]["id"] == record["id"]
    assert list(tmp_path.glob("*.pre-auth-*.sqlite3"))


def test_revoked_session_cannot_access_bound_store(tmp_path, record):
    from dvoinik.auth import AuthStore

    auth = AuthStore(tmp_path / "archive.sqlite3")
    user_id = auth.create_user("alice", "Алиса", "test-only-password-2026")
    store = auth.workspace(auth.login("alice", "test-only-password-2026"))
    store.save(record)
    auth.set_active(user_id, False)
    with pytest.raises(StorageError):
        store.list_records()
    with pytest.raises(StorageError):
        store.save(record)
