from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from typing import Protocol

from .db import transaction
from .models import AuthorStat, CommitRow, Scope

_SELECT = """
SELECT c.*, r.display_name AS repo_name, r.project_id, p.name AS project_name, p.label
FROM commits c
JOIN repos r ON r.id = c.repo_id
JOIN projects p ON p.id = r.project_id
"""


class CommitLike(Protocol):
    sha: str
    author_name: str
    author_email: str
    authored_at: str
    message: str
    files: list[str]


def _row(r: sqlite3.Row) -> CommitRow:
    return CommitRow(
        id=r["id"], repo_id=r["repo_id"], repo_name=r["repo_name"], project_id=r["project_id"],
        project_name=r["project_name"], label=r["label"], sha=r["sha"], author_name=r["author_name"],
        author_email=r["author_email"], authored_at=r["authored_at"], message=r["message"],
        files_changed=[f for f in r["files_changed"].split("\n") if f],
    )


def insert_commits(conn: sqlite3.Connection, repo_id: int, commits: Iterable[CommitLike]) -> int:
    inserted = 0
    with transaction(conn):
        for c in commits:
            cur = conn.execute(
                "INSERT OR IGNORE INTO commits(repo_id, sha, author_name, author_email, authored_at, message, files_changed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (repo_id, c.sha, c.author_name, c.author_email.lower(), c.authored_at, c.message, "\n".join(c.files)),
            )
            inserted += cur.rowcount
    return inserted


def latest_authored_at(conn: sqlite3.Connection, repo_id: int) -> str | None:
    return conn.execute("SELECT MAX(authored_at) FROM commits WHERE repo_id = ?", (repo_id,)).fetchone()[0]


def my_commits_in_range(
    conn: sqlite3.Connection, scope: Scope, start: str, end: str, emails: list[str], *, limit: int = 200
) -> list[CommitRow]:
    """My commits with start <= authored_at < end, newest first, deduplicated by sha."""
    where = [
        "c.authored_at >= ?", "c.authored_at < ?",
        "c.author_email IN (SELECT value FROM json_each(?))",
    ]
    params: list = [start, end, json.dumps(emails)]
    if scope.project_id is not None:
        where.append("r.project_id = ?")
        params.append(scope.project_id)
    else:
        where.append("p.label = ?")
        params.append(scope.label)
    rows = conn.execute(f"{_SELECT} WHERE {' AND '.join(where)} ORDER BY c.authored_at DESC", params)
    out: list[CommitRow] = []
    seen: set[str] = set()
    for r in rows:
        if r["sha"] in seen:
            continue
        seen.add(r["sha"])
        out.append(_row(r))
        if len(out) >= limit:
            break
    return out


def get_commit_row(conn: sqlite3.Connection, commit_id: int) -> CommitRow | None:
    r = conn.execute(f"{_SELECT} WHERE c.id = ?", (commit_id,)).fetchone()
    return _row(r) if r else None


def author_stats(conn: sqlite3.Connection) -> list[AuthorStat]:
    counts: dict[str, int] = defaultdict(int)
    names: dict[str, set[str]] = defaultdict(set)
    for r in conn.execute("SELECT author_email, author_name, COUNT(*) AS n FROM commits GROUP BY author_email, author_name"):
        counts[r["author_email"]] += r["n"]
        names[r["author_email"]].add(r["author_name"])
    return [AuthorStat(email=e, count=n, names=sorted(names[e])) for e, n in sorted(counts.items(), key=lambda kv: -kv[1])]
