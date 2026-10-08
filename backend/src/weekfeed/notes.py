"""'Save answer as note' from the Ask page: a one-change, undoable batch."""
from __future__ import annotations

import sqlite3

from .agent import TurnContext, apply_write
from .store import batches as batch_store
from .store import items as item_store
from .store.models import Item


def save_note(conn: sqlite3.Connection, *, text: str, label: str, project_id: int | None,
              input_text: str, now: str) -> tuple[Item, int]:
    ctx = TurnContext(conn=conn, scope=None, source="ask_chat", draft_id=None, input_text=input_text, now=lambda: now)
    try:
        note = apply_write(ctx, lambda at: (
            item_store.create_item(conn, label=label, kind="note", text=text, project_id=project_id, now=at),
            "created", None, "open",
        ))
    except Exception:
        if ctx.batch_id is not None:
            batch_store.delete_batch(conn, ctx.batch_id)
        raise
    batch_store.set_summary(conn, ctx.batch_id, "Saved answer as note")  # type: ignore[arg-type]
    return note, ctx.batch_id  # type: ignore[return-value]
