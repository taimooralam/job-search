"""Shared scout search pipeline for iteration 1 discovery cutover."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pymongo import MongoClient

SKILL_ROOT = Path(__file__).resolve().parents[3] / "n8n" / "skills" / "scout-jobs"
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.scout_linkedin_jobs import REGION_CONFIGS, SEARCH_PROFILES, search_jobs  # noqa: E402
from src.common.blacklist import filter_blacklisted  # noqa: E402
from src.common.dedupe import generate_dedupe_key  # noqa: E402
from src.common.proxy_pool import ProxyPool  # noqa: E402
from src.common.scout_queue import enqueue_jobs  # noqa: E402
from src.pipeline.discovery import SearchDiscoveryStore, build_correlation_id  # noqa: E402
from src.pipeline.legacy_scrape_handoff import LegacyScrapeHandoffBridge  # noqa: E402
from src.pipeline.queue import WorkItemQueue  # noqa: E402
from src.pipeline.tracing import SearchTracingSession  # noqa: E402

logger = logging.getLogger("scout_cron")

DEFAULT_TIME_FILTER = "r43200"  # last 12 hours
MAX_PAGES = 1

SEARCH_COMBOS = [
    ("asia_pacific", False, True, None),
    ("asia_pacific", True, True, None),
    ("mena", False, True, None),
    ("mena", True, True, None),
    ("pakistan", False, True, None),
    ("pakistan", True, True, None),
    ("eea", False, True, None),
    ("eea", True, True, None),
    ("gcc_priority", False, False, None),
    ("gcc_priority", True, False, None),
    ("gcc_priority", False, False, "ai_leadership"),
    ("gcc_priority", True, False, "ai_leadership"),
]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser shared by both scout cron entrypoints."""
    parser = argparse.ArgumentParser(description="LinkedIn Scout Cron (Search-Only)")
    parser.add_argument("--dry-run", action="store_true", help="Search and dedupe but do not write downstream state")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="Filter to a region key (eea, mena, asia_pacific, pakistan, gcc_priority, emea)",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Filter to a specific search profile",
    )
    parser.add_argument("--remote", action="store_true", help="Add remote-only filter in direct mode")
    parser.add_argument("--limit", type=int, default=None, metavar="N", help="Stop after N downstream jobs")
    parser.add_argument(
        "--time-window",
        type=str,
        default=None,
        metavar="WINDOW",
        help="LinkedIn lookback window such as 30m, 1h, 12h, or 1d",
    )
    parser.add_argument("--no-proxy", action="store_true", help="Skip proxy initialization")
    parser.add_argument(
        "--location",
        type=str,
        default=None,
        metavar="COUNTRY",
        help="Search a single country and override --region",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Run the discovery search pipeline."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    time_filter = _parse_time_window(args.time_window) if args.time_window else DEFAULT_TIME_FILTER
    flags = SearchFeatureFlags.from_env()
    flags.validate(args)

    logger.info("=" * 60)
    logger.info("Scout cron started at %s", datetime.utcnow().isoformat())
    logger.info(
        "Feature flags: write_hits=%s enqueue_work_items=%s legacy_handoff=%s direct_jsonl=%s consumer_mode=%s disable_bridge=%s",
        flags.write_search_hits_to_mongo,
        flags.enqueue_work_items,
        flags.enable_legacy_scrape_handoff,
        flags.direct_jsonl_enqueue,
        flags.search_scrape_consumer_mode,
        flags.disable_iteration1_legacy_handoff_bridge,
    )
    logger.info("=" * 60)

    db = get_db()
    discovery = SearchDiscoveryStore(db)
    discovery.ensure_indexes()

    queue = WorkItemQueue(db)
    queue.ensure_indexes()

    trigger_mode = "manual" if _is_manual_invocation(args) else "cron"
    command_mode = "direct" if _is_direct_mode(args) else "full"
    run_context = discovery.create_search_run(
        trigger_mode=trigger_mode,
        command_mode=command_mode,
        region_filter=args.location or args.region,
        profile_filter=args.profile,
        time_filter=time_filter,
    )
    tracer = SearchTracingSession(
        run_id=run_context.run_id,
        session_id=run_context.langfuse_session_id,
        metadata={
            "trigger_mode": trigger_mode,
            "command_mode": command_mode,
            "region_filter": args.location or args.region,
            "profile_filter": args.profile,
            "time_filter": time_filter,
        },
    )
    discovery.update_search_run(
        run_context.run_id,
        langfuse_trace_id=tracer.trace_id,
        langfuse_trace_url=tracer.trace_url,
    )

    stats = {
        "raw_found": 0,
        "after_blacklist": 0,
        "after_db_dedupe": 0,
        "hits_upserted": 0,
        "work_items_created": 0,
        "legacy_handoffs_created": 0,
    }
    errors: list[dict[str, Any]] = []
    direct_jsonl_enqueued = 0

    try:
        seen_job_ids: set[str] = set()
        proxy_pool = _init_proxy_pool(args.no_proxy)
        requests = _build_search_requests(args)

        for request_ctx in requests:
            if args.limit is not None and _downstream_count(stats, direct_jsonl_enqueued, flags) >= args.limit:
                logger.info("Reached --limit %s, stopping early", args.limit)
                break

            combo_span = tracer.start_combo_span(request_ctx.as_trace_metadata())
            jobs = search_jobs(
                keywords_list=request_ctx.keywords,
                time_filter=time_filter,
                regions=[request_ctx.region],
                max_pages=MAX_PAGES,
                limit=args.limit if command_mode == "direct" and args.limit else 0,
                few_applicants=request_ctx.few_applicants,
                remote_only=request_ctx.remote_only,
                proxy_pool=proxy_pool,
            )

            unique_jobs: list[dict[str, Any]] = []
            for job in jobs:
                job_id = job.get("job_id")
                if not job_id or job_id in seen_job_ids:
                    continue
                seen_job_ids.add(job_id)
                job["_search_profile"] = request_ctx.profile_name
                unique_jobs.append(job)

            stats["raw_found"] += len(unique_jobs)
            filtered_jobs = filter_blacklisted(unique_jobs)
            stats["after_blacklist"] += len(filtered_jobs)

            if args.limit is not None:
                remaining = args.limit - _downstream_count(stats, direct_jsonl_enqueued, flags)
                filtered_jobs = filtered_jobs[: max(remaining, 0)]

            new_jobs = dedupe_against_db(filtered_jobs, db)
            stats["after_db_dedupe"] += len(new_jobs)

            logger.info(
                "Search pass %s: %s raw, %s after blacklist, %s after DB dedupe",
                request_ctx.label,
                len(unique_jobs),
                len(filtered_jobs),
                len(new_jobs),
            )

            if args.dry_run:
                direct_jsonl_enqueued += len(new_jobs)
                tracer.end_span(
                    combo_span,
                    output={
                        "raw_found": len(unique_jobs),
                        "after_blacklist": len(filtered_jobs),
                        "after_db_dedupe": len(new_jobs),
                        "dry_run": True,
                    },
                )
                continue

            if flags.direct_jsonl_enqueue:
                direct_jsonl_enqueued += enqueue_jobs(new_jobs, source_cron=request_ctx.source_cron)

            if flags.write_search_hits_to_mongo:
                for job in new_jobs:
                    scout_metadata = {
                        "command_mode": command_mode,
                        "few_applicants": request_ctx.few_applicants,
                        "remote_only": request_ctx.remote_only,
                        "location_override": args.location,
                        "keywords": request_ctx.keywords,
                    }
                    correlation_id = build_correlation_id("linkedin", job.get("job_id"))
                    hit_result = discovery.upsert_search_hit(
                        source="linkedin",
                        external_job_id=job.get("job_id"),
                        job_url=job.get("job_url"),
                        title=job.get("title"),
                        company=job.get("company"),
                        location=job.get("location"),
                        search_profile=request_ctx.profile_name,
                        search_region=request_ctx.region_label,
                        source_cron=request_ctx.source_cron,
                        run_id=run_context.run_id,
                        correlation_id=correlation_id,
                        langfuse_session_id=run_context.langfuse_session_id,
                        scout_metadata=scout_metadata,
                        raw_search_payload=job,
                    )
                    stats["hits_upserted"] += 1
                    tracer.record_hit_event(
                        "new" if hit_result.inserted else "updated",
                        {
                            "hit_id": str(hit_result.hit_id),
                            "correlation_id": correlation_id,
                            "search_profile": request_ctx.profile_name,
                            "search_region": request_ctx.region_label,
                            "title": job.get("title"),
                            "company": job.get("company"),
                        },
                    )

                    if flags.enqueue_work_items:
                        enqueue_result = queue.enqueue(
                            task_type="scrape.hit",
                            lane="scrape",
                            consumer_mode=flags.search_scrape_consumer_mode,
                            subject_type="search_hit",
                            subject_id=hit_result.hit_id,
                            priority=100,
                            available_at=None,
                            max_attempts=5,
                            idempotency_key=f"scrape.hit:linkedin:{job.get('job_id')}",
                            correlation_id=correlation_id,
                            payload={
                                "job_id": job.get("job_id"),
                                "title": job.get("title", ""),
                                "company": job.get("company", ""),
                                "location": job.get("location", ""),
                                "job_url": job.get("job_url", ""),
                                "search_profile": request_ctx.profile_name,
                                "source_cron": request_ctx.source_cron,
                            },
                        )
                        if enqueue_result.created:
                            stats["work_items_created"] += 1
                        if enqueue_result.created or enqueue_result.document.get("status") in {"pending", "failed", "leased"}:
                            discovery.mark_hit_queued(
                                hit_result.hit_id,
                                consumer_mode=flags.search_scrape_consumer_mode,
                                work_item_id=enqueue_result.document.get("_id"),
                            )
                        tracer.record_enqueue_event(
                            {
                                "work_item_id": str(enqueue_result.document.get("_id")),
                                "created": enqueue_result.created,
                                "subject_id": str(hit_result.hit_id),
                                "correlation_id": correlation_id,
                                "consumer_mode": flags.search_scrape_consumer_mode,
                            }
                        )

            tracer.end_span(
                combo_span,
                output={
                    "raw_found": len(unique_jobs),
                    "after_blacklist": len(filtered_jobs),
                    "after_db_dedupe": len(new_jobs),
                    "direct_jsonl_enqueued": direct_jsonl_enqueued,
                },
            )
            discovery.update_search_run(run_context.run_id, stats=stats)

        if (
            not args.dry_run
            and flags.enqueue_work_items
            and flags.enable_legacy_scrape_handoff
            and not flags.direct_jsonl_enqueue
            and flags.search_scrape_consumer_mode == "legacy_jsonl"
            and not flags.disable_iteration1_legacy_handoff_bridge
        ):
            bridge = LegacyScrapeHandoffBridge(db, tracer=tracer)
            bridge_result = bridge.run_once(max_items=max(1, stats["work_items_created"]))
            stats["legacy_handoffs_created"] += bridge_result["handed_off"]
            if bridge_result["failed"] or bridge_result["deadlettered"]:
                errors.append(
                    {
                        "stage": "legacy_handoff",
                        "failed": bridge_result["failed"],
                        "deadlettered": bridge_result["deadlettered"],
                    }
                )

        discovery.finalize_search_run(
            run_context.run_id,
            status="completed",
            stats=stats,
            errors=errors,
        )
        tracer.complete(output={"stats": stats, "errors": errors, "direct_jsonl_enqueued": direct_jsonl_enqueued})
        _log_summary(args, stats, direct_jsonl_enqueued, flags)
        return 0
    except Exception as exc:
        logger.exception("Scout search failed: %s", exc)
        errors.append({"stage": "run", "message": str(exc)})
        discovery.finalize_search_run(
            run_context.run_id,
            status="failed",
            stats=stats,
            errors=errors,
        )
        tracer.complete(output={"stats": stats, "errors": errors, "failed": True})
        raise


def get_db():
    """Get MongoDB database connection."""
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set in environment")
    client = MongoClient(uri)
    return client["jobs"]


def dedupe_against_db(jobs: list[dict[str, Any]], db) -> list[dict[str, Any]]:
    """Remove jobs that already exist in MongoDB (checks both level-1 and level-2)."""
    if not jobs:
        return []

    dedupe_keys = []
    for job in jobs:
        dedupe_keys.append(generate_dedupe_key("linkedin_scout", source_id=job["job_id"]))
        dedupe_keys.append(generate_dedupe_key("linkedin_import", source_id=job["job_id"]))

    existing = set()
    for coll_name in ("level-2", "level-1"):
        cursor = db[coll_name].find({"dedupeKey": {"$in": dedupe_keys}}, {"dedupeKey": 1})
        for doc in cursor:
            existing.add(doc["dedupeKey"])

    new_jobs = []
    for job in jobs:
        key_scout = generate_dedupe_key("linkedin_scout", source_id=job["job_id"])
        key_import = generate_dedupe_key("linkedin_import", source_id=job["job_id"])
        if key_scout not in existing and key_import not in existing:
            new_jobs.append(job)

    return new_jobs


@dataclass(frozen=True)
class SearchRequest:
    """One region/profile search invocation."""

    region: str
    region_label: str
    profile_name: str
    keywords: list[str]
    remote_only: bool
    few_applicants: bool
    source_cron: str = "hourly"

    @property
    def label(self) -> str:
        return (
            f"profile={self.profile_name} region={self.region_label} "
            f"remote={self.remote_only} few_applicants={self.few_applicants}"
        )

    def as_trace_metadata(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "region": self.region,
            "region_label": self.region_label,
            "remote_only": self.remote_only,
            "few_applicants": self.few_applicants,
            "source_cron": self.source_cron,
        }


@dataclass(frozen=True)
class SearchFeatureFlags:
    """Rollout flags for the iteration-1 cutover."""

    write_search_hits_to_mongo: bool
    enqueue_work_items: bool
    enable_legacy_scrape_handoff: bool
    direct_jsonl_enqueue: bool
    search_scrape_consumer_mode: str
    disable_iteration1_legacy_handoff_bridge: bool

    @classmethod
    def from_env(cls) -> "SearchFeatureFlags":
        """Load feature flags with local-safe defaults.

        Local/dev defaults preserve the legacy path:
        - direct JSONL enqueue stays on
        - Mongo discovery/work-items/bridge stay off

        Expected production cutover values for iteration 1:
        - SCOUT_WRITE_SEARCH_HITS_TO_MONGO=true
        - SCOUT_ENQUEUE_WORK_ITEMS=true
        - SCOUT_ENABLE_LEGACY_SCRAPE_HANDOFF=true
        - SCOUT_DIRECT_JSONL_ENQUEUE=false
        """
        return cls(
            write_search_hits_to_mongo=_env_flag("SCOUT_WRITE_SEARCH_HITS_TO_MONGO", False),
            enqueue_work_items=_env_flag("SCOUT_ENQUEUE_WORK_ITEMS", False),
            enable_legacy_scrape_handoff=_env_flag("SCOUT_ENABLE_LEGACY_SCRAPE_HANDOFF", False),
            direct_jsonl_enqueue=_env_flag("SCOUT_DIRECT_JSONL_ENQUEUE", True),
            search_scrape_consumer_mode=os.getenv("SCOUT_SEARCH_SCRAPE_CONSUMER_MODE", "legacy_jsonl").strip() or "legacy_jsonl",
            disable_iteration1_legacy_handoff_bridge=_env_flag("SCOUT_DISABLE_ITERATION1_LEGACY_HANDOFF_BRIDGE", False),
        )

    def validate(self, args: argparse.Namespace) -> None:
        """Reject unsafe combinations that would starve the legacy scraper."""
        if args.dry_run:
            return
        if self.search_scrape_consumer_mode not in {"legacy_jsonl", "native_scrape"}:
            raise RuntimeError(
                "SCOUT_SEARCH_SCRAPE_CONSUMER_MODE must be one of legacy_jsonl or native_scrape"
            )
        if self.enqueue_work_items and not self.write_search_hits_to_mongo:
            raise RuntimeError(
                "SCOUT_ENQUEUE_WORK_ITEMS requires SCOUT_WRITE_SEARCH_HITS_TO_MONGO=true"
            )
        if self.direct_jsonl_enqueue:
            return

        if not (self.write_search_hits_to_mongo and self.enqueue_work_items):
            raise RuntimeError(
                "Unsafe scout flag combination: disabling direct JSONL enqueue requires "
                "Mongo hits and work-items to be enabled."
            )

        if self.search_scrape_consumer_mode == "legacy_jsonl":
            if self.disable_iteration1_legacy_handoff_bridge or not self.enable_legacy_scrape_handoff:
                raise RuntimeError(
                    "legacy_jsonl consumer mode requires the iteration-1 legacy handoff bridge to remain enabled"
                )
        elif not self.disable_iteration1_legacy_handoff_bridge and self.enable_legacy_scrape_handoff:
            logger.info(
                "Legacy handoff bridge remains enabled, but search is emitting native_scrape work-items only."
            )


def _build_search_requests(args: argparse.Namespace) -> list[SearchRequest]:
    """Build the concrete search requests for the current invocation."""
    requests: list[SearchRequest] = []
    if _is_direct_mode(args):
        profile_name = args.profile or "ai_core"
        keywords = SEARCH_PROFILES.get(profile_name, SEARCH_PROFILES["ai_core"])
        if args.location:
            region = f"_single_{args.location.replace(' ', '_').lower()}"
            REGION_CONFIGS[region] = {"location": args.location}
            region_label = args.location
        else:
            region = args.region or "eea"
            region_label = region
        requests.append(
            SearchRequest(
                region=region,
                region_label=region_label,
                profile_name=profile_name,
                keywords=keywords,
                remote_only=args.remote,
                few_applicants=not args.remote,
            )
        )
        return requests

    for region, remote_only, few_applicants, profile_override in SEARCH_COMBOS:
        if args.region and region != args.region:
            continue
        if profile_override is not None:
            profiles_to_search = {profile_override: SEARCH_PROFILES[profile_override]}
        else:
            profiles_to_search = SEARCH_PROFILES

        for profile_name, keywords in profiles_to_search.items():
            if args.profile and profile_name != args.profile:
                continue
            requests.append(
                SearchRequest(
                    region=region,
                    region_label=region,
                    profile_name=profile_name,
                    keywords=keywords,
                    remote_only=remote_only,
                    few_applicants=few_applicants,
                )
            )

    return requests


def _init_proxy_pool(no_proxy: bool) -> Optional[ProxyPool]:
    """Initialize the proxy pool if enabled."""
    if no_proxy:
        logger.info("Proxy pool skipped (--no-proxy)")
        return None
    try:
        pool = ProxyPool()
        working = pool.initialize()
        if working >= 1:
            logger.info("Proxy pool ready: %s working proxies", working)
            return pool
        logger.warning("Proxy pool returned 0 working proxies — using direct requests")
    except Exception as exc:
        logger.warning("Proxy pool initialization failed: %s — using direct requests", exc)
    return None


def _parse_time_window(value: str) -> str:
    """Convert human-readable time window to LinkedIn f_TPR value."""
    import re as _re

    match = _re.match(r"^(\d+)(m|h|d)$", value.strip().lower())
    if not match:
        raise ValueError(f"Invalid time window '{value}'. Use 30m, 1h, 12h, or 1d")
    number, unit = int(match.group(1)), match.group(2)
    seconds = number * {"m": 60, "h": 3600, "d": 86400}[unit]
    return f"r{seconds}"


def _downstream_count(
    stats: dict[str, int],
    direct_jsonl_enqueued: int,
    flags: SearchFeatureFlags,
) -> int:
    """Return the count that should honor --limit for this run."""
    if flags.direct_jsonl_enqueue:
        return direct_jsonl_enqueued
    return stats["work_items_created"]


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment flag."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_direct_mode(args: argparse.Namespace) -> bool:
    """Return True when the invocation targets a specific region/profile."""
    return bool(args.location or args.region or args.profile)


def _is_manual_invocation(args: argparse.Namespace) -> bool:
    """Return True when the CLI options indicate a manual run."""
    return bool(
        args.dry_run
        or args.verbose
        or args.region
        or args.profile
        or args.remote
        or args.limit is not None
        or args.time_window
        or args.no_proxy
        or args.location
    )


def _log_summary(
    args: argparse.Namespace,
    stats: dict[str, int],
    direct_jsonl_enqueued: int,
    flags: SearchFeatureFlags,
) -> None:
    """Log the final search summary."""
    logger.info("=" * 60)
    logger.info("Scout Cron Summary")
    logger.info("  Raw found:              %s", stats["raw_found"])
    logger.info("  After blacklist:        %s", stats["after_blacklist"])
    logger.info("  After DB dedupe:        %s", stats["after_db_dedupe"])
    logger.info("  Hits upserted:          %s", stats["hits_upserted"])
    logger.info("  Work items created:     %s", stats["work_items_created"])
    logger.info("  Legacy handoffs:        %s", stats["legacy_handoffs_created"])
    if flags.direct_jsonl_enqueue or args.dry_run:
        logger.info("  Direct JSONL enqueued:  %s", direct_jsonl_enqueued)
    logger.info("=" * 60)
