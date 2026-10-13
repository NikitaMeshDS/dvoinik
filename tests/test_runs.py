import copy

import pytest

from dvoinik.auth import AccessExpired
from dvoinik.experiments import load_experiment
from dvoinik.reporting import export_json
from dvoinik.scenarios import SCENARIOS


def test_shared_run_normalizes_snapshot_without_mutating_editor():
    from dvoinik.runs import RunSettings, run_experiment

    scenario = copy.deepcopy(SCENARIOS["student_card"])
    scenario["population"] = {"student_msk": 2, "student_reg": 1}
    scenario["variants"]["A"] = "  Бесплатная карта  "
    record = run_experiment("student_card", scenario, RunSettings(n=50, mock=True, seed=7))
    reopened = load_experiment(export_json(record))
    assert reopened["scenario"]["variants"]["A"] == "Бесплатная карта"
    assert reopened["population_counts"] == {"student_msk": 33, "student_reg": 17}
    assert reopened["report"]["A"]["requested_n"] == 50
    assert scenario["variants"]["A"] == "  Бесплатная карта  "
    assert scenario["population"] == {"student_msk": 2, "student_reg": 1}


def test_revoked_access_aborts_run_before_progress_or_result():
    from dvoinik.runs import RunSettings, run_experiment

    def revoked():
        raise AccessExpired("Сессия завершена")

    progress = []
    with pytest.raises(AccessExpired):
        run_experiment(
            "student_card",
            SCENARIOS["student_card"],
            RunSettings(n=50, mock=True),
            guard=revoked,
            progress=lambda done, total: progress.append((done, total)),
        )
    assert progress == []


def test_access_revoked_during_progress_never_returns_completed_snapshot():
    from dvoinik.runs import RunSettings, run_experiment

    access = {"revoked": False}
    progress = []

    def guard():
        if access["revoked"]:
            raise AccessExpired("Сессия завершена")

    def advance(done, total):
        progress.append(done)
        access["revoked"] = True

    with pytest.raises(AccessExpired):
        run_experiment(
            "student_card",
            SCENARIOS["student_card"],
            RunSettings(n=50, mock=True),
            guard=guard,
            progress=advance,
        )
    assert len(progress) == 1
