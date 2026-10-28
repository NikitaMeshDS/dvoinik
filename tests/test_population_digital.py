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
    assert all("Работа: " in t.profile() for t in students)
    families = build_population(5, {"young_family": 1})
    assert all(not t.traits and "traits" not in t.to_dict() for t in families)
    # Атрибут берётся из отдельного генератора: остальные поля те же, что без него.
    again = build_population(30, {"senior": 0.5, "student_msk": 0.5}, seed=3)
    assert [t.to_dict() for t in twins] == [t.to_dict() for t in again]


def test_digital_attribute_survives_saved_report():
    from dvoinik.experiments import load_experiment
    from dvoinik.runs import RunSettings, run_experiment
    from dvoinik.scenarios import SCENARIOS

    record = run_experiment("senior_deposit", SCENARIOS["senior_deposit"], RunSettings(n=20))
    sample = load_experiment(json.dumps(record))["population_sample"]
    assert all(p["traits"]["Цифровые навыки"] in {text for text, _ in DIGITAL["senior"]} for p in sample)


def test_llm_check_shows_probability_by_digital_level(monkeypatch, tmp_path):
    import httpx
    from openai import AsyncOpenAI

    import llm_check
    from dvoinik import engine

    def respond(request):
        payload = json.loads(request.content)
        system, user = payload["messages"][0]["content"], payload["messages"][1]["content"]
        if "Не моделируй отдельных людей" in system:
            content = json.dumps({"rates": {"A": 0.2, "B": 0.6, "C": 0.4}})
        else:
            offline = "интернетом не пользуется" in user
            p = 0.05 if offline and "приложении" in user else 0.5
            content = json.dumps(
                {"decision": p > 0.5, "probability": p, "objection": "не доверяю", "quote": "Ответ."},
                ensure_ascii=False,
            )
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
    out = tmp_path / "check.md"
    llm_check.main(["--scenario", "senior_deposit", "--n", "50", "--output", str(out)])
    text = out.read_text(encoding="utf-8")
    assert "Вероятность «да» по атрибутам профиля:" in text
    assert "Цифровые навыки: интернетом не пользуется (n≈27): A 5%, B 50%" in text
    assert "Главные причины отказа: A: не доверяю" in text


def test_youth_traits_follow_sources_and_stay_off_benchmark_questions():
    from dvoinik.population import TRAITS

    students = build_population(100, {"student_reg": 1})
    assert Counter(t.traits["Работа"] for t in students) == {
        "подрабатывает до 10 часов в неделю": 35,
        "работает больше 10 часов в неделю": 28,
        "не работает": 37,
    }
    teens = build_population(20, {"teen": 1})
    assert Counter(t.traits["Подработка"] for t in teens) == {
        "подрабатывает летом": 3,
        "не подрабатывает": 17,
    }
    # Атрибуты молодёжи не говорят о картах и счетах — это вопросы бенчмарка.
    for sid in ("teen", "student_msk", "student_reg"):
        for trait in TRAITS[sid]:
            text = " ".join([trait["label"], *(v for v, _ in trait["levels"])]).lower()
            assert not any(word in text for word in ("карт", "счёт", "счет", "вклад", "банк"))
        assert all(abs(sum(share for _, share in t["levels"]) - 1) < 1e-9 for t in TRAITS[sid])
