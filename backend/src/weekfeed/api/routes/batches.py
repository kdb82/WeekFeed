from dataclasses import asdict

from fastapi import APIRouter, Depends

from ...store import batches as batch_store
from ...timeutil import now_iso
from .. import serialize
from ..deps import get_conn
from ..schemas import UndoRequest

router = APIRouter()


@router.post("/batches/{batch_id}/undo")
def undo(batch_id: int, body: UndoRequest, conn=Depends(get_conn)) -> dict:
    result = batch_store.undo_batch(conn, batch_id, force=body.force, now=now_iso())
    return {**asdict(result), "batch": serialize.batch(conn, batch_id)}
