"""Drafting sessions: date range, context gathering, v1, chat turns, Discord version, save."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta, tzinfo

from .agent import TurnContext, run_turn
from .llm import LLM, AIDisabled, respond_json
from .sections import SECTION_TITLES, normalize_sections, render_record, sections_schema
from .store import batches as batch_store
from .store import commits as commit_store
from .store import drafts as draft_store
from .store import items as item_store
from .store import projects as project_store
from .store import settings as settings_store
from .store.errors import Conflict, Invalid
from .store.models import CommitRow, Draft, DraftMessage, Item, Scope
from .timeutil import iso, local_date, local_minute, parse
from .tools import drafting_tools

COMMIT_CAP = 200
MESSAGE_CHARS = 300
DISCORD_LIMIT = 2000

DRAFT_RULES = """You write concise work updates (standups and weekly updates) for one developer, in first person.
Rules:
- Use only the commits, items and notes provided. Never invent work.
- Turn commit messages into short, readable bullets ("- Fixed the login timeout by refreshing tokens early"), merging related commits.
- In a whole-label update, prefix bullets with the project name in brackets as given, and use [General] for items without a project.
- Every open todo must appear in Today (standup) or Next (weekly). Every open blocker must appear in Blockers. If there are none, write "None".
- Each section's text is a list of "- " bullets."""

CHAT_RULES = DRAFT_RULES + """
You are chatting with the user about this draft. Use tools to add notes, todos and blockers or close them, and call update_draft to change the draft text.
- When items change, call update_draft so Today/Next and Blockers list exactly the open items.
- When it's unclear which item the user means, change nothing for that part and ask.
- Reply in one or two sentences describing what you changed."""

NUDGE = "Items changed during this turn. Call update_draft now so the draft lists exactly the current open todos and blockers."

DISCORD_RULES = """Rewrite this work update as the body of a Discord message. Output only the body, no title line.
Format: each section title in bold on its own line (e.g. **Yesterday**), followed by "- " bullets.
Keep bullets short, keep every todo and blocker, and stay under 1,800 characters."""
SHORTEN = "That is too long for Discord. Shorten it to under 1,800 characters, keeping the same format and every section."


# --- date range ---

def default_start(kind: str, now_local: datetime) -> datetime:
    """Weekly: 7 days back. Standup: 00:00 of the previous workday (Friday when today is Mon/Sat/Sun)."""
    if kind == "weekly":
        return now_local - timedelta(days=7)
    day = now_local.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return datetime.combine(day, time(0, 0), tzinfo=now_local.tzinfo)


# --- context ---

@dataclass(frozen=True)
class DraftContext:
    kind: str
    scope: Scope
    scope_name: str
    period_start: str
    period_end: str
    commits: list[CommitRow]
    closed_items: list[Item]
    new_notes: list[Item]
    open_items: list[Item]


def scope_name(conn: sqlite3.Connection, scope: Scope) -> str:
    if scope.project_id is None:
        return scope.label
    return project_store.get_project(conn, scope.project_id).name


def gather_context(conn: sqlite3.Connection, kind: str, scope: Scope, start: str, end: str) -> DraftContext:
    emails = settings_store.get_my_emails(conn)
    return DraftContext(
        kind=kind, scope=scope, scope_name=scope_name(conn, scope), period_start=start, period_end=end,
        commits=commit_store.my_commits_in_range(conn, scope, start, end, emails, limit=COMMIT_CAP),
        closed_items=item_store.closed_in_range(conn, scope, start, end),
        new_notes=item_store.notes_in_range(conn, scope, start, end),
        open_items=item_store.list_open(conn, scope),
    )


def _tag(project_name: str | None) -> str:
    return f"[{project_name or 'General'}]"


def render_context(ctx: DraftContext) -> str:
    whole_label = " (whole label, all projects)" if ctx.scope.project_id is None else ""
    lines = [
        f"Update type: {ctx.kind}", f"Scope: {ctx.scope_name}{whole_label}",
        f"Range: {local_minute(ctx.period_start)} to {local_minute(ctx.period_end)} (local time)", "", f"## My commits ({len(ctx.commits)})",
    ]
    for c in ctx.commits:
        msg = c.message if len(c.message) <= MESSAGE_CHARS else c.message[:MESSAGE_CHARS] + "…"
        files = ", ".join(c.files_changed[:8]) + (" …" if len(c.files_changed) > 8 else "")
        lines.append(f"- {_tag(c.project_name)} {local_date(c.authored_at)} {c.sha[:7]}: {msg.replace(chr(10), ' / ')} (files: {files})")
    sections = [
        ("Completed in range", [f"- {_tag(i.project_name)} {i.kind} {i.status}: {i.text}" for i in ctx.closed_items]),
        ("Notes added in range", [f"- {_tag(i.project_name)} {i.text}" for i in ctx.new_notes]),
        ("Open todos", [f"- (id {i.id}) {_tag(i.project_name)} {i.text}" for i in ctx.open_items if i.kind == "todo"]),
        ("Open blockers", [f"- (id {i.id}) {_tag(i.project_name)} {i.text}" for i in ctx.open_items if i.kind == "blocker"]),
    ]
    for title, entries in sections:
        lines += ["", f"## {title}", *(entries or ["- none"])]
    return "\n".join(lines)


