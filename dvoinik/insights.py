"""Данные для матрицы и разбора сегмента, без изменения снимка исследования."""

from __future__ import annotations

import copy

from .engine import _interval
from .population import SEGMENTS


def matrix_rows(record: dict) -> list[dict]:
    rows = []
    for sid in record["scenario"]["population"]:
        cells = []
        for variant, result in record["report"].items():
            segment = result["segments"].get(sid, {})
            n, yes = segment.get("n", 0), segment.get("yes", 0)
            cells.append({"variant": variant, "n": n, "yes": yes, "conversion": yes / n if n else None})
        rates = [cell["conversion"] for cell in cells if cell["n"]]
        best = max(rates) if rates else None
        for cell in cells:
            cell["leading"] = bool(cell["n"] and cell["conversion"] == best)
        rows.append(
            {
                "id": sid,
                "name": SEGMENTS[sid]["name"],
                "requested_n": record["population_counts"].get(sid, 0),
                "cells": cells,
            }
        )
    return rows


def segment_report(record: dict, sid: str) -> dict:
    if sid not in record["scenario"]["population"]:
        raise ValueError("Сегмент отсутствует в сохранённой аудитории.")
    requested = record["population_counts"].get(sid, 0)
    focused = {}
    for variant, result in record["report"].items():
        segment = result["segments"].get(sid, {})
        n, yes = segment.get("n", 0), segment.get("yes", 0)
        focused[variant] = {
            "n": n,
            "yes": yes,
            "conversion": yes / n if n else None,
            "requested_n": requested,
            "failed_n": requested - n,
            "confidence_interval": _interval(yes, n),
            # Старые снимки не содержат распределения причин по сегментам.
            "objections": copy.deepcopy(segment.get("objections", {})),
            "quotes": copy.deepcopy([q for q in result["quotes"] if q["segment_id"] == sid]),
        }
    return focused


def insights_payload(record: dict, segment: str = "all") -> dict:
    """Ответ /api/insights: отчёт выбранной аудитории, сводка и встроенные проверки."""
    from .experiments import quality_status
    from .hypotheses import suggest
    from .planning import baseline_agreement, leader_stability, live_check_plan
    from .reporting import summarize

    report = record["report"] if segment == "all" else segment_report(record, segment)
    result = {
        "report": report,
        "summary": summarize(report),
        "quality": quality_status(record),
        "stability": leader_stability(report),
    }
    if segment == "all":
        result["plan"] = live_check_plan(record)
        result["baseline"] = baseline_agreement(record)
        result["hypotheses"] = suggest(record)
    return result
