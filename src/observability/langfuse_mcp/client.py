"""Async wrapper around the Langfuse Public REST API.

Scope: just the read endpoints the MCP tools need. Write endpoints
(``/api/public/scores``, dataset CRUD, etc.) are out of scope per
iteration-4.4 §3.2.

Public API reference: https://api.reference.langfuse.com/

Two ``LangfuseClient`` instances normally exist per server: one bound to
``scout-prod`` keys, one bound to ``scout-dev`` (when configured). The dev
client is optional — calls against an unconfigured project return
``DegradedResponse(reason="project_unconfigured")`` rather than raising,
matching the §14 failure-mode contract.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

import httpx

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DegradedResponse:
    """Returned by every client method when the upstream call cannot complete.

    Mirrors the shape the §14 failure modes specify so MCP tools can pass it
    straight through to the caller without wrapping. ``reason`` is a stable
    enum-like string the tool layer keys off; ``detail`` is human-readable.
    """

    reason: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"degraded": True, "reason": self.reason, "detail": self.detail}


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


class LangfuseClient:
    """Per-project async REST wrapper.

    Caller responsibility: pass an already-authenticated ``httpx.AsyncClient``
    or let the constructor build one. Either way, the client is safe to share
    across many concurrent requests — ``httpx.AsyncClient`` is connection-pooled
    and thread-safe within an event loop.
    """

    DEFAULT_TIMEOUT_SEC = 10.0
    MAX_RETRIES = 3

    def __init__(
        self,
        *,
        host: str,
        public_key: str,
        secret_key: str,
        project_name: str,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.host = host.rstrip("/")
        self.project_name = project_name
        self._public_key = public_key
        self._secret_key = secret_key
        self._timeout = timeout or self.DEFAULT_TIMEOUT_SEC
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.host,
            timeout=self._timeout,
            auth=httpx.BasicAuth(public_key, secret_key),
            headers={"User-Agent": "langfuse-mcp/1"},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------- #
    # Public surface — one async method per MCP tool that needs upstream data.
    # ------------------------------------------------------------------- #

    async def health(self) -> dict[str, Any] | DegradedResponse:
        """Hit the unauthenticated `/api/public/health` endpoint.

        Used by the MCP server's `/healthz` check to confirm in-cluster
        reachability. Does NOT use basic auth — fewer false positives when
        the credentials are rotated mid-flight.
        """
        url = f"{self.host}/api/public/health"
        try:
            async with httpx.AsyncClient(timeout=3.0) as anon:
                r = await anon.get(url)
            return {
                "status_code": r.status_code,
                "body_preview": (r.text or "")[:200],
            }
        except httpx.HTTPError as exc:
            return DegradedResponse(
                reason="langfuse_unreachable",
                detail=f"{type(exc).__name__}: {exc}",
            )

    async def list_observations(
        self,
        *,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        level: Optional[str] = None,
        name: Optional[str] = None,
        type_: Optional[str] = None,
        limit: int = 50,
        page: int = 1,
        trace_id: Optional[str] = None,
    ) -> list[dict[str, Any]] | DegradedResponse:
        """Paginated `GET /api/public/observations`.

        Returns the raw observation dicts from Langfuse. Callers post-process
        through :mod:`.aggregations`.
        """
        params: dict[str, Any] = {
            "limit": limit,
            "page": page,
        }
        if from_timestamp:
            params["fromStartTime"] = _iso(from_timestamp)
        if to_timestamp:
            params["toStartTime"] = _iso(to_timestamp)
        if level:
            params["level"] = level
        if name:
            params["name"] = name
        if type_:
            params["type"] = type_
        if trace_id:
            params["traceId"] = trace_id

        result = await self._get_with_retry("/api/public/observations", params=params)
        if isinstance(result, DegradedResponse):
            return result
        data = result.get("data") or []
        if not isinstance(data, list):
            return DegradedResponse(
                reason="schema_mismatch",
                detail=f"observations: expected list under 'data', got {type(data).__name__}",
            )
        return data

    async def get_trace(self, trace_id: str) -> dict[str, Any] | DegradedResponse:
        return await self._get_with_retry(f"/api/public/traces/{trace_id}")

    async def list_sessions(
        self,
        *,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        limit: int = 50,
        page: int = 1,
    ) -> list[dict[str, Any]] | DegradedResponse:
        params: dict[str, Any] = {"limit": limit, "page": page}
        if from_timestamp:
            params["fromTimestamp"] = _iso(from_timestamp)
        if to_timestamp:
            params["toTimestamp"] = _iso(to_timestamp)
        result = await self._get_with_retry("/api/public/sessions", params=params)
        if isinstance(result, DegradedResponse):
            return result
        data = result.get("data") or []
        if not isinstance(data, list):
            return DegradedResponse(reason="schema_mismatch", detail="sessions: missing 'data' list")
        return data

    async def get_session(self, session_id: str) -> dict[str, Any] | DegradedResponse:
        return await self._get_with_retry(f"/api/public/sessions/{session_id}")

    async def list_recent_errors(
        self,
        *,
        window_minutes: int,
        limit: int = 50,
    ) -> list[dict[str, Any]] | DegradedResponse:
        """Convenience: errors emitted in the last N minutes.

        Filters server-side by `level=ERROR`; the §9.2 broader rules
        (name prefix, error_class in payload, trace-level ERROR) are applied
        client-side in :mod:`.aggregations.is_error_observation`. To catch
        rule-2 emissions that didn't set `level=ERROR`, callers union with
        a name-prefix scan — handled by the `list_recent_errors` tool.
        """
        if window_minutes <= 0 or window_minutes > 24 * 60:
            raise ValueError("window_minutes must be in (0, 1440]")
        now = datetime.now(timezone.utc)
        return await self.list_observations(
            from_timestamp=now - timedelta(minutes=window_minutes),
            to_timestamp=now,
            level="ERROR",
            limit=limit,
        )

    # ------------------------------------------------------------------- #
    # Internal — single retry wrapper used by every endpoint.
    # ------------------------------------------------------------------- #

    async def _get_with_retry(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | DegradedResponse:
        attempt = 0
        last_exc: Exception | None = None
        while attempt < self.MAX_RETRIES:
            attempt += 1
            try:
                r = await self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                last_exc = exc
                await asyncio.sleep(_backoff(attempt))
                continue

            if r.status_code == 429:
                # Adaptive backoff with jitter, max 60s.
                await asyncio.sleep(_backoff(attempt))
                continue
            if r.status_code >= 500:
                await asyncio.sleep(_backoff(attempt))
                continue
            if r.status_code == 401 or r.status_code == 403:
                return DegradedResponse(
                    reason="upstream_auth_failed",
                    detail=f"HTTP {r.status_code} from {path}",
                )
            if r.status_code >= 400:
                return DegradedResponse(
                    reason="upstream_4xx",
                    detail=f"HTTP {r.status_code} from {path}: {r.text[:200]}",
                )
            try:
                return r.json()
            except ValueError:
                return DegradedResponse(
                    reason="schema_mismatch",
                    detail=f"non-JSON response from {path}",
                )

        return DegradedResponse(
            reason="rate_limited" if last_exc is None else "langfuse_unreachable",
            detail=str(last_exc) if last_exc else f"exhausted {self.MAX_RETRIES} retries on {path}",
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.isoformat()


def _backoff(attempt: int) -> float:
    """Exponential-with-jitter; capped at 60 s per §7.3 / §14."""
    base = min(60.0, 0.5 * (2 ** (attempt - 1)))
    return base + random.uniform(0.0, base * 0.25)


__all__ = ["LangfuseClient", "DegradedResponse"]
