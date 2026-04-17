"""
Pre-enrichment stage dispatcher.

Iterates stages in DAG order, skips already-completed stages at the
current checksum, runs each stage, and atomically persists stage metadata
+ legacy top-level fields together in a single Mongo update (§2.3).

Key guarantees:
- Only writes when lease_owner matches (compare-and-set)
- Idempotency guard via attempt_token ($ne check)
- Prerequisite enforcement per dag.py (§3.1)
- Heartbeat per stage completion
- On failure: increments retry_count; at >=3 marks failed_terminal
- On all completed: sets lifecycle="ready" + ready_at

Public API:
    single_stage(db, ctx, stage, *, force=False) -> StageResult
    run_sequence(db, ctx, stages) -> dict
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.preenrich.dag import STAGE_ORDER, _DEPENDENCIES
from src.preenrich.types import (
    StageContext,
    StageResult,
    StageStatus,
    attempt_token as make_attempt_token,
)
from src.preenrich.lease import heartbeat

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class PrerequisiteNotMet(Exception):
    """
    Raised when a stage's DAG prerequisites are not completed at the
    current checksum and force=False.

    Attributes:
        stage: The stage that cannot run.
        missing: List of prerequisite stage names that are not completed.
    """

    def __init__(self, stage: str, missing: List[str]) -> None:
        self.stage = stage
        self.missing = missing
        super().__init__(
            f"Stage '{stage}' prerequisites not met: {missing}"
        )


def _now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _check_prerequisites(
    ctx: StageContext,
    stage_name: str,
    *,
    force: bool = False,
) -> None:
    """
    Validate that all DAG dependencies for stage_name are completed at the
    current jd_checksum.

    If force=True, logs a Telegram warning instead of raising. If force=False
    and any prerequisite is not completed, raises PrerequisiteNotMet.

    Args:
        ctx: Stage context with job_doc and jd_checksum
        stage_name: Name of the stage to check prerequisites for
        force: If True, bypass enforcement but log a warning

    Raises:
        PrerequisiteNotMet: When force=False and prerequisites are unmet
    """
    deps = _DEPENDENCIES.get(stage_name, [])
    if not deps:
        return  # No dependencies, always runnable

    pre = ctx.job_doc.get("pre_enrichment") or {}
    stages = pre.get("stages") or {}

    missing = []
    for dep in deps:
        dep_doc = stages.get(dep) or {}
        if (
            dep_doc.get("status") != StageStatus.COMPLETED
            or dep_doc.get("jd_checksum_at_completion") != ctx.jd_checksum
        ):
            missing.append(dep)

    if not missing:
        return

    if force:
        try:
            from src.common.telegram import send_telegram
            send_telegram(
                f"<b>Preenrich FORCE override</b>: stage <code>{stage_name}</code> "
                f"running with unmet prerequisites: {missing}"
            )
        except Exception:
            pass
        logger.warning(
            "FORCE override: stage '%s' running with unmet prerequisites: %s",
            stage_name,
            missing,
        )
    else:
        raise PrerequisiteNotMet(stage_name, missing)


def _persist_stage_success(
    db: Any,
    ctx: StageContext,
    worker_id: str,
    stage_name: str,
    stage_doc: Dict[str, Any],
    result: StageResult,
    token: str,
    started_at: datetime,
    now: datetime,
    duration_ms: int,
) -> bool:
    """
    Atomically persist a successful stage result.

    Writes stage metadata + legacy top-level output fields in one update_one.
    Uses attempt_token idempotency guard so a retry of an already-written
    stage is a safe no-op.

    If ctx.shadow_mode is True, writes to shadow namespace only:
        pre_enrichment.stages.<stage>.shadow_output
        pre_enrichment.shadow_legacy_fields.<field>
    Not the live legacy top-level fields.

    Returns:
        True if the update matched (i.e. write succeeded), False otherwise.
    """
    job_id = ctx.job_doc["_id"]
    retry_count = stage_doc.get("retry_count", 0)

    stage_meta: Dict[str, Any] = {
        "status": StageStatus.COMPLETED,
        "provider": result.provider_used,
        "model": result.model_used,
        "prompt_version": result.prompt_version or ctx.config.prompt_version,
        "jd_checksum_at_completion": ctx.jd_checksum,
        "input_snapshot_id": ctx.input_snapshot_id,
        "attempt_token": token,
        "started_at": started_at,
        "completed_at": now,
        "duration_ms": result.duration_ms or duration_ms,
        "retry_count": retry_count,
        "last_error_at": None,
        "failure_context": None,
        "tokens_input": result.tokens_input,
        "tokens_output": result.tokens_output,
        "cost_usd": result.cost_usd,
        "skip_reason": result.skip_reason,
        "cache_source_job_id": result.cache_source_job_id,
        "provenance": {
            "forced": getattr(result, "_forced", False),
        },
    }

    if ctx.shadow_mode:
        # Shadow mode: write to shadow namespace, never touch live fields
        stage_meta["shadow_output"] = result.output
        set_doc: Dict[str, Any] = {
            f"pre_enrichment.stages.{stage_name}": stage_meta,
            "lease_heartbeat_at": now,
        }
        # Mirror output fields into shadow_legacy_fields
        for field_key, field_val in result.output.items():
            set_doc[f"pre_enrichment.shadow_legacy_fields.{field_key}"] = field_val
    else:
        # Live mode: write stage metadata + legacy top-level output fields
        set_doc = {
            f"pre_enrichment.stages.{stage_name}": stage_meta,
            "lease_heartbeat_at": now,
        }
        set_doc.update(result.output)

    matched = db["level-2"].update_one(
        {
            "_id": job_id,
            "lease_owner": worker_id,
            # Idempotency: skip if this exact attempt was already written
            f"pre_enrichment.stages.{stage_name}.attempt_token": {
                "$ne": token
            },
        },
        {"$set": set_doc},
    )

    return matched.matched_count > 0


def _persist_stage_failure(
    db: Any,
    ctx: StageContext,
    worker_id: str,
    stage_name: str,
    stage_doc: Dict[str, Any],
    error_msg: str,
    now: datetime,
) -> None:
    """Persist a stage failure with retry counting."""
    job_id = ctx.job_doc["_id"]
    retry_count = stage_doc.get("retry_count", 0) + 1
    new_status = (
        StageStatus.FAILED_TERMINAL
        if retry_count >= MAX_RETRIES
        else StageStatus.FAILED
    )

    set_doc: Dict[str, Any] = {
        f"pre_enrichment.stages.{stage_name}.status": new_status,
        f"pre_enrichment.stages.{stage_name}.retry_count": retry_count,
        f"pre_enrichment.stages.{stage_name}.last_error_at": now,
        f"pre_enrichment.stages.{stage_name}.failure_context": error_msg,
    }

    db["level-2"].update_one(
        {"_id": job_id, "lease_owner": worker_id},
        {"$set": set_doc},
    )
    logger.warning(
        "Stage %s for job %s failed (retry_count=%d, status=%s)",
        stage_name,
        job_id,
        retry_count,
        new_status,
    )


def single_stage(
    db: Any,
    ctx: StageContext,
    stage: Any,
    worker_id: str,
    *,
    force: bool = False,
) -> StageResult:
    """
    Run exactly one stage, validate prerequisites, persist atomically.

    This is the sole write path for stage results. All callers — worker,
    run_sequence, and the operator CLI — must go through this function.

    Args:
        db: PyMongo database handle
        ctx: StageContext with job_doc, checksums, attempt_number, config
        stage: StageBase instance with .name and .run(ctx) -> StageResult
        worker_id: This worker's identity string (for lease guard)
        force: If True, bypass prerequisite enforcement (logs Telegram warning
               and marks provenance.forced=True in the stage doc).

    Returns:
        StageResult from the stage

    Raises:
        PrerequisiteNotMet: When force=False and DAG prerequisites are unmet
        RuntimeError: If the Mongo update matches 0 docs (lease lost or
                      idempotent replay collision)
    """
    stage_name = stage.name
    job_id = ctx.job_doc["_id"]

    pre = ctx.job_doc.get("pre_enrichment") or {}
    existing_stages = pre.get("stages") or {}
    stage_doc = existing_stages.get(stage_name) or {}

    # Skip if already completed at the current checksum
    if (
        stage_doc.get("status") == StageStatus.COMPLETED
        and stage_doc.get("jd_checksum_at_completion") == ctx.jd_checksum
        and not force
    ):
        logger.debug(
            "Skipping completed stage %s for job %s (checksum matches)",
            stage_name,
            job_id,
        )
        # Return a synthetic skipped StageResult
        return StageResult(
            output={},
            skip_reason="already_completed_at_current_checksum",
        )

    # Prerequisite enforcement
    _check_prerequisites(ctx, stage_name, force=force)

    # Build attempt token (excludes provider/model per §2.3)
    token = make_attempt_token(
        job_id=str(job_id),
        stage=stage_name,
        jd_checksum=ctx.jd_checksum,
        prompt_version=ctx.config.prompt_version,
        attempt_number=ctx.attempt_number,
    )

    now = _now_utc()
    started_at = now

    # Mark in_progress (do NOT write attempt_token here — only on completion)
    # Writing token at in_progress would cause the $ne idempotency guard to
    # block the completion write on the same attempt.
    _update_stage_status(
        db,
        job_id,
        worker_id,
        stage_name,
        status=StageStatus.IN_PROGRESS,
        extra={"started_at": now},
    )

    result: Optional[StageResult] = None
    error_msg: Optional[str] = None

    try:
        result = stage.run(ctx)
    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            "Stage %s failed for job %s: %s", stage_name, job_id, error_msg
        )

    now = _now_utc()
    duration_ms = int((now - started_at).total_seconds() * 1000)

    if result is not None and error_msg is None:
        # Tag forced provenance if applicable
        if force:
            result._forced = True  # type: ignore[attr-defined]

        ok = _persist_stage_success(
            db=db,
            ctx=ctx,
            worker_id=worker_id,
            stage_name=stage_name,
            stage_doc=stage_doc,
            result=result,
            token=token,
            started_at=started_at,
            now=now,
            duration_ms=duration_ms,
        )

        if not ok:
            logger.warning(
                "Stage %s for job %s: update matched 0 docs "
                "(lease lost or idempotent replay). Stopping.",
                stage_name,
                job_id,
            )
            raise RuntimeError(
                f"Stage {stage_name} atomic write matched 0 docs "
                "(lease lost or idempotent replay)"
            )

        logger.info("Stage %s completed for job %s", stage_name, job_id)
        heartbeat(db, job_id, worker_id)
        return result

    else:
        _persist_stage_failure(
            db=db,
            ctx=ctx,
            worker_id=worker_id,
            stage_name=stage_name,
            stage_doc=stage_doc,
            error_msg=error_msg or "unknown error",
            now=now,
        )
        raise RuntimeError(
            f"Stage {stage_name} failed: {error_msg}"
        )


def run_sequence(
    db: Any,
    ctx: StageContext,
    stages: List[Any],
    worker_id: str,
) -> Dict[str, Any]:
    """
    Run enrichment stages in DAG order for a single job.

    Calls single_stage() for each stage. Skips stages already completed at
    the current checksum. Stops on first failure (does not retry here —
    retries happen on next worker tick via lease re-claim).

    After all required stages complete, sets lifecycle="ready" and ready_at.

    Args:
        db: PyMongo database handle
        ctx: StageContext with job_doc, checksums, attempt_number, config
        stages: List of StageBase instances in DAG order
        worker_id: This worker's identity string

    Returns:
        Dict summarising: {"completed": [...], "skipped": [...], "failed": [...]}
    """
    job_id = ctx.job_doc["_id"]
    summary: Dict[str, List[str]] = {"completed": [], "skipped": [], "failed": []}

    pre = ctx.job_doc.get("pre_enrichment") or {}
    existing_stages = pre.get("stages") or {}

    for stage in stages:
        stage_name = stage.name
        stage_doc = existing_stages.get(stage_name) or {}

        # Skip if already completed at the current checksum
        if (
            stage_doc.get("status") == StageStatus.COMPLETED
            and stage_doc.get("jd_checksum_at_completion") == ctx.jd_checksum
        ):
            logger.debug(
                "Skipping completed stage %s for job %s", stage_name, job_id
            )
            summary["skipped"].append(stage_name)
            continue

        try:
            result = single_stage(db, ctx, stage, worker_id, force=False)
            # Check if single_stage returned a "skipped" result
            if result.skip_reason == "already_completed_at_current_checksum":
                summary["skipped"].append(stage_name)
            else:
                summary["completed"].append(stage_name)
        except PrerequisiteNotMet as exc:
            logger.error(
                "Prerequisites not met for stage %s on job %s: %s",
                stage_name,
                job_id,
                exc.missing,
            )
            summary["failed"].append(stage_name)
            break
        except RuntimeError as exc:
            logger.error(
                "Stage %s failed for job %s: %s",
                stage_name,
                job_id,
                exc,
            )
            summary["failed"].append(stage_name)
            break

    # If all stages completed successfully, set lifecycle to "ready"
    if not summary["failed"]:
        ready_at = _now_utc()
        result_update = db["level-2"].update_one(
            {"_id": job_id, "lease_owner": worker_id},
            {"$set": {"lifecycle": "ready", "ready_at": ready_at}},
        )
        if result_update.matched_count > 0:
            logger.info("Job %s ready for dispatch", job_id)

    return summary


# Keep backward-compatible alias
def run_stages(
    db: Any,
    ctx: StageContext,
    stages: List[Any],
    worker_id: str,
) -> Dict[str, Any]:
    """
    Backward-compatible alias for run_sequence.

    Deprecated: prefer run_sequence() for new callers.
    """
    return run_sequence(db, ctx, stages, worker_id)


def _update_stage_status(
    db: Any,
    job_id: Any,
    worker_id: str,
    stage_name: str,
    status: StageStatus,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Apply a partial stage status update with lease guard."""
    set_doc: Dict[str, Any] = {
        f"pre_enrichment.stages.{stage_name}.status": status,
    }
    if extra:
        for k, v in extra.items():
            set_doc[f"pre_enrichment.stages.{stage_name}.{k}"] = v

    db["level-2"].update_one(
        {"_id": job_id, "lease_owner": worker_id},
        {"$set": set_doc},
    )
