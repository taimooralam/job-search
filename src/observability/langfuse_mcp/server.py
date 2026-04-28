"""HTTP entry point for langfuse-mcp.

Routes:

- ``GET  /healthz``                — unauthenticated health probe (Docker uses it)
- ``GET  /digest``                 — authenticated digest for SessionStart hook
- ``GET  /job/{level2_job_id}``    — authenticated convenience render
- ``GET  /sse/errors/live``        — authenticated SSE push-on-error subscription
- ``GET  /sse/session/{sid}/tail`` — authenticated SSE per-session tail
- ``POST /mcp``                    — authenticated MCP JSON-RPC transport (tools)

The server intentionally avoids a hard FastMCP dependency — it implements the
small subset of the MCP HTTP transport it needs (initialize, tools/list,
tools/call, resources/list, resources/read) directly. Trade: a bit more
boilerplate; benefit: no version coupling to a fast-moving SDK.

Run with::

    python -m src.observability.langfuse_mcp.server

Configuration is read from process env. The Docker image's CMD calls this
entry point.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse

from src.observability.langfuse_mcp.auth import is_authorized
from src.observability.langfuse_mcp.client import DegradedResponse, LangfuseClient
from src.observability.langfuse_mcp.digest import render_digest

logger = logging.getLogger("langfuse_mcp.server")

# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise per-project Langfuse clients at startup, close on shutdown."""
    app.state.clients = _build_clients()
    app.state.startup_ts = _now_iso()
    logger.info("langfuse-mcp ready; configured projects: %s", sorted(app.state.clients.keys()))
    try:
        yield
    finally:
        for client in app.state.clients.values():
            await client.aclose()


def _build_clients() -> dict[str, LangfuseClient]:
    host = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL")
    if not host:
        raise RuntimeError("LANGFUSE_HOST is required")

    clients: dict[str, LangfuseClient] = {}

    pk_prod = os.getenv("LANGFUSE_PROD_PUBLIC_KEY") or os.getenv("LANGFUSE_PUBLIC_KEY")
    sk_prod = os.getenv("LANGFUSE_PROD_SECRET_KEY") or os.getenv("LANGFUSE_SECRET_KEY")
    if not (pk_prod and sk_prod):
        # Per §8.2: prod is load-bearing; refuse to start without it.
        raise RuntimeError("scout-prod credentials missing; refusing to start")
    clients["scout-prod"] = LangfuseClient(
        host=host, public_key=pk_prod, secret_key=sk_prod, project_name="scout-prod"
    )

    pk_dev = os.getenv("LANGFUSE_DEV_PUBLIC_KEY")
    sk_dev = os.getenv("LANGFUSE_DEV_SECRET_KEY")
    if pk_dev and sk_dev:
        clients["scout-dev"] = LangfuseClient(
            host=host, public_key=pk_dev, secret_key=sk_dev, project_name="scout-dev"
        )
    else:
        logger.warning("LANGFUSE_DEV_* not set; serving in prod_only degraded mode")

    return clients


# --------------------------------------------------------------------------- #
# App + middleware
# --------------------------------------------------------------------------- #


def create_app() -> FastAPI:
    app = FastAPI(
        title="langfuse-mcp",
        version="0.1.0",
        description="Read-only MCP server for the langfuse stack.",
        lifespan=lifespan,
    )
    _register_routes(app)
    _install_signal_handlers()
    return app


def _install_signal_handlers() -> None:
    """SIGHUP triggers token re-read (handled implicitly: ``accepted_tokens()``
    reads env on every request, so the operator can rewrite ``.env`` and the
    container picks it up after a restart). SIGTERM/SIGINT are handled by
    uvicorn directly."""

    def _on_sighup(signum: int, frame: Any) -> None:
        logger.info("SIGHUP received; tokens will be re-read on next request")

    if hasattr(signal, "SIGHUP"):  # not available on Windows
        signal.signal(signal.SIGHUP, _on_sighup)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


