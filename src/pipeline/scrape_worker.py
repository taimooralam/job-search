"""Mongo-native scrape worker for scout iteration 2."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pymongo import MongoClient

from src.common.proxy_pool import load_proxy_pool
from src.common.scout_queue import append_scored_unique, scored_contains_job
from src.pipeline.discovery import SearchDiscoveryStore
from src.pipeline.queue import WorkItemQueue
from src.pipeline.scrape_common import (
    FailureDisposition,
    ScrapeSkipResult,
    ScrapeSuccessResult,
    classify_scrape_exception,
    evaluate_scrape_candidate,
    upsert_level1_scored_job,
)
from src.pipeline.tracing import ScrapeTracingSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scout_native_scrape")


@dataclass(frozen=True)
class ScrapeFeatureFlags:
    """Rollout flags for native scrape ownership."""

    enable_native_worker: bool
    use_mongo_work_items: bool
    enable_legacy_jsonl_consumer: bool
    write_scored_jsonl: bool
    write_level1: bool
    selector_compat_mode: bool
    persist_selector_payload: bool

    @classmethod
    def from_env(cls) -> "ScrapeFeatureFlags":
        write_scored_jsonl = _env_flag(
            "SCOUT_SCRAPE_WRITE_SCORED_JSONL_COMPAT",
            _env_flag("SCOUT_SCRAPE_WRITE_SCORED_JSONL", True),
        )
        return cls(
            enable_native_worker=_env_flag("SCOUT_SCRAPE_ENABLE_NATIVE_WORKER", False),
            use_mongo_work_items=_env_flag("SCOUT_SCRAPE_USE_MONGO_WORK_ITEMS", False),
            enable_legacy_jsonl_consumer=_env_flag("SCOUT_SCRAPE_ENABLE_LEGACY_JSONL_CONSUMER", True),
            write_scored_jsonl=write_scored_jsonl,
            write_level1=_env_flag("SCOUT_SCRAPE_WRITE_LEVEL1", True),
            selector_compat_mode=_env_flag("SCOUT_SCRAPE_SELECTOR_COMPAT_MODE", True),
            persist_selector_payload=_env_flag("SCOUT_SCRAPE_PERSIST_SELECTOR_PAYLOAD", True),
        )

    def validate(self) -> None:
        """Reject unsafe flag combinations."""
        if self.enable_native_worker and not self.use_mongo_work_items:
            raise RuntimeError(
                "SCOUT_SCRAPE_ENABLE_NATIVE_WORKER requires SCOUT_SCRAPE_USE_MONGO_WORK_ITEMS=true"
            )
        if self.enable_native_worker and self.selector_compat_mode and not (self.write_scored_jsonl and self.write_level1):
            raise RuntimeError(
                "SCOUT_SCRAPE_SELECTOR_COMPAT_MODE requires both "
                "SCOUT_SCRAPE_WRITE_SCORED_JSONL=true and SCOUT_SCRAPE_WRITE_LEVEL1=true"
            )


@dataclass
class CompatibilityWriteResult:
    """Outcome of selector-compatible handoff writes."""

    level1_upserted: bool = False
    level1_upserted_now: bool = False
    scored_jsonl_written: bool = False
    scored_jsonl_written_now: bool = False


class CompatibilityWriteError(RuntimeError):
    """Raised when selector-compatible outputs fail after scrape succeeds."""

    def __init__(self, message: str, *, partial: CompatibilityWriteResult | None = None):
        super().__init__(message)
        self.partial = partial or CompatibilityWriteResult()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the native worker."""
    parser = argparse.ArgumentParser(description="Scout native scrape worker")
    parser.add_argument("--limit", type=int, default=25, help="Maximum work items to process in one tick")
    parser.add_argument("--lease-seconds", type=int, default=300, help="Lease duration for claimed work items")
    parser.add_argument("--worker-id", type=str, default=None, help="Override generated worker id")
    parser.add_argument("--no-proxy", action="store_true", help="Skip proxy rotation and use direct requests")
    parser.add_argument("--trigger-mode", type=str, default="single_tick", choices=["single_tick", "manual", "daemon"])
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint for the native scrape worker."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")

    flags = ScrapeFeatureFlags.from_env()
    if not flags.enable_native_worker:
        logger.info("Native scrape worker disabled by SCOUT_SCRAPE_ENABLE_NATIVE_WORKER=false")
        return 0
    flags.validate()

    mongodb_uri = os.getenv("MONGODB_URI")
    if not mongodb_uri:
        raise RuntimeError("MONGODB_URI not set")

    db = MongoClient(mongodb_uri)["jobs"]
    worker = NativeScrapeWorker(db, flags=flags, worker_id=args.worker_id or build_worker_id(), use_proxy=not args.no_proxy)
    result = worker.run_once(max_items=args.limit, lease_seconds=args.lease_seconds, trigger_mode=args.trigger_mode)
    logger.info("Native scrape result: %s", result)
    return 0


