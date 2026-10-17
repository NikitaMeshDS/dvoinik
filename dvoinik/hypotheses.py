"""Гипотезы изменения предложений: что поменять, чтобы снять частые отказы.

Гипотезы строятся из снимка без новых запросов к модели:
- частые причины отказа от лидера группируются по рычагу (цена, канал, доверие,
  понятность…), для рычага правило готовит черновик нового текста: убирает
  мешающую формулировку и добавляет новую фразу;
- если в сегменте другой вариант заметно сильнее общего лидера, предлагается
  отдельное предложение для этого сегмента.

Это гипотезы для следующей итерации, а не прогноз. Потолок эффекта считается так,
будто причина отказа устранена полностью. Проверка — A/B-запуск «лидер против
гипотезы» на тех же сегментах и затем живой опрос.
"""

from __future__ import annotations

import re

from .planning import MIN_DIFFERENCE, sample_size

MAX_HYPOTHESES = 4
MIN_SEGMENT_N = 10
MIN_CEILING = 0.05
SEGMENT_GAP = 0.05
MAX_TEXT = 3000

# Рычаги: ключевые слова категории отказа → что поменять и как.
# Порядок важен: берётся первый подходящий рычаг.
# drop — предложения исходного текста, которые убираются целиком;
# replace — фрагменты, которые заменяются внутри предложения; add — новая фраза.
LEVERS = [
    {
        "id": "yield",
        "match": ["недостаточ", "низкая доходн"],
        "lever": "Доходность",
        "change": "Повысить выгоду: надбавка к ставке за понятное действие клиента",
        "add": "Надбавка к ставке за ежемесячное пополнение.",
    },
    {
        "id": "price",
        "match": ["плат", "комисс", "дорог", "цена"],
        "lever": "Цена",
        "change": "Убрать абонентскую плату и условия бесплатности, которые отпугивают",
        "drop": r"^(обслуживание|плата|стоимость)\b.*₽",
        "replace": (r"\d[\d\s]*₽\s*/\s*мес", "без абонентской платы"),
        "add": "Без скрытых платежей.",
    },
    {
        "id": "fraud",
        "match": ["мошенник"],
        "lever": "Защита",
        "change": "Явно сказать, как банк защищает от мошенников",
        "add": "Крупные операции подтверждаются отдельно, сотрудник банка никогда не просит код из СМС.",
    },
    {
        "id": "trust",
        "match": ["довер"],
        "lever": "Доверие",
        "change": "Добавить понятное подтверждение надёжности и фиксированных условий",
        "replace": (r"[,;]?\s*только сегодня", ""),
        "add": "Все условия зафиксированы в договоре и видны в приложении до оформления.",
    },
    {
        "id": "switch",
        "match": ["нет причины", "уже пользуюсь", "не вижу пользы", "не нужно", "переход"],
        "lever": "Причина перейти",
        "change": "Дать повод перейти сейчас и снизить усилие перехода",
        "add": "Бонус за первый месяц и перенос регулярных платежей из другого банка за пару минут.",
    },
    {
        "id": "channel",
        "match": ["канал", "неудобн"],
        "lever": "Канал оформления",
        "change": "Дать оформить так, как удобно сегменту: в отделении или с сотрудником",
        "replace": (r"только в приложении|только онлайн", "в приложении, в отделении или по телефону"),
        "add": "Оформить можно в отделении или по телефону с помощью сотрудника.",
    },
    {
        "id": "setup",
        "match": ["договориться"],
        "lever": "Простой старт",
        "change": "Разрешить начать вдвоём и настроить роли позже",
        "add": "Можно начать вдвоём и добавить остальных позже, роли и лимиты настраиваются за пару минут.",
    },
    {
        "id": "clarity",
        "match": ["сложн", "непонятн", "разобраться", "документ", "нет времени"],
        "lever": "Понятность",
        "change": "Оставить одно главное условие и показать пример расчёта",
        "add": "Главное условие — в одной строке, рядом пример: примерно сколько вы получите за месяц.",
    },
    {
        "id": "language",
        "match": ["язык"],
        "lever": "Язык",
        "change": "Объяснять условия на родном языке клиента",
        "add": "Подсказки к условиям и поддержка на родном языке.",
    },
    {
        "id": "categories",
        "match": ["категори", "не на мои траты"],
        "lever": "Выбор выгоды",
        "change": "Дать клиенту самому выбирать категории выгоды",
        "add": "Категории кэшбэка вы выбираете сами каждый месяц.",
    },
    {
        "id": "debt",
        "match": ["долг", "высокая ставка"],
        "lever": "Контроль долга",
        "change": "Снять страх долга: напоминания и лимит, который клиент задаёт сам",
        "add": "Напомним о платеже за 3 дня, лимит можно уменьшить самостоятельно в любой момент.",
    },
    {
        "id": "privacy",
        "match": ["приватн"],
        "lever": "Приватность",
        "change": "Оставить личные траты личными",
        "replace": (r"каждый видит все траты", "общие траты видны всем, личные — только владельцу"),
        "add": "Каждый сам решает, какие траты видны семье.",
    },
    {
        "id": "frequency",
        "match": ["спам", "уведомлен"],
        "lever": "Частота и тон",
        "change": "Писать реже, по выбору клиента и без давления",
        "replace": (r"[,;]?\s*только сегодня", ""),
        "add": "Не больше одного сообщения в неделю и только по выбранным вами категориям.",
    },
]