def _register_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        # Probe the prod project's Langfuse — that's the load-bearing path.
        prod = app.state.clients.get("scout-prod")
        upstream = await prod.health() if prod else DegradedResponse("prod_client_missing")
        if isinstance(upstream, DegradedResponse):
            body = {
                "ok": False,
                "langfuse_reachable": False,
                "dev_configured": "scout-dev" in app.state.clients,
                "started_at": app.state.startup_ts,
                **upstream.to_dict(),
            }
            return JSONResponse(body, status_code=200)
        body = {
            "ok": True,
            "langfuse_reachable": True,
            "dev_configured": "scout-dev" in app.state.clients,
            "started_at": app.state.startup_ts,
            "upstream_status": upstream.get("status_code"),
        }
        return JSONResponse(body)

    @app.get("/digest")
    async def digest(request: Request) -> Response:
        _require_auth(request)
        window = _bounded_int(request.query_params.get("window"), default=120, lo=1, hi=24 * 60)
        top = _bounded_int(request.query_params.get("top"), default=5, lo=1, hi=50)
        env = request.query_params.get("env")
        project = request.query_params.get("project") or "scout-prod"
        client = _client_for_app(app, project)
        if client is None:
            payload = DegradedResponse("project_unconfigured", detail=project).to_dict()
            payload["project"] = project
            return JSONResponse(payload, status_code=200)
        result = await render_digest(
            client=client,
            window_minutes=window,
            top=top,
            env=env,
        )
        accept = request.headers.get("accept", "")
        if "application/json" in accept and "text/markdown" not in accept:
            # JSON without the markdown blob (slimmer for tools that re-render).
            json_body = {k: v for k, v in result.items() if k != "markdown"}
            return JSONResponse(json_body)
        if "text/markdown" in accept or "*/*" in accept or not accept:
            return PlainTextResponse(result["markdown"], media_type="text/markdown; charset=utf-8")
        return JSONResponse(result)

    @app.get("/job/{level2_job_id}")
    async def job_render(level2_job_id: str, request: Request) -> Response:
        _require_auth(request)
        # Convenience: maps to canonical session_id `job:{level2_job_id}` per
        # 4.3.8 §9. Until 4.3.8 lands, the resolution is best-effort — we just
        # try the conventional id and fall back to a "session not found" message.
        project = request.query_params.get("project") or "scout-prod"
        client = _client_for_app(app, project)
        if client is None:
            return JSONResponse(
                DegradedResponse("project_unconfigured", detail=project).to_dict(),
                status_code=200,
            )
        sess = await client.get_session(f"job:{level2_job_id}")
        return JSONResponse(_unwrap(sess))

    @app.get("/sse/errors/live")
    async def errors_live(request: Request) -> StreamingResponse:
        _require_auth(request)
        env = request.query_params.get("env")
        project = request.query_params.get("project") or "scout-prod"
        client = _client_for_app(app, project)
        if client is None:
            raise HTTPException(status_code=404, detail=f"project unconfigured: {project}")
        return StreamingResponse(
            _errors_live_stream(client=client, env=env),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/sse/session/{session_id}/tail")
    async def session_tail(session_id: str, request: Request) -> StreamingResponse:
        _require_auth(request)
        project = request.query_params.get("project") or "scout-prod"
        client = _client_for_app(app, project)
        if client is None:
            raise HTTPException(status_code=404, detail=f"project unconfigured: {project}")
        return StreamingResponse(
            _session_tail_stream(client=client, session_id=session_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/sse/traces")
    async def traces_live(request: Request) -> StreamingResponse:
        """Live SSE of new traces matching a query.

        Query params:
        - ``name``        — exact upstream name filter
        - ``name_prefix`` — server-side prefix filter (over-fetch + filter)
        - ``session_id``  — pin to one session
        - ``user_id``     — filter by user
        - ``env``         — client-side metadata.env filter (prod/dev/staging)
        - ``project``     — scout-prod (default) | scout-dev

        Yields one ``event: trace`` per *new* trace seen since the connection
        opened (dedup by trace id). Polls every ``LANGFUSE_MCP_POLL_INTERVAL_SEC``
        (default 5s); the first poll seeds the dedup set with the existing
        last 50 traces in the window so callers don't get a backlog flood.
        """
        _require_auth(request)
        project = request.query_params.get("project") or "scout-prod"
        client = _client_for_app(app, project)
        if client is None:
            raise HTTPException(status_code=404, detail=f"project unconfigured: {project}")
        return StreamingResponse(
            _traces_live_stream(
                client=client,
                name=request.query_params.get("name"),
                name_prefix=request.query_params.get("name_prefix"),
                session_id=request.query_params.get("session_id"),
                user_id=request.query_params.get("user_id"),
                env=request.query_params.get("env"),
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/mcp")
    async def mcp_endpoint(request: Request) -> Response:
        """Minimal MCP JSON-RPC transport (Streamable HTTP, single-response mode).

        Implements only what the Claude Code / Codex CLI clients actually
        call: ``initialize``, ``tools/list``, ``tools/call``, ``resources/list``,
        ``resources/read``, plus the ``notifications/initialized`` notification.
        Anything else returns ``method_not_found``.

        Per the MCP Streamable HTTP spec, a request *without* an ``id`` is a
        notification: the server MUST return HTTP 202 with an empty body and
        MUST NOT send a JSON-RPC response. Returning a response payload to
        Codex's rmcp client otherwise tripped a JsonRpcMessage union
        deserialisation error and tore the transport down.
        """
        _require_auth(request)
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return _jsonrpc_error(None, code=-32700, message="parse error")

        if not isinstance(body, dict):
            return _jsonrpc_error(None, code=-32600, message="invalid request")

        method = body.get("method") or ""
        params = body.get("params") or {}
        is_notification = "id" not in body

        if is_notification:
            # Fire-and-forget. We currently don't need to act on
            # notifications/initialized but accept it (and any future
            # client→server notification) without erroring.
            return Response(status_code=202)

        rpc_id = body.get("id")
        try:
            result = await _dispatch_mcp(method, params, app=app)
        except _RpcError as exc:
            return _jsonrpc_error(rpc_id, code=exc.code, message=exc.message)
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})


# --------------------------------------------------------------------------- #
# MCP dispatch
# --------------------------------------------------------------------------- #


async def _dispatch_mcp(method: str, params: dict[str, Any], *, app: FastAPI) -> Any:
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "langfuse-mcp", "version": "0.1.0"},
        }
    if method == "tools/list":
        return {"tools": _TOOL_DESCRIPTORS}
    if method == "tools/call":
        name = params.get("name") or ""
        args = params.get("arguments") or {}
        return await _call_tool(name=name, args=args, app=app)
    if method == "resources/list":
        return {"resources": _RESOURCE_DESCRIPTORS}
    if method == "resources/read":
        uri = params.get("uri") or ""
        return await _read_resource(uri=uri, app=app)
    raise _RpcError(-32601, f"method not found: {method}")


# Tool descriptors — kept inline so the JSON-RPC path needs no extra plumbing.
_TOOL_DESCRIPTORS: list[dict[str, Any]] = [
    {
        "name": "langfuse.health",
        "description": "Check upstream Langfuse reachability + per-project configuration.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "langfuse.error_summary",
        "description": "Top-N error fingerprints in the window (default 60 min, top 10).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_minutes": {"type": "integer", "minimum": 1, "maximum": 1440, "default": 60},
                "top_n": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                "env": {"type": "string", "enum": ["prod", "dev", "staging"]},
                "project": {"type": "string", "enum": ["scout-prod", "scout-dev"], "default": "scout-prod"},
            },
        },
    },
    {
        "name": "langfuse.list_recent_errors",
        "description": "Raw recent error observations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_minutes": {"type": "integer", "minimum": 1, "maximum": 1440, "default": 60},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                "env": {"type": "string", "enum": ["prod", "dev", "staging"]},
                "project": {"type": "string", "enum": ["scout-prod", "scout-dev"], "default": "scout-prod"},
            },
        },
    },
    {
        "name": "langfuse.get_trace",
        "description": "One trace + its observations.",
        "inputSchema": {
            "type": "object",
            "required": ["trace_id"],
            "properties": {
                "trace_id": {"type": "string"},
                "project": {"type": "string", "enum": ["scout-prod", "scout-dev"], "default": "scout-prod"},
            },
        },
    },
    {
        "name": "langfuse.list_recent_traces",
        "description": "Recent traces in the window (default 60 min, limit 50). Optional name/session_id/user_id/tags narrow further.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "window_minutes": {"type": "integer", "minimum": 1, "maximum": 1440, "default": 60},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                "name": {"type": "string", "description": "Exact upstream name filter (e.g. 'scout.search.run')."},
                "name_prefix": {"type": "string", "description": "Server-side prefix filter (e.g. 'preenrich.'). Applied after fetching up to 100 traces from upstream; ignored if `name` is also set."},
                "session_id": {"type": "string"},
                "user_id": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "env": {"type": "string", "enum": ["prod", "dev", "staging"]},
                "project": {"type": "string", "enum": ["scout-prod", "scout-dev"], "default": "scout-prod"},
            },
        },
    },
    {
        "name": "langfuse.get_session",
        "description": "One session timeline.",
        "inputSchema": {
            "type": "object",
            "required": ["session_id"],
            "properties": {
                "session_id": {"type": "string"},
                "project": {"type": "string", "enum": ["scout-prod", "scout-dev"], "default": "scout-prod"},
            },
        },
    },
]


