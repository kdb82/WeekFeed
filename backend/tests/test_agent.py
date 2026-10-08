import json

import pytest

from tests.fakes import FakeLLM, reply, tool_calls
from tests.helpers import NOW, item, project
from weekfeed.agent import MAX_ROUNDS, TurnContext, run_turn
from weekfeed.llm import LLMUnavailable
from weekfeed.store import batches, drafts, items
from weekfeed.store.models import Scope
from weekfeed.tools import ask_tools, drafting_tools

SECTIONS = [{"title": "Yesterday", "text": "- a"}, {"title": "Today", "text": "- b"}, {"title": "Blockers", "text": "None"}]


def ctx_for(conn, scope, draft_id=None, source="draft_chat"):
    return TurnContext(conn=conn, scope=scope, source=source, draft_id=draft_id, input_text="user said", now=lambda: NOW)


def run(conn, llm, scope, tools=None, draft_id=None, nudge=None):
    ctx = ctx_for(conn, scope, draft_id)
    result = run_turn(llm, ctx, tools=tools or drafting_tools("standup"), instructions="rules",
                      input=[{"role": "user", "content": "go"}], nudge=nudge)
    return result


def tool_outputs(llm):
    """function_call_output payloads sent back to the model, in order."""
    outs = []
    for call in llm.calls:
        for entry in call["input"]:
            if entry.get("type") == "function_call_output":
                outs.append(json.loads(entry["output"]))
    return outs


def test_add_todo_creates_item_batch_and_change(conn):
    p = project(conn, "api-server")
    llm = FakeLLM([tool_calls(("add_todo", {"text": "Review Sam's PR", "project": None})), reply("Added it.")])
    result = run(conn, llm, Scope("work", p.id))
    assert (result.text, result.changes, result.stopped) == ("Added it.", 1, None)
    [todo] = items.list_open(conn, Scope("work"))
    assert (todo.text, todo.project_id) == ("Review Sam's PR", p.id)  # defaults to the scope's project
    assert batches.get_batch(conn, result.batch_id).summary == "Added it."
    assert [c.action for c in batches.list_changes(conn, result.batch_id)] == ["created"]


def test_project_named_case_insensitively(conn):
    p = project(conn, "api-server")
    llm = FakeLLM([tool_calls(("add_note", {"text": "n", "project": "API-SERVER"})), reply("ok")])
    run(conn, llm, Scope("work"))
    assert items.recent_notes(conn, Scope("work"))[0].project_id == p.id


def test_unknown_project_returns_valid_names_to_the_model(conn):
    project(conn, "api-server")
    project(conn, "mobile-app")
    llm = FakeLLM([tool_calls(("add_todo", {"text": "x", "project": "web"})), reply("Which project?")])
    result = run(conn, llm, Scope("work"))
    assert "api-server, mobile-app" in tool_outputs(llm)[0]["error"]
    assert result.changes == 0 and result.batch_id is None


def test_label_lock_hides_other_labels_items(conn):
    school_todo = item(conn, label="school", text="lab")
    llm = FakeLLM([tool_calls(("mark_todo_done", {"item_id": school_todo.id})), reply("hmm")])
    run(conn, llm, Scope("work"))
    assert tool_outputs(llm)[0] == {"error": f"Item {school_todo.id} not found"}
    assert items.get_item(conn, school_todo.id).status == "open"


def test_invalid_transitions_are_tool_errors(conn):
    blocker = item(conn, kind="blocker", text="db access")
    llm = FakeLLM([tool_calls(("mark_todo_done", {"item_id": blocker.id}), ("resolve_blocker", {"item_id": blocker.id})),
                   reply("done")])
    result = run(conn, llm, Scope("work"))
    outs = tool_outputs(llm)
    assert outs[0]["error"] == f"Item {blocker.id} is not an open todo"
    assert outs[1]["ok"] is True
    assert result.changes == 1
    assert items.get_item(conn, blocker.id).status == "resolved"


def test_list_open_items_is_read_only_and_creates_no_batch(conn):
    item(conn, text="t1")
    llm = FakeLLM([tool_calls(("list_open_items", {"project": None})), reply("You have one todo.")])
    result = run(conn, llm, Scope("work"))
    assert tool_outputs(llm)[0]["items"][0]["text"] == "t1"
    assert result.batch_id is None
    assert conn.execute("SELECT COUNT(*) FROM agent_batches").fetchone()[0] == 0


def test_update_draft_requires_exact_titles(conn):
    d = drafts.create_draft(conn, kind="standup", scope=Scope("work"), period_start="a", period_end="b", sections=SECTIONS, now=NOW)
    bad = [{"title": "Done", "text": "x"}]
    good = [{"title": "Yesterday", "text": "- new"}, {"title": "Today", "text": "- t"}, {"title": "Blockers", "text": "None"}]
    llm = FakeLLM([tool_calls(("update_draft", {"sections": bad})), tool_calls(("update_draft", {"sections": good})), reply("ok")])
    result = run(conn, llm, Scope("work"), draft_id=d.id)
    assert "error" in tool_outputs(llm)[0]
    assert result.draft_updated
    assert drafts.get_draft(conn, d.id).sections[0]["text"] == "- new"


def test_round_limit_stops_the_loop(conn):
    llm = FakeLLM([tool_calls(("list_open_items", {"project": None}))] * MAX_ROUNDS)
    result = run(conn, llm, Scope("work"))
    assert result.stopped == "limit"
    assert result.text == f"Stopped after {MAX_ROUNDS} steps"
    assert len(llm.calls) == MAX_ROUNDS


def test_error_mid_turn_keeps_earlier_writes(conn):
    llm = FakeLLM([tool_calls(("add_todo", {"text": "kept", "project": None})), LLMUnavailable("down")])
    result = run(conn, llm, Scope("work"))
    assert result.stopped == "error"
    assert result.text == "Stopped after an error · 1 changes applied"
    assert [i.text for i in items.list_open(conn, Scope("work"))] == ["kept"]
    assert result.batch_id is not None


def test_error_before_any_write_propagates(conn):
    llm = FakeLLM([LLMUnavailable("down")])
    with pytest.raises(LLMUnavailable):
        run(conn, llm, Scope("work"))


def test_nudge_adds_one_extra_round(conn):
    llm = FakeLLM([tool_calls(("add_todo", {"text": "x", "project": None})), reply("added"), reply("now updated")])
    nudges = []

    def nudge(ctx):
        nudges.append(ctx.changes)
        return "call update_draft"

    result = run(conn, llm, Scope("work"), nudge=nudge)
    assert nudges == [1]
    assert result.text == "now updated"
    assert "call update_draft" in llm.prompt_text(2)


def test_ask_add_note_takes_explicit_label_and_project(conn):
    p = project(conn, "cs340", "school")
    ctx = ctx_for(conn, None, source="ask_chat")
    llm = FakeLLM([tool_calls(("add_note", {"text": "remember this", "label": "school", "project": "cs340"})), reply("Saved.")])
    result = run_turn(llm, ctx, tools=ask_tools(), instructions="", input=[])
    [note] = items.recent_notes(conn, Scope("school"))
    assert (note.text, note.project_id) == ("remember this", p.id)
    b = batches.get_batch(conn, result.batch_id)
    assert (b.source, b.label) == ("ask_chat", None)
