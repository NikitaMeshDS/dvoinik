"""Снимки настроек, выводы и экспорт результатов эксперимента."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import uuid
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from .settings import model_identity


def summarize(report):
    valid = {v: r for v, r in report.items() if r["n"] > 0}
    if not valid:
        return {
            "leaders": [],
            "gap_pp": 0,
            "best": 0,
            "failed_n": sum(r.get("failed_n", 0) for r in report.values()),
        }
    ordered = sorted(valid, key=lambda v: valid[v]["conversion"], reverse=True)
    best = valid[ordered[0]]["conversion"]
    leaders = [v for v in ordered if math.isclose(valid[v]["conversion"], best)]
    gap = (best - valid[ordered[1]]["conversion"]) * 100 if len(ordered) > 1 else 0
    return {
        "leaders": leaders,
        "gap_pp": gap,
        "best": best,
        "failed_n": sum(r.get("failed_n", 0) for r in report.values()),
    }


def export_json(record):
    return json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False)


def _csv_text(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def export_csv(record):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["variant", "segment", "segment_name", "n", "conversion", "yes", "mode"])
    for vid, result in record["report"].items():
        for sid, seg in result["segments"].items():
            writer.writerow(
                [
                    _csv_text(vid),
                    _csv_text(sid),
                    _csv_text(seg["name"]),
                    seg["n"],
                    seg["conversion"],
                    seg.get("yes", ""),
                    "demo" if record.get("mock") else "llm",
                ]
            )
    return stream.getvalue()


def signature(scenario, n, mock, seed, model=None):
    # Источник (итерация, гипотеза) не меняет конфигурацию запуска и не входит в подпись.
    scenario = {k: v for k, v in scenario.items() if k != "origin"}
    payload = {"scenario": scenario, "n": n, "mock": mock, "seed": seed, "model": model if not mock else None}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


PROFILES_PER_SEGMENT = 3


def make_record(key, scenario, n, mock, seed, report, twins, elapsed=0, sample=False, baseline=None):
    seen, profiles = Counter(), []
    for twin in twins:
        if seen[twin.segment] < PROFILES_PER_SEGMENT:
            profiles.append(twin.to_dict())
            seen[twin.segment] += 1
    model, config_model = model_identity(mock)
    return {
        "schema_version": 2,
        "id": uuid.uuid4().hex[:10],
        "created_at": datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="seconds"),
        "scenario_key": key,
        "scenario": copy.deepcopy(scenario),
        "n": n,
        "mock": mock,
        "seed": seed,
        "model": model,
        "elapsed_seconds": round(elapsed, 2),
        "sample": sample,
        "report": report,
        "population_counts": dict(Counter(t.segment for t in twins)),
        "population_sample": profiles,
        "signature": signature(scenario, n, mock, seed, config_model),
    } | ({"baseline": copy.deepcopy(baseline)} if baseline is not None else {})
