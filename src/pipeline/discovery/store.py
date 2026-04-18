"""Mongo-backed discovery and scrape state for scout pipeline iterations 1 and 2."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Optional
from uuid import uuid4

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, TEXT
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from src.pipeline.selector_store import build_default_selection_state

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def build_run_id(now: Optional[datetime] = None) -> str:
    """Build a stable-ish search-run identifier."""
    timestamp = (now or utc_now()).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"searchrun:{timestamp}:{uuid4().hex[:8]}"


def build_scrape_run_id(now: Optional[datetime] = None) -> str:
    """Build a stable-ish scrape-run identifier."""
    timestamp = (now or utc_now()).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"scraperun:{timestamp}:{uuid4().hex[:8]}"


def canonicalize_job_url(job_url: Optional[str], external_job_id: Optional[str]) -> str:
    """Return a canonical LinkedIn job URL."""
    if job_url:
        return job_url.strip()
    if external_job_id:
        return f"https://www.linkedin.com/jobs/view/{external_job_id}/"
    return ""


def hash_canonical_url(canonical_url: str) -> Optional[str]:
    """Return a sparse hash value for canonical URLs."""
    if not canonical_url:
        return None
    return f"sha256:{sha256(canonical_url.encode('utf-8')).hexdigest()}"


def build_correlation_id(source: str, external_job_id: Optional[str]) -> str:
    """Build the stable hit-level correlation identifier."""
    if external_job_id:
        return f"hit:{source}:{external_job_id}"
    return f"hit:{source}:{uuid4().hex}"


def build_default_scrape_state() -> dict[str, Any]:
    """Return the default scrape subdocument for newly discovered hits."""
    return {
        "status": None,
        "consumer_mode": None,
        "work_item_id": None,
        "run_id": None,
        "attempt_count": 0,
        "last_attempt_at": None,
        "next_attempt_at": None,
        "lease_owner": None,
        "lease_expires_at": None,
        "completed_at": None,
        "last_error": None,
        "http_status": None,
        "used_proxy": None,
        "selector_payload": None,
        "score": None,
        "tier": None,
        "detected_role": None,
        "seniority_level": None,
        "employment_type": None,
        "job_function": None,
        "industries": None,
        "work_mode": None,
        "scored_at": None,
        "selector_handoff_status": None,
        "selector_handoff_at": None,
        "scored_jsonl_written_at": None,
        "level1_upserted_at": None,
    }


@dataclass(frozen=True)
class SearchRunContext:
    """Identifiers for one search run."""

    run_id: str
    langfuse_session_id: str
    started_at: datetime


@dataclass(frozen=True)
class ScrapeRunContext:
    """Identifiers for one scrape worker run."""

    run_id: str
    langfuse_session_id: str
    started_at: datetime
    worker_id: str


@dataclass(frozen=True)
class SearchHitUpsertResult:
    """Result of upserting one scout discovery hit."""

    hit_id: ObjectId
    inserted: bool
    document: dict[str, Any]


class SearchDiscoveryStore:
    """Discovery, scrape, and run collections used by the scout pipeline."""

    def __init__(self, db: Database):
        self.db = db
        self.search_runs: Collection = db["search_runs"]
        self.search_hits: Collection = db["scout_search_hits"]
        self.scrape_runs: Collection = db["scrape_runs"]

    def ensure_indexes(self) -> None:
        """Create the indexes needed for discovery and scrape state lookups."""
        self.search_runs.create_index([("run_id", ASCENDING)], unique=True, name="run_id_unique")
        self.search_runs.create_index([("started_at", DESCENDING)], name="started_at_desc")
        self.search_runs.create_index(
            [("status", ASCENDING), ("started_at", DESCENDING)],
            name="status_started_at",
        )

        self.scrape_runs.create_index([("run_id", ASCENDING)], unique=True, name="run_id_unique")
        self.scrape_runs.create_index([("started_at", DESCENDING)], name="started_at_desc")
        self.scrape_runs.create_index(
            [("status", ASCENDING), ("started_at", DESCENDING)],
            name="status_started_at",
        )
        self.scrape_runs.create_index([("worker_id", ASCENDING), ("started_at", DESCENDING)], name="worker_started_at")

        self.search_hits.create_index(
            [("source", ASCENDING), ("external_job_id", ASCENDING)],
            unique=True,
            name="source_external_job_id_unique",
        )
        self.search_hits.create_index(
            [("canonical_url_hash", ASCENDING)],
            unique=True,
            sparse=True,
            name="canonical_url_hash_unique",
        )
        self.search_hits.create_index(
            [("hit_status", ASCENDING), ("last_seen_at", DESCENDING)],
            name="hit_status_last_seen_at",
        )
        self.search_hits.create_index([("last_seen_at", DESCENDING)], name="last_seen_at_desc")
        self.search_hits.create_index([("first_seen_at", DESCENDING)], name="first_seen_at_desc")
        self.search_hits.create_index(
            [("search_profile", ASCENDING), ("last_seen_at", DESCENDING)],
            name="search_profile_last_seen_at",
        )
        self.search_hits.create_index(
            [("search_region", ASCENDING), ("last_seen_at", DESCENDING)],
            name="search_region_last_seen_at",
        )
        self.search_hits.create_index([("run_id", ASCENDING)], name="run_id")
        self.search_hits.create_index([("correlation_id", ASCENDING)], name="correlation_id")
        self.search_hits.create_index([("scrape.status", ASCENDING), ("updated_at", DESCENDING)], name="scrape_status_updated_at")
        self.search_hits.create_index(
            [("scrape.status", ASCENDING), ("last_seen_at", DESCENDING)],
            name="scrape_status_last_seen_at",
        )
        self.search_hits.create_index(
            [("scrape.selector_handoff_status", ASCENDING), ("updated_at", DESCENDING)],
            name="selector_handoff_status_updated_at",
        )
        self.search_hits.create_index([("scrape.work_item_id", ASCENDING)], sparse=True, name="scrape_work_item_id")
        self.search_hits.create_index(
            [
                ("title", TEXT),
                ("company", TEXT),
                ("location", TEXT),
                ("scrape.detected_role", TEXT),
            ],
            name="discovery_search_text",
            default_language="english",
        )

    def create_search_run(
        self,
        *,
        trigger_mode: str,
        command_mode: str,
        region_filter: Optional[str],
        profile_filter: Optional[str],
        time_filter: str,
        langfuse_session_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> SearchRunContext:
        """Insert a running search run summary."""
        started_at = now or utc_now()
        run_id = build_run_id(started_at)
        session_id = langfuse_session_id or run_id
        document = {
            "run_id": run_id,
            "trigger_mode": trigger_mode,
            "command_mode": command_mode,
            "region_filter": region_filter,
            "profile_filter": profile_filter,
            "time_filter": time_filter,
            "status": "running",
            "started_at": started_at,
            "completed_at": None,
            "stats": {
                "raw_found": 0,
                "after_blacklist": 0,
                "after_db_dedupe": 0,
                "hits_upserted": 0,
                "work_items_created": 0,
                "legacy_handoffs_created": 0,
            },
            "errors": [],
            "langfuse_session_id": session_id,
            "langfuse_trace_id": None,
            "langfuse_trace_url": None,
            "created_at": started_at,
            "updated_at": started_at,
        }
        self.search_runs.insert_one(document)
        return SearchRunContext(run_id=run_id, langfuse_session_id=session_id, started_at=started_at)

    def update_search_run(
        self,
        run_id: str,
        *,
        stats: Optional[dict[str, int]] = None,
        errors: Optional[list[dict[str, Any]]] = None,
        status: Optional[str] = None,
        completed_at: Optional[datetime] = None,
        langfuse_trace_id: Optional[str] = None,
        langfuse_trace_url: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Update run progress or final status."""
        update: dict[str, Any] = {"updated_at": now or utc_now()}
        if stats is not None:
            update["stats"] = stats
        if errors is not None:
            update["errors"] = errors
        if status is not None:
            update["status"] = status
        if completed_at is not None:
            update["completed_at"] = completed_at
        if langfuse_trace_id is not None:
            update["langfuse_trace_id"] = langfuse_trace_id
        if langfuse_trace_url is not None:
            update["langfuse_trace_url"] = langfuse_trace_url
        self.search_runs.update_one({"run_id": run_id}, {"$set": update})

    def finalize_search_run(
        self,
        run_id: str,
        *,
        status: str,
        stats: dict[str, int],
        errors: Optional[list[dict[str, Any]]] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Mark a search run as completed or failed."""
        completed_at = now or utc_now()
        self.update_search_run(
            run_id,
            stats=stats,
            errors=errors or [],
            status=status,
            completed_at=completed_at,
            now=completed_at,
        )

    def create_scrape_run(
        self,
        *,
        worker_id: str,
        trigger_mode: str,
        langfuse_session_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> ScrapeRunContext:
        """Insert a running scrape worker tick summary."""
        started_at = now or utc_now()
        run_id = build_scrape_run_id(started_at)
        session_id = langfuse_session_id or run_id
        document = {
            "run_id": run_id,
            "worker_id": worker_id,
            "trigger_mode": trigger_mode,
            "status": "running",
            "started_at": started_at,
            "completed_at": None,
            "stats": {
                "claimed": 0,
                "skipped_blacklist": 0,
                "skipped_title_filter": 0,
                "scraped_success": 0,
                "retried": 0,
                "deadlettered": 0,
                "level1_upserts": 0,
                "scored_jsonl_writes": 0,
                "scored_pool_writes": 0,
            },
            "errors": [],
            "langfuse_session_id": session_id,
            "langfuse_trace_id": None,
            "langfuse_trace_url": None,
            "created_at": started_at,
            "updated_at": started_at,
        }
        self.scrape_runs.insert_one(document)
        return ScrapeRunContext(
            run_id=run_id,
            langfuse_session_id=session_id,
            started_at=started_at,
            worker_id=worker_id,
        )

    def update_scrape_run(
        self,
        run_id: str,
        *,
        stats: Optional[dict[str, int]] = None,
        errors: Optional[list[dict[str, Any]]] = None,
        status: Optional[str] = None,
        completed_at: Optional[datetime] = None,
        langfuse_trace_id: Optional[str] = None,
        langfuse_trace_url: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Update scrape run progress or final status."""
        update: dict[str, Any] = {"updated_at": now or utc_now()}
        if stats is not None:
            update["stats"] = stats
        if errors is not None:
            update["errors"] = errors
        if status is not None:
            update["status"] = status
        if completed_at is not None:
            update["completed_at"] = completed_at
        if langfuse_trace_id is not None:
            update["langfuse_trace_id"] = langfuse_trace_id
        if langfuse_trace_url is not None:
            update["langfuse_trace_url"] = langfuse_trace_url
        self.scrape_runs.update_one({"run_id": run_id}, {"$set": update})

    def finalize_scrape_run(
        self,
        run_id: str,
        *,
        status: str,
        stats: dict[str, int],
        errors: Optional[list[dict[str, Any]]] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Mark a scrape run as completed or failed."""
        completed_at = now or utc_now()
        self.update_scrape_run(
            run_id,
            stats=stats,
            errors=errors or [],
            status=status,
            completed_at=completed_at,
            now=completed_at,
        )

    def upsert_search_hit(
        self,
        *,
        source: str,
        external_job_id: Optional[str],
        job_url: Optional[str],
        title: Optional[str],
        company: Optional[str],
        location: Optional[str],
        search_profile: Optional[str],
        search_region: Optional[str],
        source_cron: str,
        run_id: str,
        correlation_id: Optional[str],
        langfuse_session_id: Optional[str],
        scout_metadata: Optional[dict[str, Any]],
        raw_search_payload: Optional[dict[str, Any]],
        now: Optional[datetime] = None,
    ) -> SearchHitUpsertResult:
        """Upsert one search hit and increment its times_seen counter."""
        current_time = now or utc_now()
        canonical_url = canonicalize_job_url(job_url, external_job_id)
        canonical_url_hash = hash_canonical_url(canonical_url)
        correlation = correlation_id or build_correlation_id(source, external_job_id)
        session_id = langfuse_session_id or correlation

        if external_job_id:
            identity_filter: dict[str, Any] = {"source": source, "external_job_id": external_job_id}
        elif canonical_url_hash:
            identity_filter = {"canonical_url_hash": canonical_url_hash}
        else:
            raise ValueError("Search hit requires external_job_id or canonical_url_hash")

        inserted = self.search_hits.find_one(identity_filter, {"_id": 1}) is None
        update = {
            "$set": {
                "source": source,
                "external_job_id": external_job_id,
                "canonical_url": canonical_url,
                "canonical_url_hash": canonical_url_hash,
                "job_url": canonical_url,
                "title": title,
                "company": company,
                "location": location,
                "search_profile": search_profile,
                "search_region": search_region,
                "source_cron": source_cron,
                "run_id": run_id,
                "correlation_id": correlation,
                "langfuse_session_id": session_id,
                "trace.job_correlation_id": correlation,
                "trace.search_run_id": run_id,
                "scout_metadata": scout_metadata or {},
                "raw_search_payload": raw_search_payload or {},
                "updated_at": current_time,
                "last_seen_at": current_time,
            },
            "$setOnInsert": {
                "hit_status": "discovered",
                "first_seen_at": current_time,
                "last_queued_at": None,
                "last_legacy_handoff_at": None,
                "scrape": build_default_scrape_state(),
                "selection": build_default_selection_state(),
                "created_at": current_time,
            },
            "$inc": {
                "times_seen": 1,
            },
        }

        try:
            self.search_hits.update_one(identity_filter, update, upsert=True)
        except DuplicateKeyError:
            inserted = False
            fallback_filter = identity_filter if not canonical_url_hash else {"canonical_url_hash": canonical_url_hash}
            self.search_hits.update_one(fallback_filter, update, upsert=True)

        document = self.search_hits.find_one(identity_filter)
        if document is None and canonical_url_hash:
            document = self.search_hits.find_one({"canonical_url_hash": canonical_url_hash})
        if document is None:
            raise RuntimeError("Failed to fetch scout_search_hits document after upsert")

        return SearchHitUpsertResult(hit_id=document["_id"], inserted=inserted, document=document)

    def get_hit(self, hit_id: ObjectId | str) -> Optional[dict[str, Any]]:
        """Return one hit by id."""
        return self.search_hits.find_one({"_id": _coerce_object_id(hit_id)})

    def mark_hit_queued(
        self,
        hit_id: ObjectId | str,
        *,
        consumer_mode: str = "legacy_jsonl",
        work_item_id: Optional[ObjectId | str] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Mark a hit as queued for downstream scrape consumption."""
        current_time = now or utc_now()
        update: dict[str, Any] = {
            "hit_status": "queued_for_scrape",
            "last_queued_at": current_time,
            "updated_at": current_time,
            "scrape.status": "pending",
            "scrape.consumer_mode": consumer_mode,
            "scrape.last_error": None,
        }
        if work_item_id is not None:
            update["scrape.work_item_id"] = str(work_item_id)
        self.search_hits.update_one({"_id": _coerce_object_id(hit_id)}, {"$set": update})

    def mark_hit_handed_off(
        self,
        hit_id: ObjectId | str,
        *,
        now: Optional[datetime] = None,
    ) -> None:
        """Mark a hit as handed to the iteration-1 legacy scraper queue."""
        current_time = now or utc_now()
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": {
                    "hit_status": "handed_to_legacy_scraper",
                    "last_legacy_handoff_at": current_time,
                    "updated_at": current_time,
                }
            },
        )

    def mark_hit_failed(
        self,
        hit_id: ObjectId | str,
        *,
        error: str,
        now: Optional[datetime] = None,
    ) -> None:
        """Mark a hit as failed for iteration-1 legacy-handoff visibility."""
        current_time = now or utc_now()
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": {
                    "hit_status": "failed",
                    "updated_at": current_time,
                    "scout_metadata.last_error": error,
                }
            },
        )

    def mark_scrape_leased(
        self,
        hit_id: ObjectId | str,
        *,
        run_id: str,
        work_item_id: ObjectId | str,
        lease_owner: str,
        lease_expires_at: datetime,
        attempt_count: int,
        consumer_mode: str,
        now: Optional[datetime] = None,
    ) -> None:
        """Mark scrape execution as leased by a native worker."""
        current_time = now or utc_now()
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": {
                    "hit_status": "leased_for_scrape",
                    "updated_at": current_time,
                    "scrape.status": "leased",
                    "scrape.run_id": run_id,
                    "trace.scrape_run_id": run_id,
                    "scrape.work_item_id": str(work_item_id),
                    "scrape.consumer_mode": consumer_mode,
                    "scrape.attempt_count": attempt_count,
                    "scrape.last_attempt_at": current_time,
                    "scrape.lease_owner": lease_owner,
                    "scrape.lease_expires_at": lease_expires_at,
                    "scrape.last_error": None,
                }
            },
        )

    def mark_scrape_skipped(
        self,
        hit_id: ObjectId | str,
        *,
        run_id: str,
        status: str,
        reason: str,
        attempt_count: int,
        now: Optional[datetime] = None,
    ) -> None:
        """Mark a scrape hit as skipped before fetch."""
        current_time = now or utc_now()
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": {
                    "hit_status": status,
                    "updated_at": current_time,
                    "scrape.status": status,
                    "scrape.run_id": run_id,
                    "trace.scrape_run_id": run_id,
                    "scrape.attempt_count": attempt_count,
                    "scrape.last_attempt_at": current_time,
                    "scrape.completed_at": current_time,
                    "scrape.lease_owner": None,
                    "scrape.lease_expires_at": None,
                    "scrape.last_error": {"type": status, "message": reason},
                    "scrape.selector_handoff_status": "not_applicable",
                    "scrape.selector_handoff_at": current_time,
                }
            },
        )

    def mark_scrape_succeeded(
        self,
        hit_id: ObjectId | str,
        *,
        run_id: str,
        attempt_count: int,
        http_status: int,
        used_proxy: bool,
        scored_job: dict[str, Any],
        persist_selector_payload: bool = True,
        now: Optional[datetime] = None,
    ) -> None:
        """Persist authoritative scrape success metadata."""
        current_time = now or utc_now()
        update = {
            "hit_status": "scraped",
            "updated_at": current_time,
            "scrape.status": "succeeded",
            "scrape.run_id": run_id,
            "scrape.attempt_count": attempt_count,
            "scrape.last_attempt_at": current_time,
            "scrape.completed_at": current_time,
            "scrape.lease_owner": None,
            "scrape.lease_expires_at": None,
            "scrape.last_error": None,
            "scrape.http_status": http_status,
            "scrape.used_proxy": used_proxy,
            "scrape.score": scored_job.get("score"),
            "scrape.tier": scored_job.get("tier"),
            "scrape.detected_role": scored_job.get("detected_role"),
            "scrape.seniority_level": scored_job.get("seniority_level"),
            "scrape.employment_type": scored_job.get("employment_type"),
            "scrape.job_function": scored_job.get("job_function"),
            "scrape.industries": scored_job.get("industries"),
            "scrape.work_mode": scored_job.get("work_mode"),
            "scrape.scored_at": scored_job.get("scored_at"),
            "scrape.selector_handoff_status": "pending",
        }
        if persist_selector_payload:
            update["scrape.selector_payload"] = {
                "job_id": scored_job.get("job_id"),
                "title": scored_job.get("title"),
                "company": scored_job.get("company"),
                "location": scored_job.get("location"),
                "job_url": scored_job.get("job_url"),
                "description": scored_job.get("description"),
                "score": scored_job.get("score"),
                "tier": scored_job.get("tier"),
                "detected_role": scored_job.get("detected_role"),
                "seniority_level": scored_job.get("seniority_level"),
                "employment_type": scored_job.get("employment_type"),
                "job_function": scored_job.get("job_function"),
                "industries": scored_job.get("industries"),
                "work_mode": scored_job.get("work_mode"),
                "search_profile": scored_job.get("search_profile"),
                "search_region": scored_job.get("search_region"),
                "source_cron": scored_job.get("source_cron"),
                "breakdown": scored_job.get("breakdown"),
                "scored_at": scored_job.get("scored_at"),
            }
            update.update(
                {
                    "selection.main.status": "pending",
                    "selection.main.decision": "none",
                    "selection.main.selector_run_id": None,
                    "selection.main.reason": None,
                    "selection.main.rank": None,
                    "selection.main.selected_at": None,
                    "selection.main.level2_job_id": None,
                    "selection.main.level1_upserted_at": None,
                    "selection.pool.status": "not_applicable",
                    "selection.pool.pooled_at": None,
                    "selection.pool.expires_at": None,
                    "selection.profiles": {},
                }
            )

        self.search_hits.update_one({"_id": _coerce_object_id(hit_id)}, {"$set": update})

    def mark_selector_handoff_written(
        self,
        hit_id: ObjectId | str,
        *,
        run_id: str,
        scored_jsonl_written: bool,
        level1_upserted: bool,
        now: Optional[datetime] = None,
    ) -> None:
        """Mark selector-compatible writes as completed."""
        current_time = now or utc_now()
        update: dict[str, Any] = {
            "hit_status": "selector_handoff_written",
            "updated_at": current_time,
            "scrape.run_id": run_id,
            "trace.scrape_run_id": run_id,
            "scrape.selector_handoff_status": "written",
            "scrape.selector_handoff_at": current_time,
        }
        if scored_jsonl_written:
            update["scrape.scored_jsonl_written_at"] = current_time
        if level1_upserted:
            update["scrape.level1_upserted_at"] = current_time
        self.search_hits.update_one({"_id": _coerce_object_id(hit_id)}, {"$set": update})

    def mark_level1_upserted(
        self,
        hit_id: ObjectId | str,
        *,
        run_id: str,
        now: Optional[datetime] = None,
    ) -> None:
        """Persist successful level-1 compatibility staging."""
        current_time = now or utc_now()
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": {
                    "updated_at": current_time,
                    "scrape.run_id": run_id,
                    "trace.scrape_run_id": run_id,
                    "scrape.level1_upserted_at": current_time,
                }
            },
        )

    def mark_scored_jsonl_written(
        self,
        hit_id: ObjectId | str,
        *,
        run_id: str,
        now: Optional[datetime] = None,
    ) -> None:
        """Persist successful scored.jsonl selector handoff staging."""
        current_time = now or utc_now()
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": {
                    "updated_at": current_time,
                    "scrape.run_id": run_id,
                    "trace.scrape_run_id": run_id,
                    "scrape.scored_jsonl_written_at": current_time,
                }
            },
        )

    def mark_selector_handoff_failed(
        self,
        hit_id: ObjectId | str,
        *,
        run_id: str,
        error_type: str,
        message: str,
        next_attempt_at: Optional[datetime],
        now: Optional[datetime] = None,
    ) -> None:
        """Mark compatibility writes as failed and awaiting retry."""
        current_time = now or utc_now()
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": {
                    "hit_status": "retry_pending",
                    "updated_at": current_time,
                    "scrape.run_id": run_id,
                    "scrape.status": "retry_pending",
                    "scrape.next_attempt_at": next_attempt_at,
                    "scrape.selector_handoff_status": "failed",
                    "scrape.last_error": {
                        "type": error_type,
                        "message": message,
                    },
                    "scrape.lease_owner": None,
                    "scrape.lease_expires_at": None,
                }
            },
        )

    def mark_scrape_retry_pending(
        self,
        hit_id: ObjectId | str,
        *,
        run_id: str,
        error_type: str,
        message: str,
        attempt_count: int,
        next_attempt_at: datetime,
        now: Optional[datetime] = None,
    ) -> None:
        """Mark a scrape failure as retryable."""
        current_time = now or utc_now()
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": {
                    "hit_status": "retry_pending",
                    "updated_at": current_time,
                    "scrape.status": "retry_pending",
                    "scrape.run_id": run_id,
                    "scrape.attempt_count": attempt_count,
                    "scrape.last_attempt_at": current_time,
                    "scrape.next_attempt_at": next_attempt_at,
                    "scrape.lease_owner": None,
                    "scrape.lease_expires_at": None,
                    "scrape.last_error": {
                        "type": error_type,
                        "message": message,
                    },
                }
            },
        )

    def mark_scrape_deadletter(
        self,
        hit_id: ObjectId | str,
        *,
        run_id: str,
        error_type: str,
        message: str,
        attempt_count: int,
        now: Optional[datetime] = None,
    ) -> None:
        """Mark a scrape failure as exhausted and deadlettered."""
        current_time = now or utc_now()
        self.search_hits.update_one(
            {"_id": _coerce_object_id(hit_id)},
            {
                "$set": {
                    "hit_status": "deadletter",
                    "updated_at": current_time,
                    "scrape.status": "deadletter",
                    "scrape.run_id": run_id,
                    "scrape.attempt_count": attempt_count,
                    "scrape.last_attempt_at": current_time,
                    "scrape.completed_at": current_time,
                    "scrape.lease_owner": None,
                    "scrape.lease_expires_at": None,
                    "scrape.last_error": {
                        "type": error_type,
                        "message": message,
                    },
                }
            },
        )


def _coerce_object_id(value: ObjectId | str) -> ObjectId:
    """Convert string ids back to ObjectId where possible."""
    if isinstance(value, ObjectId):
        return value
    return ObjectId(str(value))