class NativeScrapeWorker:
    """Claim native scrape work-items and preserve selector compatibility outputs."""

    def __init__(
        self,
        db,
        *,
        flags: ScrapeFeatureFlags,
        worker_id: str,
        use_proxy: bool,
    ) -> None:
        self.db = db
        self.flags = flags
        self.worker_id = worker_id
        self.use_proxy = use_proxy
        self.discovery = SearchDiscoveryStore(db)
        self.queue = WorkItemQueue(db)
        self.discovery.ensure_indexes()
        self.queue.ensure_indexes()
        self.level1 = db["level-1"]
        self._proxy_pool: list[str] = []

    def run_once(
        self,
        *,
        max_items: int,
        lease_seconds: int,
        trigger_mode: str,
        now: Optional[datetime] = None,
    ) -> dict[str, int]:
        """Process up to max_items native scrape work-items."""
        if self.use_proxy:
            self._proxy_pool = load_proxy_pool()
            logger.info("Proxy pool: %s proxies", len(self._proxy_pool))

        run_context = self.discovery.create_scrape_run(worker_id=self.worker_id, trigger_mode=trigger_mode, now=now)
        tracer = ScrapeTracingSession(
            run_id=run_context.run_id,
            session_id=run_context.langfuse_session_id,
            metadata={
                "worker_id": self.worker_id,
                "trigger_mode": trigger_mode,
                "use_proxy": self.use_proxy,
            },
        )
        self.discovery.update_scrape_run(
            run_context.run_id,
            langfuse_trace_id=tracer.trace_id,
            langfuse_trace_url=tracer.trace_url,
            now=now,
        )

        stats = {
            "claimed": 0,
            "skipped_blacklist": 0,
            "skipped_title_filter": 0,
            "scraped_success": 0,
            "retried": 0,
            "deadlettered": 0,
            "level1_upserts": 0,
            "scored_jsonl_writes": 0,
            "scored_pool_writes": 0,
        }
        errors: list[dict[str, Any]] = []

        try:
            for _ in range(max_items):
                item = self.queue.claim_next(
                    task_type="scrape.hit",
                    lane="scrape",
                    consumer_mode="native_scrape",
                    worker_name=self.worker_id,
                    lease_seconds=lease_seconds,
                    now=now,
                )
                if item is None:
                    break

                stats["claimed"] += 1
                hit = self.discovery.get_hit(item["subject_id"])
                if hit is None:
                    self.queue.mark_deadletter(item["_id"], error="search_hit_missing", now=now)
                    errors.append({"work_item_id": str(item["_id"]), "error": "search_hit_missing"})
                    stats["deadlettered"] += 1
                    continue

                if hit.get("scrape", {}).get("selector_handoff_status") == "written":
                    final_ref = dict(item.get("result_ref") or {})
                    final_ref["scrape_status"] = "succeeded"
                    final_ref["scored_jsonl_written"] = True
                    final_ref["level1_upserted"] = True
                    self.queue.mark_done(item["_id"], result_ref=final_ref, now=now)
                    tracer.record_stage(
                        "idempotent_done",
                        {
                            "work_item_id": str(item["_id"]),
                            "subject_id": item["subject_id"],
                            "correlation_id": item.get("correlation_id"),
                        },
                    )
                    continue

                span = tracer.start_work_item_span(
                    {
                        "work_item_id": str(item["_id"]),
                        "subject_id": item["subject_id"],
                        "correlation_id": item.get("correlation_id"),
                    }
                )

                lease_expires_at = item.get("lease_expires_at") or datetime.now(timezone.utc)
                self.discovery.mark_scrape_leased(
                    item["subject_id"],
                    run_id=run_context.run_id,
                    work_item_id=item["_id"],
                    lease_owner=self.worker_id,
                    lease_expires_at=lease_expires_at,
                    attempt_count=item.get("attempt_count", 0),
                    consumer_mode=item.get("consumer_mode", "native_scrape"),
                    now=now,
                )

                try:
                    payload = self._build_job_payload(item, hit)
                    tracer.record_stage("claim", {"work_item_id": str(item["_id"]), "payload_job_id": payload.get("job_id")})
                    outcome = evaluate_scrape_candidate(payload, pool=self._proxy_pool, use_proxy=self.use_proxy)

                    if isinstance(outcome, ScrapeSkipResult):
                        tracer.record_stage(
                            outcome.status,
                            {
                                "work_item_id": str(item["_id"]),
                                "reason": outcome.reason,
                                "title": payload.get("title"),
                            },
                        )
                        self.discovery.mark_scrape_skipped(
                            item["subject_id"],
                            run_id=run_context.run_id,
                            status=outcome.status,
                            reason=outcome.reason,
                            attempt_count=item.get("attempt_count", 0),
                            now=now,
                        )
                        self.queue.mark_done(
                            item["_id"],
                            result_ref={
                                **dict(item.get("result_ref") or {}),
                                "scrape_status": outcome.status,
                                "scored_jsonl_written": False,
                                "level1_upserted": False,
                            },
                            now=now,
                        )
                        stats[outcome.status] += 1
                        tracer.end_span(span, output={"status": outcome.status})
                        continue

                    assert isinstance(outcome, ScrapeSuccessResult)
                    scored = outcome.scored_job
                    tracer.record_stage("fetch", {"work_item_id": str(item["_id"]), "http_status": outcome.http_status, "used_proxy": outcome.used_proxy})
                    tracer.record_stage("parse", {"work_item_id": str(item["_id"]), "title": scored.get("title"), "company": scored.get("company")})
                    tracer.record_stage("score", {"work_item_id": str(item["_id"]), "score": scored.get("score"), "tier": scored.get("tier"), "detected_role": scored.get("detected_role")})

                    self.discovery.mark_scrape_succeeded(
                        item["subject_id"],
                        run_id=run_context.run_id,
                        attempt_count=item.get("attempt_count", 0),
                        http_status=outcome.http_status,
                        used_proxy=outcome.used_proxy,
                        scored_job=scored,
                        persist_selector_payload=self.flags.persist_selector_payload,
                        now=now,
                    )

                    compat = self._write_selector_compatibility(
                        hit=hit,
                        item=item,
                        scored=scored,
                        run_id=run_context.run_id,
                        tracer=tracer,
                        now=now,
                    )

                    self.discovery.mark_selector_handoff_written(
                        item["subject_id"],
                        run_id=run_context.run_id,
                        scored_jsonl_written=compat.scored_jsonl_written,
                        level1_upserted=compat.level1_upserted,
                        now=now,
                    )
                    final_ref = {
                        **dict(item.get("result_ref") or {}),
                        "scrape_status": "succeeded",
                        "scored_payload": {
                            "score": scored.get("score"),
                            "tier": scored.get("tier"),
                            "detected_role": scored.get("detected_role"),
                        },
                        "scored_jsonl_written": compat.scored_jsonl_written,
                        "level1_upserted": compat.level1_upserted,
                    }
                    self.queue.mark_done(item["_id"], result_ref=final_ref, now=now)
                    stats["scraped_success"] += 1
                    if compat.level1_upserted_now:
                        stats["level1_upserts"] += 1
                    if compat.scored_jsonl_written_now:
                        stats["scored_jsonl_writes"] += 1
                    tracer.end_span(span, output={"status": "succeeded", "score": scored.get("score"), "tier": scored.get("tier")})
                except CompatibilityWriteError as exc:
                    transition = self._handle_failure(
                        item=item,
                        hit_id=item["subject_id"],
                        run_id=run_context.run_id,
                        error_type="compatibility_write_failed",
                        error_message=str(exc),
                        disposition=FailureDisposition(retryable=True, error_type="compatibility_write_failed"),
                        now=now,
                        errors=errors,
                    )
                    self._persist_partial_result_ref(item["_id"], exc.partial, now=now)
                    if transition == "retried":
                        stats["retried"] += 1
                        self.discovery.mark_selector_handoff_failed(
                            item["subject_id"],
                            run_id=run_context.run_id,
                            error_type="compatibility_write_failed",
                            message=str(exc),
                            next_attempt_at=self._next_attempt_at(item, now=now),
                            now=now,
                        )
                        tracer.record_stage("retry_transition", {"work_item_id": str(item["_id"]), "error": str(exc)})
                        tracer.end_span(span, output={"status": "retry_pending", "error": str(exc)})
                    else:
                        stats["deadlettered"] += 1
                        tracer.record_stage("deadletter_transition", {"work_item_id": str(item["_id"]), "error": str(exc)})
                        tracer.end_span(span, output={"status": "deadletter", "error": str(exc)})
                except Exception as exc:
                    disposition = classify_scrape_exception(exc)
                    transition = self._handle_failure(
                        item=item,
                        hit_id=item["subject_id"],
                        run_id=run_context.run_id,
                        error_type=disposition.error_type,
                        error_message=str(exc),
                        disposition=disposition,
                        now=now,
                        errors=errors,
                    )
                    if transition == "retried":
                        stats["retried"] += 1
                        tracer.record_stage("retry_transition", {"work_item_id": str(item["_id"]), "error": str(exc), "error_type": disposition.error_type})
                        tracer.end_span(span, output={"status": "retry_pending", "error": str(exc)})
                    else:
                        stats["deadlettered"] += 1
                        tracer.record_stage("deadletter_transition", {"work_item_id": str(item["_id"]), "error": str(exc), "error_type": disposition.error_type})
                        tracer.end_span(span, output={"status": "deadletter", "error": str(exc)})

            self.discovery.finalize_scrape_run(run_context.run_id, status="completed", stats=stats, errors=errors, now=now)
            tracer.complete(output={"stats": stats, "errors": errors})
            return stats
        except Exception as exc:
            logger.exception("Native scrape worker failed: %s", exc)
            errors.append({"stage": "run", "message": str(exc)})
            self.discovery.finalize_scrape_run(run_context.run_id, status="failed", stats=stats, errors=errors, now=now)
            tracer.complete(output={"stats": stats, "errors": errors, "failed": True})
            raise

    def _build_job_payload(self, item: dict[str, Any], hit: dict[str, Any]) -> dict[str, Any]:
        payload = dict(item.get("payload") or {})
        payload.setdefault("job_id", hit.get("external_job_id"))
        payload.setdefault("title", hit.get("title", ""))
        payload.setdefault("company", hit.get("company", ""))
        payload.setdefault("location", hit.get("location", ""))
        payload.setdefault("job_url", hit.get("job_url") or hit.get("canonical_url") or "")
        payload.setdefault("search_profile", hit.get("search_profile", ""))
        payload.setdefault("search_region", hit.get("search_region", ""))
        payload.setdefault("source_cron", hit.get("source_cron", "hourly"))
        return payload

    def _write_selector_compatibility(
        self,
        *,
        hit: dict[str, Any],
        item: dict[str, Any],
        scored: dict[str, Any],
        run_id: str,
        tracer: ScrapeTracingSession,
        now: Optional[datetime],
    ) -> CompatibilityWriteResult:
        if not self.flags.selector_compat_mode:
            raise CompatibilityWriteError("SCOUT_SCRAPE_SELECTOR_COMPAT_MODE=false would starve selector")

        result = CompatibilityWriteResult()
        scrape_state = hit.get("scrape", {})
        work_item_ref = dict(item.get("result_ref") or {})

        if self.flags.write_level1:
            level1_done = bool(scrape_state.get("level1_upserted_at") or work_item_ref.get("level1_upserted"))
            if not level1_done:
                try:
                    upserted = upsert_level1_scored_job(self.level1, scored, source="scout_native_scrape", status="scored", now=now)
                    result.level1_upserted = True
                    result.level1_upserted_now = bool(upserted["upserted"])
                    self.discovery.mark_level1_upserted(item["subject_id"], run_id=run_id, now=now)
                    self.queue.patch_result_ref(
                        item["_id"],
                        patch={"level1_upserted": True, "level1_upserted_at": now or datetime.now(timezone.utc)},
                        now=now,
                    )
                    tracer.record_stage("level1_upsert", {"work_item_id": str(item["_id"]), "upserted": bool(upserted["upserted"])})
                except Exception as exc:  # pragma: no cover - tested via worker path
                    raise CompatibilityWriteError(f"level-1 upsert failed: {exc}", partial=result) from exc
            else:
                result.level1_upserted = True

        if self.flags.write_scored_jsonl:
            scored_done = bool(scrape_state.get("scored_jsonl_written_at") or work_item_ref.get("scored_jsonl_written"))
            if not scored_done:
                try:
                    if scored_contains_job(scored["job_id"]):
                        written = False
                    else:
                        written = append_scored_unique([scored]) > 0
                    result.scored_jsonl_written = True
                    result.scored_jsonl_written_now = written
                    self.discovery.mark_scored_jsonl_written(item["subject_id"], run_id=run_id, now=now)
                    self.queue.patch_result_ref(
                        item["_id"],
                        patch={"scored_jsonl_written": True, "scored_jsonl_written_at": now or datetime.now(timezone.utc)},
                        now=now,
                    )
                    tracer.record_stage("scored_jsonl_write", {"work_item_id": str(item["_id"]), "written_now": written})
                except Exception as exc:  # pragma: no cover - tested via worker path
                    raise CompatibilityWriteError(f"scored.jsonl write failed: {exc}", partial=result) from exc
            else:
                result.scored_jsonl_written = True

        return result

    def _persist_partial_result_ref(
        self,
        work_item_id,
        partial: CompatibilityWriteResult,
        *,
        now: Optional[datetime],
    ) -> None:
        patch: dict[str, Any] = {}
        if partial.level1_upserted:
            patch["level1_upserted"] = True
            patch["level1_upserted_at"] = now or datetime.now(timezone.utc)
        if partial.scored_jsonl_written:
            patch["scored_jsonl_written"] = True
            patch["scored_jsonl_written_at"] = now or datetime.now(timezone.utc)
        if patch:
            self.queue.patch_result_ref(work_item_id, patch=patch, now=now)

    def _handle_failure(
        self,
        *,
        item: dict[str, Any],
        hit_id: str,
        run_id: str,
        error_type: str,
        error_message: str,
        disposition: FailureDisposition,
        now: Optional[datetime],
        errors: list[dict[str, Any]],
    ) -> str:
        if disposition.retryable and item.get("attempt_count", 0) < item.get("max_attempts", 5):
            updated = self.queue.mark_failed(item["_id"], error=error_message, now=now)
            next_attempt_at = updated.get("available_at") or self._next_attempt_at(item, now=now)
            self.discovery.mark_scrape_retry_pending(
                hit_id,
                run_id=run_id,
                error_type=error_type,
                message=error_message,
                attempt_count=item.get("attempt_count", 0),
                next_attempt_at=next_attempt_at,
                now=now,
            )
            errors.append({"work_item_id": str(item["_id"]), "status": "retry_pending", "error_type": error_type, "message": error_message})
            return "retried"

        self.queue.mark_deadletter(item["_id"], error=error_message, now=now)
        self.discovery.mark_scrape_deadletter(
            hit_id,
            run_id=run_id,
            error_type=error_type,
            message=error_message,
            attempt_count=item.get("attempt_count", 0),
            now=now,
        )
        errors.append({"work_item_id": str(item["_id"]), "status": "deadletter", "error_type": error_type, "message": error_message})
        return "deadlettered"

    def _next_attempt_at(self, item: dict[str, Any], *, now: Optional[datetime]) -> datetime:
        base = now or datetime.now(timezone.utc)
        delay_seconds = min(300, 30 * max(1, item.get("attempt_count", 1)))
        return base + timedelta(seconds=delay_seconds)


def build_worker_id() -> str:
    """Build a unique native worker id."""
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
