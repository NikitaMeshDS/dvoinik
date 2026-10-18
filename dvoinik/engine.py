"""Движок симуляции: каждый двойник получает вариант продукта и решает, объясняя причину.

LLM: любая OpenAI-совместимая модель (on-prem vLLM/Ollama, российские модели через шлюз).
Режим mock: эвристическая модель без LLM — для демо и тестов без GPU.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import random
from collections import Counter, defaultdict
from collections.abc import Callable

from . import llm_cache, llm_json, ssr
from .population import SEGMENTS, Twin

SYSTEM = (
    "Ты — конкретный клиент банка, описанный ниже. Отвечай от первого лица, как этот человек, "
    "учитывая его возраст, доход, привычки и отношение к банкам. Не будь чрезмерно позитивным: "
    "реальные клиенты часто отказываются, если не видят явной пользы.\n"
    'Ответь строго JSON: {"decision": true|false, "probability": 0..1, '
    '"objection": главная причина сомнений — одна категория из списка, даже если согласен, '
    '"quote": одна фраза от первого лица}'
)


SSR_SYSTEM = (
    "Ты — конкретный клиент банка, описанный ниже. Отвечай от первого лица, как этот человек, "
    "учитывая его возраст, доход, привычки и отношение к банкам. Не будь чрезмерно позитивным: "
    "реальные клиенты часто отказываются, если не видят явной пользы.\n"
    "Скажи одной-двумя фразами, воспользуешься ли ты предложением и почему, без чисел и оценок.\n"
    'Ответь строго JSON: {"reaction": "одна-две фразы от первого лица", '
    '"objection": главная причина сомнений — одна категория из списка}'
)


BASELINE_SYSTEM = (
    "Ты — продуктовый аналитик банка. Оцени, какая доля описанной аудитории ответит «да» "
    "на вопрос по каждому предложению. Не моделируй отдельных людей: дай одну общую оценку.\n"
    'Ответь строго JSON: {"rates": {"A": 0..1, "B": 0..1, ...}}'
)


def _client():
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("LLM_API_KEY", "ollama"),
        timeout=45,
        max_retries=2,
    )


# Причина отказа не из списка категорий: названа своими словами или не названа.
OTHER_OBJECTION = "другое"


def _clean(text: str) -> str:
    return " ".join(text.strip().strip("«»\"'.!").lower().replace("ё", "е").split())


def _match_objection(value, objections: list[str]) -> str | None:
    """Сопоставляет ответ модели с категорией: регистр, кавычки, «ё» и однозначное вхождение.

    Небольшие модели часто возвращают «Не доверяю.» вместо «не доверяю». Неоднозначные
    и посторонние ответы не угадываются: такой ответ остаётся ошибкой формата.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    if value in objections:
        return value
    cleaned = _clean(value)
    exact = [o for o in objections if _clean(o) == cleaned]
    if len(exact) == 1:
        return exact[0]
    contained = [
        o for o in objections if _clean(o) in cleaned or (len(cleaned) >= 5 and cleaned in _clean(o))
    ]
    return contained[0] if len(contained) == 1 else None


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
    objection = _match_objection(out.get("objection"), scenario["objections"]) or OTHER_OBJECTION
    return {
        "stated": out["decision"],
        "probability": probability,
        "objection": objection,
        "quote": out["quote"].strip()[:1000],
    }


def _decide(parsed: dict, twin: Twin, variant_text: str) -> dict:
    """Решение по названной вероятности, а не по ответу «да/нет».

    Ответ «да/нет» сводит сегмент к одному мнению: на открытых данных средняя ошибка
    двойников по ответу 32 п.п., по вероятности 21,5 п.п. (proof.py, qwen3.5-9b).
    Жребий детерминирован: тот же профиль и текст дают то же решение.
    """
    decision = ssr.draw(parsed["probability"], twin.id, twin.segment, variant_text)
    return {**parsed, "decision": decision, "objection": None if decision else parsed["objection"]}


