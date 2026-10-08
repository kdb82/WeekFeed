from weekfeed.store import settings


def test_my_emails_default_empty_and_are_normalized(conn):
    assert settings.get_my_emails(conn) == []
    settings.set_my_emails(conn, [" Me@Example.com", "me@example.com", "", "b@x.io"])
    assert settings.get_my_emails(conn) == ["b@x.io", "me@example.com"]


def test_github_username_round_trip(conn):
    assert settings.get_github_username(conn) == ""
    settings.set_github_username(conn, " kdb82 ")
    assert settings.get_github_username(conn) == "kdb82"
