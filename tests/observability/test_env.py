"""Environment introspection tests.

These helpers tag every Langfuse observation; if they regress, every fingerprint
and dedup bucket downstream silently breaks. Pin tightly.
"""

from __future__ import annotations

from src.observability import env


def test_current_env_known_values(monkeypatch):
    for value in ("prod", "dev", "staging"):
        monkeypatch.setenv("SCOUT_ENV", value)
        assert env.current_env() == value


def test_current_env_unknown_normalises(monkeypatch):
    monkeypatch.setenv("SCOUT_ENV", "weird")
    assert env.current_env() == "unknown"


def test_current_env_missing_normalises(monkeypatch):
    monkeypatch.delenv("SCOUT_ENV", raising=False)
    assert env.current_env() == "unknown"


def test_current_cli_known(monkeypatch):
    monkeypatch.setenv("SCOUT_CLI", "claude")
    assert env.current_cli() == "claude"
    monkeypatch.setenv("SCOUT_CLI", "CODEX")
    assert env.current_cli() == "codex"


def test_current_cli_default_none(monkeypatch):
    monkeypatch.delenv("SCOUT_CLI", raising=False)
    assert env.current_cli() == "none"


def test_current_host_returns_nonempty_string():
    assert isinstance(env.current_host(), str)
    assert env.current_host()


def test_current_git_sha_honours_explicit_override(monkeypatch):
    env.current_git_sha.cache_clear()
    monkeypatch.setenv("SCOUT_GIT_SHA", "abcdef123456789")
    try:
        assert env.current_git_sha() == "abcdef123456"
    finally:
        env.current_git_sha.cache_clear()


def test_repo_root_resolves_to_repo_with_dotgit():
    env.repo_root.cache_clear()
    try:
        root = env.repo_root()
        assert root is not None
        assert (root / ".git").exists()
    finally:
        env.repo_root.cache_clear()
