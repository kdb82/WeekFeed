from tests.helpers import FakeCommit, project, repo
from weekfeed.store import commits
from weekfeed.store.models import Scope

ME = ["me@example.com"]
START, END = "2026-10-06T00:00:00.000000+00:00", "2026-10-07T00:00:00.000000+00:00"


def setup(conn):
    work = project(conn, "api", "work")
    school = project(conn, "cs340", "school")
    return work, school, repo(conn, work.id, "/tmp/api"), repo(conn, school.id, "/tmp/cs340")


def test_insert_ignores_duplicates_and_lowercases_email(conn):
    _, _, r, _ = setup(conn)
    c = FakeCommit("aaa", author_email="Me@Example.com", files=["a.py", "b.py"])
    assert commits.insert_commits(conn, r.id, [c, c]) == 1
    assert commits.insert_commits(conn, r.id, [c]) == 0
    row = conn.execute("SELECT author_email, files_changed FROM commits").fetchone()
    assert tuple(row) == ("me@example.com", "a.py\nb.py")


def test_latest_authored_at(conn):
    _, _, r, _ = setup(conn)
    assert commits.latest_authored_at(conn, r.id) is None
    commits.insert_commits(conn, r.id, [
        FakeCommit("a", authored_at="2026-10-01T00:00:00.000000+00:00"),
        FakeCommit("b", authored_at="2026-10-03T00:00:00.000000+00:00"),
    ])
    assert commits.latest_authored_at(conn, r.id) == "2026-10-03T00:00:00.000000+00:00"


def test_my_commits_in_range_filters_scope_author_and_dates(conn):
    work, _, api, cs = setup(conn)
    commits.insert_commits(conn, api.id, [
        FakeCommit("in1", message="mine in range"),
        FakeCommit("other", author_email="sam@x.io"),
        FakeCommit("old", authored_at="2026-10-05T12:00:00.000000+00:00"),
        FakeCommit("edge", authored_at=END),  # end is exclusive
    ])
    commits.insert_commits(conn, cs.id, [FakeCommit("school1")])
    got = commits.my_commits_in_range(conn, Scope("work"), START, END, ME)
    assert [c.sha for c in got] == ["in1"]
    assert (got[0].project_name, got[0].label, got[0].repo_name) == ("api", "work", "api")
    assert [c.sha for c in commits.my_commits_in_range(conn, Scope("work", work.id), START, END, ME)] == ["in1"]


def test_my_commits_dedupes_sha_across_repos_and_caps(conn):
    work, _, api, _ = setup(conn)
    fork = repo(conn, work.id, "/tmp/api-fork")
    commits.insert_commits(conn, api.id, [FakeCommit("same")])
    commits.insert_commits(conn, fork.id, [FakeCommit("same")])
    assert len(commits.my_commits_in_range(conn, Scope("work"), START, END, ME)) == 1

    many = [FakeCommit(f"s{i}", authored_at=f"2026-10-06T10:{i:02d}:00.000000+00:00") for i in range(30)]
    commits.insert_commits(conn, api.id, many)
    got = commits.my_commits_in_range(conn, Scope("work"), START, END, ME, limit=5)
    assert len(got) == 5
    assert got[0].authored_at > got[-1].authored_at  # newest first


def test_no_confirmed_emails_means_no_commits_not_an_error(conn):
    _, _, api, _ = setup(conn)
    commits.insert_commits(conn, api.id, [FakeCommit("a")])
    assert commits.my_commits_in_range(conn, Scope("work"), START, END, []) == []


def test_author_stats(conn):
    _, _, api, _ = setup(conn)
    commits.insert_commits(conn, api.id, [
        FakeCommit("1"), FakeCommit("2", author_name="Kaden"), FakeCommit("3", author_email="sam@x.io", author_name="Sam"),
    ])
    stats = {s.email: s for s in commits.author_stats(conn)}
    assert stats["me@example.com"].count == 2
    assert sorted(stats["me@example.com"].names) == ["Kaden", "Me"]
    assert stats["sam@x.io"].count == 1
