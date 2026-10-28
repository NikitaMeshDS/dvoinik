"""Бенчмарк на открытых данных: насколько двойники и простой подход близки к известным долям.

Для каждого факта из benchmarks/open_facts.json двойники нужного сегмента отвечают «да» или «нет»
на вопрос анкеты, а простой подход одним запросом оценивает долю «да» для той же аудитории.
Сравнивается ошибка в процентных пунктах с опубликованной долей и с наивным ответом 50%.

Это проверка на чужих данных разных лет и методов, а не точность прогноза спроса на банковский
продукт. Факты, которые использовались как ориентир при составлении профилей, помечены
и считаются отдельно.

    LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=qwen2.5:7b-instruct python benchmark.py --n 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import time
from pathlib import Path

from dvoinik import engine, llm_json, ssr
from dvoinik.population import SEGMENTS, build_population

FACTS = Path(__file__).with_name("benchmarks") / "open_facts.json"

FACT_SYSTEM = (
    "Ты — конкретный человек, описанный ниже. Отвечай на вопрос анкеты честно, как ответил бы он, "
    "учитывая возраст, доход, привычки и отношение к банкам.\n"
    'Ответь строго JSON: {"answer": true|false, '
    '"probability": вероятность ответа «да» от 0 до 1, где 0 — точно нет, 1 — точно да}'
)
FACT_SSR_SYSTEM = (
    "Ты — конкретный человек, описанный ниже. Ответь на вопрос анкеты одной короткой фразой "
    "от первого лица, как ответил бы он, без чисел и оценок.\n"
    'Ответь строго JSON: {"reply": "одна фраза"}'
)
# Эталоны шкалы «нет — да» для вопросов анкеты (режим SSR).
FACT_REFERENCES = [
    ["Нет, точно нет.", "Скорее нет.", "Не знаю, затрудняюсь ответить.", "Скорее да.", "Да, конечно."],
    [
        "Нет, у меня такого нет.",
        "Почти нет, очень редко.",
        "Иногда, сложно сказать.",
        "В основном да.",
        "Да, именно так.",
    ],
]
SHARE_SYSTEM = (
    "Ты — аналитик. Оцени, какая доля описанной аудитории ответит «да» на вопрос анкеты. "
    "Не моделируй отдельных людей: дай одну общую оценку.\n"
    'Ответь строго JSON: {"share": 0..1}'
)


def load_facts(path: Path = FACTS) -> list[dict]:
    facts = json.loads(path.read_text(encoding="utf-8"))["facts"]
    for fact in facts:
        if not 0 <= fact["share"] <= 1 or not fact["question"].strip():
            raise ValueError(f"{fact['id']}: доля должна быть от 0 до 1, вопрос — непустым.")
        if any(s not in SEGMENTS for s in fact["segments"]):
            raise ValueError(f"{fact['id']}: неизвестный сегмент.")
    return facts


def _audience(segments: dict[str, float]) -> str:
    total = sum(segments.values())
    return "; ".join(f"{SEGMENTS[s]['name']} — {w / total:.0%}" for s, w in segments.items())


async def _chat(client, sem, system: str, user: str, temperature: float):
    async with sem:
        content = await llm_json.chat_json(
            client,
            os.getenv("LLM_MODEL", "qwen2.5:7b-instruct"),
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature,
        )
        return json.loads(content)


def _probability(value) -> float | None:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1
    return float(value) if ok else None


async def _twin_answer(client, sem, twin, question: str, references=None):
    """Ответ двойника: (1 или 0, названная вероятность «да» или None); в режиме SSR — (доля «скорее да/да», None)."""
    user = f"Ты: {twin.profile()}\n\nВопрос анкеты: {question}"
    try:
        if references is None:
            out = await _chat(client, sem, FACT_SYSTEM, user, 0.8)
            answer = out.get("answer") if isinstance(out, dict) else None
            if not isinstance(answer, bool):
                return None
            stated = _probability(out.get("probability"))
            if stated is None:
                return float(answer), None, False
            # Модели часто пишут уверенность в ответе вместо вероятности «да»: «нет» и 0,94.
            yes, flipped = engine.yes_probability_from(answer, stated)
            return float(answer), yes, flipped
        out = await _chat(client, sem, FACT_SSR_SYSTEM, user, 0.8)
        reply = out.get("reply") if isinstance(out, dict) else None
        if not isinstance(reply, str) or not reply.strip():
            return None
        model = ssr.embed_model()
        refs = await references.get(client, model)
        async with sem:
            (vector,) = await ssr.embed(client, model, [reply.strip()])
        return ssr.top_two(ssr.pmf(vector, refs)), None, False
    except Exception:
        return None


async def _baseline(client, sem, fact: dict) -> float | None:
    user = f"Аудитория: {_audience(fact['segments'])}.\nВопрос анкеты: {fact['question']}"
    try:
        out = await _chat(client, sem, SHARE_SYSTEM, user, 0)
    except Exception:
        return None
    share = out.get("share") if isinstance(out, dict) else None
    ok = isinstance(share, (int, float)) and not isinstance(share, bool) and 0 <= share <= 1
    return float(share) if ok else None


async def _run(facts: list[dict], n: int, concurrency: int, seed: int, use_ssr: bool = False) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    references = ssr.References(FACT_REFERENCES) if use_ssr else None
    rows = []
    async with engine._client() as client:
        for fact in facts:
            twins = build_population(n, fact["segments"], seed=seed)
            answers = await asyncio.gather(
                *(_twin_answer(client, sem, t, fact["question"], references) for t in twins)
            )
            valid = [a for a in answers if a is not None]
            baseline = await _baseline(client, sem, fact)
            twins_share = sum(a for a, _, _ in valid) / len(valid) if valid else None
            stated = [p for _, p, _ in valid if p is not None]
            flipped = sum(f for _, _, f in valid)
            # Средняя названная вероятность: учитывает неуверенность, которую ответ «да/нет» теряет.
            twins_prob = sum(stated) / len(stated) if valid and len(stated) == len(valid) else None
            rows.append(
                {
                    "id": fact["id"],
                    "question": fact["question"],
                    "truth": fact["share"],
                    "twins": twins_share,
                    "twins_prob": twins_prob,
                    "flipped": flipped,
                    "baseline": baseline,
                    "valid": len(valid),
                    "requested": len(twins),
                    "used_for_profiles": fact.get("used_for_profiles", False),
                    "source": fact["source"],
                    "url": fact["url"],
                }
            )
    return rows


def _mae(rows: list[dict], key: str) -> float | None:
    errors = [abs(r[key] - r["truth"]) for r in rows if r.get(key) is not None]
    return sum(errors) / len(errors) * 100 if errors else None


def _primary(rows: list[dict]) -> str:
    """Основная оценка двойников: названная вероятность, если она есть у всех фактов."""
    return "twins_prob" if rows and all(r.get("twins_prob") is not None for r in rows) else "twins"


def paired_gap(rows: list[dict], key: str, other: str, draws: int = 4000, seed: int = 7) -> dict | None:
    """Разница средних ошибок (key минус other, п.п.) и 95% бутстреп-интервал по фактам.

    Факты пересэмплируются с возвращением, пары ошибок сохраняются. Интервал, включающий 0,
    значит: на таком числе фактов разница не отличима от шума.
    """
    pairs = [
        abs(r[key] - r["truth"]) - abs(r[other] - r["truth"])
        for r in rows
        if r.get(key) is not None and r.get(other) is not None
    ]
    if len(pairs) < 3:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(pairs) for _ in pairs) / len(pairs) for _ in range(draws))
    low, high = means[int(0.025 * draws)], means[int(0.975 * draws) - 1]
    return {"gap": sum(pairs) / len(pairs) * 100, "ci": [low * 100, high * 100], "facts": len(pairs)}


def summarize(rows: list[dict]) -> dict:
    independent = [r for r in rows if not r["used_for_profiles"]]
    naive = [{**r, "naive": 0.5} for r in rows]
    primary = _primary(rows)
    return {
        "flipped": sum(r.get("flipped", 0) for r in rows),
        "primary": primary,
        "vs_baseline": paired_gap(rows, primary, "baseline"),
        "vs_naive": paired_gap(naive, primary, "naive"),
        "twins_mae": _mae(rows, "twins"),
        "twins_prob_mae": _mae(rows, "twins_prob"),
        "baseline_mae": _mae(rows, "baseline"),
        "naive_mae": _mae(naive, "naive"),
        "independent_twins_mae": _mae(independent, "twins"),
        "independent_twins_prob_mae": _mae(independent, "twins_prob"),
        "independent_baseline_mae": _mae(independent, "baseline"),
        "facts": len(rows),
        "independent": len(independent),
        "coverage": sum(r["valid"] for r in rows) / max(1, sum(r["requested"] for r in rows)),
    }


def _pp(value) -> str:
    return "—" if value is None else f"{value:.1f}".replace(".", ",") + " п.п."


def _pct(value) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _gap_line(name: str, gap: dict | None) -> str | None:
    if not gap:
        return None
    low, high = gap["ci"]
    verdict = (
        "интервал включает 0: разница не отличима от шума"
        if low <= 0 <= high
        else ("двойники точнее" if high < 0 else "двойники хуже")
    )
    fmt = lambda v: f"{v:+.1f}".replace(".", ",")  # noqa: E731
    return f"- против {name}: {fmt(gap['gap'])} п.п., 95% интервал [{fmt(low)}; {fmt(high)}] — {verdict}."


def _gap_lines(summary: dict) -> list[str]:
    gaps = [("простого подхода", summary.get("vs_baseline")), ("наивных 50%", summary.get("vs_naive"))]
    lines = [_gap_line(name, gap) for name, gap in gaps if gap]
    if not lines:
        return []
    facts = next(gap["facts"] for _, gap in gaps if gap)
    label = "по вероятности" if summary.get("primary") == "twins_prob" else "по ответам"
    return [
        f"Разница ошибок двойников ({label}), минус — двойники точнее; бутстреп по {facts} фактам:",
        *lines,
        "",
    ]


def format_report(rows: list[dict], summary: dict, model: str) -> str:
    prob = summary.get("twins_prob_mae") is not None
    twins_head = "Двойники, да/нет | Двойники, вероятность" if prob else "Двойники"
    head = f"| Факт | Опубликовано | {twins_head} | Простой подход |"
    lines = [
        f"# Бенчмарк на открытых данных · {model}",
        "",
        f"Фактов: {summary['facts']}, из них независимых от профилей: {summary['independent']}. "
        f"Покрытие ответов: {summary['coverage']:.0%}."
        + (
            f" Вероятность противоречила ответу и прочитана как уверенность: {summary['flipped']} ответов."
            if summary.get("flipped")
            else ""
        ),
        "",
        head,
        "|" + " --- |" * (head.count("|") - 1),
    ]
    for r in rows:
        mark = " *" if r["used_for_profiles"] else ""
        twins = f"{_pct(r['twins'])} | {_pct(r.get('twins_prob'))}" if prob else _pct(r["twins"])
        lines.append(
            f"| [{r['question']}]({r['url']}){mark} | {_pct(r['truth'])} | {twins} | {_pct(r['baseline'])} |"
        )
    lines += [
        "",
        f"Средняя ошибка: двойники {_pp(summary['twins_mae'])}"
        + (f", двойники по вероятности {_pp(summary['twins_prob_mae'])}" if prob else "")
        + f", простой подход {_pp(summary['baseline_mae'])}, наивные 50% {_pp(summary['naive_mae'])}",
        f"Без фактов, использованных при составлении профилей: двойники {_pp(summary['independent_twins_mae'])}"
        + (f", по вероятности {_pp(summary['independent_twins_prob_mae'])}" if prob else "")
        + f", простой подход {_pp(summary['independent_baseline_mae'])}",
        "",
        *_gap_lines(summary),
        "\\* факт был ориентиром при составлении профиля сегмента, поэтому проверка по нему не независимая.",
        "Источники разных лет и методов: это ориентир для сравнения подходов, а не точность прогноза спроса.",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Бенчмарк Двойника на открытых данных")
    parser.add_argument("--n", type=int, default=30, help="двойников на факт")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--facts", type=Path, default=FACTS)
    parser.add_argument("--output", type=Path, help="сохранить отчёт в Markdown")
    parser.add_argument(
        "--ssr", action="store_true", help="ответ фразой и оценка по эмбеддингам (LLM_EMBED_MODEL)"
    )
    args = parser.parse_args(argv)
    if args.n < 5:
        parser.exit(2, "Нужно хотя бы 5 двойников на факт.\n")
    started = time.perf_counter()
    rows = asyncio.run(_run(load_facts(args.facts), args.n, args.concurrency, args.seed, args.ssr))
    summary = summarize(rows)
    model = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct") + (
        f" · SSR ({ssr.embed_model()})" if args.ssr else ""
    )
    report = format_report(rows, summary, model)
    print(report)
    print(f"\n{time.perf_counter() - started:.0f} с")
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    if summary["coverage"] < 0.9:
        parser.exit(1, "\nПокрытие ниже 90%: проверьте модель и формат JSON.\n")


if __name__ == "__main__":
    main()
