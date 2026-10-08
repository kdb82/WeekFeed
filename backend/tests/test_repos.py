import pytest

from tests.helpers import NOW, project, repo
from weekfeed.store import repos
from weekfeed.store.errors import Conflict
from weekfeed.store.models import Scope


def test_list_by_scope(conn):
    work = project(conn, "api", "work")
    school = project(conn, "cs340", "school")
    a = repo(conn, work.id, "/tmp/a")
    b = repo(conn, school.id, "/tmp/b")
    assert repos.list_repos(conn) == [a, b]
    assert repos.list_repos(conn, Scope("work")) == [a]
    assert repos.list_repos(conn, Scope("school", school.id)) == [b]


def test_duplicate_path_names_the_owning_project(conn):
    p = project(conn, "api")
    repo(conn, p.id, "/tmp/a")
    other = project(conn, "other")
    with pytest.raises(Conflict, match="api"):
        repo(conn, other.id, "/tmp/a")


def test_record_fetch_sets_time_and_error(conn):
    p = project(conn)
    r = repo(conn, p.id)
    repos.record_fetch(conn, r.id, at=NOW, error="offline")
    got = repos.get_repo(conn, r.id)
    assert (got.last_fetched_at, got.last_fetch_error) == (NOW, "offline")
    repos.record_fetch(conn, r.id, at=NOW, error=None)
    assert repos.get_repo(conn, r.id).last_fetch_error is None


def test_remove(conn):
    p = project(conn)
    r = repo(conn, p.id)
    repos.remove_repo(conn, r.id)
    assert repos.list_repos(conn) == []
