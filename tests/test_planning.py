import json
import math

import httpx
import pytest
from openai import AsyncOpenAI

from dvoinik import engine
from dvoinik.experiments import attach_validation, load_experiment
from dvoinik.planning import (
    baseline_agreement,
    detectable_difference,
    interview_questions,
    leader_stability,
    live_check_plan,
    run_estimate,
    sample_size,
)
from dvoinik.population import build_population
from dvoinik.reporting import PROFILES_PER_SEGMENT, export_json
from dvoinik.runs import RunSettings, run_experiment
from dvoinik.scenarios import SCENARIOS
from dvoinik.validate import SurveyRates


def result(yes, n, objections=None):
    return {"n": n, "yes": yes, "conversion": yes / n, "objections": objections or {}, "segments": {}}


def test_sample_size_matches_textbook_two_proportion_formula():
    # 43% против 55,5%: около 250 ответов на предложение при α=0,05 и мощности 80%.
    assert 240 <= sample_size(0.555, 0.43) <= 260
    assert sample_size(0.5, 0.3) < sample_size(0.5, 0.4)
    assert sample_size(0.5, 0.49) is None
    with pytest.raises(ValueError):
        sample_size(1.2, 0.3)


def test_detectable_difference_shrinks_with_sample():
    assert detectable_difference(0.5, 30) > 0.3
    assert detectable_difference(0.5, 300) < detectable_difference(0.5, 30)


def test_leader_stability_separates_clear_and_close_leaders():
    clear = leader_stability({"A": result(10, 200), "B": result(120, 200)})
    assert clear["leader"] == "B" and clear["level"] == "stable" and clear["share"] > 0.99
    close = leader_stability({"A": result(100, 200), "B": result(104, 200)})
    assert close["level"] == "unstable" and 0.5 < close["share"] < 0.8
    assert leader_stability({"A": result(1, 2)}) is None
    # Детерминированность: одинаковый ответ при повторном расчёте.
    assert close == leader_stability({"A": result(100, 200), "B": result(104, 200)})


def test_interview_questions_follow_most_frequent_objections():
    report = {
        "A": result(1, 10, {"плата": 6, "не доверяю": 3}),
        "B": result(5, 10, {"плата": 4, "сложно": 1}),
    }
    questions = interview_questions(report)
    assert len(questions) <= 5
    assert "плата" in questions[1]["text"] and "не доверяю" in questions[3]["text"]
    assert all("?" in q["text"] for q in questions)


def test_live_check_plan_on_demo_snapshot():
    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=200, seed=42))
    plan = live_check_plan(record)
    first = plan["comparisons"][0]
    assert first["pair"] == ["C", "B"] and first["n_per_variant"] == sample_size(
        record["report"]["C"]["conversion"], record["report"]["B"]["conversion"]
    )
    assert plan["exploratory_detectable_pp"] > 20
    assert plan["questions"]
    student = run_experiment("student_card", SCENARIOS["student_card"], RunSettings(n=200, seed=42))
    leaders = {s["leader"] for s in live_check_plan(student)["focus_segments"]}
    assert leaders and all(v in student["report"] for v in leaders)


def test_demo_run_stores_baseline_profiles_and_probability():
    record = run_experiment("student_card", SCENARIOS["student_card"], RunSettings(n=60, seed=7))
    assert record["baseline"]["method"] == "demo_rule"
    assert set(record["baseline"]["rates"]) == set(record["report"])
    per_segment = {}
    for profile in record["population_sample"]:
        per_segment[profile["segment"]] = per_segment.get(profile["segment"], 0) + 1
    assert max(per_segment.values()) <= PROFILES_PER_SEGMENT
    assert all(0 <= r["probability"]["mean"] <= 1 for r in record["report"].values())
    agreement = baseline_agreement(record)
    assert agreement["rows"] and isinstance(agreement["same_leader"], bool)
    # Снимок с новыми полями проходит строгий импорт.
    loaded = load_experiment(export_json(record))
    assert loaded["baseline"] == record["baseline"]


def test_import_rejects_inconsistent_baseline_and_probability():
    record = run_experiment("student_card", SCENARIOS["student_card"], RunSettings(n=20, seed=1))
    broken = json.loads(export_json(record))
    broken["baseline"]["rates"].pop("A")
    with pytest.raises(ValueError, match="простым подходом"):
        load_experiment(json.dumps(broken))
    broken = json.loads(export_json(record))
    broken["report"]["A"]["probability"]["n"] = 1
    with pytest.raises(ValueError, match="вероятност"):
        load_experiment(json.dumps(broken))
    old = json.loads(export_json(record))
    del old["baseline"]
    for variant in old["report"].values():
        variant.pop("probability")
    assert "baseline" not in load_experiment(json.dumps(old))


def test_validation_compares_twins_and_baseline_with_survey():
    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=100, seed=3))
    survey = SurveyRates(
        {("A", "senior"): 0.1, ("B", "senior"): 0.5, ("C", "senior"): 0.4},
        {("A", "senior"): 30, ("B", "senior"): 30, ("C", "senior"): 30},
    )
    metrics = attach_validation(record, survey)["validation"]["result"]["baseline"]
    assert {row["variant"] for row in metrics["variants"]} == {"A", "B", "C"}
    assert math.isfinite(metrics["twins_mae_variants"]) and math.isfinite(metrics["baseline_mae_variants"])


