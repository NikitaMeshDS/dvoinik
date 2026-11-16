# Work preservation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for each owned task; shared working copy, separate file ownership.

**Goal:** Implement approved UX iteration1: preserve drafts, protect overwrites, expose form errors and protect survey previews.
**Architecture:** Owner-scoped sessionStorage for draft state only; no CSV persistence. React hooks own recovery and route-leave protection. Existing API and conflict checks remain authoritative.
**Tech Stack:** React, TypeScript, Vitest, existing FastAPI.
**Spec:** ../specs/2026-11-15-user-journeys-design.md

## Global Constraints
- Local modifications only; no commits/push, preserve accumulated changes.
- Draft recovery covers reload in current tab, not cross-device or permanent storage.
- Clear local draft state at logout/session loss; never restore another owner.
- Do not persist respondent CSV to browser storage.

## Review Focus
- Malformed/unavailable browser storage: editing remains available and failure visible (task1).
- Session changes: stale effect cannot overwrite another owner's draft (task1).
- Long/mobile form: focus reaches actual first invalid input on correct step (task2).
- Survey save conflict: preview remains, prior validation remains (task3).
- Back/forward and reload while preview dirty: guard; same-report tabs remain usable (task3).

## Task1: draft lifecycle
Files: app/useDrafts.ts, new app/draftStorage.ts, app/Workspace.tsx, app/useSession.ts, focused tests.
- [x] Add failing tests for reload/active template/step restoration, owner isolation, corrupt storage, unavailable storage and custom overwrite.
- [x] Implement versioned validated sessionStorage payload, saved/error indication, stage setter and explicit reset.
- [x] Clear draft keys on session invalidation/logout including other tabs via existing session event.
- [x] Protect custom replacement with explicit keep/replace choice; return false on cancel so Workspace doesn't navigate.
- [x] Expose optional Composer props: step?: number; onStepChange?: (step:number)=>void; draftStatus?: string; onReset?: ()=>void. Parent controls stage when supplied.
- [x] Run focused tests then notify root; don't edit Composer (task2 owns it).

## Task2: form errors and recovery UI
Files: draft.ts, Composer.tsx, styles/composer.css, composer-navigation.test.tsx.
- [x] Add failing user-visible tests for blank title/question/offer, invalid audience and first-field focus.
- [x] Structured validation retains draftError compatibility. Associate error with field using aria-describedby/aria-invalid; focus/scroll actual field and select correct stage.
- [x] Consume optional props from task1, show storage scope/status and explicit reset. Maintain uncontrolled fallback.
- [x] Run focused tests and build.

## Task3: survey preview lifecycle
Files: features/reports/ValidationPanel.tsx, ReportPage.tsx, new hook if needed, validation-upload.test.tsx.
- [x] Add failing tests for replacement label/count/date, preserving previous validation, dirty preview on leave and clear guard after save.
- [x] Show previous/new evaluation counts and dated replacement action, offer existing full snapshot JSON export before replace.
- [x] Add explicit discard preview; warn on leaving report or browser reload while preview unsaved, but permit same-report tabs. Retain existing conflict retry; no CSV storage.
- [x] Run targeted tests; do not edit Workspace or Composer.

## Final verification
- [x] Full frontend tests, TypeScript/Vite build, diff check.
- [x] Independent review of session/guard interactions, fix findings.
- [x] Browser: edited draft→reload, invalid fields, overwrite cancel, CSV preview→leave/cancel/discard. Verify mobile readability.

## Итог проверки — 16 ноября 2026

94 frontend-теста прошли; TypeScript/Vite build и git diff --check успешны.
В браузере проверены ошибки поля с фокусом, восстановление текста и шага после reload,
сохранность CSV-предпросмотра между вкладками, отмена ухода и явная отмена предпросмотра.
Изоляция владельца, очистка при logout/session loss, защита custom-черновика,
замена проверки и конфликты сохранения покрыты автоматическими проверками.
Независимый обзор выявил обход защиты через меню аккаунта; исправлено общим событием
перед программной навигацией и logout. Ошибка после сброса формы также устранена.

Ограничение: отмена браузерного Back возвращает текущий URL через pushState;
следующий Back доступен, но ветка Forward очищается. Полное сохранение истории требует
маршрутизатора с индексами переходов; данные предпросмотра при отмене остаются.
Черновики не синхронизируются между устройствами, CSV не записывается в browser storage.
Все изменения локальные, без commit/push.
