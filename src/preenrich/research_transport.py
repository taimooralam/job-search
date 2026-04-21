"""Codex-only structured transport for Iteration 4.1.3 live research."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
import os
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from src.common.codex_cli import _extract_json_from_stdout, _run_monitored_codex_subprocess
from src.common.json_utils import parse_llm_json
from src.preenrich.types import StepConfig

T = TypeVar("T")


def _optional_timeout_seconds(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except Exception:
        return None
    if value <= 0:
        return None
    return value


DEFAULT_RESEARCH_TIMEOUT_SECONDS = _optional_timeout_seconds("PREENRICH_RESEARCH_TRANSPORT_TIMEOUT_SECONDS")


@dataclass
class ResearchTransportResult:
    success: bool
    payload: Any = None
    error: str | None = None
    attempts: list[dict[str, Any]] | None = None
    provider_used: str | None = None
    model_used: str | None = None
    transport_used: str | None = None
    duration_ms: int | None = None


class CodexResearchTransport:
    """Small stage-native wrapper for Codex structured research calls."""

    def __init__(self, config: StepConfig) -> None:
        self.provider = (config.provider or "codex").strip().lower()
        self.model = config.primary_model or config.model or "gpt-5.4-mini"
        self.transport = (config.transport or "none").strip().lower()
        self.timeout_seconds = DEFAULT_RESEARCH_TIMEOUT_SECONDS

    def is_live_configured(self) -> bool:
        return self.provider == "codex" and self.transport.startswith("codex")

    def invoke_json(
        self,
        *,
        prompt: str,
        job_id: str,
        validator: Callable[[dict[str, Any]], T] | None = None,
    ) -> ResearchTransportResult:
        started = time.monotonic()
        if not self.is_live_configured():
            return ResearchTransportResult(
                success=False,
                error=f"unsupported codex research transport: provider={self.provider} transport={self.transport}",
                attempts=[],
                provider_used=self.provider,
                model_used=self.model,
                transport_used=self.transport,
                duration_ms=0,
            )

        command = [
            "codex",
            "exec",
            "--model",
            self.model,
            "--full-auto",
            "--skip-git-repo-check",
            prompt,
        ]
        invoked_at = datetime.utcnow().isoformat()
        try:
            proc = _run_monitored_codex_subprocess(
                cmd=command,
                timeout=self.timeout_seconds,
                job_id=job_id,
                logger=logging.getLogger(__name__),
            )
        except FileNotFoundError:
            duration_ms = int((time.monotonic() - started) * 1000)
            return ResearchTransportResult(
                success=False,
                error="codex binary not found",
                attempts=[{
                    "provider": "codex",
                    "model": self.model,
                    "transport": self.transport,
                    "outcome": "error_missing_binary",
                    "error": "codex binary not found",
                    "duration_ms": duration_ms,
                    "invoked_at": invoked_at,
                }],
                provider_used="codex",
                model_used=self.model,
                transport_used=self.transport,
                duration_ms=duration_ms,
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        attempts = [{
            "provider": "codex",
            "model": self.model,
            "transport": self.transport,
            "outcome": "success" if proc.returncode == 0 else ("error_timeout" if proc.timed_out else "error_subprocess"),
            "error": ("codex research transport timed out" if proc.timed_out else proc.stderr.strip() or None),
            "duration_ms": duration_ms,
            "invoked_at": invoked_at,
        }]
        if proc.returncode != 0:
            return ResearchTransportResult(
                success=False,
                error=(
                    "codex research transport timed out"
                    if proc.timed_out
                    else proc.stderr.strip() or proc.stdout.strip() or f"codex exec exited with code {proc.returncode}"
                ),
                attempts=attempts,
                provider_used="codex",
                model_used=self.model,
                transport_used=self.transport,
                duration_ms=duration_ms,
            )

        json_str = _extract_json_from_stdout(proc.stdout or "")
        if not json_str:
            attempts[0]["outcome"] = "error_json"
            attempts[0]["error"] = "No JSON found in codex research output"
            return ResearchTransportResult(
                success=False,
                error="No JSON found in codex research output",
                attempts=attempts,
                provider_used="codex",
                model_used=self.model,
                transport_used=self.transport,
                duration_ms=duration_ms,
            )

        payload = parse_llm_json(json_str)
        try:
            if validator is not None:
                payload = validator(payload)
            elif isinstance(payload, BaseModel):
                payload = payload.model_dump()
        except ValidationError as exc:
            attempts[0]["outcome"] = "error_schema"
            attempts[0]["error"] = str(exc)
            return ResearchTransportResult(
                success=False,
                error=f"schema validation failed: {exc}",
                attempts=attempts,
                provider_used="codex",
                model_used=self.model,
                transport_used=self.transport,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            attempts[0]["outcome"] = "error_exception"
            attempts[0]["error"] = str(exc)
            return ResearchTransportResult(
                success=False,
                error=str(exc),
                attempts=attempts,
                provider_used="codex",
                model_used=self.model,
                transport_used=self.transport,
                duration_ms=duration_ms,
            )

        if isinstance(payload, BaseModel):
            payload = payload.model_dump()

        return ResearchTransportResult(
            success=True,
            payload=payload,
            attempts=attempts,
            provider_used="codex",
            model_used=self.model,
            transport_used=self.transport,
            duration_ms=duration_ms,
        )
