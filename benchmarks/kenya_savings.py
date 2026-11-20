"""Retrospective benchmark against Schaner (2018), Table 2."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from pathlib import Path
from statistics import linear_regression, mean

import openai

from benchmarks.mobile_savings import OUTCOMES, SYSTEMS, parse
from dvoinik import engine, llm_json
from dvoinik.population import _shares

SOURCE = "https://doi.org/10.1257/app.20170453"
RATES = (0, 4, 12, 20)
# Base group observed means and coefficients from Table 2, columns 1–2.
HUMAN = {"accepted": {"rate_at_zero": 0.31, "effect": 0.17}, "used": {"rate_at_zero": 0.06, "effect": 0.09}}
TRAITS = (
    (("женщина", 0.5), ("мужчина", 0.5)),
    (("есть банковский счёт в другом банке", 0.22), ("банковского счёта нет", 0.78)),
    (("откладывает наличные дома", 0.872), ("не откладывает наличные дома", 0.128)),
    (("участвует в кассе взаимопомощи", 0.581), ("не участвует в кассе взаимопомощи", 0.419)),
)
AUDIENCE = (
    "Западная Кения, 2009 год. Супруги из сельских общин рядом с Бусиа, без счёта в банке-партнёре, "
    "ранее выразили интерес к открытию счёта и пришли вместе на встречу в местной школе. "
    "Средний возраст 40 лет, медианный доход участника 2167 KES в месяц, среднее расстояние до банка около 6 км. "
    "Половина участников — женщины, у 22% есть счёт в другом банке. 87% откладывают наличные дома, "
    "58% участвуют в кассе взаимопомощи. Обычно низкие остатки в банках не приносили процентов."
)
OFFER = (
    "На встрече можно бесплатно открыть личный счёт, отдельный счёт супруга и/или совместный счёт. "
    "Проект вносит минимальный остаток 100 KES на каждый открытый счёт. Платы за обслуживание и пополнение нет. "
    "Снятие стоит 62 KES в кассе или 30 KES в банкомате. "
    "Ставка вашего личного счёта {rate}% годовых на первые шесть месяцев, затем проценты не начисляются. "
    "Сотрудники объясняют условия и показывают числовые примеры. "
    "После решения об открытии проходит отдельный розыгрыш. У каждого шанс 20% получить 10–300 KES "
    "с возможностью забрать приз в офисе проекта или зачислить его на новый счёт."
)
QUESTION = (
    "Оцени две безусловные вероятности, учитывая и тех, кто счёт не откроет. "
    "accepted — открыть свой личный счёт на этой встрече. "
    "used — получить хотя бы одно пополнение на этот личный счёт за первые шесть месяцев, "
    "включая зачисление приза при выигрыше, без стартовых 100 KES. "
    'Ответь JSON с полями "accepted" и "used", числами от 0 до 1, used не выше accepted.'
)


def make_profiles(n, seed):
    columns = [_shares(list(levels), n, random.Random(f"{seed}:{i}")) for i, levels in enumerate(TRAITS)]
    competitors = [(spouse, joint) for spouse in RATES for joint in RATES[1:]]
    alternatives = (competitors * ((n + len(competitors) - 1) // len(competitors)))[:n]
    random.Random(f"{seed}:alternative").shuffle(alternatives)
    return [
        f"{'; '.join(traits)}. Ставка личного счёта супруга {spouse}%, совместного — {joint}%."
        for traits, (spouse, joint) in zip(zip(*columns, strict=True), alternatives, strict=True)
    ]


async def collect(model, n, seed, concurrency):
    profiles = make_profiles(n, seed)
    population_context = (
        "Для каждого участника ставка личного счёта супруга независимо и равновероятно назначается "
        "из 0%, 4%, 12% и 20%, а совместного — из 4%, 12% и 20%."
    )
    sem = asyncio.Semaphore(concurrency)
    async with engine._client() as client:

        async def ask(rate, index, profile):
            mode = "baseline" if profile is None else "twins"
            context = population_context if profile is None else f"Ваш профиль: {profile}"
            user = f"{AUDIENCE}\n{context}\n\n{OFFER.format(rate=rate)}\n\n{QUESTION}"
            messages = [{"role": "system", "content": SYSTEMS[mode]}, {"role": "user", "content": user}]
            row = {"rate": rate, "profile_id": index}
            async with sem:
                try:
                    raw = await llm_json.chat_json(client, model, messages, temperature=0)
                    return row | parse(raw)
                except (openai.APIError, ValueError) as exc:
                    return row | {"error": type(exc).__name__}

        rows = await asyncio.gather(
            *(ask(rate, i, profile) for rate in RATES for i, profile in [(None, None), *enumerate(profiles)])
        )
    return rows, profiles, population_context


def score(rows, n):
    valid = {(r["rate"], r["profile_id"]): r for r in rows if "error" not in r}
    matched = [i for i in range(n) if all((rate, i) in valid for rate in RATES)]
    cells, scores = {}, {}
    for rate in RATES:
        cells[rate] = {
            key: {
                "baseline": valid.get((rate, None), {}).get(key),
                "twins": mean(valid[rate, i][key] for i in matched) if matched else None,
            }
            for key in OUTCOMES
        }
    for key, human in HUMAN.items():
        scores[key] = {}
        for mode in SYSTEMS:
            estimates = [cells[rate][key][mode] for rate in RATES]
            if None in estimates:
                continue
            effect = linear_regression([rate / 20 for rate in RATES], estimates).slope
            scores[key][mode] = {
                "error_at_zero_pp": round(100 * abs(estimates[0] - human["rate_at_zero"]), 3),
                "estimated_effect_pp": round(100 * effect, 3),
                "effect_error_pp": round(100 * abs(effect - human["effect"]), 3),
            }
    return {"matched_n": len(matched), "cells": cells, "scores": scores}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--output", type=Path, default=Path("proof/kenya-savings.json"))
    args = parser.parse_args()
    model = os.getenv("LLM_MODEL")
    if args.n < 12 or args.n % 12 or args.concurrency < 1 or not model or not os.getenv("LLM_BASE_URL"):
        parser.error("Задайте LLM_MODEL и LLM_BASE_URL, положительный --concurrency и --n, кратное 12.")
    rows, profiles, population_context = asyncio.run(collect(model, args.n, args.seed, args.concurrency))
    report = {
        "model": model,
        "n": args.n,
        "seed": args.seed,
        "source": SOURCE,
        "human_reference": HUMAN,
        "protocol": {
            "audience": AUDIENCE,
            "offer": OFFER,
            "question": QUESTION,
            "systems": SYSTEMS,
            "profiles": profiles,
            "baseline_context": population_context,
            "temperature": 0,
        },
        **score(rows, args.n),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"matched_n": report["matched_n"], "scores": report["scores"]}, ensure_ascii=False))
    return 0 if report["matched_n"] and all(len(value) == 2 for value in report["scores"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
