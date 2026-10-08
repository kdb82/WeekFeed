import subprocess

from weekfeed import git_reader
from weekfeed.git_reader import FetchResult, classify_fetch_error, config_email, fetch, is_work_tree, parse_log, read_commits


def messages(path, since=None):
    return {c.message for c in read_commits(str(path), since)}


def test_reads_all_branches_and_skips_merges(make_repo):
    repo = make_repo()
    repo.commit("first", {"a.txt": "1"}, date="2026-10-01T10:00:00+00:00")
    repo.run("checkout", "-q", "-b", "feature")
    repo.commit("feature work", {"src/auth/session.py": "x"}, author=("Kaden", "Me@Example.com"),
                date="2026-10-02T10:00:00+00:00")
    repo.run("checkout", "-q", "main")
    repo.commit("main work", {"b.txt": "2"}, date="2026-10-03T10:00:00+00:00")
    repo.run("merge", "-q", "--no-ff", "-m", "Merge branch feature", "feature")

    commits = read_commits(str(repo.path))
    assert {c.message for c in commits} == {"first", "feature work", "main work"}
    feature = next(c for c in commits if c.message == "feature work")
    assert feature.files == ["src/auth/session.py"]
    assert feature.author_email == "me@example.com"
    assert feature.author_name == "Kaden"
    assert feature.authored_at == "2026-10-02T10:00:00.000000+00:00"


def test_unmerged_branch_commits_are_included(make_repo):
    repo = make_repo()
    repo.commit("base")
    repo.run("checkout", "-q", "-b", "wip")
    repo.commit("wip only")
    repo.run("checkout", "-q", "main")
    assert "wip only" in messages(repo.path)


def test_since_filters_older_commits(make_repo):
    repo = make_repo()
    repo.commit("old", date="2026-09-01T10:00:00+00:00")
    repo.commit("new", date="2026-10-05T10:00:00+00:00")
    assert messages(repo.path, since="2026-10-01T00:00:00.000000+00:00") == {"new"}


def test_author_dates_in_other_timezones_are_stored_as_utc(make_repo):
    repo = make_repo()
    repo.commit("late night", date="2026-10-06T23:30:00-06:00")
    assert read_commits(str(repo.path))[0].authored_at == "2026-10-07T05:30:00.000000+00:00"


def test_multiline_message_and_unicode_paths(make_repo):
    repo = make_repo()
    repo.commit("subject line\n\nbody text", {"notes/café.md": "x"})
    c = read_commits(str(repo.path))[0]
    assert c.message == "subject line\n\nbody text"
    assert c.files == ["notes/café.md"]


def test_empty_repo_has_no_commits(make_repo):
    assert read_commits(str(make_repo().path)) == []


def test_parse_log_skips_malformed_records():
    good = "\x1eabc\x1fMe\x1fme@x.io\x1f2026-10-06T10:00:00+00:00\x1fmsg\x1f\n\na.txt\n"
    bad = "\x1eonly\x1ftwo"
    assert [c.sha for c in parse_log(good + bad)] == ["abc"]


def test_is_work_tree(make_repo, tmp_path):
    assert is_work_tree(str(make_repo().path))
    plain = tmp_path / "plain"
    plain.mkdir()
    assert not is_work_tree(str(plain))
    assert not is_work_tree(str(tmp_path / "missing"))


def test_resolve_path_expands_home_and_symlinks(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    assert git_reader.resolve_path(str(link) + "/") == str(real.resolve())
    monkeypatch.setenv("HOME", str(tmp_path))
    assert git_reader.resolve_path("~/real") == str(real.resolve())


def test_config_email_global_and_local(make_repo):
    repo = make_repo()
    assert config_email(None) == "global@example.com"
    assert config_email(str(repo.path)) is None
    repo.run("config", "user.email", "Local@Example.com")
    assert config_email(str(repo.path)) == "local@example.com"


def test_fetch_without_remote_is_ok(make_repo):
    assert fetch(str(make_repo().path)) == FetchResult(ok=True)


def test_fetch_downloads_commits_pushed_elsewhere(make_repo, tmp_path):
    origin = make_repo("origin")
    origin.commit("base")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin.path), str(clone)], check=True)
    origin.commit("pushed from another machine", date="2026-10-05T10:00:00+00:00")
    assert "pushed from another machine" not in messages(clone)
    assert fetch(str(clone)) == FetchResult(ok=True)
    assert "pushed from another machine" in messages(clone)


def test_fetch_failure_reports_reason(make_repo, tmp_path):
    origin = make_repo("origin")
    origin.commit("base")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin.path), str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "remote", "set-url", "origin", str(tmp_path / "gone")], check=True)
    result = fetch(str(clone))
    assert not result.ok
    assert result.error == "fetch failed"


def test_classify_fetch_error():
    assert classify_fetch_error("fatal: unable to access: Could not resolve host: github.com") == "offline"
    assert classify_fetch_error("fatal: could not read Username: terminal prompts disabled") == "needs password"
    assert classify_fetch_error("git@github.com: Permission denied (publickey).") == "needs password"
    assert classify_fetch_error("something else") == "fetch failed"
