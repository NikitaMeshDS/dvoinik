from dvoinik.experiments import attach_validation, load_experiment
from dvoinik.reporting import export_json
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
    assert "Парное сравнение" in html and "100 из 100 профилей" in html
    assert "95% интервал" in html
    assert "Расхождения по сегментам" not in html


def test_summary_includes_survey_comparison_when_validated():
    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=100, seed=1))
    survey = SurveyRates({(v, "senior"): 0.3 for v in "ABC"}, {(v, "senior"): 30 for v in "ABC"})
    html = team_summary(attach_validation(record, survey))
    assert "90 оценок" in html and "ошибка двойников" in html


def test_summary_lists_the_five_largest_survey_discrepancies():
    scenario = {
        **SCENARIOS["senior_deposit"],
        "population": {"senior": 0.5, "student_msk": 0.5},
    }
    record = run_experiment("senior_deposit", scenario, RunSettings(n=100, seed=1))
    rates = {
        (variant, segment): float(variant == "A")
        for variant in scenario["variants"]
        for segment in scenario["population"]
    }
    counts = {key: index + 1 for index, key in enumerate(rates)}
    validated = attach_validation(record, SurveyRates(rates, counts))
    cells = validated["validation"]["result"]["cells"]
    original = [(cell["variant"], cell["segment"]) for cell in cells]
    html = team_summary(validated)
    block = html.split('id="survey-discrepancies"', 1)[1].split("</section>", 1)[0]
    assert "Сопоставленные пары (5 из 6)" in block
    assert block.count("<tr>") == 6
    assert "Симуляция выше" in block and "Симуляция ниже" in block
    assert "Студенты 18–22, Москва" in block
    assert "Общий рейтинг недоступен" in html
    expected = sorted(cells, key=lambda cell: (-cell["error"], -cell["survey_n"]))
    assert expected[0]["variant"] == "A"
    assert f"<td>{expected[0]['survey_n']}</td>" in block.split("<tbody>", 1)[1].split("</tr>", 1)[0]
    assert [(cell["variant"], cell["segment"]) for cell in cells] == original


def test_summary_starts_with_a_method_passport():
    import json
    from pathlib import Path

    from dvoinik.summary import team_summary

    record = json.loads((Path(__file__).parents[1] / "examples" / "senior-deposit.demo.json").read_text())
    html = team_summary(record)
    assert html.index("Паспорт исследования") < html.index("Предложения")
    assert "Парное сравнение" not in html
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


def test_summary_discloses_probability_corrections():
    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=100, seed=1))
    record["report"]["A"]["inconsistent_n"] = 7
    html = team_summary(record)
    assert "Корректировки вероятностей — вариант A" in html
    assert "7 из 100 ответов" in html
    assert "p на 1 − p" in html


def test_summary_exports_probability_before_and_after_correction():
    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=100, seed=1))
    record["report"]["A"].update(
        inconsistent_n=7,
        raw_probability={"mean": 0.8, "sd": 0.1, "n": 100},
        probability={"mean": 0.4, "sd": 0.3, "n": 100},
    )
    html = team_summary(record)
    assert "до корректировки: 80" in html
    assert "после: 40" in html
    del record["report"]["A"]["raw_probability"]
    html = team_summary(record)
    assert "Исходные значения не сохранены" in html
    assert "до корректировки: 80" not in html


def test_summary_discloses_protocol_without_executing_user_text():
    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=20))
    survey = SurveyRates({("A", "senior"): 0.5}, {("A", "senior"): 2})
    checked = attach_validation(
        record,
        survey,
        protocol={
            "recruitment": "<script>bad</script>",
            "assignment": "random_one",
            "collected_from": "2026-11-01",
        },
    )
    reopened = load_experiment(export_json(checked))
    result_key = "mae_interval_95_pp"
    assert reopened["validation"]["result"][result_key] == checked["validation"]["result"][result_key]
    html = team_summary(reopened)
    assert "&lt;script&gt;bad&lt;/script&gt;" in html and "<script>bad" not in html
    assert "2026-11-01" in html and "случайно" in html
    assert "Приблизительный 95%-й интервал ошибки" in html
    without_protocol = team_summary(attach_validation(record, survey))
    assert "не указаны" in without_protocol
    assert "Приблизительный 95%-й интервал ошибки" not in without_protocol


def coverage_record(counts):
    scenario = {
        **SCENARIOS["senior_deposit"],
        "population": {"senior": 0.5, "student_msk": 0.5},
        "variants": {"A": "Текст A", "B": "Текст B"},
    }
    record = run_experiment("senior_deposit", scenario, RunSettings(n=100, seed=1))
    return attach_validation(record, SurveyRates({key: 0.5 for key in counts}, counts))


def test_summary_exposes_missing_variants_and_partial_survey_coverage():
    html = team_summary(coverage_record({("A", "senior"): 4}))
    assert "1 из 4 пар «предложение — сегмент»" in html
    assert "Нет оценок предложений: B" in html
    assert "отсутствие ответов не означает отказ" in html
    assert "Для общего сравнения нужны оценки каждого предложения." in html


def test_summary_warns_when_equal_totals_hide_different_segment_composition():
    html = team_summary(
        coverage_record(
            {
                ("A", "senior"): 9,
                ("A", "student_msk"): 1,
                ("B", "senior"): 1,
                ("B", "student_msk"): 9,
            }
        )
    )
    assert "4 из 4 пар «предложение — сегмент»" in html
    assert "Состав аудитории различается" in html
    assert "90,0%" in html
    assert "Общий рейтинг недоступен." in html


def test_summary_equal_composition_is_not_a_validity_claim():
    html = team_summary(
        coverage_record(
            {
                ("A", "senior"): 2,
                ("A", "student_msk"): 2,
                ("B", "senior"): 4,
                ("B", "student_msk"): 4,
            }
        )
    )
    assert "Доли сегментов одинаковы" in html
    assert "не подтверждает репрезентативность" in html
    assert "Состав аудитории различается" not in html
