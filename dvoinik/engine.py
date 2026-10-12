"""Движок симуляции: каждый двойник получает вариант продукта и решает, объясняя причину.

LLM: любая OpenAI-совместимая модель (on-prem vLLM/Ollama, российские модели через шлюз).
Режим mock: эвристическая модель без LLM — для демо и тестов без GPU.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import random
from collections import Counter, defaultdict
from collections.abc import Callable

from .population import SEGMENTS, Twin

SYSTEM = (
    "Ты — конкретный клиент банка, описанный ниже. Отвечай от первого лица, как этот человек, "
    "учитывая его возраст, доход, привычки и отношение к банкам. Не будь чрезмерно позитивным: "
    "реальные клиенты часто отказываются, если не видят явной пользы.\n"
    'Ответь строго JSON: {"decision": true|false, "probability": 0..1, '
    '"objection": одна категория из списка или null, "quote": одна фраза от первого лица}'
)


def _client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("LLM_API_KEY", "ollama"),
        timeout=45,
        max_retries=2,
    )


def _parse_response(content, scenario):
    out = json.loads(content)
    if not isinstance(out, dict) or type(out.get("decision")) is not bool:
        raise ValueError("decision должен быть true или false")
    probability = out.get("probability")
    if (
        isinstance(probability, bool)
        or not isinstance(probability, (int, float))
        or not math.isfinite(probability)
        or not 0 <= probability <= 1
    ):
        raise ValueError("probability должна быть числом от 0 до 1")
    if not isinstance(out.get("quote"), str) or not out["quote"].strip():
        raise ValueError("quote должна содержать объяснение")
    objection = out.get("objection")
    if not out["decision"] and objection not in scenario["objections"]:
        raise ValueError("objection должна быть категорией из сценария")
    return {
        "decision": out["decision"],
        "probability": probability,
        "objection": None if out["decision"] else objection,
        "quote": out["quote"].strip()[:1000],
    }


async def _ask_llm(client, model, twin: Twin, scenario: dict, variant_text: str, sem):
    user = (
        f"Ты: {twin.profile()}\n\nБанк предлагает: {variant_text}\n\n"
        f"Вопрос: {scenario['question']}\n"
        f"Категории отказа: {', '.join(scenario['objections'])}"
    )
    async with sem:
        try:
            r = await client.chat.completions.create(
                model=model,
                temperature=0.8,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            )
            return _parse_response(r.choices[0].message.content, scenario)
        except (ValueError, TypeError, IndexError, AttributeError):
            return {"error": "Модель вернула ответ, не соответствующий JSON-схеме."}
        except Exception as exc:
            # Не включаем тело HTTP-ответа, URL или ключ в экспортируемые отчёты.
            return {
                "error": f"Запрос к модели не выполнен ({type(exc).__name__}).",
                "error_kind": type(exc).__name__,
            }


# ---- эвристический режим (без LLM) ----
KEYWORDS = {
    "бесплат": {"student_reg": 0.25, "student_msk": 0.1, "self_employed": 0.15, "nonresident": 0.1},
    "кэшбэк": {"student_msk": 0.15, "young_family": 0.1, "teen": 0.05},
    "челлендж": {"teen": 0.3, "student_msk": 0.1, "senior": -0.2},
    "друз": {"teen": 0.15},
    "приложени": {"senior": -0.25},
    "отделени": {"senior": 0.25},
    "мошенник": {"senior": 0.3, "young_family": 0.05},
    "языках": {"nonresident": 0.3},
    "родном": {"nonresident": 0.2},
    "₽/мес": {"student_reg": -0.25, "student_msk": -0.1, "teen": -0.1, "young_family": -0.05},
    "комиссия": {"self_employed": -0.15, "nonresident": -0.1},
    "без комиссии": {"self_employed": 0.25, "nonresident": 0.2},
    "прогноз": {"self_employed": 0.15},
    "налог": {"self_employed": 0.15},
    "годовых": {"young_family": -0.1, "student_reg": -0.1},
    "напомним": {"young_family": 0.1, "student_reg": 0.05},
    "только сегодня": {"senior": -0.2, "young_family": -0.1, "student_msk": -0.05},
    "примерно": {"young_family": 0.15, "senior": 0.1, "self_employed": 0.1},
    "личные": {"young_family": 0.15, "teen": 0.1},
    "видит все траты": {"young_family": -0.1, "teen": -0.15},
}
BASE = {
    "student_msk": 0.35,
    "student_reg": 0.3,
    "teen": 0.3,
    "young_family": 0.3,
    "senior": 0.2,
    "self_employed": 0.3,
    "nonresident": 0.25,
}


def _ask_mock(rng: random.Random, twin: Twin, scenario: dict, variant_text: str):
    t = variant_text.lower()
    p = BASE[twin.segment] + sum(v.get(twin.segment, 0) for k, v in KEYWORDS.items() if k in t)
    p = min(0.92, max(0.03, p + rng.gauss(0, 0.08)))
    decision = rng.random() < p
    objections, weights = scenario["objections"], []
    for reason in objections:
        weight = 1.0
        if "плата" in reason or "комисс" in reason:
            if ("бесплат" in t and "₽/мес" not in t and "комиссия" not in t) or "без комиссии" in t:
                weight = 0.0
            elif "₽/мес" in t or "комиссия" in t:
                weight = 3.0
        if "канал" in reason and twin.segment == "senior":
            weight = 4.0 if "только в приложении" in t else 0.5
        if "мошенник" in reason and "мошенник" in t:
            weight = 0.3
        weights.append(weight)
    obj = None if decision else rng.choices(objections, weights=weights)[0]
    if decision:
        motives = {
            "student_msk": "Если это подходит для моих ежедневных покупок, готов попробовать.",
            "student_reg": "Для меня важно не тратить лишнее на обслуживание карты.",
            "teen": "Обсужу с родителями, мне интересно попробовать.",
            "young_family": "Если семье будет проще планировать расходы, подключу.",
            "senior": "Сначала уточню условия у сотрудника банка.",
            "self_employed": "Попробую, если это упростит расчёты с клиентами.",
            "nonresident": "Мне важно понимать условия переводов и комиссии.",
        }
        quote = motives[twin.segment]
    else:
        quote = f"Пока не подключу: меня останавливает {obj}."
    return {"decision": decision, "probability": round(p, 2), "objection": obj, "quote": quote}


def simulate(
    twins: list[Twin],
    scenario: dict,
    mock: bool = False,
    seed: int = 0,
    concurrency: int = 16,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Оценивает варианты одной популяцией. Сбои отделены от клиентских отказов."""
    if not twins or not scenario.get("variants") or concurrency < 1:
        raise ValueError("Нужны непустая популяция, варианты и положительная параллельность.")
    if any(not isinstance(t, str) or not t.strip() for t in scenario["variants"].values()):
        raise ValueError("Текст каждого варианта должен быть заполнен.")
    results, done = {}, 0
    total = len(twins) * len(scenario["variants"])

    def advance():
        nonlocal done
        done += 1
        if progress and (done == total or done % max(1, total // 100) == 0):
            progress(done, total)

    if mock:
        for vid, text in scenario["variants"].items():
            rng = random.Random(f"{seed}-{vid}")
            results[vid] = []
            for tw in twins:
                results[vid].append((tw, _ask_mock(rng, tw, scenario, text)))
                advance()
    else:

        async def run():
            sem = asyncio.Semaphore(concurrency)
            async with _client() as client:
                model = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")

                async def ask(tw, text):
                    answer = await _ask_llm(client, model, tw, scenario, text, sem)
                    advance()
                    return tw, answer

                first_vid, first_text = next(iter(scenario["variants"].items()))
                first = await ask(twins[0], first_text)
                if first[1].get("error_kind") in {
                    "APIConnectionError",
                    "APITimeoutError",
                    "AuthenticationError",
                    "PermissionDeniedError",
                    "NotFoundError",
                }:
                    raise ValueError("LLM недоступна: проверьте адрес API, ключ доступа и название модели.")
                for vid, text in scenario["variants"].items():
                    rest = twins[1:] if vid == first_vid else twins
                    rows = await asyncio.gather(*(ask(tw, text) for tw in rest))
                    results[vid] = [first, *rows] if vid == first_vid else rows

        asyncio.run(run())
    return {vid: aggregate(rows) for vid, rows in results.items()}


def _interval(yes, n):
    """Wilson 95%: разброс ответов внутри симуляции, не точность прогноза людей."""
    if not n:
        return [0.0, 1.0]
    z, p = 1.96, yes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def aggregate(rows) -> dict:
    rows = list(rows)
    by_seg = defaultdict(lambda: [0, 0])
    objections, quote_groups, failures = Counter(), defaultdict(list), []
    for tw, out in rows:
        if out.get("error") or type(out.get("decision")) is not bool:
            failures.append(out.get("error", "Некорректный ответ модели."))
            continue
        by_seg[tw.segment][0] += 1
        by_seg[tw.segment][1] += int(out["decision"])
        if not out["decision"] and out.get("objection"):
            objections[out["objection"]] += 1
        if out.get("quote"):
            quote_groups[(tw.segment, out["decision"])].append(
                {
                    "who": f"{tw.name}, {tw.age}, {tw.region}",
                    "segment_id": tw.segment,
                    "segment": SEGMENTS[tw.segment]["name"],
                    "decision": out["decision"],
                    "quote": out["quote"],
                }
            )
    # Чередуем сегменты и решения вместо выбора первых шести ответов.
    quotes = []
    while quote_groups and len(quotes) < 12:
        for key in list(quote_groups):
            quotes.append(quote_groups[key].pop(0))
            if not quote_groups[key]:
                del quote_groups[key]
            if len(quotes) == 12:
                break
    n = sum(v[0] for v in by_seg.values())
    yes = sum(v[1] for v in by_seg.values())
    return {
        "n": n,
        "requested_n": len(rows),
        "failed_n": len(failures),
        "yes": yes,
        "conversion": yes / n if n else 0,
        "confidence_interval": _interval(yes, n),
        "segments": {
            s: {
                "name": SEGMENTS[s]["name"],
                "n": v[0],
                "yes": v[1],
                "conversion": v[1] / v[0],
                "confidence_interval": _interval(v[1], v[0]),
            }
            for s, v in by_seg.items()
        },
        "objections": dict(objections.most_common()),
        "quotes": quotes,
        "failure_examples": list(dict.fromkeys(failures))[:3],
    }