def draft_stats(conn: sqlite3.Connection, draft: Draft) -> dict:
    ctx = gather_context(conn, draft.kind, Scope(draft.label, draft.project_id), draft.period_start, draft.period_end)
    return {"commits": len(ctx.commits), "closed": len(ctx.closed_items), "notes": len(ctx.new_notes)}


def generate_sections(llm: LLM, ctx: DraftContext) -> list[dict]:
    kind_name = "standup" if ctx.kind == "standup" else "weekly update"
    titles = ", ".join(SECTION_TITLES[ctx.kind])
    data = respond_json(
        llm, [{"role": "user", "content": f"{render_context(ctx)}\n\nWrite the {kind_name} with sections {titles}."}],
        instructions=DRAFT_RULES, schema=sections_schema(ctx.kind), schema_name="draft",
    )
    return normalize_sections(ctx.kind, data.get("sections", []))


# --- session ---

def _require_llm(llm: LLM | None) -> LLM:
    if llm is None:
        raise AIDisabled("AI features are off: add OPENAI_API_KEY and OPENAI_MODEL to .env")
    return llm


def start_draft(conn: sqlite3.Connection, llm: LLM | None, *, kind: str, scope: Scope, now: datetime,
                sync: Callable[[Scope], object]) -> Draft:
    """Resume the in-progress draft for this kind and scope, or create one with a generated v1."""
    if kind not in SECTION_TITLES:
        raise Invalid(f"Unknown draft kind '{kind}'")
    existing = draft_store.find_in_progress(conn, kind, scope)
    if existing:
        return existing
    llm = _require_llm(llm)
    start = draft_store.last_saved_period_end(conn, kind, scope) or iso(default_start(kind, now.astimezone()))
    end = iso(now)
    sync(scope)
    ctx = gather_context(conn, kind, scope, start, end)
    sections = generate_sections(llm, ctx)
    try:
        draft = draft_store.create_draft(conn, kind=kind, scope=scope, period_start=start, period_end=end,
                                         sections=sections, now=end)
    except Conflict:  # another request created it meanwhile
        return draft_store.find_in_progress(conn, kind, scope)  # type: ignore[return-value]
    draft_store.add_message(
        conn, draft_id=draft.id, role="assistant", snapshot=sections, now=end,
        content=f"Here's a first draft from {len(ctx.commits)} commits and your open items.",
    )
    return draft


def _in_progress(conn: sqlite3.Connection, draft_id: int) -> Draft:
    draft = draft_store.get_draft(conn, draft_id)
    if draft.status != "in_progress":
        raise Invalid("Saved drafts are read-only")
    return draft


def chat_turn(conn: sqlite3.Connection, llm: LLM | None, draft_id: int, content: str, *,
              now: datetime) -> tuple[DraftMessage, Draft]:
    llm = _require_llm(llm)
    draft = _in_progress(conn, draft_id)
    content = content.strip()
    if not content:
        raise Invalid("Message is empty")
    draft_store.add_message(conn, draft_id=draft_id, role="user", content=content, now=iso(now))
    return _run_turn(conn, llm, draft, content, now)


def retry_turn(conn: sqlite3.Connection, llm: LLM | None, draft_id: int, *, now: datetime) -> tuple[DraftMessage, Draft]:
    """Re-run the turn for a user message that never got a reply (e.g. after an OpenAI error)."""
    llm = _require_llm(llm)
    draft = _in_progress(conn, draft_id)
    messages = draft_store.list_messages(conn, draft_id)
    if not messages or messages[-1].role != "user":
        raise Invalid("There is no unanswered message to retry")
    return _run_turn(conn, llm, draft, messages[-1].content, now)


