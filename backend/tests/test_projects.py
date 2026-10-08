import pytest

from tests.helpers import NOW, project, repo
from weekfeed.store import projects
from weekfeed.store.errors import Conflict, Invalid, NotFound


def test_list_orders_by_label_then_name(conn):
    project(conn, "zeta", "work")
    project(conn, "cs340", "school")
    project(conn, "alpha", "work")
    project(conn, "weekfeed", "personal")
    assert [(p.label, p.name) for p in projects.list_projects(conn)] == [
        ("work", "alpha"), ("work", "zeta"), ("school", "cs340"), ("personal", "weekfeed"),
    ]


def test_names_are_unique_ignoring_case(conn):
    project(conn, "API-Server")
    with pytest.raises(Conflict):
        project(conn, "api-server", "school")


def test_rejects_unknown_label_and_blank_name(conn):
    with pytest.raises(Invalid):
        project(conn, "x", "hobby")
    with pytest.raises(Invalid):
        project(conn, "   ")


def test_find_by_name_is_case_insensitive_within_label(conn):
    p = project(conn, "api-server", "work")
    assert projects.find_project_by_name(conn, "work", "API-SERVER") == p
    assert projects.find_project_by_name(conn, "school", "api-server") is None


def test_get_missing_project_raises(conn):
    with pytest.raises(NotFound):
        projects.get_project(conn, 99)


def test_rename(conn):
    p = project(conn, "old")
    assert projects.rename_project(conn, p.id, "new").name == "new"


def test_relabel_moves_items_and_in_progress_drafts_but_not_saved_drafts(conn):
    p = project(conn, "api", "work")
    conn.execute(
        "INSERT INTO items(label, project_id, kind, text, status, created_at, updated_at) VALUES ('work', ?, 'todo', 'x', 'open', ?, ?)",
        (p.id, NOW, NOW),
    )
    draft_sql = ("INSERT INTO drafts(kind, label, project_id, period_start, period_end, status, sections, created_at) "
                 "VALUES ('standup', 'work', ?, 's', 'e', ?, '[]', 't')")
    conn.execute(draft_sql, (p.id, "in_progress"))
    conn.execute(draft_sql, (p.id, "saved"))

    assert projects.relabel_project(conn, p.id, "school").label == "school"

    assert conn.execute("SELECT label FROM items").fetchone()[0] == "school"
    rows = conn.execute("SELECT status, label FROM drafts ORDER BY status").fetchall()
    assert [tuple(r) for r in rows] == [("in_progress", "school"), ("saved", "work")]


def test_delete_requires_matching_name(conn):
    p = project(conn, "api")
    with pytest.raises(Invalid):
        projects.delete_project(conn, p.id, confirm_name="nope")


def test_delete_removes_repos_and_keeps_items_label_only(conn):
    p = project(conn, "api")
    repo(conn, p.id, "/tmp/api")
    conn.execute(
        "INSERT INTO items(label, project_id, kind, text, status, created_at, updated_at) VALUES ('work', ?, 'note', 'keep me', 'open', ?, ?)",
        (p.id, NOW, NOW),
    )
    projects.delete_project(conn, p.id, confirm_name="API")
    assert conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 0
    row = conn.execute("SELECT label, project_id, text FROM items").fetchone()
    assert tuple(row) == ("work", None, "keep me")
