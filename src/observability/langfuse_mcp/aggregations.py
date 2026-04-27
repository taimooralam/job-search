"""Pure aggregation helpers used by the MCP tool layer.

All functions here are deterministic, side-effect-free, and exhaustively
unit-testable. The MCP tools call them on the output of :mod:`.client` to
build digests, top-N tables, and time-bucketed rollups. Keep them pure so the
unit tests in ``tests/observability/test_aggregations.py`` can drive them
without spinning up Langfuse.

Schema assumed for an "observation" in this module
--------------------------------------------------

A dict with at least these keys (matching the shape that
:func:`src.observability.errors.record_error` writes and that the Langfuse
REST API returns):

- ``id``: str
- ``trace_id``: str
- ``session_id``: str | None
- ``name``: str
- ``level``: str (``"ERROR" | "WARNING" | "DEFAULT"``)
- ``start_time``: ISO-8601 str
- ``input``/``metadata``/``output``: dicts that may carry
  ``error_class``, ``message``, ``fingerprint``, ``pipeline``, ``stage``
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any, Optional


def is_error_observation(obs: Mapping[str, Any]) -> bool:
    """Iteration-4.4 §9.2 — what counts as an error at the MCP layer."""
    if (obs.get("level") or "").upper() == "ERROR":
        return True
    name = obs.get("name") or ""
    if isinstance(name, str) and name.startswith("error."):
        return True
    payload = _merged_payload(obs)
    if "error_class" in payload:
        return True
    return False


def fingerprint_observation(obs: Mapping[str, Any]) -> str:
    """Return the fingerprint stored on the observation, or compute one.

    Stored fingerprints (set by :func:`src.observability.errors.record_error`)
    win — they used full traceback context. When absent (e.g. legacy emitters
    that only set ``error_class``), we compute a coarser fallback so grouping
    still collapses repeats.
    """
    payload = _merged_payload(obs)
    stored = payload.get("fingerprint")
    if isinstance(stored, str) and stored:
        return stored
    parts = [
        str(payload.get("error_class") or "<unknown>"),
        str(payload.get("pipeline") or "<unknown>"),
        str(payload.get("stage") or obs.get("name") or "<unknown>"),
    ]
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def group_by_fingerprint(
    observations: Iterable[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    """Group error observations by their fingerprint.

    Non-error observations are silently skipped — callers don't need to
    pre-filter.
    """
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for obs in observations:
        if not is_error_observation(obs):
            continue
        grouped[fingerprint_observation(obs)].append(obs)
    return dict(grouped)


def top_n_errors(
    observations: Iterable[Mapping[str, Any]],
    *,
    n: int = 10,
) -> list[dict[str, Any]]:
    """Return the top-N error fingerprints sorted by count desc, then last_seen desc.

    Each row matches the §7.1 ``error_summary`` shape:
    ``{fingerprint, error_class, message_preview, count, first_seen, last_seen,
    sample_trace_id, pipelines, stages}``.
    """
    if n <= 0:
        return []
    grouped = group_by_fingerprint(observations)
    rows: list[dict[str, Any]] = []
    for fp, members in grouped.items():
        members_sorted = sorted(members, key=lambda o: _ts(o) or datetime.min.replace(tzinfo=timezone.utc))
        first = members_sorted[0]
        last = members_sorted[-1]
        first_payload = _merged_payload(first)
        last_payload = _merged_payload(last)
        rows.append(
            {
                "fingerprint": fp,
                "error_class": first_payload.get("error_class") or "<unknown>",
                "message_preview": _preview(last_payload.get("message")),
                "count": len(members),
                "first_seen": _iso(first),
                "last_seen": _iso(last),
                "sample_trace_id": last.get("trace_id"),
                "pipelines": sorted({_str(_merged_payload(o).get("pipeline")) for o in members if _merged_payload(o).get("pipeline")}),
                "stages": sorted({_str(_merged_payload(o).get("stage")) for o in members if _merged_payload(o).get("stage")}),
            }
        )
    rows.sort(key=lambda r: (-r["count"], r["last_seen"] or ""), reverse=False)
    return rows[:n]


def time_bucketed_rollup(
    observations: Iterable[Mapping[str, Any]],
    *,
    bucket_minutes: int = 5,
) -> list[dict[str, Any]]:
    """Return a list of ``{bucket_start, count}`` for the supplied window.

    Empty buckets are not synthesised here — callers that need a dense series
    (e.g. for a sparkline) should fill on the fly.
    """
    if bucket_minutes <= 0:
        raise ValueError("bucket_minutes must be > 0")
    bucket_seconds = bucket_minutes * 60
    counts: dict[datetime, int] = defaultdict(int)
    for obs in observations:
        ts = _ts(obs)
        if ts is None:
            continue
        epoch = int(ts.timestamp())
        bucket_epoch = (epoch // bucket_seconds) * bucket_seconds
        bucket_start = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)
        counts[bucket_start] += 1
    return [
        {"bucket_start": k.isoformat(), "count": v}
        for k, v in sorted(counts.items())
    ]


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _merged_payload(obs: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten ``input``/``metadata``/``output`` so callers can look up keys
    without caring which slot Langfuse stored them in."""
    merged: dict[str, Any] = {}
    for key in ("input", "metadata", "output"):
        slot = obs.get(key)
        if isinstance(slot, Mapping):
            for k, v in slot.items():
                merged.setdefault(k, v)
    return merged


def _ts(obs: Mapping[str, Any]) -> Optional[datetime]:
    raw = obs.get("start_time") or obs.get("timestamp")
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            # Python's fromisoformat handles "2026-04-27T13:42:01+00:00" and
            # "2026-04-27T13:42:01Z" only since 3.11; normalise the trailing Z.
            normalized = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _iso(obs: Mapping[str, Any]) -> Optional[str]:
    ts = _ts(obs)
    return ts.isoformat() if ts else None


def _str(value: Any) -> str:
    return str(value) if value is not None else ""


def _preview(value: Any, limit: int = 200) -> str:
    if value is None:
        return ""
    s = str(value)
    return s if len(s) <= limit else s[: limit - 3] + "..."


def trace_summary(trace: Mapping[str, Any]) -> dict[str, Any]:
    """Project an upstream Langfuse trace dict into the MCP-facing summary shape.

    The Langfuse REST `/api/public/traces` response carries large `input` and
    `output` blobs. The MCP tool surface is read-mostly by humans-via-LLM, so
    we truncate to a 200-char preview and keep the rest of the metadata
    addressable without forcing every caller to parse a 30 kB blob.
    """
    return {
        "id": trace.get("id"),
        "name": trace.get("name"),
        "timestamp": trace.get("timestamp"),
        "session_id": trace.get("sessionId") or trace.get("session_id"),
        "user_id": trace.get("userId") or trace.get("user_id"),
        "tags": trace.get("tags") or [],
        "release": trace.get("release"),
        "version": trace.get("version"),
        "input_preview": _preview(trace.get("input")),
        "output_preview": _preview(trace.get("output")),
        "metadata": trace.get("metadata") or {},
    }


__all__ = [
    "is_error_observation",
    "fingerprint_observation",
    "group_by_fingerprint",
    "top_n_errors",
    "time_bucketed_rollup",
    "trace_summary",
]
