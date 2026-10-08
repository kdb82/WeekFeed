from pathlib import Path

from fastapi import APIRouter, Depends, Response

from ... import git_reader
from ... import sync as sync_service
from ...store import repos as repo_store
from ...store.errors import Invalid
from ...timeutil import now_iso
from .. import serialize
from ..deps import get_conn, require_git
from ..schemas import RepoCreate

router = APIRouter()


@router.post("/repos", status_code=201, dependencies=[Depends(require_git)])
def add_repo(body: RepoCreate, conn=Depends(get_conn)) -> dict:
    path = git_reader.resolve_path(body.path)
    if not git_reader.is_work_tree(path):
        raise Invalid(f"{path} is not a git repository")
    repo = repo_store.add_repo(conn, body.project_id, path, Path(path).name, now=now_iso())
    sync_service.sync_repos(conn, [repo], force=True)
    return serialize.repo(repo_store.get_repo(conn, repo.id))


@router.delete("/repos/{repo_id}", status_code=204)
def remove_repo(repo_id: int, conn=Depends(get_conn)) -> Response:
    repo_store.remove_repo(conn, repo_id)
    return Response(status_code=204)
