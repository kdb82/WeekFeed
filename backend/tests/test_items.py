import pytest

from tests.helpers import NOW, item, project
from weekfeed.store import items
from weekfeed.store.errors import Invalid
from weekfeed.store.models import Scope

LATER = "2026-10-07T16:00:00.000000+00:00"


def test_create_sets_open_and_project_name(conn):
    p = project(conn, "api")
    i = item(conn, text=" Review PR ", project_id=p.id)
    assert (i.status, i.text, i.project_name, i.closed_at) == ("open", "Review PR", "api", None)


def test_create_rejects_bad_input(conn):
    school = project(conn, "cs340", "school")
    with pytest.raises(Invalid):
        item(conn, text="  ")
    with pytest.raises(Invalid):
        item(conn, kind="idea")
    with pytest.raises(Invalid):  # project belongs to another label
        item(conn, label="work", project_id=school.id)


def test_status_transitions(conn):
    todo = item(conn, kind="todo")
    done = items.set_status(conn, todo.id, "done", now=LATER)
    assert (done.status, done.closed_at, done.updated_at) == ("done", LATER, LATER)
    reopened = items.set_status(conn, todo.id, "open", now=LATER)
    assert reopened.closed_at is None
    with pytest.raises(Invalid):
        items.set_status(conn, todo.id, "resolved", now=LATER)
    note = item(conn, kind="note")
    with pytest.raises(Invalid):
        items.set_status(conn, note.id, "done", now=LATER)


def test_list_open_scopes(conn):
    api = project(conn, "api")
    a = item(conn, text="api todo", project_id=api.id)
    loose = item(conn, text="loose todo")
    b = item(conn, kind="blocker", text="blocked", project_id=api.id)
    item(conn, kind="note", text="a note")
    item(conn, label="school", text="school todo")
    closed = item(conn, text="closed")
    items.set_status(conn, closed.id, "done", now=LATER)

    assert {i.id for i in items.list_open(conn, Scope("work"))} == {a.id, loose.id, b.id}
    assert {i.id for i in items.list_open(conn, Scope("work", api.id))} == {a.id, b.id}


def test_closed_and_notes_in_range(conn):
    t = item(conn, text="t")
    items.set_status(conn, t.id, "done", now="2026-10-06T12:00:00.000000+00:00")
    item(conn, kind="note", text="in range", now="2026-10-06T13:00:00.000000+00:00")
    item(conn, kind="note", text="too late", now="2026-10-08T00:00:00.000000+00:00")
    start, end = "2026-10-06T00:00:00.000000+00:00", "2026-10-07T00:00:00.000000+00:00"
    assert [i.text for i in items.closed_in_range(conn, Scope("work"), start, end)] == ["t"]
    assert [i.text for i in items.notes_in_range(conn, Scope("work"), start, end)] == ["in range"]


def test_recent_notes_newest_first_with_limit(conn):
    for n in range(7):
        item(conn, kind="note", text=f"n{n}", now=f"2026-10-0{n + 1}T00:00:00.000000+00:00")
    assert [i.text for i in items.recent_notes(conn, Scope("work"), limit=5)] == ["n6", "n5", "n4", "n3", "n2"]


def test_open_counts_by_project(conn):
    api = project(conn, "api")
    item(conn, project_id=api.id)
    item(conn, project_id=api.id)
    item(conn, kind="blocker", project_id=api.id)
    item(conn)
    assert items.open_counts_by_project(conn) == {api.id: (2, 1)}


def test_created_at_used_for_updated_at(conn):
    i = item(conn, now=NOW)
    assert i.updated_at == NOW
