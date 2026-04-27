"""Bearer-auth contract tests for the langfuse-mcp middleware logic.

Pinned to the §8.1 4-step rotation runbook: the server accepts comma-separated
``LANGFUSE_MCP_TOKENS`` during the overlap window so old + new clients both
authenticate without an outage.
"""

from __future__ import annotations

import pytest

from src.observability.langfuse_mcp.auth import (
    accepted_tokens,
    extract_bearer,
    is_authorized,
)

# --------------------------------------------------------------------------- #
# extract_bearer
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Bearer abc123", "abc123"),
        ("bearer ABC", "ABC"),
        ("BEARER  spaced ", "spaced"),
        ("Token abc", None),
        ("Bearer", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_bearer(header, expected):
    assert extract_bearer(header) == expected


# --------------------------------------------------------------------------- #
# accepted_tokens
# --------------------------------------------------------------------------- #


def test_accepted_tokens_reads_singular(monkeypatch):
    monkeypatch.delenv("LANGFUSE_MCP_TOKENS", raising=False)
    monkeypatch.setenv("LANGFUSE_MCP_TOKEN", "single")
    assert accepted_tokens() == ("single",)


def test_accepted_tokens_prefers_plural(monkeypatch):
    monkeypatch.setenv("LANGFUSE_MCP_TOKEN", "single")
    monkeypatch.setenv("LANGFUSE_MCP_TOKENS", "old, new ,, ")
    # Empty entries dropped, whitespace stripped, plural wins.
    assert accepted_tokens() == ("old", "new")


def test_accepted_tokens_returns_empty_when_unset(monkeypatch):
    monkeypatch.delenv("LANGFUSE_MCP_TOKEN", raising=False)
    monkeypatch.delenv("LANGFUSE_MCP_TOKENS", raising=False)
    assert accepted_tokens() == ()


# --------------------------------------------------------------------------- #
# is_authorized — covers the rotation overlap window
# --------------------------------------------------------------------------- #


def test_is_authorized_accepts_valid_token():
    assert is_authorized("Bearer abc", accepted=("abc",))


def test_is_authorized_accepts_either_during_rotation_overlap():
    assert is_authorized("Bearer old", accepted=("old", "new"))
    assert is_authorized("Bearer new", accepted=("old", "new"))


def test_is_authorized_rejects_unknown_token():
    assert not is_authorized("Bearer wrong", accepted=("right",))


def test_is_authorized_rejects_missing_header():
    assert not is_authorized(None, accepted=("right",))


def test_is_authorized_rejects_empty_acceptlist():
    assert not is_authorized("Bearer abc", accepted=())


def test_is_authorized_reads_env_when_no_acceptlist_passed(monkeypatch):
    monkeypatch.setenv("LANGFUSE_MCP_TOKEN", "from-env")
    monkeypatch.delenv("LANGFUSE_MCP_TOKENS", raising=False)
    assert is_authorized("Bearer from-env")
    assert not is_authorized("Bearer wrong")
