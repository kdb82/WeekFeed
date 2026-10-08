"""Typed rows returned by the store."""
from __future__ import annotations

from dataclasses import dataclass

LABELS = ("work", "school", "personal")


@dataclass(frozen=True)
class Scope:
    """What a draft or agent run covers: one project, or a whole label (project_id None)."""

    label: str
    project_id: int | None = None


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    label: str
    created_at: str


@dataclass(frozen=True)
class Repo:
    id: int
    project_id: int
    path: str
    display_name: str
    added_at: str
    last_fetched_at: str | None
    last_fetch_error: str | None


@dataclass(frozen=True)
class CommitRow:
    id: int
    repo_id: int
    repo_name: str
    project_id: int
    project_name: str
    label: str
    sha: str
    author_name: str
    author_email: str
    authored_at: str
    message: str
    files_changed: list[str]


@dataclass(frozen=True)
class AuthorStat:
    email: str
    count: int
    names: list[str]


@dataclass(frozen=True)
class Item:
    id: int
    label: str
    project_id: int | None
    project_name: str | None
    kind: str
    text: str
    status: str
    created_at: str
    updated_at: str
    closed_at: str | None


@dataclass(frozen=True)
class Draft:
    id: int
    kind: str
    label: str
    project_id: int | None
    period_start: str
    period_end: str
    status: str
    sections: list[dict]
    record_text: str | None
    discord_text: str | None
    created_at: str
    saved_at: str | None


@dataclass(frozen=True)
class DraftMessage:
    id: int
    draft_id: int
    role: str
    content: str
    draft_snapshot: list[dict] | None
    batch_id: int | None
    created_at: str


@dataclass(frozen=True)
class Batch:
    id: int
    source: str
    label: str | None
    project_id: int | None
    draft_id: int | None
    input_text: str
    summary: str
    created_at: str
    undone_at: str | None


@dataclass(frozen=True)
class BatchChange:
    id: int
    batch_id: int
    item_id: int
    item_kind: str
    item_text: str
    action: str
    old_status: str | None
    new_status: str | None
    applied_at: str


@dataclass(frozen=True)
class UndoConflict:
    item_id: int
    text: str
    reason: str


@dataclass(frozen=True)
class UndoResult:
    reverted: int
    already_gone: list[int]
    # None: the batch didn't come from a drafting chat (or its draft is gone).
    # False: the draft changed after that message, so its text was left alone.
    draft_restored: bool | None = None


@dataclass(frozen=True)
class SearchHit:
    source_type: str
    source_id: int
    title: str
    meta: str
    body: str
    label: str
    project_id: int | None
    score: float
