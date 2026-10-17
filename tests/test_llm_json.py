import json

import httpx
import pytest
from openai import AsyncOpenAI

from dvoinik import engine, llm_json
from dvoinik.population import build_population
from dvoinik.scenarios import SCENARIOS


@pytest.fixture(autouse=True)
def fresh_state():
    llm_json.reset()
    yield
    llm_json.reset()


def lm_studio(monkeypatch, content):
    seen = []

    def respond(request):
        payload = json.loads(request.content)
        seen.append("response_format" in payload)
        if "response_format" in payload:
            return httpx.Response(
                400, json={"error": "'response_format.type' must be 'json_schema' or 'text'"}
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
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        ),
    )
    return seen


def test_extract_strips_reasoning_fences_and_chatter():
    raw = '<think>подумаю...</think>\n```json\n{"decision": true}\n```'
    assert llm_json.extract(raw) == '{"decision": true}'
    assert llm_json.extract('Ответ: {"a": {"b": 1}} готово') == '{"a": {"b": 1}}'
    assert llm_json.extract("без json") == "без json"
    with pytest.raises(ValueError):
        llm_json.extract(None)


def test_lm_studio_style_server_switches_to_text_once(monkeypatch):
    answer = {"decision": False, "probability": 0.2, "objection": "Не доверяю", "quote": "Нет."}
    seen = lm_studio(monkeypatch, "<think>...</think>" + json.dumps(answer, ensure_ascii=False))
    report = engine.simulate(build_population(4, {"senior": 1}), SCENARIOS["senior_deposit"], concurrency=1)
    assert report["A"]["n"] == 4 and report["A"]["failed_n"] == 0
    assert report["A"]["objections"] == {"не доверяю": 4}
    # Один отказ из-за response_format, дальше — только текстовые запросы.
    assert seen[0] is True and seen.count(True) == 1 and all(not s for s in seen[1:])


def test_explicit_modes(monkeypatch):
    seen = lm_studio(monkeypatch, '{"rates": {"A": 0.1, "B": 0.2, "C": 0.3}}')
    monkeypatch.setenv("LLM_JSON_MODE", "text")
    result = engine.baseline_estimate(SCENARIOS["senior_deposit"])
    assert result["rates"] == {"A": 0.1, "B": 0.2, "C": 0.3} and seen == [False]
    monkeypatch.setenv("LLM_JSON_MODE", "json_object")
    failed = engine.baseline_estimate(SCENARIOS["senior_deposit"])
    assert "error" in failed
    monkeypatch.setenv("LLM_JSON_MODE", "yaml")
    with pytest.raises(ValueError):
        llm_json.mode()
