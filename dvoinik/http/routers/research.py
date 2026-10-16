"""Research HTTP routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from ...experiments import (
    CUSTOM_SCENARIO,
    load_experiment,
    normalize_population,
    normalize_scenario,
    quality_status,
)
from ...insights import segment_report
from ...planning import baseline_agreement, leader_stability, live_check_plan, run_estimate
from ...population import SEGMENTS, allocate_population
from ...reporting import summarize
from ...runs import RunSettings
from ...scenarios import SCENARIOS
from ..models import Compare, Estimate, Import, Insights, Preview, Run
from ..runtime import get_runtime
from ..security import identity

router = APIRouter()


@router.get("/api/catalog")
def catalog(access=Depends(identity)):
    return {"scenarios": {**SCENARIOS, "custom": CUSTOM_SCENARIO}, "segments": SEGMENTS}


@router.post("/api/preview")
def preview(body: Preview, access=Depends(identity)):
    RunSettings(n=body.n)
    shares = normalize_population(body.population)
    return {"counts": allocate_population(body.n, shares), "shares": shares}


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


@router.post("/api/runs/{job_id}/retry")
def retry(job_id: str, access=Depends(identity), runtime=Depends(get_runtime)):
    return runtime.jobs.retry(access[0], job_id)


@router.post("/api/compare")
def compare(body: Compare, access=Depends(identity), runtime=Depends(get_runtime)):
    return runtime.comparison(access[0], body)


@router.post("/api/insights")
def insights(body: Insights, access=Depends(identity), runtime=Depends(get_runtime)):
    record = runtime.accessible(access[0], body.record_id)
    report = record["report"] if body.segment == "all" else segment_report(record, body.segment)
    result = {
        "report": report,
        "summary": summarize(report),
        "quality": quality_status(record),
        "stability": leader_stability(report),
    }
    if body.segment == "all":
        result["plan"] = live_check_plan(record)
        result["baseline"] = baseline_agreement(record)
    return result


@router.post("/api/estimate")
def estimate(body: Estimate, access=Depends(identity)):
    settings = RunSettings(n=body.n, concurrency=body.concurrency)
    scenario = normalize_scenario(body.scenario)
    return run_estimate(scenario, settings.n, concurrency=settings.concurrency)
