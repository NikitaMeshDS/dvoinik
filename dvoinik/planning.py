"""Подготовка живой проверки и оценка запуска по сохранённому снимку.

Все функции детерминированы и не меняют снимок. Они описывают разброс внутри
симуляции и требования к будущему опросу, а не точность прогноза поведения людей.
"""

from __future__ import annotations

import math
import os
import random
from statistics import NormalDist

from .population import SEGMENTS

Z = NormalDist()
STABILITY_DRAWS = 4000
# Порог «заметной» разницы для расчёта выборки: меньшую опросом обычно не различить.
MIN_DIFFERENCE = 0.02
# Разброс заявленной вероятности ниже этого порога — признак одинаковых ответов для разных профилей.
HOMOGENEOUS_SD = 0.05
EXPLORATORY_N = 30


def _valid(report: dict) -> dict:
    return {v: r for v, r in report.items() if r.get("n", 0) > 0}


def leader_stability(report: dict, draws: int = STABILITY_DRAWS, seed: int = 0) -> dict | None:
    """Доля повторных выборок, в которых лидер симуляции остаётся лидером.

    Для каждого варианта берётся бета-распределение Beta(yes + 1, no + 1) по сохранённым
    количествам. Это разброс ответов этой же симуляции: устойчивость к другой популяции
    или формулировке и совпадение с людьми здесь не проверяются. Профили для вариантов
    одинаковые, а расчёт считает варианты независимыми, поэтому оценка консервативная.
    """
    valid = _valid(report)
    if len(valid) < 2:
        return None
    ordered = sorted(valid, key=lambda v: valid[v]["yes"] / valid[v]["n"], reverse=True)
    leader = ordered[0]
    rng = random.Random(f"stability-{seed}")
    wins = 0
    for _ in range(draws):
        sampled = {v: rng.betavariate(r["yes"] + 1, r["n"] - r["yes"] + 1) for v, r in valid.items()}
        if max(sampled, key=sampled.get) == leader:
            wins += 1
    share = wins / draws
    if share >= 0.95:
        level, label = "stable", "Лидер устойчив в этой выборке"
    elif share >= 0.8:
        level, label = "moderate", "Лидер умеренно устойчив в этой выборке"
    else:
        level, label = "unstable", "Лидер неустойчив даже в этой выборке"
    return {
        "leader": leader,
        "runner_up": ordered[1],
        "share": share,
        "level": level,
        "label": label,
        "draws": draws,
        "detail": "Доля повторных выборок ответов этой симуляции, где лидер сохраняется. "
        "Не проверяет другие формулировки, популяцию или поведение людей.",
    }


