from dataclasses import replace

import pytest

from dvoinik import engine
from dvoinik.experiments import load_experiment, normalize_scenario
from dvoinik.population import build_population
from dvoinik.reporting import export_json, make_record
from dvoinik.runs import RunSettings, run_experiment
from dvoinik.scenarios import SCENARIOS
from dvoinik.summary import team_summary
from dvoinik.survey_materials import questionnaire


def test_deposit_interest_survives_financial_gate_and_minimum_is_inclusive(monkeypatch):
    scenario = {**SCENARIOS["senior_deposit"], "deposit_minimum_rub": 50000}
    twins = build_population(3, {"senior": 1})
    twins = [replace(t, available_deposit_rub=sum_rub) for t, sum_rub in zip(twins, (49999, 50000, None))]
    answers = []

    def answer(_rng, twin, _scenario, _text):
        answers.append(twin.id)
        return {"decision": True}

    monkeypatch.setattr(engine, "_ask_mock", answer)
    report = engine.simulate(twins, scenario, mock=True)
    record = make_record("senior_deposit", scenario, 3, True, 42, report, twins)
    assert len(answers) == 3 * len(scenario["variants"])
    assert all(result["yes"] == 3 for result in report.values())
    assert record["deposit_eligibility"] == {"available_n": 1, "unavailable_n": 1, "unknown_n": 1}
    restored = load_experiment(export_json(record))
    assert restored["deposit_eligibility"] == record["deposit_eligibility"]
    assert "Минимальный взнос" in questionnaire(restored)
    assert "По минимальному взносу" in team_summary(restored)
    record["deposit_eligibility"]["available_n"] = 2
    with pytest.raises(ValueError, match="доступност"):
        load_experiment(export_json(record))


def test_deposit_template_produces_reproducible_synthetic_amounts():
    scenario = SCENARIOS["senior_deposit"]
    assert scenario["deposit_minimum_rub"] == 50000
    record = run_experiment("senior_deposit", scenario, RunSettings(n=12, mock=True))
    assert record["deposit_eligibility"] == {"available_n": 6, "unavailable_n": 6, "unknown_n": 0}
    sample = record["population_sample"]
    assert all("available_deposit_rub" in row and "Цифровые навыки" in row["traits"] for row in sample)
    regular = run_experiment("student_card", SCENARIOS["student_card"], RunSettings(n=12, mock=True))
    assert "deposit_eligibility" not in regular
    assert all("available_deposit_rub" not in row for row in regular["population_sample"])


def test_deposit_removes_branch_preference_without_resampling_profiles():
    population = {"senior": 1}
    ordinary = build_population(24, population, seed=42)
    deposit = build_population(24, population, seed=42, deposit=True)
    assert any(twin.attitude == "предпочитает отделение" for twin in ordinary)
    for before, after in zip(ordinary, deposit, strict=True):
        expected = "" if before.attitude == "предпочитает отделение" else before.attitude
        assert after == replace(before, attitude=expected, available_deposit_rub=after.available_deposit_rub)
        assert "предпочитает отделение" not in after.profile()
        assert "Цифровые навыки" in after.profile()
        if not expected:
            assert "Отношение к банкам:" not in after.profile()

    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=24, mock=True))
    assert load_experiment(export_json(record))["population_sample"] == record["population_sample"]
    without_minimum = dict(SCENARIOS["senior_deposit"])
    del without_minimum["deposit_minimum_rub"]
    record = run_experiment("senior_deposit", without_minimum, RunSettings(n=24, mock=True))
    sample = load_experiment(export_json(record))["population_sample"]
    assert any(profile["attitude"] == "" for profile in sample)
    assert all("available_deposit_rub" not in profile for profile in sample)


@pytest.mark.parametrize("remove_total", [False, True])
def test_import_rejects_deposit_totals_inconsistent_with_snapshot(remove_total):
    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=3, mock=True))
    if remove_total:
        del record["deposit_eligibility"]
    else:
        record["deposit_eligibility"] = {"available_n": 3, "unavailable_n": 0, "unknown_n": 0}
        assert any(profile["available_deposit_rub"] < 50_000 for profile in record["population_sample"])
    with pytest.raises(ValueError, match="доступност"):
        load_experiment(export_json(record))


@pytest.mark.parametrize("minimum", [True, "50000", 0, -1, 1.5, None])
def test_deposit_minimum_must_be_positive_integer(minimum):
    scenario = {**SCENARIOS["senior_deposit"], "deposit_minimum_rub": minimum}
    with pytest.raises(ValueError, match="Минимальный взнос"):
        normalize_scenario(scenario)


def test_llm_evaluates_interest_without_the_assigned_amount(monkeypatch):
    import asyncio

    scenario = SCENARIOS["senior_deposit"]
    twin = replace(build_population(1, {"senior": 1})[0], available_deposit_rub=28473)

    async def chat_json(_client, _model, messages, _temperature):
        text = messages[-1]["content"]
        assert "Цифровые навыки" in text
        assert scenario["description"] not in text
        assert scenario["variants"]["B"] not in text
        assert "Минимальный взнос — 50 000 ₽." in text
        assert "Если бы у вас была нужная сумма" in text
        assert "28473" not in text and "28 473" not in text
        return '{"decision": true, "probability": 1, "quote": "Мне интересно"}'

    monkeypatch.setattr(engine.llm_json, "chat_json", chat_json)
    answer = asyncio.run(
        engine._ask_llm(None, "test", twin, scenario, scenario["variants"]["A"], asyncio.Semaphore(1))
    )
    assert answer["decision"] is True
