"""
Pre-enrichment worker — long-running entrypoint.

Started as: python -m src.preenrich.worker

Feature flag: PREENRICH_WORKER_ENABLED (default "false"). When false, the
worker logs "disabled" and sleeps without claiming any work — safe to deploy
without activating.

Environment variables:
    PREENRICH_WORKER_ENABLED   Enable the worker (default: false)
    PREENRICH_TICK_SECONDS     Polling interval in seconds (default: 30)
    PREENRICH_MAX_IN_FLIGHT    Max concurrent in-flight jobs (default: 12)
    MONGODB_URI                MongoDB connection string
    TELEGRAM_BOT_TOKEN         For per-tick Telegram summary (optional)
    TELEGRAM_CHAT_ID           Target chat for Telegram (optional)
"""

import logging
import os
import signal
import socket
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _build_worker_id() -> str:
    """Unique worker identity: hostname + pid + random suffix."""
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _get_db() -> Any:
    """Connect to MongoDB and return the jobs database."""
    from pymongo import MongoClient

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    client = MongoClient(uri)
    return client["jobs"]


def _count_in_flight(db: Any) -> int:
    """Count jobs currently in preenriching lifecycle."""
    return db["level-2"].count_documents({"lifecycle": "preenriching"})


def _format_fallback_summary(fallback_counts: Dict[str, Any]) -> str:
    """
    Format per-stage fallback-rate metrics for the Telegram tick summary.

    Example output:
      jd_extraction: 12/12 success, 0 fallback
      pain_points: 11/12 success, 1 fallback (error_schema)

    Args:
        fallback_counts: Aggregated {stage_name: {success, fallback, fallback_reason}} dict.

    Returns:
        Formatted multi-line string, or empty string if no data.
    """
    if not fallback_counts:
        return ""

    lines = []
    for stage, counts in sorted(fallback_counts.items()):
        total = counts.get("total", 0)
        successes = counts.get("success", 0)
        fallbacks = counts.get("fallback", 0)
        reason = counts.get("last_fallback_reason")
        fallback_str = f"{fallbacks} fallback"
        if reason:
            fallback_str += f" ({reason})"
        lines.append(
            f"  {stage}: {successes}/{total} success, {fallback_str}"
        )
    return "\n".join(lines)


def _send_tick_summary(
    worker_id: str,
    tick_stats: Dict[str, Any],
) -> None:
    """Best-effort Telegram tick summary with per-stage fallback-rate metrics."""
    try:
        from src.common.telegram import send_telegram

        lines = [
            f"<b>Preenrich tick</b>: {worker_id[:20]}",
            f"claimed={tick_stats.get('claimed', 0)} "
            f"completed={tick_stats.get('completed', 0)} "
            f"failed={tick_stats.get('failed', 0)} "
            f"skipped={tick_stats.get('skipped', 0)}",
        ]

        # Phase 2b: per-stage fallback rate
        fallback_summary = _format_fallback_summary(
            tick_stats.get("fallback_counts", {})
        )
        if fallback_summary:
            lines.append("<b>Fallback rates:</b>")
            lines.append(fallback_summary)

        send_telegram("\n".join(lines))
    except Exception:
        pass  # Best-effort — never block the worker


class _GracefulShutdown:
    """SIGTERM handler that lets the current tick finish."""

    def __init__(self) -> None:
        self.should_stop = False
        signal.signal(signal.SIGTERM, self._handle)
        signal.signal(signal.SIGINT, self._handle)

    def _handle(self, signum: int, frame: Any) -> None:
        logger.info("Received signal %d — finishing current tick then shutting down", signum)
        self.should_stop = True


