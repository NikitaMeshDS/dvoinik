# Modular research workspace

The user requested stronger architecture and a better research interface after the React migration. This iteration preserves accounts, archive schema2, API routes, cookie/CSRF guards, model behavior and the existing guided workflow. The working application remains local.

## Chosen design

A modular monolith fits the current MVP: one deployment and database, explicit application-service boundaries. Cosmetic cleanup alone leaves session/data orchestration coupled; a new distributed backend would add operational requirements without serving this local research workflow. Server modules separate HTTP access, research, survey and export responsibilities. React separates the session lifetime, archive/report data, job polling, workspace layout and report panels.

## Boundaries

- `dvoinik/api.py` remains the compatible factory entry point. `dvoinik/http/` owns strict request models, runtime services, HTTP security/errors and route groups. Existing domain modules and Jobs remain authoritative for metrics and storage. `app.state.auth/jobs` stay compatible with isolated integration tests.
- `frontend/src/app/` owns session lifecycle, hash navigation, archive loading, report loading, job polling and layout. Workspace data belongs to a mounted cookie session: changing it disposes the whole workspace. No private browser persistence.
- `frontend/src/features/reports/` owns report panels, chart, validation and insights loading. Shared API/domain types and UI primitives remain reusable.
- A small request lifecycle utility prevents late completions from replacing a newer load or saved result; cancellation and authentication epochs retain their distinct purposes.

## Interface direction

Preserve cobalt #3154c9, teal #137d76, lilac #7d65b4, ink #202b38, muted #6c7886 and paper #f5f7fb. Use local system typography, strong research titles, compact navigation and restrained surfaces. The catalogue becomes a research overview: each snapshot shows its question, audience, A–E response preview and verification state. Percentages come directly from the server snapshot. Ties and missing answers remain explicit. One row opens the report; import/comparison remain in the menu.

Loading must not look like an empty archive. Unavailable data offers a retry; existing data stays readable after a failed refresh. Report panels retain CSV previews across tab changes, roving keyboard navigation, focus return, responsive tables and clear demo labeling. UI errors do not expose provider credentials.

## Acceptance

All187 existing Python and11 frontend checks remain green. API factories remain independent: two apps must not share runtime caches or owners. Request lifecycle tests pin latest-wins and disposal, including a save invalidating an earlier read. Browser QA on an isolated mock database covers sample/run/archive/import/compare/validation/reload/logout, keyboard and390px. No real credentials or real archive are used for QA. Update architecture documentation and real screenshots, review the complete diff independently, fast-forward clean main, back up actual SQLite before restart, push and verify CI.
