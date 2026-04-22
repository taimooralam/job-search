"""
StageBase Protocol and shared LLM helpers for pre-enrichment stages.

Each stage must implement:
    name: str               — unique stage identifier matching DAG names
    dependencies: list[str] — stage names this stage depends on
    run(ctx) -> StageResult — pure function, no Mongo I/O

Shared helper:
    _call_llm_with_fallback() — Codex-primary with automatic Claude fallback
                                (Phase 2b, plan §4 rule 1 + review-3 item #4)
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError

from src.common.codex_cli import CodexCLI
from src.preenrich.types import StageContext, StageResult

logger = logging.getLogger(__name__)


def _call_llm_with_fallback(
    *,
    primary_provider: str,
    primary_model: str,
    fallback_provider: str,
    fallback_model: str,
    prompt: str,
    job_id: str,
    schema: Optional[Type[BaseModel]] = None,
    claude_invoker: Callable[..., Any],
    codex_cwd: str | None = None,
    reasoning_effort: str | None = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Invoke the primary provider (Codex) and optionally fall back on failure.

    Primary transport: CodexCLI.invoke() from src/common/codex_cli.py.
    Fallback transport: claude_invoker callable (caller-supplied Claude path).

    Failure conditions that trigger fallback (plan §4 rule 1 + review-3 item #4):
      - CodexResult.success == False  → outcome="error_subprocess"
      - Pydantic ValidationError on schema validation → outcome="error_schema"
      - Any unexpected exception during Codex call → outcome="error_exception"

    If fallback also fails, re-raises — the dispatcher's outer retry loop across
    worker ticks handles further reliability (plan §4 rule 1 contract).

    Args:
        primary_provider: Provider label for provenance (e.g. "codex").
        primary_model:    Model identifier for Codex (e.g. "gpt-5.4").
        fallback_provider: Provider label for fallback (e.g. "claude").
        fallback_model:   Model identifier for Claude fallback.
        prompt:           Full prompt text.
        job_id:           Tracking identifier for logging.
        schema:           Optional Pydantic BaseModel subclass for output validation.
        claude_invoker:   Callable(prompt, model, job_id) -> Dict[str, Any].
                          Called when Codex fails.

    Returns:
        Tuple of (parsed_output_dict, attempts_list).

        attempts_list entries:
          {
            "provider": str,
            "model": str,
            "outcome": "success" | "error_subprocess" | "error_schema" | "error_exception",
            "error": str | None,
            "duration_ms": int,
            "input_tokens": int | None,
            "output_tokens": int | None,
          }

    Raises:
        RuntimeError: If both primary and fallback fail.
    """
    attempts: List[Dict[str, Any]] = []

    # ── Primary (Codex) ────────────────────────────────────────────────────────
    codex_outcome: Optional[str] = None
    codex_error: Optional[str] = None
    codex_result_dict: Optional[Dict[str, Any]] = None

    t0 = time.monotonic()
    try:
        cli = CodexCLI(model=primary_model, cwd=codex_cwd, reasoning_effort=reasoning_effort)
        codex_result = cli.invoke(prompt, job_id=job_id, validate_json=True)
        primary_duration_ms = int((time.monotonic() - t0) * 1000)

        if not codex_result.success:
            codex_outcome = "error_subprocess"
            codex_error = codex_result.error or "codex returned success=False"
            logger.warning(
                "_call_llm_with_fallback: Codex failed for job %s: %s",
                job_id, codex_error,
            )
        else:
            raw = codex_result.result or {}
            if schema is not None:
                try:
                    validated = schema.model_validate(raw)
                    codex_result_dict = validated.model_dump()
                    codex_outcome = "success"
                except ValidationError as ve:
                    codex_outcome = "error_schema"
                    codex_error = f"Schema validation failed: {ve}"
                    logger.warning(
                        "_call_llm_with_fallback: Codex schema error for job %s: %s",
                        job_id, codex_error,
                    )
            else:
                codex_result_dict = raw
                codex_outcome = "success"

        attempts.append({
            "provider": primary_provider,
            "model": primary_model,
            "outcome": codex_outcome,
            "error": codex_error,
            "duration_ms": primary_duration_ms,
            "input_tokens": codex_result.input_tokens,
            "output_tokens": codex_result.output_tokens,
        })

    except Exception as exc:
        primary_duration_ms = int((time.monotonic() - t0) * 1000)
        codex_outcome = "error_exception"
        codex_error = str(exc)
        logger.warning(
            "_call_llm_with_fallback: Codex exception for job %s: %s",
            job_id, codex_error,
        )
        attempts.append({
            "provider": primary_provider,
            "model": primary_model,
            "outcome": "error_exception",
            "error": codex_error,
            "duration_ms": primary_duration_ms,
            "input_tokens": None,
            "output_tokens": None,
        })

    if codex_outcome == "success" and codex_result_dict is not None:
        return codex_result_dict, attempts

    if fallback_provider in {"", "none"} or not fallback_model:
        raise RuntimeError(
            f"Primary provider ({primary_provider}/{primary_model}) failed for job {job_id} "
            f"and no fallback is configured. Primary error: {codex_error}"
        )

    # ── Fallback ───────────────────────────────────────────────────────────────
    logger.info(
        "_call_llm_with_fallback: falling back to %s/%s for job %s (primary outcome: %s)",
        fallback_provider, fallback_model, job_id, codex_outcome,
    )
    t1 = time.monotonic()
    try:
        fallback_output = claude_invoker(
            prompt=prompt,
            model=fallback_model,
            job_id=job_id,
        )
        fallback_duration_ms = int((time.monotonic() - t1) * 1000)

        if schema is not None and isinstance(fallback_output, dict):
            validated = schema.model_validate(fallback_output)
            fallback_output = validated.model_dump()

        attempts.append({
            "provider": fallback_provider,
            "model": fallback_model,
            "outcome": "success",
            "error": None,
            "duration_ms": fallback_duration_ms,
            "input_tokens": None,
            "output_tokens": None,
        })
        return fallback_output, attempts

    except Exception as fb_exc:
        fallback_duration_ms = int((time.monotonic() - t1) * 1000)
        attempts.append({
            "provider": fallback_provider,
            "model": fallback_model,
            "outcome": "error_exception",
            "error": str(fb_exc),
            "duration_ms": fallback_duration_ms,
            "input_tokens": None,
            "output_tokens": None,
        })
        raise RuntimeError(
            f"Both primary ({primary_provider}/{primary_model}) and fallback "
            f"({fallback_provider}/{fallback_model}) failed for job {job_id}. "
            f"Primary error: {codex_error}. Fallback error: {fb_exc}"
        ) from fb_exc


try:
    from typing import Protocol, runtime_checkable
except ImportError:
    from typing_extensions import Protocol, runtime_checkable  # type: ignore


@runtime_checkable
class StageBase(Protocol):
    """
    Protocol that all pre-enrichment stages must satisfy.

    Stages are pure functions from context to result. All persistence
    is handled by the dispatcher (§3 package layout).
    """

    name: str
    """Unique stage identifier. Must match a key in STAGE_ORDER (dag.py)."""

    dependencies: List[str]
    """Names of stages this stage depends on. Used for DAG validation."""

    def run(self, ctx: StageContext) -> StageResult:
        """
        Execute the stage and return a result.

        Args:
            ctx: Immutable stage context with job_doc, checksums, config

        Returns:
            StageResult with output patch and provenance metadata

        Raises:
            Any exception causes the dispatcher to treat this as a failure
            and increment retry_count.
        """
        ...
