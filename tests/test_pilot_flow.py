"""A reproducible MVP pilot rehearsal with synthetic fixtures and isolated accounts.

Run: python -m pytest tests/test_pilot_flow.py -q
No real survey participants, external model, or product database are used.
"""

import json
import time

from fastapi.testclient import TestClient

from dvoinik.api import create_app
from dvoinik.auth import AuthStore
from dvoinik.scenarios import SCENARIOS


def test_pilot_rehearsal_preserves_provenance_and_private_exports(tmp_path):
    path = tmp_path / "pilot.sqlite3"
    auth = AuthStore(path)
    password = "synthetic-pilot-test-only"
    for username in ("alice", "bob"):
        auth.create_user(username, username.title(), password)
    app = create_app(path, mode="local")
    alice = TestClient(app, base_url="http://127.0.0.1")
    bob = TestClient(app, base_url="http://127.0.0.1")
    try:
        for client, username in ((alice, "alice"), (bob, "bob")):
            response = client.post("/api/login", json={"username": username, "password": password})
            assert response.status_code == 200
            client.headers["X-CSRF-Token"] = response.json()["csrf_token"]

        start = alice.post(
            "/api/runs",
            json={
                "scenario_key": "senior_deposit",
                "scenario": SCENARIOS["senior_deposit"],
                "n": 50,
                "mock": True,
                "seed": 42,
                "concurrency": 2,
            },
        )
        assert start.status_code == 202
        deadline = time.monotonic() + 10
        while True:
            status = alice.get("/api/runs/" + start.json()["id"])
            assert status.status_code == 200
            job = status.json()
            if job["status"] not in {"queued", "running"}:
                break
            assert time.monotonic() < deadline, "Synthetic pilot run did not complete within 10 seconds"
            time.sleep(0.01)
        assert job["status"] == "completed" and job["saved"]
        assert job["done"] == job["total"] == 150
        record = job["record"]
        assert record["mock"] is True
        rid = record["id"]
        endpoint = f"/api/experiments/{rid}/validation"
        protocol = {
            "recruitment": "TECHNICAL FIXTURE — no people surveyed",
            "assignment": "all_variants",
            "notes": "Synthetic CSV for MVP rehearsal only.",
        }
        # Two observations per proposal, with distinct hand-checkable rates.
        csv = "segment,variant,decision\nsenior,A,0\nsenior,A,0\nsenior,B,1\nsenior,B,0\nsenior,C,1\nsenior,C,1\n"
        payload = {"csv": csv, "protocol": protocol}
        preview = alice.post(endpoint + "/preview", json=payload)
        assert preview.status_code == 200
        assert preview.json()["base_validation"] is None
        assert "validation" not in alice.get(f"/api/experiments/{rid}").json()
        checked = preview.json()["record"]["validation"]
        assert checked["protocol"] == protocol
        assert checked["result"]["survey_n"] == 6
        assert checked["result"]["matched_cells"] == 3
        rates = {cell["variant"]: cell["actual"] for cell in checked["result"]["cells"]}
        assert rates == {"A": 0.0, "B": 0.5, "C": 1.0}

        saved = alice.put(endpoint, json={**payload, "base_validation": None})
        assert saved.status_code == 200
        assert saved.json()["validation"]["protocol"] == protocol
        assert saved.json()["mock"] is True  # A CSV never turns demo output into a model prediction.

        def export_link(format, kind="record"):
            response = alice.post("/api/export", json={"record_id": rid, "format": format, "kind": kind})
            assert response.status_code == 200
            return response.json()["url"]

        json_link = export_link("json")
        assert bob.get(json_link).status_code != 200
        downloaded = alice.get(json_link)
        assert downloaded.status_code == 200
        snapshot = downloaded.json()
        assert snapshot["validation"]["protocol"] == protocol
        assert snapshot["validation"]["result"]["survey_n"] == 6
        html = alice.get(export_link("html", "summary"))
        assert html.status_code == 200
        assert "TECHNICAL FIXTURE" in html.text
        assert "Synthetic CSV for MVP rehearsal only." in html.text

        copied = alice.post("/api/import", json={"content": json.dumps(snapshot)})
        assert copied.status_code == 200
        assert copied.json()["id"] != rid
        assert copied.json()["validation"]["protocol"] == protocol
        assert copied.json()["validation"]["result"]["survey_n"] == 6
        assert bob.get(f"/api/experiments/{rid}").status_code == 404
        assert bob.get(f"/api/experiments/{copied.json()['id']}").status_code == 404
        assert bob.post(endpoint + "/preview", json=payload).status_code == 404
        assert bob.get("/api/experiments").json() == {"records": []}

        revoked = export_link("json")
        assert alice.post("/api/logout").status_code == 200
        assert alice.get(revoked).status_code == 410
        assert alice.get(f"/api/experiments/{rid}").status_code == 401
    finally:
        alice.close()
        bob.close()
        app.state.jobs.close()
