"""Retrospective benchmark against FDIC 2023 household survey, Tables B.1 and B.6."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from itertools import product
from pathlib import Path
from statistics import mean

import openai

from benchmark import _probability
from dvoinik import engine, llm_json

SOURCE = (
    "https://www.fdic.gov/household-survey/"
    "2023-fdic-national-survey-unbanked-and-underbanked-households-appendix-tables"
)
METHODS = {
    "atm": "automated teller machine or bank kiosk",
    "teller": "in-person bank teller",
    "mobile": "app, text messaging, or browser on a mobile phone",
    "online": "banking through a computer or tablet",
    "telephone": "calling the bank",
    "other": "some other way",
}
# Table B.1: percent among adequately observed banked households. Table B.6:
# smartphone access among all households, used as an approximate input.
DATA = {
    "25–34": ((9.8, 4.6, 74.8, 9.8, 0.7, 0.3), 0.934),
    "35–44": ((12.0, 6.4, 66.4, 14.0, 0.8, 0.3), 0.934),
    "45–54": ((13.2, 10.3, 54.7, 20.1, 1.2, 0.5), 0.924),
    "55–64": ((16.0, 15.8, 39.7, 25.8, 2.3, 0.5), 0.898),
    "65+": ((16.7, 30.4, 19.3, 27.2, 5.1, 1.4), 0.763),
}
HUMAN = {group: dict(zip(METHODS, row, strict=True)) for group, (row, _) in DATA.items()}
MODES = ("aggregate", "without_device", "with_device")
ORDERS = ("published", "reversed")
QUESTION = "Which one method did the household use most to access its bank accounts in the last 12 months?"
POPULATION = "In the June 2023 United States, consider households with a bank account they accessed in the prior 12 months."
SYSTEMS = {
    "aggregate": "You are a survey researcher. Estimate the distribution of answers from these households.",
    "individual": "You are a respondent answering on behalf of your household. Estimate your probability of giving each answer.",
}


def messages(age, order, mode, access=None):
    methods = list(METHODS.items())
    if order == "reversed":
        methods.reverse()
    options = "\n".join(f"{key}: {label}" for key, label in methods)
    group = f"The age of the household reference person is {age}."
    device = ""
    if access is True:
        device = "\nAt least one member of the household has access to a smartphone."
    elif access is False:
        device = "\nNobody in the household has access to a smartphone."
    use = "share of households" if mode == "aggregate" else "your household's probability"
    task = f"Return JSON mapping the six listed keys to {use} for each as a number from 0 to 1. The numbers must sum to 1."
    content = f"{POPULATION}\n{group}{device}\n\n{QUESTION}\n{options}\n\n{task}"
    return [
        {"role": "system", "content": SYSTEMS["aggregate" if mode == "aggregate" else "individual"]},
        {"role": "user", "content": content},
    ]


def parse(raw):
    obj = json.loads(raw)
    if not isinstance(obj, dict) or set(obj) != set(METHODS):
        raise ValueError("Expected all six banking methods.")
    dist = {key: _probability(value) for key, value in obj.items()}
    if None in dist.values() or not 0.98 <= sum(dist.values()) <= 1.02:
        raise ValueError("Expected probabilities summing to 1, within rounding tolerance.")
    total = sum(dist.values())
    return {key: value / total for key, value in dist.items()}


async def collect(model, concurrency, structured=False):
    sem = asyncio.Semaphore(concurrency)
    variants = (("aggregate", None), ("without_device", None), ("with_device", True), ("with_device", False))
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "channel_probabilities",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {method: {"type": "number"} for method in METHODS},
                "required": list(METHODS),
                "additionalProperties": False,
            },
        },
    }
    async with engine._client() as client:

        async def request(prompt):
            if not structured:
                return await llm_json.chat_json(client, model, prompt, 0)
            response = await client.chat.completions.create(
                model=model,
                messages=prompt,
                temperature=0,
                response_format=response_format,
                extra_body=llm_json.extra_body(),
            )
            return llm_json.extract(response.choices[0].message.content)

        async def ask(age, order, mode, access):
            row = {"age": age, "order": order, "mode": mode, "access": access}
            prompt = messages(age, order, mode, access)
            async with sem:
                for attempt in range(1, 3):
                    try:
                        return row | {
                            "probabilities": parse(await request(prompt)),
                            "attempts": attempt,
                        }
                    except (openai.APIError, ValueError) as exc:
                        error = type(exc).__name__
            return row | {"error": error, "attempts": attempt}

        return await asyncio.gather(
            *(ask(age, order, *variant) for age, order, variant in product(DATA, ORDERS, variants))
        )


def score(rows):
    index = {
        (r["age"], r["order"], r["mode"], r["access"]): r["probabilities"] for r in rows if "error" not in r
    }
    report = {}
    for mode in MODES:
        cohorts = {}
        for age, (_, smartphone) in DATA.items():
            weights = {True: smartphone, False: 1 - smartphone} if mode == "with_device" else {None: 1}
            if any(
                (age, order, mode, available) not in index for order, available in product(ORDERS, weights)
            ):
                continue
            predictions = {
                order: {
                    method: sum(
                        weight * index[age, order, mode, available][method]
                        for available, weight in weights.items()
                    )
                    for method in METHODS
                }
                for order in ORDERS
            }
            cohorts[age] = {
                "mean_percent": {
                    method: 100 * mean(d[method] for d in predictions.values()) for method in METHODS
                },
                "order_shift_pp": {
                    method: 100 * abs(predictions[ORDERS[0]][method] - predictions[ORDERS[1]][method])
                    for method in METHODS
                },
            }
        if len(cohorts) != len(DATA):
            report[mode] = {"cohorts": cohorts, "metrics": None}
            continue
        estimates = {age: cell["mean_percent"] for age, cell in cohorts.items()}
        report[mode] = {
            "cohorts": cohorts,
            "metrics": {
                "level_mae_pp": {
                    method: mean(abs(estimates[age][method] - HUMAN[age][method]) for age in DATA)
                    for method in METHODS
                },
                "oldest_vs_youngest_pp": {
                    method: estimates["65+"][method] - estimates["25–34"][method] for method in METHODS
                },
                "mobile_minus_teller_65_pp": estimates["65+"]["mobile"] - estimates["65+"]["teller"],
            },
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--structured", action="store_true", help="Request a JSON schema from the server.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    model = os.getenv("LLM_MODEL")
    if args.concurrency < 1 or not model or not os.getenv("LLM_BASE_URL"):
        parser.error("Задайте LLM_MODEL, LLM_BASE_URL и положительный --concurrency.")
    rows = asyncio.run(collect(model, args.concurrency, args.structured))
    report = {
        "model": model,
        "source": SOURCE,
        "human": HUMAN,
        "smartphone_weights": {age: data[1] for age, data in DATA.items()},
        "protocol": {
            "question": QUESTION,
            "population": POPULATION,
            "systems": SYSTEMS,
            "methods": METHODS,
            "orders": ORDERS,
            "temperature": 0,
            "output_format": "json_schema" if args.structured else llm_json.mode(),
        },
        "results": score(rows),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {mode: result["metrics"] for mode, result in report["results"].items()}, ensure_ascii=False
        )
    )
    return 0 if all(result["metrics"] is not None for result in report["results"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
