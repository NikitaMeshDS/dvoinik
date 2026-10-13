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
            # Снимок не содержит количественного распределения причин по сегментам.
            "objections": {},
            "quotes": copy.deepcopy([q for q in result["quotes"] if q["segment_id"] == sid]),
        }
    return focused
