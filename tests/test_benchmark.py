import json
import re

import httpx
import pytest
from openai import AsyncOpenAI

import benchmark
from dvoinik import engine


def fake(monkeypatch, broken=False):
    def respond(request):
        payload = json.loads(request.content)
        system, user = payload["messages"][0]["content"], payload["messages"][1]["content"]
        if broken:
            content = "not json"
        elif "Оцени, какая доля" in system:
            content = json.dumps({"share": 0.5})
        else:
            age = int(re.search(r", (\d+) лет", user).group(1))
            content = json.dumps({"answer": age < 60})
        return httpx.Response(
            200,
            json={
                "id": "t",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    monkeypatch.setattr(
        engine,
        "_client",
        lambda: AsyncOpenAI(
            api_key="k",
            base_url="http://local-test/v1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        ),
    )


def test_facts_are_sourced_and_valid():
    facts = benchmark.load_facts()
    assert len(facts) >= 7
    for fact in facts:
        assert fact["url"].startswith("https://") and fact["source"]
    assert {f["id"] for f in facts if f["used_for_profiles"]} == {"senior-mobile-bank", "senior-internet"}


def test_benchmark_compares_twins_baseline_and_naive(monkeypatch, tmp_path):
    fake(monkeypatch)
    out = tmp_path / "bench.md"
    benchmark.main(["--n", "10", "--output", str(out)])
    text = out.read_text(encoding="utf-8")
    assert "Покрытие ответов: 100%" in text
    rows = [line for line in text.splitlines() if line.startswith("| [")]
    assert len(rows) == 7 and rows[0].endswith("| 24% | 0% | 50% |")
    assert "* | 24%" in rows[0]
    assert "наивные 50%" in text and "Без фактов, использованных при составлении профилей" in text


def test_summary_math():
    rows = [
        {
            "truth": 0.2,
            "twins": 0.3,
            "baseline": 0.5,
            "used_for_profiles": True,
            "valid": 10,
            "requested": 10,
        },
        {
            "truth": 0.8,
            "twins": 0.6,
            "baseline": None,
            "used_for_profiles": False,
            "valid": 8,
            "requested": 10,
        },
    ]
    s = benchmark.summarize(rows)
    assert s["twins_mae"] == pytest.approx(15)
    assert s["baseline_mae"] == pytest.approx(30)
    assert s["naive_mae"] == pytest.approx(30)
    assert s["independent_twins_mae"] == pytest.approx(20) and s["independent_baseline_mae"] is None
    assert s["coverage"] == pytest.approx(0.9)


def test_bad_answers_fail_the_run(monkeypatch):
    fake(monkeypatch, broken=True)
    with pytest.raises(SystemExit) as exc:
        benchmark.main(["--n", "5"])
    assert exc.value.code == 1


def test_invalid_fact_file(tmp_path):
    bad = tmp_path / "facts.json"
    bad.write_text(
        json.dumps({"facts": [{"id": "x", "segments": {"alien": 1}, "question": "?", "share": 0.5}]})
    )
    with pytest.raises(ValueError):
        benchmark.load_facts(bad)


def test_benchmark_ssr_mode_uses_embeddings(monkeypatch, tmp_path):
    refs = {t: i for ref in benchmark.FACT_REFERENCES for i, t in enumerate(ref)}

    def respond(request):
        payload = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            data = [
                {
                    "object": "embedding",
                    "index": i,
                    "embedding": [1.0 if j == refs.get(t, 4 if "Да" in t else 0) else 0.0 for j in range(5)],
                }
                for i, t in enumerate(payload["input"])
            ]
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": data,
                    "model": "e",
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                },
            )
        system, user = payload["messages"][0]["content"], payload["messages"][1]["content"]
        if "Оцени, какая доля" in system:
            content = json.dumps({"share": 0.5})
        else:
            age = int(re.search(r", (\d+) лет", user).group(1))
            content = json.dumps(
                {"reply": "Да, у меня есть." if age < 60 else "Нет, у меня нет."}, ensure_ascii=False
            )
        return httpx.Response(
            200,
            json={
                "id": "t",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    monkeypatch.setattr(
        engine,
        "_client",
        lambda: AsyncOpenAI(
            api_key="k",
            base_url="http://local-test/v1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        ),
    )
    monkeypatch.setenv("LLM_EMBED_MODEL", "bge-m3")
    out = tmp_path / "ssr.md"
    benchmark.main(["--n", "5", "--ssr", "--output", str(out)])
    text = out.read_text(encoding="utf-8")
    assert "· SSR (bge-m3)" in text and "Покрытие ответов: 100%" in text
    rows = [line for line in text.splitlines() if line.startswith("| [")]
    truth, twins, base = [c.strip() for c in rows[0].split("|")[2:5]]
    assert truth == "24%" and base == "50%" and int(twins.rstrip("%")) <= 5
