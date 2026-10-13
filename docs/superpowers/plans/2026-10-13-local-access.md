# Local Access Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task with a final independent review.

**Goal:** локальный вход, изоляция исследований и отзыв доступа к экспорту после выхода или блокировки.

**Architecture:** SQLite хранит аккаунты, хеши токенов и владельцев записей. Streamlit допускает к рабочему пространству только проверенную серверную сессию. Отдельный HTTP-сервис выдаёт только подготовленные одноразовые файлы по краткоживущим ссылкам, связанным с действующей сессией; публичный media-route не используется для отчётов.

**Tech Stack:** Python 3.11/3.12, Streamlit 1.65, SQLite, argon2-cffi 25.1, стандартный HTTPServer.

**Spec:** `docs/access-proposal.md`. Выбран локальный вариант; отдельного SSO сейчас нет.

## Global Constraints

- Пароли: Argon2id, память 19456 KiB, два прохода, parallelism=1; длина 12–256 символов.
- Режим `local` по умолчанию; `demo` явно включается и использует отдельный архив, LLM отключена.
- Idle timeout 30 минут, абсолютный срок 8 часов; logout, блокировка и reset отзывают сессии.
- Логин: ASCII 3–80 символов, регистр нормализуется; ошибки входа не раскрывают существование аккаунта.
- Пять неудачных попыток на логин за 5 минут, общий предел 100 за минуту; лимиты хранятся на сервере.
- Владелец не берётся из JSON. Старые записи остаются без владельца, миграция создаёт резервную копию.
- Ссылка экспорта: 15 минут, одна выдача, проверка действующей сессии, no-store/no-referrer; токены и payload не пишутся в логи.
- Сервис привязан к localhost. Сетевой пилот требует TLS/шлюз/SSO; пароль и bootstrap-файл исключены из Git.

## Review Focus

- Две одновременные попытки скачивания: ровно одна получает файл.
- Другая учётка с тем же ID записи: нет чтения или перезаписи.
- Истечение доступа при несохранённом опросе: нет retry под следующей учёткой.
- Unicode/переводы строк в логине, имени файла и ошибках: нет HTML/header injection.
- Неверная конфигурация и недоступная база: закрытый доступ, без перехода к общему архиву.

### Task 1: Accounts, Sessions, Ownership

Files: `dvoinik/auth.py`, `dvoinik/storage.py`, `tests/test_auth.py`, `tests/test_storage.py`, `requirements.txt`.
Interfaces: `AuthStore(path, clock=time.time, allow_demo=False)`; `create_user(username, name, password, role='analyst') -> id`; `login(username,password) -> token`; `resolve(token,touch=False) -> Principal`; `logout(token)`; `workspace(token) -> ExperimentStore`. Principal содержит id, username, name, role. Store получает серверный owner_id и guard; методы list/save/get проверяют доступ.

- [ ] RED: тесты входа, одинаковой ошибки неизвестного логина/пароля, лимита из второй сессии, idle/absolute deadline, блокировки/reset/logout, изоляции двух владельцев, непередачи legacy первому пользователю.
```python
token = auth.login("alice", "a sufficiently long password")
alice = auth.workspace(token)
alice.save(record)
assert auth.workspace(bob_token).list_records() == []
```
- [ ] Run: `python -m pytest tests/test_auth.py tests/test_storage.py -q` — новые тесты сначала FAIL.
- [ ] Implement: параметризованные SQL, BEGIN IMMEDIATE для мутаций, хеши паролей/токенов, backup перед owner-миграцией. Проверить guard повторно перед записью в транзакции.
- [ ] GREEN: focused tests и полный `python -m pytest -q`; commit `feat: add local accounts and isolated experiment archives`.

### Task 2: Protected Exports and Service Launcher

Files: `dvoinik/downloads.py`, `serve.py`, `tests/test_downloads.py`.
Interfaces: `AuthStore.issue_export(token,data,mime,filename) -> handle`; `consume_export(handle) -> (bytes,mime,filename)`; `create_download_server(auth,port=0) -> ThreadingHTTPServer`.

