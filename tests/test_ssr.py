import json

import httpx
import pytest
from openai import AsyncOpenAI

from dvoinik import engine, ssr
from dvoinik.experiments import load_experiment
from dvoinik.population import build_population
from dvoinik.reporting import make_record
from dvoinik.settings import model_identity


def one_hot(i, size=5):
    return [1.0 if j == i else 0.0 for j in range(size)]


def test_pmf_follows_the_closest_reference_and_sums_to_one():
    refs = [[one_hot(i) for i in range(5)], [one_hot(i) for i in range(5)]]
    yes = ssr.pmf(one_hot(4), refs)
    no = ssr.pmf(one_hot(0), refs)
    unsure = ssr.pmf([0, 0.5, 1, 0.5, 0], refs)
    assert sum(yes) == pytest.approx(1, abs=1e-5) and max(yes) == yes[4]
    assert ssr.top_two(yes) > 0.9 and ssr.top_two(no) < 0.05
    assert max(unsure) == unsure[2] and 0.1 < ssr.top_two(unsure) < 0.6
    with pytest.raises(ValueError):
        ssr.pmf(one_hot(0), [])
    with pytest.raises(ValueError):
        ssr.cosine([0, 0], [1, 0])


def test_draw_is_deterministic_and_follows_probability():
    assert ssr.draw(0.5, 1, "senior", "text") == ssr.draw(0.5, 1, "senior", "text")
    share = sum(ssr.draw(0.3, i, "x") for i in range(4000)) / 4000
    assert share == pytest.approx(0.3, abs=0.03)
    assert not ssr.draw(0.0, 1) and ssr.draw(1.0, 1)


def test_mode_and_model_identity(monkeypatch):
    monkeypatch.delenv("DVOINIK_ELICITATION", raising=False)
    assert ssr.mode() == "probability"
    monkeypatch.setenv("DVOINIK_ELICITATION", "SSR")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b-instruct")
    monkeypatch.setenv("LLM_EMBED_MODEL", "bge-m3")
    assert ssr.mode() == "ssr"
    name, config = model_identity(False)
    assert name == "qwen2.5:7b-instruct · SSR" and config.endswith("|ssr:bge-m3")
    assert model_identity(True) == ("Эвристика", None)
    monkeypatch.setenv("DVOINIK_ELICITATION", "votes")
    with pytest.raises(ValueError):
        ssr.mode()


def fake_llm(monkeypatch, reaction_for, bad_embeddings=False):
    seen = {"chat": [], "embeddings": 0}
    references = {text: i for ref in ssr.REFERENCE_SETS for i, text in enumerate(ref)}

    def vector(text):
        if text in references:
            return one_hot(references[text])
        return one_hot(4) if "оформлю" in text else one_hot(0)

    def respond(request):
        payload = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            seen["embeddings"] += 1
            data = (
                []
                if bad_embeddings
                else [
                    {"object": "embedding", "index": i, "embedding": vector(t)}
                    for i, t in enumerate(payload["input"])
                ]
            )
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": data,
                    "model": "e",
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                },
            )
        seen["chat"].append(payload["messages"])
        user = payload["messages"][1]["content"]
        content = json.dumps(reaction_for(user))
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
    monkeypatch.setenv("DVOINIK_ELICITATION", "ssr")
    monkeypatch.setenv("LLM_EMBED_MODEL", "bge-m3")
    return seen


SCENARIO = {
    "title": "Подписка",
    "description": "Проверка подписки",
    "question": "Подключите?",
    "variants": {"A": "accept-offer", "B": "decline-offer"},
    "objections": ["плата", "не доверяю"],
    "population": {"senior": 1},
}


def reaction(user):
    if "accept-offer" in user:
        return {"reaction": "Да, точно оформлю, мне подходит.", "objection": "плата"}
    return {"reaction": "Нет, мне это не нужно.", "objection": "Не доверяю."}


def test_ssr_run_rates_by_meaning_and_records_the_scale(monkeypatch):
    seen = fake_llm(monkeypatch, reaction)
    twins = build_population(20, {"senior": 1})
    report = engine.simulate(twins, SCENARIO)
    assert "Скажи одной-двумя фразами" in seen["chat"][0][0]["content"]
    assert report["A"]["conversion"] > 0.85 and report["B"]["conversion"] < 0.15
    assert report["A"]["likert"][4] > 0.9 and report["B"]["likert"][0] > 0.9
    assert report["B"]["objections"] == {"не доверяю": report["B"]["n"] - report["B"]["yes"]}
    assert report["A"]["probability"]["n"] == 20
    assert report["A"]["quotes"][0]["quote"].startswith("Да, точно оформлю")
    # Эталоны считаются один раз на запуск, ответы — по одному запросу на ответ.
    assert seen["embeddings"] == 1 + 40
    record = make_record("custom", SCENARIO, 20, False, 0, report, twins)
    assert record["model"].endswith("· SSR")
    loaded = load_experiment(json.dumps(record))
    assert loaded["report"]["A"]["likert"] == report["A"]["likert"]


def test_ssr_reports_bad_answers_and_embedding_failures_as_model_errors(monkeypatch):
    fake_llm(monkeypatch, lambda user: {"reaction": "", "objection": "плата"})
    report = engine.simulate(build_population(3, {"senior": 1}), SCENARIO)
    assert report["A"]["n"] == 0 and report["A"]["failed_n"] == 3
    assert report["A"]["failure_examples"] == [
        "Модель вернула ответ, не соответствующий JSON-схеме: reaction должна содержать ответ клиента."
    ]
    fake_llm(monkeypatch, reaction, bad_embeddings=True)
    report = engine.simulate(build_population(3, {"senior": 1}), SCENARIO)
    assert report["A"]["failed_n"] == 3 and "likert" not in report["A"]


def test_snapshot_rejects_broken_scale():
    from dvoinik.runs import RunSettings, run_experiment
    from dvoinik.scenarios import SCENARIOS

    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=20))
    record["report"]["A"]["likert"] = [0.5, 0.5, 0.5, 0, 0]
    with pytest.raises(ValueError, match="1–5"):
        load_experiment(json.dumps(record))
    record["report"]["A"]["likert"] = [0.2, 0.2, 0.2, 0.2]
    with pytest.raises(ValueError):
        load_experiment(json.dumps(record))


def test_llm_check_and_estimate_show_ssr(monkeypatch, tmp_path):
    import llm_check
    from dvoinik.planning import run_estimate
    from dvoinik.scenarios import SCENARIOS

    fake_llm(monkeypatch, lambda user: {"reaction": "Да, оформлю.", "objection": "не доверяю"})
    out = tmp_path / "check.md"
    llm_check.main(["--scenario", "senior_deposit", "--n", "4", "--output", str(out)])
    text = out.read_text(encoding="utf-8")
    assert "Шкала 1–5 (SSR)" in text and "Покрытие: 100%" in text
    estimate = run_estimate(SCENARIOS["senior_deposit"], 10)
    assert "Режим SSR: плюс короткие запросы" in estimate["detail"]
