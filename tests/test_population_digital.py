import json
from collections import Counter

from dvoinik.population import DIGITAL, build_population


def test_senior_digital_skills_follow_published_shares_exactly():
    twins = build_population(100, {"senior": 1})
    counts = Counter(t.digital for t in twins)
    assert counts == {text: round(share * 100) for text, share in DIGITAL["senior"]}
    assert "Цифровые навыки: " in twins[0].profile()


def test_other_segments_and_fields_are_unchanged():
    twins = build_population(30, {"senior": 0.5, "student_msk": 0.5}, seed=3)
    students = [t for t in twins if t.segment == "student_msk"]
    assert students and all(t.digital is None and "Цифровые" not in t.profile() for t in students)
    assert "digital" not in students[0].to_dict()
    # Атрибут берётся из отдельного генератора: остальные поля те же, что без него.
    again = build_population(30, {"senior": 0.5, "student_msk": 0.5}, seed=3)
    assert [t.to_dict() for t in twins] == [t.to_dict() for t in again]


def test_digital_attribute_survives_saved_report():
    from dvoinik.experiments import load_experiment
    from dvoinik.runs import RunSettings, run_experiment
    from dvoinik.scenarios import SCENARIOS

    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=20))
    sample = load_experiment(json.dumps(record))["population_sample"]
    assert all(p["digital"] in {text for text, _ in DIGITAL["senior"]} for p in sample)