def lever_for(objection: str) -> dict | None:
    text = objection.lower().replace("ё", "е")
    for lever in LEVERS:
        if any(word in text for word in lever["match"]):
            return lever
    return None


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def rewrite(text: str, lever: dict) -> dict:
    """Черновик нового текста по правилу и список изменений для показа «было → стало»."""
    removed, added, kept = [], [], []
    for sentence in _sentences(text):
        if lever.get("drop") and re.search(lever["drop"], sentence, re.IGNORECASE):
            removed.append(sentence)
            continue
        if lever.get("replace"):
            pattern, value = lever["replace"]
            found = [m.group(0).strip(" ,;") for m in re.finditer(pattern, sentence, re.IGNORECASE)]
            if found:
                sentence = re.sub(pattern, value, sentence, flags=re.IGNORECASE)
                sentence = re.sub(r"\s+([,.:;!?])", r"\1", re.sub(r"\s{2,}", " ", sentence)).strip()
                removed += found
                if value:
                    added.append(value)
        kept.append(sentence)
    if lever["add"] not in kept:
        kept.append(lever["add"])
        added.append(lever["add"])
    proposal = " ".join(kept)
    if proposal == text.strip() or len(proposal) > MAX_TEXT:
        return {"proposal": None, "removed": [], "added": []}
    return {"proposal": proposal, "removed": removed, "added": added}


def _leader(report: dict) -> str | None:
    valid = {v: r for v, r in report.items() if r.get("n")}
    if not valid:
        return None
    return max(sorted(valid), key=lambda v: valid[v]["conversion"])


def _check_size(rate: float, ceiling: float) -> int | None:
    """Ответов на вариант, чтобы в живом тесте заметить половину потолка эффекта."""
    target = min(0.99, rate + ceiling / 2)
    if target - rate < MIN_DIFFERENCE:
        return None
    return sample_size(rate, target)


def _pp(value: float) -> str:
    return f"{value * 100:.1f}".replace(".", ",") + "%"


