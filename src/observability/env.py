"""Environment introspection for observability emissions.

These helpers tag every Langfuse observation with deterministic, low-cardinality
metadata so the MCP server can filter cleanly. All helpers are pure functions
and never raise — failure modes return ``"unknown"`` so callers don't need
defensive wrappers.
"""

from __future__ import annotations

import os
import socket
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Literal

EnvName = Literal["prod", "dev", "staging", "unknown"]
CliName = Literal["claude", "codex", "none"]


def current_env() -> EnvName:
    """Return the deployment environment as tagged on Langfuse observations.

    Reads ``SCOUT_ENV``. Anything outside the known set normalises to
    ``"unknown"`` so the MCP server's env filter never silently drops rows.
    """
    raw = (os.getenv("SCOUT_ENV") or "").strip().lower()
    if raw in {"prod", "dev", "staging"}:
        return raw  # type: ignore[return-value]
    return "unknown"


def current_cli() -> CliName:
    """Return the CLI shell that initiated the current process, if any.

    Set by the SessionStart hook (Claude Code) or the proactive Codex skill.
    Defaults to ``"none"`` for non-interactive workers / cron jobs.
    """
    raw = (os.getenv("SCOUT_CLI") or "").strip().lower()
    if raw in {"claude", "codex"}:
        return raw  # type: ignore[return-value]
    return "none"


def current_host() -> str:
    """Best-effort hostname; ``"unknown"`` on failure."""
    try:
        return socket.gethostname() or "unknown"
    except OSError:
        return "unknown"


@lru_cache(maxsize=1)
def current_git_sha() -> str:
    """Short git SHA of the working tree.

    Cached for process lifetime — assumes the SHA does not change while a
    process is running, which is true for every emitter in this codebase.
    Falls back to ``$SCOUT_GIT_SHA`` (set by deploy scripts where ``git``
    is unavailable, e.g. inside the runner image), then ``"unknown"``.
    """
    explicit = os.getenv("SCOUT_GIT_SHA")
    if explicit:
        return explicit.strip()[:12]
    try:
        repo_root = _find_repo_root()
        if repo_root is None:
            return "unknown"
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


@lru_cache(maxsize=1)
def repo_root() -> Path | None:
    """Resolve the repository root (the directory containing ``.git``).

    Walks up from this file's location. Returned as ``Path`` (or ``None`` when
    not in a git checkout — e.g. inside a slim container). Used by the
    fingerprinter in :mod:`src.observability.errors` to render POSIX-relative
    paths so Windows and Linux runs of the same bug fingerprint identically.
    """
    return _find_repo_root()


def _find_repo_root(start: Path | None = None) -> Path | None:
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


__all__ = [
    "EnvName",
    "CliName",
    "current_env",
    "current_cli",
    "current_host",
    "current_git_sha",
    "repo_root",
]
