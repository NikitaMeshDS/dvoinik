"""CLI для воспроизводимых симуляций, экспорта и сравнения с опросом."""

from __future__ import annotations

import argparse
from pathlib import Path

from dvoinik.experiments import attach_validation
from dvoinik.planning import live_check_plan
from dvoinik.reporting import export_json
from dvoinik.runs import RunSettings, run_experiment
from dvoinik.scenarios import SCENARIOS
from dvoinik.validate import load_survey


def main():
    parser = argparse.ArgumentParser(description="Двойник — синтетическое тестирование банковских продуктов")
    parser.add_argument("scenario", choices=list(SCENARIOS))
    parser.add_argument("--n", type=int, default=200, help="размер популяции")
    parser.add_argument("--mock", action="store_true", help="эвристическая модель без LLM")
    parser.add_argument("--seed", type=int, default=42, help="seed популяции и демо-ответов")
    parser.add_argument("--concurrency", type=int, default=16, help="параллельных запросов к LLM")
    parser.add_argument("--survey", help="CSV живого опроса: segment,variant,decision")
    parser.add_argument("--output", type=Path, help="сохранить настройки, отчёт и валидацию в JSON")
    args = parser.parse_args()
    try:
        settings = RunSettings(n=args.n, mock=args.mock, seed=args.seed, concurrency=args.concurrency)
        record = run_experiment(args.scenario, SCENARIOS[args.scenario], settings)
        if args.survey:
            record = attach_validation(record, load_survey(args.survey))
        if args.output:
            args.output.write_text(export_json(record), encoding="utf-8")
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(
        "ДЕМО: эвристические ответы, не прогноз реального спроса."
        if args.mock
        else "LLM: синтетические ответы требуют живой валидации."
    )
    for vid, result in record["report"].items():
        print(
            f"\nВариант {vid}: {result['conversion']:.1%} согласий (валидных: {result['n']}, ошибок: {result['failed_n']})"
        )
        for segment in result["segments"].values():
            print(f"  {segment['name']:<42} {segment['conversion']:>6.1%}  (n={segment['n']})")
    baseline = record.get("baseline", {})
    if "rates" in baseline:
        rates = ", ".join(f"{vid} {rate:.1%}" for vid, rate in baseline["rates"].items())
        print(f"\nПростой подход ({baseline['method']}): {rates}")
    elif baseline.get("error"):
        print(f"\nПростой подход не дал оценку: {baseline['error']}")
    plan = live_check_plan(record)
    for item in plan["comparisons"][:1]:
        needed = item["n_per_variant"]
        print(
            f"Живая проверка {item['pair'][0]} против {item['pair'][1]}: "
            + (f"≈ {needed} оценок на предложение" if needed else "разница меньше 2 п.п.")
        )
    if "validation" in record:
        print("\nВалидация:", export_json(record["validation"]))
    if args.output:
        print(f"\nОтчёт сохранён: {args.output}")
    if not any(result["n"] for result in record["report"].values()):
        parser.exit(1, "Модель не вернула валидных ответов. Проверьте подключение.\n")


if __name__ == "__main__":
    main()
