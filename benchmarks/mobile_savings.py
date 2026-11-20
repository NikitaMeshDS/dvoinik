"""Retrospective benchmark against de Mel et al., Table 1 (Sri Lanka).

Run from the repository root: python -m benchmarks.mobile_savings
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from pathlib import Path
from statistics import mean

import openai

from benchmark import _probability
from dvoinik import engine, llm_json

SOURCE = "https://chriswoodruff.qeh.ox.ac.uk/wp-content/uploads/2020/06/MobileBank_RStat_Accepted_200624.pdf"
OUTCOMES = ("accepted", "used")
ARMS = {
    0: (656, 0.910, 0.258),
    2: (300, 0.903, 0.203),
    4: (292, 0.921, 0.226),
    8: (292, 0.873, 0.178),
}
# Pretreatment marginals from Appendix A.2 (total sample).
TRAITS = (
    ((0.192, "женщина"), (0.808, "мужчина")),
    ((0.848, "в браке"), (0.152, "не в браке")),
    ((0.892, "есть собственный телефон"), (0.108, "нет собственного телефона")),
    ((0.438, "до банка менее 2 км"), (0.397, "до банка 2–5 км"), (0.165, "до банка более 5 км")),
)
AUDIENCE = (
    "Центральная Шри-Ланка, конец 2011 года. Экономически активные взрослые из семей с дневной "
    "или недельной оплатой, ранее сказали, что им интересен процентный сберегательный счёт. "
    "Примерно 19% женщин, 85% в браке, 89% имеют телефон. 44% живут ближе 2 км к банку, "
    "40% в 2–5 км, 16% дальше 5 км. Торговые точки для пополнения телефона обычно ближе."
)
OFFER = (
    "Предложение приходит письмом. Можно прийти в отделение госбанка в назначенные даты, "
    "открыть сберегательный счёт под 4% годовых и получить телефон с SIM-картой. Проект "
    "покрывает минимальный остаток при открытии. Затем сотрудник на дому показывает, "
    "как пополнить счёт: приобрести карту пополнения у местного агента и перевести "
    "сумму в банк с телефона через PIN. Учебные пополнения оплачивает проект. "
    "В отделении тоже можно вносить деньги. В течение двух месяцев самостоятельные "
    "мобильные пополнения дают шанс выиграть 5 000 LKR. "
    "Комиссия за самостоятельное мобильное пополнение — {fee}% от суммы пополнения."
)
QUESTION = (
    "Оцени вероятности двух событий среди всех, кому назначено это предложение, включая тех, "
    "кто откажется. accepted — человек придёт в отделение и откроет счёт. "
    "used — человек хотя бы раз сам пополнит его через телефон с момента запуска по май 2013 года "
    "включительно. Учебные пополнения не учитывай.\n"
    'Ответь JSON с полями "accepted" и "used", каждое число от 0 до 1, used не выше accepted.'
)
SYSTEMS = {
    "baseline": "Ты банковский исследователь. Дай две доли для всей описанной аудитории.",
    "twins": "Представь себя участником по данному профилю. Оцени две вероятности своего поведения.",
}


def profiles(n, seed):
    columns = []
    for index, levels in enumerate(TRAITS):
        values = []
        for weight, label in levels:
            values.append((weight * n, label))
        counts = [int(expected) for expected, _ in values]
        remaining = n - sum(counts)
        order = sorted(range(len(counts)), key=lambda i: values[i][0] - counts[i], reverse=True)
        for i in order[:remaining]:
            counts[i] += 1
        column = [label for (_, label), count in zip(values, counts, strict=True) for _ in range(count)]
        random.Random(f"{seed}:{index}").shuffle(column)
        columns.append(column)
    return ["; ".join(row) for row in zip(*columns, strict=True)]


def parse(raw):
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Ожидался JSON-объект событий.")
    accepted, used = (_probability(value.get(key)) for key in OUTCOMES)
    if accepted is None or used is None or used > accepted:
        raise ValueError("Ожидались вероятности 0 ≤ used ≤ accepted ≤ 1.")
    return {"accepted": accepted, "used": used}


async def collect(model, n, seed, concurrency):
    population = profiles(n, seed)
    sem = asyncio.Semaphore(concurrency)
    async with engine._client() as client:

        async def ask(fee, profile_id, profile):
            mode = "baseline" if profile is None else "twins"
            context = AUDIENCE if profile is None else f"{AUDIENCE}\nВаш профиль: {profile}."
            user = f"{context}\n\n{OFFER.format(fee=fee)}\n\n{QUESTION}"
            messages = [{"role": "system", "content": SYSTEMS[mode]}, {"role": "user", "content": user}]
            entry = {"fee": fee, "profile_id": profile_id}
            async with sem:
                try:
                    text = await llm_json.chat_json(client, model, messages, temperature=0)
                    return entry | parse(text)
                except (openai.APIError, ValueError) as exc:
                    return entry | {"error": type(exc).__name__}

        return await asyncio.gather(
            *(
                ask(fee, profile_id, profile)
                for fee in ARMS
                for profile_id, profile in [(None, None), *enumerate(population)]
            )
        )


def score(rows, n):
    valid = {(r["fee"], r["profile_id"]): r for r in rows if "error" not in r}
    matched = [i for i in range(n) if all((fee, i) in valid for fee in ARMS)]
    cells, scores = {}, {}
    for fee, (human_n, *rates) in ARMS.items():
        cells[fee] = {"human_n": human_n}
        for outcome, actual in zip(OUTCOMES, rates, strict=True):
            cells[fee][outcome] = {
                "observed": actual,
                "baseline": valid.get((fee, None), {}).get(outcome),
                "twins": mean(valid[fee, i][outcome] for i in matched) if matched else None,
            }

    for outcome in OUTCOMES:
        for method in SYSTEMS:
            comparable = all(c[outcome][method] is not None for c in cells.values())
            if not comparable:
                continue
            actual_gap = cells[0][outcome]["observed"] - cells[8][outcome]["observed"]
            predicted_gap = cells[0][outcome][method] - cells[8][outcome][method]
            scores.setdefault(outcome, {})[method] = {
                "mae_pp": round(
                    100 * mean(abs(c[outcome]["observed"] - c[outcome][method]) for c in cells.values()), 3
                ),
                "observed_gap_0_minus_8_pp": round(100 * actual_gap, 3),
                "estimated_gap_0_minus_8_pp": round(100 * predicted_gap, 3),
                "gap_error_pp": round(100 * abs(actual_gap - predicted_gap), 3),
            }
    return {"matched_n": len(matched), "cells": cells, "scores": scores}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--output", type=Path, default=Path("proof/mobile-savings.json"))
    args = parser.parse_args()
    model = os.getenv("LLM_MODEL")
    if args.n < 1 or args.concurrency < 1 or not model or not os.getenv("LLM_BASE_URL"):
        parser.error("Задайте LLM_MODEL, LLM_BASE_URL, положительные --n и --concurrency.")
    rows = asyncio.run(collect(model, args.n, args.seed, args.concurrency))
    report = {
        "source": SOURCE,
        "reference": "Table 1; profiles: Appendix Table A.2",
        "model": model,
        "seed": args.seed,
        "n": args.n,
        "protocol": {
            "audience": AUDIENCE,
            "offer": OFFER,
            "question": QUESTION,
            "systems": SYSTEMS,
            "traits": TRAITS,
            "temperature": 0,
            "json_mode": llm_json.mode(),
        },
        **score(rows, args.n),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"matched_n": report["matched_n"], "scores": report["scores"]}, ensure_ascii=False))
    return 0 if report["matched_n"] and len(report["scores"].get("used", {})) == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
