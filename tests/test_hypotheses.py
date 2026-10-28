import copy
import json
from pathlib import Path

import httpx
import pytest
from openai import AsyncOpenAI

from dvoinik import engine
from dvoinik.hypotheses import LEVERS, MAX_HYPOTHESES, lever_for, rewrite, suggest
from dvoinik.runs import RunSettings, run_experiment
from dvoinik.scenarios import SCENARIOS
from dvoinik.summary import team_summary

SAMPLE = json.loads((Path(__file__).parents[1] / "examples" / "senior-deposit.demo.json").read_text())


@pytest.fixture(scope="module")
def records():
    return {k: run_experiment(k, SCENARIOS[k], RunSettings(n=200, mock=True, seed=42)) for k in SCENARIOS}


def test_every_template_objection_has_a_lever():
    for scenario in SCENARIOS.values():
        for objection in scenario["objections"]:
            assert lever_for(objection), objection
    assert lever_for("сложно договориться в семье")["id"] == "setup"
    assert lever_for("неудобный переход")["id"] == "switch"
    assert lever_for("неудобный канал")["id"] == "channel"
    assert lever_for("Высокая ставка")["id"] == "debt"
    assert lever_for("что-то своё") is None
    assert len({lever["id"] for lever in LEVERS}) == len(LEVERS)


def test_rewrite_edits_price_inside_sentence_or_drops_price_sentence():
    price = lever_for("плата")
    inline = rewrite("Семейная подписка 199 ₽/мес: общий счёт, детские карты бесплатно.", price)
    assert inline["proposal"].startswith("Семейная подписка без абонентской платы: общий счёт")
    assert inline["removed"] == ["199 ₽/мес"] and "Без скрытых платежей." in inline["added"]
    whole = rewrite("Кэшбэк 10% на такси. Обслуживание 99 ₽/мес, бесплатно при тратах от 5 000 ₽.", price)
    assert whole["proposal"] == "Кэшбэк 10% на такси. Без скрытых платежей."
    assert whole["removed"] == ["Обслуживание 99 ₽/мес, бесплатно при тратах от 5 000 ₽."]
    pushy = rewrite("Кэшбэк 5% на продукты, только сегодня!", lever_for("похоже на спам"))
    assert "только сегодня" not in pushy["proposal"] and pushy["removed"] == ["только сегодня"]
    again = rewrite(pushy["proposal"], lever_for("похоже на спам"))
    assert again["proposal"] is None


def test_suggestions_are_grounded_in_leader_objections(records):
    for key, record in records.items():
        result = suggest(record)
        leader = result["leader"]
        rates = {v: r["conversion"] for v, r in record["report"].items()}
        assert rates[leader] == max(rates.values())
        assert len(result["items"]) <= MAX_HYPOTHESES
        assert [h["id"] for h in result["items"]] == [f"h{i}" for i in range(1, len(result["items"]) + 1)]
        impacts = [h["audience_pp"] for h in result["items"]]
        assert impacts == sorted(impacts, reverse=True)
        for h in result["items"]:
            assert h["variant"] == leader and h["proposal"] != h["base_text"]
            assert len({h["lever_id"] for h in result["items"]}) == len(result["items"])
            if h["kind"] == "objection":
                counts = record["report"][leader]["segments"]
                for sid in h["segments"]:
                    assert set(h["objections"]) & set(counts[sid]["objections"])
                assert all(lever_for(o)["id"] == h["lever_id"] for o in h["objections"])
            assert h["ceiling_pp"] >= 5
    assert suggest(records["nonresident_transfer"])["items"] == []
    family = suggest(records["family_budget"])["items"][0]
    assert family["lever"] == "Цена" and "без абонентской платы" in family["proposal"]
    assert family["check_n"] and family["check_n"] > 30


def test_segment_offer_when_another_variant_wins_a_segment():
    record = copy.deepcopy(SAMPLE)
    report = record["report"]
    seg = report["B"]["segments"]["senior"]
    seg["yes"] = seg["n"] - 5
    seg["conversion"] = seg["yes"] / seg["n"]
    items = suggest(record)["items"]
    offer = next(h for h in items if h["kind"] == "segment_offer")
    assert offer["alternative"] == "B" and offer["segments"] == ["senior"]
    assert offer["proposal"] == record["scenario"]["variants"]["B"]
    assert offer == items[0]


def test_old_snapshots_without_segment_objections_use_overall_reasons():
    record = copy.deepcopy(SAMPLE)
    for variant in record["report"].values():
        for seg in variant["segments"].values():
            seg.pop("objections", None)
    items = suggest(record)["items"]
    assert items and items[0]["segments"] == [] and items[0]["segment_names"] == ["Вся аудитория"]


def test_empty_report_has_no_hypotheses():
    assert suggest({"report": {}}) == {"leader": None, "items": []}


def test_team_summary_lists_hypotheses():
    html = team_summary(SAMPLE)
    assert "Гипотезы: что поменять в предложении" in html
    assert "Надбавка к ставке за ежемесячное пополнение." in html
    assert "<script" not in html


def _llm(monkeypatch, content):
    seen = []

    def respond(request):
        seen.append(json.loads(request.content))
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
    return seen


def test_rewrite_offer_uses_hypothesis_context(monkeypatch):
    hypothesis = suggest(SAMPLE)["items"][0]
    seen = _llm(monkeypatch, json.dumps({"proposal": "Вклад с надбавкой к ставке за пополнение."}))
    text = engine.rewrite_offer(SAMPLE["scenario"], hypothesis)
    assert text == "Вклад с надбавкой к ставке за пополнение."
    prompt = seen[0]["messages"][1]["content"]
    assert hypothesis["base_text"] in prompt and hypothesis["change"] in prompt
    assert "ставка недостаточная" in prompt


@pytest.mark.parametrize(
    "content", ["{}", json.dumps({"proposal": ""}), json.dumps({"proposal": "x" * 3001})]
)
def test_rewrite_offer_rejects_bad_answers(monkeypatch, content):
    hypothesis = suggest(SAMPLE)["items"][0]
    _llm(monkeypatch, content)
    with pytest.raises(ValueError):
        engine.rewrite_offer(SAMPLE["scenario"], hypothesis)


def test_rewrite_offer_rejects_unchanged_text(monkeypatch):
    hypothesis = suggest(SAMPLE)["items"][0]
    _llm(monkeypatch, json.dumps({"proposal": hypothesis["base_text"]}))
    with pytest.raises(ValueError, match="без изменений"):
        engine.rewrite_offer(SAMPLE["scenario"], hypothesis)