def _parse_ssr(content, scenario):
    out = json.loads(content)
    if not isinstance(out, dict) or not isinstance(out.get("reaction"), str) or not out["reaction"].strip():
        raise ValueError("reaction должна содержать ответ клиента")
    objection = _match_objection(out.get("objection"), scenario["objections"])
    if objection is None:
        objection = OTHER_OBJECTION
    return {"reaction": out["reaction"].strip()[:1000], "objection": objection}


async def _ask_llm(
    client,
    model,
    twin: Twin,
    scenario: dict,
    variant_text: str,
    sem,
    guard: Callable[[], None] | None = None,
    references: ssr.References | None = None,
):
    user = (
        f"Ты: {twin.profile()}\n\nБанк предлагает: {variant_text}\n\n"
        f"Контекст исследования: {scenario.get('description', '')}\n"
        f"Вопрос: {scenario['question']}\n"
        f"Категории отказа: {', '.join(scenario['objections'])}"
    )
    system = SSR_SYSTEM if references is not None else SYSTEM
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    # «|draw»: решение по вероятности; старые записи кэша с решением модели не подходят.
    identity = f"{model}|draw" if references is None else f"{model}|ssr:{ssr.embed_model()}"
    cache_key = llm_cache.key(identity, messages, 0.8)
    async with sem:
        # Check after waiting for capacity and outside the provider-error handler.
        # Access revocation must abort the run, never become a simulated refusal.
        if guard:
            guard()
        cached = llm_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            content = await llm_json.chat_json(client, model, messages, 0.8)
            if references is None:
                answer = _decide(_parse_response(content, scenario), twin, variant_text)
            else:
                answer = await _rate_ssr(client, content, scenario, twin, variant_text, references)
            llm_cache.put(cache_key, answer)
            return answer
        except (ValueError, TypeError, IndexError, AttributeError) as exc:
            return {"error": f"Модель вернула ответ, не соответствующий JSON-схеме: {_schema_reason(exc)}."}
        except Exception as exc:
            # Не включаем тело HTTP-ответа, URL или ключ в экспортируемые отчёты.
            return {
                "error": f"Запрос к модели не выполнен ({type(exc).__name__}).",
                "error_kind": type(exc).__name__,
            }


def _schema_reason(exc: Exception) -> str:
    """Причина отказа без текста ответа модели: какое поле не прошло проверку."""
    if isinstance(exc, json.JSONDecodeError):
        return "ответ не является JSON"
    if isinstance(exc, ValueError) and str(exc):
        return str(exc).rstrip(".")[:120]
    return type(exc).__name__


