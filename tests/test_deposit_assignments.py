import csv
import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def generate(output, per_variant):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.deposit_assignments",
            "--n-per-variant",
            str(per_variant),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_schedule_is_balanced_numbered_and_preserved_on_retry(tmp_path):
    path = tmp_path / "assignment.csv"
    first = generate(path, 12)
    assert first.returncode == 0, first.stderr
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() in first.stdout
    if os.name == "posix":
        assert path.stat().st_mode & 0o077 == 0
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        assert reader.fieldnames == ["slot", "variant"]
    assert [int(row["slot"]) for row in rows] == list(range(1, 25))
    assert sorted(row["variant"] for row in rows) == ["A"] * 12 + ["B"] * 12

    second = generate(path, 6)
    assert second.returncode != 0
    assert path.read_bytes() == content


def test_invalid_size_leaves_no_file(tmp_path):
    path = tmp_path / "assignment.csv"
    result = generate(path, 0)
    assert result.returncode == 2
    assert "от 1 до 10 000" in result.stderr
    assert not path.exists()
