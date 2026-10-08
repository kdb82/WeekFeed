import itertools
import os
import subprocess
from pathlib import Path

import pytest

from weekfeed.store.db import connect, migrate


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "test.db")
    migrate(c)
    yield c
    c.close()


@pytest.fixture(autouse=True)
def isolated_git(tmp_path_factory, monkeypatch):
    """Tests never read the developer's real git config."""
    home = tmp_path_factory.mktemp("home")
    cfg = home / ".gitconfig"
    cfg.write_text(
        "[user]\n\temail = Global@Example.com\n\tname = Global User\n"
        "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(home))


_file_counter = itertools.count()


class RepoHelper:
    def __init__(self, path: Path):
        self.path = path

    def run(self, *args: str, env_extra: dict | None = None) -> str:
        env = {**os.environ, **(env_extra or {})}
        return subprocess.run(
            ["git", *args], cwd=self.path, check=True, capture_output=True, text=True, env=env
        ).stdout

    def commit(self, message: str, files: dict[str, str] | None = None, *,
               author: tuple[str, str] = ("Me", "me@example.com"),
               date: str = "2026-10-06T10:00:00+00:00") -> str:
        files = files or {f"file-{next(_file_counter)}.txt": message}
        for rel, content in files.items():
            p = self.path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            self.run("add", rel)
        env = {
            "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1], "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": author[0], "GIT_COMMITTER_EMAIL": author[1], "GIT_COMMITTER_DATE": date,
        }
        self.run("commit", "-q", "-m", message, env_extra=env)
        return self.run("rev-parse", "HEAD").strip()


@pytest.fixture
def make_repo(tmp_path):
    def _make(name: str = "repo") -> RepoHelper:
        path = tmp_path / name
        path.mkdir()
        helper = RepoHelper(path)
        helper.run("init", "-q", "-b", "main")
        return helper

    return _make
