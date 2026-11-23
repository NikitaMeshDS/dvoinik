"""Сравнение симуляции с CSV живого опроса на одинаковом составе сегментов."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from contextlib import nullcontext
from fractions import Fraction
from itertools import combinations
from pathlib import Path
from statistics import NormalDist
from typing import TextIO

from .report_stats import difference_interval_95_pp, wilson_interval

RANKING_LIMITS = {
    "missing_variants": "Для общего сравнения нужны оценки каждого предложения.",
    "different_mix": "Доли сегментов отличаются между предложениями. Сравнивайте результаты внутри сегментов.",
}


BASELINE_LIMITS = {
    "unknown_population": "В сохранённой оценке простого подхода не указан состав аудитории.",
    "different_population": "Состав опроса отличается от аудитории, для которой был рассчитан простой подход.",
}


class SurveyRates(dict):
    """Конверсии по ячейкам с сохранением количества живых респондентов."""

    def __init__(self, rates, counts):
        super().__init__(rates)
        self.counts = counts


def load_survey(source: str | Path | TextIO) -> SurveyRates:
    context = (
        open(source, encoding="utf-8-sig", newline="")
        if isinstance(source, (str, Path))
        else nullcontext(source)
    )
    agg = defaultdict(lambda: [0, 0])
    with context as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"segment", "variant", "decision"}.issubset(reader.fieldnames):
            raise ValueError("В CSV опроса нужны колонки segment, variant, decision.")
        for line, row in enumerate(reader, 2):
            variant = (row.get("variant") or "").strip()
            segment = (row.get("segment") or "").strip()
            decision = (row.get("decision") or "").strip()
            if not variant or not segment or decision not in {"0", "1"}:
                raise ValueError(f"Строка {line}: укажите segment, variant и decision (0 или 1).")
            key = (variant, segment)
            agg[key][0] += 1
            agg[key][1] += int(decision)
    if not agg:
        raise ValueError("CSV опроса пуст: добавьте ответы респондентов.")
    return SurveyRates({k: yes / n for k, (n, yes) in agg.items()}, {k: n for k, (n, _) in agg.items()})


def _rank(xs):
    """Средние ранги для совпадающих значений."""
    ranks = [0.0] * len(xs)
    for value in set(xs):
        positions = [i for i, x in enumerate(xs) if x == value]
        rank = sum(x < value for x in xs) + (len(positions) - 1) / 2
        for i in positions:
            ranks[i] = rank
    return ranks


def _correlation(xs, ys):
    if len(xs) < 2:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    vx, vy = sum((x - mx) ** 2 for x in xs), sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def _segment_contrasts(cells, *, intervals, paired_probabilities):
    by_segment = defaultdict(list)
    for cell in cells:
        by_segment[cell["segment"]].append(cell)
    model_pairs = {
        (tuple(pair["variants"]), segment): data
        for pair in paired_probabilities or ()
        for segment, data in pair.get("segments", {}).items()
    }
    results = []
    for segment, entries in sorted(by_segment.items()):
        for a, b in combinations(sorted(entries, key=lambda cell: cell["variant"]), 2):
            left, right = a["variant"], b["variant"]
            comparison = {"segment": segment, "pair": [left, right]}
            model = model_pairs.get(((left, right), segment))
            if not intervals and model is None:
                continue
            if intervals:
                a_n, b_n = a["survey_n"], b["survey_n"]
                low, high = difference_interval_95_pp(
                    round(a["actual"] * a_n), a_n, round(b["actual"] * b_n), b_n
                )
                comparison["interval_95_pp"] = [low, high]
                comparison["direction"] = left if low > 0 else right if high < 0 else "uncertain"
            if model is not None:
                observed = (a["actual"] - b["actual"]) * 100
                comparison["model_pair"] = {**model, "absolute_error_pp": abs(model["gap_pp"] - observed)}
            results.append(comparison)
    return results


def _mae_interval_95_pp(cells, survey_n):
    """Project simultaneous Wilson bounds onto weighted MAE with fixed predictions and weights."""
    z = NormalDist().inv_cdf(1 - 0.05 / (2 * len(cells)))
    lower_error = upper_error = 0.0
    for cell in cells:
        n = cell["survey_n"]
        low, high = wilson_interval(round(cell["actual"] * n), n, z=z)
        predicted = cell["predicted"]
        lower_error += n * max(0.0, low - predicted, predicted - high)
        upper_error += n * max(abs(predicted - low), abs(predicted - high))
    return [100 * (lower_error / survey_n), 100 * (upper_error / survey_n)]


def compare(
    report: dict,
    survey: dict,
    baseline: dict | None = None,
    *,
    baseline_population=None,
    assignment=None,
    paired_probabilities=None,
) -> dict:
    if not survey:
        raise ValueError("Добавьте ответы живого опроса для сравнения.")
    counts = getattr(survey, "counts", {})
    cells, totals = [], defaultdict(lambda: [0.0, 0.0, 0])
    for (vid, seg), real in survey.items():
        if vid not in report:
            raise ValueError(f"Вариант {vid} отсутствует в эксперименте.")
        data = report[vid].get("segments", {}).get(seg)
        if data is None or data.get("n", 1) == 0:
            raise ValueError(f"Сегмент {seg} варианта {vid} отсутствует в результатах.")
        if not isinstance(real, (int, float)) or not math.isfinite(real) or not 0 <= real <= 1:
            raise ValueError("Конверсия опроса должна быть от 0 до 1.")
        weight, pred = counts.get((vid, seg), 1), data["conversion"]
        cells.append(
            {
                "variant": vid,
                "segment": seg,
                "survey_n": weight,
                "actual": real,
                "predicted": pred,
                "error": abs(pred - real),
            }
        )
        totals[vid][0] += real * weight
        totals[vid][1] += pred * weight
        totals[vid][2] += weight
    variants = sorted(totals)
    mixes = defaultdict(dict)
    for cell in cells:
        variant = cell["variant"]
        mixes[variant][cell["segment"]] = Fraction(cell["survey_n"], totals[variant][2])
    ranking_unavailable = None
    if len(variants) < 2 or totals.keys() != report.keys():
        ranking_unavailable = "missing_variants"
    elif any(mixes[v] != mixes[variants[0]] for v in variants[1:]):
        ranking_unavailable = "different_mix"
    real = [totals[v][0] / totals[v][2] for v in variants]
    pred = [totals[v][1] / totals[v][2] for v in variants]
    actual_winners, predicted_winners = [], []
    if ranking_unavailable is None:
        actual_winners = [v for v, x in zip(variants, real) if math.isclose(x, max(real))]
        predicted_winners = [v for v, x in zip(variants, pred) if math.isclose(x, max(pred))]
    unique = len(actual_winners) == len(predicted_winners) == 1
    survey_n = sum(c["survey_n"] for c in cells)
    result = {
        "mae_conversion": sum(c["error"] * c["survey_n"] for c in cells) / survey_n,
        "spearman_variants": _correlation(_rank(real), _rank(pred)) if ranking_unavailable is None else None,
        "winner_match": actual_winners == predicted_winners if unique else None,
        "survey_n": survey_n,
        "matched_cells": len(cells),
        "cells": cells,
        "actual_winners": actual_winners,
        "predicted_winners": predicted_winners,
    }
    intervals = assignment == "random_one" and bool(counts)
    if intervals:
        result["mae_interval_95_pp"] = _mae_interval_95_pp(cells, survey_n)
    if intervals or paired_probabilities:
        contrasts = _segment_contrasts(cells, intervals=intervals, paired_probabilities=paired_probabilities)
        if intervals or contrasts:
            result["segment_contrasts"] = contrasts
    if ranking_unavailable:
        result["ranking_unavailable"] = ranking_unavailable
    elif baseline and all(v in baseline for v in variants):
        mix = mixes[variants[0]]
        if not baseline_population:
            result["baseline_unavailable"] = "unknown_population"
        elif mix.keys() != baseline_population.keys() or any(
            not math.isclose(float(share), baseline_population[segment], rel_tol=0, abs_tol=1e-10)
            for segment, share in mix.items()
        ):
            result["baseline_unavailable"] = "different_population"
        else:
            result["baseline"] = _baseline_metrics(
                variants, real, pred, [baseline[v] for v in variants], totals
            )
    return result


def _baseline_metrics(variants, real, pred, base, totals):
    """Сравнение двойников и простого подхода на уровне предложений, по весам опроса.

    Сравнение строится только на совпадающем составе аудитории по каждому предложению.
    """
    weights = [totals[v][2] for v in variants]
    total = sum(weights)

    def mae(xs):
        return sum(abs(x - r) * w for x, r, w in zip(xs, real, weights)) / total

    actual = [v for v, x in zip(variants, real) if math.isclose(x, max(real))]
    base_winners = [v for v, x in zip(variants, base) if math.isclose(x, max(base))]
    unique = len(actual) == len(base_winners) == 1 and len(variants) > 1
    return {
        "twins_mae_variants": mae(pred),
        "baseline_mae_variants": mae(base),
        "twins_spearman": _correlation(_rank(real), _rank(pred)),
        "baseline_spearman": _correlation(_rank(real), _rank(base)),
        "baseline_winner_match": actual == base_winners if unique else None,
        "variants": [
            {"variant": v, "actual": r, "twins": p, "baseline": b}
            for v, r, p, b in zip(variants, real, pred, base)
        ],
    }
