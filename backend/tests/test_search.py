from datetime import datetime, timezone

import pytest

from tests.fakes import FakeLLM, reply, structured, tool_calls
from tests.helpers import FakeCommit, item, project, repo
from weekfeed import notes, search
from weekfeed.llm import AIDisabled, LLMUnavailable
from weekfeed.store import batches, commits, items, settings
from weekfeed.store.errors import Invalid
from weekfeed.store.models import Scope

NOW = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)


def seed(conn):
    api = project(conn, "api-server")
    r = repo(conn, api.id, "/tmp/api")
    settings.set_my_emails(conn, ["me@example.com"])
    commits.insert_commits(conn, r.id, [
        FakeCommit("a1b2c3d4", message="fix: refresh token 60s before expiry", files=["auth/session.py"]),
        FakeCommit("ffff0000", message="auth rewrite by sam", author_email="sam@x.io"),
    ])
    item(conn, kind="note", text="Token bug was clock skew", project_id=api.id)
    return api


def ask(conn, llm, *messages):
    return search.ask(conn, llm, [{"role": r, "content": c} for r, c in messages], now=NOW)


def test_fallback_terms_drop_stop_words():
    assert search.fallback_terms("How did I fix the auth bug?") == ["fix", "auth", "bug"]


def test_answer_cites_only_referenced_sources(conn):
    seed(conn)
    llm = FakeLLM([structured({"terms": ["auth", "token"]}), reply("Clock skew [1], fixed by early refresh [2].")])
    result = ask(conn, llm, ("user", "how did I fix the auth bug?"))
    assert result.terms == ["auth", "token"]
    assert [c.n for c in result.citations] == [1, 2]
    assert {c.source_type for c in result.citations} == {"item", "commit"}
    sources_prompt = llm.prompt_text(1)
    assert "auth rewrite by sam" not in sources_prompt  # other authors excluded
    assert result.batch_id is None


def test_keyword_call_sees_recent_conversation(conn):
    seed(conn)
    llm = FakeLLM([structured({"terms": ["token"]}), reply("Because [1].")])
    ask(conn, llm, ("user", "how did I fix the auth bug?"), ("assistant", "Early refresh."), ("user", "and why?"))
    assert "how did I fix the auth bug?" in llm.prompt_text(0)


def test_falls_back_when_keywords_find_nothing(conn):
    seed(conn)
    llm = FakeLLM([structured({"terms": ["zzzz"]}), reply("Clock skew [1].")])
    result = ask(conn, llm, ("user", "what was the token issue"))
    assert result.terms == ["token", "issue"]
    assert result.citations


def test_falls_back_when_keyword_call_fails(conn):
    seed(conn)
    llm = FakeLLM([LLMUnavailable("down"), reply("Clock skew [1].")])
    assert ask(conn, llm, ("user", "token bug")).citations


def test_no_sources_still_answers(conn):
    llm = FakeLLM([structured({"terms": ["nothing"]}), reply(search.NOT_FOUND)])
    result = ask(conn, llm, ("user", "anything?"))
    assert result.answer == search.NOT_FOUND and result.citations == []
    assert "(no matching sources)" in llm.prompt_text(1)


def test_out_of_range_citation_numbers_are_ignored(conn):
    seed(conn)
    llm = FakeLLM([structured({"terms": ["token"]}), reply("See [1] and [99].")])
    assert [c.n for c in ask(conn, llm, ("user", "token")).citations] == [1]


def test_add_note_from_ask(conn):
    seed(conn)
    llm = FakeLLM([structured({"terms": ["x"]}),
                   tool_calls(("add_note", {"text": "remember: deploy fridays", "label": "work", "project": None})),
                   reply("Saved.")])
    result = ask(conn, llm, ("user", "remember that we deploy on fridays"))
    assert result.batch_id is not None
    assert items.recent_notes(conn, Scope("work"))[0].text == "remember: deploy fridays"


def test_ask_requires_ai_and_a_question(conn):
    with pytest.raises(AIDisabled):
        ask(conn, None, ("user", "q"))
    with pytest.raises(Invalid):
        ask(conn, FakeLLM(), ("assistant", "hi"))


def test_save_note_records_an_undoable_batch(conn):
    api = seed(conn)
    note, batch_id = notes.save_note(conn, text="answer text", label="work", project_id=api.id,
                                     input_text="Save answer as note", now="2026-10-07T15:00:00.000000+00:00")
    assert note.kind == "note" and note.project_id == api.id
    b = batches.get_batch(conn, batch_id)
    assert (b.source, b.summary) == ("ask_chat", "Saved answer as note")
    batches.undo_batch(conn, batch_id, force=False, now="2026-10-07T16:00:00.000000+00:00")
    assert items.get_item(conn, note.id) is None
