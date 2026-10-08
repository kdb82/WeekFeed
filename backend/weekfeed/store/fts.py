"""Keyword search over notes/items and my commits (SQLite FTS5, BM25 ranking)."""
from __future__ import annotations

import json
import sqlite3

from .commits import get_commit_row
from .items import get_item
from .models import SearchHit


def build_match(terms: list[str]) -> str:
    """Each term becomes a quoted FTS5 string (so operators and punctuation are literal), ORed together."""
    quoted: list[str] = []
    for term in terms:
        term = term.strip()
        if not any(ch.isalnum() for ch in term):
            continue
        q = '"' + term.replace('"', '""') + '"'
        if q not in quoted:
            quoted.append(q)
    return " OR ".join(quoted)


def search(conn: sqlite3.Connection, terms: list[str], my_emails: list[str], *, limit: int = 15) -> list[SearchHit]:
    match = build_match(terms)
    if not match:
        return []
    rows = conn.execute(
        """
        SELECT search_index.source_type AS st, search_index.source_id AS sid, bm25(search_index) AS score
        FROM search_index
        LEFT JOIN commits c ON search_index.source_type = 'commit' AND c.id = search_index.source_id
        WHERE search_index MATCH ?
          AND (search_index.source_type = 'item' OR c.author_email IN (SELECT value FROM json_each(?)))
        ORDER BY score
        LIMIT ?
        """,
        (match, json.dumps(my_emails), limit),
    ).fetchall()
    hits = [_hydrate(conn, r["st"], int(r["sid"]), r["score"]) for r in rows]
    return [h for h in hits if h is not None]


def _where(label: str, project_name: str | None) -> str:
    return f"{label} › {project_name}" if project_name else label


def _hydrate(conn: sqlite3.Connection, source_type: str, source_id: int, score: float) -> SearchHit | None:
    if source_type == "item":
        i = get_item(conn, source_id)
        if i is None:
            return None
        return SearchHit(
            source_type="item", source_id=i.id, title=i.text.splitlines()[0][:80],
            meta=f"{i.kind} · {_where(i.label, i.project_name)} · {i.created_at[:10]}",
            body=i.text, label=i.label, project_id=i.project_id, score=score,
        )
    c = get_commit_row(conn, source_id)
    if c is None:
        return None
    body = c.message + (f"\n\nFiles: {', '.join(c.files_changed)}" if c.files_changed else "")
    return SearchHit(
        source_type="commit", source_id=c.id, title=c.message.splitlines()[0][:80] if c.message else c.sha[:7],
        meta=f"commit {c.sha[:7]} · {_where(c.label, c.project_name)} · {c.authored_at[:10]}",
        body=body, label=c.label, project_id=c.project_id, score=score,
    )
