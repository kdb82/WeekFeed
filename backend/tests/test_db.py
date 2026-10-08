import sqlite3

import pytest

from weekfeed.store.db import connect, migrate, transaction

TABLES = {
    "settings", "projects", "repos", "commits", "items", "drafts",
    "draft_messages", "agent_batches", "batch_changes", "search_index",
}


def test_migrate_creates_schema_and_sets_version(tmp_path):
    c = connect(tmp_path / "a.db")
    migrate(c)
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert TABLES <= names
    assert c.execute("PRAGMA user_version").fetchone()[0] == 1


def test_migrate_is_idempotent(tmp_path):
    c = connect(tmp_path / "a.db")
    migrate(c)
    migrate(c)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 1


def test_connection_pragmas(tmp_path):
    c = connect(tmp_path / "a.db")
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert c.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_transaction_rolls_back_on_error(conn):
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute("INSERT INTO settings(key, value) VALUES ('a', '1')")
            raise RuntimeError("boom")
    assert conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0


def test_nested_transaction_joins_outer(conn):
    with transaction(conn):
        with transaction(conn):
            conn.execute("INSERT INTO settings(key, value) VALUES ('a', '1')")
    assert conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 1


@pytest.mark.parametrize("kind,status", [("note", "done"), ("todo", "resolved"), ("blocker", "done")])
def test_items_reject_status_that_does_not_fit_kind(conn, kind, status):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO items(label, kind, text, status, created_at, updated_at) VALUES ('work', ?, 'x', ?, 't', 't')",
            (kind, status),
        )


def test_only_one_in_progress_draft_per_scope_and_kind(conn):
    sql = ("INSERT INTO drafts(kind, label, project_id, period_start, period_end, status, sections, created_at) "
           "VALUES (?, 'work', NULL, 's', 'e', ?, '[]', 't')")
    conn.execute(sql, ("standup", "in_progress"))
    conn.execute(sql, ("weekly", "in_progress"))
    conn.execute(sql, ("standup", "saved"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, ("standup", "in_progress"))
