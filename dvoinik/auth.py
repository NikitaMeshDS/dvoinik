"""Локальные аккаунты. В браузер не передаются хеши паролей или токены сессии."""

from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from .storage import ExperimentStore, StorageError

IDLE_SECONDS = 1800
SESSION_SECONDS = 28800
LOGIN_ERROR = "Логин или пароль неверны."
HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


class AuthError(ValueError):
    pass


class AccessExpired(StorageError):
    pass


@dataclass(frozen=True)
class Principal:
    id: str
    username: str
    name: str
    role: str


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _username(value):
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.@-]{2,79}", value):
        raise AuthError("Логин: 3–80 латинских букв, цифр или символов . _ @ -.")
    return value


def _password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 256 or not value.strip():
        raise AuthError("Пароль должен содержать от 12 до 256 символов.")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise AuthError("Пароль содержит некорректный текст.") from exc


class AuthStore:
    def __init__(self, path, *, clock=time.time, allow_demo=False):
        self.path = Path(path)
        self.clock = clock
        self.allow_demo = allow_demo
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                    password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at REAL NOT NULL,
                    last_seen REAL NOT NULL, demo INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS login_attempts (username_hash TEXT NOT NULL, attempted_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS attempts_time ON login_attempts(attempted_at);
                CREATE TABLE IF NOT EXISTS export_links (
                    handle_hash TEXT PRIMARY KEY, session_hash TEXT NOT NULL,
                    payload BLOB NOT NULL, mime TEXT NOT NULL, filename TEXT NOT NULL, expires_at REAL NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.path, timeout=5)
            db.row_factory = sqlite3.Row
            self.path.chmod(0o600)
            with db:
                yield db
        except (OSError, sqlite3.Error) as exc:
            raise AuthError("Хранилище доступа недоступно. Обратитесь к администратору.") from exc
        finally:
            if db is not None:
                db.close()

    def create_user(self, username, name, password, role="analyst"):
        username = _username(username)
        _password(password)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or role not in {"admin", "analyst"}:
            raise AuthError("Укажите имя до 80 символов и роль admin или analyst.")
        try:
            name.encode("utf-8")
        except UnicodeError as exc:
            raise AuthError("Имя содержит некорректный текст.") from exc
        user_id = uuid.uuid4().hex
        password_hash = HASHER.hash(password)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                raise AuthError("Этот логин уже используется.")
            db.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, 1)",
                (user_id, username, name.strip(), password_hash, role),
            )
        return user_id

    def users(self):
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute("SELECT id, username, name, role, active FROM users ORDER BY username")
            ]

    def login(self, username, password):
        try:
            key = _username(str(username))
        except AuthError as exc:
            raise AuthError(LOGIN_ERROR) from exc
        if not isinstance(password, str) or len(password) > 256:
            raise AuthError(LOGIN_ERROR)
        now = self.clock()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (now - 300,))
            count = db.execute(
                "SELECT count(*) FROM login_attempts WHERE username_hash = ?", (digest(key),)
            ).fetchone()[0]
            global_count = db.execute(
                "SELECT count(*) FROM login_attempts WHERE attempted_at >= ?", (now - 60,)
            ).fetchone()[0]
            if count >= 5 or global_count >= 100:
                raise AuthError("Слишком много попыток входа. Повторите через несколько минут.")
            user = db.execute("SELECT * FROM users WHERE username = ?", (key,)).fetchone()
            try:
                verified = HASHER.verify(user["password_hash"] if user else DUMMY_HASH, password)
            except (VerificationError, ValueError):
                verified = False
            valid = bool(user and user["active"] and verified)
            if not valid:
                db.execute("INSERT INTO login_attempts VALUES (?, ?)", (digest(key), now))
            else:
                db.execute("DELETE FROM login_attempts WHERE username_hash = ?", (digest(key),))
                token = self._session(db, user["id"], now)
        # Ошибка вне транзакции: неудачная попытка должна оставаться в базе.
        if not valid:
            raise AuthError(LOGIN_ERROR)
        return token

    def _session(self, db, user_id, now, demo=False):
        token = secrets.token_urlsafe(32)
        db.execute(
            "DELETE FROM sessions WHERE created_at <= ? OR last_seen <= ?",
            (now - SESSION_SECONDS, now - IDLE_SECONDS),
        )
        db.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)", (digest(token), user_id, now, now, int(demo))
        )
        return token

    def create_demo_session(self):
        if not self.allow_demo:
            raise AuthError("Демо без входа отключено.")
        with self.connection() as db:
            return self._session(db, "__demo__", self.clock(), demo=True)

    def _resolve(self, db, token_hash):
        row = db.execute(
            "SELECT s.*, u.username, u.name, u.role, u.active FROM sessions s "
            "LEFT JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (token_hash,),
        ).fetchone()
        now = self.clock()
        if not row or now - row["created_at"] >= SESSION_SECONDS or now - row["last_seen"] >= IDLE_SECONDS:
            raise AuthError("Сессия завершена. Войдите снова.")
        if row["demo"] and self.allow_demo:
            return Principal("__demo__", "demo", "Демо-пространство", "demo")
        if row["demo"] or not row["active"]:
            raise AuthError("Сессия завершена. Войдите снова.")
        return Principal(row["user_id"], row["username"], row["name"], row["role"])

    def resolve(self, token, *, touch=False):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise AuthError("Сессия завершена. Войдите снова.")
        with self.connection() as db:
            user = self._resolve(db, digest(token))
            if touch:
                db.execute(
                    "UPDATE sessions SET last_seen = ? WHERE token_hash = ?", (self.clock(), digest(token))
                )
        return user

    def logout(self, token):
        with self.connection() as db:
            db.execute("DELETE FROM export_links WHERE session_hash = ?", (digest(token),))
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (digest(token),))

    def set_active(self, user_id, active):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            user = db.execute("SELECT role, active FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                raise AuthError("Учётная запись не найдена.")
            if not active and user["role"] == "admin" and user["active"]:
                remaining = db.execute(
                    "SELECT count(*) FROM users WHERE role = 'admin' AND active = 1"
                ).fetchone()[0]
                if remaining <= 1:
                    raise AuthError("Нельзя отключить последнего активного администратора.")
            db.execute("UPDATE users SET active = ? WHERE id = ?", (int(active), user_id))
            if not active:
                db.execute(
                    "DELETE FROM export_links WHERE session_hash IN (SELECT token_hash FROM sessions WHERE user_id = ?)",
                    (user_id,),
                )
                db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def reset_password(self, username, password):
        _password(password)
        username = _username(username)
        password_hash = HASHER.hash(password)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            user = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if not user:
                raise AuthError("Учётная запись не найдена.")
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user["id"]))
            db.execute(
                "DELETE FROM export_links WHERE session_hash IN (SELECT token_hash FROM sessions WHERE user_id = ?)",
                (user["id"],),
            )
            db.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
            db.execute("DELETE FROM login_attempts WHERE username_hash = ?", (digest(username),))

    def workspace(self, token):
        user = self.resolve(token)

        def guard():
            try:
                current = self.resolve(token)
                if current.id != user.id:
                    raise AuthError("Сессия завершена.")
            except AuthError as exc:
                raise AccessExpired("Доступ завершён. Войдите снова.") from exc

        return ExperimentStore(self.path, owner_id=user.id, guard=guard)

    def issue_export(self, token, data, mime, filename):
        if isinstance(data, str):
            data = data.encode("utf-8")
        if not isinstance(data, bytes) or len(data) > 10 * 1024 * 1024:
            raise AuthError("Максимальный размер скачивания — 10 МБ.")
        if mime not in {"application/json", "text/csv"} or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,180}", filename
        ):
            raise AuthError("Недопустимый формат или имя файла.")
        handle = secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._resolve(db, digest(token))
            db.execute(
                "DELETE FROM export_links WHERE expires_at <= ? OR session_hash NOT IN (SELECT token_hash FROM sessions)",
                (self.clock(),),
            )
            db.execute(
                "DELETE FROM export_links WHERE handle_hash IN (SELECT handle_hash FROM export_links WHERE session_hash = ? ORDER BY expires_at DESC LIMIT -1 OFFSET 127)",
                (digest(token),),
            )
            db.execute(
                "INSERT INTO export_links VALUES (?, ?, ?, ?, ?, ?)",
                (digest(handle), digest(token), data, mime, filename, self.clock() + 900),
            )
        return handle

    def export_available(self, handle, token):
        with self.connection() as db:
            self._resolve(db, digest(token))
            row = db.execute(
                "SELECT 1 FROM export_links WHERE handle_hash = ? AND session_hash = ? AND expires_at > ?",
                (digest(handle), digest(token), self.clock()),
            ).fetchone()
            return row is not None

    def consume_export(self, handle, *, head=False):
        if not isinstance(handle, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", handle):
            raise AuthError("Ссылка недоступна. Подготовьте скачивание заново в приложении.")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM export_links WHERE handle_hash = ?", (digest(handle),)).fetchone()
            if not row or row["expires_at"] <= self.clock():
                raise AuthError("Ссылка недоступна. Подготовьте скачивание заново в приложении.")
            self._resolve(db, row["session_hash"])
            if not head:
                db.execute("DELETE FROM export_links WHERE handle_hash = ?", (digest(handle),))
            return bytes(row["payload"]), row["mime"], row["filename"]
