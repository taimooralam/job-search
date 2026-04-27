#!/usr/bin/env python3
"""Hook-friendly digest fetcher for the langfuse-mcp ``/digest`` endpoint.

This script exists so the ``Authorization: Bearer ...`` header is never put
on a command line — it lives in the process env (``LANGFUSE_MCP_TOKEN``) and
is constructed in-process. Used by:

- ``.claude/settings.local.json`` ``SessionStart`` hook
- the ``lf-recent``/``lf-job`` shell + PowerShell aliases
- the OpenClaw ``oc`` container's startup digest fetch

Zero non-stdlib dependencies on purpose — this runs inside hook contexts
where ``pip install`` is not assumed.

Usage::

    python infra/scripts/langfuse_digest.py [--window 120] [--top 5] \\
        [--env prod] [--project scout-prod] [--job <level2_job_id>] \\
        [--format markdown|json] [--wrap-system-reminder]

Env::

    LANGFUSE_MCP_TOKEN          required; bearer token (never on argv)
    LANGFUSE_MCP_URL            default ``https://langfuse-mcp.srv1112039.hstgr.cloud``
    LANGFUSE_MCP_TIMEOUT_SEC    default ``8``

Exits 0 on success (including degraded responses), 2 on auth failure, 3 on
network failure, 4 on bad arguments. The hook handler treats non-zero exits
as silent skip.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://langfuse-mcp.srv1112039.hstgr.cloud"
DEFAULT_TIMEOUT_SEC = 8.0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    token = os.getenv("LANGFUSE_MCP_TOKEN", "").strip()
    if not token:
        print("LANGFUSE_MCP_TOKEN not set; skipping digest", file=sys.stderr)
        return 2

    base_url = (os.getenv("LANGFUSE_MCP_URL") or DEFAULT_BASE_URL).rstrip("/")
    timeout = float(os.getenv("LANGFUSE_MCP_TIMEOUT_SEC") or DEFAULT_TIMEOUT_SEC)

    if args.job:
        path = f"/job/{urllib.parse.quote(args.job, safe='')}"
        query: dict[str, str] = {}
    else:
        path = "/digest"
        query = {
            "window": str(args.window),
            "top": str(args.top),
        }
        if args.env:
            query["env"] = args.env
        if args.project:
            query["project"] = args.project

    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    accept = "application/json" if args.format == "json" else "text/markdown"

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "User-Agent": "langfuse-digest/1 (+infra/scripts/langfuse_digest.py)",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            content_type = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            print("langfuse-mcp 401 (token rejected); skipping", file=sys.stderr)
            return 2
        print(f"langfuse-mcp HTTP {exc.code}: {exc.reason}", file=sys.stderr)
        return 3
    except urllib.error.URLError as exc:
        print(f"langfuse-mcp unreachable: {exc.reason}", file=sys.stderr)
        return 3
    except TimeoutError:
        print(f"langfuse-mcp timeout after {timeout}s", file=sys.stderr)
        return 3

    rendered = _render(body, content_type, args.format)

    if args.wrap_system_reminder and args.format == "markdown":
        rendered = (
            "<system-reminder>\n"
            "Recent failures from langfuse-mcp (auto-fetched by SessionStart hook):\n\n"
            f"{rendered.strip()}\n"
            "</system-reminder>"
        )

    print(rendered)
    return 0


def _render(body: str, content_type: str, requested: str) -> str:
    if requested == "json":
        # Validate JSON shape so the hook gets a clean error if the server
        # returned an HTML 5xx page or similar.
        try:
            parsed: Any = json.loads(body)
        except json.JSONDecodeError:
            return body
        return json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False)
    # Markdown / text: pass through whatever the server sent.
    return body


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="langfuse_digest",
        description=(
            "Fetch the langfuse-mcp /digest endpoint with the bearer token "
            "kept off the command line."
        ),
    )
    p.add_argument("--window", type=int, default=120, help="window in minutes (default 120)")
    p.add_argument("--top", type=int, default=5, help="top-N error fingerprints (default 5)")
    p.add_argument("--env", choices=("prod", "dev", "staging"), default=None)
    p.add_argument("--project", default=None, help="scout-prod or scout-dev")
    p.add_argument("--job", default=None, help="level2_job_id; switches to /job/{id} render")
    p.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
    )
    p.add_argument(
        "--wrap-system-reminder",
        action="store_true",
        help="wrap the markdown digest in <system-reminder> tags",
    )
    return p


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
