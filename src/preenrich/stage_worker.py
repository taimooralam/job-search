"""Shared stage-worker entrypoint for the iteration-4 preenrich DAG."""

from __future__ import annotations

import argparse
import copy
import logging
import os
import socket
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from src.observability import record_error
from src.pipeline.queue import WorkItemQueue
from src.pipeline.tracing import PreenrichTracingSession
from src.preenrich.blueprint_config import (
    current_dag_version,
    current_input_snapshot_id,
    validate_blueprint_feature_flags,
)
from src.preenrich.blueprint_store import artifact_ref, upsert_artifact
from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.root_enqueuer import DAG_VERSION, SCHEMA_VERSION
from src.preenrich.schema import attempt_token, idempotency_key, input_snapshot_id
from src.preenrich.stage_registry import get_stage_definition, iter_stage_definitions
from src.preenrich.sweepers import drain_pending_next_stages, finalize_cv_ready
from src.preenrich.types import StageContext, get_stage_step_config

logger = logging.getLogger(__name__)

RETRY_BACKOFF_SECONDS = (30, 120, 600, 1800, 3600)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def build_worker_id() -> str:
    """Build a stable-enough worker id for lease ownership."""
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def stage_factory_map() -> dict[str, Callable[[], Any]]:
    """Return the concrete implementation factory for every registered stage."""
    from src.preenrich.stages.ai_classification import AIClassificationStage
    from src.preenrich.stages.annotations import AnnotationsStage
    from src.preenrich.stages.application_surface import ApplicationSurfaceStage
    from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
    from src.preenrich.stages.classification import ClassificationStage
    from src.preenrich.stages.company_research import CompanyResearchStage
    from src.preenrich.stages.cv_guidelines import CVGuidelinesStage
    from src.preenrich.stages.jd_extraction import JDExtractionStage
    from src.preenrich.stages.jd_facts import JDFactsStage
    from src.preenrich.stages.jd_structure import JDStructureStage
    from src.preenrich.stages.job_hypotheses import JobHypothesesStage
    from src.preenrich.stages.job_inference import JobInferenceStage
    from src.preenrich.stages.pain_point_intelligence import PainPointIntelligenceStage
    from src.preenrich.stages.pain_points import PainPointsStage
    from src.preenrich.stages.persona import PersonaStage
    from src.preenrich.stages.presentation_contract import PresentationContractStage
    from src.preenrich.stages.research_enrichment import ResearchEnrichmentStage
    from src.preenrich.stages.role_research import RoleResearchStage
    from src.preenrich.stages.stakeholder_surface import StakeholderSurfaceStage

    return {
        "jd_structure": JDStructureStage,
        "jd_extraction": JDExtractionStage,
        "jd_facts": JDFactsStage,
        "ai_classification": AIClassificationStage,
        "classification": ClassificationStage,
        "pain_points": PainPointsStage,
        "pain_point_intelligence": PainPointIntelligenceStage,
        "annotations": AnnotationsStage,
        "persona": PersonaStage,
        "persona_compat": PersonaStage,
        "company_research": CompanyResearchStage,
        "research_enrichment": ResearchEnrichmentStage,
        "stakeholder_surface": StakeholderSurfaceStage,
        "presentation_contract": PresentationContractStage,
        "application_surface": ApplicationSurfaceStage,
        "job_inference": JobInferenceStage,
        "job_hypotheses": JobHypothesesStage,
        "cv_guidelines": CVGuidelinesStage,
        "blueprint_assembly": BlueprintAssemblyStage,
        "role_research": RoleResearchStage,
    }


