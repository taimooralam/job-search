"""Bridge Mongo work-items into the legacy queue.jsonl scraper path."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pymongo.database import Database

from src.common.scout_queue import enqueue_jobs, get_queue_dir
from src.pipeline.discovery import SearchDiscoveryStore
from src.pipeline.queue import WorkItemQueue
from src.pipeline.tracing import emit_standalone_event

logger = logging.getLogger(__name__)


def build_worker_name() -> str:
    """Build a unique worker id for queue leases."""
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


class LegacyScrapeHandoffBridge:
    """Claims pending scrape work-items and writes them to queue.jsonl."""

    def __init__(
        self,
        db: Database,
        *,
        tracer: Optional[Any] = None,
        retry_delay_seconds: int = 30,
    ) -> None:
        self.db = db
        self.discovery = SearchDiscoveryStore(db)
        self.queue = WorkItemQueue(db)
        self.tracer = tracer
        self.retry_delay_seconds = retry_delay_seconds

    def run_once(
        self,
        *,
        max_items: int = 50,
        worker_name: Optional[str] = None,
        lease_seconds: int = 300,
        now: Optional[datetime] = None,
    ) -> dict[str, int]:
        """Process up to max_items pending legacy handoff items."""
        worker = worker_name or build_worker_name()
        processed = 0
        handed_off = 0
        failed = 0
        deadlettered = 0
        attempted_ids: set[str] = set()

        while processed < max_items:
            item = self.queue.claim_next(
                lane="scrape",
                consumer_mode="legacy_jsonl",
                worker_name=worker,
                lease_seconds=lease_seconds,
                exclude_ids=attempted_ids,
                now=now,
            )
            if item is None:
                break
            item_id = str(item["_id"])
            if item_id in attempted_ids:
                logger.warning("Skipping repeated claim of %s within the same bridge tick", item_id)
                break
            attempted_ids.add(item_id)

            processed += 1
            try:
                result_ref = self._handoff_item(item, now=now)
                self.queue.mark_done(item["_id"], result_ref=result_ref, now=now)
                self.discovery.mark_hit_handed_off(item["subject_id"], now=now)
                handed_off += 1
                if self.tracer is not None:
                    self.tracer.record_legacy_handoff(
                        {
                            "work_item_id": str(item["_id"]),
                            "subject_id": item["subject_id"],
                            "correlation_id": item.get("correlation_id"),
                            "result_ref": result_ref,
                        }
                    )
                else:
                    emit_standalone_event(
                        name="scout.legacy_handoff.bridge",
                        session_id=item.get("correlation_id") or f"bridge:{item_id}",
                        metadata={
                            "work_item_id": item_id,
                            "subject_id": item["subject_id"],
                            "correlation_id": item.get("correlation_id"),
                            "result_ref": result_ref,
                        },
                    )
            except Exception as exc:
                logger.warning("Legacy handoff failed for %s: %s", item.get("_id"), exc)
                updated = self.queue.mark_failed(
                    item["_id"],
                    error=str(exc),
                    retry_delay_seconds=self.retry_delay_seconds,
                    now=now,
                )
                self.discovery.mark_hit_failed(item["subject_id"], error=str(exc), now=now)
                if updated.get("status") == "deadletter":
                    deadlettered += 1
                else:
                    failed += 1
                emit_standalone_event(
                    name="scout.legacy_handoff.bridge_failed",
                    session_id=item.get("correlation_id") or f"bridge:{item_id}",
                    metadata={
                        "work_item_id": item_id,
                        "subject_id": item.get("subject_id"),
                        "correlation_id": item.get("correlation_id"),
                        "status": updated.get("status"),
                        "error": str(exc),
                    },
                )

        return {
            "processed": processed,
            "handed_off": handed_off,
            "failed": failed,
            "deadlettered": deadlettered,
        }

    def _handoff_item(
        self,
        item: dict[str, Any],
        *,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Write a compatible JSONL queue entry using the existing queue helper."""
        payload = dict(item.get("payload") or {})
        current_time = now or datetime.now(timezone.utc)
        jobs = [
            {
                "job_id": payload.get("job_id"),
                "title": payload.get("title", ""),
                "company": payload.get("company", ""),
                "location": payload.get("location", ""),
                "job_url": payload.get("job_url", ""),
                "_search_profile": payload.get("search_profile", ""),
            }
        ]
        written = enqueue_jobs(
            jobs,
            source_cron=payload.get("source_cron", "hourly"),
            search_profile=payload.get("search_profile", ""),
        )
        return {
            "legacy_queue_written": bool(written),
            "legacy_queue_written_at": current_time,
            "legacy_queue_path": str(get_queue_dir() / "queue.jsonl"),
            "legacy_queue_job_id": payload.get("job_id"),
            "legacy_queue_deduped": written == 0,
        }


def main() -> None:
    """CLI entrypoint for the host-side bridge worker."""
    parser = argparse.ArgumentParser(description="Bridge Mongo scrape work-items into queue.jsonl")
    parser.add_argument("--limit", type=int, default=50, help="Maximum items to hand off in one run")
    parser.add_argument("--lease-seconds", type=int, default=300, help="Lease duration for claimed work items")
    parser.add_argument("--retry-delay-seconds", type=int, default=30, help="Retry delay after bridge failures")
    args = parser.parse_args()

    from pymongo import MongoClient

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    mongodb_uri = os.getenv("MONGODB_URI")
    if not mongodb_uri:
        raise RuntimeError("MONGODB_URI not set")

    db = MongoClient(mongodb_uri)["jobs"]
    bridge = LegacyScrapeHandoffBridge(
        db,
        retry_delay_seconds=args.retry_delay_seconds,
    )
    result = bridge.run_once(max_items=args.limit, lease_seconds=args.lease_seconds)
    logger.info("Legacy handoff result: %s", result)


if __name__ == "__main__":
    main()