def _run_turn(conn, llm, draft: Draft, content: str, now: datetime) -> tuple[DraftMessage, Draft]:
    scope = Scope(draft.label, draft.project_id)
    ctx = gather_context(conn, draft.kind, scope, draft.period_start, draft.period_end)
    history = [{"role": m.role, "content": m.content} for m in draft_store.list_messages(conn, draft.id)[:-1]]
    prompt = f"{render_context(ctx)}\n\n## Current draft\n{render_record(draft.sections)}\n\n## User message\n{content}"
    turn = TurnContext(conn=conn, scope=scope, source="draft_chat", draft_id=draft.id, input_text=content,
                       now=lambda: iso(now))
    result = run_turn(
        llm, turn, tools=drafting_tools(draft.kind), instructions=CHAT_RULES,
        input=[*history, {"role": "user", "content": prompt}],
        nudge=lambda c: NUDGE if c.changes and not c.draft_updated else None,
    )
    updated = draft_store.get_draft(conn, draft.id)
    if result.batch_id is not None:
        batch_store.set_draft_snapshots(conn, result.batch_id, draft.sections, updated.sections)
    message = draft_store.add_message(
        conn, draft_id=draft.id, role="assistant", content=result.text or "Done.",
        snapshot=updated.sections if result.draft_updated else None, batch_id=result.batch_id, now=iso(now),
    )
    return message, updated


def edit_sections(conn: sqlite3.Connection, draft_id: int, sections: list[dict]) -> Draft:
    draft = _in_progress(conn, draft_id)
    return draft_store.update_sections(conn, draft_id, normalize_sections(draft.kind, sections))


def change_range(conn: sqlite3.Connection, llm: LLM | None, draft_id: int, start: str, end: str, *,
                 now: datetime) -> Draft:
    llm = _require_llm(llm)
    draft = _in_progress(conn, draft_id)
    try:
        start_iso, end_iso = iso(parse(start)), iso(parse(end))
    except ValueError as e:
        raise Invalid("Dates must be ISO-8601 timestamps") from e
    draft_store.set_period(conn, draft_id, start_iso, end_iso)
    ctx = gather_context(conn, draft.kind, Scope(draft.label, draft.project_id), start_iso, end_iso)
    updated = draft_store.update_sections(conn, draft_id, generate_sections(llm, ctx))
    draft_store.add_message(
        conn, draft_id=draft_id, role="assistant", snapshot=updated.sections, now=iso(now),
        content=f"Range changed to {local_minute(start_iso)} → {local_minute(end_iso)}. I regenerated the draft.",
    )
    return updated


def _local_tz() -> tzinfo:
    return datetime.now().astimezone().tzinfo  # type: ignore[return-value]


def discord_header(draft: Draft, name: str, tz: tzinfo) -> str:
    end = parse(draft.period_end).astimezone(tz)
    if draft.kind == "standup":
        when = f"{end.strftime('%a %b')} {end.day}"
        title = "Standup"
    else:
        start = parse(draft.period_start).astimezone(tz)
        when = f"{start.strftime('%b')} {start.day} – {end.strftime('%b')} {end.day}"
        title = "Weekly"
    return f"**{title} · {when} · {name}**"


def discord_text(conn: sqlite3.Connection, llm: LLM | None, draft_id: int, *, tz: tzinfo | None = None) -> tuple[str, bool]:
    draft = draft_store.get_draft(conn, draft_id)
    if draft.discord_text:
        return draft.discord_text, len(draft.discord_text) > DISCORD_LIMIT
    llm = _require_llm(llm)
    header = discord_header(draft, scope_name(conn, Scope(draft.label, draft.project_id)), tz or _local_tz())
    messages = [{"role": "user", "content": render_record(draft.sections)}]
    body = llm.respond(messages, instructions=DISCORD_RULES).text.strip()
    text = f"{header}\n{body}"
    if len(text) > DISCORD_LIMIT:
        messages += [{"role": "assistant", "content": body}, {"role": "user", "content": SHORTEN}]
        body = llm.respond(messages, instructions=DISCORD_RULES).text.strip()
        text = f"{header}\n{body}"
    draft_store.set_discord(conn, draft_id, text)
    return text, len(text) > DISCORD_LIMIT


def save_draft(conn: sqlite3.Connection, llm: LLM | None, draft_id: int, *, now: datetime) -> Draft:
    draft = _in_progress(conn, draft_id)
    discord, _ = discord_text(conn, llm, draft_id)
    return draft_store.mark_saved(conn, draft_id, record_text=render_record(draft.sections), discord_text=discord, now=iso(now))


def discard_draft(conn: sqlite3.Connection, draft_id: int) -> None:
    """Deletes the draft and its chat; item changes made during the chat stay (and stay undoable)."""
    draft_store.delete_draft(conn, draft_id)
