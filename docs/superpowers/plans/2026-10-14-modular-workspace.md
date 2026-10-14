# Modular Workspace Implementation Plan

> Implement inline using superpowers:executing-plans. Independently scoped HTTP refactoring may run alongside frontend work under dispatching-parallel-agents; one complete review follows integration.

**Goal:** Establish clear application boundaries and a more informative research catalogue without breaking the MVP.
**Architecture:** Modular FastAPI runtime/routers; session-scoped React workspace with focused data hooks and report panels.
**Tech Stack:** Existing Python/FastAPI, React/TypeScript/Vite; no new runtime dependency.
**Spec:** docs/superpowers/specs/2026-10-14-modular-workspace-design.md

## Global Constraints

Preserve187 Python and11 frontend checks; localhost only; schema2 and all routes/cookie/CSRF unchanged. No actual credentials or archive in QA or Git. No client-recomputed simulation metrics. One current-session workspace. Preserve retained pending jobs, exact preview IDs, CAS and guarded download.

## Review Focus

1. Account switch/expired session with in-flight reads: no prior data is mounted again.
2. Older read after retry or successful validation save: no stale replacement.
3. Failed archive load: show retry, not misleading empty success.
4. Split report tabs: unsaved CSV preview and keyboard behavior survive transitions.
5. Two FastAPI factories: independent stores/caches/secrets and identical route errors/guards.

## Task1: HTTP modules

Files: dvoinik/api.py, dvoinik/http/{models,runtime,security,routers}.py or focused route files; tests/test_api.py.
Interfaces: create_app(path=None,mode=None,static_dir=None), COOKIE, app.state.auth/jobs and all HTTP payloads remain compatible. Route modules depend on per-app runtime; runtime uses existing auth/storage/domain functions.
- [x] Confirm clean baseline; use existing HTTP tests as behavior characterization.
- [x] Extract request schemas/runtime/access boundary and focused route groups without new domain logic or global state.
- [x] Verify two separate factories cannot share caches/records; run187 Python tests and Ruff; commit backend paths only.

## Task2: React boundaries and data lifecycle

Files: app/{App,Workspace,useSession,useArchive,useRecord,useJob,useHashRoute}.tsx/ts, features/reports/{ReportPage,Overview,Audience,Voices,ConversionChart,ValidationPanel,useInsights,types}; services/data helpers as needed.
Interfaces: typed session/record/job domain payloads unchanged; focused hooks expose loading/error/retry, current record and pending snapshots. Workspace remounts on cookie session identity.
- [x] Add lifecycle regression tests: latest read wins, invalidating after save rejects old results, disposing rejects writes. Run Vitest to observe RED.
- [x] Implement lifecycle cancellation utility and focused hooks; keep transport epoch guard authoritative for account changes.
- [x] Extract views without changing their simulation/validation meaning; preserve hidden mounted validation panel and native keyboard/modal behavior.
- [x] Run all frontend tests/strict TypeScript/build/format; commit focused frontend boundary changes.

## Task3: Research overview and delivery

Files: Library.tsx/feature helpers, style.css or focused styles, app layout/loading states, docs/architecture.md, README screenshots.
Interfaces: preview rendering consumes saved report conversions/nulls; no estimates or extra API calls. Existing onOpen/onNew/onCompare unchanged.
- [x] Add visible A–E preview and question/audience/quality context per snapshot; restrained cobalt/teal/lilac palette and mobile layout.
- [x] Add loading/failed-refresh/retry states; browser QA with isolated demo and fake accounts, including390px and real run/CSV/import.
- [x] Save screenshots; update architecture docs and plan status from verified results.
- [x] Run full Python/frontend verification; independent whole-diff review and fix material findings.
- [ ] Back up root SQLite, fast-forward clean main, build/restart service, verify preservation, push and observe successful CI.
