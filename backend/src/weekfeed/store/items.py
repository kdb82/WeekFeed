from __future__ import annotations

import sqlite3

from .errors import Invalid, NotFound
from .models import LABELS, Item, Scope
from .projects import get_project

KINDS = ("note", "todo", "blocker")
ALLOWED_STATUS = {"note": {"open"}, "todo": {"open", "done"}, "blocker": {"open", "resolved"}}

_SELECT = "SELECT i.*, p.name AS project_name FROM items i LEFT JOIN projects p ON p.id = i.project_id"


def _row(r: sqlite3.Row) -> Item:
    return Item(
        id=r["id"], label=r["label"], project_id=r["project_id"], project_name=r["project_name"],
        kind=r["kind"], text=r["text"], status=r["status"], created_at=r["created_at"],
        updated_at=r["updated_at"], closed_at=r["closed_at"],
    )


def _scope_where(scope: Scope) -> tuple[str, list]:
    if scope.project_id is not None:
        return "i.project_id = ?", [scope.project_id]
    return "i.label = ?", [scope.label]


def create_item(
    conn: sqlite3.Connection, *, label: str, kind: str, text: str, project_id: int | None = None, now: str
) -> Item:
    text = text.strip()
    if not text:
        raise Invalid("Text is required")
    if label not in LABELS:
        raise Invalid(f"Unknown label '{label}'")
    if kind not in KINDS:
        raise Invalid(f"Unknown kind '{kind}'")
    if project_id is not None and get_project(conn, project_id).label != label:
        raise Invalid("That project belongs to a different label")
    cur = conn.execute(
        "INSERT INTO items(label, project_id, kind, text, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'open', ?, ?)",
        (label, project_id, kind, text, now, now),
    )
    return get_item(conn, cur.lastrowid)  # type: ignore[return-value]


def get_item(conn: sqlite3.Connection, item_id: int) -> Item | None:
    r = conn.execute(f"{_SELECT} WHERE i.id = ?", (item_id,)).fetchone()
    return _row(r) if r else None


def set_status(conn: sqlite3.Connection, item_id: int, status: str, *, now: str) -> Item:
    item = get_item(conn, item_id)
    if item is None:
        raise NotFound(f"Item {item_id} not found")
    if status not in ALLOWED_STATUS[item.kind]:
        raise Invalid(f"A {item.kind} can't be '{status}'")
    closed_at = None if status == "open" else now
    conn.execute(
        "UPDATE items SET status = ?, closed_at = ?, updated_at = ? WHERE id = ?", (status, closed_at, now, item_id)
    )
    return get_item(conn, item_id)  # type: ignore[return-value]


def delete_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))


def list_open(conn: sqlite3.Connection, scope: Scope) -> list[Item]:
    """Open todos and blockers in scope."""
    where, params = _scope_where(scope)
    rows = conn.execute(
        f"{_SELECT} WHERE {where} AND i.status = 'open' AND i.kind IN ('todo', 'blocker') ORDER BY i.kind DESC, i.created_at, i.id",
        params,
    )
    return [_row(r) for r in rows]


def recent_notes(conn: sqlite3.Connection, scope: Scope, limit: int = 5) -> list[Item]:
    where, params = _scope_where(scope)
    rows = conn.execute(
        f"{_SELECT} WHERE {where} AND i.kind = 'note' ORDER BY i.created_at DESC, i.id DESC LIMIT ?", [*params, limit]
    )
    return [_row(r) for r in rows]


def closed_in_range(conn: sqlite3.Connection, scope: Scope, start: str, end: str) -> list[Item]:
    where, params = _scope_where(scope)
    rows = conn.execute(
        f"{_SELECT} WHERE {where} AND i.status != 'open' AND i.closed_at >= ? AND i.closed_at < ? ORDER BY i.closed_at",
        [*params, start, end],
    )
    return [_row(r) for r in rows]


def notes_in_range(conn: sqlite3.Connection, scope: Scope, start: str, end: str) -> list[Item]:
    where, params = _scope_where(scope)
    rows = conn.execute(
        f"{_SELECT} WHERE {where} AND i.kind = 'note' AND i.created_at >= ? AND i.created_at < ? ORDER BY i.created_at",
        [*params, start, end],
    )
    return [_row(r) for r in rows]


def open_counts_by_project(conn: sqlite3.Connection) -> dict[int, tuple[int, int]]:
    """project_id -> (open todos, open blockers)."""
    rows = conn.execute(
        "SELECT project_id, SUM(kind = 'todo') AS todos, SUM(kind = 'blocker') AS blockers "
        "FROM items WHERE status = 'open' AND project_id IS NOT NULL GROUP BY project_id"
    )
    return {r["project_id"]: (r["todos"], r["blockers"]) for r in rows}
