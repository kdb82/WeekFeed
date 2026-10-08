"""The only code that runs git. No database, no AI."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .timeutil import iso

log = logging.getLogger(__name__)

RS, US = "\x1e", "\x1f"  # record / unit separators: never appear in normal commit text
LOG_FORMAT = f"{RS}%H{US}%an{US}%ae{US}%aI{US}%B{US}"
FETCH_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=8"}


@dataclass(frozen=True)
class GitCommit:
    sha: str
    author_name: str
    author_email: str
    authored_at: str
    message: str
    files: list[str]


@dataclass(frozen=True)
class FetchResult:
    ok: bool
    error: str | None = None


class GitError(Exception):
    pass


def git_available() -> bool:
    return shutil.which("git") is not None


def _git(path: str, *args: str, timeout: float = 60, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", path, *args], capture_output=True, text=True, timeout=timeout, env=env
    )


def resolve_path(path: str) -> str:
    return str(Path(path.strip()).expanduser().resolve())


def is_work_tree(path: str) -> bool:
    if not Path(path).is_dir():
        return False
    r = _git(path, "rev-parse", "--is-inside-work-tree")
    return r.returncode == 0 and r.stdout.strip() == "true"


def read_commits(path: str, since: str | None = None) -> list[GitCommit]:
    """Non-merge commits on every branch (local and remote-tracking), optionally since an ISO time."""
    args = ["-c", "core.quotePath=false", "log", "--all", "--no-merges", f"--format={LOG_FORMAT}", "--name-only"]
    if since:
        args.append(f"--since={since}")
    r = _git(path, *args)
    if r.returncode != 0:
        if "does not have any commits" in r.stderr or "bad default revision" in r.stderr:
            return []
        raise GitError(r.stderr.strip() or "git log failed")
    return parse_log(r.stdout)


def parse_log(output: str) -> list[GitCommit]:
    commits: list[GitCommit] = []
    for record in output.split(RS)[1:]:
        parts = record.split(US)
        if len(parts) < 6:
            log.warning("skipping unparseable git log record")
            continue
        sha, name, email, date, body = parts[:5]
        files_part = US.join(parts[5:])
        try:
            authored_at = iso(datetime.fromisoformat(date.strip()))
        except ValueError:
            log.warning("skipping commit %s with unparseable date %r", sha, date)
            continue
        files = [line.strip() for line in files_part.splitlines() if line.strip()]
        commits.append(GitCommit(sha.strip(), name.strip(), email.strip().lower(), authored_at, body.strip(), files))
    return commits


def has_remote(path: str) -> bool:
    r = _git(path, "remote")
    return r.returncode == 0 and bool(r.stdout.strip())


def fetch(path: str, timeout: float = 10) -> FetchResult:
    if not has_remote(path):
        return FetchResult(ok=True)
    try:
        r = _git(path, "fetch", "--all", "--prune", "--quiet", timeout=timeout, env={**os.environ, **FETCH_ENV})
    except subprocess.TimeoutExpired:
        return FetchResult(ok=False, error="timed out")
    if r.returncode == 0:
        return FetchResult(ok=True)
    return FetchResult(ok=False, error=classify_fetch_error(r.stderr))


def classify_fetch_error(stderr: str) -> str:
    s = stderr.lower()
    if any(k in s for k in ("could not resolve host", "network is unreachable", "failed to connect")):
        return "offline"
    if any(k in s for k in ("authentication", "terminal prompts disabled", "permission denied", "could not read username")):
        return "needs password"
    return "fetch failed"


def config_email(path: str | None = None) -> str | None:
    """user.email from global config (path None) or one repo's local config."""
    args = ["config", "--global", "user.email"] if path is None else ["-C", path, "config", "--local", "user.email"]
    r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10)
    value = r.stdout.strip().lower()
    return value or None
