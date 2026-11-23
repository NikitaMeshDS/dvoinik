"""Проверка пользовательских сценариев и переносимых экспериментов.

Импортированные файлы — данные: их содержимое не исполняется, показатели проверки
пересчитываются по сохранённым ячейкам опроса. Истинность самого опроса не подтверждается.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections import Counter
from datetime import datetime
from itertools import combinations
from zoneinfo import ZoneInfo

from .population import SEGMENTS
from .report_stats import OTHER_OBJECTION, wilson_interval
from .reporting import PROFILES_PER_SEGMENT
from .scenarios import MAX_DEPOSIT_RUB
from .validate import SurveyRates, compare

MAX_IMPORT_BYTES = 5 * 1024 * 1024
BASELINE_METHODS = {"single_prompt", "demo_rule"}
CUSTOM_SCENARIO = {
    "title": "Новый эксперимент",
    "description": "Проверка собственной продуктовой гипотезы",
    "question": "Подключили бы вы это предложение?",
    "variants": {"A": "", "B": ""},
    "population": {},
    "objections": ["дорого", "непонятные условия", "не вижу пользы", "не доверяю", "нет причины менять банк"],
}


def _text(value, label, maximum=3000, required=True):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValueError(f"{label}: нужен {'непустой ' if required else ''}текст до {maximum} символов.")
    return value.strip()


def _integer(value, label, minimum=0, maximum=10000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label}: нужно целое число от {minimum} до {maximum}.")
    return value


def _number(value, label, minimum=0, maximum=1):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{label}: нужно конечное число от {minimum} до {maximum}.")
    return value


def normalize_scenario(scenario):
    if not isinstance(scenario, dict):
        raise ValueError("Сценарий должен быть объектом.")
    result = copy.deepcopy(scenario)
    for field, label, limit in [
        ("title", "Название исследования", 200),
        ("question", "Вопрос двойникам", 1000),
    ]:
        result[field] = _text(result.get(field), label, limit)
    result["description"] = _text(result.get("description", ""), "Описание", 4000, required=False)
    variants = result.get("variants")
    if (
        not isinstance(variants, dict)
        or not 2 <= len(variants) <= 5
        or list(variants) != list("ABCDE"[: len(variants)])
    ):
        raise ValueError("Нужны от двух до пяти вариантов A, B, C, D, E по порядку.")
    result["variants"] = {v: _text(t, f"Вариант {v}") for v, t in variants.items()}
    objections = result.get("objections")
    if not isinstance(objections, list) or not 1 <= len(objections) <= 12:
        raise ValueError("Укажите от 1 до 12 категорий отказа.")
    result["objections"] = [_text(o, "Категория отказа", 120) for o in objections]
    if len(set(result["objections"])) != len(objections):
        raise ValueError("Категории отказа не должны повторяться.")
    result["population"] = normalize_population(result.get("population"))
    if "deposit_minimum_rub" in result:
        _integer(result["deposit_minimum_rub"], "Минимальный взнос", minimum=1, maximum=MAX_DEPOSIT_RUB)
    if "origin" in result:
        result["origin"] = _origin(result["origin"])
    return result


ORIGIN_KINDS = {"iteration", "hypothesis"}


def _origin(value):
    """Откуда исследование: следующая итерация или проверка гипотезы другого снимка."""
    if not isinstance(value, dict) or value.get("kind") not in ORIGIN_KINDS:
        raise ValueError("Источник исследования: укажите тип iteration или hypothesis.")
    record_id = _text(value.get("record_id"), "Исходное исследование", 64)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", record_id):
        raise ValueError("Исходное исследование: некорректный идентификатор.")
    allowed = {"kind", "record_id", "title"}
    origin = {
        "kind": value["kind"],
        "record_id": record_id,
        "title": _text(value.get("title"), "Название исходного исследования", 200),
    }
    if value["kind"] == "hypothesis":
        allowed |= {"lever", "change", "variant", "hypothesis_id"}
        origin["lever"] = _text(value.get("lever"), "Рычаг гипотезы", 80)
        origin["change"] = _text(value.get("change"), "Изменение гипотезы", 300)
        variant = value.get("variant")
        if variant not in set("ABCDE"):
            raise ValueError("Гипотеза: исходный вариант должен быть A–E.")
        origin["variant"] = variant
        if "hypothesis_id" in value:
            identity = value["hypothesis_id"]
            if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
                raise ValueError("Гипотеза: некорректный стабильный идентификатор.")
            origin["hypothesis_id"] = identity
    if set(value) - allowed:
        raise ValueError("Источник исследования содержит лишние поля.")
    return origin


def normalize_population(weights):
    """Единая нормализация долей для предпросмотра и снимка запуска."""
    if not isinstance(weights, dict) or not weights or any(s not in SEGMENTS for s in weights):
        raise ValueError("Выберите известные сегменты аудитории.")
    for weight in weights.values():
        _number(weight, "Доля сегмента", maximum=1e6)
    total = sum(weights.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("Сумма долей аудитории должна быть больше нуля.")
    return {sid: weight / total for sid, weight in weights.items() if weight > 0}


def _timestamp(value):
    stamp = datetime.fromisoformat(_text(value, "Время запуска", 64))
    if stamp.tzinfo is None:
        raise ValueError("Время запуска должно содержать часовой пояс.")
    try:
        stamp.astimezone(ZoneInfo("Europe/Moscow"))
    except (OverflowError, ValueError) as exc:
        raise ValueError("Дата не может быть отображена в московском часовом поясе.") from exc
    return stamp


def format_timestamp(value):
    return _timestamp(value).astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M МСК")


def _check_result(result, population, objections, requested):
    if not isinstance(result, dict):
        raise ValueError("Результат варианта должен быть объектом.")
    n = _integer(result.get("n"), "Валидных ответов", maximum=requested)
    if "inconsistent_n" in result:
        _integer(result["inconsistent_n"], "Корректировок вероятности", maximum=n)
    known = {*objections, OTHER_OBJECTION}
    yes = _integer(result.get("yes"), "Согласий", maximum=n)
    failed = _integer(result.get("failed_n"), "Ошибок", maximum=requested)
    if _integer(result.get("requested_n"), "Запрошено ответов") != requested or n + failed != requested:
        raise ValueError("Количество ответов и ошибок не соответствует размеру аудитории.")
    rate = _number(result.get("conversion"), "Конверсия")
    if not math.isclose(rate, yes / n if n else 0, abs_tol=1e-10):
        raise ValueError("Конверсия не соответствует числу согласий.")
    segments = result.get("segments")
    if not isinstance(segments, dict) or any(s not in population for s in segments):
        raise ValueError("Результаты содержат неизвестный сегмент.")
    for sid, segment in segments.items():
        if not isinstance(segment, dict):
            raise ValueError("Результат сегмента должен быть объектом.")
        sn = _integer(segment.get("n"), "Ответов в сегменте", minimum=1, maximum=n)
        syes = _integer(segment.get("yes"), "Согласий в сегменте", maximum=sn)
        if not math.isclose(
            _number(segment.get("conversion"), "Конверсия сегмента"), syes / sn, abs_tol=1e-10
        ):
            raise ValueError("Конверсия сегмента не соответствует числу согласий.")
        segment["name"] = SEGMENTS[sid]["name"]
        segment["confidence_interval"] = wilson_interval(syes, sn)
        seg_reasons = segment.get("objections")
        if seg_reasons is not None:
            if not isinstance(seg_reasons, dict) or any(o not in known for o in seg_reasons):
                raise ValueError("В сегменте есть неизвестная категория отказа.")
            for count in seg_reasons.values():
                _integer(count, "Количество отказов в сегменте", maximum=sn)
            if sum(seg_reasons.values()) != sn - syes:
                raise ValueError("Причины отказа сегмента не соответствуют его ответам «нет».")
    if sum(s["n"] for s in segments.values()) != n or sum(s["yes"] for s in segments.values()) != yes:
        raise ValueError("Итоги сегментов не соответствуют итогам варианта.")
    reasons = result.get("objections")
    if not isinstance(reasons, dict) or any(o not in known for o in reasons):
        raise ValueError("В отчёте есть неизвестная категория отказа.")
    for count in reasons.values():
        _integer(count, "Количество отказов", maximum=n)
    if sum(reasons.values()) != n - yes:
        raise ValueError("Причины отказа не соответствуют количеству ответов «нет».")
    quotes = result.get("quotes")
    if not isinstance(quotes, list) or len(quotes) > 12:
        raise ValueError("Некорректная подборка синтетических ответов.")
    for quote in quotes:
        if (
            not isinstance(quote, dict)
            or type(quote.get("decision")) is not bool
            or quote.get("segment_id") not in segments
        ):
            raise ValueError("Некорректный ответ двойника в подборке.")
        _text(quote.get("who"), "Профиль ответа", 500)
        _text(quote.get("quote"), "Реплика", 1000)
        quote["segment"] = SEGMENTS[quote["segment_id"]]["name"]
    for field in ("probability", "raw_probability"):
        if field not in result or (field == "probability" and result[field] is None):
            continue
        probability = result[field]
        if not isinstance(probability, dict):
            raise ValueError("Сводка заявленной вероятности должна быть объектом.")
        _number(probability.get("mean"), "Средняя вероятность")
        _number(probability.get("sd"), "Разброс вероятности", maximum=0.5)
        minimum = 1 if field == "raw_probability" else 0
        if _integer(probability.get("n"), "Ответов с вероятностью", minimum=minimum, maximum=n) != n:
            raise ValueError("Сводка вероятности не соответствует числу ответов.")
    likert = result.get("likert")
    if likert is not None:
        if not isinstance(likert, list) or len(likert) != 5:
            raise ValueError("Распределение по шкале 1–5 должно содержать пять долей.")
        for share in likert:
            _number(share, "Доля точки шкалы")
        if abs(sum(likert) - 1) > 0.01:
            raise ValueError("Доли шкалы 1–5 должны давать в сумме 1.")
    examples = result.get("failure_examples", [])
    if not isinstance(examples, list) or len(examples) > 3:
        raise ValueError("Некорректные сведения об ошибках модели.")
    for error in examples:
        _text(error, "Ошибка модели", 1000)
    result["confidence_interval"] = wilson_interval(yes, n)


def _survey_from_cells(cells):
    if not isinstance(cells, list) or not cells or len(cells) > 35:
        raise ValueError("В проверке нужны ячейки живого опроса.")
    rates, counts = {}, {}
    for cell in cells:
        if not isinstance(cell, dict):
            raise ValueError("Ячейка опроса должна быть объектом.")
        key = (
            _text(cell.get("variant"), "Вариант опроса", 1),
            _text(cell.get("segment"), "Сегмент опроса", 64),
        )
        n = _integer(cell.get("n"), "Ответов в опросе", minimum=1, maximum=1000000)
        yes = _integer(cell.get("yes"), "Согласий в опросе", maximum=n)
        if key in rates:
            raise ValueError("Повторяющаяся ячейка опроса.")
        rates[key], counts[key] = yes / n, n
    return SurveyRates(rates, counts)


def _compare_survey(record, survey, protocol):
    baseline = record.get("baseline")
    baseline = baseline if isinstance(baseline, dict) else {}
    return compare(
        record["report"],
        survey,
        baseline=baseline.get("rates"),
        baseline_population=baseline.get("population"),
        assignment=protocol.get("assignment"),
        paired_probabilities=record.get("paired_probabilities"),
    )


def _check_baseline(baseline, variants):
    if not isinstance(baseline, dict) or baseline.get("method") not in BASELINE_METHODS:
        raise ValueError("Некорректная оценка простым подходом.")
    if "population" in baseline:
        population = baseline["population"]
        if (
            not isinstance(population, dict)
            or not population
            or any(segment not in SEGMENTS for segment in population)
            or not math.isclose(
                sum(
                    _number(weight, "Доля сегмента простого подхода", minimum=0)
                    for weight in population.values()
                ),
                1,
                rel_tol=0,
                abs_tol=1e-9,
            )
            or any(weight <= 0 for weight in population.values())
        ):
            raise ValueError("Некорректный состав аудитории простого подхода.")
    if "rates" in baseline:
        rates = baseline["rates"]
        if not isinstance(rates, dict) or set(rates) != set(variants):
            raise ValueError("Оценка простым подходом не совпадает с предложениями.")
        for value in rates.values():
            _number(value, "Доля простого подхода")
        if "error" in baseline:
            raise ValueError("Оценка простым подходом не может одновременно содержать доли и ошибку.")
    else:
        _text(baseline.get("error"), "Ошибка простого подхода", 1000)


PROTOCOL_ASSIGNMENTS = {
    "unknown": "Не указано",
    "random_one": "Один вариант на человека, назначен случайно",
    "one_nonrandom": "Один вариант на человека, без случайного назначения",
    "all_variants": "Каждый участник оценивал все варианты",
}


def normalize_protocol(protocol):
    """User-declared survey context; never inferred from response rows."""
    if protocol is None:
        return {}
    fields = {"recruitment", "collected_from", "collected_to", "assignment", "notes"}
    if not isinstance(protocol, dict) or set(protocol) - fields:
        raise ValueError("Некорректные сведения о происхождении опроса.")
    cleaned = {}
    for key, value in protocol.items():
        if not isinstance(value, str):
            raise ValueError("Сведения об опросе должны быть текстом.")
        value = value.strip()
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("Сведения об опросе: требуется корректный UTF-8.") from exc
        if not value:
            continue
        maximum = 1000 if key in {"recruitment", "notes"} else 40
        _text(value, "Сведения об опросе", maximum)
        if key in {"collected_from", "collected_to"}:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("Дата сбора опроса: требуется ГГГГ-ММ-ДД.")
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("Некорректная дата сбора опроса.") from exc
        if key == "assignment" and value not in PROTOCOL_ASSIGNMENTS:
            raise ValueError("Неизвестный способ распределения вариантов.")
        cleaned[key] = value
    if cleaned.get("collected_from", "") > cleaned.get("collected_to", "9999-12-31"):
        raise ValueError("Начало сбора опроса не может быть позже окончания.")
    return cleaned


def attach_validation(record, survey, protocol=None):
    protocol = normalize_protocol(protocol)
    result = _compare_survey(record, survey, protocol)
    counts = getattr(survey, "counts", None)
    if counts is None:
        raise ValueError("Для сохранения проверки нужны количества ответов опроса.")
    saved = copy.deepcopy(record)
    saved["validation"] = {
        "created_at": datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="seconds"),
        "source": "user_supplied_survey",
        "cells": [
            {"variant": vid, "segment": sid, "n": counts[(vid, sid)], "yes": round(rate * counts[(vid, sid)])}
            for (vid, sid), rate in survey.items()
        ],
        "result": result,
    }
    if protocol:
        saved["validation"]["protocol"] = protocol
    return saved


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        key.encode("utf-8")
        if key in result:
            raise ValueError(f"Повторяющееся поле JSON: {key[:80]}.")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Недопустимое число JSON: {value}.")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON содержит число за допустимым диапазоном.")
    return number


def _check_utf8(value):
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            item.encode("utf-8")
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def _check_run_usage(usage, mock, evaluations):
    fields = {"concurrency", "sdk_calls", "calls_with_usage", "reported_tokens", "cache_hits"}
    if not isinstance(usage, dict) or set(usage) != fields:
        raise ValueError("Некорректные поля статистики запуска.")
    _integer(usage["concurrency"], "Параллельность", minimum=1, maximum=64)
    calls = _integer(usage["sdk_calls"], "Вызовы SDK", maximum=0 if mock else 2**53 - 1)
    covered = _integer(usage["calls_with_usage"], "Вызовы с учётом токенов", maximum=calls)
    if covered or calls == 0:
        _integer(usage["reported_tokens"], "Учтённые токены", maximum=2**53 - 1 if covered else 0)
    elif usage["reported_tokens"] is not None:
        raise ValueError("Без данных провайдера расход токенов неизвестен.")
    _integer(usage["cache_hits"], "Ответы из кэша", maximum=0 if mock else evaluations)


def _check_paired_segments(segments, left, right, total, gap):
    if not isinstance(segments, dict) or set(segments) - (left["segments"].keys() & right["segments"].keys()):
        raise ValueError("Неизвестный сегмент парного сравнения.")
    matched, total_gap = 0, 0.0
    for segment, item in segments.items():
        if not isinstance(item, dict) or set(item) != {"matched_n", "gap_pp"}:
            raise ValueError("Некорректные данные парного сравнения по сегменту.")
        maximum = min(left["segments"][segment]["n"], right["segments"][segment]["n"])
        n = _integer(item["matched_n"], "Число пар в сегменте", minimum=1, maximum=maximum)
        measured = _number(item["gap_pp"], "Парная разница в сегменте", minimum=-100, maximum=100)
        matched += n
        total_gap += n * measured
    if matched != total or (total and not math.isclose(total_gap / total, gap, abs_tol=1e-9)):
        raise ValueError("Парное сравнение по сегментам не совпадает с общим итогом.")


def _check_paired_probabilities(pairs, report):
    expected = list(combinations(sorted(report), 2))
    if not isinstance(pairs, list) or len(pairs) != len(expected):
        raise ValueError("Некорректный список парных сравнений.")
    for item, (left, right) in zip(pairs, expected, strict=True):
        fields = {"variants", "matched_n", "means", "gap_pp", "interval_95_pp"}
        if (
            not isinstance(item, dict)
            or set(item) - {"segments"} != fields
            or item["variants"] != [left, right]
        ):
            raise ValueError("Парное сравнение не совпадает с вариантами отчёта.")
        n = _integer(
            item["matched_n"], "Число полных пар", maximum=min(report[left]["n"], report[right]["n"])
        )
        means, gap, interval = item["means"], item["gap_pp"], item["interval_95_pp"]
        if not n:
            if any(value is not None for value in (means, gap, interval)):
                raise ValueError("Для расчёта разницы нужна хотя бы одна полная пара.")
            if "segments" in item:
                _check_paired_segments(item["segments"], report[left], report[right], 0, None)
            continue
        if not isinstance(means, list) or len(means) != 2:
            raise ValueError("Для парного сравнения нужны две средние вероятности.")
        a, b = (_number(value, "Средняя вероятность") for value in means)
        measured = _number(gap, "Парная разница", minimum=-100, maximum=100)
        if not math.isclose(measured, (a - b) * 100, abs_tol=1e-9):
            raise ValueError("Парная разница не совпадает со средними вероятностями.")
        if "segments" in item:
            _check_paired_segments(item["segments"], report[left], report[right], n, measured)
        if n == 1 and interval is None:
            continue
        if n < 2 or not isinstance(interval, list) or len(interval) != 2:
            raise ValueError("Некорректный интервал парной разницы.")
        low, high = (_number(value, "Граница интервала", minimum=-100, maximum=100) for value in interval)
        if low > high:
            raise ValueError("Границы интервала должны быть упорядочены.")


def load_experiment(source):
    if not isinstance(source, (str, bytes)):
        raise ValueError("Нужен JSON-файл эксперимента.")
    try:
        size = len(source.encode("utf-8")) if isinstance(source, str) else len(source)
    except UnicodeError as exc:
        raise ValueError("Файл эксперимента должен содержать корректный текст UTF-8.") from exc
    if size > MAX_IMPORT_BYTES:
        raise ValueError("Максимальный размер эксперимента — 5 МБ.")
    try:
        text = source.decode("utf-8-sig") if isinstance(source, bytes) else source.lstrip("\ufeff")
        record = json.loads(
            text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant, parse_float=_finite_float
        )
        _check_utf8(record)
        if not isinstance(record, dict):
            raise ValueError("Эксперимент должен быть JSON-объектом.")
        if type(record.get("schema_version")) is not int or record["schema_version"] not in {1, 2}:
            raise ValueError("Поддерживаются версии формата 1 и 2.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", _text(record.get("id"), "ID", 64)):
            raise ValueError("Некорректный ID эксперимента.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", _text(record.get("scenario_key"), "ID сценария", 64)):
            raise ValueError("Некорректный ID сценария.")
        _timestamp(record.get("created_at"))
        n = _integer(record.get("n"), "Размер аудитории", minimum=1)
        _integer(record.get("seed"), "Seed", maximum=999999)
        for flag in ["mock", "sample"]:
            if type(record.get(flag)) is not bool:
                raise ValueError(f"Поле {flag} должно быть true или false.")
        _text(record.get("model"), "Модель", 200)
        _number(record.get("elapsed_seconds"), "Длительность", maximum=1e9)
        original = record.get("scenario")
        scenario = normalize_scenario(original)
        # Проверяем сценарий, но сохраняем точные тексты старых снимков и исходные относительные доли.
        record["scenario"] = copy.deepcopy(original)
        report = record.get("report")
        if not isinstance(report, dict) or set(report) != set(scenario["variants"]):
            raise ValueError("Варианты отчёта не совпадают с предложениями сценария.")
        if "run_usage" in record:
            _check_run_usage(record["run_usage"], record["mock"], n * len(report))
        counts = record.get("population_counts")
        if not isinstance(counts, dict) or any(s not in scenario["population"] for s in counts):
            raise ValueError("Некорректный состав аудитории.")
        for count in counts.values():
            _integer(count, "Число двойников", maximum=n)
        if sum(counts.values()) != n:
            raise ValueError("Состав аудитории не соответствует её размеру.")
        for result in report.values():
            _check_result(result, scenario["population"], scenario["objections"], n)
            if any(s["n"] > counts.get(sid, 0) for sid, s in result["segments"].items()):
                raise ValueError("В сегменте больше ответов, чем двойников.")
        if "paired_probabilities" in record:
            _check_paired_probabilities(record["paired_probabilities"], report)
        minimum = scenario.get("deposit_minimum_rub")
        eligibility = record.get("deposit_eligibility")
        if minimum is not None or "deposit_eligibility" in record:
            fields = {"available_n", "unavailable_n", "unknown_n"}
            if (
                minimum is None
                or not isinstance(eligibility, dict)
                or set(eligibility) != fields
                or sum(
                    _integer(eligibility[field], "Проверка доступности вклада", maximum=n) for field in fields
                )
                != n
            ):
                raise ValueError("Числа проверки доступности вклада не соответствуют размеру аудитории.")
        profiles = record.get("population_sample")
        if not isinstance(profiles, list) or len(profiles) > PROFILES_PER_SEGMENT * len(SEGMENTS):
            raise ValueError("Некорректная подборка профилей.")
        sampled_eligibility = Counter()
        for profile in profiles:
            if not isinstance(profile, dict) or profile.get("segment") not in counts:
                raise ValueError("Неизвестный сегмент профиля.")
            _integer(profile.get("id"), "ID профиля", maximum=n - 1)
            _integer(profile.get("age"), "Возраст", minimum=14, maximum=120)
            for field in ["name", "region", "income"]:
                _text(profile.get(field), f"Профиль: {field}", 500)
            _text(
                profile.get("attitude"),
                "Профиль: attitude",
                500,
                required=minimum is None and record["scenario_key"] != "senior_deposit",
            )
            habits = profile.get("habits")
            if not isinstance(habits, list) or not 1 <= len(habits) <= 10:
                raise ValueError("Привычки профиля должны быть списком.")
            for habit in habits:
                _text(habit, "Привычка", 500)
            if profile.get("digital") is not None:
                _text(profile["digital"], "Профиль: цифровые навыки", 500)
            if "available_deposit_rub" in profile:
                _integer(profile["available_deposit_rub"], "Свободная сумма", maximum=MAX_DEPOSIT_RUB)
            if minimum is not None:
                amount = profile.get("available_deposit_rub")
                category = (
                    "unknown_n" if amount is None else "available_n" if amount >= minimum else "unavailable_n"
                )
                sampled_eligibility[category] += 1
            traits = profile.get("traits")
            if traits is not None:
                if not isinstance(traits, dict) or len(traits) > 10:
                    raise ValueError("Атрибуты профиля должны быть словарём.")
                for label, value in traits.items():
                    _text(label, "Атрибут профиля", 100)
                    _text(value, "Значение атрибута", 500)
        if any(count > eligibility[category] for category, count in sampled_eligibility.items()):
            raise ValueError("Числа проверки доступности вклада не совпадают с сохранёнными профилями.")
        baseline = record.get("baseline")
        if baseline is not None:
            _check_baseline(baseline, scenario["variants"])
        validation = record.get("validation")
        if validation is not None:
            if not isinstance(validation, dict):
                raise ValueError("Некорректная проверка живым опросом.")
            if (
                record["schema_version"] == 1
                and "result" not in validation
                and "created_at" not in validation
            ):
                cells = validation.get("cells")
                if not isinstance(cells, list):
                    raise ValueError("В старом отчёте отсутствуют ячейки опроса.")
                migrated = []
                for cell in cells:
                    if not isinstance(cell, dict):
                        raise ValueError("Некорректная ячейка опроса в старом отчёте.")
                    count = _integer(cell.get("survey_n"), "Ответов в опросе", minimum=1, maximum=1000000)
                    agreed = _number(cell.get("actual"), "Конверсия опроса") * count
                    if not math.isclose(agreed, round(agreed), abs_tol=1e-7):
                        raise ValueError("В старом отчёте не согласованы доля и количество ответов опроса.")
                    migrated.append(
                        {
                            "variant": cell.get("variant"),
                            "segment": cell.get("segment"),
                            "n": count,
                            "yes": round(agreed),
                        }
                    )
                validation = {
                    "created_at": record["created_at"],
                    "timestamp_source": "experiment_export",
                    "cells": migrated,
                }
                record["validation"] = validation
            if "protocol" in validation:
                protocol = normalize_protocol(validation["protocol"])
                if protocol:
                    validation["protocol"] = protocol
                else:
                    validation.pop("protocol")
            _timestamp(validation.get("created_at"))
            survey = _survey_from_cells(validation.get("cells"))
            validation["result"] = _compare_survey(record, survey, validation.get("protocol", {}))
            validation["source"] = "user_supplied_survey"
        return record
    except (KeyError, TypeError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("Файл эксперимента повреждён или не содержит обязательных данных.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Не удалось прочитать JSON эксперимента.") from exc


def quality_status(record):
    failed = sum(r.get("failed_n", 0) for r in record["report"].values())
    validation = record.get("validation")
    if record["mock"]:
        return {
            "kind": "demo",
            "title": "Демонстрационный режим",
            "detail": "Эвристические ответы показывают рабочий процесс. Их нельзя использовать как прогноз реального спроса.",
        }
    if failed:
        return {
            "kind": "incomplete",
            "title": "Неполное покрытие ответов",
            "detail": f"{failed} запросов завершились ошибкой. Состав ответившей аудитории может сместить сравнение.",
        }
    if not validation:
        return {
            "kind": "unvalidated",
            "title": "Без проверки живым опросом",
            "detail": "LLM-результат ещё не сопоставлен с ответами людей. Следующий шаг — загрузить опрос.",
        }
    expected = {(v, s) for v, r in record["report"].items() for s in r["segments"]}
    covered = {(c["variant"], c["segment"]) for c in validation["cells"]}
    result = validation["result"]
    partial = expected != covered
    return {
        "kind": "partial_validation" if partial else "validated",
        "title": "Частичная проверка опросом" if partial else "Сопоставлен с живым опросом",
        "detail": f"{result['survey_n']} ответов опроса; ошибка {result['mae_conversion'] * 100:.1f} п.п. "
        + ("Не все варианты и сегменты проверены. " if partial else "")
        + "Источник опроса предоставлен пользователем; это не гарантия качества прогноза.",
    }
