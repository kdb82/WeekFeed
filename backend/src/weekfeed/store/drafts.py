"""Standup / weekly drafts and their chat messages."""
from __future__ import annotations

import json
import sqlite3

from .errors import Conflict, Invalid, NotFound
from .models import Draft, DraftMessage, Scope


def _draft(r: sqlite3.Row) -> Draft:
    return Draft(
        id=r["id"], kind=r["kind"], label=r["label"], project_id=r["project_id"], period_start=r["period_start"],
        period_end=r["period_end"], status=r["status"], sections=json.loads(r["sections"]),
        record_text=r["record_text"], discord_text=r["discord_text"], created_at=r["created_at"], saved_at=r["saved_at"],
    )


def _message(r: sqlite3.Row) -> DraftMessage:
    snapshot = r["draft_snapshot"]
    return DraftMessage(
        id=r["id"], draft_id=r["draft_id"], role=r["role"], content=r["content"],
        draft_snapshot=json.loads(snapshot) if snapshot is not None else None,
        batch_id=r["batch_id"], created_at=r["created_at"],
    )


def _scope_sql(scope: Scope) -> tuple[str, list]:
    if scope.project_id is not None:
        return "project_id = ?", [scope.project_id]
    return "label = ? AND project_id IS NULL", [scope.label]


def create_draft(conn, *, kind: str, scope: Scope, period_start: str, period_end: str,
                 sections: list[dict], now: str) -> Draft:
    try:
        cur = conn.execute(
            "INSERT INTO drafts(kind, label, project_id, period_start, period_end, status, sections, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'in_progress', ?, ?)",
            (kind, scope.label, scope.project_id, period_start, period_end, json.dumps(sections), now),
        )
    except sqlite3.IntegrityError as e:
        raise Conflict("An in-progress draft already exists for this scope") from e
    return get_draft(conn, cur.lastrowid)


def get_draft(conn, draft_id: int) -> Draft:
    r = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if r is None:
        raise NotFound(f"Draft {draft_id} not found")
    return _draft(r)


def _require_in_progress(conn, draft_id: int) -> Draft:
    d = get_draft(conn, draft_id)
    if d.status != "in_progress":
        raise Invalid("Saved drafts are read-only")
    return d


def find_in_progress(conn, kind: str, scope: Scope) -> Draft | None:
    where, params = _scope_sql(scope)
    r = conn.execute(
        f"SELECT * FROM drafts WHERE kind = ? AND {where} AND status = 'in_progress'", [kind, *params]
    ).fetchone()
    return _draft(r) if r else None


def list_drafts(conn, scope: Scope) -> list[Draft]:
    where, params = _scope_sql(scope)
    rows = conn.execute(
        f"SELECT * FROM drafts WHERE {where} ORDER BY status = 'saved', COALESCE(saved_at, created_at) DESC, id DESC",
        params,
    )
    return [_draft(r) for r in rows]


def last_saved_period_end(conn, kind: str, scope: Scope) -> str | None:
    where, params = _scope_sql(scope)
    return conn.execute(
        f"SELECT MAX(period_end) FROM drafts WHERE kind = ? AND {where} AND status = 'saved'", [kind, *params]
    ).fetchone()[0]


def update_sections(conn, draft_id: int, sections: list[dict]) -> Draft:
    _require_in_progress(conn, draft_id)
    conn.execute("UPDATE drafts SET sections = ?, discord_text = NULL WHERE id = ?", (json.dumps(sections), draft_id))
    return get_draft(conn, draft_id)


def set_period(conn, draft_id: int, start: str, end: str) -> Draft:
    _require_in_progress(conn, draft_id)
    if start >= end:
        raise Invalid("The range must start before it ends")
    conn.execute("UPDATE drafts SET period_start = ?, period_end = ? WHERE id = ?", (start, end, draft_id))
    return get_draft(conn, draft_id)


def set_discord(conn, draft_id: int, text: str) -> None:
    conn.execute("UPDATE drafts SET discord_text = ? WHERE id = ?", (text, draft_id))


def mark_saved(conn, draft_id: int, *, record_text: str, discord_text: str, now: str) -> Draft:
    _require_in_progress(conn, draft_id)
    conn.execute(
        "UPDATE drafts SET status = 'saved', record_text = ?, discord_text = ?, saved_at = ? WHERE id = ?",
        (record_text, discord_text, now, draft_id),
    )
    return get_draft(conn, draft_id)


def delete_draft(conn, draft_id: int) -> None:
    _require_in_progress(conn, draft_id)
    conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))


def add_message(conn, *, draft_id: int, role: str, content: str, snapshot: list[dict] | None = None,
                batch_id: int | None = None, now: str) -> DraftMessage:
    cur = conn.execute(
        "INSERT INTO draft_messages(draft_id, role, content, draft_snapshot, batch_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (draft_id, role, content, json.dumps(snapshot) if snapshot is not None else None, batch_id, now),
    )
    return _message(conn.execute("SELECT * FROM draft_messages WHERE id = ?", (cur.lastrowid,)).fetchone())


def list_messages(conn, draft_id: int) -> list[DraftMessage]:
    return [_message(r) for r in conn.execute("SELECT * FROM draft_messages WHERE draft_id = ? ORDER BY id", (draft_id,))]


def last_saved_standups(conn) -> dict[int, str]:
    rows = conn.execute(
        "SELECT project_id, MAX(saved_at) AS at FROM drafts "
        "WHERE kind = 'standup' AND status = 'saved' AND project_id IS NOT NULL GROUP BY project_id"
    )
    return {r["project_id"]: r["at"] for r in rows}
