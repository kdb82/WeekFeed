"""Ask chat: question -> keywords -> FTS5 top 15 -> answer with [n] citations.

Swapping in embedding search later means replacing find_sources() only.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from .agent import TurnContext, run_turn
from .llm import LLM, AIDisabled, LLMError, respond_json
from .store import fts
from .store import settings as settings_store
from .store.errors import Invalid
from .store.models import SearchHit
from .timeutil import iso
from .tools import ask_tools

TOP_K = 15
NOT_FOUND = "I couldn't find this in your notes or commits."

STOP_WORDS = frozenset(
    "a an and are as at be but by can could did do does for from had has have how i if in into is it its me my "
    "of on or our should so that the their them then there these this to was we were what when where which who "
    "why will with would you your about again any".split()
)
WORD_RE = re.compile(r"[A-Za-z0-9_./+-]+")

TERMS_RULES = """Turn the user's latest question into 3-10 keyword search terms for a full-text search over their notes,
todos, and git commit messages and file paths. Include close variants and synonyms (e.g. auth, login, token, session).
Single lowercase words. Use the earlier messages to resolve follow-up questions."""
TERMS_SCHEMA = {
    "type": "object",
    "properties": {"terms": {"type": "array", "items": {"type": "string"}}},
    "required": ["terms"],
    "additionalProperties": False,
}

ANSWER_RULES = f"""You answer questions about the user's own past work using only the numbered sources provided.
- Cite sources inline as [n] right after the claim they support.
- If the sources don't contain the answer, reply exactly: "{NOT_FOUND}"
- Be concise.
- Only call add_note when the user explicitly asks you to remember or save something."""


@dataclass(frozen=True)
class Citation:
    n: int
    source_type: str
    source_id: int
    title: str
    meta: str
    body: str
    label: str
    project_id: int | None


@dataclass(frozen=True)
class AskResult:
    answer: str
    terms: list[str]
    citations: list[Citation]
    batch_id: int | None


def fallback_terms(question: str) -> list[str]:
    words = [w.strip("./+-").lower() for w in WORD_RE.findall(question)]
    return list(dict.fromkeys(w for w in words if len(w) > 1 and w not in STOP_WORDS))


def extract_terms(llm: LLM, messages: list[dict]) -> list[str]:
    recent = [{"role": m["role"], "content": m["content"]} for m in messages[-5:]]
    data = respond_json(llm, recent, instructions=TERMS_RULES, schema=TERMS_SCHEMA, schema_name="search_terms")
    return [t.strip().lower() for t in data.get("terms", []) if isinstance(t, str) and t.strip()]


def find_sources(conn: sqlite3.Connection, llm: LLM, messages: list[dict], question: str) -> tuple[list[str], list[SearchHit]]:
    emails = settings_store.get_my_emails(conn)
    try:
        terms = extract_terms(llm, messages)
    except LLMError:
        terms = []
    hits = fts.search(conn, terms, emails, limit=TOP_K) if terms else []
    if not hits:
        terms = fallback_terms(question)
        hits = fts.search(conn, terms, emails, limit=TOP_K)
    return terms, hits


def ask(conn: sqlite3.Connection, llm: LLM | None, messages: list[dict], *, now: datetime) -> AskResult:
    if llm is None:
        raise AIDisabled("AI features are off: add OPENAI_API_KEY and OPENAI_MODEL to .env")
    if not messages or messages[-1].get("role") != "user" or not str(messages[-1].get("content", "")).strip():
        raise Invalid("Ask needs a question as the last message")
    question = str(messages[-1]["content"]).strip()
    terms, hits = find_sources(conn, llm, messages, question)

    sources = "\n\n".join(f"[{n}] {h.meta}\n{h.body}" for n, h in enumerate(hits, start=1)) or "(no matching sources)"
    history = [{"role": m["role"], "content": m["content"]} for m in messages[:-1]]
    ctx = TurnContext(conn=conn, scope=None, source="ask_chat", draft_id=None, input_text=question, now=lambda: iso(now))
    result = run_turn(
        llm, ctx, tools=ask_tools(), instructions=ANSWER_RULES,
        input=[*history, {"role": "user", "content": f"Sources:\n{sources}\n\nQuestion: {question}"}],
    )
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", result.text) if 1 <= int(n) <= len(hits)})
    citations = [
        Citation(n, h.source_type, h.source_id, h.title, h.meta, h.body, h.label, h.project_id)
        for n, h in ((n, hits[n - 1]) for n in cited)
    ]
    return AskResult(answer=result.text, terms=terms, citations=citations, batch_id=result.batch_id)