_RESOURCE_DESCRIPTORS: list[dict[str, Any]] = [
    {
        "uri": "langfuse://errors/last-1h",
        "name": "Errors in the last hour (Markdown)",
        "mimeType": "text/markdown",
    },
    {
        "uri": "langfuse://summary/today",
        "name": "Today's digest (Markdown)",
        "mimeType": "text/markdown",
    },
]


async def _call_tool(*, name: str, args: dict[str, Any], app: FastAPI) -> dict[str, Any]:
    project = args.get("project") or "scout-prod"
    client = _client_for_app(app, project)
    if client is None:
        return _tool_result_text(json.dumps(
            DegradedResponse("project_unconfigured", detail=project).to_dict() | {"project": project}
        ))

    if name == "langfuse.health":
        prod = app.state.clients.get("scout-prod")
        upstream = await prod.health() if prod else DegradedResponse("prod_client_missing")
        body: dict[str, Any]
        if isinstance(upstream, DegradedResponse):
            body = {"ok": False, "langfuse_reachable": False, **upstream.to_dict()}
        else:
            body = {
                "ok": True,
                "langfuse_reachable": True,
                "dev_configured": "scout-dev" in app.state.clients,
                "upstream_status": upstream.get("status_code"),
            }
        return _tool_result_text(json.dumps(body))

    if name == "langfuse.error_summary":
        window = int(args.get("window_minutes") or 60)
        top = int(args.get("top_n") or 10)
        env = args.get("env")
        result = await render_digest(client=client, window_minutes=window, top=top, env=env)
        return _tool_result_text(json.dumps({k: v for k, v in result.items() if k != "markdown"}))

    if name == "langfuse.list_recent_errors":
        window = int(args.get("window_minutes") or 60)
        limit = int(args.get("limit") or 50)
        result = await client.list_recent_errors(window_minutes=window, limit=limit)
        if isinstance(result, DegradedResponse):
            return _tool_result_text(json.dumps(result.to_dict()))
        # Trim to keep payload bounded.
        return _tool_result_text(json.dumps(result[:limit]))

    if name == "langfuse.get_trace":
        trace_id = args.get("trace_id")
        if not trace_id:
            raise _RpcError(-32602, "trace_id is required")
        result = await client.get_trace(trace_id)
        return _tool_result_text(json.dumps(_unwrap(result)))

    if name == "langfuse.list_recent_traces":
        from src.observability.langfuse_mcp.aggregations import trace_summary

        window = max(1, min(int(args.get("window_minutes") or 60), 1440))
        limit = max(1, min(int(args.get("limit") or 50), 100))
        env_filter = args.get("env")
        # Upstream `name` is exact-match only. `name_prefix` is server-side:
        # we over-fetch (up to 100, the upstream cap) and prefix-filter, then
        # truncate to `limit`. Ignored if `name` is also set (exact wins).
        exact_name = args.get("name")
        prefix = args.get("name_prefix")
        if prefix and not exact_name:
            fetch_limit = 100
        else:
            prefix = None
            fetch_limit = limit
        try:
            traces = await client.list_recent_traces(
                window_minutes=window,
                limit=fetch_limit,
                name=exact_name,
                session_id=args.get("session_id"),
                user_id=args.get("user_id"),
                tags=args.get("tags"),
            )
        except ValueError as exc:
            return _tool_result_text(json.dumps(
                DegradedResponse("invalid_argument", detail=str(exc)).to_dict()
            ))
        if isinstance(traces, DegradedResponse):
            payload = traces.to_dict() | {"project": project, "window_minutes": window}
            return _tool_result_text(json.dumps(payload))

        # Optional client-side env filter on metadata.env (matches the
        # convention used by record_error and the SSE filter helper).
        if env_filter:
            traces = [
                t for t in traces
                if isinstance(t, dict)
                and isinstance(t.get("metadata"), dict)
                and t["metadata"].get("env") == env_filter
            ]

        if prefix:
            traces = [
                t for t in traces
                if isinstance(t, dict) and isinstance(t.get("name"), str)
                and t["name"].startswith(prefix)
            ]

        # Truncate to caller-requested limit (over-fetch was internal).
        traces = traces[:limit]

        summaries = [trace_summary(t) for t in traces if isinstance(t, dict)]
        return _tool_result_text(json.dumps({
            "ok": True,
            "project": project,
            "window_minutes": window,
            "count": len(summaries),
            "traces": summaries,
        }))

    if name == "langfuse.get_session":
        session_id = args.get("session_id")
        if not session_id:
            raise _RpcError(-32602, "session_id is required")
        result = await client.get_session(session_id)
        return _tool_result_text(json.dumps(_unwrap(result)))

    raise _RpcError(-32601, f"tool not found: {name}")


