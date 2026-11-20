"""Retrospective benchmark against Choi et al., BIS WP 1147, Table A4."""

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
from dvoinik.population import _shares

SOURCE = (
    "https://www.bis.org/publications/"
    "working-paper-1147-central-bank-digital-currency-and-privacy-randomized-survey-experiment.pdf"
)
CONTEXTS = ("sensitive_offline", "sensitive_online", "ordinary_offline", "ordinary_online")
DESIGNS = {
    "cr": "CBDC stores identity and transaction records together at one public institution, which may link them.",
    "sr": "CBDC stores identity and transaction records at separate public institutions so the records cannot readily be linked.",
    "voucher": "For small payments, a CBDC anonymity voucher leaves no personal or transaction record, including for AML/CFT checks.",
}
PCU = "Using CBDC can prevent financial firms and big technology companies from using your personal and transaction data commercially."
# Table A4, columns without controls: reference arm mean plus unadjusted contrasts.
CONTROL = (0.223, 0.338, 0.240, 0.265)
DIFFERENCES = {
    "cr": (0, 0, 0, 0),
    "cr_pcu": (0.073, 0.038, 0.056, 0.029),
    "sr": (0.084, 0.108, 0.042, 0.020),
    "sr_pcu": (0.132, 0.143, 0.050, 0.053),
    "voucher": (0.066, 0.084, 0.017, 0.029),
    "voucher_pcu": (0.105, 0.120, 0.034, 0.063),
}
HUMAN = {
    arm: dict(zip(CONTEXTS, (round(a + b, 3) for a, b in zip(CONTROL, delta, strict=True)), strict=True))
    for arm, delta in DIFFERENCES.items()
}
OPTIONS = ("cbdc", "cash", "card", "mobile", "no_preference")
TRAITS = (
    (("woman", 0.509), ("man", 0.491)),
    (("age 19–29", 0.161), ("age 30–45", 0.263), ("age 46–59", 0.287), ("age 60+", 0.289)),
    (("lives in Seoul", 0.179), ("lives outside Seoul", 0.821)),
    (("married", 0.616), ("not married", 0.384)),
    (("college degree or higher", 0.470), ("no college degree", 0.530)),
    (
        ("usually chose cash in the preceding private in-store scenario without CBDC", 0.390),
        ("chose a debit or credit card in that preceding scenario", 0.342),
        ("chose a mobile payment service in that preceding scenario", 0.084),
        ("had no preference in that preceding scenario", 0.184),
    ),
)
AUDIENCE = (
    "An online survey of adults in South Korea about a new digital currency issued by the central bank (CBDC). "
    "Around 51% women, 18% in Seoul, 62% married, 47% with a college degree. "
    "Age breakdown: 16% ages 19–29, 26% ages 30–45, 29% ages 46–59, 29% age 60+. "
    "Before CBDC is offered, for a private purchase in person about 39% choose cash, 34% card, 8% mobile, and the rest have no preference."
)
QUESTION = (
    "Imagine buying something private, such as a mental health service, and something ordinary, such as food. "
    "Consider both in-person and online purchases, weighing convenience and privacy. "
    "For each of sensitive_offline, sensitive_online, ordinary_offline, ordinary_online, "
    "the choices are cbdc (the central bank digital currency above), card (credit or debit), "
    "mobile (a fast mobile payment service), no_preference, and cash (in person only). "
    "Cash can generally be used without linking payment records to your identity; card and mobile payments leave linked records."
)
SYSTEMS = {
    "baseline": "You are a survey researcher. Predict the share choosing CBDC in each setting.",
    "twins": "You are a participant in this survey. Choose one payment method in each setting for the person described.",
}


def profiles(n, seed):
    columns = [
        _shares(list(levels), n, random.Random(f"{seed}:{index}")) for index, levels in enumerate(TRAITS)
    ]
    return ["; ".join(row) for row in zip(*columns, strict=True)]


def parse(raw, mode):
    response = json.loads(raw)
    if not isinstance(response, dict) or set(response) != set(CONTEXTS):
        raise ValueError("Expected all four survey outcomes.")
    if mode == "baseline":
        shares = {key: _probability(value) for key, value in response.items()}
        if None in shares.values():
            raise ValueError("Expected shares in [0, 1].")
        return shares
    for key, value in response.items():
        if value not in OPTIONS or (key.endswith("_online") and value == "cash"):
            raise ValueError("Unsupported payment method.")
    return {key: float(value == "cbdc") for key, value in response.items()}


INDIVIDUAL_SYSTEM = "You are a participant in this survey. Estimate the probability that you would choose CBDC in each setting."
INDIVIDUAL_OUTPUT = (
    "Return a JSON object mapping the four settings to your personal probability of choosing cbdc, "
    "each a number from 0 to 1. A probability is not a yes/no answer."
)
PROFILE_TEST_ARMS = ("cr", "sr", "sr_pcu")


