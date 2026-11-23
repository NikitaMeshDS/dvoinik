"""Вывести по строке JSON с техническими метриками каждого сохранённого снимка."""

import argparse
import json
from pathlib import Path

from .experiments import MAX_IMPORT_BYTES, load_experiment


def journal_entry(record):
    results = record["report"].values()
    usage = record.get("run_usage", {})
    baseline = record.get("baseline")
    return {
        "id": record["id"],
        "created_at": record["created_at"],
        "scenario_key": record["scenario_key"],
        "model": record["model"],
        "mock": record["mock"],
        "sample": record["sample"],
        "seed": record["seed"],
        "profiles": record["n"],
        "elapsed_seconds": record["elapsed_seconds"],
        "valid_answers": sum(result["n"] for result in results),
        "failed_answers": sum(result["failed_n"] for result in results),
        "baseline_ok": "rates" in baseline if baseline is not None else None,
        "concurrency": usage.get("concurrency"),
        "sdk_calls": usage.get("sdk_calls"),
        "cache_hits": usage.get("cache_hits"),
        "calls_with_usage": usage.get("calls_with_usage"),
        "reported_tokens": usage.get("reported_tokens"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshots", nargs="+", type=Path, metavar="SNAPSHOT.json")
    for path in parser.parse_args().snapshots:
        try:
            with path.open("rb") as snapshot:
                record = load_experiment(snapshot.read(MAX_IMPORT_BYTES + 1))
        except (OSError, ValueError) as exc:
            parser.exit(1, f"{path.name}: {exc}\n")
        print(json.dumps(journal_entry(record), ensure_ascii=False))


if __name__ == "__main__":
    main()
