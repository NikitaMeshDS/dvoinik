import json
import subprocess
import sys
from pathlib import Path

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
