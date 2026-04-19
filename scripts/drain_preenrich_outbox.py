"""Drain the legacy Redis preenrich outbox and resolve stranded lifecycle docs."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pymongo import MongoClient

from src.preenrich.outbox import DEADLETTER_KEY, STREAM_KEY, outbox_consumer_tick

from scripts.backfill_preenrich_states import _cv_ready_at, _derive_stage_states_from_legacy, utc_now


REPORT_DIR = Path("reports")


def finalize_or_mark_stranded(
    db: Any,
    *,
    now: Optional[datetime] = None,
    dry_run: bool = True,
) -> dict[str, int]:
    """Finalize ready/queued/running docs to cv_ready or stale after the outbox drain."""
    current_time = now or utc_now()
    stats = {"cv_ready": 0, "stale": 0}
    for doc in db["level-2"].find({"lifecycle": {"$in": ["ready", "queued", "running"]}}):
        pre = doc.get("pre_enrichment") or {}
        stage_states = pre.get("stage_states") or _derive_stage_states_from_legacy(pre)
        cv_ready_at = _cv_ready_at(stage_states)
        if cv_ready_at is not None:
            update = {"lifecycle": "cv_ready", "pre_enrichment.cv_ready_at": cv_ready_at, "updated_at": current_time}
            stats["cv_ready"] += 1
        else:
            update = {"lifecycle": "stale", "updated_at": current_time}
            stats["stale"] += 1
        if not dry_run:
            db["level-2"].update_one({"_id": doc["_id"]}, {"$set": update})
    return stats


def drain_legacy_outbox(
    db: Any,
    redis: Any,
    *,
    runner_client: Any,
    dry_run: bool = True,
    deadline_seconds: int = 1800,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Drain the Redis outbox until quiescent, then resolve stranded lifecycle docs."""
    current_time = now or utc_now()
    deadline = time.monotonic() + deadline_seconds
    stats = {"acked": 0, "retried": 0, "deadlettered": 0, "ticks": 0}
    if not dry_run:
        while time.monotonic() < deadline:
            tick = outbox_consumer_tick(redis, runner_client)
            stats["ticks"] += 1
            for key in ("acked", "retried", "deadlettered"):
                stats[key] += tick[key]
            if tick == {"acked": 0, "retried": 0, "deadlettered": 0}:
                break
    stats["stranded"] = finalize_or_mark_stranded(db, now=current_time, dry_run=dry_run)
    stats["archived_deadletter"] = _archive_deadletter(redis, current_time, dry_run=dry_run)
    return stats


def _archive_deadletter(redis: Any, now: datetime, *, dry_run: bool) -> str:
    if not hasattr(redis, "xrange"):
        return ""
    entries = redis.xrange(DEADLETTER_KEY)
    report_path = REPORT_DIR / f"preenrich-deadletter-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(entries, indent=2, default=str))
    if not dry_run and hasattr(redis, "delete"):
        redis.delete(DEADLETTER_KEY)
    return str(report_path)


def _get_db() -> Any:
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    return MongoClient(uri)["jobs"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Drain the legacy Redis preenrich outbox")
    parser.add_argument("--apply", action="store_true", help="Apply changes instead of dry-run")
    parser.add_argument("--deadline-seconds", type=int, default=1800)
    args = parser.parse_args()
    raise RuntimeError("Use this module with a real Redis client and runner client from the VPS environment")


if __name__ == "__main__":
    main()
