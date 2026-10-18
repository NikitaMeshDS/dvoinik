"""Проверка подключённой LLM перед демонстрацией: протокол, покрытие и признаки однородности.

Запускает небольшие исследования через настроенную модель и печатает сводку:
доля валидных ответов, доли по вариантам, разброс заявленной вероятности
и совпадение лидера с простым подходом. Точность прогноза людей здесь не измеряется.

    LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=qwen2.5:7b-instruct python llm_check.py --n 20

Режим SSR (ответ фразой, оценка по эмбеддингам): DVOINIK_ELICITATION=ssr LLM_EMBED_MODEL=bge-m3.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from dvoinik.engine import paraphrase_variants
from dvoinik.planning import HOMOGENEOUS_SD, baseline_agreement, leader_stability
from dvoinik.runs import RunSettings, run_experiment
from dvoinik.scenarios import SCENARIOS

MIN_COVERAGE = 0.9


def _leaders(report: dict) -> list[str]:
    rates = {v: r["conversion"] for v, r in report.items() if r["n"]}
    best = max(rates.values()) if rates else None
    return sorted(v for v, rate in rates.items() if rate == best)


def paraphrase_check(key: str, record: dict, settings: RunSettings) -> dict:
    """Тот же сценарий с перефразированными предложениями: меняется ли лидер и доли."""
    scenario = {**SCENARIOS[key], "variants": paraphrase_variants(SCENARIOS[key])}
    other = run_experiment(key, scenario, settings)
    shifts = {
        v: abs(other["report"][v]["conversion"] - r["conversion"]) * 100
        for v, r in record["report"].items()
        if r["n"] and other["report"][v]["n"]
    }
    return {
        "variants": scenario["variants"],
        "same_leader": _leaders(record["report"]) == _leaders(other["report"]),
        "max_shift_pp": max(shifts.values()) if shifts else None,
        "rates": {v: r["conversion"] for v, r in other["report"].items() if r["n"]},
    }


def check(key: str, n: int, concurrency: int, seed: int, paraphrase: bool = False) -> dict:
    started = time.perf_counter()
    settings = RunSettings(n=n, mock=False, seed=seed, concurrency=concurrency)
    record = run_experiment(key, SCENARIOS[key], settings)
    report = record["report"]
    requested = sum(r["requested_n"] for r in report.values())
    valid = sum(r["n"] for r in report.values())
    narrow = [
        v for v, r in report.items() if r.get("probability") and r["probability"]["sd"] < HOMOGENEOUS_SD
    ]
    agreement = baseline_agreement(record) or {}
    stability = leader_stability(report)
    return {
        "key": key,
        "coverage": valid / requested if requested else 0,
        "rates": {v: r["conversion"] for v, r in report.items() if r["n"]},
        "probability": {v: r.get("probability") for v, r in report.items()},
        "inconsistent": {v: (r.get("inconsistent_n", 0), r["n"]) for v, r in report.items() if r.get("n")},
        "likert": {v: r.get("likert") for v, r in report.items()},
        "by_digital": {v: r["by_digital"] for v, r in report.items() if r.get("by_digital")},
        "objections": {v: r.get("objections", {}) for v, r in report.items()},
        "narrow": narrow,
        "baseline": agreement,
        "stability": stability,
        "failures": sorted({e for r in report.values() for e in r.get("failure_examples", [])}),
        "paraphrase": paraphrase_check(key, record, settings) if paraphrase else None,
        "seconds": time.perf_counter() - started,
    }


def format_result(result: dict) -> str:
    lines = [f"## {result['key']}"]
    lines.append(f"Покрытие: {result['coverage']:.0%} · {result['seconds']:.0f} с")
    rates = ", ".join(f"{v} {rate:.0%}" for v, rate in result["rates"].items()) or "нет валидных ответов"
    lines.append(f"Двойники: {rates}")
    baseline = result["baseline"]
    if baseline.get("rows"):
        base = ", ".join(f"{row['variant']} {row['baseline']:.0%}" for row in baseline["rows"])
        lines.append(
            f"Простой подход: {base} · лидер {'совпадает' if baseline['same_leader'] else 'различается'}"
        )
    elif baseline.get("error"):
        lines.append(f"Простой подход: ошибка — {baseline['error']}")
    if result["stability"]:
        lines.append(f"{result['stability']['label']}: {result['stability']['share']:.0%} повторных выборок")
    stated = {v: r for v, r in result.get("probability", {}).items() if r}
    if stated and not any(result.get("likert", {}).values()):
        rows = ", ".join(f"{v} {r['mean']:.0%} (разброс {r['sd']:.0%})" for v, r in stated.items())
        lines.append(f"Названная вероятность, среднее: {rows}")
        flips = {v: f for v, f in result.get("inconsistent", {}).items() if f[0]}
        if flips:
            text = ", ".join(f"{v} {k} из {n}" for v, (k, n) in flips.items())
            lines.append(f"Вероятность противоречила решению (перевёрнута как уверенность): {text}")
    digital = result.get("by_digital") or {}
    if digital:
        levels = list(dict.fromkeys(level for d in digital.values() for level in d))
        lines.append("Вероятность «да» по цифровым навыкам:")
        for level in levels:
            cells = ", ".join(f"{v} {d[level]['mean']:.0%}" for v, d in digital.items() if level in d)
            n = max(d[level]["n"] for d in digital.values() if level in d)
            lines.append(f"  {level} (n≈{n}): {cells}")
    reasons = {v: r for v, r in result.get("objections", {}).items() if r}
    if reasons:
        top = " · ".join(
            f"{v}: " + ", ".join(f"{o} {c}" for o, c in list(r.items())[:2]) for v, r in reasons.items()
        )
        lines.append(f"Главные причины отказа: {top}")
    likert = {v: r for v, r in result.get("likert", {}).items() if r}
    if likert:
        rows = " · ".join(f"{v}: " + "/".join(f"{x:.0%}" for x in r) for v, r in likert.items())
        lines.append(f"Шкала 1–5 (SSR): {rows}")
    if result["narrow"]:
        lines.append(f"ВНИМАНИЕ: однородные ответы в предложениях {', '.join(result['narrow'])}")
    para = result.get("paraphrase")
    if para:
        rates = ", ".join(f"{v} {rate:.0%}" for v, rate in para["rates"].items())
        shift = "—" if para["max_shift_pp"] is None else f"{para['max_shift_pp']:.1f} п.п."
        lines.append(
            f"Перефразировка: {rates} · лидер {'тот же' if para['same_leader'] else 'ИЗМЕНИЛСЯ'} · "
            f"наибольший сдвиг {shift}"
        )
        lines += [f"  {v}: {text}" for v, text in para["variants"].items()]
    for error in result["failures"]:
        lines.append(f"Ошибка модели: {error}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Проверка подключённой LLM для Двойника")
    parser.add_argument(
        "--scenario", choices=list(SCENARIOS), action="append", help="по умолчанию все шаблоны"
    )
    parser.add_argument("--n", type=int, default=20, help="двойников на сценарий")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, help="сохранить сводку в Markdown")
    parser.add_argument(
        "--paraphrase",
        action="store_true",
        help="повторить с перефразированными предложениями (вдвое больше запросов)",
    )
    args = parser.parse_args(argv)
    model = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
    header = f"# Проверка LLM: {model} · {os.getenv('LLM_BASE_URL', 'http://localhost:11434/v1')}"
    print(header)
    blocks, failed = [header], False
    for key in args.scenario or list(SCENARIOS):
        try:
            result = check(key, args.n, args.concurrency, args.seed, paraphrase=args.paraphrase)
        except ValueError as exc:
            parser.exit(1, f"{key}: {exc}\n")
        block = format_result(result)
        print("\n" + block)
        blocks.append(block)
        failed = failed or result["coverage"] < MIN_COVERAGE
    if args.output:
        args.output.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    if failed:
        parser.exit(1, f"\nПокрытие ниже {MIN_COVERAGE:.0%}: проверьте модель и формат JSON.\n")


if __name__ == "__main__":
    main()
