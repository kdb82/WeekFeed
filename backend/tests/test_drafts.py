from datetime import datetime, timedelta, timezone

import pytest

from tests.fakes import FakeLLM, reply, structured, tool_calls
from tests.helpers import FakeCommit, item, project, repo
from weekfeed import drafts
from weekfeed.llm import AIDisabled, LLMUnavailable
from weekfeed.store import batches as batch_store, commits, drafts as draft_store, items, settings
from weekfeed.store.errors import Invalid
from weekfeed.store.models import Scope

NOW = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
MDT = timezone(timedelta(hours=-6))
V1 = {"sections": [{"title": "Yesterday", "text": "- Fixed login"}, {"title": "Today", "text": "- Review PR"},
                   {"title": "Blockers", "text": "- DB access"}]}
NO_SYNC = lambda scope: None  # noqa: E731


# --- date ranges ---

@pytest.mark.parametrize("today,expected", [
    (datetime(2026, 10, 7, 9, 0, tzinfo=MDT), datetime(2026, 10, 6, 0, 0, tzinfo=MDT)),  # Wed -> Tue
    (datetime(2026, 10, 5, 9, 0, tzinfo=MDT), datetime(2026, 10, 2, 0, 0, tzinfo=MDT)),  # Mon -> Fri
    (datetime(2026, 10, 4, 9, 0, tzinfo=MDT), datetime(2026, 10, 2, 0, 0, tzinfo=MDT)),  # Sun -> Fri
])
def test_standup_default_start_is_previous_workday(today, expected):
    assert drafts.default_start("standup", today) == expected


def test_weekly_default_start_is_seven_days_back():
    now = datetime(2026, 10, 7, 9, 0, tzinfo=MDT)
    assert drafts.default_start("weekly", now) == now - timedelta(days=7)


# --- gathering ---

def seed(conn):
    api = project(conn, "api-server", "work")
    r = repo(conn, api.id, "/tmp/api")
    settings.set_my_emails(conn, ["me@example.com"])
    commits.insert_commits(conn, r.id, [
        FakeCommit("aaa1111", message="fix: refresh token early", files=["auth/session.py"]),
        FakeCommit("bbb2222", message="someone else's work", author_email="sam@x.io"),
    ])
    item(conn, text="Review Sam's PR", project_id=api.id)
    item(conn, kind="blocker", text="Waiting on DB access")
    item(conn, label="school", text="Finish lab")
    return api


def test_gather_context_and_render(conn):
    api = seed(conn)
    ctx = drafts.gather_context(conn, "standup", Scope("work"), "2026-10-06T00:00:00.000000+00:00", "2026-10-07T15:00:00.000000+00:00")
    assert [c.sha for c in ctx.commits] == ["aaa1111"]
    assert {i.text for i in ctx.open_items} == {"Review Sam's PR", "Waiting on DB access"}
    text = drafts.render_context(ctx)
    assert "[api-server]" in text and "aaa1111" in text and "auth/session.py" in text
    assert "someone else's work" not in text and "Finish lab" not in text
    assert "[General]" in text  # the blocker has no project
    assert "Range: 2026-10-05 18:00 to 2026-10-07 09:00 (local time)" in text


def test_render_context_dates_commits_by_local_day(conn):
    api = project(conn, "api-server", "work")
    r = repo(conn, api.id, "/tmp/api")
    settings.set_my_emails(conn, ["me@example.com"])
    commits.insert_commits(conn, r.id, [FakeCommit("ccc3333", message="late fix", authored_at="2026-10-08T03:00:00.000000+00:00")])
    ctx = drafts.gather_context(conn, "standup", Scope("work"), "2026-10-07T00:00:00.000000+00:00", "2026-10-08T15:00:00.000000+00:00")
    assert "2026-10-07 ccc3333" in drafts.render_context(ctx)
    assert drafts.gather_context(conn, "standup", Scope("work", api.id), "a", "z").scope_name == "api-server"


# --- start ---

def test_start_creates_v1_with_every_open_item_in_the_prompt(conn):
    seed(conn)
    llm = FakeLLM([structured(V1)])
    synced = []
    d = drafts.start_draft(conn, llm, kind="standup", scope=Scope("work"), now=NOW, sync=synced.append)
    assert synced == [Scope("work")]
    assert d.status == "in_progress" and d.sections == V1["sections"]
    prompt = llm.prompt_text(0)
    assert "Review Sam's PR" in prompt and "Waiting on DB access" in prompt
    [msg] = draft_store.list_messages(conn, d.id)
    assert msg.role == "assistant" and msg.draft_snapshot == V1["sections"]
    assert "1 commits" in msg.content


def test_start_resumes_existing_in_progress_without_ai(conn):
    d = drafts.start_draft(conn, FakeLLM([structured(V1)]), kind="standup", scope=Scope("work"), now=NOW, sync=NO_SYNC)
    again = drafts.start_draft(conn, None, kind="standup", scope=Scope("work"), now=NOW, sync=NO_SYNC)
    assert again.id == d.id


