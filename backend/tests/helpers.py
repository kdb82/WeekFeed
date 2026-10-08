"""Small factories shared by tests."""
from __future__ import annotations

from dataclasses import dataclass, field

NOW = "2026-10-07T15:00:00.000000+00:00"


def project(conn, name="api-server", label="work"):
    from weekfeed.store import projects

    return projects.create_project(conn, name, label, now=NOW)


def repo(conn, project_id, path="/tmp/repo", name=None):
    from weekfeed.store import repos

    return repos.add_repo(conn, project_id, path, name or path.rsplit("/", 1)[-1], now=NOW)


def item(conn, *, label="work", kind="todo", text="Do the thing", project_id=None, now=NOW):
    from weekfeed.store import items

    return items.create_item(conn, label=label, kind=kind, text=text, project_id=project_id, now=now)


@dataclass
class FakeCommit:
    sha: str
    message: str = "a commit"
    author_email: str = "me@example.com"
    author_name: str = "Me"
    authored_at: str = "2026-10-06T12:00:00.000000+00:00"
    files: list[str] = field(default_factory=list)
