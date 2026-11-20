"""Retrospective wording benchmark based on UAS 117."""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import os
from pathlib import Path
from statistics import mean

import openai

from benchmark import _probability
from dvoinik import engine, llm_json

SOURCE = "https://pmc.ncbi.nlm.nih.gov/articles/PMC9643168/"
ARMS = {
    "hrs": (
        "Other than assets already reported, do you or your spouse or partner hold a checking account, savings account, or money market fund? Leave out certificates of deposit (CDs).",
    ),
    "simple_i": (
        "Do you or your spouse or partner hold a checking account, savings account, or money market fund?",
    ),
    "simple_ii": (
        "Do you or your spouse or partner hold a checking or savings account?",
        "Do you or your spouse or partner hold a money market fund?",
    ),
}
PREFIX = (
    ("stocks", "Do you or your spouse or partner hold stocks or stock mutual funds?"),
    ("bonds", "Do you or your spouse or partner hold bonds or bond funds?"),
    ("cds", "Do you or your spouse or partner hold CDs, government savings bonds, or Treasury bills?"),
)
# Rounded chart labels in Figure 1; original unconditional contrasts from Table 1.
HUMAN = {"hrs": 0.74, "simple_i": 0.85, "simple_ii": 0.92}
CONTRASTS = (("hrs", "simple_i", 10.77), ("simple_i", "simple_ii", 6.99), ("hrs", "simple_ii", 17.75))
AUDIENCE = "An English-language, self-administered online survey of U.S. adults in late 2017."
PROFILE_DESIGN = (
    (25, 40, 55, 70),
    ("lives without a spouse or partner", "lives with a spouse or partner"),
    ("under $30,000", "$30,000 to $75,000", "over $75,000"),
)
BASELINE_SYSTEM = "You are a survey researcher. Estimate the fraction of participants who would answer yes."
TWIN_SYSTEM = (
    "You are a survey participant. Answer as this particular person and use the questionnaire as presented."
)


def profile_context():
    return [
        f"Age {age}; {partner}; annual household income {income}."
        for age, partner, income in itertools.product(*PROFILE_DESIGN)
    ]


def participant_prompt(profile):
    return f"{AUDIENCE}\nYour profile: {profile}\n\n"


def prompt_for_arm(arm):
    if arm == "simple_ii":
        return (
            "\n".join(ARMS[arm])
            + '\nAnswer with JSON containing two booleans "accounts" and "funds", one for each question in order.'
        )
    return ARMS[arm][0] + '\nAnswer with JSON containing one boolean "yes".'


def parse_yes(raw, arm):
    obj = json.loads(raw)
    keys = ("accounts", "funds") if arm == "simple_ii" else ("yes",)
    return any(read_bools(obj, keys).values())


def read_bools(obj, keys):
    if not isinstance(obj, dict) or any(type(obj.get(k)) is not bool for k in keys):
        raise ValueError("Expected boolean answers.")
    return {k: obj[k] for k in keys}


def parse_share(raw):
    obj = json.loads(raw)
    rate = _probability(obj.get("share")) if isinstance(obj, dict) else None
    if rate is None:
        raise ValueError("Expected a share in [0, 1].")
    return rate


