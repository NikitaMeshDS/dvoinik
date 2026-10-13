import json

import httpx
import pytest
from openai import AsyncOpenAI

from dvoinik import engine
from dvoinik.population import build_population


def test_openai_compatible_protocol_and_client_lifecycle(monkeypatch):
    messages = []

    def respond(request):
        payload = json.loads(request.content)
        messages.append(payload["messages"][1]["content"])
        accept = "accept-offer" in payload["messages"][1]["content"]
        answer = {
            "decision": accept,
            "probability": 0.8 if accept else 0.1,
            "objection": None if accept else "плата",
            "quote": "Решение клиента",
        }
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(answer)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
        )

    clients = []

    def client_factory():
        client = AsyncOpenAI(
            api_key="local-test",
            base_url="http://local-test/v1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(engine, "_client", client_factory)
    scenario = {
        "description": "Контекст: клиент изучает новую банковскую подписку",
        "question": "Подключите?",
        "variants": {"A": "accept-offer", "B": "decline-offer"},
        "objections": ["плата"],
    }
    report = engine.simulate(build_population(4, {"senior": 1}), scenario)
    assert report["A"]["conversion"] == 1
    assert report["B"]["conversion"] == 0
    assert report["B"]["objections"] == {"плата": 4}
    assert clients[0].is_closed()
    assert all(scenario["description"] in message for message in messages)
    # Повторный запуск не переиспользует закрытый клиент или event loop.
    assert engine.simulate(build_population(4, {"senior": 1}), scenario)["A"]["n"] == 4


def test_missing_model_fails_before_launching_whole_population(monkeypatch):
    requests = []

    def missing(request):
        requests.append(request)
        return httpx.Response(404, json={"error": {"message": "model missing", "type": "not_found"}})

    monkeypatch.setattr(
        engine,
        "_client",
        lambda: AsyncOpenAI(
            api_key="test",
            base_url="http://test/v1",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(missing)),
        ),
    )
    scenario = {"question": "Подключите?", "variants": {"A": "a", "B": "b"}, "objections": ["плата"]}
    with pytest.raises(ValueError, match="LLM"):
        engine.simulate(build_population(100, {"senior": 1}), scenario)
    assert len(requests) == 1
