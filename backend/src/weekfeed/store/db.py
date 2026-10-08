"""Connections, transactions and schema migrations."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

MIGRATIONS = ["0001_initial.sql", "0002_batch_draft_snapshots.sql"]


def connect(path: Path | str) -> sqlite3.Connection:
    # isolation_level=None: autocommit, with explicit BEGIN via transaction().
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    if conn.in_transaction:  # nested: the outer transaction owns commit/rollback
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, name in enumerate(MIGRATIONS, start=1):
        if version <= current:
            continue
        sql = resources.files("weekfeed.store.migrations").joinpath(name).read_text()
        try:
            conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
