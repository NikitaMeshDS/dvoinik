"""Парное сравнение профиля и двух уточнений в эксперименте со вкладом."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections import Counter
from pathlib import Path

from dvoinik import engine, llm_json
from dvoinik.population import build_population

MODES = ("no_profile", "profile", "dialogue")
OFFERS = {
    "A": "Вклад на 6 месяцев под 15% годовых от 50 000 ₽. Открытие только в приложении банка.",
    "B": "Вклад на 6 месяцев под 15% годовых от 50 000 ₽. Открытие только в отделении банка.",
}
FOLLOWUPS = (
    "Как вы обычно решаете вопросы с банком? Кто-нибудь помогает вам с этим?",
    "Что вам сложнее всего, когда вы хотите воспользоваться новой банковской услугой?",
)
QUESTION = "Открыли бы вы этот вклад?"
REASONS = (
    "неудобный канал",
    "не подходят условия вклада",
    "не доверяю банку",
    "нет свободных денег",
    "сейчас не нужен вклад",
    engine.OTHER_OBJECTION,
)
SYSTEM = (
    "Представь себя клиентом банка старше 60 лет. Отвечай от первого лица. "
    "Если дан профиль, придерживайся его. Ответ верни одним JSON-объектом."
)


def message(role, content):
    return {"role": role, "content": content}


def parse_answer(value):
    if not isinstance(value, dict) or type(value.get("decision")) is not bool:
        raise ValueError("Ожидается решение true или false.")
    decision = value["decision"]
    if decision and value.get("reason") is None:
        return True, None
    reason = engine._match_objection(value.get("reason"), REASONS)
    if not decision and reason is not None:
        return False, reason
    raise ValueError("Для согласия нужна причина null, для отказа — категория из списка.")


async def simulate(twin, ask):
    system = message("system", SYSTEM)
    intro = f"Профиль: {twin.profile()}\n\n"

    async def evaluate(history, prefix):
        results = {}
        for key, offer in OFFERS.items():
            prompt = (
                f"{prefix}{offer}\n{QUESTION}\n"
                'Ответь JSON с полем "decision" (true или false) и полем "reason". '
                f"При согласии reason — null. При отказе выбери одну причину: {', '.join(REASONS)}."
            )
            try:
                results[key] = parse_answer(json.loads(await ask([*history, message("user", prompt)])))
            except ValueError:
                results[key] = None
        return results

    results = {
        "no_profile": await evaluate([system], ""),
        "profile": await evaluate([system], intro),
        "dialogue": dict.fromkeys(OFFERS),
    }
    history = [system]
    for prefix, question in zip((intro, ""), FOLLOWUPS, strict=True):
        history.append(message("user", f'{prefix}Ответь JSON: {{"reply": "короткий ответ"}}.\n{question}'))
        try:
            value = json.loads(await ask(history.copy()))
        except ValueError:
            return results
        reply = value.get("reply") if isinstance(value, dict) else None
        if not isinstance(reply, str) or not reply.strip():
            return results
        history.append(message("assistant", json.dumps({"reply": reply.strip()[:500]}, ensure_ascii=False)))
    results["dialogue"] = await evaluate(history, "")
    return results


def load_human(path):
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Ожидается массив ответов.")
    result = {key: [] for key in OFFERS}
    for i, row in enumerate(records, 1):
        if not isinstance(row, dict) or set(row) != {"variant", "decision", "reason"}:
            raise ValueError(f"Строка {i}: нужны только variant, decision, reason.")
        variant = row["variant"]
        if not isinstance(variant, str) or variant not in result:
            raise ValueError(f"Строка {i}: вариант должен быть A или B.")
        try:
            result[variant].append(parse_answer(row))
        except ValueError as exc:
            raise ValueError(f"Ошибка в данных, строка {i}: {exc}") from exc
    if not all(result.values()):
        raise ValueError("Нужен хотя бы один валидный ответ по каждому варианту.")
    return result


def metrics(rows):
    reasons = Counter(reason for yes, reason in rows if not yes)
    declined = sum(reasons.values())
    return {
        "n": len(rows),
        "yes_share": sum(yes for yes, _ in rows) / len(rows) if rows else None,
        "declined": declined,
        "reason_counts": dict(reasons),
    }


def reason_distance(model, human):
    if not model["declined"] or not human["declined"]:
        return None
    return 50 * sum(
        abs(
            model["reason_counts"].get(reason, 0) / model["declined"]
            - human["reason_counts"].get(reason, 0) / human["declined"]
        )
        for reason in REASONS
    )


def summarize(rows, human=None):
    coverage = {
        mode: {key: sum(result[mode][key] is not None for _, result in rows) for key in OFFERS}
        for mode in MODES
    }
    matched = [
        (level, result)
        for level, result in rows
        if all(result[mode][key] is not None for mode in MODES for key in OFFERS)
    ]
    synthetic = {}
    for mode in MODES:
        offers = {key: metrics([result[mode][key] for _, result in matched]) for key in OFFERS}
        offers["delta_b_minus_a_pp"] = (
            100 * (offers["B"]["yes_share"] - offers["A"]["yes_share"]) if matched else None
        )
        synthetic[mode] = offers
    levels = dict.fromkeys(level for level, _ in matched if level is not None)
    report = {
        "requested_n": len(rows),
        "matched_n": len(matched),
        "coverage": coverage,
        "human": None,
        "synthetic": synthetic,
        "by_digital_skill": {
            level: {
                mode: {
                    key: metrics([result[mode][key] for group, result in matched if group == level])
                    for key in OFFERS
                }
                for mode in ("profile", "dialogue")
            }
            for level in levels
        },
    }

    if human is not None:
        compare(report, human)
    return report


def compare(report, human):
    reference = {key: metrics(human[key]) for key in OFFERS}
    report["human"] = reference
    for mode in MODES:
        offers = report["synthetic"][mode]
        errors = []
        for key in OFFERS:
            model = offers[key]
            model["reason_distance_pp"] = reason_distance(model, reference[key])
            model["abs_error_pp"] = (
                100 * abs(model["yes_share"] - reference[key]["yes_share"])
                if model["yes_share"] is not None
                else None
            )
            if model["abs_error_pp"] is not None:
                errors.append(model["abs_error_pp"])
        offers["mean_abs_error_pp"] = sum(errors) / len(OFFERS) if len(errors) == len(OFFERS) else None


async def run(model, n, seed, concurrency):
    async with engine._client() as client:
        sem = asyncio.Semaphore(concurrency)

        async def ask(messages):
            return await llm_json.chat_json(client, model, messages, temperature=0)

        async def participant(twin):
            async with sem:
                return twin.digital, await simulate(twin, ask)

        population = build_population(n, {"senior": 1}, seed)
        rows = await asyncio.gather(*(participant(twin) for twin in population))
    return summarize(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--human", type=Path, help="JSON с обезличенными кодами ответов участников.")
    parser.add_argument("--compare", type=Path, help="Сохранённый отчёт симуляции для сравнения с опросом.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.n < 1 or args.concurrency < 1:
        parser.error("--n и --concurrency должны быть положительными.")
    if bool(args.compare) != bool(args.human):
        parser.error("--compare и --human нужно указывать вместе.")
    protocol = {
        "question": QUESTION,
        "offers": OFFERS,
        "followups": list(FOLLOWUPS),
        "reasons": list(REASONS),
    }
    if args.compare:
        args.output = args.output or Path("proof/context-study-compared.json")
        if args.output.resolve() in {args.compare.resolve(), args.human.resolve()}:
            parser.error("Укажите отдельный выходной файл.")
        try:
            result = json.loads(args.compare.read_text(encoding="utf-8"))
            if not isinstance(result, dict) or any(
                result.get(key) != value for key, value in protocol.items()
            ):
                raise ValueError("В сохранённом отчёте другой протокол.")
            compare(result, load_human(args.human))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            parser.error(str(exc))
    else:
        args.output = args.output or Path("proof/context-study.json")
        model = os.getenv("LLM_MODEL")
        if not model or not os.getenv("LLM_BASE_URL"):
            parser.error("Задайте LLM_BASE_URL и LLM_MODEL.")
        start = time.monotonic()
        result = asyncio.run(run(model, args.n, args.seed, args.concurrency))
        result.update(
            {
                **protocol,
                "model": model,
                "seed": args.seed,
                "temperature": 0,
                "seconds": round(time.monotonic() - start, 2),
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.output}: полных профилей {result['matched_n']} из {result['requested_n']}")
    return 0 if result["matched_n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
