"""Bearer-token middleware for the MCP HTTP transport.

Supports the multi-token rotation contract from iteration-4.4 §8.1:
``LANGFUSE_MCP_TOKENS`` may carry a comma-separated list of accepted tokens
during the rotation overlap window. ``LANGFUSE_MCP_TOKEN`` (singular) is
honoured for back-compat as a single-token alias.

This module deliberately keeps zero hard dependency on Starlette / FastAPI /
FastMCP — the actual middleware integration lives in ``server.py`` and just
calls :func:`is_authorized`. This keeps the auth logic unit-testable without
spinning up a web server.
"""

from __future__ import annotations

import hmac
import os
from typing import Iterable


def accepted_tokens() -> tuple[str, ...]:
    """Return the set of currently accepted bearer tokens.

    Reads ``LANGFUSE_MCP_TOKENS`` (preferred, comma-separated) then falls back
    to the single-token alias ``LANGFUSE_MCP_TOKEN``. Whitespace is stripped;
    empty entries are dropped.
    """
    raw = os.getenv("LANGFUSE_MCP_TOKENS")
    if raw:
        return tuple(t for t in (s.strip() for s in raw.split(",")) if t)
    single = (os.getenv("LANGFUSE_MCP_TOKEN") or "").strip()
    return (single,) if single else ()


def extract_bearer(authorization_header: str | None) -> str | None:
    """Return the token from an ``Authorization: Bearer <token>`` header.

    Returns ``None`` if the header is missing or malformed. Preserves the
    original token string verbatim — comparison is constant-time in
    :func:`is_authorized`.
    """
    if not authorization_header:
        return None
    parts = authorization_header.split(None, 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def is_authorized(
    authorization_header: str | None,
    *,
    accepted: Iterable[str] | None = None,
) -> bool:
    """Validate a request against the current accepted-tokens set.

    Comparison is constant-time per token via :func:`hmac.compare_digest` to
    blunt timing attacks. ``accepted`` is provided for tests; production
    callers omit it and let the function read env at request time.
    """
    presented = extract_bearer(authorization_header)
    if not presented:
        return False
    candidates = tuple(accepted) if accepted is not None else accepted_tokens()
    if not candidates:
        return False
    return any(hmac.compare_digest(presented, accepted_token) for accepted_token in candidates)


__all__ = ["accepted_tokens", "extract_bearer", "is_authorized"]
