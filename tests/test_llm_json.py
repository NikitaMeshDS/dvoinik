import asyncio
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


def test_no_think_switch_and_auto_enable_for_qwen3(monkeypatch):
    import proof

    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    monkeypatch.delenv("LLM_NO_THINK", raising=False)
    assert llm_json._no_think(messages) is messages
    monkeypatch.setenv("LLM_NO_THINK", "1")
    patched = llm_json._no_think(messages)
    assert patched[-1]["content"] == "u\n/no_think" and messages[-1]["content"] == "u"
    assert proof.planned_requests(True, False) < proof.planned_requests(False, True)


def test_tune_thinking_finds_the_switch_and_chat_json_sends_it(monkeypatch):
    import http.server
    import threading

    import proof

    bodies = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            bodies.append(body)
            off = body.get("chat_template_kwargs", {}).get("enable_thinking") is False
            message = {"role": "assistant", "content": '{"ok": true}'}
            if not off:
                message["reasoning_content"] = "думаю " * 50
            payload = json.dumps(
                {
                    "id": "t",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "m",
                    "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        found = proof.tune_thinking(base, "qwen/qwen3.5-9b")
        assert found == {"chat_template_kwargs": {"enable_thinking": False}}
        monkeypatch.setenv("LLM_EXTRA_BODY", json.dumps(found))
        monkeypatch.setenv("LLM_JSON_MODE", "json_object")
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key="k", base_url=base)
        text = asyncio.run(llm_json.chat_json(client, "m", [{"role": "user", "content": "x"}], 0))
        assert json.loads(text) == {"ok": True}
        assert bodies[-1]["chat_template_kwargs"] == {"enable_thinking": False}
    finally:
        server.shutdown()
    monkeypatch.setenv("LLM_EXTRA_BODY", "[1]")
    with pytest.raises(ValueError):
        llm_json.extra_body()
