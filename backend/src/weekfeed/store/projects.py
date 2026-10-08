from __future__ import annotations

import sqlite3

from .db import transaction
from .errors import Conflict, Invalid, NotFound
from .models import LABELS, Project

LABEL_ORDER = "CASE label WHEN 'work' THEN 0 WHEN 'school' THEN 1 ELSE 2 END"


def _row(r: sqlite3.Row) -> Project:
    return Project(id=r["id"], name=r["name"], label=r["label"], created_at=r["created_at"])


def check_label(label: str) -> None:
    if label not in LABELS:
        raise Invalid(f"Unknown label '{label}'")


def create_project(conn: sqlite3.Connection, name: str, label: str, *, now: str) -> Project:
    name = name.strip()
    if not name:
        raise Invalid("Project name is required")
    check_label(label)
    try:
        cur = conn.execute(
            "INSERT INTO projects(name, label, created_at) VALUES (?, ?, ?)", (name, label, now)
        )
    except sqlite3.IntegrityError as e:
        raise Conflict(f"A project named '{name}' already exists") from e
    return get_project(conn, cur.lastrowid)


def get_project(conn: sqlite3.Connection, project_id: int) -> Project:
    r = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if r is None:
        raise NotFound(f"Project {project_id} not found")
    return _row(r)


def list_projects(conn: sqlite3.Connection) -> list[Project]:
    rows = conn.execute(f"SELECT * FROM projects ORDER BY {LABEL_ORDER}, name COLLATE NOCASE")
    return [_row(r) for r in rows]


def list_projects_in_label(conn: sqlite3.Connection, label: str) -> list[Project]:
    rows = conn.execute("SELECT * FROM projects WHERE label = ? ORDER BY name COLLATE NOCASE", (label,))
    return [_row(r) for r in rows]


def find_project_by_name(conn: sqlite3.Connection, label: str, name: str) -> Project | None:
    r = conn.execute(
        "SELECT * FROM projects WHERE label = ? AND name = ? COLLATE NOCASE", (label, name.strip())
    ).fetchone()
    return _row(r) if r else None


def rename_project(conn: sqlite3.Connection, project_id: int, name: str) -> Project:
    get_project(conn, project_id)
    name = name.strip()
    if not name:
        raise Invalid("Project name is required")
    try:
        conn.execute("UPDATE projects SET name = ? WHERE id = ?", (name, project_id))
    except sqlite3.IntegrityError as e:
        raise Conflict(f"A project named '{name}' already exists") from e
    return get_project(conn, project_id)


def relabel_project(conn: sqlite3.Connection, project_id: int, label: str) -> Project:
    """Items and in-progress drafts follow the project; saved drafts keep the label they were written under."""
    check_label(label)
    get_project(conn, project_id)
    with transaction(conn):
        conn.execute("UPDATE projects SET label = ? WHERE id = ?", (label, project_id))
        conn.execute("UPDATE items SET label = ? WHERE project_id = ?", (label, project_id))
        conn.execute(
            "UPDATE drafts SET label = ? WHERE project_id = ? AND status = 'in_progress'", (label, project_id)
        )
    return get_project(conn, project_id)


def delete_project(conn: sqlite3.Connection, project_id: int, *, confirm_name: str) -> None:
    """Repos, commits and drafts cascade away; items stay as label-only items (FK SET NULL)."""
    p = get_project(conn, project_id)
    if confirm_name.strip().lower() != p.name.lower():
        raise Invalid("Type the project's name to confirm deletion")
    with transaction(conn):
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
