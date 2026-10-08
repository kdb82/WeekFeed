from tests.helpers import FakeCommit, project, repo
from weekfeed import identity
from weekfeed.store import commits, settings
from weekfeed.store.models import AuthorStat


def stat(email, count=1, names=("Someone",)):
    return AuthorStat(email=email, count=count, names=list(names))


def test_first_setup_prechecks_every_candidate():
    stats = [
        stat("me@personal.com", 10),
        stat("12345678+kdb82@users.noreply.github.com", 5),
        stat("kdb82@school.edu", 3, names=("KDB82",)),
        stat("sam@company.com", 50),
    ]
    got = {c.email: c for c in identity.classify(stats, my_emails=[], username="kdb82", config_emails={"me@personal.com"})}
    assert got["me@personal.com"].reasons == ["your git config"]
    assert got["12345678+kdb82@users.noreply.github.com"].reasons == ["GitHub private email"]
    assert got["kdb82@school.edu"].reasons == ["author name matches"]
    assert [e for e, c in got.items() if c.checked] == [
        "me@personal.com", "12345678+kdb82@users.noreply.github.com", "kdb82@school.edu",
    ]
    assert not any(c.is_new for c in got.values())


def test_noreply_without_digits_and_case_insensitive_username():
    got = identity.classify([stat("kdb82@users.noreply.github.com")], my_emails=[], username="KDB82", config_emails=set())
    assert got[0].reasons == ["GitHub private email"]


def test_no_username_means_only_git_config_candidates():
    got = identity.classify([stat("kdb82@users.noreply.github.com")], my_emails=[], username="", config_emails=set())
    assert got[0].reasons == []
    assert not got[0].checked


def test_after_setup_saved_list_wins_and_new_candidates_are_flagged_unchecked():
    stats = [stat("me@personal.com"), stat("new@personal.com"), stat("sam@company.com")]
    got = {c.email: c for c in identity.classify(
        stats, my_emails=["me@personal.com"], username="", config_emails={"me@personal.com", "new@personal.com"},
    )}
    assert got["me@personal.com"].checked and not got["me@personal.com"].is_new
    assert not got["new@personal.com"].checked and got["new@personal.com"].is_new
    assert not got["sam@company.com"].checked and not got["sam@company.com"].is_new


def test_detect_emails_reads_git_config_and_commit_stats(conn, make_repo):
    git_repo = make_repo()
    git_repo.run("config", "user.email", "local@example.com")
    p = project(conn)
    r = repo(conn, p.id, str(git_repo.path))
    commits.insert_commits(conn, r.id, [
        FakeCommit("1", author_email="global@example.com"),
        FakeCommit("2", author_email="local@example.com"),
        FakeCommit("3", author_email="sam@x.io"),
    ])
    settings.set_github_username(conn, "kdb82")
    got = {c.email: c for c in identity.detect_emails(conn)}
    assert got["global@example.com"].checked
    assert got["local@example.com"].checked
    assert not got["sam@x.io"].checked
