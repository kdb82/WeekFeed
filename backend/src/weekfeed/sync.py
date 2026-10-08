"""Brings repos up to date: throttled git fetch, then new commits into the store."""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import git_reader
from .store import commits as commit_store
from .store import repos as repo_store
from .store.models import Repo, Scope
from .timeutil import iso, parse, utcnow

FETCH_INTERVAL = timedelta(minutes=15)
OVERLAP = timedelta(days=1)

_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(repo_id: int) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(repo_id, threading.Lock())


@dataclass(frozen=True)
class RepoSyncResult:
    repo_id: int
    fetched: bool
    error: str | None
    new_commits: int


def sync_repos(
    conn: sqlite3.Connection,
    repos: list[Repo],
    *,
    force: bool,
    now: datetime | None = None,
    fetch: Callable[[str], git_reader.FetchResult] = git_reader.fetch,
    read: Callable[[str, str | None], list[git_reader.GitCommit]] = git_reader.read_commits,
) -> list[RepoSyncResult]:
    started = now or utcnow()
    return [_sync_one(conn, r.id, force=force, now=started, fetch=fetch, read=read) for r in repos]


def sync_scope(conn: sqlite3.Connection, scope: Scope | None, *, force: bool, **kwargs) -> list[RepoSyncResult]:
    return sync_repos(conn, repo_store.list_repos(conn, scope), force=force, **kwargs)


def _sync_one(conn, repo_id, *, force, now, fetch, read) -> RepoSyncResult:
    # The lock serialises syncs of one repo; a second unforced caller then sees the
    # fresh last_fetched_at and skips its own fetch.
    with _lock_for(repo_id):
        repo = repo_store.get_repo(conn, repo_id)
        if not Path(repo.path).is_dir():
            repo_store.set_repo_error(conn, repo_id, "folder missing")
            return RepoSyncResult(repo_id, False, "folder missing", 0)
        if repo.last_fetch_error == "folder missing":
            repo_store.set_repo_error(conn, repo_id, None)

        error = None if repo.last_fetch_error == "folder missing" else repo.last_fetch_error
        fetched = False
        last = parse(repo.last_fetched_at) if repo.last_fetched_at else None
        if force or last is None or now - last >= FETCH_INTERVAL:
            result = fetch(repo.path)
            fetched, error = True, result.error
            repo_store.record_fetch(conn, repo_id, at=iso(now), error=result.error)

        latest = commit_store.latest_authored_at(conn, repo_id)
        since = iso(parse(latest) - OVERLAP) if latest else None
        try:
            new = commit_store.insert_commits(conn, repo_id, read(repo.path, since))
        except git_reader.GitError:
            repo_store.set_repo_error(conn, repo_id, "git log failed")
            return RepoSyncResult(repo_id, fetched, "git log failed", 0)
        return RepoSyncResult(repo_id, fetched, error, new)
