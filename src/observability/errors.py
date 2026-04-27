"""Best-effort exception → Langfuse error observation emitter.

This is the bridge between Python exceptions and the read-only MCP server in
:mod:`src.observability.langfuse_mcp`. ``record_error`` takes the same
defensive shape as ``SearchTracingSession`` in :mod:`src.pipeline.tracing` —
it never raises, never blocks, and degrades cleanly when Langfuse is
unreachable or unconfigured.

Project routing
---------------

Two Langfuse projects are supported:

- ``scout-prod`` (default; uses ``LANGFUSE_PUBLIC_KEY`` / ``LANGFUSE_SECRET_KEY``
  per the existing :func:`src.pipeline.tracing._langfuse_config` contract).
- ``scout-dev`` (selected when ``SCOUT_LANGFUSE_DEV=true`` or
  ``SCOUT_LANGFUSE_PROJECT=scout-dev``; uses ``LANGFUSE_DEV_PUBLIC_KEY``
  / ``LANGFUSE_DEV_SECRET_KEY``).

Missing dev keys do not raise — the emitter logs a warning once and degrades
to disabled. Missing prod keys behave the same way (matching the existing
tracing emitters).
"""

from __future__ import annotations

import hashlib
import logging
import os
import traceback
from typing import Any, Literal, Optional

from src.observability.env import (
    current_cli,
    current_env,
    current_git_sha,
    current_host,
    repo_root,
)
from src.pipeline.tracing import (
    _langfuse_config,
    _sanitize_langfuse_payload,
)

try:  # pragma: no cover - optional dependency, mirrors src.pipeline.tracing
    from langfuse import Langfuse
except ImportError:  # pragma: no cover
    Langfuse = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

PipelineName = Literal["preenrich", "cv_assembly", "runner", "scout", "ad_hoc"]
Severity = Literal["WARN", "ERROR", "FATAL"]

_FRAME_DEPTH_LIMIT = 8
_LANGFUSE_LEVEL_BY_SEVERITY = {
    "WARN": "WARNING",
    "ERROR": "ERROR",
    "FATAL": "ERROR",  # Langfuse has no FATAL; carried as severity metadata
}


def record_error(
    *,
    session_id: str,
    trace_id: Optional[str],
    pipeline: PipelineName,
    stage: str,
    exc: BaseException,
    metadata: Optional[dict[str, Any]] = None,
    severity: Severity = "ERROR",
) -> None:
    """Emit one Langfuse ``event`` for an exception.

    Best-effort: any failure to construct the client, sanitize the payload, or
    flush to Langfuse is logged at ``WARNING`` and swallowed. Callers MUST be
    able to assume this function returns without raising for any input.

    The emitted event's ``name`` is ``error.<pipeline>.<stage>`` and its level
    is set so the MCP server's ``error_summary`` / ``list_recent_errors`` rules
    (§9.2 of the iteration plan) pick it up.
    """
    try:
        config = _resolve_langfuse_config()
        if config is None:
            return
        if Langfuse is None:
            return

        payload = _build_payload(
            exc=exc,
            pipeline=pipeline,
            stage=stage,
            severity=severity,
            metadata=metadata,
        )

        client = Langfuse(
            host=config["host"],
            public_key=config["public_key"],
            secret_key=config["secret_key"],
        )

        event_name = f"error.{pipeline}.{stage}"
        level = _LANGFUSE_LEVEL_BY_SEVERITY[severity]

        # Resolve / synthesise trace_id so update_trace can attach session_id.
        # Reuses the same pattern as src/pipeline/tracing.py: trace_id is
        # required by every observation in Langfuse SDK 4.x; if the caller
        # didn't supply one, derive a deterministic id from session_id so
        # repeated record_error calls in the same session group together.
        effective_trace_id = trace_id
        if not effective_trace_id:
            try:
                effective_trace_id = client.create_trace_id(seed=session_id)
            except Exception:  # pragma: no cover - defensive
                effective_trace_id = None

        # Emit as a short-lived span with level set at construction time.
        # We deliberately avoid as_type="event" here: in SDK 4.x events are
        # immutable after creation, so trace metadata (incl. session_id)
        # cannot be attached afterwards. A span lets us update_trace().
        try:
            obs = client.start_observation(  # type: ignore[attr-defined]
                trace_context={"trace_id": effective_trace_id} if effective_trace_id else None,
                name=event_name,
                as_type="span",
                input=payload,
                metadata=payload,
                level=level,
                status_message=type(exc).__name__,
            )
            if hasattr(obs, "update_trace"):
                try:
                    obs.update_trace(
                        name=event_name,
                        session_id=session_id,
                        input=payload,
                        metadata=payload,
                    )
                except Exception:  # pragma: no cover - defensive
                    pass
            if hasattr(obs, "end"):
                try:
                    obs.end()
                except Exception:  # pragma: no cover - defensive
                    pass
        except Exception as inner:  # pragma: no cover - defensive
            logger.warning("record_error emit (span) failed: %s", inner)

        try:
            client.flush()
        except Exception:  # pragma: no cover - defensive
            pass
    except Exception as inner:  # pragma: no cover - belt and braces
        logger.warning(
            "record_error swallowed exception while emitting %s.%s: %s",
            pipeline,
            stage,
            inner,
        )


