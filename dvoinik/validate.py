"""Валидация прогноза против опроса живых респондентов.

Формат опроса (CSV): segment,variant,decision  (decision = 1/0)
Метрики: абсолютная ошибка конверсии по варианту и сегменту, совпадение ранжирования вариантов
(Spearman), совпадение победителя.
"""
from __future__ import annotations

import csv
from collections import defaultdict


def load_survey(path: str) -> dict:
    agg = defaultdict(lambda: [0, 0])
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["variant"], row["segment"])
            agg[key][0] += 1
            agg[key][1] += int(row["decision"])
    return {k: v[1] / v[0] for k, v in agg.items()}


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0] * len(xs)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def compare(report: dict, survey: dict) -> dict:
    errors = []
    for (vid, seg), real in survey.items():
        pred = report.get(vid, {}).get("segments", {}).get(seg, {}).get("conversion")
        if pred is not None:
            errors.append(abs(pred - real))
    variants = sorted({v for v, _ in survey})
    real_by_v = [sum(c for (v, _), c in survey.items() if v == vid) /
                 max(1, sum(1 for (v, _) in survey if v == vid)) for vid in variants]
    pred_by_v = [report[v]["conversion"] for v in variants]
    rr, rp = _rank(real_by_v), _rank(pred_by_v)
    n = len(variants)
    spearman = 1 - 6 * sum((a - b) ** 2 for a, b in zip(rr, rp)) / (n * (n * n - 1)) if n > 1 else 1.0
    return {
        "mae_conversion": sum(errors) / len(errors) if errors else None,
        "spearman_variants": spearman,
        "winner_match": variants[rr.index(n - 1)] == variants[rp.index(n - 1)],
    }
