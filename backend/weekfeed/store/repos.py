from __future__ import annotations

import sqlite3

from .errors import Conflict, NotFound
from .models import Repo, Scope
from .projects import get_project


def _row(r: sqlite3.Row) -> Repo:
    return Repo(
        id=r["id"], project_id=r["project_id"], path=r["path"], display_name=r["display_name"],
        added_at=r["added_at"], last_fetched_at=r["last_fetched_at"], last_fetch_error=r["last_fetch_error"],
    )


def add_repo(conn: sqlite3.Connection, project_id: int, path: str, display_name: str, *, now: str) -> Repo:
    get_project(conn, project_id)
    try:
        cur = conn.execute(
            "INSERT INTO repos(project_id, path, display_name, added_at) VALUES (?, ?, ?, ?)",
            (project_id, path, display_name, now),
        )
    except sqlite3.IntegrityError as e:
        owner = conn.execute(
            "SELECT p.name FROM repos r JOIN projects p ON p.id = r.project_id WHERE r.path = ?", (path,)
        ).fetchone()
        raise Conflict(f"Already added to {owner['name']}" if owner else "Repo already added") from e
    return get_repo(conn, cur.lastrowid)


def get_repo(conn: sqlite3.Connection, repo_id: int) -> Repo:
    r = conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone()
    if r is None:
        raise NotFound(f"Repo {repo_id} not found")
    return _row(r)


def list_repos(conn: sqlite3.Connection, scope: Scope | None = None) -> list[Repo]:
    if scope is None:
        rows = conn.execute("SELECT * FROM repos ORDER BY id")
    elif scope.project_id is not None:
        rows = conn.execute("SELECT * FROM repos WHERE project_id = ? ORDER BY id", (scope.project_id,))
    else:
        rows = conn.execute(
            "SELECT r.* FROM repos r JOIN projects p ON p.id = r.project_id WHERE p.label = ? ORDER BY r.id",
            (scope.label,),
        )
    return [_row(r) for r in rows]


def remove_repo(conn: sqlite3.Connection, repo_id: int) -> None:
    get_repo(conn, repo_id)
    conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))


def record_fetch(conn: sqlite3.Connection, repo_id: int, *, at: str, error: str | None) -> None:
    """last_fetched_at is the last fetch *attempt*, so an offline repo isn't retried on every sync."""
    conn.execute(
        "UPDATE repos SET last_fetched_at = ?, last_fetch_error = ? WHERE id = ?", (at, error, repo_id)
    )


def set_repo_error(conn: sqlite3.Connection, repo_id: int, error: str | None) -> None:
    conn.execute("UPDATE repos SET last_fetch_error = ? WHERE id = ?", (error, repo_id))