def fingerprint(exc: BaseException) -> str:
    """Compute the SHA-1 fingerprint used to bucket repeated occurrences.

    Per the iteration-4.4 plan §5.2 (review-amended): hashes
    ``class | repo_relative_posix_path | top_frame_func``. ``lineno`` is
    deliberately excluded so harmless refactors don't fork the bucket.
    Path is normalised to POSIX-relative-to-repo-root so Windows and Linux
    runs of the same bug fingerprint identically.
    """
    frame = _top_frame(exc)
    file_part = "<unknown>"
    func_part = "<unknown>"
    if frame is not None:
        file_part = _normalise_frame_path(frame.filename)
        func_part = frame.name or "<unknown>"
    raw = f"{type(exc).__name__}|{file_part}|{func_part}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _resolve_langfuse_config() -> Optional[dict[str, str]]:
    """Pick the right project's credentials based on env."""
    if _project_is_dev():
        host = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL")
        pk = os.getenv("LANGFUSE_DEV_PUBLIC_KEY")
        sk = os.getenv("LANGFUSE_DEV_SECRET_KEY")
        if not (host and pk and sk):
            logger.debug("Langfuse dev project not configured; record_error disabled")
            return None
        return {"host": host, "public_key": pk, "secret_key": sk}
    return _langfuse_config()


def _project_is_dev() -> bool:
    if (os.getenv("SCOUT_LANGFUSE_DEV") or "").lower() == "true":
        return True
    return (os.getenv("SCOUT_LANGFUSE_PROJECT") or "").strip() == "scout-dev"


def _build_payload(
    *,
    exc: BaseException,
    pipeline: str,
    stage: str,
    severity: str,
    metadata: Optional[dict[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error_class": type(exc).__name__,
        "message": _short_message(exc),
        "fingerprint": fingerprint(exc),
        "frames": _bounded_frames(exc),
        "pipeline": pipeline,
        "stage": stage,
        "severity": severity,
        "env": current_env(),
        "cli": current_cli(),
        "host": current_host(),
        "git_sha": current_git_sha(),
    }
    if metadata:
        # ``_sanitize_langfuse_payload`` redacts prompt-shaped keys unless
        # ``LANGFUSE_CAPTURE_FULL_PROMPTS=true``.
        payload["metadata"] = _sanitize_langfuse_payload(metadata)
    return payload


def _short_message(exc: BaseException, limit: int = 500) -> str:
    msg = str(exc) or type(exc).__name__
    if len(msg) <= limit:
        return msg
    return msg[: limit - 3] + "..."


def _bounded_frames(exc: BaseException) -> list[dict[str, Any]]:
    tb = exc.__traceback__
    if tb is None:
        return []
    summary = traceback.extract_tb(tb, limit=_FRAME_DEPTH_LIMIT)
    out: list[dict[str, Any]] = []
    for frame in summary:
        out.append(
            {
                "file": _normalise_frame_path(frame.filename),
                "func": frame.name,
                "lineno": frame.lineno,
                "line": frame.line,
            }
        )
    return out


def _top_frame(exc: BaseException):
    tb = exc.__traceback__
    if tb is None:
        return None
    frames = traceback.extract_tb(tb, limit=_FRAME_DEPTH_LIMIT)
    return frames[-1] if frames else None


def _normalise_frame_path(path: str) -> str:
    """POSIX-relative-to-repo-root, falling back to absolute POSIX path.

    Always returns forward-slashes so a Windows traceback fingerprints
    identically to the same bug captured on Linux CI.
    """
    from pathlib import Path

    if not path:
        return "<unknown>"
    try:
        absolute = Path(path).resolve()
    except (OSError, ValueError):
        return path.replace("\\", "/")
    root = repo_root()
    if root is not None:
        try:
            return absolute.relative_to(root).as_posix().replace("\\", "/")
        except ValueError:
            pass
    return absolute.as_posix().replace("\\", "/")


__all__ = [
    "PipelineName",
    "Severity",
    "record_error",
    "fingerprint",
]
