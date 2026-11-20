import asyncio
import json

import pytest

from dvoinik import engine
from dvoinik.population import build_population


def test_dialogue_carries_two_answers_but_offers_remain_independent():
    import context_study as study

    calls = []

    async def ask(messages):
        calls.append(messages)
        if any(messages[-1]["content"].endswith(question) for question in study.FOLLOWUPS):
            return json.dumps({"reply": "ответ участника"})
        return json.dumps({"decision": False, "reason": "неудобный канал"})

    twin = build_population(1, {"senior": 1})[0]
    results = asyncio.run(study.simulate(twin, ask))
    assert len(calls) == 8
    assert twin.profile() not in calls[0][1]["content"]
    assert twin.profile() in calls[2][1]["content"]
    assert calls[-2][:-1] == calls[-1][:-1]
    assert [message["role"] for message in calls[-1]] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert [message["content"] for message in calls[-1] if message["role"] == "assistant"] == [
        '{"reply": "ответ участника"}',
        '{"reply": "ответ участника"}',
    ]
    assert results["dialogue"]["B"] == (False, "неудобный канал")


def test_errors_reported_and_only_complete_pairs_compared():
    import context_study as study

    valid = (True, None)
    refusal = (False, "неудобный канал")
    complete = {mode: {"A": refusal, "B": valid} for mode in study.MODES}
    incomplete = {**complete, "dialogue": {"A": None, "B": valid}}
    human = {"A": [refusal], "B": [valid]}
    result = study.summarize([(None, complete), (None, incomplete)], human)
    assert result["matched_n"] == 1
    assert result["coverage"]["dialogue"] == {"A": 1, "B": 2}
    assert result["synthetic"]["profile"]["A"]["yes_share"] == 0
    assert result["synthetic"]["profile"]["mean_abs_error_pp"] == 0
    assert result["synthetic"]["profile"]["A"]["reason_distance_pp"] == 0
    assert result["synthetic"]["profile"]["B"]["reason_distance_pp"] is None


def test_human_input_accepts_only_coded_answers(tmp_path):
    import context_study as study

    path = tmp_path / "answers.json"
    path.write_text(
        json.dumps(
            [
                {"variant": "A", "decision": True, "reason": None},
                {"variant": "B", "decision": False, "reason": engine.OTHER_OBJECTION},
            ]
        )
    )
    assert study.load_human(path)["B"] == [(False, engine.OTHER_OBJECTION)]
    path.write_text(json.dumps([{"variant": "A", "decision": "нет", "reason": None}]))
    with pytest.raises(ValueError, match="строка 1"):
        study.load_human(path)


def test_saved_run_can_be_compared_without_calling_model(tmp_path, monkeypatch):
    import sys

    import context_study as study

    yes = (True, None)
    no = (False, "неудобный канал")
    snapshot = study.summarize([(None, {mode: {"A": no, "B": yes} for mode in study.MODES})])
    snapshot.update(
        question=study.QUESTION, offers=study.OFFERS, followups=study.FOLLOWUPS, reasons=study.REASONS
    )
    source = tmp_path / "before.json"
    source.write_text(json.dumps(snapshot))
    human = tmp_path / "human.json"
    human.write_text(
        json.dumps(
            [
                {"variant": "A", "decision": False, "reason": "неудобный канал"},
                {"variant": "B", "decision": True, "reason": None},
            ]
        )
    )
    output = tmp_path / "after.json"
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["context_study.py", "--compare", str(source), "--human", str(human), "--output", str(output)],
    )
    assert study.main() == 0
    assert json.loads(output.read_text())["synthetic"]["dialogue"]["mean_abs_error_pp"] == 0
    assert json.loads(source.read_text())["human"] is None
