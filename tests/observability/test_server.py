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

    def __init__(
        self,
        *,
        observations: list[dict[str, Any]] | None = None,
        health_ok: bool = True,
        traces: list[dict[str, Any]] | None = None,
        traces_response: Any = None,
    ) -> None:
        self._obs = observations or []
        self._health_ok = health_ok
        self._traces = traces or []
        # If set, list_recent_traces returns this verbatim (used to inject
        # DegradedResponse / ValueError sentinels). Else it returns _traces
        # capped by limit.
        self._traces_response = traces_response
        # Capture call kwargs so tests can assert clamping / arg-passthrough.
        self.list_recent_traces_calls: list[dict[str, Any]] = []
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

    async def list_recent_traces(self, **kwargs):
        self.list_recent_traces_calls.append(kwargs)
        # Mirror the real client's bounds check so tests cover the route.
        window = kwargs.get("window_minutes")
        if window is not None and (window <= 0 or window > 1440):
            raise ValueError("window_minutes must be in (0, 1440]")
        if isinstance(self._traces_response, BaseException):
            raise self._traces_response
        if self._traces_response is not None:
            return self._traces_response
        limit = int(kwargs.get("limit") or 50)
        return list(self._traces)[:limit]

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


# --------------------------------------------------------------------------- #
# langfuse.list_recent_traces (iteration-4.4 §20)
# --------------------------------------------------------------------------- #


def _trace(*, tid: str, env: str = "prod", name: str = "scout.search.run") -> dict[str, Any]:
    return {
        "id": tid,
        "name": name,
        "timestamp": "2026-04-28T10:00:00+00:00",
        "sessionId": f"sess_{tid}",
        "userId": None,
        "tags": [],
        "release": None,
        "version": None,
        "input": {"x": 1},
        "output": {"y": 2},
        "metadata": {"env": env, "pipeline": "preenrich"},
    }


def _traces_app(monkeypatch, *, traces=None, traces_response=None):
    """Build the FastAPI app with a fake client preloaded with traces."""
    monkeypatch.setenv("LANGFUSE_HOST", "http://example.invalid")
    monkeypatch.setenv("LANGFUSE_PROD_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_PROD_SECRET_KEY", "sk")
    monkeypatch.delenv("LANGFUSE_DEV_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_DEV_SECRET_KEY", raising=False)
    monkeypatch.setenv("LANGFUSE_MCP_TOKEN", "secret-1")
    monkeypatch.delenv("LANGFUSE_MCP_TOKENS", raising=False)
    fake = _FakeClient(traces=traces, traces_response=traces_response)
    monkeypatch.setattr(server_mod, "_build_clients", lambda: {"scout-prod": fake})
    return fake


def _call_list_recent_traces(client: TestClient, **arguments):
    return client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {"name": "langfuse.list_recent_traces", "arguments": arguments},
        },
        headers={"Authorization": "Bearer secret-1"},
    )


def test_mcp_tools_list_includes_list_recent_traces(app_with_fakes):
    c, _ = app_with_fakes
    r = c.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": "Bearer secret-1"},
    )
    tool_names = {t["name"] for t in r.json()["result"]["tools"]}
    assert "langfuse.list_recent_traces" in tool_names


def test_list_recent_traces_returns_array(monkeypatch):
    fake = _traces_app(
        monkeypatch,
        traces=[_trace(tid="a"), _trace(tid="b"), _trace(tid="c")],
    )
    with TestClient(server_mod.create_app()) as c:
        r = _call_list_recent_traces(c, window_minutes=60, limit=5)
    assert r.status_code == 200
    import json as _json
    parsed = _json.loads(r.json()["result"]["content"][0]["text"])
    assert parsed["ok"] is True
    assert parsed["count"] == 3
    assert [t["id"] for t in parsed["traces"]] == ["a", "b", "c"]
    assert parsed["traces"][0]["session_id"] == "sess_a"
    # capture: real client got the right call kwargs
    assert fake.list_recent_traces_calls[-1]["window_minutes"] == 60
    assert fake.list_recent_traces_calls[-1]["limit"] == 5


def test_list_recent_traces_clamps_limit_to_100(monkeypatch):
    fake = _traces_app(monkeypatch, traces=[_trace(tid=str(i)) for i in range(5)])
    with TestClient(server_mod.create_app()) as c:
        r = _call_list_recent_traces(c, window_minutes=60, limit=500)
    assert r.status_code == 200
    assert fake.list_recent_traces_calls[-1]["limit"] == 100