def test_start_without_ai_raises(conn):
    with pytest.raises(AIDisabled):
        drafts.start_draft(conn, None, kind="standup", scope=Scope("work"), now=NOW, sync=NO_SYNC)


def test_range_starts_at_last_saved_period_end(conn):
    first = drafts.start_draft(conn, FakeLLM([structured(V1)]), kind="standup", scope=Scope("work"), now=NOW, sync=NO_SYNC)
    draft_store.mark_saved(conn, first.id, record_text="r", discord_text="d", now="x")
    later = NOW + timedelta(days=1)
    second = drafts.start_draft(conn, FakeLLM([structured(V1)]), kind="standup", scope=Scope("work"), now=later, sync=NO_SYNC)
    assert second.period_start == first.period_end


def test_start_with_no_confirmed_emails_still_works(conn):
    api = project(conn)
    r = repo(conn, api.id, "/tmp/api")
    commits.insert_commits(conn, r.id, [FakeCommit("a")])
    d = drafts.start_draft(conn, FakeLLM([structured(V1)]), kind="weekly", scope=Scope("work"), now=NOW, sync=NO_SYNC)
    assert [s["title"] for s in d.sections] == ["Done", "Next", "Blockers"]  # normalized to the kind


# --- chat ---

def started(conn):
    seed(conn)
    return drafts.start_draft(conn, FakeLLM([structured(V1)]), kind="standup", scope=Scope("work"), now=NOW, sync=NO_SYNC)


def test_chat_turn_changes_items_and_updates_draft(conn):
    d = started(conn)
    new_sections = [{"title": "Yesterday", "text": "- Fixed login"}, {"title": "Today", "text": "- Review PR\n- Pair with Sam"},
                    {"title": "Blockers", "text": "- DB access"}]
    llm = FakeLLM([tool_calls(("add_todo", {"text": "Pair with Sam", "project": None})),
                   tool_calls(("update_draft", {"sections": new_sections})), reply("Added a todo.")])
    msg, draft = drafts.chat_turn(conn, llm, d.id, "also pairing with Sam", now=NOW)
    assert msg.role == "assistant" and msg.content == "Added a todo."
    assert msg.batch_id is not None and msg.draft_snapshot == new_sections
    assert draft.sections == new_sections
    assert [m.role for m in draft_store.list_messages(conn, d.id)] == ["assistant", "user", "assistant"]
    assert "also pairing with Sam" in llm.prompt_text(0)


PAIRING = [{"title": "Yesterday", "text": "- Fixed login"}, {"title": "Today", "text": "- Review PR\n- Pair with Sam"},
           {"title": "Blockers", "text": "- DB access"}]


def pairing_turn(conn, d):
    llm = FakeLLM([tool_calls(("add_todo", {"text": "Pair with Sam", "project": None})),
                   tool_calls(("update_draft", {"sections": PAIRING})), reply("Added a todo.")])
    msg, _ = drafts.chat_turn(conn, llm, d.id, "also pairing with Sam", now=NOW)
    return msg.batch_id


def test_undo_restores_the_draft_text_from_before_the_message(conn):
    d = started(conn)
    batch_id = pairing_turn(conn, d)
    draft_store.set_discord(conn, d.id, "cached")
    result = batch_store.undo_batch(conn, batch_id, force=False, now="2026-10-07T16:00:00.000000+00:00")
    assert result.draft_restored is True
    restored = draft_store.get_draft(conn, d.id)
    assert restored.sections == V1["sections"] and restored.discord_text is None
    assert "Pair with Sam" not in {i.text for i in items.list_open(conn, Scope("work"))}


def test_undo_leaves_draft_text_that_changed_after_the_message(conn):
    d = started(conn)
    batch_id = pairing_turn(conn, d)
    mine = [{**s, "text": s["text"] + "\n- my own line"} if s["title"] == "Today" else s for s in PAIRING]
    drafts.edit_sections(conn, d.id, mine)
    result = batch_store.undo_batch(conn, batch_id, force=False, now="2026-10-07T16:00:00.000000+00:00")
    assert result.draft_restored is False and result.reverted == 1
    assert draft_store.get_draft(conn, d.id).sections == mine


def test_undo_of_a_batch_without_a_draft_reports_no_draft(conn):
    i = item(conn)
    ctx_batch = batch_store.create_batch(conn, source="ask_chat", label="work", project_id=None, draft_id=None,
                                         input_text="x", now=NOW.isoformat())
    batch_store.record_change(conn, batch_id=ctx_batch.id, item=i, action="created", old_status=None, new_status=None,
                              applied_at=i.updated_at)
    assert batch_store.undo_batch(conn, ctx_batch.id, force=False, now="2026-10-07T16:00:00.000000+00:00").draft_restored is None


