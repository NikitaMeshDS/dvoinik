import json

import httpx
import pytest
from openai import AsyncOpenAI

import proof
from dvoinik import engine, llm_json


def content_for(system: str, user: str) -> dict:
    if '{"ok": true}' in system:
        return {"ok": True}
    if "Оцени, какая доля" in system:
        return {"share": 0.4}
    if '"answer"' in system:
        return {"answer": True}
    if '"reply"' in system:
        return {"reply": "Да, конечно."}
    if "Перефразируй" in system:
        variants = [line.split(":")[0] for line in user.splitlines()]
        return {"variants": {v: f"Другими словами {v}" for v in variants}}
    if "Не моделируй отдельных людей" in system:
        variants = [
            line.split(":")[0].split()[-1] for line in user.splitlines() if line.startswith("Предложение")
        ]
        return {"rates": {v: 0.5 for v in variants}}
    if '"reaction"' in system:
        return {"reaction": "Да, оформлю.", "objection": "не доверяю"}
    return {"decision": True, "probability": 0.7, "objection": None, "quote": "Да."}


@pytest.fixture
def server(monkeypatch):
    llm_json.reset()

    def respond(request):
        payload = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            data = [
                {"object": "embedding", "index": i, "embedding": [1.0, float(len(t) % 3), 0.5]}
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
        if "response_format" in payload:
            return httpx.Response(
                400, json={"error": "'response_format.type' must be 'json_schema' or 'text'"}
            )
        body = content_for(payload["messages"][0]["content"], payload["messages"][1]["content"])
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
                        "message": {
                            "role": "assistant",
                            "content": "<think>x</think>" + json.dumps(body, ensure_ascii=False),
                        },
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
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        ),
    )
    for name in ["LLM_BASE_URL", "LLM_MODEL", "LLM_EMBED_MODEL", "DVOINIK_ELICITATION"]:
        monkeypatch.delenv(name, raising=False)
    yield
    llm_json.reset()


def test_discover_prefers_lm_studio_and_splits_embedding_models(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_EMBED_MODEL", raising=False)
    answers = {
        "http://localhost:1234/v1": ["text-embedding-bge-m3", "qwen2.5-7b-instruct"],
        "http://localhost:11434/v1": ["llama"],
    }
    monkeypatch.setattr(proof, "_models", answers.get)
    assert proof.discover() == ("http://localhost:1234/v1", "qwen2.5-7b-instruct", "text-embedding-bge-m3")
    monkeypatch.setattr(proof, "_models", lambda url: None)
    with pytest.raises(SystemExit, match="Start Server"):
        proof.discover()
    monkeypatch.setattr(proof, "_models", lambda url: ["nomic-embed-text"])
    with pytest.raises(SystemExit, match="нет загруженной чат-модели"):
        proof.discover()


def test_quick_run_writes_all_reports(monkeypatch, tmp_path, server):
    monkeypatch.setattr(proof, "_models", lambda url: ["qwen2.5-7b-instruct", "text-embedding-bge-m3"])
    out = tmp_path / "latest"
    proof.main(["--quick", "--out", str(out)])
    files = {p.name for p in out.iterdir()}
    assert files == {"benchmark.md", "benchmark_ssr.md", "llm_check.md", "llm_check_ssr.md", "summary.json"}
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["model"] == "qwen2.5-7b-instruct" and summary["json_mode"] == "text"
    assert [s["status"] for s in summary["steps"]] == ["ok"] * 4
    bench = summary["steps"][0]["summary"]
    assert bench["coverage"] == 1 and bench["baseline_mae"] is not None
    assert "Покрытие: 100%" in (out / "llm_check.md").read_text(encoding="utf-8")
