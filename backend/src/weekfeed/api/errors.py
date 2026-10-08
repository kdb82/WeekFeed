"""Maps domain errors to HTTP responses with a uniform {"error", "message"} body."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..llm import AIDisabled, LLMAuthError, LLMError
from ..store.batches import UndoConflictError
from ..store.errors import Conflict, Invalid, NotFound


class GitUnavailable(Exception):
    pass


def error_response(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message, **extra})


def register_error_handlers(app: FastAPI) -> None:
    simple = [
        (NotFound, 404, "not_found"),
        (Conflict, 409, "conflict"),
        (Invalid, 422, "invalid"),
        (AIDisabled, 503, "ai_disabled"),
        (GitUnavailable, 503, "git_unavailable"),
        (LLMAuthError, 502, "llm_auth"),
        (LLMError, 502, "llm_unavailable"),
    ]
    for exc_type, status, code in simple:
        def handler(request: Request, exc: Exception, status=status, code=code) -> JSONResponse:
            return error_response(status, code, str(exc))
        app.add_exception_handler(exc_type, handler)

    def undo_conflict(request: Request, exc: UndoConflictError) -> JSONResponse:
        return error_response(409, "undo_conflict", str(exc), conflicts=[asdict(c) for c in exc.conflicts])
    app.add_exception_handler(UndoConflictError, undo_conflict)
