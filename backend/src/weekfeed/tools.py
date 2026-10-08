"""Tool sets the agent can use: drafting chat (items + update_draft) and Ask chat (add_note only)."""
from __future__ import annotations

from .agent import Tool, ToolError, TurnContext, apply_write
from .llm import function_tool
from .sections import SECTION_TITLES, sections_array_schema
from .store import drafts as draft_store
from .store import items as item_store
from .store import projects as project_store
from .store.models import LABELS, Item, Scope

PROJECT_PARAM = {
    "type": ["string", "null"],
    "description": "Project name within the label, or null to use the current project (or none).",
}
TEXT_PARAM = {"type": "string"}


def _item_json(i: Item) -> dict:
    return {"id": i.id, "kind": i.kind, "text": i.text, "status": i.status, "project": i.project_name}


def _resolve_project(ctx: TurnContext, label: str, name) -> int | None:
    """Label lock: project names only resolve inside the given label."""
    if name is None or not str(name).strip():
        if ctx.scope is not None and ctx.scope.label == label:
            return ctx.scope.project_id
        return None
    found = project_store.find_project_by_name(ctx.conn, label, str(name))
    if found is None:
        valid = ", ".join(p.name for p in project_store.list_projects_in_label(ctx.conn, label)) or "none"
        raise ToolError(f"Unknown project '{name}' in {label}. Valid projects: {valid}")
    return found.id


def _locked_item(ctx: TurnContext, item_id) -> Item:
    item = item_store.get_item(ctx.conn, int(item_id))
    if item is None or ctx.scope is None or item.label != ctx.scope.label:
        raise ToolError(f"Item {item_id} not found")
    return item


def _list_open(ctx: TurnContext, args: dict) -> dict:
    label = ctx.scope.label
    project_id = _resolve_project(ctx, label, args.get("project"))
    return {"items": [_item_json(i) for i in item_store.list_open(ctx.conn, Scope(label, project_id))]}


def _adder(kind: str):
    def handler(ctx: TurnContext, args: dict) -> dict:
        text = str(args["text"]).strip()
        if not text:
            raise ToolError("text is required")
        label = ctx.scope.label
        project_id = _resolve_project(ctx, label, args.get("project"))
        item = apply_write(ctx, lambda at: (
            item_store.create_item(ctx.conn, label=label, kind=kind, text=text, project_id=project_id, now=at),
            "created", None, "open",
        ))
        return {"ok": True, "item": _item_json(item)}
    return handler


def _closer(kind: str, status: str):
    def handler(ctx: TurnContext, args: dict) -> dict:
        item = _locked_item(ctx, args["item_id"])
        if item.kind != kind or item.status != "open":
            raise ToolError(f"Item {item.id} is not an open {kind}")
        updated = apply_write(ctx, lambda at: (
            item_store.set_status(ctx.conn, item.id, status, now=at), "status_changed", "open", status,
        ))
        return {"ok": True, "item": _item_json(updated)}
    return handler


def _update_draft(kind: str):
    titles = SECTION_TITLES[kind]

    def handler(ctx: TurnContext, args: dict) -> dict:
        sections = args["sections"]
        if [s.get("title") for s in sections] != titles:
            raise ToolError(f"Sections must be exactly {', '.join(titles)}, in that order")
        draft_store.update_sections(ctx.conn, ctx.draft_id, [{"title": s["title"], "text": str(s["text"])} for s in sections])
        ctx.draft_updated = True
        return {"ok": True}
    return handler


def drafting_tools(kind: str) -> list[Tool]:
    titles = SECTION_TITLES[kind]
    project_only = {"project": PROJECT_PARAM}
    add_props = {"text": TEXT_PARAM, "project": PROJECT_PARAM}
    id_props = {"item_id": {"type": "integer"}}
    return [
        Tool("list_open_items", function_tool("list_open_items", "List open todos and blockers in scope, with ids.", project_only), _list_open),
        Tool("add_note", function_tool("add_note", "Save a note to the user's knowledge base.", add_props), _adder("note")),
        Tool("add_todo", function_tool("add_todo", "Add an open todo.", add_props), _adder("todo")),
        Tool("add_blocker", function_tool("add_blocker", "Add an open blocker.", add_props), _adder("blocker")),
        Tool("mark_todo_done", function_tool("mark_todo_done", "Mark an open todo as done.", id_props), _closer("todo", "done")),
        Tool("resolve_blocker", function_tool("resolve_blocker", "Mark an open blocker as resolved.", id_props), _closer("blocker", "resolved")),
        Tool("update_draft", function_tool(
            "update_draft", f"Replace the whole draft. Sections must be exactly {', '.join(titles)}, in that order.",
            {"sections": sections_array_schema(titles)},
        ), _update_draft(kind)),
    ]


def _ask_add_note(ctx: TurnContext, args: dict) -> dict:
    label = args["label"]
    if label not in LABELS:
        raise ToolError(f"label must be one of {', '.join(LABELS)}")
    text = str(args["text"]).strip()
    if not text:
        raise ToolError("text is required")
    project_id = _resolve_project(ctx, label, args.get("project"))
    item = apply_write(ctx, lambda at: (
        item_store.create_item(ctx.conn, label=label, kind="note", text=text, project_id=project_id, now=at),
        "created", None, "open",
    ))
    return {"ok": True, "item": _item_json(item)}


def ask_tools() -> list[Tool]:
    return [Tool("add_note", function_tool(
        "add_note", "Save a note to the user's knowledge base. Only when the user asks you to remember or save something.",
        {"text": TEXT_PARAM, "label": {"type": "string", "enum": list(LABELS)}, "project": PROJECT_PARAM},
    ), _ask_add_note)]
