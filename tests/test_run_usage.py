import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from dvoinik import engine, llm_json, ssr
from dvoinik.experiments import load_experiment
from dvoinik.reporting import export_json
from dvoinik.run_journal import journal_entry
from dvoinik.run_usage import collect_usage, measure_call
from dvoinik.runs import RunSettings, run_experiment
from dvoinik.scenarios import SCENARIOS


def test_sdk_format_retry_and_embedding_usage_share_one_meter(monkeypatch):
    class FormatError(Exception):
        status_code = 400

    async def chat(**options):
        if "response_format" in options:
            raise FormatError("response_format")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    async def embed(**options):
        return SimpleNamespace(
            usage=SimpleNamespace(total_tokens=12),
            data=[SimpleNamespace(index=0, embedding=[0.5])],
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat)),
        embeddings=SimpleNamespace(create=embed),
    )
    monkeypatch.setenv("LLM_JSON_MODE", "auto")
    monkeypatch.setattr(llm_json, "_STATE", {"text": None})
    with collect_usage() as usage:
        assert asyncio.run(llm_json.chat_json(client, "test", [], 0)) == "{}"
        assert usage.snapshot(1)["reported_tokens"] is None
        assert asyncio.run(ssr.embed(client, "test", ["text"])) == [[0.5]]
    assert usage.snapshot(1) == {
        "sdk_calls": 3,
        "calls_with_usage": 1,
        "reported_tokens": 12,
        "cache_hits": 0,
        "concurrency": 1,
    }


def test_parallel_runs_have_independent_usage():
    def run(amount):
        async def response():
            await asyncio.sleep(0)
            return SimpleNamespace(usage=SimpleNamespace(total_tokens=amount))

        async def parallel():
            await asyncio.gather(*(measure_call(response()) for _ in range(3)))

        with collect_usage() as usage:
            asyncio.run(parallel())
        return usage.reported_tokens

    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(run, [1, 7])) == [3, 21]


def test_cache_and_baseline_accounted_across_runs(monkeypatch, tmp_path):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def client():
        async def create(**options):
            baseline = "Не моделируй отдельных людей" in options["messages"][0]["content"]
            content = (
                '{"rates":{"A":0,"B":0,"C":0}}'
                if baseline
                else '{"decision":true,"probability":1,"objection":"плата","quote":"Да"}'
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                usage=SimpleNamespace(total_tokens=8),
            )

        yield SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr(engine, "_client", client)
    monkeypatch.setenv("DVOINIK_ELICITATION", "probability")
    monkeypatch.setenv("DVOINIK_LLM_CACHE", "1")
    monkeypatch.setenv("DVOINIK_LLM_CACHE_PATH", str(tmp_path / "cache"))
    for cached in (False, True):
        record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=2, mock=False))
        entry = journal_entry(load_experiment(export_json(record)))
        calls = 1 if cached else 7
        assert entry["sdk_calls"] == entry["calls_with_usage"] == calls
        assert entry["reported_tokens"] == calls * 8
        assert entry["cache_hits"] == (6 if cached else 0)
        assert entry["valid_answers"] == 6 and entry["failed_answers"] == 0 and entry["baseline_ok"]


def test_legacy_and_demo_usage_and_import_validation():
    record = run_experiment("student_card", SCENARIOS["student_card"], RunSettings(n=2))
    assert journal_entry(load_experiment(export_json(record)))["reported_tokens"] == 0
    usage = record.pop("run_usage")
    assert journal_entry(load_experiment(export_json(record)))["reported_tokens"] is None
    for bad in ({"sdk_calls": 1}, {"cache_hits": True}, {"calls_with_usage": 1}, {"reported_tokens": 10}):
        record["run_usage"] = {**usage, **bad}
        with pytest.raises(ValueError):
            load_experiment(export_json(record))
