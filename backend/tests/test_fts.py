import pytest

from tests.helpers import FakeCommit, item, project, repo
from weekfeed.store import commits, fts

ME = ["me@example.com"]


@pytest.fixture
def api_repo(conn):
    p = project(conn, "api-server", "work")
    return repo(conn, p.id, "/tmp/api-server")


def test_stemming_matches_word_forms(conn):
    item(conn, kind="note", text="Fixing the token bug by refreshing early")
    hits = fts.search(conn, ["fixed"], ME)
    assert [h.source_type for h in hits] == ["item"]


def test_file_paths_are_searchable(conn, api_repo):
    commits.insert_commits(conn, api_repo.id, [FakeCommit("abc1234def", message="fix timeout", files=["auth/session.py"])])
    hits = fts.search(conn, ["session"], ME)
    assert len(hits) == 1
    h = hits[0]
    assert h.source_type == "commit"
    assert h.title == "fix timeout"
    assert h.meta == "commit abc1234 · work › api-server · 2026-10-06"
    assert "Files: auth/session.py" in h.body


def test_other_authors_commits_are_excluded(conn, api_repo):
    commits.insert_commits(conn, api_repo.id, [FakeCommit("x", message="auth work", author_email="sam@x.io")])
    assert fts.search(conn, ["auth"], ME) == []


def test_terms_are_ored_and_limited(conn):
    for n in range(20):
        item(conn, kind="note", text=f"login note {n}")
    item(conn, kind="note", text="session thing")
    assert len(fts.search(conn, ["login", "session"], ME, limit=15)) == 15
    assert any("session" in h.body for h in fts.search(conn, ["session", "nothingmatches"], ME))


def test_item_meta_includes_kind_label_and_project(conn):
    p = project(conn, "cs340", "school")
    item(conn, label="school", kind="todo", text="finish lab", project_id=p.id)
    item(conn, label="personal", kind="note", text="lab equipment list")
    metas = sorted(h.meta for h in fts.search(conn, ["lab"], ME))
    assert metas == ["note · personal · 2026-10-07", "todo · school › cs340 · 2026-10-07"]


@pytest.mark.parametrize("term", ['don"t', "a:b", "-x", "*", "NEAR", "AND", "(", "", "   ", "c++", "über"])
def test_fts_syntax_characters_never_error(conn, term):
    item(conn, kind="note", text="ordinary text über c")
    fts.search(conn, [term], ME)  # must not raise


def test_empty_terms_return_nothing(conn):
    item(conn, kind="note", text="x")
    assert fts.search(conn, [], ME) == []


def test_meta_dates_are_local_days(conn, api_repo):
    evening = "2026-10-08T03:00:00.000000+00:00"  # 21:00 MDT on Oct 7
    commits.insert_commits(conn, api_repo.id, [FakeCommit("eee5555", message="late fix", authored_at=evening)])
    item(conn, kind="note", text="late thought", now=evening)
    metas = sorted(h.meta for h in fts.search(conn, ["late"], ME))
    assert metas == ["commit eee5555 · work › api-server · 2026-10-07", "note · work · 2026-10-07"]
