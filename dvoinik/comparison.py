"""Описательные различия двух снимков. Дельта не является оценкой причинного эффекта."""

from __future__ import annotations

from .experiments import normalize_scenario
from .reporting import profile_policy_label


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
        "deposit_minimum_rub",
        "Минимальный взнос, ₽",
        a.get("deposit_minimum_rub"),
        b.get("deposit_minimum_rub"),
    )
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
    compare(
        "profile_policy",
        "Версия анкеты вклада",
        profile_policy_label(left.get("profile_policy")),
        profile_policy_label(right.get("profile_policy")),
    )
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
    warnings = []

    def warn(code, text):
        warnings.append({"code": code, "text": text})

    fields = {item["field"] for item in changes}
    if "mode" in fields:
        warn("mode", "Режимы различаются: демо и LLM формируют ответы разными способами.")
    if "model" in fields:
        warn(
            "model",
            "Модели различаются. Разница результатов может зависеть от модели, а не только от предложения.",
        )
    if fields & {"question", "description", "objections"}:
        warn(
            "question_context",
            "Вопрос, контекст или категории отказа изменены. Условия получения ответов различаются.",
        )
    if "deposit_minimum_rub" in fields:
        warn(
            "deposit_minimum",
            "Условия минимального взноса различаются. Оценки интереса получены для разных условий вклада.",
        )
    if "population" in fields:
        warn(
            "population",
            "Состав или доли целевой аудитории изменены. Общие доли согласий относятся к разным аудиториям.",
        )
    if fields & {"seed", "n", "population_counts"}:
        warn(
            "profile_sample",
            "Размер, распределение или seed выборки профилей изменены. Разница может зависеть от состава симуляции.",
        )
    if "profile_policy" in fields:
        warn(
            "profile_policy",
            "Версия анкеты вклада сохранена только в одном снимке. Оценки LLM могли быть получены по разным описаниям профилей.",
        )
    if set(a["variants"]) != set(b["variants"]):
        warn("variant_set", "Набор предложений различается. Не все варианты имеют пару для сравнения.")
    if any(a["variants"][vid] != b["variants"][vid] for vid in set(a["variants"]) & set(b["variants"])):
        warn(
            "variant_text",
            "Тексты предложений изменены. Одинаковые буквы не гарантируют одинаковых условий; сверьте тексты перед интерпретацией дельт.",
        )
    incomplete = any(row["left"] is None or row["right"] is None for row in variants + segments)
    for current in (left, right):
        for vid in current["scenario"]["variants"]:
            result = current["report"].get(vid)
            if not result or not result["n"]:
                incomplete = True
                continue
            if any(
                weight > 0 and not result["segments"].get(sid, {}).get("n")
                for sid, weight in current["scenario"]["population"].items()
            ):
                incomplete = True
    if incomplete:
        warn(
            "missing_data",
            "Для части предложений или сегментов нет валидных ответов в одном из запусков. Пропуски не означают нулевое согласие.",
        )
    if any(
        result.get("failed_n", 0) > 0 or result.get("inconsistent_n", 0) > 0
        for current in (left, right)
        for result in current["report"].values()
    ):
        warn(
            "response_quality",
            "В одном из запусков есть ошибки ответов или корректировки вероятностей. Невалидные ответы исключены из долей, корректировки включены в результат; проверьте качество каждого запуска перед сравнением.",
        )
    if "configuration" in fields:
        warn(
            "configuration",
            "Подписи конфигурации различаются. Сверьте параметры сервера и способ получения ответов.",
        )
    return {"changes": changes, "variants": variants, "segments": segments, "warnings": warnings}