async def _read_resource(*, uri: str, app: FastAPI) -> dict[str, Any]:
    client = app.state.clients.get("scout-prod")
    if client is None:
        raise _RpcError(-32603, "scout-prod not configured")

    if uri == "langfuse://errors/last-1h":
        result = await render_digest(client=client, window_minutes=60, top=10, env=None)
        return {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": result["markdown"]}]}
    if uri == "langfuse://summary/today":
        result = await render_digest(client=client, window_minutes=24 * 60, top=10, env=None)
        return {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": result["markdown"]}]}
    raise _RpcError(-32601, f"resource not found: {uri}")


# --------------------------------------------------------------------------- #
# SSE streams
# --------------------------------------------------------------------------- #


async def _errors_live_stream(*, client: LangfuseClient, env: str | None) -> AsyncIterator[bytes]:
    """Poll Langfuse every 5 s; yield SSE events for new error observations.

    Dedup is in-memory (per-stream): we track observation IDs we've already
    pushed during this connection. The §11 cooldown / fingerprint dedup is
    layered on top by the client subscription handler; here we just avoid
    re-emitting the same observation_id multiple times.
    """
    seen: set[str] = set()
    keepalive_every = 5  # poll iterations
    iteration = 0
    poll_interval = float(os.getenv("LANGFUSE_MCP_POLL_INTERVAL_SEC") or "5")
    while True:
        iteration += 1
        result = await client.list_recent_errors(window_minutes=10, limit=50)
        if not isinstance(result, DegradedResponse):
            for obs in result:
                obs_id = obs.get("id")
                if not obs_id or obs_id in seen:
                    continue
                if env and _env_of(obs) != env:
                    continue
                seen.add(obs_id)
                yield _sse_event("error", obs)
        if iteration % keepalive_every == 0:
            yield b": keepalive\n\n"
        await asyncio.sleep(poll_interval)


async def _traces_live_stream(
    *,
    client: LangfuseClient,
    name: Optional[str] = None,
    name_prefix: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    env: Optional[str] = None,
) -> AsyncIterator[bytes]:
    """Poll Langfuse every 5 s; yield SSE events for new traces matching the query.

    Dedup is per-stream via an in-memory set of trace ids. The first poll
    primes the dedup set so we don't re-emit historical rows that pre-date
    the connection — only events ingested *after* connect time stream out.
    """
    from src.observability.langfuse_mcp.aggregations import trace_summary

    seen: set[str] = set()
    keepalive_every = 5
    iteration = 0
    poll_interval = float(os.getenv("LANGFUSE_MCP_POLL_INTERVAL_SEC") or "5")
    primed = False

    # `name_prefix` is a server-side filter: the upstream supports exact `name`
    # only. When prefix is in play, over-fetch the upstream cap and filter
    # locally; otherwise fetch a small page.
    over_fetch = bool(name_prefix and not name)

    while True:
        iteration += 1
        try:
            traces = await client.list_recent_traces(
                window_minutes=10,
                limit=100 if over_fetch else 50,
                name=name,
                session_id=session_id,
                user_id=user_id,
            )
        except ValueError:
            traces = []
        if not isinstance(traces, DegradedResponse):
            for tr in traces:
                if not isinstance(tr, dict):
                    continue
                tid = tr.get("id")
                if not tid:
                    continue
                if name_prefix and not str(tr.get("name") or "").startswith(name_prefix):
                    continue
                if env:
                    md = tr.get("metadata") or {}
                    if not (isinstance(md, dict) and md.get("env") == env):
                        continue
                if tid in seen:
                    continue
                seen.add(tid)
                if primed:
                    # Only yield events *after* the priming pass so callers
                    # don't get an immediate backlog dump on connect.
                    yield _sse_event("trace", trace_summary(tr))
            primed = True
        if iteration % keepalive_every == 0:
            yield b": keepalive\n\n"
        await asyncio.sleep(poll_interval)


async def _session_tail_stream(*, client: LangfuseClient, session_id: str) -> AsyncIterator[bytes]:
    """Poll Langfuse for new observations on one session_id; yield SSE per delta."""
    seen: set[str] = set()
    keepalive_every = 5
    iteration = 0
    poll_interval = float(os.getenv("LANGFUSE_MCP_POLL_INTERVAL_SEC") or "5")
    while True:
        iteration += 1
        # Pull recent observations and filter client-side. (Langfuse's REST API
        # supports filtering by trace; session-level requires the session GET +
        # pagination; we use the cheap path for v1.)
        result = await client.list_observations(limit=50)
        if not isinstance(result, DegradedResponse):
            for obs in result:
                if obs.get("session_id") != session_id:
                    continue
                obs_id = obs.get("id")
                if not obs_id or obs_id in seen:
                    continue
                seen.add(obs_id)
                yield _sse_event("observation", obs)
        if iteration % keepalive_every == 0:
            yield b": keepalive\n\n"
        await asyncio.sleep(poll_interval)


def _sse_event(event: str, payload: dict[str, Any]) -> bytes:
    encoded = json.dumps(payload, default=str)
    return f"event: {event}\ndata: {encoded}\n\n".encode("utf-8")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _jsonrpc_error(rpc_id: Any, *, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}})