def sample_size(p1: float, p2: float, alpha: float = 0.05, power: float = 0.8) -> int | None:
    """Ответов на каждое предложение, чтобы различить две доли двусторонним тестом."""
    for value in (p1, p2, alpha, power):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Доли, уровень значимости и мощность должны быть от 0 до 1.")
    if not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError("Уровень значимости и мощность должны быть строго между 0 и 1.")
    delta = abs(p1 - p2)
    if delta < MIN_DIFFERENCE:
        return None
    za, zb = Z.inv_cdf(1 - alpha / 2), Z.inv_cdf(power)
    pooled = (p1 + p2) / 2
    root = za * math.sqrt(2 * pooled * (1 - pooled)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    return math.ceil(root * root / (delta * delta))


def detectable_difference(rate: float, n: int, alpha: float = 0.05, power: float = 0.8) -> float:
    """Минимальная разница долей, которую опрос n человек на предложение заметит с заданной мощностью."""
    if n < 1:
        raise ValueError("Нужен хотя бы один ответ на предложение.")
    rate = min(max(rate, 0.01), 0.99)
    za, zb = Z.inv_cdf(1 - alpha / 2), Z.inv_cdf(power)
    return min(1.0, (za + zb) * math.sqrt(2 * rate * (1 - rate) / n))


INTERVIEW_TEMPLATES = [
    "Вспомните последний раз, когда вы выбирали похожий банковский продукт. Что повлияло на решение?",
    "Причина «{reason}»: вспомните последний случай, когда она повлияла на ваше решение о банковском "
    "продукте. Что произошло и чем закончилось?",
    "Что должно измениться, чтобы причина «{reason}» перестала вас останавливать? Как бы вы это проверили?",
]


def interview_questions(report: dict, limit: int = 5) -> list[dict]:
    """Вопросы в стиле «прошлый опыт, а не мнение» по частым синтетическим возражениям."""
    totals: dict[str, int] = {}
    for result in report.values():
        for reason, count in result.get("objections", {}).items():
            totals[reason] = totals.get(reason, 0) + count
    reasons = [r for r, _ in sorted(totals.items(), key=lambda item: (-item[1], item[0]))][:2]
    questions = [{"text": INTERVIEW_TEMPLATES[0], "source": "общий вопрос о выборе"}]
    for reason in reasons:
        for template in INTERVIEW_TEMPLATES[1:]:
            questions.append({"text": template.format(reason=reason), "source": f"возражение «{reason}»"})
    return questions[:limit]


def live_check_plan(record: dict) -> dict:
    """Какие сравнения переносить в живой опрос и сколько ответов для них нужно."""
    report = record["report"]
    valid = _valid(report)
    rates = {v: r["yes"] / r["n"] for v, r in valid.items()}
    ordered = sorted(rates, key=rates.get, reverse=True)
    comparisons = []
    if len(ordered) >= 2:
        leader = ordered[0]
        for other in ordered[1:3]:
            needed = sample_size(rates[leader], rates[other])
            comparisons.append(
                {
                    "pair": [leader, other],
                    "rates": [rates[leader], rates[other]],
                    "gap_pp": (rates[leader] - rates[other]) * 100,
                    "n_per_variant": needed,
                }
            )
    mean = sum(rates.values()) / len(rates) if rates else 0.5
    focus_segments = []
    if ordered:
        overall = ordered[0]
        for sid in record["scenario"]["population"]:
            seg_rates = {
                v: r["segments"][sid]["yes"] / r["segments"][sid]["n"]
                for v, r in valid.items()
                if r["segments"].get(sid, {}).get("n")
            }
            if not seg_rates:
                continue
            best = max(seg_rates, key=seg_rates.get)
            if best != overall and seg_rates[best] - seg_rates.get(overall, 0) >= MIN_DIFFERENCE:
                focus_segments.append(
                    {
                        "segment": sid,
                        "name": SEGMENTS[sid]["name"],
                        "leader": best,
                        "gap_pp": (seg_rates[best] - seg_rates.get(overall, 0)) * 100,
                    }
                )
    return {
        "comparisons": comparisons,
        "exploratory_n": EXPLORATORY_N,
        "exploratory_detectable_pp": detectable_difference(mean, EXPLORATORY_N) * 100,
        "focus_segments": focus_segments,
        "questions": interview_questions(report),
        "assumptions": "Двусторонний тест разницы двух долей, α = 0,05, мощность 80%. "
        "Доли взяты из симуляции и служат только ориентиром: реальные доли могут отличаться.",
    }


# ---- оценка запуска на LLM ----
CHARS_PER_TOKEN = 3.0
OUTPUT_TOKENS = 90
PROFILE_CHARS = 260


def run_estimate(scenario: dict, n: int, concurrency: int = 16, baseline: bool = True) -> dict:
    """Порядок затрат LLM-запуска до старта. Длину профиля и задержку оцениваем грубо."""
    from .engine import BASELINE_SYSTEM, SYSTEM

    variants = scenario["variants"]
    shared = len(SYSTEM) + len(scenario.get("description", "")) + len(scenario["question"])
    shared += sum(len(o) + 2 for o in scenario["objections"]) + PROFILE_CHARS + 120
    requests = n * len(variants)
    input_chars = sum((shared + len(text)) * n for text in variants.values())
    if baseline:
        requests += 1
        input_chars += len(BASELINE_SYSTEM) + sum(len(t) + 20 for t in variants.values()) + 600
    input_tokens = math.ceil(input_chars / CHARS_PER_TOKEN)
    output_tokens = requests * OUTPUT_TOKENS
    latency = _env_float("DVOINIK_LLM_LATENCY_S", 3.0)
    minutes = math.ceil(requests / max(1, concurrency)) * latency / 60
    price = _env_float("DVOINIK_PRICE_PER_1K_TOKENS", None)
    return {
        "requests": requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "minutes": minutes,
        "latency_s": latency,
        "concurrency": concurrency,
        "cost": round((input_tokens + output_tokens) / 1000 * price, 2) if price is not None else None,
        "currency": os.getenv("DVOINIK_PRICE_CURRENCY", "₽") if price is not None else None,
        "detail": f"≈ по {CHARS_PER_TOKEN:g} символа на токен и {latency:g} с на запрос при параллельности "
        f"{concurrency}. Фактические значения зависят от модели и сервера."
        + (" Кэш включён: повторные тексты не запрашиваются, это верхняя оценка." if _cache_on() else "")
        + (
            " Режим SSR: плюс короткие запросы к модели эмбеддингов — по одному на ответ и один на эталоны."
            if _ssr_on()
            else ""
        ),
    }


def _ssr_on() -> bool:
    from .ssr import mode

    return mode() == "ssr"


def _env_float(name: str, default):
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = float(raw)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name}: нужно неотрицательное число.")
    return value


def baseline_agreement(record: dict) -> dict | None:
    """Согласие двойников и простого подхода до живой проверки. Совпадение не означает точность."""
    from .validate import _correlation, _rank

    baseline = record.get("baseline")
    if not isinstance(baseline, dict):
        return None
    if "rates" not in baseline:
        return {"method": baseline.get("method"), "error": baseline.get("error")}
    valid = _valid(record["report"])
    variants = [v for v in record["report"] if v in valid]
    twins = [valid[v]["yes"] / valid[v]["n"] for v in variants]
    base = [baseline["rates"][v] for v in variants]
    if not variants:
        return None
    twin_leaders = [v for v, x in zip(variants, twins) if math.isclose(x, max(twins))]
    base_leaders = [v for v, x in zip(variants, base) if math.isclose(x, max(base))]
    return {
        "method": baseline["method"],
        "rows": [{"variant": v, "twins": t, "baseline": b} for v, t, b in zip(variants, twins, base)],
        "same_leader": twin_leaders == base_leaders,
        "twin_leaders": twin_leaders,
        "baseline_leaders": base_leaders,
        "spearman": _correlation(_rank(twins), _rank(base)),
    }


def _cache_on() -> bool:
    from .llm_cache import enabled

    return enabled()
