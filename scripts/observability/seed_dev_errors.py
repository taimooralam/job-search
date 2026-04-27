"""Smoke emitter for the langfuse-mcp end-to-end loop.

Emits one synthetic error to either ``scout-prod`` or ``scout-dev`` so the
operator (or CI) can verify ``record_error`` → Langfuse → MCP query round-trip
within seconds, without waiting for an organic failure.

Examples::

    SCOUT_LANGFUSE_DEV=true python -m scripts.observability.seed_dev_errors
    SCOUT_LANGFUSE_DEV=true python -m scripts.observability.seed_dev_errors \\
        --message "smoke from $(hostname)" --pipeline scout
    SCOUT_LANGFUSE_PROJECT=scout-prod python -m scripts.observability.seed_dev_errors \\
        --severity FATAL --stage rotation_smoke

Exits 0 always — best-effort, mirrors :func:`record_error` semantics.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import get_args

from src.observability.errors import PipelineName, Severity, record_error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seed_dev_errors",
        description="Emit one synthetic error observation to Langfuse via record_error().",
    )
    parser.add_argument(
        "--pipeline",
        choices=list(get_args(PipelineName)),
        default="ad_hoc",
    )
    parser.add_argument("--stage", default="seed_smoke")
    parser.add_argument("--message", default="synthetic error from seed_dev_errors")
    parser.add_argument(
        "--severity",
        choices=list(get_args(Severity)),
        default="ERROR",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Langfuse session_id (default: synthesises 'seed:<uuid>')",
    )
    parser.add_argument(
        "--trace-id",
        default=None,
        help="Optional Langfuse trace_id to attach the event to",
    )
    args = parser.parse_args(argv)

    session_id = args.session_id or f"seed:{uuid.uuid4()}"

    try:
        raise SyntheticSmokeError(args.message)
    except SyntheticSmokeError as exc:
        record_error(
            session_id=session_id,
            trace_id=args.trace_id,
            pipeline=args.pipeline,
            stage=args.stage,
            exc=exc,
            severity=args.severity,
            metadata={"source": "seed_dev_errors", "session_id_synth": session_id},
        )

    print(session_id)
    return 0


class SyntheticSmokeError(RuntimeError):
    """Marker class so the fingerprint is stable across runs of this script."""


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
