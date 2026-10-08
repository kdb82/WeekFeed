from dataclasses import asdict

from fastapi import APIRouter, Depends

from ... import search
from ...timeutil import utcnow
from .. import serialize
from ..deps import get_conn, get_llm
from ..schemas import AskRequest

router = APIRouter()


@router.post("/ask")
def ask(body: AskRequest, conn=Depends(get_conn), llm=Depends(get_llm)) -> dict:
    result = search.ask(conn, llm, [m.model_dump() for m in body.messages], now=utcnow())
    return {
        "answer": result.answer, "terms": result.terms,
        "citations": [asdict(c) for c in result.citations],
        "batch": serialize.batch(conn, result.batch_id),
    }
