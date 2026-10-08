from __future__ import annotations

import json
import sqlite3
from typing import Any


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return default if r is None else json.loads(r["value"])


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def get_my_emails(conn: sqlite3.Connection) -> list[str]:
    return list(get_setting(conn, "my_emails", []))


def set_my_emails(conn: sqlite3.Connection, emails: list[str]) -> None:
    set_setting(conn, "my_emails", sorted({e.strip().lower() for e in emails if e.strip()}))


def get_github_username(conn: sqlite3.Connection) -> str:
    return get_setting(conn, "github_username", "")


def set_github_username(conn: sqlite3.Connection, username: str) -> None:
    set_setting(conn, "github_username", username.strip())
