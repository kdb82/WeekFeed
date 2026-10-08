from tests.helpers import FakeCommit, item, project, repo
from weekfeed.store import commits, items, projects, repos


def index_rows(conn):
    return [tuple(r) for r in conn.execute("SELECT source_type, source_id, content FROM search_index ORDER BY rowid")]


def test_items_are_indexed_updated_and_removed(conn):
    i = item(conn, text="token bug")
    assert index_rows(conn) == [("item", i.id, "token bug")]
    conn.execute("UPDATE items SET text = 'token bug fixed' WHERE id = ?", (i.id,))
    assert index_rows(conn) == [("item", i.id, "token bug fixed")]
    items.delete_item(conn, i.id)
    assert index_rows(conn) == []


def test_status_change_does_not_duplicate_index_row(conn):
    i = item(conn, text="x")
    items.set_status(conn, i.id, "done", now="2026-10-07T16:00:00.000000+00:00")
    assert len(index_rows(conn)) == 1


def test_commits_indexed_with_files_and_removed_with_repo(conn):
    p = project(conn)
    r = repo(conn, p.id, "/tmp/api")
    commits.insert_commits(conn, r.id, [FakeCommit("a", message="fix timeout", files=["auth/session.py"])])
    assert index_rows(conn)[0][2] == "fix timeout\nauth/session.py"
    repos.remove_repo(conn, r.id)
    assert index_rows(conn) == []


def test_project_delete_removes_commit_rows_but_keeps_item_rows(conn):
    p = project(conn, "api")
    r = repo(conn, p.id, "/tmp/api")
    commits.insert_commits(conn, r.id, [FakeCommit("a")])
    item(conn, kind="note", text="keep", project_id=p.id)
    projects.delete_project(conn, p.id, confirm_name="api")
    assert [row[0] for row in index_rows(conn)] == ["item"]
