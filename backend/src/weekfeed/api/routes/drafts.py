from fastapi import APIRouter, Depends, Request, Response

from ... import drafts as draft_service
from ... import sync as sync_service
from ...store import drafts as draft_store
from ...store.errors import Invalid
from ...timeutil import utcnow
from .. import serialize
from ..deps import get_conn, get_llm, scope_from
from ..schemas import DraftCreate, DraftPatch, MessageCreate

router = APIRouter()


def _detail(conn, draft_id: int) -> dict:
    draft = draft_store.get_draft(conn, draft_id)
    return {
        "draft": serialize.draft(draft),
        "messages": [serialize.message(conn, m) for m in draft_store.list_messages(conn, draft_id)],
        "stats": draft_service.draft_stats(conn, draft),
    }


@router.get("/drafts")
def history(label: str | None = None, project_id: int | None = None, conn=Depends(get_conn)) -> dict:
    scope = scope_from(conn, label, project_id)
    return {"drafts": [serialize.draft(d) for d in draft_store.list_drafts(conn, scope)]}


@router.post("/drafts", status_code=201)
def start(body: DraftCreate, request: Request, conn=Depends(get_conn), llm=Depends(get_llm)) -> dict:
    scope = scope_from(conn, body.label, body.project_id)

    def sync(s):
        if request.app.state.git_available:
            sync_service.sync_scope(conn, s, force=False)

    draft = draft_service.start_draft(conn, llm, kind=body.kind, scope=scope, now=utcnow(), sync=sync)
    return _detail(conn, draft.id)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int, conn=Depends(get_conn)) -> dict:
    return _detail(conn, draft_id)


@router.patch("/drafts/{draft_id}")
def patch_draft(draft_id: int, body: DraftPatch, conn=Depends(get_conn), llm=Depends(get_llm)) -> dict:
    if body.sections is not None:
        draft_service.edit_sections(conn, draft_id, [s.model_dump() for s in body.sections])
    elif body.period_start and body.period_end:
        draft_service.change_range(conn, llm, draft_id, body.period_start, body.period_end, now=utcnow())
    else:
        raise Invalid("Send sections, or both period_start and period_end")
    return _detail(conn, draft_id)


def _turn_response(conn, message, draft) -> dict:
    return {"message": serialize.message(conn, message), "draft": serialize.draft(draft)}


@router.post("/drafts/{draft_id}/messages")
def send_message(draft_id: int, body: MessageCreate, conn=Depends(get_conn), llm=Depends(get_llm)) -> dict:
    message, draft = draft_service.chat_turn(conn, llm, draft_id, body.content, now=utcnow())
    return _turn_response(conn, message, draft)


@router.post("/drafts/{draft_id}/retry")
def retry(draft_id: int, conn=Depends(get_conn), llm=Depends(get_llm)) -> dict:
    message, draft = draft_service.retry_turn(conn, llm, draft_id, now=utcnow())
    return _turn_response(conn, message, draft)


@router.get("/drafts/{draft_id}/discord")
def discord(draft_id: int, conn=Depends(get_conn), llm=Depends(get_llm)) -> dict:
    text, over_limit = draft_service.discord_text(conn, llm, draft_id)
    return {"text": text, "over_limit": over_limit}


@router.post("/drafts/{draft_id}/save")
def save(draft_id: int, conn=Depends(get_conn), llm=Depends(get_llm)) -> dict:
    draft_service.save_draft(conn, llm, draft_id, now=utcnow())
    return _detail(conn, draft_id)


@router.delete("/drafts/{draft_id}", status_code=204)
def discard(draft_id: int, conn=Depends(get_conn)) -> Response:
    draft_service.discard_draft(conn, draft_id)
    return Response(status_code=204)
