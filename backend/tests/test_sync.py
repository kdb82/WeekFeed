import shutil
import threading
import time
from datetime import datetime, timedelta, timezone

from tests.helpers import project, repo
from weekfeed import sync
from weekfeed.git_reader import FetchResult
from weekfeed.store import repos
from weekfeed.store.db import connect

T0 = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)


class CountingFetch:
    def __init__(self, result=FetchResult(ok=True), delay=0.0):
        self.calls = 0
        self.result = result
        self.delay = delay

    def __call__(self, path):
        self.calls += 1
        time.sleep(self.delay)
        return self.result


def setup(conn, make_repo):
    git_repo = make_repo()
    git_repo.commit("one", date="2026-10-06T10:00:00+00:00")
    p = project(conn)
    return repo(conn, p.id, str(git_repo.path)), git_repo


def count_commits(conn):
    return conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]


def test_unforced_sync_fetches_at_most_every_15_minutes(conn, make_repo):
    r, _ = setup(conn, make_repo)
    f = CountingFetch()
    sync.sync_repos(conn, [r], force=False, now=T0, fetch=f)
    sync.sync_repos(conn, [r], force=False, now=T0 + timedelta(minutes=14), fetch=f)
    assert f.calls == 1
    sync.sync_repos(conn, [r], force=False, now=T0 + timedelta(minutes=15), fetch=f)
    assert f.calls == 2


def test_forced_sync_always_fetches(conn, make_repo):
    r, _ = setup(conn, make_repo)
    f = CountingFetch()
    sync.sync_repos(conn, [r], force=True, now=T0, fetch=f)
    sync.sync_repos(conn, [r], force=True, now=T0 + timedelta(minutes=1), fetch=f)
    assert f.calls == 2


def test_reads_new_commits_incrementally_without_duplicates(conn, make_repo):
    r, git_repo = setup(conn, make_repo)
    f = CountingFetch()
    first = sync.sync_repos(conn, [r], force=True, now=T0, fetch=f)
    assert first[0].new_commits == 1
    git_repo.commit("two", date="2026-10-07T10:00:00+00:00")
    second = sync.sync_repos(conn, [r], force=True, now=T0, fetch=f)
    assert second[0].new_commits == 1
    assert count_commits(conn) == 2


def test_fetch_failure_is_recorded_and_local_commits_still_read(conn, make_repo):
    r, _ = setup(conn, make_repo)
    result = sync.sync_repos(conn, [r], force=True, now=T0, fetch=CountingFetch(FetchResult(False, "offline")))[0]
    assert result.error == "offline"
    assert repos.get_repo(conn, r.id).last_fetch_error == "offline"
    assert count_commits(conn) == 1


def test_missing_folder_is_flagged_and_skipped(conn, make_repo):
    r, git_repo = setup(conn, make_repo)
    shutil.rmtree(git_repo.path)
    f = CountingFetch()
    result = sync.sync_repos(conn, [r], force=True, now=T0, fetch=f)[0]
    assert result.error == "folder missing"
    assert f.calls == 0
    assert repos.get_repo(conn, r.id).last_fetch_error == "folder missing"


def test_folder_missing_error_clears_when_folder_returns(conn, make_repo):
    r, _ = setup(conn, make_repo)
    repos.set_repo_error(conn, r.id, "folder missing")
    sync.sync_repos(conn, [r], force=False, now=T0, fetch=CountingFetch())
    assert repos.get_repo(conn, r.id).last_fetch_error is None


def test_concurrent_unforced_syncs_fetch_once(tmp_path, make_repo, conn):
    r, _ = setup(conn, make_repo)
    db_path = conn.execute("PRAGMA database_list").fetchone()["file"]
    f = CountingFetch(delay=0.3)

    def worker():
        c = connect(db_path)
        sync.sync_repos(c, [r], force=False, now=T0, fetch=f)
        c.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert f.calls == 1
