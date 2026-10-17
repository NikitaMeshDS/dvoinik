from dvoinik.experiments import attach_validation
from dvoinik.runs import RunSettings, run_experiment
from dvoinik.scenarios import SCENARIOS
from dvoinik.summary import team_summary
from dvoinik.validate import SurveyRates


def test_summary_is_self_contained_and_escapes_user_text():
    scenario = {**SCENARIOS["senior_deposit"], "title": "<script>alert(1)</script> Вклад"}
    record = run_experiment("senior_deposit", scenario, RunSettings(n=100, seed=42))
    html = team_summary(record)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "default-src 'none'" in html and "<script" not in html.replace("&lt;script", "")
    assert "Демо" in html and "План живой проверки" in html and "Простой подход" in html
    assert "Живой опрос:</b> ещё не загружен" in html


def test_summary_includes_survey_comparison_when_validated():
    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=100, seed=1))
    survey = SurveyRates({(v, "senior"): 0.3 for v in "ABC"}, {(v, "senior"): 30 for v in "ABC"})
    html = team_summary(attach_validation(record, survey))
    assert "90 оценок" in html and "ошибка двойников" in html


def test_summary_starts_with_a_method_passport():
    import json
    from pathlib import Path

    from dvoinik.summary import team_summary

    record = json.loads((Path(__file__).parents[1] / "examples" / "senior-deposit.demo.json").read_text())
    html = team_summary(record)
    assert html.index("Паспорт исследования") < html.index("Предложения")
    assert "Демо-эвристика по ключевым словам" in html and "ещё не проводилась" in html
    assert "Риск искажений" in html and "Пенсионеры 60+" in html
    llm = {**record, "mock": False, "model": "qwen2.5:7b-instruct · SSR"}
    assert "готовность — по смыслу ответа (SSR" in team_summary(llm)
    child = {
        **record,
        "scenario": {
            **record["scenario"],
            "origin": {
                "kind": "hypothesis",
                "record_id": "p1",
                "title": "Исходное",
                "lever": "Цена",
                "change": "x",
                "variant": "C",
            },
        },
    }
    assert "проверка гипотезы «Цена» исследования «Исходное»" in team_summary(child)