def test_chat_turn_nudges_when_items_change_without_update_draft(conn):
    d = started(conn)
    llm = FakeLLM([tool_calls(("add_todo", {"text": "x", "project": None})), reply("added"),
                   tool_calls(("update_draft", {"sections": V1["sections"]})), reply("updated")])
    msg, _ = drafts.chat_turn(conn, llm, d.id, "add x", now=NOW)
    assert msg.content == "updated"
    assert "update_draft" in llm.prompt_text(2)


def test_failed_turn_can_be_retried_without_resaving_the_message(conn):
    d = started(conn)
    with pytest.raises(LLMUnavailable):
        drafts.chat_turn(conn, FakeLLM([LLMUnavailable("down")]), d.id, "hello", now=NOW)
    msg, _ = drafts.retry_turn(conn, FakeLLM([reply("hi again")]), d.id, now=NOW)
    assert msg.content == "hi again"
    assert [m.role for m in draft_store.list_messages(conn, d.id)] == ["assistant", "user", "assistant"]


def test_retry_with_nothing_pending_is_invalid(conn):
    d = started(conn)
    with pytest.raises(Invalid):
        drafts.retry_turn(conn, FakeLLM(), d.id, now=NOW)


def test_edit_sections_normalizes_and_clears_discord(conn):
    d = started(conn)
    draft_store.set_discord(conn, d.id, "cached")
    edited = drafts.edit_sections(conn, d.id, [{"title": "Today", "text": "- mine"}])
    assert [s["title"] for s in edited.sections] == ["Yesterday", "Today", "Blockers"]
    assert edited.discord_text is None


def test_change_range_regenerates(conn):
    d = started(conn)
    regenerated = {"sections": [{"title": "Yesterday", "text": "- longer range"}, {"title": "Today", "text": ""},
                                {"title": "Blockers", "text": ""}]}
    updated = drafts.change_range(conn, FakeLLM([structured(regenerated)]), d.id,
                                  "2026-10-01T00:00:00Z", "2026-10-07T15:00:00Z", now=NOW)
    assert updated.period_start == "2026-10-01T00:00:00.000000+00:00"
    assert updated.sections[0]["text"] == "- longer range"
    message = draft_store.list_messages(conn, d.id)[-1].content
    assert "Range changed to 2026-09-30 18:00 → 2026-10-07 09:00" in message  # local time, not UTC


# --- discord, save, discard ---

def test_discord_has_code_built_header_and_is_cached(conn):
    d = started(conn)
    llm = FakeLLM([reply("**Yesterday**\n- Fixed login")])
    text, over = drafts.discord_text(conn, llm, d.id, tz=MDT)
    assert text == "**Standup · Wed Oct 7 · work**\n**Yesterday**\n- Fixed login"
    assert not over
    assert drafts.discord_text(conn, None, d.id, tz=MDT) == (text, False)  # cached, no AI needed


def test_discord_shortens_once_then_flags_over_limit(conn):
    d = started(conn)
    llm = FakeLLM([reply("x" * 2500), reply("y" * 2100)])
    text, over = drafts.discord_text(conn, llm, d.id, tz=MDT)
    assert text.endswith("y" * 2100) and over
    assert len(llm.calls) == 2


def test_weekly_discord_header_shows_range(conn):
    d = drafts.start_draft(conn, FakeLLM([structured({"sections": []})]), kind="weekly", scope=Scope("work"), now=NOW, sync=NO_SYNC)
    text, _ = drafts.discord_text(conn, FakeLLM([reply("**Done**\n- x")]), d.id, tz=MDT)
    assert text.startswith("**Weekly · Sep 30 – Oct 7 · work**")


def test_save_renders_record_and_ensures_discord(conn):
    d = started(conn)
    saved = drafts.save_draft(conn, FakeLLM([reply("**Yesterday**\n- Fixed login")]), d.id, now=NOW)
    assert saved.status == "saved"
    assert saved.record_text.startswith("Yesterday\n- Fixed login\n\nToday")
    assert saved.discord_text.startswith("**Standup")
    with pytest.raises(Invalid):
        drafts.chat_turn(conn, FakeLLM(), d.id, "more", now=NOW)


def test_discard_keeps_item_changes(conn):
    d = started(conn)
    drafts.chat_turn(conn, FakeLLM([tool_calls(("add_todo", {"text": "kept", "project": None})),
                                    tool_calls(("update_draft", {"sections": V1["sections"]})), reply("ok")]),
                     d.id, "add kept", now=NOW)
    drafts.discard_draft(conn, d.id)
    assert "kept" in {i.text for i in items.list_open(conn, Scope("work"))}


def test_draft_stats(conn):
    d = started(conn)
    assert drafts.draft_stats(conn, d) == {"commits": 1, "closed": 0, "notes": 0}