def test_list_recent_traces_window_validation_returns_degraded(monkeypatch):
    # window_minutes=0 trips the (0, 1440] guard inside the fake (which
    # mirrors the real client) and the dispatch branch must catch it as a
    # DegradedResponse rather than raising to MCP.
    _traces_app(monkeypatch, traces=[_trace(tid="a")])
    with TestClient(server_mod.create_app()) as c:
        # window_minutes default = 60, but a too-low explicit value coerces
        # via the dispatch's max(1, min(..., 1440)). To actually hit the
        # ValueError path we have to bypass dispatch's clamp by injecting a
        # fake that raises unconditionally:
        pass
    # Now exercise the explicit ValueError path by replacing the fake.
    fake = _traces_app(monkeypatch, traces_response=ValueError("window_minutes must be in (0, 1440]"))
    with TestClient(server_mod.create_app()) as c:
        r = _call_list_recent_traces(c, window_minutes=60)
    assert r.status_code == 200
    import json as _json
    parsed = _json.loads(r.json()["result"]["content"][0]["text"])
    assert parsed.get("degraded") is True
    assert parsed["reason"] == "invalid_argument"
    assert "window_minutes" in parsed["detail"]
    assert fake.list_recent_traces_calls  # the call was attempted


def test_list_recent_traces_filters_by_env(monkeypatch):
    _traces_app(
        monkeypatch,
        traces=[
            _trace(tid="a", env="prod"),
            _trace(tid="b", env="prod"),
            _trace(tid="c", env="dev"),
        ],
    )
    with TestClient(server_mod.create_app()) as c:
        r = _call_list_recent_traces(c, window_minutes=60, env="prod")
    import json as _json
    parsed = _json.loads(r.json()["result"]["content"][0]["text"])
    assert parsed["count"] == 2
    assert {t["id"] for t in parsed["traces"]} == {"a", "b"}


def test_list_recent_traces_name_prefix_filters_clientside(monkeypatch):
    fake = _traces_app(
        monkeypatch,
        traces=[
            _trace(tid="a", name="preenrich.jd_extraction"),
            _trace(tid="b", name="preenrich.classification"),
            _trace(tid="c", name="scout.work_item.enqueue"),
            _trace(tid="d", name="scout.search.run"),
            _trace(tid="e", name="preenrich.role_research"),
        ],
    )
    with TestClient(server_mod.create_app()) as c:
        r = _call_list_recent_traces(c, name_prefix="preenrich.", limit=10)
    import json as _json
    parsed = _json.loads(r.json()["result"]["content"][0]["text"])
    # All three preenrich.* traces returned; both scout.* dropped.
    assert parsed["count"] == 3
    assert {t["id"] for t in parsed["traces"]} == {"a", "b", "e"}
    # Server over-fetched up to 100 to give the prefix filter room to work.
    assert fake.list_recent_traces_calls[-1]["limit"] == 100
    # `name` upstream filter not set when prefix is in play.
    assert fake.list_recent_traces_calls[-1]["name"] is None


def test_list_recent_traces_exact_name_wins_over_prefix(monkeypatch):
    fake = _traces_app(
        monkeypatch,
        traces=[_trace(tid="x", name="scout.search.run")],
    )
    with TestClient(server_mod.create_app()) as c:
        r = _call_list_recent_traces(
            c,
            name="scout.search.run",
            name_prefix="preenrich.",
            limit=5,
        )
    parsed = __import__("json").loads(r.json()["result"]["content"][0]["text"])
    # When both are passed, exact `name` is used and prefix is ignored;
    # over-fetch should NOT trigger (limit stays at caller's limit).
    assert parsed["count"] == 1
    assert fake.list_recent_traces_calls[-1]["name"] == "scout.search.run"
    assert fake.list_recent_traces_calls[-1]["limit"] == 5


def test_list_recent_traces_name_prefix_truncates_to_limit(monkeypatch):
    # Prefix matches 5 traces; caller asks for limit=2; only 2 returned.
    _traces_app(
        monkeypatch,
        traces=[_trace(tid=str(i), name=f"preenrich.stage{i}") for i in range(5)],
    )
    with TestClient(server_mod.create_app()) as c:
        r = _call_list_recent_traces(c, name_prefix="preenrich.", limit=2)
    parsed = __import__("json").loads(r.json()["result"]["content"][0]["text"])
    assert parsed["count"] == 2


def test_list_recent_traces_degrades_on_upstream_4xx(monkeypatch):
    _traces_app(
        monkeypatch,
        traces_response=DegradedResponse("upstream_4xx", detail="HTTP 400"),
    )
    with TestClient(server_mod.create_app()) as c:
        r = _call_list_recent_traces(c, window_minutes=60)
    import json as _json
    parsed = _json.loads(r.json()["result"]["content"][0]["text"])
    assert parsed["degraded"] is True
    assert parsed["reason"] == "upstream_4xx"
    assert parsed["project"] == "scout-prod"
    assert parsed["window_minutes"] == 60


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
