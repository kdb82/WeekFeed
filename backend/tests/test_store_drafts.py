import pytest

from tests.helpers import NOW, project
from weekfeed.store import drafts
from weekfeed.store.errors import Conflict, Invalid
from weekfeed.store.models import Scope

SECTIONS = [{"title": "Yesterday", "text": "- a"}, {"title": "Today", "text": "- b"}, {"title": "Blockers", "text": "None"}]


def new_draft(conn, scope, kind="standup", start="2026-10-06T00:00:00.000000+00:00", end="2026-10-07T09:00:00.000000+00:00"):
    return drafts.create_draft(conn, kind=kind, scope=scope, period_start=start, period_end=end, sections=SECTIONS, now=NOW)


def test_create_and_one_in_progress_per_scope_and_kind(conn):
    p = project(conn)
    d = new_draft(conn, Scope("work", p.id))
    assert (d.status, d.sections, d.project_id) == ("in_progress", SECTIONS, p.id)
    new_draft(conn, Scope("work"))  # label-wide is a different scope
    new_draft(conn, Scope("work", p.id), kind="weekly")
    with pytest.raises(Conflict):
        new_draft(conn, Scope("work", p.id))
    assert drafts.find_in_progress(conn, "standup", Scope("work", p.id)).id == d.id


def test_update_sections_clears_discord_cache(conn):
    d = new_draft(conn, Scope("work"))
    drafts.set_discord(conn, d.id, "**cached**")
    updated = drafts.update_sections(conn, d.id, [{"title": "Yesterday", "text": "- new"}])
    assert updated.discord_text is None
    assert updated.sections[0]["text"] == "- new"


def test_saved_drafts_are_read_only_and_cannot_be_discarded(conn):
    d = new_draft(conn, Scope("work"))
    drafts.mark_saved(conn, d.id, record_text="r", discord_text="d", now=NOW)
    saved = drafts.get_draft(conn, d.id)
    assert (saved.status, saved.record_text, saved.saved_at) == ("saved", "r", NOW)
    with pytest.raises(Invalid):
        drafts.update_sections(conn, d.id, SECTIONS)
    with pytest.raises(Invalid):
        drafts.delete_draft(conn, d.id)


def test_last_saved_period_end_per_kind_and_scope(conn):
    scope = Scope("work")
    assert drafts.last_saved_period_end(conn, "standup", scope) is None
    d1 = new_draft(conn, scope, end="2026-10-05T09:00:00.000000+00:00")
    drafts.mark_saved(conn, d1.id, record_text="r", discord_text="d", now=NOW)
    d2 = new_draft(conn, scope, end="2026-10-06T09:00:00.000000+00:00")
    drafts.mark_saved(conn, d2.id, record_text="r", discord_text="d", now=NOW)
    new_draft(conn, scope, end="2026-10-07T09:00:00.000000+00:00")  # in progress: ignored
    assert drafts.last_saved_period_end(conn, "standup", scope) == "2026-10-06T09:00:00.000000+00:00"
    assert drafts.last_saved_period_end(conn, "weekly", scope) is None


def test_list_in_progress_first_then_newest_saved(conn):
    scope = Scope("work")
    a = new_draft(conn, scope)
    drafts.mark_saved(conn, a.id, record_text="r", discord_text="d", now="2026-10-05T00:00:00.000000+00:00")
    b = new_draft(conn, scope)
    drafts.mark_saved(conn, b.id, record_text="r", discord_text="d", now="2026-10-06T00:00:00.000000+00:00")
    c = new_draft(conn, scope)
    assert [d.id for d in drafts.list_drafts(conn, scope)] == [c.id, b.id, a.id]


def test_set_period_validates_order(conn):
    d = new_draft(conn, Scope("work"))
    with pytest.raises(Invalid):
        drafts.set_period(conn, d.id, "2026-10-07T00:00:00.000000+00:00", "2026-10-06T00:00:00.000000+00:00")


def test_messages_round_trip_and_cascade_on_discard(conn):
    d = new_draft(conn, Scope("work"))
    m = drafts.add_message(conn, draft_id=d.id, role="assistant", content="v1", snapshot=SECTIONS, now=NOW)
    drafts.add_message(conn, draft_id=d.id, role="user", content="hi", now=NOW)
    msgs = drafts.list_messages(conn, d.id)
    assert [(x.role, x.content) for x in msgs] == [("assistant", "v1"), ("user", "hi")]
    assert msgs[0].draft_snapshot == SECTIONS and msgs[0].id == m.id
    drafts.delete_draft(conn, d.id)
    assert drafts.list_messages(conn, d.id) == []


def test_last_saved_standups_by_project(conn):
    p = project(conn)
    d = new_draft(conn, Scope("work", p.id))
    drafts.mark_saved(conn, d.id, record_text="r", discord_text="d", now=NOW)
    assert drafts.last_saved_standups(conn) == {p.id: NOW}
