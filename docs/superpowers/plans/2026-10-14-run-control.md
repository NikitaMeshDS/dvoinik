# Run Control Implementation Plan

> Implement inline using superpowers:executing-plans; one independent whole-branch review before delivery.

**Goal:** Make existing runs discoverable and cancellable across workspace navigation.
**Architecture:** Existing per-app Jobs owns cancellation and active discovery; session-scoped React hooks monitor progress separately from navigation.
**Tech Stack:** Python/FastAPI, React/TypeScript/Vite, existing dependencies.
**Spec:** docs/superpowers/specs/2026-10-14-run-control-design.md

## Global Constraints

Node 24.15+, Python 3.11+. No new runtime dependencies. Preserve account, password, archive and localhost access boundaries. Original cookie owns runs; GET polling never extends idle TTL. No partial result on cancellation; no persisted queue or restart resumption promised.

## Review Focus

1. Cancel during an in-flight provider call: next evaluation cannot start, capacity remains occupied until cleanup.
2. Queued cancellation: no engine call and exactly one capacity release.
3. Cancel after completion: preserve persisted record and downloadability.
4. Background polling failures: retain last known state, show retry, suppress unmounted callbacks.
5. Navigate during completion: archive updates without forcing user away from current work.

## Task1: Jobs lifecycle and HTTP

Files: dvoinik/jobs.py, dvoinik/http/routers/research.py, dvoinik/http/security.py; tests/test_api.py, tests/test_engine.py.
Interfaces: active(token)->list[dict]; cancel(token,job_id)->dict; GET /api/runs->{jobs}; POST /api/runs/{id}/cancel->Job. New statuses cancelling/cancelled.
- [x] Write cancellation, discovery, session/CSRF and TTL regressions; run pytest to observe RED.
- [x] Add Future/cancel flag, guard interruption and original-session active discovery. Guard save and cancellation under existing lock; include cancelling in active retention.
- [x] Verify all Python tests/Ruff; commit backend changes and tests.

## Task2: Workspace monitoring and controls

Files: frontend/src/app/{useJob,Workspace}.ts/tsx, frontend/src/JobView.tsx, frontend/src/Composer.tsx, frontend/src/types.ts, frontend/src/styles/activity.css.
Interfaces: useJob(route,onFinished)->{job,active,error,refresh,accept}. One monitor handles discovery and terminal events; Workspace owns navigation. accept(Job) applies a confirmed mutation before re-reading.
- [x] Write actual React hook regressions for discovery, completion, transient error and unmount; observe Vitest RED.
- [x] Monitor original-session active run globally with guarded requests and bounded timers; show compact route link, cancellation action and truthful terminal/error states.
- [x] Verify complete frontend suite, TypeScript/build/Prettier; commit frontend change.

## Task3: Review and delivery

Files: README.md, docs/architecture.md and this plan.
- [x] Run isolated browser QA for route/reload/control and mobile width; document behavior and process-restart limitation.
- [x] Run full suites; obtain independent whole-branch review, address material findings with regression tests.
- [ ] Back up real SQLite and compare archive/account manifests before/after fast-forward/build/restart.
- [ ] Push main, observe exact-commit successful CI; mark plan complete.
