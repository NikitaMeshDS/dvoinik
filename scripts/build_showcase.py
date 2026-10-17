"""Данные онлайн-витрины: готовые демо-запуски шаблонов и аналитика к ним.

Витрина — статическая сборка того же React-интерфейса без сервера. Запросы к /api
обслуживает frontend/src/showcase/backend.ts по этим данным. Запускаются только
шаблоны без изменений в демо-режиме; результаты те же, что у локального сервиса.

    python scripts/build_showcase.py frontend/showcase-data.json
    VITE_SHOWCASE=1 npm run build --prefix frontend -- --outDir dist-showcase
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dvoinik.engine import BASELINE_SYSTEM, SYSTEM  # noqa: E402
from dvoinik.experiments import CUSTOM_SCENARIO  # noqa: E402
from dvoinik.hypotheses import suggest  # noqa: E402
from dvoinik.insights import insights_payload  # noqa: E402
from dvoinik.planning import CHARS_PER_TOKEN, OUTPUT_TOKENS, PROFILE_CHARS  # noqa: E402
from dvoinik.population import SEGMENT_SOURCES, SEGMENTS, SOURCE_GAPS  # noqa: E402
from dvoinik.runs import RunSettings, run_experiment  # noqa: E402
from dvoinik.scenarios import SCENARIOS  # noqa: E402

SIZES = [50, 100, 200, 500, 1000]
CREATED_AT = "2026-10-17T10:00:00+03:00"
HYPOTHESIS_N = 200


def hypothesis_scenario(record: dict, hypothesis: dict) -> dict:
    """Тот же сценарий, что собирает draftFromHypothesis в интерфейсе."""
    scenario = record["scenario"]
    segments = [s for s in hypothesis["segments"] if scenario["population"].get(s, 0) > 0]
    population = {s: scenario["population"][s] for s in segments} or dict(scenario["population"])
    return {
        **copy.deepcopy(scenario),
        "title": (scenario["title"] + " · гипотеза «" + hypothesis["lever"] + "»")[:200],
        "description": (
            f"Проверка гипотезы «{hypothesis['lever']}»: A — текущий вариант {hypothesis['variant']}, "
            f"B — {hypothesis['change'][:1].lower()}{hypothesis['change'][1:]}. {scenario['description']}"
        )[:4000],
        "variants": {"A": hypothesis["base_text"], "B": hypothesis["proposal"]},
        "population": population,
    }


def build() -> dict:
    records, insights = {}, {}
    for key, scenario in SCENARIOS.items():
        for n in SIZES:
            record = run_experiment(key, scenario, RunSettings(n=n))
            record["id"] = f"{key}-{n}"
            record["created_at"] = CREATED_AT
            record["elapsed_seconds"] = 0.0
            records[f"{key}|{n}"] = record
            for segment in ["all", *record["scenario"]["population"]]:
                insights[f"{record['id']}|{segment}"] = insights_payload(record, segment)
    experiments = []
    for key in SCENARIOS:
        base = records[f"{key}|{HYPOTHESIS_N}"]
        for hypothesis in suggest(base)["items"]:
            scenario = hypothesis_scenario(base, hypothesis)
            record = run_experiment("custom", scenario, RunSettings(n=HYPOTHESIS_N))
            record["id"] = f"{key}-{hypothesis['id']}"
            record["created_at"] = CREATED_AT
            record["elapsed_seconds"] = 0.0
            experiments.append({"scenario": scenario, "n": HYPOTHESIS_N, "record": record})
            for segment in ["all", *record["scenario"]["population"]]:
                insights[f"{record['id']}|{segment}"] = insights_payload(record, segment)
    return {
        "session": {
            "user": {"id": "__showcase__", "username": "demo", "name": "Онлайн-витрина", "role": "demo"},
            "csrf_token": "showcase",
            "mode": "demo",
            "default_mock": True,
            "model": "Эвристика",
        },
        "catalog": {
            "scenarios": {**SCENARIOS, "custom": CUSTOM_SCENARIO},
            "segments": SEGMENTS,
            "sources": {"segments": SEGMENT_SOURCES, "gaps": SOURCE_GAPS},
        },
        "sizes": SIZES,
        "seed": 42,
        "records": records,
        "experiments": experiments,
        "insights": insights,
        "estimate": {
            "system_chars": len(SYSTEM),
            "baseline_chars": len(BASELINE_SYSTEM),
            "chars_per_token": CHARS_PER_TOKEN,
            "output_tokens": OUTPUT_TOKENS,
            "profile_chars": PROFILE_CHARS,
            "latency_s": 3.0,
        },
        "templates": copy.deepcopy(SCENARIOS),
    }


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "frontend/showcase-data.json")
    data = build()
    target.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{target}: {target.stat().st_size / 1e6:.1f} МБ, {len(data['records'])} запусков")