def _objection_items(record: dict, leader: str, total: int) -> list[dict]:
    variant = record["report"][leader]
    segments = [(sid, s) for sid, s in variant.get("segments", {}).items() if s.get("objections")]
    if not segments and variant.get("objections"):
        # Старые снимки без причин по сегментам: гипотезы на всю аудиторию.
        segments = [(None, {"name": "Вся аудитория", **variant})]
    groups: dict[str, dict] = {}
    for sid, seg in segments:
        n = seg.get("n") or 0
        if n < MIN_SEGMENT_N:
            continue
        for objection, count in seg["objections"].items():
            lever = lever_for(objection)
            if not lever or not count or count / n < MIN_CEILING:
                continue
            group = groups.setdefault(lever["id"], {"lever": lever, "rows": []})
            group["rows"].append(
                {
                    "segment": sid,
                    "segment_name": seg["name"],
                    "objection": objection,
                    "count": count,
                    "n": n,
                    "share": count / n,
                    "base_rate": seg["conversion"],
                }
            )
    text = record["scenario"]["variants"][leader]
    items = []
    for lever_id, group in groups.items():
        lever, rows = group["lever"], sorted(group["rows"], key=lambda r: (-r["count"], str(r["segment"])))
        draft = rewrite(text, lever)
        if draft["proposal"] is None:
            continue
        main = rows[0]
        segment_ids = list(dict.fromkeys(r["segment"] for r in rows))
        items.append(
            {
                "kind": "objection",
                "lever_id": lever_id,
                "lever": lever["lever"],
                "change": lever["change"],
                "variant": leader,
                "segments": [s for s in segment_ids if s is not None],
                "segment_names": list(dict.fromkeys(r["segment_name"] for r in rows)),
                "objections": list(dict.fromkeys(r["objection"] for r in rows)),
                "evidence": [
                    f"«{r['objection']}» — {r['count']} из {r['n']} в сегменте «{r['segment_name']}»"
                    for r in rows
                ],
                "base_rate": main["base_rate"],
                "ceiling_pp": round(main["share"] * 100, 1),
                "audience_pp": round(sum(r["count"] for r in rows) / total * 100, 1),
                "check_n": _check_size(main["base_rate"], main["share"]),
                "base_text": text,
                **draft,
            }
        )
    return items


def _segment_items(record: dict, leader: str, total: int) -> list[dict]:
    report = record["report"]
    items = []
    for sid, lead in report[leader].get("segments", {}).items():
        if (lead.get("n") or 0) < MIN_SEGMENT_N:
            continue
        rivals = [
            (v, r["segments"][sid])
            for v, r in sorted(report.items())
            if v != leader and (r.get("segments", {}).get(sid, {}).get("n") or 0) >= MIN_SEGMENT_N
        ]
        if not rivals:
            continue
        best, seg = max(rivals, key=lambda item: item[1]["conversion"])
        gap = seg["conversion"] - lead["conversion"]
        if gap < SEGMENT_GAP:
            continue
        items.append(
            {
                "kind": "segment_offer",
                "lever_id": "segment",
                "lever": "Своё предложение для сегмента",
                "change": f"Предлагать этому сегменту вариант {best} вместо общего лидера {leader}",
                "variant": leader,
                "alternative": best,
                "segments": [sid],
                "segment_names": [lead["name"]],
                "objections": [],
                "evidence": [
                    f"В сегменте «{lead['name']}» вариант {best} — {_pp(seg['conversion'])}, "
                    f"общий лидер {leader} — {_pp(lead['conversion'])}"
                ],
                "base_rate": lead["conversion"],
                "ceiling_pp": round(gap * 100, 1),
                "audience_pp": round(gap * lead["n"] / total * 100, 1),
                "check_n": _check_size(lead["conversion"], gap),
                "base_text": record["scenario"]["variants"][leader],
                "proposal": record["scenario"]["variants"][best],
                "removed": [],
                "added": [],
            }
        )
    return items


def suggest(record: dict, limit: int = MAX_HYPOTHESES) -> dict:
    """Гипотезы для следующей итерации, по убыванию потолка эффекта на всю аудиторию."""
    report = record.get("report") or {}
    leader = _leader(report)
    if leader is None:
        return {"leader": None, "items": []}
    total = report[leader]["n"]
    candidates = _segment_items(record, leader, total) + _objection_items(record, leader, total)
    candidates.sort(key=lambda h: (-h["audience_pp"], -h["ceiling_pp"], h["lever_id"], h["segments"]))
    items = [{"id": f"h{i}", **item} for i, item in enumerate(candidates[:limit], 1)]
    return {"leader": leader, "items": items}