def run_worker_loop(db: Optional[Any] = None) -> None:
    """
    Main worker loop.

    Checks PREENRICH_WORKER_ENABLED on each tick so the flag can be toggled
    at runtime without restarting the container.
    """
    shutdown = _GracefulShutdown()
    worker_id = _build_worker_id()
    tick_seconds = int(os.getenv("PREENRICH_TICK_SECONDS", "30"))
    max_in_flight = int(os.getenv("PREENRICH_MAX_IN_FLIGHT", "12"))

    logger.info("Pre-enrichment worker starting: id=%s", worker_id)

    if db is None:
        db = _get_db()

    # Import stage modules (lazy to avoid import cost when disabled)
    from src.preenrich.lease import claim_one, release
    from src.preenrich.checksums import jd_checksum, company_checksum
    from src.preenrich.types import StageContext, StepConfig
    from src.preenrich.dispatcher import run_sequence as run_stages
    from src.preenrich.stages.jd_structure import JDStructureStage
    from src.preenrich.stages.jd_extraction import JDExtractionStage
    from src.preenrich.stages.ai_classification import AIClassificationStage
    from src.preenrich.stages.pain_points import PainPointsStage
    from src.preenrich.stages.annotations import AnnotationsStage
    from src.preenrich.stages.persona import PersonaStage
    from src.preenrich.stages.company_research import CompanyResearchStage
    from src.preenrich.stages.role_research import RoleResearchStage

    # Phase 2: all 8 stages in DAG order
    # fit_signal deferred to Phase 5 (no live consumer in BatchPipelineService yet)
    stages = [
        JDStructureStage(),
        JDExtractionStage(),
        AIClassificationStage(),
        PainPointsStage(),
        AnnotationsStage(),
        PersonaStage(),
        CompanyResearchStage(),
        RoleResearchStage(),
    ]

    while not shutdown.should_stop:
        enabled = os.getenv("PREENRICH_WORKER_ENABLED", "false").lower() == "true"

        if not enabled:
            logger.info(
                "Pre-enrichment worker disabled (PREENRICH_WORKER_ENABLED=false). "
                "Sleeping %ds.",
                tick_seconds,
            )
            time.sleep(tick_seconds)
            continue

        tick_stats: Dict[str, Any] = {
            "claimed": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "fallback_counts": {},  # {stage_name: {total, success, fallback, last_fallback_reason}}
        }

        try:
            # Backpressure: refuse new claims when too many in-flight
            in_flight = _count_in_flight(db)
            if in_flight >= max_in_flight:
                logger.info(
                    "Backpressure: %d jobs in-flight (max %d). Sleeping.",
                    in_flight, max_in_flight,
                )
                time.sleep(tick_seconds)
                continue

            now = datetime.now(timezone.utc)
            job_doc = claim_one(db, worker_id, now=now)

            if job_doc is None:
                logger.debug("No claimable jobs. Sleeping %ds.", tick_seconds)
                time.sleep(tick_seconds)
                continue

            tick_stats["claimed"] += 1
            job_id = job_doc["_id"]
            logger.info("Claimed job %s", job_id)

            # Build context
            description = job_doc.get("description", "")
            jd_cs = jd_checksum(description)
            company_name = job_doc.get("company", "")
            company_domain = job_doc.get("company_domain", "")
            company_cs = company_checksum(company_name, company_domain)

            import hashlib
            snapshot_id = "sha256:" + hashlib.sha256(
                description.encode("utf-8")
            ).hexdigest()

            # Determine attempt_number
            pre = job_doc.get("pre_enrichment") or {}
            attempt_number = pre.get("attempt_number", 0) + 1

            shadow_mode = os.getenv("PREENRICH_SHADOW_MODE", "false").lower() == "true"
            ctx = StageContext(
                job_doc=job_doc,
                jd_checksum=jd_cs,
                company_checksum=company_cs,
                input_snapshot_id=snapshot_id,
                attempt_number=attempt_number,
                config=StepConfig(),
                shadow_mode=shadow_mode,
            )

            # Initialise pre_enrichment root if absent
            db["level-2"].update_one(
                {"_id": job_id},
                {
                    "$setOnInsert": {},
                    "$set": {
                        "pre_enrichment.schema_version": 1,
                        "pre_enrichment.jd_checksum": jd_cs,
                        "pre_enrichment.company_checksum": company_cs,
                        "pre_enrichment.input_snapshot_id": snapshot_id,
                        "pre_enrichment.attempt_number": attempt_number,
                    },
                },
            )

            summary = run_stages(db, ctx, stages, worker_id)
            tick_stats["completed"] += len(summary.get("completed", []))
            tick_stats["failed"] += len(summary.get("failed", []))
            tick_stats["skipped"] += len(summary.get("skipped", []))

            # Phase 2b: accumulate per-stage fallback metrics across jobs in the tick
            for stage_name, counts in summary.get("fallback_counts", {}).items():
                agg = tick_stats["fallback_counts"].setdefault(
                    stage_name,
                    {"total": 0, "success": 0, "fallback": 0, "last_fallback_reason": None},
                )
                agg["total"] += 1
                agg["success"] += counts.get("success", 0)
                agg["fallback"] += counts.get("fallback", 0)
                if counts.get("fallback_reason"):
                    agg["last_fallback_reason"] = counts["fallback_reason"]

            new_lifecycle = "ready" if not summary.get("failed") else "failed"
            release(db, job_id, worker_id, new_lifecycle)

        except Exception as exc:
            logger.exception("Unexpected error in worker tick: %s", exc)

        _send_tick_summary(worker_id, tick_stats)
        time.sleep(tick_seconds)

    logger.info("Pre-enrichment worker shut down cleanly.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    run_worker_loop()
