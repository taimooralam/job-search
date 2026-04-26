"""Codex-only structured transport for Iteration 4.1.3 live research."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from src.common.codex_cli import _extract_json_from_stdout, _run_monitored_codex_subprocess
from src.common.json_utils import parse_llm_json
from src.preenrich.types import StepConfig

logger = logging.getLogger(__name__)

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
        self.model = config.primary_model or config.model or "gpt-5.2"
        self.transport = (config.transport or "none").strip().lower()
        self.timeout_seconds = DEFAULT_RESEARCH_TIMEOUT_SECONDS
        self.cwd = config.codex_workdir
        self.reasoning_effort = (config.reasoning_effort or "").strip() or None

    def is_live_configured(self) -> bool:
        return self.provider == "codex" and self.transport.startswith("codex")

    def invoke_json(
        self,
        *,
        prompt: str,
        job_id: str,
        validator: Callable[[dict[str, Any]], T] | None = None,
        tracer: Any = None,
        stage_name: str | None = None,
        substage: str | None = None,
        trace_metadata: dict[str, Any] | None = None,
    ) -> ResearchTransportResult:
        started = time.monotonic()
        span = None
        span_metadata = {
            "provider": self.provider,
            "model": self.model,
            "transport": self.transport,
            "stage_name": stage_name,
            "substage": substage,
            "prompt_length": len(prompt or ""),
            "prompt": prompt,
            "reasoning_effort": self.reasoning_effort,
            "timeout_seconds": self.timeout_seconds,
            "job_id": job_id,
        }
        if trace_metadata:
            span_metadata.update(trace_metadata)
        if tracer is not None and stage_name and substage and getattr(tracer, "trace", None) is not None:
            try:
                span = tracer.start_substage_span(stage_name, f"research.{substage}", span_metadata)
            except Exception:  # pragma: no cover - defensive, tracing must never break stages
                span = None

        def _end_span(outcome: str, *, result: "ResearchTransportResult", schema_valid: bool | None = None) -> None:
            if span is None or tracer is None:
                return
            try:
                tracer.end_span(
                    span,
                    output={
                        "outcome": outcome,
                        "success": result.success,
                        "duration_ms": result.duration_ms,
                        "error_class": outcome if not result.success else None,
                        "error_message_preview": (result.error or "")[:240] if result.error else None,
                        "schema_valid": schema_valid,
                        "provider": result.provider_used,
                        "model": result.model_used,
                        "transport": result.transport_used,
                    },
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("research transport span finalization failed: %s", exc)

        if not self.is_live_configured():
            result = ResearchTransportResult(
                success=False,
                error=f"unsupported codex research transport: provider={self.provider} transport={self.transport}",
                attempts=[],
                provider_used=self.provider,
                model_used=self.model,
                transport_used=self.transport,
                duration_ms=0,
            )
            _end_span("unsupported_transport", result=result, schema_valid=None)
            return result

        command = [
            "codex",
            "exec",
            "--model",
            self.model,
            "--full-auto",
        ]
        if self.reasoning_effort:
            command.extend(["-c", f'model_reasoning_effort="{self.reasoning_effort}"'])
        command.extend([
            "--skip-git-repo-check",
            prompt,
        ])
        invoked_at = datetime.utcnow().isoformat()
        try:
            proc = _run_monitored_codex_subprocess(
                cmd=command,
                timeout=self.timeout_seconds,
                job_id=job_id,
                logger=logging.getLogger(__name__),
                cwd=self.cwd,
            )
        except FileNotFoundError:
            duration_ms = int((time.monotonic() - started) * 1000)
            result = ResearchTransportResult(
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
            _end_span("error_missing_binary", result=result, schema_valid=None)
            return result

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
            outcome = "error_timeout" if proc.timed_out else "error_subprocess"
            result = ResearchTransportResult(
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
            _end_span(outcome, result=result, schema_valid=None)
            return result

        json_str = _extract_json_from_stdout(proc.stdout or "")
        if not json_str:
            attempts[0]["outcome"] = "error_json"
            attempts[0]["error"] = "No JSON found in codex research output"
            result = ResearchTransportResult(
                success=False,
                error="No JSON found in codex research output",
                attempts=attempts,
                provider_used="codex",
                model_used=self.model,
                transport_used=self.transport,
                duration_ms=duration_ms,
            )
            _end_span("error_no_json", result=result, schema_valid=None)
            return result

        payload = parse_llm_json(json_str)
        try:
            if validator is not None:
                payload = validator(payload)
            elif isinstance(payload, BaseModel):
                payload = payload.model_dump()
        except ValidationError as exc:
            attempts[0]["outcome"] = "error_schema"
            attempts[0]["error"] = str(exc)
            result = ResearchTransportResult(
                success=False,
                payload=payload,
                error=f"schema validation failed: {exc}",
                attempts=attempts,
                provider_used="codex",
                model_used=self.model,
                transport_used=self.transport,
                duration_ms=duration_ms,
            )
            _end_span("error_schema", result=result, schema_valid=False)
            return result
        except Exception as exc:
            attempts[0]["outcome"] = "error_exception"
            attempts[0]["error"] = str(exc)
            result = ResearchTransportResult(
                success=False,
                error=str(exc),
                attempts=attempts,
                provider_used="codex",
                model_used=self.model,
                transport_used=self.transport,
                duration_ms=duration_ms,
            )
            _end_span("error_exception", result=result, schema_valid=False)
            return result

        if isinstance(payload, BaseModel):
            payload = payload.model_dump()

        result = ResearchTransportResult(
            success=True,
            payload=payload,
            attempts=attempts,
            provider_used="codex",
            model_used=self.model,
            transport_used=self.transport,
            duration_ms=duration_ms,
        )
        _end_span("success", result=result, schema_valid=True)
        return result
