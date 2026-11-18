"""Агрегация ответов симуляции и описательная статистика для отчётов."""

from __future__ import annotations

import math
from collections import Counter, defaultdict, deque

from .population import SEGMENTS
from .ssr import POINTS

# Общая категория для ответов вне заданного списка причин отказа.
OTHER_OBJECTION = "другое"


def wilson_interval(yes: int, n: int) -> list[float]:
    """Wilson 95%: разброс ответов внутри симуляции, не точность прогноза людей."""
    if not n:
        return [0.0, 1.0]
    z, p = 1.96, yes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def aggregate(rows) -> dict:
    requested_n = 0
    by_seg = defaultdict(lambda: [0, 0])
    objections, quote_groups, failures, probabilities = Counter(), defaultdict(deque), [], []
    seg_objections = defaultdict(Counter)
    likerts = []
    raw_probabilities = []
    inconsistent = 0
    by_digital = defaultdict(list)
    for tw, out in rows:
        requested_n += 1
        if out.get("error") or type(out.get("decision")) is not bool:
            failures.append(out.get("error", "Некорректный ответ модели."))
            continue
        inconsistent += bool(out.get("inconsistent"))
        raw_probability = out.get("raw_probability")
        if isinstance(raw_probability, (int, float)) and not isinstance(raw_probability, bool):
            if math.isfinite(raw_probability) and 0 <= raw_probability <= 1:
                raw_probabilities.append(float(raw_probability))
        probability = out.get("probability")
        if isinstance(probability, (int, float)) and not isinstance(probability, bool):
            if math.isfinite(probability) and 0 <= probability <= 1:
                probabilities.append(float(probability))
        by_seg[tw.segment][0] += 1
        by_seg[tw.segment][1] += int(out["decision"])
        if isinstance(out.get("probability"), (int, float)):
            for label, value in getattr(tw, "traits", {}).items():
                by_digital[f"{label}: {value}"].append(float(out["probability"]))
        if isinstance(out.get("likert"), list) and len(out["likert"]) == POINTS:
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
            quotes.append(quote_groups[key].popleft())
            if not quote_groups[key]:
                del quote_groups[key]
            if len(quotes) == 12:
                break
    n = sum(v[0] for v in by_seg.values())
    yes = sum(v[1] for v in by_seg.values())
    result = {
        "n": n,
        "requested_n": requested_n,
        "failed_n": len(failures),
        "yes": yes,
        "conversion": yes / n if n else 0,
        "confidence_interval": wilson_interval(yes, n),
        "segments": {
            s: {
                "name": SEGMENTS[s]["name"],
                "n": v[0],
                "yes": v[1],
                "conversion": v[1] / v[0],
                "confidence_interval": wilson_interval(v[1], v[0]),
                "objections": dict(seg_objections[s].most_common()),
            }
            for s, v in by_seg.items()
        },
        "objections": dict(objections.most_common()),
        "quotes": quotes,
        "failure_examples": list(dict.fromkeys(failures))[:3],
    }
    if inconsistent:
        result["inconsistent_n"] = inconsistent
        # Only report the original aggregate when every valid answer supplied it.
        # SSR, demo and historical rows must not acquire inferred originals.
        if len(raw_probabilities) == n:
            result["raw_probability"] = _probability_summary(raw_probabilities)
    if by_digital:
        # Проверка, что двойники учитывают атрибуты профиля: средняя вероятность «да» по их значениям.
        result["by_trait"] = {
            level: {"n": len(values), "mean": round(sum(values) / len(values), 4)}
            for level, values in by_digital.items()
        }
    if probabilities and len(probabilities) == n:
        result["probability"] = _probability_summary(probabilities)
    if n and len(likerts) == n:
        result["likert"] = [round(sum(d[i] for d in likerts) / n, 4) for i in range(POINTS)]
    return result


def _probability_summary(values: list[float]) -> dict:
    """Заявленная вероятность: средняя и разброс. Низкий разброс — признак однородных персонажей."""
    mean = sum(values) / len(values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    return {"mean": round(mean, 4), "sd": round(sd, 4), "n": len(values)}