async def _rate_ssr(client, content, scenario, twin, variant_text, references):
    """Ответ фразой → распределение по шкале 1–5 → доля «скорее да» и «точно да» → решение."""
    parsed = _parse_ssr(content, scenario)
    model = ssr.embed_model()
    refs = await references.get(client, model)
    (vector,) = await ssr.embed(client, model, [parsed["reaction"]])
    distribution = ssr.pmf(vector, refs)
    probability = round(ssr.top_two(distribution), 4)
    decision = ssr.draw(probability, twin.id, twin.segment, variant_text)
    return {
        "decision": decision,
        "probability": probability,
        "objection": None if decision else parsed["objection"],
        "quote": parsed["reaction"],
        "likert": distribution,
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


MOTIVES = {
    "student_msk": [
        "Если это подходит для моих ежедневных покупок, готов попробовать.",
        "Звучит выгодно для того, как я трачу. Оформлю и посмотрю месяц.",
        "Сравню с тем, что у меня уже есть, но предложение интересное.",
    ],
    "student_reg": [
        "Для меня важно не тратить лишнее на обслуживание карты.",
        "Если правда без скрытых платежей, переведу сюда стипендию.",
        "Подходит, пока условия понятные и ничего не списывают.",
    ],
    "teen": [
        "Обсужу с родителями, мне интересно попробовать.",
        "Если друзья тоже будут пользоваться, попрошу маму оформить.",
        "Хочу попробовать, но решать будут родители.",
    ],
    "young_family": [
        "Если семье будет проще планировать расходы, подключу.",
        "Обсудим дома: если сэкономит время на бюджете, оформим.",
        "Для семьи это может быть удобно, попробуем.",
    ],
    "senior": [
        "Сначала уточню условия у сотрудника банка.",
        "Если помогут оформить и всё объяснят, открою.",
        "Посоветуюсь с дочерью, но в целом подходит.",
    ],
    "self_employed": [
        "Попробую, если это упростит расчёты с клиентами.",
        "Если комиссии честные, перейду с текущего счёта.",
        "Это может сэкономить мне время на отчётности.",
    ],
    "nonresident": [
        "Мне важно понимать условия переводов и комиссии.",
        "Если всё объяснено понятно, буду пользоваться.",
        "Подойдёт для переводов домой, если комиссия честная.",
    ],
}
REFUSALS = [
    "Пока не подключу. Причина: {reason}.",
    "Не вижу смысла менять что-то сейчас: {reason}.",
    "Скорее нет. Главное для меня — {reason}.",
    "Отложу решение: {reason}.",
]


def _pick(options: list[str], *keys) -> str:
    """Детерминированный выбор формулировки без расхода генератора решений."""
    digest = hashlib.sha256("|".join(map(str, keys)).encode()).digest()
    return options[int.from_bytes(digest[:4], "big") % len(options)]


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
        if "кэшбэк" in reason and "кэшбэк" not in t:
            weight = 0.0
        weights.append(weight)
    obj = None if decision else rng.choices(objections, weights=weights if sum(weights) else None)[0]
    if decision:
        quote = _pick(MOTIVES[twin.segment], twin.id, t)
    else:
        quote = _pick(REFUSALS, twin.id, t).format(reason=obj)
    return {"decision": decision, "probability": round(p, 2), "objection": obj, "quote": quote}


def simulate(
    twins: list[Twin],
    scenario: dict,
    mock: bool = False,
    seed: int = 0,
    concurrency: int = 16,
    progress: Callable[[int, int], None] | None = None,
    guard: Callable[[], None] | None = None,
) -> dict:
    """Оценивает варианты одной популяцией. Сбои отделены от клиентских отказов."""
    if not twins or not scenario.get("variants") or concurrency < 1:
        raise ValueError("Нужны непустая популяция, варианты и положительная параллельность.")
    if any(not isinstance(t, str) or not t.strip() for t in scenario["variants"].values()):
        raise ValueError("Текст каждого варианта должен быть заполнен.")
    results, done = {}, 0
    total = len(twins) * len(scenario["variants"])
    check_access = guard or (lambda: None)
    check_access()

    def advance():
        nonlocal done
        check_access()
        done += 1
        if progress and (done == total or done % max(1, total // 100) == 0):
            progress(done, total)

    if mock:
        for vid, text in scenario["variants"].items():
            rng = random.Random(f"{seed}-{vid}")
            results[vid] = []
            for tw in twins:
                check_access()
                results[vid].append((tw, _ask_mock(rng, tw, scenario, text)))
                advance()
    else:

        async def run():
            sem = asyncio.Semaphore(concurrency)
            references = ssr.References() if ssr.mode() == "ssr" else None
            async with _client() as client:
                model = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")

                async def ask(tw, text):
                    answer = await _ask_llm(
                        client, model, tw, scenario, text, sem, guard=check_access, references=references
                    )
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
                    check_access()
                    rest = twins[1:] if vid == first_vid else twins
                    rows = await asyncio.gather(*(ask(tw, text) for tw in rest))
                    results[vid] = [first, *rows] if vid == first_vid else rows

        asyncio.run(run())
    return {vid: aggregate(rows) for vid, rows in results.items()}


def _audience_text(scenario: dict) -> str:
    return "; ".join(
        f"{SEGMENTS[sid]['name']} — {share * 100:.0f}%" for sid, share in scenario["population"].items()
    )


def _parse_baseline(content, variants):
    out = json.loads(content)
    rates = out.get("rates") if isinstance(out, dict) else None
    if not isinstance(rates, dict) or set(rates) != set(variants):
        raise ValueError("rates должны содержать все варианты")
    clean = {}
    for vid in variants:
        value = rates[vid]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("доля должна быть числом")
        if not 0 <= value <= 1:
            raise ValueError("доля должна быть от 0 до 1")
        clean[vid] = float(value)
    return clean


def _demo_baseline(scenario: dict) -> dict:
    """Правило без профилей для демо: те же ключевые слова, усреднённые по всем сегментам."""
    rates = {}
    for vid, text in scenario["variants"].items():
        t = text.lower()
        effect = sum(sum(v.values()) / len(BASE) for k, v in KEYWORDS.items() if k in t)
        rates[vid] = round(min(0.92, max(0.03, sum(BASE.values()) / len(BASE) + effect)), 4)
    return {"method": "demo_rule", "rates": rates}


def baseline_estimate(scenario: dict, mock: bool = False) -> dict:
    """Простой подход для сравнения: одна оценка по описанию аудитории, без персонажей.

    Ошибка модели не прерывает исследование: она сохраняется вместо долей.
    """
    if mock:
        return _demo_baseline(scenario)
    variants = scenario["variants"]
    user = (
        f"Аудитория: {_audience_text(scenario)}.\n"
        f"Контекст: {scenario.get('description', '')}\n"
        f"Вопрос: {scenario['question']}\n"
        + "\n".join(f"Предложение {vid}: {text}" for vid, text in variants.items())
    )

    async def ask():
        async with _client() as client:
            return await llm_json.chat_json(
                client,
                os.getenv("LLM_MODEL", "qwen2.5:7b-instruct"),
                [{"role": "system", "content": BASELINE_SYSTEM}, {"role": "user", "content": user}],
                0,
            )

    try:
        return {"method": "single_prompt", "rates": _parse_baseline(asyncio.run(ask()), variants)}
    except (ValueError, TypeError, IndexError, AttributeError):
        return {"method": "single_prompt", "error": "Модель вернула ответ, не соответствующий JSON-схеме."}
    except Exception as exc:
        return {"method": "single_prompt", "error": f"Запрос к модели не выполнен ({type(exc).__name__})."}


PARAPHRASE_SYSTEM = (
    "Перефразируй каждое банковское предложение другими словами. Сохрани все условия, числа, "
    "ограничения и смысл; не добавляй и не убирай выгоды. Длина — примерно та же.\n"
    'Ответь строго JSON: {"variants": {"A": "...", "B": "...", ...}}'
)


def paraphrase_variants(scenario: dict) -> dict[str, str]:
    """Перефразировки предложений той же моделью — для проверки чувствительности к формулировке.

    Проверяется только формат; сохранение условий нужно просмотреть глазами.
    """
    variants = scenario["variants"]
    user = "\n".join(f"{vid}: {text}" for vid, text in variants.items())

    async def ask():
        async with _client() as client:
            return await llm_json.chat_json(
                client,
                os.getenv("LLM_MODEL", "qwen2.5:7b-instruct"),
                [
                    {"role": "system", "content": PARAPHRASE_SYSTEM},
                    {"role": "user", "content": user},
                ],
                0.7,
            )

    out = json.loads(asyncio.run(ask()))
    texts = out.get("variants") if isinstance(out, dict) else None
    if not isinstance(texts, dict) or set(texts) != set(variants):
        raise ValueError("Модель не вернула перефразировки всех предложений.")
    if any(not isinstance(t, str) or not t.strip() or len(t) > 3000 for t in texts.values()):
        raise ValueError("Перефразировка должна быть непустым текстом до 3000 символов.")
    return {vid: texts[vid].strip() for vid in variants}


REWRITE_SYSTEM = (
    "Ты — продуктовый маркетолог банка. Перепиши предложение так, чтобы снять названные "
    "причины отказа у указанных сегментов. Сохрани продукт и его ключевые условия; не добавляй "
    "выгод и цифр, которых нет в исходном тексте или в описании изменения. Пиши коротко, "
    "как текст для клиента, не длиннее полутора исходных.\n"
    'Ответь строго JSON: {"proposal": "..."}'
)


def rewrite_offer(scenario: dict, hypothesis: dict) -> str:
    """Текст гипотезы, переписанный моделью вместо черновика по правилу."""
    user = (
        f"Контекст: {scenario.get('description', '')}\n"
        f"Вопрос клиенту: {scenario['question']}\n"
        f"Исходное предложение: {hypothesis['base_text']}\n"
        f"Сегменты: {', '.join(hypothesis['segment_names'])}\n"
        f"Причины отказа: {', '.join(hypothesis['objections']) or 'нет'}\n"
        f"Что изменить: {hypothesis['change']}\n"
        f"Черновик по правилу: {hypothesis['proposal']}"
    )

    async def ask():
        async with _client() as client:
            return await llm_json.chat_json(
                client,
                os.getenv("LLM_MODEL", "qwen2.5:7b-instruct"),
                [{"role": "system", "content": REWRITE_SYSTEM}, {"role": "user", "content": user}],
                0.4,
            )

    out = json.loads(asyncio.run(ask()))
    text = out.get("proposal") if isinstance(out, dict) else None
    if not isinstance(text, str) or not text.strip() or len(text) > 3000:
        raise ValueError("Модель не вернула текст предложения до 3000 символов.")
    if text.strip() == hypothesis["base_text"].strip():
        raise ValueError("Модель вернула исходный текст без изменений.")
    return text.strip()


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
    objections, quote_groups, failures, probabilities = Counter(), defaultdict(list), [], []
    seg_objections = defaultdict(Counter)
    likerts = []
    for tw, out in rows:
        if out.get("error") or type(out.get("decision")) is not bool:
            failures.append(out.get("error", "Некорректный ответ модели."))
            continue
        probability = out.get("probability")
        if isinstance(probability, (int, float)) and not isinstance(probability, bool):
            if math.isfinite(probability) and 0 <= probability <= 1:
                probabilities.append(float(probability))
        by_seg[tw.segment][0] += 1
        by_seg[tw.segment][1] += int(out["decision"])
        if isinstance(out.get("likert"), list) and len(out["likert"]) == ssr.POINTS:
            likerts.append(out["likert"])
        if not out["decision"] and out.get("objection"):
            objections[out["objection"]] += 1
            seg_objections[tw.segment][out["objection"]] += 1
        if out.get("quote"):
            # Цитату подписываем тем, что сказал двойник, а не жребием по вероятности.
            said = out.get("stated", out["decision"])
            quote_groups[(tw.segment, said)].append(
                {
                    "who": f"{tw.name}, {tw.age}, {tw.region}",
                    "segment_id": tw.segment,
                    "segment": SEGMENTS[tw.segment]["name"],
                    "decision": said,
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
    result = {
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
                "objections": dict(seg_objections[s].most_common()),
            }
            for s, v in by_seg.items()
        },
        "objections": dict(objections.most_common()),
        "quotes": quotes,
        "failure_examples": list(dict.fromkeys(failures))[:3],
    }
    if probabilities and len(probabilities) == n:
        result["probability"] = _probability_summary(probabilities)
    if n and len(likerts) == n:
        result["likert"] = [round(sum(d[i] for d in likerts) / n, 4) for i in range(ssr.POINTS)]
    return result


def _probability_summary(values: list[float]) -> dict:
    """Заявленная вероятность: средняя и разброс. Низкий разброс — признак однородных персонажей."""
    mean = sum(values) / len(values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    return {"mean": round(mean, 4), "sd": round(sd, 4), "n": len(values)}
