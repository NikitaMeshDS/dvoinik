import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def test_cli_exports_reproducible_experiment(tmp_path):
    output = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "cli.py",
            "senior_deposit",
            "--n",
            "50",
            "--mock",
            "--seed",
            "7",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    record = json.loads(output.read_text())
    assert record["n"] == 50
    assert record["seed"] == 7
    assert record["scenario"]["question"] == "Открыли бы вы этот вклад?"
    assert record["report"]["A"]["n"] == 50


def test_cli_invalid_input_has_no_traceback():
    result = subprocess.run(
        [sys.executable, "cli.py", "senior_deposit", "--n", "0", "--mock"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_cli_survey_export_can_be_reopened(tmp_path):
    from dvoinik.experiments import load_experiment

    survey = tmp_path / "survey.csv"
    survey.write_text("segment,variant,decision\nsenior,A,0\nsenior,B,1\nsenior,C,1\n")
    output = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "cli.py",
            "senior_deposit",
            "--n",
            "50",
            "--mock",
            "--survey",
            str(survey),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    saved = load_experiment(output.read_bytes())
    assert saved["validation"]["result"]["survey_n"] == 3


@pytest.mark.parametrize("flag,value", [("--seed", "-1"), ("--seed", "1000000"), ("--n", "10001")])
def test_cli_rejects_values_that_cannot_be_reopened(flag, value):
    result = subprocess.run(
        [sys.executable, "cli.py", "senior_deposit", "--mock", flag, value],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_cli_refuses_excessive_concurrency_without_creating_report(tmp_path):
    output = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "cli.py",
            "senior_deposit",
            "--mock",
            "--concurrency",
            "65",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not output.exists()
    assert "Traceback" not in result.stderr
