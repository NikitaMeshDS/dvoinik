"""Проверка пользовательских сценариев и переносимых экспериментов.

Импортированные файлы — данные: их содержимое не исполняется, показатели проверки
пересчитываются по сохранённым ячейкам опроса. Истинность самого опроса не подтверждается.
"""

from __future__ import annotations

import copy
import json
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .engine import _interval
from .population import SEGMENTS
from .reporting import PROFILES_PER_SEGMENT
from .validate import SurveyRates, compare

MAX_IMPORT_BYTES = 5 * 1024 * 1024
BASELINE_METHODS = {"single_prompt", "demo_rule"}
CUSTOM_SCENARIO = {
    "title": "Новый эксперимент",
    "description": "Проверка собственной продуктовой гипотезы",
    "question": "Подключили бы вы это предложение?",
    "variants": {"A": "", "B": ""},
    "population": {"student_msk": 0.5, "student_reg": 0.5},
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
        allowed |= {"lever", "change", "variant"}
        origin["lever"] = _text(value.get("lever"), "Рычаг гипотезы", 80)
        origin["change"] = _text(value.get("change"), "Изменение гипотезы", 300)
        variant = value.get("variant")
        if variant not in set("ABCDE"):
            raise ValueError("Гипотеза: исходный вариант должен быть A–E.")
        origin["variant"] = variant
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
        segment["confidence_interval"] = _interval(syes, sn)
        seg_reasons = segment.get("objections")
        if seg_reasons is not None:
            if not isinstance(seg_reasons, dict) or any(o not in objections for o in seg_reasons):
                raise ValueError("В сегменте есть неизвестная категория отказа.")
            for count in seg_reasons.values():
                _integer(count, "Количество отказов в сегменте", maximum=sn)
            if sum(seg_reasons.values()) != sn - syes:
                raise ValueError("Причины отказа сегмента не соответствуют его ответам «нет».")
    if sum(s["n"] for s in segments.values()) != n or sum(s["yes"] for s in segments.values()) != yes:
        raise ValueError("Итоги сегментов не соответствуют итогам варианта.")
    reasons = result.get("objections")
    if not isinstance(reasons, dict) or any(o not in objections for o in reasons):
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
    probability = result.get("probability")
    if probability is not None:
        if not isinstance(probability, dict):
            raise ValueError("Сводка заявленной вероятности должна быть объектом.")
        _number(probability.get("mean"), "Средняя вероятность")
        _number(probability.get("sd"), "Разброс вероятности", maximum=0.5)
        if _integer(probability.get("n"), "Ответов с вероятностью", maximum=n) != n:
            raise ValueError("Сводка вероятности не соответствует числу ответов.")
    examples = result.get("failure_examples", [])
    if not isinstance(examples, list) or len(examples) > 3:
        raise ValueError("Некорректные сведения об ошибках модели.")
    for error in examples:
        _text(error, "Ошибка модели", 1000)
    result["confidence_interval"] = _interval(yes, n)


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


def _baseline_rates(record):
    baseline = record.get("baseline")
    return baseline.get("rates") if isinstance(baseline, dict) else None


def _check_baseline(baseline, variants):
    if not isinstance(baseline, dict) or baseline.get("method") not in BASELINE_METHODS:
        raise ValueError("Некорректная оценка простым подходом.")
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


def attach_validation(record, survey):
    result = compare(record["report"], survey, baseline=_baseline_rates(record))
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
        profiles = record.get("population_sample")
        if not isinstance(profiles, list) or len(profiles) > PROFILES_PER_SEGMENT * len(SEGMENTS):
            raise ValueError("Некорректная подборка профилей.")
        for profile in profiles:
            if not isinstance(profile, dict) or profile.get("segment") not in counts:
                raise ValueError("Неизвестный сегмент профиля.")
            _integer(profile.get("id"), "ID профиля", maximum=n - 1)
            _integer(profile.get("age"), "Возраст", minimum=14, maximum=120)
            for field in ["name", "region", "income", "attitude"]:
                _text(profile.get(field), f"Профиль: {field}", 500)
            habits = profile.get("habits")
            if not isinstance(habits, list) or not 1 <= len(habits) <= 10:
                raise ValueError("Привычки профиля должны быть списком.")
            for habit in habits:
                _text(habit, "Привычка", 500)
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
            _timestamp(validation.get("created_at"))
            survey = _survey_from_cells(validation.get("cells"))
            validation["result"] = compare(report, survey, baseline=_baseline_rates(record))
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
