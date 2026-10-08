from dataclasses import asdict

from fastapi import APIRouter, Depends

from ... import sync as sync_service
from ..deps import get_conn, require_git, scope_from
from ..schemas import SyncRequest

router = APIRouter()


@router.post("/sync", dependencies=[Depends(require_git)])
def run_sync(body: SyncRequest, conn=Depends(get_conn)) -> dict:
    scope = None
    if body.project_id is not None or body.label is not None:
        scope = scope_from(conn, body.label, body.project_id)
    results = sync_service.sync_scope(conn, scope, force=body.force)
    return {"results": [asdict(r) for r in results]}
