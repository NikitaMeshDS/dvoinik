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


def test_optional_cache_reuses_validated_answers(monkeypatch, tmp_path):
    monkeypatch.setenv("DVOINIK_LLM_CACHE", "1")
    monkeypatch.setenv("DVOINIK_LLM_CACHE_PATH", str(tmp_path / "cache.sqlite3"))
    calls = []

    def respond(request):
        calls.append(request)
        answer = {"decision": True, "probability": 0.7, "objection": None, "quote": "Да"}
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
                        "message": {"role": "assistant", "content": json.dumps(answer)},
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
    scenario = {
        "description": "",
        "question": "Да?",
        "variants": {"A": "x", "B": "y"},
        "objections": ["плата"],
    }
    twins = build_population(3, {"senior": 1})
    first = engine.simulate(twins, scenario)
    assert len(calls) == 6
    second = engine.simulate(twins, scenario)
    assert len(calls) == 6 and second["A"]["yes"] == first["A"]["yes"] == 3
    changed = {**scenario, "variants": {"A": "x", "B": "новое"}}
    engine.simulate(twins, changed)
    assert len(calls) == 9


def test_llm_check_reports_coverage_baseline_and_homogeneity(monkeypatch, tmp_path, capsys):
    import llm_check

    def respond(request):
        payload = json.loads(request.content)
        if "Перефразируй" in payload["messages"][0]["content"]:
            content = json.dumps({"variants": {v: "иначе " + v for v in "ABC"}})
        elif "Не моделируй отдельных людей" in payload["messages"][0]["content"]:
            variants = [
                line.split(":")[0].split()[-1] for line in payload["messages"][1]["content"].splitlines()
            ]
            content = json.dumps({"rates": {v: 0.5 for v in variants if len(v) == 1}})
        else:
            content = json.dumps({"decision": True, "probability": 1.0, "objection": None, "quote": "Да"})
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
    report = tmp_path / "check.md"
    llm_check.main(["--scenario", "senior_deposit", "--n", "5", "--paraphrase", "--output", str(report)])
    text = report.read_text(encoding="utf-8")
    assert "Покрытие: 100%" in text
    assert "однородные ответы" in text
    assert "Простой подход" in text
    assert "Перефразировка" in text and "лидер тот же" in text and "иначе A" in text


def test_decision_follows_stated_probability_and_unknown_objection_is_kept(monkeypatch):
    """Конверсия — по названной вероятности, цитата — по сказанному, причина «своими словами» — «другое»."""

    def respond(request):
        user = json.loads(request.content)["messages"][1]["content"]
        if "accept-offer" in user:
            answer = {"decision": True, "probability": 0.3, "objection": None, "quote": "Пожалуй, да."}
        else:
            answer = {"decision": False, "probability": 0.0, "objection": "дорого и скучно", "quote": "Нет."}
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
                        "message": {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
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
    scenario = {
        "description": "Проверка",
        "question": "Подключите?",
        "variants": {"A": "accept-offer", "B": "decline-offer"},
        "objections": ["плата", "не доверяю"],
    }
    report = engine.simulate(build_population(200, {"student_msk": 1}), scenario)
    # Все сказали «да», но с вероятностью 0,3: конверсия около 30%, а не 100%.
    assert report["A"]["failed_n"] == 0 and 0.2 < report["A"]["conversion"] < 0.4
    assert all(q["decision"] for q in report["A"]["quotes"])
    # Причина своими словами не теряет ответ, а попадает в «другое».
    assert report["B"]["failed_n"] == 0 and report["B"]["conversion"] == 0
    assert report["B"]["objections"] == {engine.OTHER_OBJECTION: 200}
    # Отчёт с причиной «другое» сохраняется и загружается.
    from dvoinik.experiments import load_experiment
    from dvoinik.reporting import make_record

    twins = build_population(200, {"student_msk": 1})
    full = {**scenario, "title": "Подписка", "population": {"student_msk": 1}}
    record = make_record("custom", full, 200, False, 0, report, twins)
    assert load_experiment(json.dumps(record))["report"]["B"]["objections"] == {"другое": 200}
