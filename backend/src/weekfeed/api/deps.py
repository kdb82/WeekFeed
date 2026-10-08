from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from fastapi import Request

from ..llm import LLM
from ..store.db import connect
from ..store.errors import Invalid
from ..store.models import LABELS, Scope
from ..store.projects import get_project
from .errors import GitUnavailable


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.config.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_llm(request: Request) -> LLM | None:
    """None when AI is off; the domain functions raise AIDisabled only when they actually need the model."""
    return request.app.state.llm


def require_git(request: Request) -> None:
    if not request.app.state.git_available:
        raise GitUnavailable("git was not found on PATH")


def scope_from(conn: sqlite3.Connection, label: str | None, project_id: int | None) -> Scope:
    if project_id is not None:
        p = get_project(conn, project_id)
        return Scope(p.label, p.id)
    if label not in LABELS:
        raise Invalid("Give a project_id or a label (work, school, personal)")
    return Scope(label)
