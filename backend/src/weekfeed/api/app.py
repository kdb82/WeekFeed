from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import git_reader
from ..config import REPO_ROOT, Config, load_config
from ..llm import LLM, make_llm
from ..store.db import connect, migrate
from .errors import register_error_handlers
from .routes import ask, batches, drafts, health, items, notes, projects, repos, settings, sync


def create_app(config: Config | None = None, llm: LLM | None = None, static_dir: Path | None = None) -> FastAPI:
    config = config or load_config()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(config.db_path)
    migrate(conn)
    conn.close()

    app = FastAPI(title="WeekFeed")
    app.state.config = config
    app.state.llm = llm if llm is not None else make_llm(config)
    app.state.git_available = git_reader.git_available()
    register_error_handlers(app)
    for module in (health, projects, repos, sync, settings, drafts, items, notes, batches, ask):
        app.include_router(module.router, prefix="/api")
    mount_frontend(app, static_dir if static_dir is not None else REPO_ROOT / "frontend" / "dist")
    return app


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built React app; unknown non-API paths fall back to index.html for client-side routing."""
    index = dist / "index.html"
    if not index.exists():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)
