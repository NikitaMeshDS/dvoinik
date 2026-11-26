"""Research HTTP routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from ... import llm_json, ssr
from ...engine import respondent_messages, rewrite_offer
from ...experiments import (
    CUSTOM_SCENARIO,
    load_experiment,
    normalize_population,
    normalize_scenario,
)
from ...hypotheses import suggest
from ...insights import insights_payload
from ...planning import run_estimate
from ...population import (
    DISTORTION_RISK,
    RISK_SOURCE,
    SEGMENT_SOURCES,
    SEGMENTS,
    SOURCE_GAPS,
    allocate_population,
)
from ...runs import RunSettings, build_run_population
from ...scenarios import SCENARIOS
from ..models import Compare, Estimate, Import, Insights, Preview, Rewrite, Run
from ..runtime import get_runtime
from ..security import identity

router = APIRouter()


@router.get("/api/catalog")
def catalog(access=Depends(identity)):
    return {
        "scenarios": {**SCENARIOS, "custom": CUSTOM_SCENARIO},
        "segments": SEGMENTS,
        "sources": {"segments": SEGMENT_SOURCES, "gaps": SOURCE_GAPS},
        "risks": {"segments": DISTORTION_RISK, "source": RISK_SOURCE},
    }


@router.post("/api/preview")
def preview(body: Preview, access=Depends(identity)):
    settings = RunSettings(n=body.n, seed=42 if body.seed is None else body.seed)
    shares = normalize_population(body.population)
    result = {"counts": allocate_population(body.n, shares), "shares": shares}
    if body.seed is not None:
        scenario = normalize_scenario(body.scenario) if body.scenario is not None else None
        deposit = "deposit_minimum_rub" in scenario if scenario is not None else body.deposit
        use_ssr = scenario is not None and ssr.mode() == "ssr"
        profiles = {}
        for twin in build_run_population(body.scenario_key, shares, settings, deposit=deposit):
            if twin.segment in profiles:
                continue
            entry = {"id": twin.id, "text": twin.profile()}
            if twin.available_deposit_rub is not None:
                entry["available_deposit_rub"] = twin.available_deposit_rub
            if scenario is not None:
                prompts = {}
                for variant, text in scenario["variants"].items():
                    system, user = llm_json.prepare_messages(
                        respondent_messages(twin, scenario, text, use_ssr=use_ssr)
                    )
                    result["respondent_system"] = system["content"]
                    prompts[variant] = user["content"]
                entry["offer_prompts"] = prompts
            profiles[twin.segment] = entry
        result["profiles"] = profiles
    return result


@router.get("/api/experiments")
def experiments(access=Depends(identity), runtime=Depends(get_runtime)):
    return {"records": runtime.auth.workspace(access[0]).list_records()}


@router.get("/api/experiments/{record_id}")
def experiment(record_id: str, access=Depends(identity), runtime=Depends(get_runtime)):
    return runtime.accessible(access[0], record_id)


@router.post("/api/import")
def import_record(body: Import, access=Depends(identity), runtime=Depends(get_runtime)):
    record = load_experiment(runtime.checked_text(body.content, "JSON"))
    record["import_origin_id"] = record["id"]
    record["id"] = uuid.uuid4().hex[:10]
    return runtime.auth.workspace(access[0]).save(record)


@router.get("/api/sample/{key}")
def sample(key: str, access=Depends(identity), runtime=Depends(get_runtime)):
    return runtime.sample(access[0], key)


@router.post("/api/runs", status_code=202)
def run(body: Run, access=Depends(identity), runtime=Depends(get_runtime)):
    if body.scenario_key not in {*SCENARIOS, "custom"}:
        raise ValueError("Неизвестный сценарий исследования.")
    scenario = normalize_scenario(body.scenario)
    settings = RunSettings(body.n, True if runtime.mode == "demo" else body.mock, body.seed, body.concurrency)
    result = runtime.jobs.submit(access[0], body.scenario_key, scenario, settings)
    return {key: result[key] for key in ("id", "status", "done", "total")}


@router.get("/api/runs/{job_id}")
def job(job_id: str, access=Depends(identity), runtime=Depends(get_runtime)):
    return runtime.jobs.get(access[0], job_id)


@router.get("/api/runs")
def active_runs(access=Depends(identity), runtime=Depends(get_runtime)):
    return {"jobs": runtime.jobs.active(access[0])}


@router.post("/api/runs/{job_id}/cancel")
def cancel_run(job_id: str, access=Depends(identity), runtime=Depends(get_runtime)):
    return runtime.jobs.cancel(access[0], job_id)


@router.get("/api/recovery")
def recovery(access=Depends(identity), runtime=Depends(get_runtime)):
    return {"jobs": runtime.jobs.recovery(access[0])}


@router.delete("/api/recovery/{job_id}")
def dismiss_interrupted(job_id: str, access=Depends(identity), runtime=Depends(get_runtime)):
    runtime.jobs.dismiss_interrupted(access[0], job_id)
    return {"ok": True}


@router.post("/api/runs/{job_id}/retry")
def retry(job_id: str, access=Depends(identity), runtime=Depends(get_runtime)):
    return runtime.jobs.retry(access[0], job_id)


@router.post("/api/compare")
def compare(body: Compare, access=Depends(identity), runtime=Depends(get_runtime)):
    return runtime.comparison(access[0], body)


@router.post("/api/insights")
def insights(body: Insights, access=Depends(identity), runtime=Depends(get_runtime)):
    record = runtime.accessible(access[0], body.record_id)
    return insights_payload(record, body.segment)


@router.post("/api/estimate")
def estimate(body: Estimate, access=Depends(identity)):
    settings = RunSettings(n=body.n, concurrency=body.concurrency)
    scenario = normalize_scenario(body.scenario)
    return run_estimate(scenario, settings.n, concurrency=settings.concurrency)


@router.post("/api/hypotheses/rewrite")
def rewrite_hypothesis(body: Rewrite, access=Depends(identity), runtime=Depends(get_runtime)):
    record = runtime.accessible(access[0], body.record_id)
    if runtime.mode == "demo" or record.get("mock"):
        raise ValueError("Переписать текст моделью можно для исследования, запущенного с LLM.")
    found = next((h for h in suggest(record)["items"] if h["id"] == body.hypothesis_id), None)
    if found is None:
        raise ValueError("Гипотеза не найдена.")
    try:
        return {"id": found["id"], "proposal": rewrite_offer(record["scenario"], found), "method": "llm"}
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Запрос к модели не выполнен ({type(exc).__name__}).") from exc
