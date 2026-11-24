"""Резюме исследования для команды: один самодостаточный HTML без скриптов.

Документ повторяет данные снимка и встроенные проверки. Все тексты экранируются,
внешние ресурсы запрещены CSP. Резюме не добавляет выводов сверх отчёта:
синтетические доли подписаны как гипотезы для живой проверки.
"""

from __future__ import annotations

from html import escape

from .experiments import format_timestamp
from .hypotheses import suggest
from .planning import baseline_agreement, leader_stability, live_check_plan
from .population import DISTORTION_RISK, SEGMENTS
from .reporting import profile_policy_label
from .scenarios import deposit_terms
from .validate import BASELINE_LIMITS, RANKING_LIMITS


def _pct(value) -> str:
    return "—" if value is None else f"{value * 100:.1f}".replace(".", ",") + "%"


def _num(value, digits=1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def _matrix(record) -> str:
    variants = list(record["report"])
    head = "".join(f"<th>{escape(v)}</th>" for v in variants)
    rows = []
    for sid in record["scenario"]["population"]:
        cells = []
        rates = []
        for vid in variants:
            seg = record["report"][vid]["segments"].get(sid)
            rates.append(seg["yes"] / seg["n"] if seg and seg["n"] else None)
        best = max((r for r in rates if r is not None), default=None)
        for rate in rates:
            mark = ' class="lead"' if rate is not None and rate == best else ""
            cells.append(f"<td{mark}>{_pct(rate)}</td>")
        name = escape(SEGMENTS[sid]["name"])
        count = record["population_counts"].get(sid, 0)
        rows.append(f"<tr><th>{name}<small>{count} профилей</small></th>{''.join(cells)}</tr>")
    total = "".join(
        f"<td><b>{_pct(r['conversion'] if r['n'] else None)}</b></td>" for r in record["report"].values()
    )
    rows.append(f"<tr class='total'><th>Вся аудитория</th>{total}</tr>")
    return f"<table><thead><tr><th>Сегмент</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _paired_comparison(record) -> str:
    pairs = record.get("paired_probabilities")
    if not pairs:
        return ""
    rows = []
    for pair in pairs:
        name = escape(" − ".join(pair["variants"]))
        means = " / ".join(_pct(p) for p in pair["means"]) if pair["means"] is not None else "—"
        gap = _num(pair["gap_pp"]) if pair["gap_pp"] is not None else "—"
        interval = pair["interval_95_pp"]
        bounds = " … ".join(_num(value) for value in interval) if interval is not None else "—"
        rows.append(
            f"<tr><th>{name}<small>{pair['matched_n']} из {record['n']} профилей</small></th>"
            f"<td>{means}</td><td>{gap}</td><td>{bounds}</td></tr>"
        )
    return (
        "<h2>Парное сравнение</h2><table><thead><tr>"
        "<th>Пара</th><th>Средние оценки «да»</th><th>Разница, п. п.</th><th>95% интервал, п. п.</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        "<p class='note'>Интервал показывает разброс при перевыборке общих синтетических профилей. "
        "Точность прогноза по ответам людей проверяется опросом.</p>"
    )


def _objections(record) -> str:
    items = []
    for vid, result in record["report"].items():
        top = sorted(result["objections"].items(), key=lambda kv: -kv[1])[:3]
        refusals = result["n"] - result["yes"]
        text = ", ".join(
            f"{escape(name)} ({_pct(count / refusals if refusals else None)})" for name, count in top
        )
        items.append(f"<li><b>{escape(vid)}:</b> {text or 'отказов нет'}</li>")
    return f"<ul>{''.join(items)}</ul>"


def _survey_coverage(record, result) -> str:
    variants = list(record["scenario"]["variants"])
    selected = [sid for sid, weight in record["scenario"]["population"].items() if weight > 0]
    counts = {(cell["variant"], cell["segment"]): cell["survey_n"] for cell in result["cells"]}
    totals = {vid: sum(counts.get((vid, sid), 0) for sid in selected) for vid in variants}
    covered = sum(counts.get((vid, sid), 0) > 0 for vid in variants for sid in selected)
    expected = len(variants) * len(selected)
    complete = expected > 0 and covered == expected
    lines = [f"<li><b>Покрытие опроса:</b> {covered} из {expected} пар «предложение — сегмент».</li>"]
    missing = [escape(vid) for vid in variants if not totals[vid]]
    if missing:
        lines.append(
            f"<li>Нет оценок предложений: {', '.join(missing)}. Сравнение всех предложений невозможно.</li>"
        )
    if not complete:
        lines.append(
            "<li>Часть выбранной аудитории не покрыта. Метрики относятся только к загруженным парам; отсутствие ответов не означает отказ.</li>"
        )
    elif len(variants) > 1:
        first = variants[0]
        same = all(
            abs(counts[(vid, sid)] / totals[vid] - counts[(first, sid)] / totals[first]) < 1e-9
            for vid in variants
            for sid in selected
        )
        lines.append(
            "<li>Доли сегментов одинаковы у всех предложений, число оценок может различаться.</li>"
            if same
            else "<li>Состав аудитории различается между предложениями. Разница долей согласий может быть связана с составом групп; проверьте схему набора и распределения участников.</li>"
        )
    for vid in variants:
        parts = []
        for sid in selected:
            count = counts.get((vid, sid), 0)
            share = f"{count} ({_pct(count / totals[vid])})" if count else "нет ответов"
            parts.append(f"{escape(SEGMENTS[sid]['name'])}: {share}")
        lines.append(f"<li><b>Предложение {escape(vid)}</b> — {totals[vid]} оценок; {'; '.join(parts)}.</li>")
    lines.append(
        "<li>Проценты — доля сегмента среди оценок каждого предложения. Полное покрытие не подтверждает репрезентативность, независимость ответов или достаточный размер выборки. Число уникальных людей и способ распределения нужно сверить с протоколом исследования.</li>"
    )
    return "".join(lines)


def _survey_discrepancies(record) -> str:
    validation = record.get("validation")
    if not validation or not (cells := validation["result"]["cells"]):
        return ""
    largest = sorted(cells, key=lambda cell: (-cell["error"], -cell["survey_n"]))[:5]
    rows = []
    for cell in largest:
        actual, predicted = cell["actual"], cell["predicted"]
        direction = (
            "Доли совпали"
            if actual == predicted
            else "Симуляция выше"
            if predicted > actual
            else "Симуляция ниже"
        )
        rows.append(
            f"<tr><th scope='row'>{escape(cell['variant'])}"
            f"<small>{escape(SEGMENTS[cell['segment']]['name'])}</small></th>"
            f"<td>{cell['survey_n']}</td>"
            f"<td>{_pct(actual)}<small>{_pct(predicted)}</small></td>"
            f"<td>{_num(cell['error'] * 100)} п.п.<small>{direction}</small></td></tr>"
        )
    return (
        '<section id="survey-discrepancies" aria-labelledby="survey-discrepancies-heading">'
        '<h2 id="survey-discrepancies-heading">Расхождения по сегментам</h2>'
        f'<p class="note">Сопоставленные пары ({len(largest)} из {len(cells)}) идут '
        "от большего расхождения к меньшему. Учитывайте число оценок в каждой паре. "
        "Полная таблица доступна в отчёте и в метриках проверки JSON.</p>"
        '<table class="survey-discrepancies"><thead><tr>'
        "<th scope='col'>Вариант и сегмент</th><th scope='col'>Оценок</th>"
        "<th scope='col'>Опрос<small>Симуляция</small></th>"
        "<th scope='col' aria-sort='descending'>Расхождение</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></section>"
    )


def _checks(record) -> str:
    report = record["report"]
    lines = []
    for variant, result in report.items():
        corrected = result.get("inconsistent_n", 0)
        if corrected:
            raw, adjusted = result.get("raw_probability"), result.get("probability")
            means = (
                f"Средняя вероятность по всем {result['n']} валидным ответам "
                f"до корректировки: {_pct(raw['mean'])}; после: {_pct(adjusted['mean'])}."
                if raw is not None and adjusted is not None
                else "Исходные значения не сохранены; среднее до корректировки неизвестно."
            )
            lines.append(
                f"<li><b>Корректировки вероятностей — вариант {escape(variant)}:</b> "
                f"{corrected} из {result['n']} ответов. Ответ «да/нет» расходился с вероятностью. "
                "Приложение заменило вероятность p на 1 − p. "
                f"Итоговые показатели включают эту корректировку. {means}</li>"
            )
    stability = leader_stability(report)
    if stability:
        lines.append(
            f"<li><b>Устойчивость лидера:</b> {escape(stability['leader'])} впереди "
            f"{escape(stability['runner_up'])} в {_num(stability['share'] * 100, 0)}% повторных выборок "
            f"({escape(stability['label'].lower())}). Это разброс внутри симуляции, а не точность.</li>"
        )
    agreement = baseline_agreement(record)
    if agreement and agreement.get("rows"):
        method = "один запрос без персонажей" if agreement["method"] == "single_prompt" else "демо-правило"
        rates = ", ".join(f"{escape(r['variant'])} {_pct(r['baseline'])}" for r in agreement["rows"])
        verdict = "совпадает" if agreement["same_leader"] else "различается"
        lines.append(f"<li><b>Простой подход</b> ({method}): {rates}; лидер {verdict}.</li>")
    elif agreement and agreement.get("error"):
        lines.append(f"<li><b>Простой подход:</b> оценка не получена ({escape(agreement['error'])}).</li>")
    validation = record.get("validation")
    if validation:
        result = validation["result"]
        line = (
            f"<li><b>Живой опрос:</b> {result['survey_n']} оценок, ошибка долей "
            f"{_num(result['mae_conversion'] * 100)} п.п."
        )
        base = result.get("baseline")
        if base:
            line += (
                f"; ошибка двойников {_num(base['twins_mae_variants'] * 100)} п.п., "
                f"простого подхода {_num(base['baseline_mae_variants'] * 100)} п.п."
            )
        lines.append(line + ". Источник ответов предоставлен пользователем.</li>")
        if interval := result.get("mae_interval_95_pp"):
            low, high = interval
            lines.append(
                f"<li><b>Приблизительный 95%-й интервал ошибки:</b> {_num(low)}–{_num(high)} п.п. "
                "Учитывает случайный разброс ответов опроса при фиксированных оценках "
                "симуляции и составе выборки.</li>"
            )
        if reason := result.get("baseline_unavailable"):
            lines.append(
                f"<li><b>Сравнение ошибок двух подходов недоступно.</b> {escape(BASELINE_LIMITS[reason])}</li>"
            )
        if reason := result.get("ranking_unavailable"):
            lines.append(f"<li><b>Общий рейтинг недоступен.</b> {escape(RANKING_LIMITS[reason])}</li>")
        lines.append(_survey_coverage(record, result))
        from .experiments import PROTOCOL_ASSIGNMENTS, normalize_protocol

        protocol = normalize_protocol(validation.get("protocol"))
        if not protocol:
            lines.append(
                "<li><b>Происхождение опроса:</b> сведения о наборе, периоде и распределении не указаны.</li>"
            )
        else:
            recruitment = escape(protocol.get("recruitment", "не указан"))
            first = escape(protocol.get("collected_from", "не указано"))
            last = escape(protocol.get("collected_to", "не указано"))
            assignment = escape(PROTOCOL_ASSIGNMENTS.get(protocol.get("assignment", "unknown"), "Не указано"))
            lines.append(
                f"<li><b>Происхождение опроса:</b> набор — {recruitment}; начало — {first}; окончание — {last}; распределение — {assignment}.</li>"
            )
            if protocol.get("notes"):
                lines.append(f"<li><b>Заметки исследователя:</b> {escape(protocol['notes'])}</li>")

    else:
        lines.append("<li><b>Живой опрос:</b> ещё не загружен.</li>")
    return f"<ul>{''.join(lines)}</ul>"


def _plan(record) -> str:
    plan = live_check_plan(record)
    rows = []
    for item in plan["comparisons"]:
        needed = (
            "без расчёта при разнице < 2 п.п."
            if item["n_per_variant"] is None
            else f"≈ {item['n_per_variant']}"
        )
        left, right = (escape(v) for v in item["pair"])
        rows.append(
            f"<tr><td>{left} против {right}</td><td>{_num(item['gap_pp'])} п.п.</td><td>{needed}</td></tr>"
        )
    table = (
        "<table><thead><tr><th>Сравнение</th><th>Разница в симуляции</th><th>Оценок на предложение</th></tr>"
        f"</thead><tbody>{''.join(rows)}</tbody></table>"
        if rows
        else ""
    )
    focus = "".join(
        f"<li>{escape(s['name'])}: лидирует {escape(s['leader'])} (+{_num(s['gap_pp'])} п.п.)</li>"
        for s in plan["focus_segments"]
    )
    questions = "".join(f"<li>{escape(q['text'])}</li>" for q in plan["questions"])
    return (
        table + f"<p>Разведка на {plan['exploratory_n']} оценках на предложение заметит только разницу от "
        f"{_num(plan['exploratory_detectable_pp'])} п.п.</p>"
        + (f"<h3>Проверить отдельно</h3><ul>{focus}</ul>" if focus else "")
        + f"<h3>Вопросы для интервью</h3><ol>{questions}</ol>"
        + f"<p class='note'>{escape(plan['assumptions'])}</p>"
    )


def _hypotheses(record) -> str:
    items = suggest(record)["items"]
    if not items:
        return "<p>Частых причин отказа, которые можно снять изменением текста, не найдено.</p>"
    blocks = []
    for h in items:
        evidence = "".join(f"<li>{escape(e)}</li>" for e in h["evidence"])
        check = (
            f"≈ {h['check_n']} оценок на вариант при целевой разнице в половину указанной величины"
            if h["check_n"]
            else "объём живого теста не рассчитан"
        )
        metric = (
            "Разница между вариантами в главном сегменте симуляции"
            if h["kind"] == "segment_offer"
            else "Доля отказов по этой причине среди ответов главного сегмента"
        )
        blocks.append(
            f"<h3>{escape(h['lever'])}</h3><p>{escape(h['change'])}.</p><ul>{evidence}</ul>"
            f"<p><b>Новый текст:</b> {escape(h['proposal'])}</p>"
            f"<p class='note'>{metric} — {_num(h['ceiling_pp'])} п.п. Ориентир для опроса — {check}.</p>"
        )
    return "".join(blocks)


def _passport(record) -> str:
    """Раскрытие метода по образцу рекомендаций ESOMAR и AAPOR для синтетических данных."""
    scenario = record["scenario"]
    if record["mock"]:
        method = "Демо-эвристика по ключевым словам, без LLM"
    elif "SSR" in record["model"]:
        method = "LLM играет персонажей; готовность — по смыслу ответа (SSR, эмбеддинги)"
    else:
        method = "LLM играет персонажей и называет решение и вероятность"
    segments = ", ".join(SEGMENTS[s]["name"] for s in scenario["population"])
    risky = [SEGMENTS[s]["name"] for s in scenario["population"] if s in DISTORTION_RISK]
    validation = record.get("validation")
    origin = scenario.get("origin")
    rows = [
        ("Метод", method),
        ("Модель", record["model"]),
        ("Аудитория", f"{record['n']} синтетических профилей: {segments}"),
        ("Воспроизводимость", f"seed {record['seed']}, подпись снимка {record.get('signature', '—')[:12]}"),
        (
            "Проверка на людях",
            f"загружен опрос, {validation['result']['survey_n']} оценок"
            if validation
            else "ещё не проводилась",
        ),
        (
            "Ограничения",
            "Синтетические ответы — гипотезы для живого исследования, а не измерение спроса. "
            "Средние и ранги ближе к людям, чем ответы отдельных персонажей.",
        ),
    ]
    if risky:
        rows.append(("Риск искажений", "Низкий доход, проверить в первую очередь: " + ", ".join(risky)))
    if record["population_counts"].get("senior") and (
        record["scenario_key"] == "senior_deposit" or "deposit_minimum_rub" in scenario
    ):
        rows.append(("Версия анкеты вклада", profile_policy_label(record.get("profile_policy"))))
    if origin:
        kind = (
            "проверка гипотезы «" + origin.get("lever", "") + "»"
            if origin["kind"] == "hypothesis"
            else "итерация"
        )
        rows.append(("Источник", f"{kind} исследования «{origin['title']}»"))
    body = "".join(f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in rows)
    return f"<table class='passport'><tbody>{body}</tbody></table>"


def team_summary(record: dict) -> str:
    scenario = record["scenario"]
    mode = (
        "Демо: эвристические ответы показывают рабочий процесс, а не прогноз спроса."
        if record["mock"]
        else f"LLM: {escape(record['model'])}. Синтетические ответы требуют живой проверки."
    )
    offers = "".join(
        f"<li><b>{escape(vid)}.</b> {escape(text)}</li>" for vid, text in scenario["variants"].items()
    )
    eligibility = record.get("deposit_eligibility")
    access = ""
    if eligibility is not None:
        access = (
            f"<h2>По минимальному взносу</h2><p>{escape(deposit_terms(scenario))} "
            f"Хватает средств у {eligibility['available_n']} из {record['n']} профилей. "
            f"Не хватает у {eligibility['unavailable_n']}, сумма неизвестна у {eligibility['unknown_n']}. "
            "Суммы синтетические.</p>"
        )
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{escape(scenario["title"])} — резюме исследования</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f1f4f9;color:#192d40;
font:15px/1.6 "Avenir Next","Segoe UI",system-ui,sans-serif}}
main{{max-width:880px;margin:32px auto;background:#fff;padding:40px;border-radius:14px}}
h1{{font-size:28px;line-height:1.2;margin:0 0 6px}}h2{{font-size:18px;margin:32px 0 10px;
padding-top:20px;border-top:1px solid #dce4ee}}h3{{font-size:15px;margin:18px 0 6px}}
.meta{{color:#60758c;margin:0}}.mode{{background:#edf2fc;border-radius:10px;padding:10px 14px;margin:18px 0;
font-size:14px}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #e6ecf3;vertical-align:top}}
thead th{{font-size:12px;color:#60758c;font-weight:600}}tbody th small{{display:block;color:#60758c;font-weight:400}}
td.lead{{color:#315cf3;font-weight:700}}.passport th{{width:30%;font-weight:600}}tr.total th,tr.total td{{border-top:2px solid #dce4ee}}
.note{{font-size:13px;color:#60758c}}ul,ol{{padding-left:20px}}li{{margin:4px 0}}
.survey-discrepancies small{{display:block;color:#60758c;font-weight:400}}
.survey-discrepancies th,.survey-discrepancies td{{overflow-wrap:anywhere}}
footer{{margin-top:32px;font-size:12px;color:#60758c}}
@media(max-width:640px){{main{{margin:0;padding:22px;border-radius:0}}
.survey-discrepancies th,.survey-discrepancies td{{padding:7px 5px;font-size:12px}}}}
@media print{{@page{{size:A4;margin:16mm}}body{{background:#fff}}main{{margin:0;padding:0;max-width:none}}
h2{{break-after:avoid}}table{{break-inside:avoid}}}}
</style></head><body><main>
<h1>{escape(scenario["title"])}</h1>
<p class="meta">{escape(format_timestamp(record["created_at"]))} · {record["n"]} двойников · снимок {escape(record["id"])}</p>
<p class="mode">{mode}</p>
<p><b>Вопрос:</b> {escape(scenario["question"])}</p>
<h2>Паспорт исследования</h2>{_passport(record)}
<h2>Предложения</h2><ul>{offers}</ul>
{_paired_comparison(record)}
<h2>{"Интерес по сегментам" if eligibility is not None else "Доли согласий по сегментам"}</h2>{_matrix(record)}
{access}
<p class="note">Выделены наибольшие доли в строке; статистическая значимость не проверялась.</p>
<h2>Частые причины отказа</h2>{_objections(record)}
<h2>Проверки качества</h2>{_checks(record)}
{_survey_discrepancies(record)}
<h2>Гипотезы: что поменять в предложении</h2>{_hypotheses(record)}
<h2>План живой проверки</h2>{_plan(record)}
<footer>Двойник · синтетическая аудитория для подготовки живых исследований. Доли — заявленная готовность
синтетических персонажей, а не фактическое оформление продукта. Резюме сформировано из сохранённого снимка.</footer>
</main></body></html>"""
