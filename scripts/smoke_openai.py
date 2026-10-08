"""Opt-in check against the real OpenAI API. Never part of pytest.

Run from backend/:  uv run python ../scripts/smoke_openai.py
Needs OPENAI_API_KEY and OPENAI_MODEL in .env. Uses a throwaway database and this repo's own git history.
"""
import tempfile
from dataclasses import replace
from pathlib import Path

from weekfeed import drafts, git_reader, search, sync
from weekfeed.config import REPO_ROOT, load_config
from weekfeed.llm import make_llm
from weekfeed.store import projects, repos, settings
from weekfeed.store.db import connect, migrate
from weekfeed.store.models import Scope
from weekfeed.timeutil import now_iso, utcnow


def main() -> None:
    config = load_config()
    llm = make_llm(config)
    if llm is None:
        raise SystemExit("Set OPENAI_API_KEY and OPENAI_MODEL in .env first.")
    with tempfile.TemporaryDirectory() as tmp:
        config = replace(config, db_path=Path(tmp) / "smoke.db")
        conn = connect(config.db_path)
        migrate(conn)
        p = projects.create_project(conn, "weekfeed", "personal", now=now_iso())
        r = repos.add_repo(conn, p.id, str(REPO_ROOT), "WeekFeed", now=now_iso())
        sync.sync_repos(conn, [r], force=False)
        settings.set_my_emails(conn, [e for e in [git_reader.config_email(None)] if e])
        scope = Scope("personal", p.id)

        draft = drafts.start_draft(conn, llm, kind="weekly", scope=scope, now=utcnow(), sync=lambda s: None)
        print("v1 sections:", draft.sections)
        msg, draft = drafts.chat_turn(conn, llm, draft.id, "Add a todo to write the frontend tests.", now=utcnow())
        print("chat reply:", msg.content, "| batch:", msg.batch_id)
        text, over = drafts.discord_text(conn, llm, draft.id)
        print(f"discord ({len(text)} chars, over_limit={over}):\n{text}")

        answer = search.ask(conn, llm, [{"role": "user", "content": "What did I build in the store layer?"}], now=utcnow())
        print("ask terms:", answer.terms)
        print("ask answer:", answer.answer)
        print("citations:", [c.meta for c in answer.citations])
        conn.close()


if __name__ == "__main__":
    main()
