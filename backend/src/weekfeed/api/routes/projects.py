from fastapi import APIRouter, Depends, Response

from ...store import drafts as draft_store
from ...store import items as item_store
from ...store import projects as project_store
from ...store import repos as repo_store
from ...timeutil import now_iso
from .. import serialize
from ..deps import get_conn
from ..schemas import ProjectCreate, ProjectPatch

router = APIRouter()


@router.get("/projects")
def list_projects(conn=Depends(get_conn)) -> dict:
    repos = repo_store.list_repos(conn)
    counts = item_store.open_counts_by_project(conn)
    last = draft_store.last_saved_standups(conn)
    return {"projects": [
        serialize.project_card(p, [r for r in repos if r.project_id == p.id], counts.get(p.id, (0, 0)), last.get(p.id))
        for p in project_store.list_projects(conn)
    ]}


def _one_card(conn, project_id: int) -> dict:
    p = project_store.get_project(conn, project_id)
    repos = [r for r in repo_store.list_repos(conn) if r.project_id == p.id]
    return serialize.project_card(
        p, repos, item_store.open_counts_by_project(conn).get(p.id, (0, 0)), draft_store.last_saved_standups(conn).get(p.id)
    )


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, conn=Depends(get_conn)) -> dict:
    p = project_store.create_project(conn, body.name, body.label, now=now_iso())
    return _one_card(conn, p.id)


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectPatch, conn=Depends(get_conn)) -> dict:
    if body.name is not None:
        project_store.rename_project(conn, project_id, body.name)
    if body.label is not None:
        project_store.relabel_project(conn, project_id, body.label)
    return _one_card(conn, project_id)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, confirm_name: str, conn=Depends(get_conn)) -> Response:
    project_store.delete_project(conn, project_id, confirm_name=confirm_name)
    return Response(status_code=204)
