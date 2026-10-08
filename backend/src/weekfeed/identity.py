"""Suggests which commit author emails are "me" (the user confirms in Settings)."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from . import git_reader
from .store import commits as commit_store
from .store import repos as repo_store
from .store import settings as settings_store
from .store.models import AuthorStat


@dataclass(frozen=True)
class EmailCandidate:
    email: str
    commit_count: int
    reasons: list[str]
    checked: bool
    is_new: bool


def candidate_reasons(email: str, names: list[str], *, username: str, config_emails: set[str]) -> list[str]:
    reasons = []
    if email in config_emails:
        reasons.append("your git config")
    if username:
        u = re.escape(username.lower())
        if re.fullmatch(rf"(\d+\+)?{u}@users\.noreply\.github\.com", email):
            reasons.append("GitHub private email")
        if any(n.strip().lower() == username.lower() for n in names):
            reasons.append("author name matches")
    return reasons


def classify(
    stats: list[AuthorStat], *, my_emails: list[str], username: str, config_emails: set[str]
) -> list[EmailCandidate]:
    first_setup = not my_emails
    mine = set(my_emails)
    out = []
    for s in stats:
        reasons = candidate_reasons(s.email, s.names, username=username, config_emails=config_emails)
        if first_setup:
            checked, is_new = bool(reasons), False
        else:
            checked = s.email in mine
            is_new = bool(reasons) and not checked
        out.append(EmailCandidate(s.email, s.count, reasons, checked, is_new))
    out.sort(key=lambda c: (not c.checked, not c.reasons, -c.commit_count, c.email))
    return out


def detect_emails(conn: sqlite3.Connection) -> list[EmailCandidate]:
    config_emails: set[str] = set()
    for path in [None, *(r.path for r in repo_store.list_repos(conn))]:
        email = git_reader.config_email(path)
        if email:
            config_emails.add(email)
    return classify(
        commit_store.author_stats(conn),
        my_emails=settings_store.get_my_emails(conn),
        username=settings_store.get_github_username(conn),
        config_emails=config_emails,
    )
