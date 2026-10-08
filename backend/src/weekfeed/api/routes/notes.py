from fastapi import APIRouter, Depends

from ... import notes as note_service
from ...timeutil import now_iso
from .. import serialize
from ..deps import get_conn
from ..schemas import NoteCreate

router = APIRouter()


@router.post("/notes", status_code=201)
def save_note(body: NoteCreate, conn=Depends(get_conn)) -> dict:
    note, batch_id = note_service.save_note(
        conn, text=body.text, label=body.label, project_id=body.project_id,
        input_text="Save answer as note", now=now_iso(),
    )
    return {"item": serialize.item(note), "batch": serialize.batch(conn, batch_id)}
