"""Agent batches: every item change an agent message made, undoable as a unit."""
from __future__ import annotations

import json
import sqlite3

from .db import transaction
from .errors import Conflict, NotFound
from .items import get_item
from .models import Batch, BatchChange, Item, UndoConflict, UndoResult


class UndoConflictError(Exception):
    def __init__(self, conflicts: list[UndoConflict]):
        super().__init__(f"{len(conflicts)} item(s) changed after this batch")
        self.conflicts = conflicts


def _batch(r: sqlite3.Row) -> Batch:
    return Batch(
        id=r["id"], source=r["source"], label=r["label"], project_id=r["project_id"], draft_id=r["draft_id"],
        input_text=r["input_text"], summary=r["summary"], created_at=r["created_at"], undone_at=r["undone_at"],
    )


def _change(r: sqlite3.Row) -> BatchChange:
    return BatchChange(
        id=r["id"], batch_id=r["batch_id"], item_id=r["item_id"], item_kind=r["item_kind"], item_text=r["item_text"],
        action=r["action"], old_status=r["old_status"], new_status=r["new_status"], applied_at=r["applied_at"],
    )


def create_batch(conn, *, source: str, label: str | None, project_id: int | None, draft_id: int | None,
                 input_text: str, now: str) -> Batch:
    cur = conn.execute(
        "INSERT INTO agent_batches(source, label, project_id, draft_id, input_text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (source, label, project_id, draft_id, input_text, now),
    )
    return get_batch(conn, cur.lastrowid)


def get_batch(conn, batch_id: int) -> Batch:
    r = conn.execute("SELECT * FROM agent_batches WHERE id = ?", (batch_id,)).fetchone()
    if r is None:
        raise NotFound(f"Batch {batch_id} not found")
    return _batch(r)


def record_change(conn, *, batch_id: int, item: Item, action: str, old_status: str | None,
                  new_status: str | None, applied_at: str) -> None:
    conn.execute(
        "INSERT INTO batch_changes(batch_id, item_id, item_kind, item_text, action, old_status, new_status, applied_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (batch_id, item.id, item.kind, item.text, action, old_status, new_status, applied_at),
    )


def list_changes(conn, batch_id: int) -> list[BatchChange]:
    return [_change(r) for r in conn.execute("SELECT * FROM batch_changes WHERE batch_id = ? ORDER BY id", (batch_id,))]


def set_draft_snapshots(conn, batch_id: int, before: list[dict], after: list[dict]) -> None:
    conn.execute(
        "UPDATE agent_batches SET draft_before = ?, draft_after = ? WHERE id = ?",
        (json.dumps(before), json.dumps(after), batch_id),
    )


def _restore_draft(conn, batch_id: int) -> bool | None:
    """Put the draft back to how it was before the batch's turn, unless it changed since then."""
    b = conn.execute("SELECT draft_id, draft_before, draft_after FROM agent_batches WHERE id = ?", (batch_id,)).fetchone()
    if b["draft_id"] is None or b["draft_before"] is None:
        return None
    d = conn.execute("SELECT status, sections FROM drafts WHERE id = ?", (b["draft_id"],)).fetchone()
    if d is None:
        return None
    if d["status"] != "in_progress" or json.loads(d["sections"]) != json.loads(b["draft_after"]):
        return False
    conn.execute("UPDATE drafts SET sections = ?, discord_text = NULL WHERE id = ?", (b["draft_before"], b["draft_id"]))
    return True


def set_summary(conn, batch_id: int, summary: str) -> None:
    conn.execute("UPDATE agent_batches SET summary = ? WHERE id = ?", (summary[:200], batch_id))


def delete_batch(conn, batch_id: int) -> None:
    conn.execute("DELETE FROM agent_batches WHERE id = ?", (batch_id,))


def find_conflicts(conn, batch_id: int) -> list[UndoConflict]:
    """Items edited after the batch's own last change to them."""
    last_applied: dict[int, str] = {}
    for c in list_changes(conn, batch_id):
        last_applied[c.item_id] = max(last_applied.get(c.item_id, ""), c.applied_at)
    conflicts = []
    for item_id, applied_at in last_applied.items():
        item = get_item(conn, item_id)
        if item is not None and item.updated_at > applied_at:
            conflicts.append(UndoConflict(item_id, item.text, f"'{item.text[:60]}' was changed after this batch"))
    return conflicts


def undo_batch(conn, batch_id: int, *, force: bool, now: str) -> UndoResult:
    batch = get_batch(conn, batch_id)
    if batch.undone_at is not None:
        raise Conflict("This batch was already undone")
    if not force:
        conflicts = find_conflicts(conn, batch_id)
        if conflicts:
            raise UndoConflictError(conflicts)
    reverted, gone = 0, []
    with transaction(conn):
        for c in reversed(list_changes(conn, batch_id)):
            if get_item(conn, c.item_id) is None:
                if c.item_id not in gone:
                    gone.append(c.item_id)
                continue
            if c.action == "created":
                conn.execute("DELETE FROM items WHERE id = ?", (c.item_id,))
            else:
                closed_at = None if c.old_status == "open" else c.applied_at
                conn.execute(
                    "UPDATE items SET status = ?, closed_at = ?, updated_at = ? WHERE id = ?",
                    (c.old_status, closed_at, now, c.item_id),
                )
            reverted += 1
        draft_restored = _restore_draft(conn, batch_id)
        conn.execute("UPDATE agent_batches SET undone_at = ? WHERE id = ?", (now, batch_id))
    return UndoResult(reverted=reverted, already_gone=gone, draft_restored=draft_restored)
