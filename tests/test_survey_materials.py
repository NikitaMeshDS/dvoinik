"""A real survey export must not fabricate answers or expose model outcomes."""

import copy
import csv
import io
import zipfile

import pytest
from test_api import app as api_fixture
from test_api import completed, login, run, start

app = api_fixture


def export(client, record, kind, format):
    response = client.post("/api/export", json={"record_id": record["id"], "kind": kind, "format": format})
    assert response.status_code == 200, response.text
    return response.json()["url"]


def test_unfilled_template_cannot_be_mistaken_for_real_rejections(app):
    client = login(app)
    record = run(client)["record"]
    template = client.get(export(client, record, "survey-template", "csv")).text
    rows = list(csv.DictReader(io.StringIO(template)))
    assert rows and {row["decision"] for row in rows} == {""}
    preview = client.post(f"/api/experiments/{record['id']}/validation/preview", json={"csv": template})
    assert preview.status_code == 422
    assert client.get(f"/api/experiments/{record['id']}").json().get("validation") is None
    rows[0]["decision"] = "1"
    filled = io.StringIO()
    writer = csv.DictWriter(filled, fieldnames=["segment", "variant", "decision"])
    writer.writeheader()
    writer.writerow(rows[0])
    preview = client.post(
        f"/api/experiments/{record['id']}/validation/preview", json={"csv": filled.getvalue()}
    )
    assert preview.status_code == 200
    assert preview.json()["record"]["validation"]["result"]["survey_n"] == 1


def test_kit_is_portable_safe_and_scoped_to_original_session(app):
    client = login(app)
    from dvoinik.scenarios import SCENARIOS

    scenario = copy.deepcopy(next(iter(SCENARIOS.values())))
    scenario["title"] = 'Тест <img src=x onerror="alert(1)">'
    scenario["question"] = "Открыли бы вы счёт? <script>alert(1)</script>"
    scenario["variants"]["A"] = "Условия <b>без комиссии</b> & без подписки"
    scenario["description"] = "INTERNAL-RESEARCH-STRATEGY"
    result = completed(client, start(client, scenario=scenario).json()["id"])
    record = result["record"]
    url = export(client, record, "survey-kit", "zip")
    assert login(app, "bob").get(url).status_code == 410
    assert login(app).get(url).status_code == 410
    assert client.head(url).status_code == 200
    response = client.get(url)
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        assert set(bundle.namelist()) == {"questionnaire.html", "responses.csv", "README.txt"}
        html = bundle.read("questionnaire.html").decode("utf-8")
        assert "Открыли бы вы счёт?" in html
        assert "Условия &lt;b&gt;без комиссии&lt;/b&gt; &amp; без подписки" in html
        assert "<script>" not in html and "<img src=x" not in html
        assert "INTERNAL-RESEARCH-STRATEGY" not in html
        assert "confidence_interval" not in html and "conversion" not in html
        assert "<form" not in html and "https://" not in html
        assert "UTF-8" in bundle.read("README.txt").decode("utf-8")
        assert (
            bundle.read("responses.csv").decode("utf-8")
            == client.get(export(client, record, "survey-template", "csv")).text
        )
    assert client.get(url).status_code == 410
    assert client.get(f"/api/experiments/{record['id']}").json() == record


def test_templates_only_include_cells_with_valid_simulation_answers(app):
    client = login(app)
    result = completed(client, start(client, n=1).json()["id"])
    record = result["record"]
    template = client.get(export(client, record, "survey-template", "csv")).text
    rows = list(csv.DictReader(io.StringIO(template)))
    assert len(rows) == len(record["scenario"]["variants"])
    for row in rows:
        assert record["report"][row["variant"]]["segments"][row["segment"]]["n"] > 0


@pytest.mark.parametrize(
    "kind,format", [("survey-kit", "csv"), ("record", "zip"), ("survey-template", "zip")]
)
def test_rejects_invalid_survey_export_combinations(app, kind, format):
    client = login(app)
    record = run(client)["record"]
    assert (
        client.post(
            "/api/export", json={"record_id": record["id"], "kind": kind, "format": format}
        ).status_code
        == 422
    )
