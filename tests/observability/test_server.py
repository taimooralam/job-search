"""End-to-end-ish tests for the Starlette/FastAPI server.

Spins up the full app under FastAPI's ``TestClient`` (which uses httpx's
WSGI-style transport — no real network). Langfuse is replaced with an in-memory
double that returns canned observation lists. Verifies:

- /healthz works without auth and reflects the upstream double's reachability
- /digest returns 401 without bearer, JSON or markdown with bearer
- tools/list contains the documented surface
- tools/call dispatches to error_summary correctly
- Bearer token rotation overlap (LANGFUSE_MCP_TOKENS comma-separated) works end-to-end
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.observability.langfuse_mcp import server as server_mod
from src.observability.langfuse_mcp.client import DegradedResponse

# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class _FakeClient:
    """Stand-in for LangfuseClient used in tests."""

    project_name = "scout-prod"

    def __init__(self, *, observations: list[dict[str, Any]] | None = None,
                 health_ok: bool = True) -> None:
        self._obs = observations or []
        self._health_ok = health_ok
        self.closed = False

    async def health(self):
        if not self._health_ok:
            return DegradedResponse("langfuse_unreachable", detail="fake")
        return {"status_code": 200, "body_preview": "ok"}

    async def list_recent_errors(self, *, window_minutes: int, limit: int = 50):
        return list(self._obs)[:limit]

    async def list_observations(self, **_kwargs):
        return list(self._obs)

    async def get_trace(self, trace_id: str):
        for obs in self._obs:
            if obs.get("trace_id") == trace_id:
                return {"id": trace_id, "name": "synthetic"}
        return DegradedResponse("upstream_4xx", detail="404")

    async def get_session(self, session_id: str):
        return {"id": session_id, "events": []}

    async def aclose(self) -> None:
        self.closed = True


def _err_obs(*, obs_id: str, fp: str, ts: datetime | None = None) -> dict[str, Any]:
    payload = {
        "error_class": "BoomError",
        "fingerprint": fp,
        "pipeline": "preenrich",
        "stage": "jd_extraction",
        "message": "boom",
        "env": "prod",
    }
    return {
        "id": obs_id,
        "trace_id": f"tr_{obs_id}",
        "session_id": "sess_x",
        "name": "error.preenrich.jd_extraction",
        "level": "ERROR",
        "start_time": (ts or datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)).isoformat(),
        "input": payload,
        "metadata": payload,
        "output": {},
    }


# --------------------------------------------------------------------------- #
# Fixture: app with the prod client patched to a fake
# --------------------------------------------------------------------------- #


@pytest.fixture
def app_with_fakes(monkeypatch):
    """Build the app, then swap in a fake prod client during lifespan."""
    monkeypatch.setenv("LANGFUSE_HOST", "http://example.invalid")
    monkeypatch.setenv("LANGFUSE_PROD_PUBLIC_KEY", "pk-prod")
    monkeypatch.setenv("LANGFUSE_PROD_SECRET_KEY", "sk-prod")
    monkeypatch.delenv("LANGFUSE_DEV_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_DEV_SECRET_KEY", raising=False)
    monkeypatch.setenv("LANGFUSE_MCP_TOKEN", "secret-1")
    monkeypatch.delenv("LANGFUSE_MCP_TOKENS", raising=False)

    fake = _FakeClient(observations=[
        _err_obs(obs_id="a", fp="fp_loud"),
        _err_obs(obs_id="b", fp="fp_loud"),
        _err_obs(obs_id="c", fp="fp_quiet"),
    ])

    # Patch _build_clients so lifespan hands us the fake instead of real LangfuseClient.
    def _fake_build():
        fake.project_name = "scout-prod"
        return {"scout-prod": fake}

    monkeypatch.setattr(server_mod, "_build_clients", _fake_build)

    app = server_mod.create_app()
    with TestClient(app) as client:
        yield client, fake

    assert fake.closed, "lifespan must close the client on shutdown"


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_healthz_no_auth_required(app_with_fakes):
    client, _ = app_with_fakes
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["langfuse_reachable"] is True
    assert body["dev_configured"] is False


def test_healthz_reports_degraded_upstream(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "http://example.invalid")
    monkeypatch.setenv("LANGFUSE_PROD_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_PROD_SECRET_KEY", "sk")
    monkeypatch.delenv("LANGFUSE_DEV_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_DEV_SECRET_KEY", raising=False)
    monkeypatch.setenv("LANGFUSE_MCP_TOKEN", "secret")

    fake = _FakeClient(health_ok=False)
    monkeypatch.setattr(server_mod, "_build_clients", lambda: {"scout-prod": fake})

    with TestClient(server_mod.create_app()) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["langfuse_reachable"] is False
        assert body["reason"] == "langfuse_unreachable"


def test_digest_requires_bearer(app_with_fakes):
    client, _ = app_with_fakes
    r = client.get("/digest")
    assert r.status_code == 401


def test_digest_markdown_default(app_with_fakes):
    client, _ = app_with_fakes
    r = client.get(
        "/digest?window=10&top=5",
        headers={"Authorization": "Bearer secret-1"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    body = r.text
    assert "scout-prod" in body
    assert "BoomError" in body
    assert "| 2 |" in body  # fp_loud collapsed two observations


def test_digest_json_when_accept_json(app_with_fakes):
    client, _ = app_with_fakes
    r = client.get(
        "/digest?window=10&top=5",
        headers={"Authorization": "Bearer secret-1", "Accept": "application/json"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "markdown" not in body  # JSON view drops the Markdown blob
    assert any(row["error_class"] == "BoomError" for row in body["errors"])


def test_mcp_tools_list_returns_documented_surface(app_with_fakes):
    client, _ = app_with_fakes
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": "Bearer secret-1"},
    )
    assert r.status_code == 200
    body = r.json()
    tool_names = {t["name"] for t in body["result"]["tools"]}
    assert {"langfuse.health", "langfuse.error_summary", "langfuse.list_recent_errors"} <= tool_names


def test_mcp_tools_call_error_summary(app_with_fakes):
    client, _ = app_with_fakes
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "langfuse.error_summary", "arguments": {"window_minutes": 60, "top_n": 10}},
        },
        headers={"Authorization": "Bearer secret-1"},
    )
    assert r.status_code == 200
    body = r.json()
    text = body["result"]["content"][0]["text"]
    import json as _json
    parsed = _json.loads(text)
    assert parsed["ok"] is True
    assert parsed["window_minutes"] == 60


def test_mcp_unknown_tool_returns_method_not_found(app_with_fakes):
    client, _ = app_with_fakes
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "langfuse.nope", "arguments": {}},
        },
        headers={"Authorization": "Bearer secret-1"},
    )
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == -32601


def test_token_rotation_overlap(monkeypatch):
    """During rotation overlap, BOTH old and new tokens must authenticate."""
    monkeypatch.setenv("LANGFUSE_HOST", "http://example.invalid")
    monkeypatch.setenv("LANGFUSE_PROD_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_PROD_SECRET_KEY", "sk")
    monkeypatch.delenv("LANGFUSE_DEV_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_DEV_SECRET_KEY", raising=False)
    monkeypatch.setenv("LANGFUSE_MCP_TOKENS", "old-tok, new-tok")
    monkeypatch.delenv("LANGFUSE_MCP_TOKEN", raising=False)

    fake = _FakeClient()
    monkeypatch.setattr(server_mod, "_build_clients", lambda: {"scout-prod": fake})

    with TestClient(server_mod.create_app()) as c:
        for tok in ("old-tok", "new-tok"):
            r = c.get("/digest", headers={"Authorization": f"Bearer {tok}"})
            assert r.status_code == 200, f"token {tok} should still work in overlap window"
        r = c.get("/digest", headers={"Authorization": "Bearer rotated-out"})
        assert r.status_code == 401
