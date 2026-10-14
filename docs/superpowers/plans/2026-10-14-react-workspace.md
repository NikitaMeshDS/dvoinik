# React Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace the main Streamlit experience with React while retaining the verified Python MVP behavior.

**Architecture:** The same-origin FastAPI service wraps existing domain functions and owner-scoped storage. Bounded background jobs expose actual engine progress. React owns presentation and draft state; Python owns authentication, validation, results and persistence.

**Tech Stack:** React, TypeScript, Vite; FastAPI, Python 3.11/3.12, SQLite, existing Argon2 and domain modules.

**Spec:** `docs/superpowers/specs/2026-10-14-react-workspace-design.md`

## Global Constraints

- Service listens on 127.0.0.1; no public web deployment or SSO change.
- Existing accounts, owner IDs, archive JSON schema 2 and CLI behavior remain compatible.
- HttpOnly SameSite Strict session cookie; no session token in JSON, URLs or localStorage.
- At most two engine workers and one active run per owner; progress polling does not touch idle time.
- Preserve 153 existing checks and add meaningful API tests against an isolated database.
- No client-supplied owner, result percentages or trusted validation metrics.
- Keep demo mock-only and visibly distinct from a validated forecast.

## Review Focus

1. Session revocation during a run: guard prevents returning or writing a result.
2. Unknown/foreign experiment and job IDs: no existence or payload disclosure.
3. Storage error after completed simulation: snapshot can be downloaded/retried by its original session.
4. Concurrent survey updates: second save conflicts and does not erase the first.
5. Navigation/logout while a request is pending: stale responses do not repopulate another user's UI.

## Task 1: API and jobs

**Files:** Create `dvoinik/api.py`, `dvoinik/jobs.py`, `tests/test_api.py`; modify `requirements.txt`, `requirements-dev.txt` only for pinned dependencies.

**Interfaces:** Produces `create_app(path=None, mode=None, static_dir=None) -> FastAPI`, matching the complete route table in the spec. Consumes `AuthStore.workspace`, `RunSettings`, `run_experiment`, `attach_validation`, `load_experiment`, `compare_runs` and existing export methods.

- [x] Write tests using `TestClient(create_app(tmp_path / 'app.sqlite3', mode='local'))`; an unauthenticated `GET /api/experiments` returns 401.
- [x] Exercise separate admin/analyst cookies: another owner's record and job return 404; admin can manage users but cannot read their records.
- [x] Send mutating requests with a foreign Origin or missing CSRF header and assert rejection. Verify demo API forces mock and a status poll does not extend idle lifetime.
- [x] Run `python -m pytest -q tests/test_api.py` and record the initial failure before writing endpoints.
- [x] Implement session dependencies and response errors, bounded jobs, owner-scoped records/import/comparison, survey preview/CAS, and protected exports according to the spec.
- [x] Pin and test run revocation, bounded queue, failed storage/export/retry and concurrent validation conflicts.
- [x] Run API tests and existing auth/storage/run/download tests; commit the focused backend changes.

## Task 2: React workspace

**Files:** Create `frontend/package.json`, lockfile, Vite/TypeScript config, `index.html`, `src/types.ts`, `src/api.ts`, `src/draft.ts`, `src/App.tsx`, focused page/component files and `src/style.css`.

**Interfaces:** Consumes the spec HTTP contracts; API requests use the same origin and in-memory CSRF token. Session/record/run data are typed. UI exports request a protected server URL instead of materializing private payloads into static media.

- [x] Define the API types and client; HTTP 401 clears workspace state, and failed logout remains visibly blocked until server revocation succeeds.
- [x] Implement login, archive search/filter/page, owner-bound transient drafts, two-step editor with hidden D/E retention and server audience preview.
- [x] Implement actual run progress, guarded recovery/export, matrix and selected segment report, profiles, voices and survey preview/save/conflict.
- [x] Implement comparison, sample/import/reuse, methodology and admin activation controls. Export actions live in accessible menus.
- [x] Build with `npm ci` and `npm run build`; TypeScript must pass without weakening strict checks.
- [x] Verify browser paths against a separate mock API: default sample, edited run, archive/reuse, compare, CSV/import/download, 390 px and keyboard menus.
- [x] Save real screenshots and commit the frontend.

## Task 3: Integration and release

**Files:** Modify `serve.py`, `.gitignore`, `.github/workflows/checks.yml`, `README.md`, `docs/development.md`, `docs/demo.md`, `docs/architecture.md`; retain `app.py` and Streamlit modules for the explicit fallback.

**Interfaces:** `python serve.py` serves the built React app plus API/download routes; `python serve.py --ui streamlit` preserves the former local launcher. `DVOINIK_AUTH_MODE=demo` remains a separate mock-only archive.

- [x] Add launcher selection and a clear missing-build message; document exact install/build/run commands.
- [x] Add frontend installation/build to CI while retaining Python tests on 3.11 and 3.12.
- [x] Run all Python tests, Ruff checks and frontend build; review the whole branch independently before merge.
- [x] Make an ignored local backup of the working SQLite database and confirm existing IDs/validation survive after switching the service.
- [ ] Fast-forward clean main, push the public repository and verify CI on the published SHA.
- [x] Restart the main local service only after acceptance checks pass; keep fallback and CLI usable. Reset browser viewport, close temporary QA tabs and deliver screenshots.

## Self-review

Every spec route belongs to Task 1 and has a Task 2 consumer. Background jobs retain the original session guard, validation uses the existing CAS, and protected export never trusts browser-supplied result values. Task 3 owns deployment/build and preservation checks. The five review conditions above are exercised in API tests or browser verification; no unrelated domain rewrite is included.