class StageWorker:
    """Claim and execute one stage-specific work item at a time."""

    def __init__(
        self,
        db: Any,
        *,
        stage_name: str,
        worker_id: Optional[str] = None,
        queue: Optional[WorkItemQueue] = None,
        stage_factories: Optional[dict[str, Callable[[], Any]]] = None,
        lease_seconds: Optional[int] = None,
        heartbeat_seconds: Optional[int] = None,
    ) -> None:
        self.db = db
        self.stage_name = stage_name
        self.worker_id = worker_id or build_worker_id()
        self.queue = queue or WorkItemQueue(db)
        self.level2 = db["level-2"]
        self.work_items = db["work_items"]
        self.stage_runs = db["preenrich_stage_runs"]
        self.job_runs = db["preenrich_job_runs"]
        self.definition = get_stage_definition(stage_name)
        self.stage_factories = stage_factories or stage_factory_map()
        self.lease_seconds = lease_seconds or int(os.getenv("PREENRICH_STAGE_LEASE_SECONDS", "600"))
        self.heartbeat_seconds = heartbeat_seconds or int(os.getenv("PREENRICH_STAGE_HEARTBEAT_SECONDS", "60"))

    def claim_next_work_item(self, *, now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
        """Claim the next eligible work item for this stage and mirror the lease to level-2."""
        current_time = now or utc_now()
        lease_expires_at = current_time + timedelta(seconds=self.lease_seconds)
        available_now = _lte_now("available_at", current_time, collection=self.work_items)
        lease_expired = _lte_now("lease_expires_at", current_time, collection=self.work_items)
        query = {
            "lane": "preenrich",
            "task_type": self.definition.task_type,
            "consumer_mode": "native_stage_dag",
            "$or": [
                {
                    "status": "pending",
                    **available_now,
                },
                {
                    "status": "failed",
                    **available_now,
                },
                {
                    "status": "leased",
                    **lease_expired,
                },
            ],
        }

        candidates = list(
            self.work_items.find(query)
            .sort([("priority", -1), ("available_at", 1), ("created_at", 1)])
            .limit(10)
        )
        for candidate in candidates:
            updated = self.work_items.find_one_and_update(
                {
                    "_id": candidate["_id"],
                    "$or": [
                        {
                            "status": "pending",
                            **available_now,
                        },
                        {
                            "status": "failed",
                            **available_now,
                        },
                        {
                            "status": "leased",
                            **lease_expired,
                        },
                    ],
                },
                {
                    "$set": {
                        "status": "leased",
                        "lease_owner": self.worker_id,
                        "lease_expires_at": lease_expires_at,
                        "updated_at": current_time,
                    },
                    "$inc": {"attempt_count": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
            if updated is None:
                continue

            self.level2.update_one(
                {"_id": _coerce_object_id(updated["subject_id"])},
                {
                    "$set": {
                        f"pre_enrichment.stage_states.{self.stage_name}.status": "leased",
                        f"pre_enrichment.stage_states.{self.stage_name}.attempt_count": updated["attempt_count"],
                        f"pre_enrichment.stage_states.{self.stage_name}.lease_owner": self.worker_id,
                        f"pre_enrichment.stage_states.{self.stage_name}.lease_expires_at": lease_expires_at,
                        f"pre_enrichment.stage_states.{self.stage_name}.started_at": current_time,
                        f"pre_enrichment.stage_states.{self.stage_name}.work_item_id": updated["_id"],
                        "updated_at": current_time,
                    }
                },
            )
            return updated

        return None

    def process_one(self, *, now: Optional[datetime] = None) -> dict[str, Any]:
        """Claim and process a single stage work item."""
        validate_blueprint_feature_flags()
        work_item = self.claim_next_work_item(now=now)
        if work_item is None:
            return {"status": "idle", "stage_name": self.stage_name}
        return self.process_claimed_work_item(work_item, now=now)

    def process_claimed_work_item(
        self,
        work_item: dict[str, Any],
        *,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Process one already-claimed stage work item."""
        current_time = now or utc_now()
        level2_id = _coerce_object_id(work_item["subject_id"])
        job_doc = self.level2.find_one({"_id": level2_id})
        if job_doc is None:
            self._cancel_work_item(work_item, reason="job_missing", now=current_time)
            return {"status": "cancelled", "reason": "job_missing", "work_item_id": work_item["_id"]}

        payload = work_item.get("payload") or {}
        current_snapshot = self._current_snapshot(job_doc, payload=payload)
        stage_state = (((job_doc.get("pre_enrichment") or {}).get("stage_states") or {}).get(self.stage_name) or {})
        attempt_number = int(work_item.get("attempt_count", stage_state.get("attempt_count", 1)))
        tracer = PreenrichTracingSession(
            run_id=f"preenrich:{self.stage_name}:{work_item['_id']}",
            session_id=payload.get("langfuse_session_id") or work_item["correlation_id"],
            metadata=self._trace_metadata(
                job_doc=job_doc,
                work_item=work_item,
                input_snapshot_id=current_snapshot,
                jd_checksum=str((job_doc.get("pre_enrichment") or {}).get("jd_checksum") or jd_checksum(job_doc.get("description", ""))),
                attempt_count=attempt_number,
                lifecycle_before=str(job_doc.get("lifecycle") or "selected"),
                lifecycle_after=str(job_doc.get("lifecycle") or "selected"),
            ),
        )
        tracer.record_event(
            "scout.preenrich.claim",
            self._trace_metadata(
                job_doc=job_doc,
                work_item=work_item,
                input_snapshot_id=current_snapshot,
                jd_checksum=str((job_doc.get("pre_enrichment") or {}).get("jd_checksum") or jd_checksum(job_doc.get("description", ""))),
                attempt_count=attempt_number,
                lifecycle_before=str(job_doc.get("lifecycle") or "selected"),
                lifecycle_after=str(job_doc.get("lifecycle") or "selected"),
            ),
        )

        payload_snapshot = payload.get("input_snapshot_id")
        if payload_snapshot != current_snapshot:
            self._cancel_for_snapshot_change(work_item, job_doc, current_snapshot=current_snapshot, now=current_time)
            cancelled = {
                "status": "cancelled",
                "reason": "snapshot_changed",
                "work_item_id": work_item["_id"],
                "job_id": str(level2_id),
            }
            tracer.record_event(
                "scout.preenrich.retry",
                self._trace_metadata(
                    job_doc=job_doc,
                    work_item=work_item,
                    input_snapshot_id=current_snapshot,
                    jd_checksum=str((job_doc.get("pre_enrichment") or {}).get("jd_checksum") or jd_checksum(job_doc.get("description", ""))),
                    attempt_count=attempt_number,
                    lifecycle_before=str(job_doc.get("lifecycle") or "preenriching"),
                    lifecycle_after=str(job_doc.get("lifecycle") or "preenriching"),
                    extra={"reason": "snapshot_changed"},
                ),
            )
            tracer.complete(output=cancelled)
            return cancelled

        prereq_missing = self._missing_prerequisites(job_doc, current_snapshot)
        if prereq_missing:
            self._retry_work_item(
                work_item,
                job_doc,
                error_class="prerequisite_not_ready",
                error_message=f"Missing prerequisites: {', '.join(prereq_missing)}",
                now=current_time,
            )
            retry_result = {
                "status": "retry_pending",
                "reason": "prerequisite_not_ready",
                "missing_prerequisites": prereq_missing,
                "work_item_id": work_item["_id"],
            }
            tracer.record_event(
                "scout.preenrich.retry",
                self._trace_metadata(
                    job_doc=job_doc,
                    work_item=work_item,
                    input_snapshot_id=current_snapshot,
                    jd_checksum=str((job_doc.get("pre_enrichment") or {}).get("jd_checksum") or jd_checksum(job_doc.get("description", ""))),
                    attempt_count=attempt_number,
                    lifecycle_before=str(job_doc.get("lifecycle") or "preenriching"),
                    lifecycle_after=str(job_doc.get("lifecycle") or "preenriching"),
                    extra={"reason": "prerequisite_not_ready", "missing_prerequisites": prereq_missing},
                ),
            )
            tracer.complete(output=retry_result)
            return retry_result

        stage = self._make_stage()
        shadow_mode = os.getenv("PREENRICH_SHADOW_MODE", "false").strip().lower() == "true"
        ctx = StageContext(
            job_doc=job_doc,
            jd_checksum=str((job_doc.get("pre_enrichment") or {}).get("jd_checksum") or jd_checksum(job_doc.get("description", ""))),
            company_checksum=str((job_doc.get("pre_enrichment") or {}).get("company_checksum") or company_checksum(job_doc.get("company"), job_doc.get("company_domain"))),
            input_snapshot_id=current_snapshot,
            attempt_number=attempt_number,
            config=get_stage_step_config(self.stage_name),
            shadow_mode=shadow_mode,
            stage_name=self.stage_name,
        )
        token = attempt_token(
            job_id=str(job_doc.get("job_id") or level2_id),
            stage=self.stage_name,
            jd_checksum=ctx.jd_checksum,
            prompt_version=ctx.config.prompt_version,
            attempt_number=attempt_number,
        )

        run_id = self._insert_stage_run(
            job_doc,
            work_item,
            attempt_number,
            current_time,
            trace_id=tracer.trace_id,
            trace_url=tracer.trace_url,
        )
        result = None
        error: Optional[Exception] = None
        start_monotonic = time.monotonic()
        stage_tracer = tracer.start_stage_span(
            self.stage_name,
            self._trace_metadata(
                job_doc=job_doc,
                work_item=work_item,
                input_snapshot_id=current_snapshot,
                jd_checksum=ctx.jd_checksum,
                attempt_count=attempt_number,
                attempt_token=token,
                lifecycle_before=str(job_doc.get("lifecycle") or "preenriching"),
                lifecycle_after=str(job_doc.get("lifecycle") or "preenriching"),
            ),
        )
        ctx.tracer = stage_tracer
        with self._heartbeat_loop(work_item["_id"], level2_id):
            try:
                result = stage.run(ctx)
            except Exception as exc:  # pragma: no cover - exercised through tests via fake stages
                error = exc

        finished_at = utc_now()
        duration_ms = int((time.monotonic() - start_monotonic) * 1000)
        if error is not None:
            stage_tracer.complete(output={"status": "failed", "error_class": classify_error(error), "shadow_mode": shadow_mode})
            error_class = classify_error(error)
            record_error(
                session_id=str(getattr(stage_tracer, "session_id", None) or level2_id),
                trace_id=getattr(stage_tracer, "trace_id", None),
                pipeline="preenrich",
                stage=self.stage_name,
                exc=error,
                metadata={
                    "level2_job_id": str(level2_id),
                    "attempt_number": attempt_number,
                    "shadow_mode": shadow_mode,
                    "error_class": error_class,
                },
            )
            self._finish_stage_run(run_id, status="failed", duration_ms=duration_ms, error=error)
            failure_result = self._handle_stage_failure(
                work_item,
                job_doc,
                ctx=ctx,
                attempt_number=attempt_number,
                error=error,
                error_class=error_class,
                now=finished_at,
            )
            tracer.record_event(
                "scout.preenrich.deadletter" if failure_result["status"] == "deadletter" else "scout.preenrich.retry",
                self._trace_metadata(
                    job_doc=job_doc,
                    work_item=work_item,
                    input_snapshot_id=current_snapshot,
                    jd_checksum=ctx.jd_checksum,
                    attempt_count=attempt_number,
                    attempt_token=token,
                    lifecycle_before=str(job_doc.get("lifecycle") or "preenriching"),
                    lifecycle_after="deadletter" if failure_result["status"] == "deadletter" else "preenriching",
                    extra={"error_class": error_class, "status": failure_result["status"]},
                ),
            )
            tracer.complete(output=failure_result)
            return failure_result

        assert result is not None
        stage_tracer.complete(
            output={
                "status": "completed",
                "provider": result.provider_used,
                "model": result.model_used,
                "tokens_input": result.tokens_input,
                "tokens_output": result.tokens_output,
                "cost_usd": result.cost_usd,
                "shadow_mode": shadow_mode,
            },
        )
        artifact_refs = self._upsert_stage_artifacts(
            job_doc,
            result,
            now=finished_at,
            tracer=ctx.tracer,
        )
        next_stage_entries = self._build_next_stage_entries(
            job_doc=job_doc,
            snapshot_id=current_snapshot,
            jd_cs=ctx.jd_checksum,
            company_cs=ctx.company_checksum,
            session_id=payload.get("langfuse_session_id") or work_item["correlation_id"],
        )
        self._persist_stage_success_phase_a(
            job_doc=job_doc,
            work_item=work_item,
            result=result,
            ctx=ctx,
            token=token,
            artifact_refs=artifact_refs,
            next_stage_entries=next_stage_entries,
            now=finished_at,
            duration_ms=duration_ms,
        )
        self._finish_stage_run(run_id, status="completed", duration_ms=duration_ms, result=result)

        try:
            self._inline_phase_b_enqueue(level2_id=job_doc["_id"], now=finished_at)
            tracer.record_event(
                "scout.preenrich.enqueue_next",
                self._trace_metadata(
                    job_doc=job_doc,
                    work_item=work_item,
                    input_snapshot_id=current_snapshot,
                    jd_checksum=ctx.jd_checksum,
                    attempt_count=attempt_number,
                    attempt_token=token,
                    lifecycle_before=str(job_doc.get("lifecycle") or "preenriching"),
                    lifecycle_after="preenriching",
                    extra={"next_stage_count": len(next_stage_entries)},
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive; sweeper covers this path
            logger.warning("inline next-stage enqueue failed for %s/%s: %s", level2_id, self.stage_name, exc)

        self.queue.mark_done(
            work_item["_id"],
            result_ref={
                "stage_name": self.stage_name,
                "level2_job_id": str(level2_id),
                "status": "completed",
                "attempt_token": token,
                "duration_ms": duration_ms,
            },
            now=finished_at,
        )
        finalized = finalize_cv_ready(self.db, level2_id=level2_id, now=finished_at)
        tracer.record_event(
            "scout.preenrich.finalize_cv_ready",
            self._trace_metadata(
                job_doc=job_doc,
                work_item=work_item,
                input_snapshot_id=current_snapshot,
                jd_checksum=ctx.jd_checksum,
                attempt_count=attempt_number,
                attempt_token=token,
                lifecycle_before=str(job_doc.get("lifecycle") or "preenriching"),
                lifecycle_after="cv_ready" if finalized else "preenriching",
                extra={"finalized": finalized},
            ),
        )
        success_result = {
            "status": "completed",
            "stage_name": self.stage_name,
            "work_item_id": work_item["_id"],
            "job_id": str(level2_id),
            "next_stage_count": len(next_stage_entries),
        }
        tracer.complete(output=success_result | {"cv_ready_finalized": finalized})
        return success_result

    def _persist_stage_success_phase_a(
        self,
        *,
        job_doc: dict[str, Any],
        work_item: dict[str, Any],
        result: Any,
        ctx: StageContext,
        token: str,
        artifact_refs: dict[str, Any],
        next_stage_entries: list[dict[str, Any]],
        now: datetime,
        duration_ms: int,
    ) -> None:
        """Phase A single-document write for stage success."""
        stage_output = self._resolve_placeholders(
            dict(result.stage_output or {}),
            refs={**self._known_artifact_refs(job_doc), **artifact_refs},
            now=now,
        )
        if not stage_output and not result.artifact_writes:
            stage_output = self._resolve_placeholders(
                dict(result.output),
                refs={**self._known_artifact_refs(job_doc), **artifact_refs},
                now=now,
            )
        if artifact_refs:
            stage_output["artifact_refs"] = artifact_refs
        set_doc: dict[str, Any] = {
            f"pre_enrichment.outputs.{self.stage_name}": stage_output,
            f"pre_enrichment.stage_states.{self.stage_name}.status": "completed",
            f"pre_enrichment.stage_states.{self.stage_name}.completed_at": now,
            f"pre_enrichment.stage_states.{self.stage_name}.attempt_token": token,
            f"pre_enrichment.stage_states.{self.stage_name}.jd_checksum_at_completion": ctx.jd_checksum,
            f"pre_enrichment.stage_states.{self.stage_name}.input_snapshot_id": ctx.input_snapshot_id,
            f"pre_enrichment.stage_states.{self.stage_name}.provider": result.provider_used,
            f"pre_enrichment.stage_states.{self.stage_name}.model": result.model_used,
            f"pre_enrichment.stage_states.{self.stage_name}.prompt_version": result.prompt_version or ctx.config.prompt_version,
            f"pre_enrichment.stage_states.{self.stage_name}.output_ref": {
                "path": f"pre_enrichment.outputs.{self.stage_name}",
                "artifacts": artifact_refs,
            },
            f"pre_enrichment.stage_states.{self.stage_name}.last_error": None,
            f"pre_enrichment.stage_states.{self.stage_name}.tokens_input": result.tokens_input,
            f"pre_enrichment.stage_states.{self.stage_name}.tokens_output": result.tokens_output,
            f"pre_enrichment.stage_states.{self.stage_name}.cost_usd": result.cost_usd,
            f"pre_enrichment.stage_states.{self.stage_name}.lease_owner": None,
            f"pre_enrichment.stage_states.{self.stage_name}.lease_expires_at": None,
            f"pre_enrichment.stage_states.{self.stage_name}.attempt_count": work_item["attempt_count"],
            f"pre_enrichment.stage_states.{self.stage_name}.work_item_id": work_item["_id"],
            "updated_at": now,
        }
        set_doc.update(
            self._resolve_placeholders(
                dict(result.output),
                refs={**self._known_artifact_refs(job_doc), **artifact_refs},
                now=now,
            )
        )

        update = {"$set": set_doc}
        if next_stage_entries:
            update["$push"] = {
                "pre_enrichment.pending_next_stages": {
                    "$each": next_stage_entries,
                }
            }

        result_update = self.level2.update_one(
            {
                "_id": job_doc["_id"],
                f"pre_enrichment.stage_states.{self.stage_name}.lease_owner": self.worker_id,
                f"pre_enrichment.stage_states.{self.stage_name}.attempt_token": {"$ne": token},
            },
            update,
        )
        if result_update.modified_count != 1:
            raise RuntimeError(f"phase-a success write lost lease for {job_doc['_id']}:{self.stage_name}")

    def _inline_phase_b_enqueue(self, *, level2_id: ObjectId | str, now: Optional[datetime] = None) -> dict[str, int]:
        """Inline Phase B downstream enqueue, backed by the sweeper implementation."""
        return drain_pending_next_stages(self.db, level2_id=level2_id, now=now, limit=1)

    def _build_next_stage_entries(
        self,
        *,
        job_doc: dict[str, Any],
        snapshot_id: str,
        jd_cs: str,
        company_cs: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """Build pending_next_stages entries for direct downstream stages."""
        entries: list[dict[str, Any]] = []
        for stage in iter_stage_definitions():
            if self.stage_name not in stage.prerequisites:
                continue
            dag_version = str(((job_doc.get("pre_enrichment") or {}).get("dag_version")) or current_dag_version())
            entries.append(
                {
                    "idempotency_key": idempotency_key(stage.name, str(job_doc["_id"]), snapshot_id),
                    "task_type": stage.task_type,
                    "priority": stage.default_priority,
                    "max_attempts": stage.max_attempts,
                    "correlation_id": session_id,
                    "payload": {
                        "stage_name": stage.name,
                        "input_snapshot_id": snapshot_id,
                        "jd_checksum": jd_cs,
                        "company_checksum": company_cs,
                        "dag_version": dag_version,
                        "schema_version": SCHEMA_VERSION,
                        "langfuse_session_id": session_id,
                    },
                    "enqueued_at": None,
                }
            )
        return entries

    def _handle_stage_failure(
        self,
        work_item: dict[str, Any],
        job_doc: dict[str, Any],
        *,
        ctx: StageContext,
        attempt_number: int,
        error: Exception,
        error_class: str,
        now: datetime,
    ) -> dict[str, Any]:
        """Apply retry or deadletter semantics for one stage failure."""
        terminal = self._is_terminal_error(error_class) or work_item["attempt_count"] >= self.definition.max_attempts
        if terminal:
            self._deadletter_work_item(
                work_item,
                job_doc,
                error_class=error_class,
                error_message=str(error),
                now=now,
            )
            return {
                "status": "deadletter",
                "stage_name": self.stage_name,
                "work_item_id": work_item["_id"],
                "job_id": str(job_doc["_id"]),
                "error_class": error_class,
            }

        self._retry_work_item(
            work_item,
            job_doc,
            error_class=error_class,
            error_message=str(error),
            now=now,
        )
        return {
            "status": "retry_pending",
            "stage_name": self.stage_name,
            "work_item_id": work_item["_id"],
            "job_id": str(job_doc["_id"]),
            "error_class": error_class,
        }

    def _retry_work_item(
        self,
        work_item: dict[str, Any],
        job_doc: dict[str, Any],
        *,
        error_class: str,
        error_message: str,
        now: datetime,
    ) -> None:
        """Move the work item and stage state back to retry-pending."""
        retry_delay = retry_delay_seconds(int(work_item.get("attempt_count", 1)))
        available_at = now + timedelta(seconds=retry_delay)
        self.work_items.update_one(
            {"_id": work_item["_id"], "lease_owner": self.worker_id},
            {
                "$set": {
                    "status": "pending",
                    "available_at": available_at,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                    "last_error": {
                        "class": error_class,
                        "message": error_message,
                        "at": now,
                    },
                }
            },
        )
        self.level2.update_one(
            {"_id": job_doc["_id"]},
            {
                "$set": {
                    f"pre_enrichment.stage_states.{self.stage_name}.status": "retry_pending",
                    f"pre_enrichment.stage_states.{self.stage_name}.attempt_count": work_item["attempt_count"],
                    f"pre_enrichment.stage_states.{self.stage_name}.lease_owner": None,
                    f"pre_enrichment.stage_states.{self.stage_name}.lease_expires_at": None,
                    f"pre_enrichment.stage_states.{self.stage_name}.last_error": {
                        "class": error_class,
                        "message": error_message,
                        "at": now,
                    },
                    "pre_enrichment.last_error": {
                        "stage": self.stage_name,
                        "class": error_class,
                        "message": error_message,
                        "at": now,
                    },
                    "updated_at": now,
                }
            },
        )

    def _deadletter_work_item(
        self,
        work_item: dict[str, Any],
        job_doc: dict[str, Any],
        *,
        error_class: str,
        error_message: str,
        now: datetime,
    ) -> None:
        """Deadletter the stage and cancel remaining downstream work."""
        self.queue.mark_deadletter(work_item["_id"], error=error_message, now=now)
        lifecycle = "deadletter" if self.definition.job_fail_policy == "deadletter" else "failed"
        self.level2.update_one(
            {"_id": job_doc["_id"]},
            {
                "$set": {
                    f"pre_enrichment.stage_states.{self.stage_name}.status": "deadletter",
                    f"pre_enrichment.stage_states.{self.stage_name}.lease_owner": None,
                    f"pre_enrichment.stage_states.{self.stage_name}.lease_expires_at": None,
                    f"pre_enrichment.stage_states.{self.stage_name}.last_error": {
                        "class": error_class,
                        "message": error_message,
                        "at": now,
                    },
                    "pre_enrichment.deadletter_reason": {
                        "stage": self.stage_name,
                        "class": error_class,
                        "message": error_message,
                        "at": now,
                    },
                    "pre_enrichment.last_error": {
                        "stage": self.stage_name,
                        "class": error_class,
                        "message": error_message,
                        "at": now,
                    },
                    "lifecycle": lifecycle,
                    "updated_at": now,
                }
            },
        )
        self.job_runs.update_one(
            {"level2_job_id": str(job_doc["_id"])},
            {
                "$set": {
                    "status": lifecycle,
                    "updated_at": now,
                    "last_error": {
                        "stage": self.stage_name,
                        "class": error_class,
                        "message": error_message,
                        "at": now,
                    },
                }
            },
        )
        self._send_deadletter_alert_if_allowed(
            job_doc,
            error_class=error_class,
            error_message=error_message,
            now=now,
        )
        self.work_items.update_many(
            {
                "lane": "preenrich",
                "subject_id": str(job_doc["_id"]),
                "status": {"$in": ["pending", "leased", "failed"]},
                "_id": {"$ne": work_item["_id"]},
            },
            {
                "$set": {
                    "status": "cancelled",
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                    "last_error": {
                        "class": "cancelled_due_to_deadletter",
                        "message": error_message,
                        "at": now,
                    },
                }
            },
        )

    def _send_deadletter_alert_if_allowed(
        self,
        job_doc: dict[str, Any],
        *,
        error_class: str,
        error_message: str,
        now: datetime,
    ) -> None:
        """Send a rate-limited deadletter Telegram alert."""
        limit = int(os.getenv("PREENRICH_ALERT_MAX_PER_HOUR", "10") or "10")
        bucket = now.strftime("%Y%m%d%H")
        alerts = self.db["preenrich_alerts"]
        current = alerts.find_one({"bucket": bucket}) or {"count": 0}
        if int(current.get("count", 0)) >= limit:
            return
        alerts.update_one(
            {"bucket": bucket},
            {"$inc": {"count": 1}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        try:
            from src.common.telegram import send_telegram

            send_telegram(
                "\n".join(
                    [
                        "&#10060; <b>Preenrich Deadletter</b>",
                        f"<b>{job_doc.get('company', 'Unknown company')}</b> — {job_doc.get('title', 'Untitled role')}",
                        f"Stage: <code>{self.stage_name}</code>",
                        f"Job: <code>{job_doc.get('job_id') or job_doc['_id']}</code>",
                        f"Error: <code>{error_class}: {error_message[:180]}</code>",
                    ]
                )
            )
        except Exception:  # pragma: no cover - best effort
            logger.warning("Deadletter alert failed for %s/%s", job_doc.get("_id"), self.stage_name)

    def _is_terminal_error(self, error_class: str) -> bool:
        """Return whether the classified error should deadletter immediately."""
        return error_class in self.definition.terminal_error_tags

    def _cancel_for_snapshot_change(
        self,
        work_item: dict[str, Any],
        job_doc: dict[str, Any],
        *,
        current_snapshot: str,
        now: datetime,
    ) -> None:
        """Cancel stale work after snapshot drift is detected."""
        self._cancel_work_item(work_item, reason="snapshot_changed", now=now)
        self.level2.update_one(
            {"_id": job_doc["_id"]},
            {
                "$set": {
                    f"pre_enrichment.stage_states.{self.stage_name}.status": "cancelled",
                    f"pre_enrichment.stage_states.{self.stage_name}.lease_owner": None,
                    f"pre_enrichment.stage_states.{self.stage_name}.lease_expires_at": None,
                    f"pre_enrichment.stage_states.{self.stage_name}.input_snapshot_id": current_snapshot,
                    f"pre_enrichment.stage_states.{self.stage_name}.last_error": {
                        "class": "snapshot_changed",
                        "message": "work item snapshot no longer matches current job snapshot",
                        "at": now,
                    },
                    "updated_at": now,
                }
            },
        )

    def _cancel_work_item(self, work_item: dict[str, Any], *, reason: str, now: datetime) -> None:
        """Cancel a claimed work item."""
        self.work_items.update_one(
            {"_id": work_item["_id"], "lease_owner": self.worker_id},
            {
                "$set": {
                    "status": "cancelled",
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                    "last_error": {
                        "class": reason,
                        "message": reason,
                        "at": now,
                    },
                }
            },
        )

    def _missing_prerequisites(self, job_doc: dict[str, Any], snapshot_id: str) -> list[str]:
        """Return any prerequisites that are not completed at the current snapshot."""
        stage_states = ((job_doc.get("pre_enrichment") or {}).get("stage_states") or {})
        missing: list[str] = []
        for prereq in self.definition.prerequisites:
            state = stage_states.get(prereq) or {}
            if state.get("status") != "completed":
                missing.append(prereq)
                continue
            if state.get("input_snapshot_id") != snapshot_id:
                missing.append(prereq)
        return missing

    def _make_stage(self) -> Any:
        """Instantiate the stage implementation for this worker."""
        try:
            factory = self.stage_factories[self.stage_name]
        except KeyError as exc:
            raise RuntimeError(f"No stage factory registered for {self.stage_name}") from exc
        return factory()

    def _current_snapshot(self, job_doc: dict[str, Any], *, payload: dict[str, Any]) -> str:
        """Recompute the current snapshot from level-2 state."""
        pre = job_doc.get("pre_enrichment") or {}
        dag_version = str(payload.get("dag_version") or pre.get("dag_version") or DAG_VERSION)
        current_jd_checksum = jd_checksum(job_doc.get("description", "") or job_doc.get("job_description", "") or "")
        current_company_checksum = company_checksum(job_doc.get("company"), job_doc.get("company_domain"))
        if dag_version == current_dag_version():
            return current_input_snapshot_id(current_jd_checksum, current_company_checksum, dag_version=dag_version)
        return input_snapshot_id(current_jd_checksum, current_company_checksum, dag_version)

    def _renew_leases(self, work_item_id: ObjectId, level2_id: ObjectId) -> None:
        """Renew the claimed work item lease and mirror it to stage state."""
        current_time = utc_now()
        new_expiry = current_time + timedelta(seconds=self.lease_seconds)
        self.queue.heartbeat(
            work_item_id,
            lease_owner=self.worker_id,
            lease_seconds=self.lease_seconds,
            now=current_time,
        )
        self.level2.update_one(
            {
                "_id": level2_id,
                f"pre_enrichment.stage_states.{self.stage_name}.lease_owner": self.worker_id,
            },
            {
                "$set": {
                    f"pre_enrichment.stage_states.{self.stage_name}.lease_expires_at": new_expiry,
                    "updated_at": current_time,
                }
            },
        )

    @contextmanager
    def _heartbeat_loop(self, work_item_id: ObjectId, level2_id: ObjectId):
        """Background lease renewal while the stage body executes."""
        stop_event = threading.Event()

        def _runner() -> None:
            while not stop_event.wait(self.heartbeat_seconds):
                self._renew_leases(work_item_id, level2_id)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop_event.set()
            thread.join(timeout=1)

    def _insert_stage_run(
        self,
        job_doc: dict[str, Any],
        work_item: dict[str, Any],
        attempt_number: int,
        started_at: datetime,
        *,
        trace_id: Optional[str] = None,
        trace_url: Optional[str] = None,
    ) -> ObjectId:
        """Persist one stage run audit document."""
        document = {
            "job_id": str(job_doc.get("job_id") or job_doc["_id"]),
            "level2_job_id": str(job_doc["_id"]),
            "stage": self.stage_name,
            "status": "running",
            "worker_id": self.worker_id,
            "attempt_count": attempt_number,
            "work_item_id": work_item["_id"],
            "started_at": started_at,
            "updated_at": started_at,
            "langfuse_session_id": (work_item.get("payload") or {}).get("langfuse_session_id") or work_item["correlation_id"],
            "langfuse_trace_id": trace_id,
            "langfuse_trace_url": trace_url,
        }
        inserted = self.stage_runs.insert_one(document)
        self.job_runs.update_one(
            {"level2_job_id": str(job_doc["_id"]), "status": {"$ne": "completed"}},
            {
                "$setOnInsert": {
                    "job_id": str(job_doc.get("job_id") or job_doc["_id"]),
                    "level2_job_id": str(job_doc["_id"]),
                    "started_at": started_at,
                },
                "$set": {
                    "status": "running",
                    "updated_at": started_at,
                    "langfuse_session_id": (work_item.get("payload") or {}).get("langfuse_session_id") or work_item["correlation_id"],
                    "langfuse_trace_id": trace_id,
                    "langfuse_trace_url": trace_url,
                },
            },
            upsert=True,
        )
        return inserted.inserted_id

    def _finish_stage_run(
        self,
        run_id: ObjectId,
        *,
        status: str,
        duration_ms: int,
        result: Any | None = None,
        error: Exception | None = None,
    ) -> None:
        """Finalize one stage run audit document."""
        update: dict[str, Any] = {
            "status": status,
            "duration_ms": duration_ms,
            "updated_at": utc_now(),
        }
        if result is not None:
            update["provider"] = getattr(result, "provider_used", None)
            update["model"] = getattr(result, "model_used", None)
        if error is not None:
            update["error"] = {"class": classify_error(error), "message": str(error)}
        self.stage_runs.update_one({"_id": run_id}, {"$set": update})

    def _trace_metadata(
        self,
        *,
        job_doc: dict[str, Any],
        work_item: dict[str, Any],
        input_snapshot_id: str,
        jd_checksum: str,
        attempt_count: int,
        lifecycle_before: str,
        lifecycle_after: str,
        attempt_token: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Build the canonical preenrich correlation payload for Langfuse."""
        payload = work_item.get("payload") or {}
        metadata = {
            "job_id": str(job_doc.get("job_id") or job_doc["_id"]),
            "level2_job_id": str(job_doc["_id"]),
            "correlation_id": work_item["correlation_id"],
            "langfuse_session_id": payload.get("langfuse_session_id") or work_item["correlation_id"],
            "run_id": f"preenrich:{self.stage_name}:{work_item['_id']}",
            "worker_id": self.worker_id,
            "task_type": work_item["task_type"],
            "stage_name": self.stage_name,
            "attempt_count": attempt_count,
            "attempt_token": attempt_token,
            "input_snapshot_id": input_snapshot_id,
            "jd_checksum": jd_checksum,
            "lifecycle_before": lifecycle_before,
            "lifecycle_after": lifecycle_after,
            "work_item_id": str(work_item["_id"]),
            "shadow_mode": os.getenv("PREENRICH_SHADOW_MODE", "false").strip().lower() == "true",
        }
        if extra:
            metadata.update(extra)
        return metadata

    def _upsert_stage_artifacts(
        self,
        job_doc: dict[str, Any],
        result: Any,
        *,
        now: datetime,
        tracer: Any,
    ) -> dict[str, Any]:
        """Persist any collection-backed artifacts and return ref metadata."""
        refs: dict[str, Any] = {}
        known_refs = self._known_artifact_refs(job_doc)
        artifacts = list(getattr(result, "artifact_writes", []) or [])
        span = tracer.start_substage_span(
            self.stage_name,
            "artifact_persist",
            {
                "stage_name": self.stage_name,
                "artifact_count": len(artifacts),
                "collections": [artifact.collection for artifact in artifacts],
                "job_id": str(job_doc.get("job_id") or job_doc["_id"]),
                "level2_job_id": str(job_doc["_id"]),
            },
        )
        try:
            for artifact in artifacts:
                stored = upsert_artifact(
                    self.db,
                    collection=artifact.collection,
                    unique_filter=self._resolve_placeholders(copy.deepcopy(artifact.unique_filter), refs=known_refs, now=now),
                    document=self._resolve_placeholders(copy.deepcopy(artifact.document), refs=known_refs, now=now),
                    now=now,
                )
                refs[artifact.ref_name] = artifact_ref(stored, collection=artifact.collection)
        except Exception:
            tracer.end_span(
                span,
                output={
                    "status": "failed",
                    "artifact_count": len(artifacts),
                },
            )
            raise
        tracer.end_span(
            span,
            output={
                "status": "completed",
                "artifact_count": len(artifacts),
                "artifact_ref_names": sorted(refs.keys()),
            },
        )
        return refs

    def _known_artifact_refs(self, job_doc: dict[str, Any]) -> dict[str, Any]:
        refs: dict[str, Any] = {}
        outputs = ((job_doc.get("pre_enrichment") or {}).get("outputs") or {})
        for stage_output in outputs.values():
            for key, value in (stage_output.get("artifact_refs") or {}).items():
                refs[key] = value
        refs.update(((job_doc.get("pre_enrichment") or {}).get("job_blueprint_refs") or {}))
        return refs

    def _resolve_placeholders(self, value: Any, *, refs: dict[str, Any], now: datetime) -> Any:
        if isinstance(value, dict):
            return {key: self._resolve_placeholders(inner, refs=refs, now=now) for key, inner in value.items()}
        if isinstance(value, list):
            return [self._resolve_placeholders(item, refs=refs, now=now) for item in value]
        if isinstance(value, str):
            if value == "__now__":
                return now
            if value.startswith("__ref__:"):
                path = value.split(":", 1)[1]
                parts = path.split(".")
                current: Any = refs
                for part in parts:
                    current = current[part]
                return current
            if value.startswith("__artifact__:"):
                key = value.split(":", 1)[1]
                current = refs.get(key)
                if isinstance(current, dict) and "id" in current:
                    return current["id"]
        return value


def retry_delay_seconds(attempt_count: int) -> int:
    """Return the configured backoff for the current attempt count."""
    index = max(0, min(attempt_count - 1, len(RETRY_BACKOFF_SECONDS) - 1))
    return RETRY_BACKOFF_SECONDS[index]


def classify_error(error: Exception) -> str:
    """Map an exception into a retry/deadletter class tag."""
    message = str(error).lower()
    if isinstance(error, NotImplementedError):
        return "unsupported_provider"
    if "unsupported provider" in message:
        return "unsupported_provider"
    if "no " in message or "missing" in message:
        return "missing_required_input"
    if "schema" in message or "validation" in message:
        return "schema_validation"
    if "timeout" in message:
        return "provider_timeout"
    return "transient_error"


def run_once(db: Any, *, stage_name: str) -> dict[str, Any]:
    """Process exactly one work item for the selected stage."""
    return StageWorker(db, stage_name=stage_name).process_one()


def _coerce_object_id(value: ObjectId | str) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    return ObjectId(str(value))


def _lte_now(field_name: str, current_time: datetime, *, collection: Any) -> dict[str, Any]:
    """Build a `$lte now` filter using `$$NOW` in production and a local fallback in mongomock tests."""
    module_name = type(collection).__module__
    if "mongomock" in module_name:
        return {field_name: {"$lte": current_time}}
    return {"$expr": {"$lte": [f"${field_name}", "$$NOW"]}}


def _get_db() -> Any:
    from pymongo import MongoClient

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    return MongoClient(uri)["jobs"]


def _parse_stage_name() -> str:
    raw = os.getenv("PREENRICH_STAGE_ALLOWLIST", "").strip()
    if not raw:
        raise RuntimeError("PREENRICH_STAGE_ALLOWLIST must contain exactly one stage name")
    parts = [item.strip() for item in raw.split(",") if item.strip()]
    if len(parts) != 1:
        raise RuntimeError("PREENRICH_STAGE_ALLOWLIST must contain exactly one stage name")
    return parts[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Iteration-4 preenrich stage worker")
    parser.add_argument("--stage", dest="stage_name", default=None, help="Override the single allowed stage name")
    args = parser.parse_args()

    stage_name = args.stage_name or _parse_stage_name()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = run_once(_get_db(), stage_name=stage_name)
    logger.info("preenrich stage worker result=%s", result)


if __name__ == "__main__":
    main()
