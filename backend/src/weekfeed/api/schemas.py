"""Request bodies."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    label: str


class ProjectPatch(BaseModel):
    name: str | None = None
    label: str | None = None


class RepoCreate(BaseModel):
    path: str
    project_id: int


class SyncRequest(BaseModel):
    project_id: int | None = None
    label: str | None = None
    force: bool = True


class SettingsUpdate(BaseModel):
    github_username: str
    my_emails: list[str]


class Section(BaseModel):
    title: str
    text: str


class DraftCreate(BaseModel):
    kind: Literal["standup", "weekly"]
    label: str
    project_id: int | None = None


class DraftPatch(BaseModel):
    sections: list[Section] | None = None
    period_start: str | None = None
    period_end: str | None = None


class MessageCreate(BaseModel):
    content: str


class NoteCreate(BaseModel):
    text: str
    label: str
    project_id: int | None = None


class UndoRequest(BaseModel):
    force: bool = False


class AskMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AskRequest(BaseModel):
    messages: list[AskMessage]
