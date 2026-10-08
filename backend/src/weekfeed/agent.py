"""The shared tool-calling loop. Callers pass a tool set; label lock and batches are enforced here and in tools."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from .llm import LLM, LLMError
from .store import batches as batch_store
from .store.db import transaction
from .store.errors import StoreError
from .store.models import Item, Scope
from .timeutil import now_iso

MAX_ROUNDS = 10


class ToolError(Exception):
    """Reported back to the model as a tool result; the turn continues."""


@dataclass
class TurnContext:
    conn: sqlite3.Connection
    scope: Scope | None  # None only for Ask chat, whose add_note takes an explicit label
    source: str  # 'draft_chat' | 'ask_chat'
    draft_id: int | None
    input_text: str
    now: Callable[[], str] = now_iso
    batch_id: int | None = None
    changes: int = 0
    draft_updated: bool = False

    def ensure_batch(self) -> int:
        if self.batch_id is None:
            batch = batch_store.create_batch(
                self.conn, source=self.source,
                label=self.scope.label if self.scope else None,
                project_id=self.scope.project_id if self.scope else None,
                draft_id=self.draft_id, input_text=self.input_text, now=self.now(),
            )
            self.batch_id = batch.id
        return self.batch_id


@dataclass(frozen=True)
class Tool:
    name: str
    schema: dict
    handler: Callable[[TurnContext, dict], dict]


@dataclass(frozen=True)
class TurnResult:
    text: str
    batch_id: int | None
    changes: int
    draft_updated: bool
    stopped: str | None = None  # None | 'error' | 'limit'


Write = Callable[[str], tuple[Item, str, str | None, str | None]]


def apply_write(ctx: TurnContext, write: Write) -> Item:
    """Run one item write and its batch_changes row in a single transaction.

    `write(applied_at)` performs the change using applied_at as the item's timestamp and
    returns (item, action, old_status, new_status).
    """
    batch_id = ctx.ensure_batch()
    applied_at = ctx.now()
    with transaction(ctx.conn):
        item, action, old_status, new_status = write(applied_at)
        batch_store.record_change(ctx.conn, batch_id=batch_id, item=item, action=action,
                                  old_status=old_status, new_status=new_status, applied_at=applied_at)
    ctx.changes += 1
    return item


def run_turn(
    llm: LLM,
    ctx: TurnContext,
    *,
    tools: list[Tool],
    instructions: str,
    input: list[dict],
    nudge: Callable[[TurnContext], str | None] | None = None,
) -> TurnResult:
    by_name = {t.name: t for t in tools}
    schemas = [t.schema for t in tools]
    messages = list(input)
    nudged = False
    for _ in range(MAX_ROUNDS):
        try:
            result = llm.respond(messages, instructions=instructions, tools=schemas)
        except LLMError:
            if ctx.changes:
                return _finish(ctx, f"Stopped after an error · {ctx.changes} changes applied", "error")
            _finish(ctx, "", None)  # drops an empty batch
            raise
        if result.tool_calls:
            messages.extend(result.output_items)
            for call in result.tool_calls:
                output = _call_tool(ctx, by_name, call.name, call.arguments)
                messages.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(output)})
            continue
        if nudge is not None and not nudged:
            prompt = nudge(ctx)
            if prompt:
                nudged = True
                messages.extend(result.output_items)
                messages.append({"role": "user", "content": prompt})
                continue
        return _finish(ctx, result.text, None)
    suffix = f" · {ctx.changes} changes applied" if ctx.changes else ""
    return _finish(ctx, f"Stopped after {MAX_ROUNDS} steps{suffix}", "limit")


def _call_tool(ctx: TurnContext, by_name: dict[str, Tool], name: str, args: dict) -> dict:
    tool = by_name.get(name)
    if tool is None:
        return {"error": f"Unknown tool '{name}'"}
    try:
        return tool.handler(ctx, args)
    except (ToolError, StoreError) as e:
        return {"error": str(e)}
    except (KeyError, TypeError, ValueError) as e:
        return {"error": f"Bad arguments: {e}"}


def _finish(ctx: TurnContext, text: str, stopped: str | None) -> TurnResult:
    if ctx.batch_id is not None:
        if ctx.changes:
            batch_store.set_summary(ctx.conn, ctx.batch_id, text)
        else:
            batch_store.delete_batch(ctx.conn, ctx.batch_id)
            ctx.batch_id = None
    return TurnResult(text=text, batch_id=ctx.batch_id, changes=ctx.changes,
                      draft_updated=ctx.draft_updated, stopped=stopped)
