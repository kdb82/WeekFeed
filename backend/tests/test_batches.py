import pytest

from tests.helpers import NOW, item
from weekfeed.store import batches, items
from weekfeed.store.errors import Conflict
from weekfeed.store.models import UndoConflict

T1 = "2026-10-07T15:00:01.000000+00:00"
T2 = "2026-10-07T15:00:02.000000+00:00"
LATER = "2026-10-08T09:00:00.000000+00:00"


def new_batch(conn):
    return batches.create_batch(conn, source="draft_chat", label="work", project_id=None, draft_id=None,
                                input_text="finished login, add review", now=NOW)


def created(conn, b, text, at=T1, kind="todo"):
    i = item(conn, kind=kind, text=text, now=at)
    batches.record_change(conn, batch_id=b.id, item=i, action="created", old_status=None, new_status="open", applied_at=at)
    return i


def closed(conn, b, i, at=T2):
    updated = items.set_status(conn, i.id, "done", now=at)
    batches.record_change(conn, batch_id=b.id, item=updated, action="status_changed", old_status="open", new_status="done", applied_at=at)
    return updated


def test_changes_snapshot_item_kind_and_text(conn):
    b = new_batch(conn)
    created(conn, b, "Review PR")
    [c] = batches.list_changes(conn, b.id)
    assert (c.item_kind, c.item_text, c.action, c.new_status) == ("todo", "Review PR", "created", "open")


def test_undo_reverts_newest_first(conn):
    existing = item(conn, text="Finish login", now=NOW)
    b = new_batch(conn)
    closed(conn, b, existing, at=T1)
    new = created(conn, b, "Review PR", at=T2)
    result = batches.undo_batch(conn, b.id, force=False, now=LATER)
    assert result.reverted == 2 and result.already_gone == []
    assert items.get_item(conn, new.id) is None
    restored = items.get_item(conn, existing.id)
    assert (restored.status, restored.closed_at) == ("open", None)
    assert batches.get_batch(conn, b.id).undone_at == LATER


def test_created_then_closed_in_same_batch_is_not_a_conflict(conn):
    b = new_batch(conn)
    i = created(conn, b, "temp", at=T1)
    closed(conn, b, i, at=T2)
    assert batches.find_conflicts(conn, b.id) == []
    batches.undo_batch(conn, b.id, force=False, now=LATER)
    assert items.get_item(conn, i.id) is None


def test_item_changed_after_batch_is_a_conflict_unless_forced(conn):
    b = new_batch(conn)
    i = created(conn, b, "Review Sam's PR")
    items.set_status(conn, i.id, "done", now=LATER)
    with pytest.raises(batches.UndoConflictError) as exc:
        batches.undo_batch(conn, b.id, force=False, now=LATER)
    assert exc.value.conflicts == [UndoConflict(i.id, "Review Sam's PR", "'Review Sam's PR' was changed after this batch")]
    assert items.get_item(conn, i.id) is not None  # nothing reverted
    batches.undo_batch(conn, b.id, force=True, now=LATER)
    assert items.get_item(conn, i.id) is None


def test_hand_deleted_item_is_reported_already_gone(conn):
    b = new_batch(conn)
    i = created(conn, b, "gone")
    items.delete_item(conn, i.id)
    assert batches.undo_batch(conn, b.id, force=False, now=LATER).already_gone == [i.id]


def test_double_undo_is_rejected(conn):
    b = new_batch(conn)
    created(conn, b, "x")
    batches.undo_batch(conn, b.id, force=False, now=LATER)
    with pytest.raises(Conflict):
        batches.undo_batch(conn, b.id, force=False, now=LATER)


def test_summary_truncated_and_delete(conn):
    b = new_batch(conn)
    batches.set_summary(conn, b.id, "x" * 500)
    assert len(batches.get_batch(conn, b.id).summary) == 200
    batches.delete_batch(conn, b.id)
    assert conn.execute("SELECT COUNT(*) FROM agent_batches").fetchone()[0] == 0
