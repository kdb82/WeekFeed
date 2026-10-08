from fastapi import APIRouter, Depends

from ...store import items as item_store
from .. import serialize
from ..deps import get_conn, scope_from

router = APIRouter()


@router.get("/items")
def open_items_panel(label: str | None = None, project_id: int | None = None, conn=Depends(get_conn)) -> dict:
    scope = scope_from(conn, label, project_id)
    open_items = item_store.list_open(conn, scope)
    return {
        "todos": [serialize.item(i) for i in open_items if i.kind == "todo"],
        "blockers": [serialize.item(i) for i in open_items if i.kind == "blocker"],
        "notes": [serialize.item(i) for i in item_store.recent_notes(conn, scope, limit=5)],
    }
