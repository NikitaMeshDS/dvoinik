"""Isolate digital banking skill in the senior deposit benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import replace
from itertools import product
from pathlib import Path
from statistics import mean

import openai

from benchmark import _probability
from context_study import OFFERS, SYSTEM, message
from dvoinik import engine, llm_json
from dvoinik.population import DIGITAL, DIGITAL_LABEL, build_population
from dvoinik.validate import load_survey

QUESTION = "Если бы у вас была нужная сумма, заинтересовал бы вас этот вклад?"
FORMAT = (
    "Оцени вероятность своего ответа «да» по шкале от 0 до 1. "
    'Верни JSON с одним числом "interest" в этом диапазоне.'
)
MODES = ("without_skill", "with_skill")
GROUPS = dict(
    zip(("independent", "assisted", "offline"), (text for text, _ in DIGITAL["senior"]), strict=True)
)
GROUP_ID = {text: code for code, text in GROUPS.items()}
SEEDS = (137, 211)
N_PER_SEED = 12


def prompt(twin, variant, mode):
    if mode == "without_skill":
        twin = replace(
            twin, traits={key: value for key, value in twin.traits.items() if key != DIGITAL_LABEL}
        )
    return f"Профиль: {twin.profile()}\n\n{OFFERS[variant]}\n{QUESTION}\n{FORMAT}"


def parse(raw):
    obj = json.loads(raw)
    interest = _probability(obj.get("interest")) if isinstance(obj, dict) else None
    if interest is None:
        raise ValueError("Ожидается число от 0 до 1 в поле interest.")
    return interest


async def collect(model, concurrency):
    population = [
        (seed, twin) for seed in SEEDS for twin in build_population(N_PER_SEED, {"senior": 1}, seed)
    ]
    sem = asyncio.Semaphore(concurrency)
    async with engine._client() as client:

        async def ask(seed, twin, mode, variant):
            row = {
                "seed": seed,
                "id": twin.id,
                "group": GROUP_ID[twin.digital],
                "mode": mode,
                "variant": variant,
            }
            messages = [message("system", SYSTEM), message("user", prompt(twin, variant, mode))]
            async with sem:
                for attempt in range(1, 3):
                    try:
                        return row | {
                            "interest": parse(await llm_json.chat_json(client, model, messages, 0)),
                            "attempts": attempt,
                        }
                    except (openai.APIError, ValueError) as exc:
                        error = type(exc).__name__
            return row | {"error": error, "attempts": attempt}

        rows = await asyncio.gather(
            *(
                ask(seed, twin, mode, variant)
                for (seed, twin), mode, variant in product(population, MODES, OFFERS)
            )
        )
    return rows, [
        {"seed": seed, "id": twin.id, "group": GROUP_ID[twin.digital], "profile": twin.profile()}
        for seed, twin in population
    ]


def score(rows):
    index = {(r["seed"], r["id"], r["mode"], r["variant"]): r for r in rows if "error" not in r}
    keys = {(r["seed"], r["id"]): r["group"] for r in rows}
    matched = [
        key for key in keys if all((*key, mode, variant) in index for mode, variant in product(MODES, OFFERS))
    ]

    def estimates(people):
        levels = {
            mode: {
                variant: mean(index[(*key, mode, variant)]["interest"] for key in people) if people else None
                for variant in OFFERS
            }
            for mode in MODES
        }
        return {"n": len(people), "levels": levels}

    return {
        "requested_n": len(keys),
        "matched_n": len(matched),
        "overall": estimates(matched),
        "groups": {group: estimates([key for key in matched if keys[key] == group]) for group in GROUPS},
        "by_seed": {
            seed: {
                group: estimates([key for key in matched if key[0] == seed and keys[key] == group])
                for group in GROUPS
            }
            for seed in sorted({key[0] for key in keys})
        },
        "errors": [r for r in rows if "error" in r],
    }


def compare(report, survey):
    if any(group not in GROUPS or variant not in OFFERS for variant, group in survey):
        raise ValueError("В опросе допустимы варианты A/B и сегменты independent, assisted, offline.")
    groups = {
        group: {
            variant: {
                "n": survey.counts[variant, group],
                "yes_share": survey[variant, group],
                "estimates": {mode: results["levels"][mode][variant] for mode in MODES},
            }
            for variant in OFFERS
            if (variant, group) in survey
        }
        for group, results in report["groups"].items()
    }
    for cells in groups.values():
        for cell in cells.values():
            cell["absolute_error_pp"] = {
                mode: 100 * abs(estimate - cell["yes_share"]) if estimate is not None else None
                for mode, estimate in cell["estimates"].items()
            }
        if set(cells) == set(OFFERS):
            cells["gap_a_minus_b_error_pp"] = {
                mode: 100
                * abs(
                    (cells["A"]["estimates"][mode] - cells["B"]["estimates"][mode])
                    - (cells["A"]["yes_share"] - cells["B"]["yes_share"])
                )
                if all(cells[v]["estimates"][mode] is not None for v in OFFERS)
                else None
                for mode in MODES
            }
    return {group: cells for group, cells in groups.items() if cells}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--survey", type=Path)
    args = parser.parse_args()
    if bool(args.compare) != bool(args.survey):
        parser.error("--compare и --survey указываются вместе.")
    if args.compare:
        if args.output.resolve() in {args.compare.resolve(), args.survey.resolve()}:
            parser.error("Укажите отдельный выходной файл.")
        report = json.loads(args.compare.read_text(encoding="utf-8"))
        if report.get("offers") != OFFERS or report.get("question") != QUESTION:
            parser.error("Отчёт использует другой протокол.")
        report["human_comparison"] = compare(report, load_survey(args.survey))
    else:
        model = os.getenv("LLM_MODEL")
        if not model or not os.getenv("LLM_BASE_URL") or args.concurrency < 1:
            parser.error("Нужны LLM_MODEL, LLM_BASE_URL и положительный --concurrency.")
        rows, population = asyncio.run(collect(model, args.concurrency))
        report = {
            "model": model,
            "offers": OFFERS,
            "question": QUESTION,
            "system": SYSTEM,
            "format": FORMAT,
            "population": population,
            "rows": rows,
            "human_comparison": None,
            **score(rows),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.output}: {report['matched_n']}/{report['requested_n']} полных профилей")
    return 0 if report["matched_n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
