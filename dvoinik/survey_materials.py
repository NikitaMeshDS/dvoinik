"""Neutral, offline materials for collecting real answers to a saved scenario.

No model results or fabricated responses belong in the respondent questionnaire.
Only cells with valid simulation answers can be compared by the existing validator.
"""

from __future__ import annotations

import csv
import io
from html import escape
from zipfile import ZIP_DEFLATED, ZipFile

from .population import SEGMENTS


def comparable_cells(record):
    return [
        (sid, vid)
        for vid in record["scenario"]["variants"]
        for sid in record["scenario"]["population"]
        if record["report"].get(vid, {}).get("segments", {}).get(sid, {}).get("n", 0) > 0
    ]


def survey_template(record):
    cells = comparable_cells(record)
    if not cells:
        raise ValueError("Нет валидных ответов симуляции для сопоставления. Повторите исследование.")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["segment", "variant", "decision"])
    writer.writerows((sid, vid, "") for sid, vid in cells)
    return stream.getvalue()


def questionnaire(record):
    scenario = record["scenario"]
    offers = "".join(
        f'<section class="offer"><h2>Предложение {escape(vid)}</h2>'
        f'<p class="terms">{escape(text)}</p>'
        f'<p class="question">{escape(scenario["question"])}</p>'
        '<p class="answers">☐ Да &nbsp;&nbsp;&nbsp; ☐ Нет</p>'
        '<p class="reason">Почему вы выбрали этот ответ? (необязательно)</p>'
        '<div class="writing-space"></div></section>'
        for vid, text in scenario["variants"].items()
    )
    return (
        """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Оценка банковских предложений</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f1f4f9;color:#192d40;
font:16px/1.65 "Avenir Next","Segoe UI",system-ui,sans-serif}
main{max-width:800px;margin:40px auto;background:white;padding:40px}
h1{font-size:30px;line-height:1.25;margin:0 0 20px}h2{font-size:19px;margin:0 0 15px}
.intro{color:#506579}.offer{border-top:1px solid #dce4ee;padding-top:28px;margin-top:32px}
.terms,.question{white-space:pre-wrap;overflow-wrap:anywhere}.question{font-weight:600}
.answers{font-size:20px}.reason{font-size:14px;color:#506579;margin-bottom:0}
.writing-space{height:70px;border-bottom:1px solid #dce4ee}footer{font-size:13px;margin-top:36px;color:#506579}
@media(max-width:600px){main{margin:0;padding:24px}h1{font-size:25px}}
@media print{@page{size:A4;margin:18mm}body{background:white;font-size:12pt}
main{margin:0;padding:0;max-width:none}.offer{break-inside:avoid}h1{font-size:22pt}}
</style></head><body><main>
<h1>Оценка банковских предложений</h1>
<p class="intro">Прочитайте условия каждого предложения и выберите один ответ на вопрос.
Правильных или неправильных ответов нет: нам важно ваше мнение.</p>
"""
        + offers
        + """
<footer>Это исследовательские варианты. Анкета не оформляет банковский продукт.
Не указывайте имя, телефон, номер счёта или другие персональные данные.</footer>
</main></body></html>"""
    )


def survey_kit(record):
    template = survey_template(record)
    scenario = record["scenario"]
    covered = set(comparable_cells(record))
    mapping = "\n".join(f"  {sid} — {SEGMENTS[sid]['name']}" for sid in scenario["population"])
    missing = [
        f"{sid}/{vid}"
        for vid in scenario["variants"]
        for sid in scenario["population"]
        if (sid, vid) not in covered
    ]
    guide = f"""Двойник · материалы для живого опроса
Исследование: {scenario["title"]}
Снимок: {record["id"]}

Состав комплекта
questionnaire.html — нейтральная анкета без результатов симуляции. Откройте в браузере;
её можно распечатать или сохранить в PDF через стандартное меню печати.
responses.csv — пустой шаблон ответов в UTF-8. Пустые decision намеренно не принимаются
за ответы: 0 означает настоящий отказ, 1 — настоящее согласие.

Перед опросом
1. Определите критерии набора целевой аудитории и правила отнесения к сегментам.
   Названия ниже — группы прототипа, а не подтверждённая банковская выборка.
2. Сохраняйте исходный вопрос и условия предложений. Можно показывать варианты
   по одному в разном порядке; сохраняйте их буквенные коды A–E при записи ответов.
3. Сравнивайте варианты на сопоставимом составе аудитории. Планируйте набор заранее;
   число двойников не задаёт необходимый размер живой выборки.
4. Не показывайте респондентам лидера, доли или объяснения модели до получения ответов.

Коды сегментов
{mapping}

Как заполнить responses.csv
Одна строка — одна оценка одного предложения одним респондентом.
segment — один из кодов выше; variant — буква показанного предложения;
decision — строго 0 или 1. Разделитель — запятая, кодировка — UTF-8.
Дублируйте строки для следующих оценок; удалите все незаполненные строки.
Шаблон содержит по одной заготовке для каждой ячейки с валидными ответами симуляции,
а не план набора и не пример состоявшегося опроса.
Не добавляйте контактные данные и персональные идентификаторы в файл загрузки.
Свободные комментарии в анкете необязательны и не входят в расчёт метрик CSV.

После опроса
В отчёте откройте вкладку «Проверка опросом», загрузите CSV, проверьте предпросмотр
и сохраните проверку. Загрузка нового файла заменяет прежний опрос, а не дополняет его.
Показатель количества в MVP считает оценки предложений, а не уникальных людей:
один человек, оценивший три варианта, даёт три оценки.
Совпадение лидера не доказывает точность прогноза. Заявленное намерение в анкете
не равно реальному оформлению продукта. Подлинность ответов сервис не проверяет.
"""
    if missing:
        guide += (
            "\nВ этих ячейках нет валидных ответов симуляции: " + ", ".join(missing) + ".\n"
            "Они исключены из шаблона: текущий валидатор не сможет их сопоставить.\n"
            "Для проверки всей аудитории повторите симуляцию с нужным покрытием.\n"
        )
    stream = io.BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as bundle:
        bundle.writestr("questionnaire.html", questionnaire(record))
        bundle.writestr("responses.csv", template)
        bundle.writestr("README.txt", guide)
    return stream.getvalue()
