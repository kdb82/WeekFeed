"""Settings loaded from .env (or the real environment, which wins)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    openai_api_key: str | None
    openai_model: str | None
    db_path: Path
    port: int

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key and self.openai_model)


def load_config(env_file: Path | None = None) -> Config:
    path = env_file or REPO_ROOT / ".env"
    file_values = dotenv_values(path) if path.exists() else {}

    def get(key: str) -> str | None:
        return os.environ.get(key) or file_values.get(key) or None

    db_path = Path(get("WEEKFEED_DB_PATH") or "weekfeed.db")
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    return Config(
        openai_api_key=get("OPENAI_API_KEY"),
        openai_model=get("OPENAI_MODEL"),
        db_path=db_path,
        port=int(get("WEEKFEED_PORT") or 8765),
    )