def _tool_result_text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _require_auth(request: Request) -> None:
    if not is_authorized(request.headers.get("authorization")):
        raise HTTPException(status_code=401, detail="invalid bearer token")


def _bounded_int(raw: Optional[str], *, default: int, lo: int, hi: int) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def _client_for_app(app: FastAPI, project: str) -> LangfuseClient | None:
    return app.state.clients.get(project)


def _unwrap(result: Any) -> Any:
    if isinstance(result, DegradedResponse):
        return result.to_dict()
    return result


def _env_of(obs: dict[str, Any]) -> str | None:
    for key in ("input", "metadata"):
        slot = obs.get(key)
        if isinstance(slot, dict) and "env" in slot:
            return slot.get("env")
    return None


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Module entry point: ``python -m src.observability.langfuse_mcp.server``
# --------------------------------------------------------------------------- #


def main() -> None:
    import uvicorn

    bind = os.getenv("MCP_BIND", "0.0.0.0:4000")
    if ":" in bind:
        host, port_s = bind.rsplit(":", 1)
        port = int(port_s)
    else:
        host, port = "0.0.0.0", int(bind)
    logging.basicConfig(
        level=os.getenv("LANGFUSE_MCP_LOG_LEVEL", "INFO"),
        format='{"ts":"%(asctime)s","lvl":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    )
    uvicorn.run(create_app(), host=host, port=port, log_level="info", access_log=True)


if __name__ == "__main__":  # pragma: no cover
    main()
