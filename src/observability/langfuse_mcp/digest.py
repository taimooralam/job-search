"""Render a top-N error digest as JSON or Markdown.

The `/digest` HTTP endpoint and the `langfuse://summary/today` MCP resource
both call into here. Pure async function so the renderer is testable without
spinning up the Starlette app.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.observability.langfuse_mcp.aggregations import top_n_errors
from src.observability.langfuse_mcp.client import DegradedResponse, LangfuseClient


async def render_digest(
    *,
    client: LangfuseClient,
    window_minutes: int,
    top: int,
    env: Optional[str] = None,
) -> dict[str, Any]:
    """Build the digest payload.

    Returns a dict with both ``markdown`` and ``json`` keys so the HTTP layer
    can content-negotiate without re-running the upstream query.
    """
    raw = await client.list_recent_errors(window_minutes=window_minutes, limit=200)
    if isinstance(raw, DegradedResponse):
        return _degraded_payload(
            window_minutes=window_minutes,
            project=client.project_name,
            env=env,
            degraded=raw,
        )

    if env:
        raw = [obs for obs in raw if _env_of(obs) == env]

    rows = top_n_errors(raw, n=top)

    return {
        "ok": True,
        "project": client.project_name,
        "env": env,
        "window_minutes": window_minutes,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "errors": rows,
        "markdown": _markdown(
            project=client.project_name,
            env=env,
            window_minutes=window_minutes,
            rows=rows,
        ),
    }


# --------------------------------------------------------------------------- #
# Markdown rendering — kept simple so SessionStart hook output stays terse.
# --------------------------------------------------------------------------- #


def _markdown(
    *,
    project: str,
    env: Optional[str],
    window_minutes: int,
    rows: list[dict[str, Any]],
) -> str:
    header = f"## langfuse-mcp digest — {project}"
    if env:
        header += f" / env={env}"
    header += f" / last {window_minutes} min"

    if not rows:
        return f"{header}\n\n_No errors in window. Quiet, healthy._\n"

    lines = [header, "", "| count | error | pipeline · stage | last_seen | trace |", "|---|---|---|---|---|"]
    for row in rows:
        pipelines = ",".join(row.get("pipelines") or []) or "-"
        stages = ",".join(row.get("stages") or []) or "-"
        last_seen = (row.get("last_seen") or "").replace("T", " ").split("+")[0]
        trace = row.get("sample_trace_id") or "-"
        msg = (row.get("message_preview") or "").replace("|", "\\|")
        lines.append(
            f"| {row['count']} | `{row['error_class']}` — {msg} | "
            f"{pipelines} · {stages} | {last_seen} | `{trace}` |"
        )
    return "\n".join(lines) + "\n"


def _degraded_payload(
    *,
    window_minutes: int,
    project: str,
    env: Optional[str],
    degraded: DegradedResponse,
) -> dict[str, Any]:
    md = (
        f"## langfuse-mcp digest — {project}"
        + (f" / env={env}" if env else "")
        + f" / last {window_minutes} min\n\n"
        f"_Degraded: `{degraded.reason}` — {degraded.detail or 'no detail'}_\n"
    )
    return {
        "ok": False,
        "project": project,
        "env": env,
        "window_minutes": window_minutes,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "errors": [],
        "markdown": md,
        **degraded.to_dict(),
    }


def _env_of(obs: dict[str, Any]) -> str | None:
    """Pull `env` tag from observation metadata (set by record_error)."""
    for key in ("input", "metadata"):
        slot = obs.get(key)
        if isinstance(slot, dict) and "env" in slot:
            return slot.get("env")
    return None


__all__ = ["render_digest"]