async def collect(model, concurrency):
    profiles = profile_context()
    sem = asyncio.Semaphore(concurrency)
    rows = []
    async with engine._client() as client:

        async def ask(messages, parser):
            for attempt in range(2):
                try:
                    async with sem:
                        raw = await llm_json.chat_json(client, model, messages, temperature=0)
                    return {"rate": parser(raw), "attempts": attempt + 1}
                except (openai.APIError, ValueError) as exc:
                    error = type(exc).__name__
            return {"error": error}

        def message(role, content):
            return {"role": role, "content": content}

        prefix_text = "\n".join(f"{key}: {question}" for key, question in PREFIX)

        async def baseline(arm):
            user = (
                f"{AUDIENCE} Adults vary by age, household income and whether they have a spouse or partner. "
                "Before the target wording, the survey asks these questions in order:\n"
                f"{prefix_text}\n\nTarget wording:\n"
                + "\n".join(ARMS[arm])
                + '\nFor two questions, count people who answer yes to either. Return JSON with one number "share" from 0 to 1.'
            )
            result = await ask([message("system", BASELINE_SYSTEM), message("user", user)], parse_share)
            return {"arm": arm, "profile_id": None} | result

        async def participant(index, profile):
            system = message("system", TWIN_SYSTEM)
            context = participant_prompt(profile)
            first = await ask(
                [
                    system,
                    message(
                        "user",
                        context + prefix_text + '\nReturn JSON with booleans "stocks", "bonds", "cds".',
                    ),
                ],
                lambda raw: read_bools(json.loads(raw), [key for key, _ in PREFIX]),
            )
            if "error" in first:
                return [
                    {"arm": arm, "profile_id": index, "error": f"prefix:{first['error']}"} for arm in ARMS
                ]
            history = [system]
            for i, (key, question) in enumerate(PREFIX):
                history.append(message("user", (context if i == 0 else "") + question))
                history.append(message("assistant", "Yes." if first["rate"][key] else "No."))

            async def target(arm):
                result = await ask(
                    [*history, message("user", prompt_for_arm(arm))],
                    lambda raw: parse_yes(raw, arm),
                )
                return {"arm": arm, "profile_id": index, "preceding_answers": first["rate"]} | result

            return await asyncio.gather(*(target(arm) for arm in ARMS))

        rows.extend(await asyncio.gather(*(baseline(arm) for arm in ARMS)))
        for i in range(0, len(profiles), concurrency):
            batch = await asyncio.gather(
                *(participant(j, profiles[j]) for j in range(i, min(i + concurrency, len(profiles))))
            )
            for group in batch:
                rows.extend(group)
    return rows


def score(rows, n):
    valid = {(r["arm"], r["profile_id"]): r["rate"] for r in rows if "error" not in r}
    complete = [i for i in range(n) if all((a, i) in valid for a in ARMS)]
    cells = {
        a: {
            "observed_rounded": HUMAN[a],
            "baseline": valid.get((a, None)),
            "twins": mean(valid[a, i] for i in complete) if complete else None,
        }
        for a in ARMS
    }
    scores = {}
    for method in ("baseline", "twins"):
        if any(c[method] is None for c in cells.values()):
            continue
        effects = []
        for first, last, actual in CONTRASTS:
            estimated = 100 * (cells[last][method] - cells[first][method])
            effects.append(
                {
                    "from": first,
                    "to": last,
                    "observed_pp": actual,
                    "estimated_pp": round(estimated, 3),
                    "absolute_error_pp": round(abs(estimated - actual), 3),
                }
            )
        scores[method] = {
            "level_mae_pp": round(
                100 * mean(abs(c[method] - c["observed_rounded"]) for c in cells.values()), 3
            ),
            "effect_mae_pp": round(mean(e["absolute_error_pp"] for e in effects), 3),
            "contrasts": effects,
        }
    return {"matched_n": len(complete), "cells": cells, "scores": scores}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = os.getenv("LLM_MODEL")
    if not model or not os.getenv("LLM_BASE_URL") or args.concurrency < 1:
        parser.error("Задайте LLM_MODEL, LLM_BASE_URL и положительный --concurrency.")
    n = len(profile_context())
    rows = asyncio.run(collect(model, args.concurrency))
    report = {
        "model": model,
        "source": SOURCE,
        "n": n,
        "protocol": {
            "audience": AUDIENCE,
            "prefix": PREFIX,
            "questions": ARMS,
            "profiles": profile_context(),
            "temperature": 0,
            "wording": "English paraphrases of Section 4.1",
        },
        **score(rows, n),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"matched_n": report["matched_n"], "scores": report["scores"]}, ensure_ascii=False))
    return 0 if len(report["scores"]) == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
