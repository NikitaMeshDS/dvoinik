"""Локальное администрирование аккаунтов. Пароли не передаются аргументами команды."""

from __future__ import annotations

import argparse
import getpass
import json
import sqlite3
import sys
import uuid
from pathlib import Path

from dvoinik.auth import AuthError, AuthStore
from dvoinik.settings import storage_path
from dvoinik.storage import ExperimentStore


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Некорректная команда. Используйте --help.\n")


def read_password(args):
    if args.password_file:
        return Path(args.password_file).read_text(encoding="utf-8").rstrip("\r\n")
    first = getpass.getpass("Пароль (12–256 символов): ")
    if first != getpass.getpass("Повторите пароль: "):
        raise AuthError("Пароли не совпадают.")
    return first


def assign_legacy(auth, user_id, record_id=None):
    ExperimentStore(auth.path).list_records()  # Подготовка owner-схемы, исходные записи не меняются.
    backup_path = auth.path.with_name(f"{auth.path.stem}.legacy-assign-{uuid.uuid4().hex[:8]}.sqlite3")
    with auth.connection() as db:
        with sqlite3.connect(backup_path) as backup:
            db.backup(backup)
        backup_path.chmod(0o600)
        db.execute("BEGIN IMMEDIATE")
        if record_id:
            result = db.execute(
                "UPDATE experiments SET owner_id = ? WHERE owner_id IS NULL AND id = ?", (user_id, record_id)
            )
        else:
            result = db.execute("UPDATE experiments SET owner_id = ? WHERE owner_id IS NULL", (user_id,))
        return result.rowcount


def main(argv=None):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--path", help="Путь к архиву SQLite")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    for name in ["create-user", "reset-password"]:
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument("--username", required=True)
        command.add_argument("--password-file", help="Локальный файл пароля для автоматизации; не коммитить")
        if name == "create-user":
            command.add_argument("--name", required=True)
            command.add_argument("--admin", action="store_true")
    for name in ["disable-user", "enable-user"]:
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument("--username", required=True)
    command = commands.add_parser("assign-legacy", allow_abbrev=False)
    command.add_argument("--to", required=True)
    command.add_argument(
        "--record-id", help="Передать одну старую запись; без параметра — все записи без владельца"
    )
    commands.add_parser("list-users")
    args = parser.parse_args(argv)
    try:
        auth = AuthStore(args.path or storage_path())
        if args.command == "create-user":
            auth.create_user(
                args.username, args.name, read_password(args), "admin" if args.admin else "analyst"
            )
            print("Учётная запись создана.")
        elif args.command == "reset-password":
            auth.reset_password(args.username, read_password(args))
            print("Пароль изменён. Предыдущие сессии отозваны.")
        elif args.command == "list-users":
            print(json.dumps(auth.users(), ensure_ascii=False, indent=2))
        else:
            username = (args.to if args.command == "assign-legacy" else args.username).strip().lower()
            user = next((u for u in auth.users() if u["username"] == username), None)
            if not user:
                raise AuthError("Учётная запись не найдена.")
            if args.command == "assign-legacy":
                print(
                    f"Передано исследований: {assign_legacy(auth, user['id'], args.record_id)}. Резервная копия сохранена рядом с архивом."
                )
            else:
                auth.set_active(user["id"], args.command == "enable-user")
                print("Доступ к учётной записи обновлён.")
    except (AuthError, OSError, UnicodeError) as exc:
        # Не печатаем содержимое password-file и введённый пароль.
        print(
            str(exc) if isinstance(exc, AuthError) else "Не удалось прочитать файл или записать изменения.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