def prompt(arm, profile, *, individual_probabilities=False):
    design = DESIGNS[arm.removesuffix("_pcu")]
    terms = f"{design} {PCU}" if arm.endswith("_pcu") else design
    persona = f"\nYour profile: {profile}." if profile is not None else ""
    if individual_probabilities:
        output = INDIVIDUAL_OUTPUT
    elif profile is None:
        output = "Return a JSON object mapping the four settings to the fraction choosing cbdc, each a number from 0 to 1."
    else:
        output = "Return a JSON object mapping the four settings to your four payment method names as lowercase strings."
    return f"{AUDIENCE}{persona}\n\nCBDC design: {terms}\n\n{QUESTION}\n{output}"


async def collect(model, population, concurrency, *, arms=tuple(HUMAN), individual_probabilities=False):
    sem = asyncio.Semaphore(concurrency)
    async with engine._client() as client:

        async def ask(arm, index, profile):
            mode = "baseline" if index is None else "twins"
            row = {"arm": arm, "profile_id": index}
            system = INDIVIDUAL_SYSTEM if individual_probabilities else SYSTEMS[mode]
            messages = [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": prompt(arm, profile, individual_probabilities=individual_probabilities),
                },
            ]
            numeric = individual_probabilities or mode == "baseline"
            async with sem:
                for count in range(1, 3):
                    try:
                        raw = await llm_json.chat_json(client, model, messages, 0)
                        return row | {
                            "predictions": parse(raw, "baseline" if numeric else "twins"),
                            "attempts": count,
                        }
                    except (openai.APIError, ValueError) as exc:
                        error = type(exc).__name__
            return row | {"error": error, "attempts": count}

        return await asyncio.gather(
            *(ask(arm, i, profile) for arm in arms for i, profile in [(None, None), *enumerate(population)])
        )


def score(rows, n, *, arms=tuple(HUMAN)):
    valid = {(r["arm"], r["profile_id"]): r["predictions"] for r in rows if "error" not in r}
    matched = [i for i in range(n) if all((arm, i) in valid for arm in arms)]
    estimates = {
        "baseline": {arm: valid.get((arm, None)) for arm in arms},
        "twins": {
            arm: {context: mean(valid[arm, i][context] for i in matched) for context in CONTEXTS}
            if matched
            else None
            for arm in arms
        },
    }
    metrics = {}
    for mode, prediction in estimates.items():
        if any(result is None for result in prediction.values()):
            continue
        metrics[mode] = {}
        for context in CONTEXTS:
            predicted_effects = {a: 100 * (prediction[a][context] - prediction["cr"][context]) for a in arms}
            observed_effects = {a: 100 * (HUMAN[a][context] - HUMAN["cr"][context]) for a in arms}
            metrics[mode][context] = {
                "level_mae_pp": round(
                    100 * mean(abs(prediction[a][context] - HUMAN[a][context]) for a in arms), 3
                ),
                "effect_mae_pp": round(
                    mean(abs(predicted_effects[a] - observed_effects[a]) for a in arms if a != "cr"), 3
                ),
                "combined_effect_pp": round(predicted_effects["sr_pcu"], 3),
                "observed_combined_effect_pp": round(observed_effects["sr_pcu"], 3),
            }
    return {"matched_n": len(matched), "estimates": estimates, "metrics": metrics}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--profile-test",
        action="store_true",
        help="Три условия. Одинаковая вероятность на выходе с профилем и без него.",
    )
    args = parser.parse_args()
    model = os.getenv("LLM_MODEL")
    if min(args.n, args.concurrency) < 1 or not model or not os.getenv("LLM_BASE_URL"):
        parser.error("Задайте LLM_MODEL, LLM_BASE_URL и положительные --n, --concurrency.")
    population = profiles(args.n, args.seed)
    arms = PROFILE_TEST_ARMS if args.profile_test else tuple(HUMAN)
    rows = asyncio.run(
        collect(model, population, args.concurrency, arms=arms, individual_probabilities=args.profile_test)
    )
    result = score(rows, args.n, arms=arms)
    if args.profile_test:
        for key in ("estimates", "metrics"):
            result[key] = {
                "without_profile": result[key].pop("baseline", None),
                "with_profile": result[key].pop("twins", None),
            }
    report = {
        "model": model,
        "n": args.n,
        "seed": args.seed,
        "source": SOURCE,
        "human": {arm: HUMAN[arm] for arm in arms},
        "protocol": {
            "audience": AUDIENCE,
            "designs": DESIGNS,
            "pcu": PCU,
            "question": QUESTION,
            "systems": INDIVIDUAL_SYSTEM if args.profile_test else SYSTEMS,
            "output_format": INDIVIDUAL_OUTPUT
            if args.profile_test
            else "aggregate share / individual categorical choice",
            "profiles": population,
            "temperature": 0,
        },
        **result,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"matched_n": report["matched_n"], "metrics": report["metrics"]}, ensure_ascii=False))
    return 0 if len(report["metrics"]) == 2 and all(report["metrics"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
