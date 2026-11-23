"""Isolate digital banking skill in the senior deposit benchmark."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from dataclasses import replace
from itertools import product
from math import hypot
from pathlib import Path
from statistics import mean

import openai

from benchmark import _probability
from benchmarks.deposit_assignments import reconcile
from context_study import OFFERS, SYSTEM, message
from dvoinik import engine, llm_json
from dvoinik.population import DIGITAL, DIGITAL_LABEL, build_population
from dvoinik.report_stats import wilson_interval
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


def baseline_rates(baseline, model):
    if (
        not isinstance(baseline, dict)
        or baseline.get("model") != model
        or baseline.get("offers") != OFFERS
        or baseline.get("question") != QUESTION
        or baseline.get("groups") != GROUPS
    ):
        raise ValueError("Простой промпт должен использовать ту же модель, предложения, вопрос и группы.")
    rates = baseline.get("rates")
    if (
        not isinstance(rates, dict)
        or set(rates) != set(GROUPS)
        or any(
            not isinstance(pair, dict)
            or set(pair) != set(OFFERS)
            or any(_probability(value) is None for value in pair.values())
            for pair in rates.values()
        )
    ):
        raise ValueError("Для простого промпта нужны доли от 0 до 1 по каждому варианту и группе.")
    return rates


def survey_gap_interval(a, b):
    """Newcombe method 10 for independent groups, in percentage points."""
    a_low, a_high = wilson_interval(a["yes"], a["n"])
    b_low, b_high = wilson_interval(b["yes"], b["n"])
    p_a, p_b = a["yes_share"], b["yes_share"]
    gap = p_a - p_b
    return [
        100 * (gap - hypot(p_a - a_low, b_high - p_b)),
        100 * (gap + hypot(a_high - p_a, p_b - b_low)),
    ]


def compare(report, survey, baseline=None):
    if any(group not in GROUPS or variant not in OFFERS for variant, group in survey):
        raise ValueError("В опросе допустимы варианты A/B и сегменты independent, assisted, offline.")
    modes = MODES + ("simple_prompt",) if baseline is not None else MODES
    groups = {}
    for group in GROUPS:
        levels = report["groups"].get(group, {}).get("levels", {})
        if baseline is not None:
            levels = {**levels, "simple_prompt": baseline[group]}
        cells = {
            variant: {
                "n": survey.counts[variant, group],
                "yes": round(survey[variant, group] * survey.counts[variant, group]),
                "yes_share": survey[variant, group],
                "estimates": {mode: levels.get(mode, {}).get(variant) for mode in modes},
            }
            for variant in OFFERS
            if (variant, group) in survey
        }
        if not cells:
            continue
        groups[group] = cells
        for cell in cells.values():
            cell["absolute_error_pp"] = {
                mode: 100 * abs(estimate - cell["yes_share"]) if estimate is not None else None
                for mode, estimate in cell["estimates"].items()
            }
        if set(cells) == set(OFFERS):
            observed_gap = 100 * (cells["A"]["yes_share"] - cells["B"]["yes_share"])
            model_gaps = {
                mode: 100 * (cells["A"]["estimates"][mode] - cells["B"]["estimates"][mode])
                if all(cells[v]["estimates"][mode] is not None for v in OFFERS)
                else None
                for mode in modes
            }
            cells["gap_a_minus_b_pp"] = {"survey": observed_gap, **model_gaps}
            low, high = survey_gap_interval(cells["A"], cells["B"])
            cells["survey_gap_interval_95_pp"] = [low, high]
            cells["survey_gap_direction"] = "A" if low > 0 else "B" if high < 0 else "uncertain"
            cells["model_direction_match"] = {
                mode: (gap > 0) == (observed_gap > 0) if gap and (low > 0 or high < 0) else None
                for mode, gap in model_gaps.items()
            }
            cells["gap_a_minus_b_error_pp"] = {
                mode: abs(gap - observed_gap) if gap is not None else None for mode, gap in model_gaps.items()
            }
    return groups


def survey_coverage(comparison):
    missing_survey, missing_model = [], []
    comparable = set()
    survey_n = survey_cells = 0
    for group, variant in product(GROUPS, OFFERS):
        key = {"variant": variant, "group": group}
        cell = comparison.get(group, {}).get(variant)
        if cell is None:
            missing_survey.append(key)
            continue
        survey_n += cell["n"]
        survey_cells += 1
        if any(value is None for value in cell["estimates"].values()):
            missing_model.append(key)
        else:
            comparable.add((group, variant))
    return {
        "survey_n": survey_n,
        "expected_cells": len(GROUPS) * len(OFFERS),
        "survey_cells": survey_cells,
        "comparable_cells": len(comparable),
        "paired_groups": [
            group for group in GROUPS if all((group, variant) in comparable for variant in OFFERS)
        ],
        "missing_survey_cells": missing_survey,
        "missing_model_cells": missing_model,
    }


def summary_markdown(report):
    def number(value, spec):
        return format(value, spec).replace(".", ",").replace("-", "−") if value is not None else "—"

    def answers(cell):
        if not cell:
            return "—"
        return f"{cell['yes']}/{cell['n']} ({number(100 * cell['yes_share'], '.1f')}%)"

    coverage = report["human_coverage"]
    lines = ["# Опрос по вкладу для участников 60+", ""]
    if report["survey_input_kind"] == "rehearsal":
        lines += ["**Репетиция. Синтетические данные.**", ""]
    else:
        lines += [
            "Источник ответов — предоставленный CSV. Происхождение подтверждает координатор опроса.",
            "",
        ]
    lines += [
        "A — открытие в приложении. B — открытие в отделении.",
        f"Ответов в анализе — {coverage['survey_n']}. Покрыто {coverage['survey_cells']} из "
        f"{coverage['expected_cells']} сочетаний группы и варианта.",
        "",
    ]
    audit = report.get("assignment_reconciliation")
    if audit:
        lines += [
            "## Выдача бланков",
            "",
            "| Вариант | План | Выдано | В анализе | Пропуски | Ответы без группы |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for variant, counts in audit["counts"].items():
            lines.append(
                f"| {variant} | {counts['planned']} | {counts['issued']} | {counts['valid']} | "
                f"{counts['missing']} | {counts['unclassified']} |"
            )
        lines.append("")

    labels = {"independent": "Самостоятельно", "assisted": "С помощью", "offline": "Без интернета"}
    directions = {"A": "Выше A", "B": "Выше B", "uncertain": "Неопределённо"}
    lines += [
        "## Ответы и отличие от прогнозов",
        "",
        "| Цифровой навык | A, «да» / всего | B, «да» / всего | A − B, п. п. (95% ДИ) | Направление | "
        "Ошибка двойников, п. п. | Ошибка простого промпта, п. п. |",
        "| --- | ---: | ---: | --- | --- | ---: | ---: |",
    ]
    for group, label in labels.items():
        cells = report["human_comparison"].get(group, {})
        interval = cells.get("survey_gap_interval_95_pp")
        gap = "—"
        if interval is not None:
            low, high = interval
            observed = cells["gap_a_minus_b_pp"]["survey"]
            gap = f"{number(observed, '+.1f')} [{number(low, '+.1f')} … {number(high, '+.1f')}]"
        errors = cells.get("gap_a_minus_b_error_pp", {})
        direction = directions.get(cells.get("survey_gap_direction"), "—")
        lines.append(
            f"| {label} | {answers(cells.get('A'))} | {answers(cells.get('B'))} | {gap} | {direction} | "
            f"{number(errors.get('with_skill'), '.1f')} | {number(errors.get('simple_prompt'), '.1f')} |"
        )
    lines += [
        "",
        "Ошибка — абсолютное расхождение прогноза с наблюдаемой разницей A − B. "
        "При интервале, включающем ноль, направление остаётся неопределённым.",
        "",
    ]
    return "\n".join(lines)


def write_summary(path, report):
    content = summary_markdown(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--survey", type=Path)
    parser.add_argument("--baseline", type=Path, help="Зафиксированные оценки простого промпта")
    parser.add_argument("--assignments", type=Path, help="Список назначений для опроса с колонкой slot")
    parser.add_argument("--assignment-sha256", help="Контрольная сумма согласованного списка назначений")
    parser.add_argument("--summary", type=Path, help="Краткое резюме опроса в Markdown")
    parser.add_argument(
        "--summary-from", type=Path, help="Сохранённый JSON сравнения для повторного экспорта"
    )
    parser.add_argument(
        "--rehearsal", action="store_true", help="Пометить синтетические ответы для репетиции"
    )
    args = parser.parse_args()
    if args.summary_from:
        if not args.summary or any(
            (
                args.compare,
                args.survey,
                args.baseline,
                args.assignments,
                args.assignment_sha256,
                args.output,
                args.rehearsal,
            )
        ):
            parser.error("--summary-from требует --summary и используется отдельно от сравнения.")
        if args.summary.resolve() == args.summary_from.resolve():
            parser.error("Укажите отдельный файл для резюме.")
        try:
            saved = json.loads(args.summary_from.read_text(encoding="utf-8"))
            if (
                not isinstance(saved, dict)
                or saved.get("survey_input_kind") not in {"csv", "rehearsal"}
                or saved.get("offers") != OFFERS
                or saved.get("question") != QUESTION
            ):
                raise ValueError("Нужен сохранённый результат сравнения с опросом.")
            write_summary(args.summary, saved)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            parser.error("Не удалось экспортировать резюме. Проверьте JSON сравнения и выходной путь.")
        return 0
    if not args.output:
        parser.error("Укажите --output.")
    if bool(args.compare) != bool(args.survey):
        parser.error("--compare и --survey указываются вместе.")
    if args.baseline and not args.compare:
        parser.error("--baseline требует --compare и --survey.")
    if args.assignments and not args.compare:
        parser.error("--assignments требует --compare и --survey.")
    if args.assignment_sha256 and not args.assignments:
        parser.error("--assignment-sha256 требует --assignments.")
    if (args.summary or args.rehearsal) and not args.compare:
        parser.error("--summary и --rehearsal требуют --compare и --survey.")
    if args.compare:
        inputs = (args.compare, args.survey, args.baseline, args.assignments)
        input_paths = {path.resolve() for path in inputs if path is not None}
        if args.output.resolve() in input_paths:
            parser.error("Укажите отдельный выходной файл.")
        if args.summary and args.summary.resolve() in input_paths | {args.output.resolve()}:
            parser.error("Укажите отдельный файл для резюме.")
        report = json.loads(args.compare.read_text(encoding="utf-8"))
        if report.get("offers") != OFFERS or report.get("question") != QUESTION:
            parser.error("Отчёт использует другой протокол.")
        if report.get("survey_input_kind") == "rehearsal" and not args.rehearsal:
            parser.error(
                "Для повторной репетиции укажите --rehearsal. Для живого опроса возьмите исходный прогноз."
            )
        baseline = None
        report.pop("simple_prompt_baseline", None)
        if args.baseline:
            try:
                source = json.loads(args.baseline.read_text(encoding="utf-8"))
                baseline = baseline_rates(source, report.get("model"))
            except (OSError, ValueError) as exc:
                parser.error(str(exc))
            report["simple_prompt_baseline"] = source
        report.pop("assignment_reconciliation", None)
        try:
            if args.assignments:
                survey, audit = reconcile(args.assignments, args.survey, GROUPS, args.assignment_sha256)
                report["assignment_reconciliation"] = audit
            else:
                survey = load_survey(args.survey)
            report["human_comparison"] = compare(report, survey, baseline)
        except (OSError, ValueError, csv.Error) as exc:
            parser.error(str(exc))
        report["human_coverage"] = survey_coverage(report["human_comparison"])
        report["survey_input_kind"] = "rehearsal" if args.rehearsal else "csv"
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
    if args.summary:
        write_summary(args.summary, report)
    print(f"{args.output}: {report['matched_n']}/{report['requested_n']} полных профилей")
    if args.compare:
        coverage = report["human_coverage"]
        print(
            f"Ответов в опросе: {coverage['survey_n']}. "
            f"Сопоставимо сочетаний группы и варианта: {coverage['comparable_cells']}/{coverage['expected_cells']}. "
            f"Сопоставимо групп с обоими каналами: {len(coverage['paired_groups'])}/{len(GROUPS)}."
        )
        if "assignment_reconciliation" in report:
            for variant, counts in report["assignment_reconciliation"]["counts"].items():
                print(
                    f"{variant} · выдано {counts['issued']} из {counts['planned']} · в анализе {counts['valid']} · "
                    f"пропусков {counts['missing']} · ответов без группы {counts['unclassified']}"
                )
        for group, cells in report["human_comparison"].items():
            if "survey_gap_interval_95_pp" in cells:
                low, high = cells["survey_gap_interval_95_pp"]
                gap = cells["gap_a_minus_b_pp"]["survey"]
                direction = cells["survey_gap_direction"]
                note = (
                    "направление неопределённо"
                    if direction == "uncertain"
                    else f"выше доля «да» у {direction}"
                )
                print(f"{group} · A − B {gap:+.1f} п. п. · 95% ДИ [{low:+.1f}, {high:+.1f}] · {note}")
    return 0 if report["matched_n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