- [ ] RED: реальные HTTP-тесты без handle, с изменённым handle, после logout/disable/timeout; однократность и гонка двух запросов; CSV/JSON content-disposition и безопасные заголовки.
```python
handle = auth.issue_export(token, b"{}", "application/json", "report.json")
assert download(handle).status == 200
assert download(handle).status == 410
```
- [ ] Run `python -m pytest tests/test_downloads.py -q` — сначала FAIL.
- [ ] Implement: payload ограничен 10 MiB, endpoint только GET/HEAD download, без файловой системы; атомарная выдача, общий JSON/plain-text отказ без данных записи. Launcher запускает оба сервиса и завершает дочерний процесс при выходе.
- [ ] GREEN: HTTP suite и полный suite; commit `feat: protect report downloads with revocable session links`.

### Task 3: Login, Logout, Account Administration and CLI

Files: `dvoinik/auth_ui.py`, `dvoinik/download_ui.py`, `manage.py`, `app.py`, `dvoinik/ui.py`, `dvoinik/library.py`, `assets/style.css`, `tests/test_auth_app.py`, `tests/test_app.py`, `tests/test_manage.py`.
Interfaces: `require_access(path,mode) -> (AuthStore,token,Principal)` before archive initialization; secure download replaces public st.download_button. CLI create-user/reset-password uses getpass or explicit local password-file, disable/enable and assign-legacy have named targets.

- [ ] RED: гость не читает archive и не запускает модель; вход/выход очищают history, active_record, saved_inputs, pending; новый пользователь не видит старый файл; ошибка конфигурации закрывает вход; demos не обращаются к LLM. Existing tests явно используют demo-mode.
- [ ] Run `python -m pytest tests/test_auth_app.py tests/test_manage.py tests/test_app.py -q` — новые тесты сначала FAIL.
- [ ] Implement: форма входа, отображение учётки, выход с подтверждением при pending, фоновая проверка срока без продления idle. Администратор видит аккаунты без хешей; CLI выполняет backup/назначение legacy явно. При отказе auth запись не становится обычной ошибкой диска.
- [ ] GREEN: полный suite, Ruff, браузер с двумя отдельными тестовыми аккаунтами, скачивание и отзыв ссылки; commit `feat: integrate account access into research workspace`.

### Task 4: Delivery

Files: README, .env.example, .streamlit/config.toml, docs/access-proposal.md, docs/images/login.png.
- [ ] Обновить команды запуска/создания учётки/назначения архива, сроки сессии и границы прототипа.
- [ ] Проверить real-model mode не объявлять протестированным: тесты используют демо и изолированный транспорт.
- [ ] Fresh independent security review, исправления с regression tests, полный suite/Ruff/diff-check.
- [ ] Перенести проверенные коммиты в основную папку, запустить сервис, push main и проверить CI. Игнорируемые аккаунты/архивы не коммитить.

## Execution evidence

- Tasks 1–3 implemented together: account/session/owner checks, one-time HTTP exports, UI and administration CLI share one access boundary. Consolidated feature commit replaces the three proposed intermediate feature commits.
- New behavior tests were observed failing before implementation. Independent review reproduced three additional defects (failed logout, consumed export cache, relative archive path); all three regression tests were observed failing, then passing after fixes.
- Final local verification: 141 tests passed; Ruff check/format and git diff --check passed. Includes actual HTTP concurrent consumption, revoked links, owner isolation, legacy validation preservation, failed logout and unavailable access database.
- Browser: wrong password refused; Alice created/saved an experiment and downloaded its JSON (file contents verified); Bob saw zero studies; Alice re-login restored one study. Login checked at 1440 px and 390 px, viewport reset afterward.
- Review rulings: a one-time export URL is a bearer secret tied to a live server session, documented as such; local accounts do not imply SSO or certification. On database failure logout remains pending and another login is blocked.
- No real LLM endpoint, bank SSO or live respondent accuracy was validated in this iteration.
- Delivery: user already authorized pushing all project changes, so main integration and push follow that instruction without another approval menu.
