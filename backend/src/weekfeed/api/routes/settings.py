from dataclasses import asdict

from fastapi import APIRouter, Depends

from ... import identity
from ...store import settings as settings_store
from ..deps import get_conn
from ..schemas import SettingsUpdate

router = APIRouter()


def _settings(conn) -> dict:
    return {"github_username": settings_store.get_github_username(conn), "my_emails": settings_store.get_my_emails(conn)}


@router.get("/settings")
def get_settings(conn=Depends(get_conn)) -> dict:
    return _settings(conn)


@router.put("/settings")
def put_settings(body: SettingsUpdate, conn=Depends(get_conn)) -> dict:
    settings_store.set_github_username(conn, body.github_username)
    settings_store.set_my_emails(conn, body.my_emails)
    return _settings(conn)


@router.get("/settings/emails")
def detected_emails(conn=Depends(get_conn)) -> dict:
    return {"emails": [asdict(c) for c in identity.detect_emails(conn)]}
