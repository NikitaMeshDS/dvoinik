"""Сравнение симуляции с CSV живого опроса на одинаковом составе сегментов."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from contextlib import nullcontext
from pathlib import Path
from typing import TextIO


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


def compare(report: dict, survey: dict) -> dict:
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
    real = [totals[v][0] / totals[v][2] for v in variants]
    pred = [totals[v][1] / totals[v][2] for v in variants]
    actual_winners = [v for v, x in zip(variants, real) if math.isclose(x, max(real))]
    predicted_winners = [v for v, x in zip(variants, pred) if math.isclose(x, max(pred))]
    unique = len(actual_winners) == len(predicted_winners) == 1 and len(variants) > 1
    return {
        "mae_conversion": sum(c["error"] * c["survey_n"] for c in cells) / sum(c["survey_n"] for c in cells),
        "spearman_variants": _correlation(_rank(real), _rank(pred)),
        "winner_match": actual_winners == predicted_winners if unique else None,
        "survey_n": sum(c["survey_n"] for c in cells),
        "matched_cells": len(cells),
        "cells": cells,
        "actual_winners": actual_winners,
        "predicted_winners": predicted_winners,
    }
