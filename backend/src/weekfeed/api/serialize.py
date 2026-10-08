"""Response shapes. frontend/src/types.ts mirrors these."""
from __future__ import annotations

import sqlite3
from dataclasses import asdict

from ..store import batches as batch_store
from ..store.models import Draft, DraftMessage, Item, Project, Repo


def repo(r: Repo) -> dict:
    return {
        "id": r.id, "project_id": r.project_id, "path": r.path, "display_name": r.display_name,
        "last_fetched_at": r.last_fetched_at, "last_fetch_error": r.last_fetch_error,
    }


def project_card(p: Project, repos: list[Repo], counts: tuple[int, int], last_standup_at: str | None) -> dict:
    fetched = [r.last_fetched_at for r in repos if r.last_fetched_at]
    return {
        "id": p.id, "name": p.name, "label": p.label, "repos": [repo(r) for r in repos],
        "open_todos": counts[0], "open_blockers": counts[1],
        "last_standup_at": last_standup_at, "oldest_fetch_at": min(fetched) if fetched else None,
    }


def item(i: Item) -> dict:
    return {
        "id": i.id, "label": i.label, "project_id": i.project_id, "project_name": i.project_name,
        "kind": i.kind, "text": i.text, "status": i.status, "created_at": i.created_at, "closed_at": i.closed_at,
    }


def draft(d: Draft) -> dict:
    return asdict(d)


def batch(conn: sqlite3.Connection, batch_id: int | None) -> dict | None:
    if batch_id is None:
        return None
    b = batch_store.get_batch(conn, batch_id)
    return {
        "id": b.id, "undone_at": b.undone_at,
        "changes": [
            {"action": c.action, "kind": c.item_kind, "text": c.item_text, "new_status": c.new_status}
            for c in batch_store.list_changes(conn, batch_id)
        ],
    }


def message(conn: sqlite3.Connection, m: DraftMessage) -> dict:
    return {
        "id": m.id, "role": m.role, "content": m.content, "draft_snapshot": m.draft_snapshot,
        "batch": batch(conn, m.batch_id), "created_at": m.created_at,
    }
