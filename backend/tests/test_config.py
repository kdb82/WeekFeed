from pathlib import Path

import pytest

from weekfeed.config import REPO_ROOT, load_config

ENV_KEYS = ("OPENAI_API_KEY", "OPENAI_MODEL", "WEEKFEED_DB_PATH", "WEEKFEED_PORT")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_reads_values_from_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "OPENAI_API_KEY=sk-test\nOPENAI_MODEL=test-model\n"
        "WEEKFEED_DB_PATH=/tmp/weekfeed-test.db\nWEEKFEED_PORT=9000\n"
    )
    cfg = load_config(env)
    assert cfg.openai_api_key == "sk-test"
    assert cfg.openai_model == "test-model"
    assert cfg.db_path == Path("/tmp/weekfeed-test.db")
    assert cfg.port == 9000
    assert cfg.ai_enabled


def test_defaults_when_nothing_is_set(tmp_path):
    cfg = load_config(tmp_path / "missing.env")
    assert cfg.openai_api_key is None
    assert not cfg.ai_enabled
    assert cfg.port == 8765
    assert cfg.db_path == REPO_ROOT / "weekfeed.db"


def test_environment_overrides_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("OPENAI_MODEL=from-file\n")
    monkeypatch.setenv("OPENAI_MODEL", "from-env")
    assert load_config(env).openai_model == "from-env"


def test_ai_needs_both_key_and_model(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-test\n")
    assert not load_config(env).ai_enabled
