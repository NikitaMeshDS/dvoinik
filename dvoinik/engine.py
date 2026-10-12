"""Движок симуляции: каждый двойник получает вариант продукта и решает, объясняя причину.

LLM: любая OpenAI-совместимая модель (on-prem vLLM/Ollama, российские модели через шлюз).
Режим mock: эвристическая модель без LLM — для демо и тестов без GPU.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
from collections import Counter, defaultdict

from .population import SEGMENTS, Twin

SYSTEM = (
    "Ты — конкретный клиент банка, описанный ниже. Отвечай от первого лица, как этот человек, "
    "учитывая его возраст, доход, привычки и отношение к банкам. Не будь чрезмерно позитивным: "
    "реальные клиенты часто отказываются, если не видят явной пользы.\n"
    "Ответь строго JSON: {\"decision\": true|false, \"probability\": 0..1, "
    "\"objection\": одна категория из списка или null, \"quote\": одна фраза от первого лица}"
)


def _client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
                       api_key=os.getenv("LLM_API_KEY", "ollama"))


async def _ask_llm(client, model, twin: Twin, scenario: dict, variant_text: str, sem):
    user = (f"Ты: {twin.profile()}\n\nБанк предлагает: {variant_text}\n\n"
            f"Вопрос: {scenario['question']}\n"
            f"Категории отказа: {', '.join(scenario['objections'])}")
    async with sem:
        r = await client.chat.completions.create(
            model=model, temperature=0.8, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
    try:
        out = json.loads(r.choices[0].message.content)
    except json.JSONDecodeError:
        out = {"decision": False, "probability": 0.0, "objection": None, "quote": ""}
    if out.get("objection") not in scenario["objections"]:
        out["objection"] = None if out.get("decision") else scenario["objections"][-2]
    return out


# ---- эвристический режим (без LLM) ----
KEYWORDS = {
    "бесплат": {"student_reg": .25, "student_msk": .1, "self_employed": .15, "nonresident": .1},
    "кэшбэк": {"student_msk": .15, "young_family": .1, "teen": .05},
    "челлендж": {"teen": .3, "student_msk": .1, "senior": -.2},
    "друз": {"teen": .15},
    "приложени": {"senior": -.25},
    "отделени": {"senior": .25},
    "мошенник": {"senior": .3, "young_family": .05},
    "языках": {"nonresident": .3},
    "родном": {"nonresident": .2},
    "₽/мес": {"student_reg": -.25, "student_msk": -.1, "teen": -.1, "young_family": -.05},
    "комиссия": {"self_employed": -.15, "nonresident": -.1},
    "без комиссии": {"self_employed": .25, "nonresident": .2},
    "прогноз": {"self_employed": .15},
    "налог": {"self_employed": .15},
    "годовых": {"young_family": -.1, "student_reg": -.1},
    "напомним": {"young_family": .1, "student_reg": .05},
    "только сегодня": {"senior": -.2, "young_family": -.1, "student_msk": -.05},
    "примерно": {"young_family": .15, "senior": .1, "self_employed": .1},
    "личные": {"young_family": .15, "teen": .1},
    "видит все траты": {"young_family": -.1, "teen": -.15},
}
BASE = {"student_msk": .35, "student_reg": .3, "teen": .3, "young_family": .3,
        "senior": .2, "self_employed": .3, "nonresident": .25}


def _ask_mock(rng: random.Random, twin: Twin, scenario: dict, variant_text: str):
    t = variant_text.lower()
    p = BASE[twin.segment] + sum(v.get(twin.segment, 0) for k, v in KEYWORDS.items() if k in t)
    p = min(.92, max(.03, p + rng.gauss(0, .08)))
    decision = rng.random() < p
    objections = scenario["objections"]
    obj = None if decision else objections[min(len(objections) - 1, int(rng.random() ** 1.6 * len(objections)))]
    quote = ("Звучит выгодно, попробую." if decision else f"Нет, главное — {obj}.")
    return {"decision": decision, "probability": round(p, 2), "objection": obj, "quote": quote}


def simulate(twins: list[Twin], scenario: dict, mock: bool = False, seed: int = 0,
             concurrency: int = 16) -> dict:
    """Прогоняет все варианты сценария через популяцию. Возвращает отчёт по вариантам."""
    results = {}
    if mock:
        for vid, text in scenario["variants"].items():
            rng = random.Random(f"{seed}-{vid}")
            results[vid] = [(tw, _ask_mock(rng, tw, scenario, text)) for tw in twins]
    else:
        client, model = _client(), os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")

        async def run():
            sem = asyncio.Semaphore(concurrency)
            for vid, text in scenario["variants"].items():
                outs = await asyncio.gather(*[_ask_llm(client, model, tw, scenario, text, sem)
                                              for tw in twins])
                results[vid] = list(zip(twins, outs))
        asyncio.run(run())
    return {vid: aggregate(rows) for vid, rows in results.items()}


def aggregate(rows) -> dict:
    by_seg = defaultdict(lambda: [0, 0])
    objections, quotes = Counter(), []
    for tw, out in rows:
        by_seg[tw.segment][0] += 1
        if out["decision"]:
            by_seg[tw.segment][1] += 1
        elif out["objection"]:
            objections[out["objection"]] += 1
        if out.get("quote") and len(quotes) < 6:
            quotes.append({"who": f"{tw.name}, {tw.age}, {tw.region}",
                           "segment": SEGMENTS[tw.segment]["name"],
                           "decision": out["decision"], "quote": out["quote"]})
    n = len(rows)
    yes = sum(v[1] for v in by_seg.values())
    return {
        "n": n, "conversion": yes / n if n else 0,
        "segments": {s: {"name": SEGMENTS[s]["name"], "n": v[0], "conversion": v[1] / v[0]}
                     for s, v in by_seg.items()},
        "objections": dict(objections.most_common()),
        "quotes": quotes,
    }
