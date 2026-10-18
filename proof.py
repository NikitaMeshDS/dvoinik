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
import re
import shutil
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

CANDIDATES = ["http://localhost:1234/v1", "http://localhost:11434/v1"]
EMBED_HINTS = ("embed", "bge", "e5", "gte", "nomic", "minilm")
MULTILINGUAL_HINTS = ("bge-m3", "multilingual", "labse", "qwen3-embedding", "gte-multilingual")
SSR_MIN_SEPARATION = 0.3


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
        # Многоязычные модели понимают русский; англоязычные (nomic, minilm) — плохо.
        embeds.sort(key=lambda i: not any(h in i.lower() for h in MULTILINGUAL_HINTS))
        chats = [i for i in ids if i not in embeds]
        chat = os.getenv("LLM_MODEL") or (chats[0] if chats else None)
        embed = os.getenv("LLM_EMBED_MODEL") or (embeds[0] if embeds else None)
        if not chat:
            raise SystemExit(f"На {url} нет загруженной чат-модели. Загрузите её в LM Studio и повторите.")
        return url, chat, embed
    raise SystemExit(
        "Не нашёл сервер модели. В LM Studio: Developer → Start Server (порт 1234) и загрузите модель."
    )


# Способы отключить рассуждения у разных серверов и шаблонов; неизвестные поля обычно игнорируются.
THINK_OFF = [
    {"chat_template_kwargs": {"enable_thinking": False}},
    {"reasoning_effort": "none"},
    {"reasoning": {"effort": "none"}},
    {"enable_thinking": False},
]


def _probe(base: str, model: str, extra: dict) -> tuple[float, int, bool]:
    """Один короткий запрос: время, длина рассуждения и успех."""
    body = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": 'Ответь строго JSON {"ok": true}'}],
        **extra,
    }
    request = urllib.request.Request(
        base + "/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            message = json.load(response)["choices"][0]["message"]
    except Exception:
        return time.perf_counter() - started, 0, False
    content = message.get("content") or ""
    reasoning = len(message.get("reasoning_content") or message.get("reasoning") or "")
    reasoning += sum(len(m) for m in re.findall(r"<think>(.*?)</think>", content, re.S))
    return time.perf_counter() - started, reasoning, '"ok"' in content


def tune_thinking(base: str, model: str) -> dict | None:
    """Если модель рассуждает, подбирает поле запроса, которое это отключает."""
    seconds, reasoning, ok = _probe(base, model, {})
    print(f"Без настроек: {seconds:.1f} с, рассуждение {reasoning} символов")
    if ok and not reasoning:
        return None
    for extra in THINK_OFF:
        seconds, reasoning, ok = _probe(base, model, extra)
        print(f"{json.dumps(extra, ensure_ascii=False)}: {seconds:.1f} с, рассуждение {reasoning} символов")
        if ok and not reasoning:
            return extra
    return None


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
    # При выводе в tee Python копит вывод блоками; построчно видно, что прогон идёт.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    base, chat, embed = discover()
    os.environ.update(
        {"LLM_BASE_URL": base, "LLM_MODEL": chat, "LLM_API_KEY": os.getenv("LLM_API_KEY", "local")}
    )
    if embed:
        os.environ["LLM_EMBED_MODEL"] = embed
    print(f"Сервер: {base}\nМодель: {chat}\nЭмбеддинги: {embed or 'нет — шаги SSR пропускаю'}")
    if not os.getenv("LLM_EXTRA_BODY"):
        found = tune_thinking(base, chat)
        if found:
            os.environ["LLM_EXTRA_BODY"] = json.dumps(found)
            print(f"Рассуждения отключены полем {json.dumps(found, ensure_ascii=False)}.")
    latency = asyncio.run(_ping())
    requests = planned_requests(args.quick, bool(embed))
    # LM Studio обрабатывает запросы почти по одному, а промпты двойников длиннее пробного:
    # на qwen3.5-9b реальный запрос шёл примерно втрое дольше пробного.
    minutes = requests * latency * 3 / 60
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

    separation, embed_name = None, embed
    if embed:
        from dvoinik import engine, ssr

        async def _separation():
            async with engine._client() as client:
                return {
                    "offers": await ssr.separation(client, embed),
                    "survey": await ssr.separation(client, embed, benchmark.FACT_REFERENCES),
                }

        try:
            separation = asyncio.run(_separation())
        except Exception as exc:
            print(f"Проверка эмбеддингов не удалась ({type(exc).__name__}); шаги SSR пропускаю.")
            embed = None
    if separation:
        low = min(separation.values())
        print(f"Различение «да»/«нет» моделью эмбеддингов: {low:.2f} (норма — от {SSR_MIN_SEPARATION}).")
        if low < SSR_MIN_SEPARATION:
            print(
                "Модель эмбеддингов почти не различает русские ответы, оценки SSR сожмутся к середине. "
                "Загрузите многоязычную модель (bge-m3 или multilingual-e5) и повторите; шаги SSR пропускаю."
            )
            embed = None

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
        "embed_model": embed_name,
        "embed_separation": separation,
        "json_mode": "text" if llm_json._STATE["text"] else llm_json.mode(),
        "extra_body": os.getenv("LLM_EXTRA_BODY"),
        "latency_s": round(latency, 2),
        "quick": args.quick,
        "steps": log,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nГотово: {out}")


if __name__ == "__main__":
    main()
