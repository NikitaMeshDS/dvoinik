"""Все замеры на подключённой модели одной командой: бенчмарк, SSR и проверка протокола.

Находит сервер (LM Studio на :1234 или Ollama на :11434), выбирает загруженные модели
и складывает отчёты в proof/latest: benchmark.md, benchmark_ssr.md, llm_check.md и summary.json.

    python proof.py            # около 15–25 минут на 7B-модели
    python proof.py --quick    # около 5–10 минут, меньше двойников
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import time
import urllib.request
from datetime import datetime
from pathlib import Path

CANDIDATES = ["http://localhost:1234/v1", "http://localhost:11434/v1"]
EMBED_HINTS = ("embed", "bge", "e5", "gte", "nomic", "minilm")


def _models(base: str) -> list[str] | None:
    try:
        with urllib.request.urlopen(base + "/models", timeout=3) as response:
            return [m["id"] for m in json.load(response).get("data", [])]
    except Exception:
        return None


def discover() -> tuple[str, str, str | None]:
    base = os.getenv("LLM_BASE_URL")
    bases = [base] if base else CANDIDATES
    for url in bases:
        ids = _models(url)
        if ids is None:
            continue
        embeds = [i for i in ids if any(h in i.lower() for h in EMBED_HINTS)]
        chats = [i for i in ids if i not in embeds]
        chat = os.getenv("LLM_MODEL") or (chats[0] if chats else None)
        embed = os.getenv("LLM_EMBED_MODEL") or (embeds[0] if embeds else None)
        if not chat:
            raise SystemExit(f"На {url} нет загруженной чат-модели. Загрузите её в LM Studio и повторите.")
        return url, chat, embed
    raise SystemExit(
        "Не нашёл сервер модели. В LM Studio: Developer → Start Server (порт 1234) и загрузите модель."
    )


async def _ping() -> float:
    from dvoinik import engine, llm_json

    started = time.perf_counter()
    async with engine._client() as client:
        text = await llm_json.chat_json(
            client,
            os.environ["LLM_MODEL"],
            [
                {"role": "system", "content": 'Ответь строго JSON: {"ok": true}'},
                {"role": "user", "content": "Проверка"},
            ],
            0,
        )
    if json.loads(text).get("ok") is not True:
        raise SystemExit(f"Модель отвечает не по формату: {text[:200]}")
    return time.perf_counter() - started


def planned_requests(quick: bool, ssr: bool) -> int:
    """Грубая оценка числа запросов к чат-модели для всех шагов."""
    facts, n_bench, n_check = 7, (15 if quick else 30), (10 if quick else 20)
    bench = facts * (n_bench + 1)
    check = 3 * n_check + 1 if quick else 2 * 2 * (3 * n_check + 1) + 2
    return bench * (2 if ssr else 1) + check + ((3 * n_check + 1) if ssr else 0)


def _step(name: str, action, log: list) -> dict:
    print(f"\n=== {name}", flush=True)
    started = time.perf_counter()
    try:
        result = action() or {}
        status = "ok"
    except SystemExit as exc:
        result, status = {}, f"exit {exc.code}"
    except Exception as exc:  # шаг не должен останавливать остальные замеры
        result, status = {}, f"{type(exc).__name__}: {exc}"
    seconds = round(time.perf_counter() - started)
    log.append({"step": name, "status": status, "seconds": seconds, **result})
    print(f"--- {name}: {status}, {seconds} с", flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Замеры Двойника на подключённой модели")
    parser.add_argument("--quick", action="store_true", help="меньше двойников и без перефразировки")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("proof") / "latest")
    args = parser.parse_args(argv)

    base, chat, embed = discover()
    os.environ.update(
        {"LLM_BASE_URL": base, "LLM_MODEL": chat, "LLM_API_KEY": os.getenv("LLM_API_KEY", "local")}
    )
    if embed:
        os.environ["LLM_EMBED_MODEL"] = embed
    if os.getenv("LLM_NO_THINK") is None and "qwen3" in chat.lower().replace(".", ""):
        os.environ["LLM_NO_THINK"] = "1"
    print(f"Сервер: {base}\nМодель: {chat}\nЭмбеддинги: {embed or 'нет — шаги SSR пропускаю'}")
    if os.getenv("LLM_NO_THINK") == "1":
        print("Рассуждения модели отключены (/no_think): для коротких JSON-ответов они не нужны.")
    latency = asyncio.run(_ping())
    requests = planned_requests(args.quick, bool(embed))
    minutes = requests * latency / max(1, args.concurrency) / 60
    print(f"Один запрос: {latency:.1f} с · запросов около {requests} · ожидаемо {minutes:.0f} мин")
    if latency > 8:
        print(
            "Запросы медленные. Если модель рассуждает, отключите это в настройках LM Studio "
            "или возьмите instruct-модель; для короткого прогона — python proof.py --quick."
        )

    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    n_bench, n_check = (15, 10) if args.quick else (30, 20)
    conc = str(args.concurrency)
    log: list[dict] = []

    import benchmark
    import llm_check
    from dvoinik import llm_json

    def bench(ssr: bool):
        os.environ.pop("DVOINIK_ELICITATION", None)
        rows = asyncio.run(benchmark._run(benchmark.load_facts(), n_bench, args.concurrency, 42, use_ssr=ssr))
        summary = benchmark.summarize(rows)
        name = chat + (f" · SSR ({embed})" if ssr else "")
        (out / ("benchmark_ssr.md" if ssr else "benchmark.md")).write_text(
            benchmark.format_report(rows, summary, name) + "\n", encoding="utf-8"
        )
        print(benchmark.format_report(rows, summary, name))
        return {"summary": summary}

    def check(ssr: bool):
        if ssr:
            os.environ["DVOINIK_ELICITATION"] = "ssr"
        else:
            os.environ.pop("DVOINIK_ELICITATION", None)
        target = out / ("llm_check_ssr.md" if ssr else "llm_check.md")
        argv = [
            "--scenario",
            "senior_deposit",
            "--n",
            str(n_check),
            "--concurrency",
            conc,
            "--output",
            str(target),
        ]
        if not ssr and not args.quick:
            argv += ["--scenario", "student_card", "--paraphrase"]
        llm_check.main(argv)
        return {"report": target.name}

    _step("Бенчмарк на открытых данных", lambda: bench(False), log)
    if embed:
        _step("Бенчмарк в режиме SSR", lambda: bench(True), log)
    _step("Проверка протокола и перефразировки", lambda: check(False), log)
    if embed:
        _step("Проверка протокола в режиме SSR", lambda: check(True), log)

    summary = {
        "when": datetime.now().isoformat(timespec="seconds"),
        "base_url": base,
        "model": chat,
        "embed_model": embed,
        "json_mode": "text" if llm_json._STATE["text"] else llm_json.mode(),
        "latency_s": round(latency, 2),
        "quick": args.quick,
        "steps": log,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nГотово: {out}")


if __name__ == "__main__":
    main()