def test_llm_baseline_uses_single_request_and_reports_schema_errors(monkeypatch):
    replies = iter(['{"rates": {"A": 0.2, "B": 0.6}}', '{"rates": {"A": 2, "B": 0.6}}'])
    seen = []

    def respond(request):
        payload = json.loads(request.content)
        seen.append(payload)
        body = {
            "id": "t",
            "object": "chat.completion",
            "created": 0,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": next(replies)},
                    "finish_reason": "stop",
                }
            ],
        }
        return httpx.Response(200, json=body)

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
        "question": "Подключите?",
        "variants": {"A": "первое", "B": "второе"},
        "population": {"senior": 1.0},
        "objections": ["плата"],
    }
    assert engine.baseline_estimate(scenario) == {"method": "single_prompt", "rates": {"A": 0.2, "B": 0.6}}
    assert "Пенсионеры 60+" in seen[0]["messages"][1]["content"] and seen[0]["temperature"] == 0
    assert "error" in engine.baseline_estimate(scenario)


def test_run_estimate_counts_requests_and_optional_price(monkeypatch):
    scenario = SCENARIOS["student_card"]
    estimate = run_estimate(scenario, 200, concurrency=16)
    assert estimate["requests"] == 200 * 3 + 1
    assert estimate["input_tokens"] > estimate["requests"] * 100
    assert estimate["cost"] is None
    monkeypatch.setenv("DVOINIK_PRICE_PER_1K_TOKENS", "0.5")
    priced = run_estimate(scenario, 200, concurrency=16)
    assert priced["cost"] == round((priced["input_tokens"] + priced["output_tokens"]) / 1000 * 0.5, 2)
    monkeypatch.setenv("DVOINIK_PRICE_PER_1K_TOKENS", "-1")
    with pytest.raises(ValueError):
        run_estimate(scenario, 200)


@pytest.mark.parametrize(
    "n, concurrency, baseline, batches", [(6, 4, True, 8), (6, 1, True, 19), (1, 16, False, 3)]
)
def test_estimate_keeps_probe_variant_groups_and_baseline_separate(
    monkeypatch, n, concurrency, baseline, batches
):
    monkeypatch.setenv("DVOINIK_LLM_LATENCY_S", "3")
    estimate = run_estimate(SCENARIOS["senior_deposit"], n, concurrency=concurrency, baseline=baseline)
    assert estimate["requests"] == n * 3 + baseline
    assert estimate["minutes"] == pytest.approx(batches * 3 / 60)


def test_demo_quotes_vary_without_changing_decisions():
    twins = build_population(200, {"senior": 1.0}, seed=42)
    scenario = SCENARIOS["senior_deposit"]
    report = engine.simulate(twins, scenario, mock=True, seed=42)
    assert report == engine.simulate(twins, scenario, mock=True, seed=42)
    quotes = {q["quote"] for r in report.values() for q in r["quotes"]}
    assert len(quotes) >= 4


def test_seed_robustness_counts_leaders_across_neighbouring_seeds():
    from dvoinik.runs import seed_robustness

    robust = seed_robustness("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=100, seed=5), 3)
    assert sum(robust["leaders"].values()) == 3
    assert [r["seed"] for r in robust["runs"]] == [5, 6, 7]
    with pytest.raises(ValueError):
        seed_robustness("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(), 1)


def test_segment_objections_sum_to_segment_refusals_and_are_validated():
    record = run_experiment("student_card", SCENARIOS["student_card"], RunSettings(n=120, seed=3))
    for result in record["report"].values():
        total = {}
        for segment in result["segments"].values():
            assert sum(segment["objections"].values()) == segment["n"] - segment["yes"]
            for reason, count in segment["objections"].items():
                total[reason] = total.get(reason, 0) + count
        assert total == result["objections"]
    broken = json.loads(export_json(record))
    sid = next(iter(broken["report"]["A"]["segments"]))
    broken["report"]["A"]["segments"][sid]["objections"] = {"плата и условия": 10_000}
    with pytest.raises(ValueError):
        load_experiment(json.dumps(broken))


def test_focus_segments_require_observed_rates_for_both_variants():
    record = {
        "scenario": {"population": {"senior": 1.0}},
        "report": {"A": result(8, 10), "B": result(2, 10)},
    }
    record["report"]["A"]["segments"] = {"senior": {"yes": 0, "n": 0}}
    record["report"]["B"]["segments"] = {"senior": {"yes": 2, "n": 10}}
    assert live_check_plan(record)["focus_segments"] == []
    # An observed zero is a valid comparator, unlike missing observations.
    record["report"]["A"]["segments"]["senior"]["n"] = 10
    focus = live_check_plan(record)["focus_segments"]
    assert len(focus) == 1
    assert focus[0]["leader"] == "B"
    assert focus[0]["gap_pp"] == pytest.approx(20)


@pytest.mark.parametrize("left,right", [(0.22, 0.20), (0.42, 0.40), (0.52, 0.50)])
def test_sample_size_includes_exact_two_percentage_point_boundary(left, right):
    assert sample_size(left, right) is not None
    assert sample_size(right, left) == sample_size(left, right)
    assert sample_size(right + 0.01999, right) is None
