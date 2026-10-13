"""Описательные различия двух снимков. Дельта не является оценкой причинного эффекта."""

from __future__ import annotations

from .experiments import normalize_scenario


def _row(variant, left, right, segment=None):
    left_rate = left["conversion"] if left and left["n"] else None
    right_rate = right["conversion"] if right and right["n"] else None
    row = {
        "variant": variant,
        "left": left_rate,
        "right": right_rate,
        "left_n": left["n"] if left else None,
        "right_n": right["n"] if right else None,
        "delta_pp": (right_rate - left_rate) * 100
        if left_rate is not None and right_rate is not None
        else None,
    }
    if segment is not None:
        row["segment"] = segment
    return row


def compare_runs(left, right):
    changes = []

    def compare(field, label, before, after):
        if before != after:
            changes.append({"field": field, "label": label, "before": before, "after": after})

    a, b = left["scenario"], right["scenario"]
    for field, label in [
        ("question", "Вопрос двойникам"),
        ("description", "Контекст исследования"),
        ("objections", "Категории отказа"),
    ]:
        compare(field, label, a[field], b[field])
    compare(
        "population",
        "Доли целевых сегментов",
        normalize_scenario(a)["population"],
        normalize_scenario(b)["population"],
    )
    compare(
        "population_counts",
        "Число профилей по сегментам",
        left["population_counts"],
        right["population_counts"],
    )
    compare("n", "Размер аудитории", left["n"], right["n"])
    compare("seed", "Seed", left["seed"], right["seed"])
    compare("mode", "Режим", "Демо" if left["mock"] else "LLM", "Демо" if right["mock"] else "LLM")
    compare("model", "Модель", left["model"], right["model"])
    variants, segments = [], []
    for vid in sorted(set(left["report"]) | set(right["report"])):
        compare(f"variant_{vid}", f"Предложение {vid}", a["variants"].get(vid), b["variants"].get(vid))
        first, second = left["report"].get(vid), right["report"].get(vid)
        variants.append(_row(vid, first, second))
        first_segments = first["segments"] if first else {}
        second_segments = second["segments"] if second else {}
        for sid in sorted(set(first_segments) | set(second_segments)):
            segments.append(_row(vid, first_segments.get(sid), second_segments.get(sid), sid))
    if not changes and left.get("signature") != right.get("signature"):
        compare(
            "configuration",
            "Подпись конфигурации",
            left.get("signature", "Не сохранена"),
            right.get("signature", "Не сохранена"),
        )
    return {"changes": changes, "variants": variants, "segments": segments}
