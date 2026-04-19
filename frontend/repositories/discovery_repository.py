"""Repository for discovery and native scrape pipeline visibility."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo import DESCENDING, MongoClient
from pymongo.errors import OperationFailure

try:
    from src.common.dedupe import generate_dedupe_key as _generate_dedupe_key
except ImportError:
    def _normalize_for_dedupe(value: Optional[str]) -> str:
        return re.sub(r"[^a-z0-9]", "", (value or "").lower())

    def _generate_dedupe_key(
        source: str,
        source_id: Optional[str] = None,
        company: Optional[str] = None,
        title: Optional[str] = None,
        location: Optional[str] = None,
    ) -> str:
        if source_id:
            return f"{source}|{source_id}"
        return "|".join(
            [
                source,
                _normalize_for_dedupe(company),
                _normalize_for_dedupe(title),
                _normalize_for_dedupe(location),
            ]
        )

try:
    from src.pipeline.discovery import SearchDiscoveryStore
    from src.pipeline.queue import WorkItemQueue
    from src.pipeline.selector_store import SelectorStore
except ImportError:
    SearchDiscoveryStore = None
    WorkItemQueue = None
    SelectorStore = None

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_HOURS = 24
DEFAULT_RESULTS_LIMIT = 25
MAX_RESULTS_LIMIT = 100


class DiscoveryRepository:
    """Access search, scrape, and queue state for the discovery dashboard."""

    _instance: Optional["DiscoveryRepository"] = None

    def __init__(self, mongodb_uri: str, database: str = "jobs"):
        self.client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[database]
        self.search_runs = self.db["search_runs"]
        self.search_hits = self.db["scout_search_hits"]
        self.scrape_runs = self.db["scrape_runs"]
        self.selector_runs = self.db["selector_runs"]
        self.work_items = self.db["work_items"]
        self.level2 = self.db["level-2"]
        self._ensure_indexes()

    @classmethod
    def get_instance(cls) -> "DiscoveryRepository":
        if cls._instance is None:
            uri = (
                os.getenv("DISCOVERY_MONGODB_URI")
                or os.getenv("VPS_MONGODB_URI")
                or os.getenv("MONGODB_URI")
            )
            if not uri:
                raise ValueError(
                    "DiscoveryRepository requires DISCOVERY_MONGODB_URI, VPS_MONGODB_URI, or MONGODB_URI"
                )
            cls._instance = cls(uri)
            logger.info("Initialized DiscoveryRepository")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        if cls._instance is not None:
            cls._instance.client.close()
            cls._instance = None

    def _ensure_indexes(self) -> None:
        """Ensure the discovery dashboard's hot query indexes exist.

        On the VPS/backend code path we reuse the pipeline stores. On Vercel we
        cannot rely on importing the full backend package layout, so we skip
        index management and rely on the authoritative backend/VPS workers to
        own Mongo index creation.
        """
        if SearchDiscoveryStore and WorkItemQueue and SelectorStore:
            SearchDiscoveryStore(self.db).ensure_indexes()
            WorkItemQueue(self.db).ensure_indexes()
            SelectorStore(self.db).ensure_indexes()
            return
        logger.info("Skipping discovery dashboard index management in frontend-only runtime")

    def get_stats(self, since: datetime) -> dict[str, int]:
        """Return top-level stats for the discovery dashboard."""
        return {
            "search_runs_last_24h": self.search_runs.count_documents({"started_at": {"$gte": since}}),
            "discoveries_last_24h": self.search_hits.count_documents({"first_seen_at": {"$gte": since}}),
            "pending_scrapes": self.search_hits.count_documents({"scrape.status": {"$in": ["pending", "leased", "retry_pending"]}}),
            "selector_handoffs_written": self.search_hits.count_documents({"scrape.selector_handoff_status": "written"}),
            "selector_runs_last_24h": self.selector_runs.count_documents({"scheduled_for": {"$gte": since}}),
            "pool_available": self.search_hits.count_documents({"selection.pool.status": "available"}),
            "selected_for_preenrich": self.level2.count_documents({"lifecycle": "selected"}),
            "failures_deadletters": self.search_hits.count_documents({"scrape.status": {"$in": ["retry_pending", "deadletter"]}}),
        }

    def get_pipeline_heartbeat(
        self,
        *,
        now: Optional[datetime] = None,
        activity_window_minutes: int = 15,
    ) -> dict[str, Any]:
        """Return stage-level heartbeat cards for iterations 1/2/3."""
        current_time = now or datetime.now(timezone.utc)
        activity_since = current_time - timedelta(minutes=activity_window_minutes)
        selector_since = current_time - timedelta(hours=8)

        latest_search_run = self.search_runs.find_one(sort=[("started_at", DESCENDING)])
        latest_scrape_run = self.scrape_runs.find_one(sort=[("started_at", DESCENDING)])
        latest_selector_run = self.selector_runs.find_one(sort=[("scheduled_for", DESCENDING)])

        latest_selected_doc = self.level2.find_one(
            {"selected_at": {"$ne": None}},
            sort=[("selected_at", DESCENDING)],
            projection={"selected_at": 1, "lifecycle": 1},
        )

        iteration_1 = {
            "title": "Iteration 1",
            "subtitle": "Search -> hits -> scrape work-items",
            "last_seen_at": latest_search_run.get("started_at") if latest_search_run else None,
            "primary_metric": self.search_hits.count_documents({"first_seen_at": {"$gte": activity_since}}),
            "primary_label": f"new hits in {activity_window_minutes}m",
            "secondary_metric": self.work_items.count_documents(
                {"task_type": "scrape.hit", "created_at": {"$gte": activity_since}}
            ),
            "secondary_label": f"scrape work-items in {activity_window_minutes}m",
            "state": _heartbeat_state(
                last_seen_at=latest_search_run.get("started_at") if latest_search_run else None,
                ok_within=timedelta(minutes=30),
                warn_within=timedelta(hours=2),
            ),
        }
        iteration_1["reason"] = self._build_reason(
            last_seen_at=iteration_1["last_seen_at"],
            primary_metric=iteration_1["primary_metric"],
            primary_label=iteration_1["primary_label"],
        )

        iteration_2 = {
            "title": "Iteration 2",
            "subtitle": "Native scrape execution",
            "last_seen_at": latest_scrape_run.get("started_at") if latest_scrape_run else None,
            "primary_metric": self.search_hits.count_documents(
                {
                    "scrape.status": "succeeded",
                    "scrape.completed_at": {"$gte": activity_since},
                }
            ),
            "primary_label": f"scrape successes in {activity_window_minutes}m",
            "secondary_metric": self.work_items.count_documents(
                {
                    "task_type": "scrape.hit",
                    "consumer_mode": "native_scrape",
                    "status": {"$in": ["pending", "failed"]},
                }
            ),
            "secondary_label": "scrape queue open",
            "state": _heartbeat_state(
                last_seen_at=latest_scrape_run.get("started_at") if latest_scrape_run else None,
                ok_within=timedelta(minutes=20),
                warn_within=timedelta(hours=1),
            ),
        }
        iteration_2["reason"] = self._build_reason(
            last_seen_at=iteration_2["last_seen_at"],
            primary_metric=iteration_2["primary_metric"],
            primary_label=iteration_2["primary_label"],
        )

        iteration_3 = {
            "title": "Iteration 3",
            "subtitle": "Selector runs -> level-2 handoff",
            "last_seen_at": latest_selector_run.get("scheduled_for") if latest_selector_run else None,
            "primary_metric": self.selector_runs.count_documents({"scheduled_for": {"$gte": selector_since}}),
            "primary_label": "selector runs in 8h",
            "secondary_metric": self.level2.count_documents({"selected_at": {"$gte": selector_since}}),
            "secondary_label": "selected docs in 8h",
            "state": _heartbeat_state(
                last_seen_at=latest_selector_run.get("scheduled_for") if latest_selector_run else None,
                ok_within=timedelta(hours=8),
                warn_within=timedelta(hours=24),
            ),
            "selected_lifecycle": latest_selected_doc.get("lifecycle") if latest_selected_doc else None,
            "latest_selected_at": latest_selected_doc.get("selected_at") if latest_selected_doc else None,
        }
        iteration_3["reason"] = self._build_reason(
            last_seen_at=iteration_3["last_seen_at"],
            primary_metric=iteration_3["primary_metric"],
            primary_label=iteration_3["primary_label"],
        )

        return {
            "cards": [iteration_1, iteration_2, iteration_3],
            "summary": {
                "pending_scrapes": self.search_hits.count_documents(
                    {"scrape.status": {"$in": ["pending", "leased", "retry_pending"]}}
                ),
                "pool_available": self.search_hits.count_documents({"selection.pool.status": "available"}),
                "selected_ready": self.level2.count_documents({"lifecycle": "selected"}),
                "failures": self.search_hits.count_documents(
                    {"scrape.status": {"$in": ["retry_pending", "deadletter"]}}
                ) + self.selector_runs.count_documents({"status": {"$in": ["failed", "deadletter"]}}),
            },
        }

    def get_hits(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent discovery hits with their related work-item state."""
        hits = list(
            self.search_hits.find(
                {},
                projection=_results_projection(),
            ).sort([("last_seen_at", DESCENDING), ("_id", DESCENDING)]).limit(limit)
        )
        for hit in hits:
            hit["related_work_item"] = self.get_related_work_item(str(hit["_id"]))
            hit["level2_state"] = self.get_level2_state(hit)
            hit["display_status"] = self._compute_display_status(hit)
        return hits

    def search_hits_page(
        self,
        *,
        query_text: Optional[str] = None,
        window: str = "24h",
        profile: Optional[str] = None,
        region: Optional[str] = None,
        scrape_status: Optional[str] = None,
        main_decision: Optional[str] = None,
        pool_status: Optional[str] = None,
        failures_only: bool = False,
        cursor: Optional[str] = None,
        limit: int = DEFAULT_RESULTS_LIMIT,
    ) -> dict[str, Any]:
        """Return a filtered, paginated hit list for the dashboard."""
        effective_limit = max(1, min(limit, MAX_RESULTS_LIMIT))
        query = self._build_hits_query(
            query_text=query_text,
            window=window,
            profile=profile,
            region=region,
            scrape_status=scrape_status,
            main_decision=main_decision,
            pool_status=pool_status,
            failures_only=failures_only,
            cursor=cursor,
        )
        projection = _results_projection()
        try:
            results = list(
                self.search_hits.find(query, projection=projection)
                .sort([("last_seen_at", DESCENDING), ("_id", DESCENDING)])
                .limit(effective_limit + 1)
            )
        except OperationFailure:
            fallback_query = dict(query)
            search_value = _extract_text_search(fallback_query)
            if search_value:
                _remove_text_search(fallback_query)
                fallback_query["$and"] = fallback_query.get("$and", [])
                fallback_query["$and"].append({"$or": _regex_search(search_value)})
            results = list(
                self.search_hits.find(fallback_query, projection=projection)
                .sort([("last_seen_at", DESCENDING), ("_id", DESCENDING)])
                .limit(effective_limit + 1)
            )
        has_more = len(results) > effective_limit
        hits = results[:effective_limit]
        for hit in hits:
            hit["related_work_item"] = self.get_related_work_item(str(hit["_id"]))
            hit["level2_state"] = self.get_level2_state(hit)
            hit["display_status"] = self._compute_display_status(hit)

        next_cursor = None
        if has_more and hits:
            last_hit = hits[-1]
            next_cursor = _encode_cursor(last_hit.get("last_seen_at"), last_hit["_id"])

        return {
            "hits": hits,
            "page": {
                "limit": effective_limit,
                "has_more": has_more,
                "next_cursor": next_cursor,
                "cursor": cursor,
            },
            "filters": {
                "q": query_text or "",
                "window": window,
                "profile": profile or "",
                "region": region or "",
                "scrape_status": scrape_status or "",
                "main_decision": main_decision or "",
                "pool_status": pool_status or "",
                "failures_only": failures_only,
            },
        }

    def get_recent_search_runs(self, limit: int = 8) -> list[dict[str, Any]]:
        """Return recent search runs."""
        return list(
            self.search_runs.find(
                {},
                projection={
                    "command_mode": 1,
                    "status": 1,
                    "started_at": 1,
                    "region_filter": 1,
                    "profile_filter": 1,
                    "stats": 1,
                    "langfuse_session_id": 1,
                    "langfuse_trace_url": 1,
                },
            ).sort([("started_at", DESCENDING)]).limit(limit)
        )

    def get_recent_scrape_runs(self, limit: int = 8) -> list[dict[str, Any]]:
        """Return recent scrape worker runs."""
        return list(
            self.scrape_runs.find(
                {},
                projection={
                    "worker_id": 1,
                    "status": 1,
                    "started_at": 1,
                    "trigger_mode": 1,
                    "stats": 1,
                    "langfuse_session_id": 1,
                    "langfuse_trace_url": 1,
                },
            ).sort([("started_at", DESCENDING)]).limit(limit)
        )

    def get_recent_selector_runs(self, limit: int = 8) -> list[dict[str, Any]]:
        """Return recent native selector runs."""
        return list(
            self.selector_runs.find(
                {},
                projection={
                    "run_kind": 1,
                    "profile_name": 1,
                    "status": 1,
                    "scheduled_for": 1,
                    "trigger_mode": 1,
                    "stats": 1,
                    "langfuse_session_id": 1,
                    "langfuse_trace_url": 1,
                },
            ).sort([("scheduled_for", DESCENDING)]).limit(limit)
        )

    def get_recent_failures(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return recent scrape and selector failures."""
        scrape_failures = list(
            self.search_hits.find(
                {"scrape.status": {"$in": ["retry_pending", "deadletter"]}},
                {
                    "title": 1,
                    "company": 1,
                    "scrape.status": 1,
                    "scrape.run_id": 1,
                    "scrape.last_error": 1,
                    "scrape.attempt_count": 1,
                    "correlation_id": 1,
                    "updated_at": 1,
                },
            )
            .sort([("updated_at", DESCENDING)])
            .limit(limit)
        )
        selector_failures = list(
            self.selector_runs.find(
                {"status": {"$in": ["failed", "deadletter"]}},
                {
                    "run_id": 1,
                    "run_kind": 1,
                    "profile_name": 1,
                    "status": 1,
                    "errors": 1,
                    "updated_at": 1,
                    "langfuse_trace_url": 1,
                },
            )
            .sort([("updated_at", DESCENDING)])
            .limit(limit)
        )
        normalized = []
        for item in scrape_failures:
            trace_url = None
            scrape_run_id = ((item.get("scrape") or {}).get("run_id"))
            if scrape_run_id:
                scrape_run = self.scrape_runs.find_one({"run_id": scrape_run_id}, {"langfuse_trace_url": 1})
                trace_url = scrape_run.get("langfuse_trace_url") if scrape_run else None
            normalized.append({"kind": "scrape", "langfuse_trace_url": trace_url, **item})
        normalized += [
            {"kind": "selector", **item}
            for item in selector_failures
        ]
        normalized.sort(
            key=lambda item: (item.get("updated_at") or datetime(1970, 1, 1, tzinfo=timezone.utc)).timestamp(),
            reverse=True,
        )
        return normalized[:limit]

    def get_queue_snapshot(self) -> dict[str, Any]:
        """Return queue counts grouped by scrape consumer mode."""
        def _counts(base_query: dict[str, Any], extra: dict[str, Any]) -> dict[str, int]:
            counts = {
                status: self.work_items.count_documents({**base_query, **extra, "status": status})
                for status in ("pending", "leased", "done", "failed", "deadletter")
            }
            counts["total"] = sum(counts.values())
            return counts

        native = _counts({"task_type": "scrape.hit"}, {"consumer_mode": "native_scrape"})
        legacy = _counts({"task_type": "scrape.hit"}, {"consumer_mode": "legacy_jsonl"})
        selector = _counts({"lane": "selector"}, {"consumer_mode": "native_selector"})
        return {
            "native": native,
            "legacy": legacy,
            "selector": selector,
            "all": _counts({}, {}),
        }

    def get_hit_detail(self, hit_id: str) -> Optional[dict[str, Any]]:
        """Return one hit plus its related work-item."""
        document = self.search_hits.find_one({"_id": ObjectId(hit_id)})
        if document is None:
            return None
        document["related_work_item"] = self.get_related_work_item(hit_id)
        document["level2_state"] = self.get_level2_state(document)
        document["display_status"] = self._compute_display_status(document)
        document["trace_links"] = self.get_trace_links_for_hit(document)
        document["run_links"] = self.get_run_links_for_hit(document)
        return document

    def get_hit_peek(self, hit_id: str) -> Optional[dict[str, Any]]:
        """Return a compact peek view for one hit."""
        document = self.search_hits.find_one({"_id": ObjectId(hit_id)}, projection=_peek_projection())
        if document is None:
            return None
        document["level2_state"] = self.get_level2_state(document)
        document["display_status"] = self._compute_display_status(document)
        document["trace_links"] = self.get_trace_links_for_hit(document)
        return document

    def get_related_work_item(self, hit_id: str) -> Optional[dict[str, Any]]:
        """Return the most relevant work-item for one search hit."""
        return self.work_items.find_one(
            {
                "subject_type": "search_hit",
                "subject_id": hit_id,
            },
            sort=[("updated_at", DESCENDING)],
        )

    def get_level2_state(self, hit: dict[str, Any]) -> dict[str, Any]:
        """Return linked level-2 visibility for one discovery hit."""
        selection = hit.get("selection") or {}
        main = selection.get("main") or {}
        profile_states = selection.get("profiles") or {}

        level2_doc = None
        if main.get("level2_job_id"):
            try:
                level2_doc = self.level2.find_one({"_id": ObjectId(main["level2_job_id"])})
            except Exception:
                level2_doc = None

        if level2_doc is None and hit.get("external_job_id"):
            dedupe_key = _generate_dedupe_key("linkedin_scout", source_id=hit["external_job_id"])
            level2_doc = self.level2.find_one({"dedupeKey": dedupe_key})

        profile_links: dict[str, dict[str, Any]] = {}
        for profile_name, state in profile_states.items():
            if not isinstance(state, dict):
                continue
            level2_job_id = state.get("level2_job_id")
            if not level2_job_id:
                continue
            try:
                document = self.level2.find_one({"_id": ObjectId(level2_job_id)})
            except Exception:
                document = None
            if document:
                profile_links[profile_name] = {
                    "id": str(document["_id"]),
                    "lifecycle": document.get("lifecycle"),
                }

        return {
            "exists": level2_doc is not None,
            "id": str(level2_doc["_id"]) if level2_doc is not None else None,
            "lifecycle": level2_doc.get("lifecycle") if level2_doc else None,
            "status": level2_doc.get("status") if level2_doc else None,
            "selected_at": level2_doc.get("selected_at") if level2_doc else None,
            "preenrich_claimed": bool(level2_doc and level2_doc.get("lifecycle") == "preenriching"),
            "profile_links": profile_links,
        }

    def get_langfuse_panel(self) -> dict[str, Any]:
        """Return optional Langfuse metadata for the UI."""
        latest_search_run = self.search_runs.find_one(sort=[("started_at", DESCENDING)])
        latest_scrape_run = self.scrape_runs.find_one(sort=[("started_at", DESCENDING)])
        latest_selector_run = self.selector_runs.find_one(sort=[("scheduled_for", DESCENDING)])
        latest_hit = self.search_hits.find_one(sort=[("last_seen_at", DESCENDING)])
        return {
            "public_url": os.getenv("LANGFUSE_PUBLIC_URL"),
            "latest_search_run_session_id": latest_search_run.get("langfuse_session_id") if latest_search_run else None,
            "latest_scrape_run_session_id": latest_scrape_run.get("langfuse_session_id") if latest_scrape_run else None,
            "latest_selector_run_session_id": latest_selector_run.get("langfuse_session_id") if latest_selector_run else None,
            "latest_hit_session_id": latest_hit.get("langfuse_session_id") if latest_hit else None,
            "latest_search_trace_url": latest_search_run.get("langfuse_trace_url") if latest_search_run else None,
            "latest_scrape_trace_url": latest_scrape_run.get("langfuse_trace_url") if latest_scrape_run else None,
            "latest_selector_trace_url": latest_selector_run.get("langfuse_trace_url") if latest_selector_run else None,
        }

    def get_trace_links_for_hit(self, hit: dict[str, Any]) -> dict[str, Optional[str]]:
        """Return trace/session links derivable from the hit's related runs."""
        trace_links = {
            "search_trace_url": None,
            "scrape_trace_url": None,
            "selector_trace_url": None,
            "langfuse_session_id": hit.get("langfuse_session_id"),
        }
        run_links = self.get_run_links_for_hit(hit)
        if run_links.get("search_run"):
            trace_links["search_trace_url"] = run_links["search_run"].get("langfuse_trace_url")
        if run_links.get("scrape_run"):
            trace_links["scrape_trace_url"] = run_links["scrape_run"].get("langfuse_trace_url")
        if run_links.get("selector_run"):
            trace_links["selector_trace_url"] = run_links["selector_run"].get("langfuse_trace_url")
        return trace_links

    def get_run_links_for_hit(self, hit: dict[str, Any]) -> dict[str, Any]:
        """Return related search/scrape/selector run summaries for one hit."""
        selection = hit.get("selection") or {}
        main = selection.get("main") or {}
        search_run = self.search_runs.find_one(
            {"run_id": hit.get("run_id")},
            projection={"run_id": 1, "started_at": 1, "langfuse_session_id": 1, "langfuse_trace_url": 1},
        ) if hit.get("run_id") else None
        scrape_run = self.scrape_runs.find_one(
            {"run_id": (hit.get("scrape") or {}).get("run_id")},
            projection={"run_id": 1, "started_at": 1, "langfuse_session_id": 1, "langfuse_trace_url": 1},
        ) if (hit.get("scrape") or {}).get("run_id") else None
        selector_run = self.selector_runs.find_one(
            {"run_id": main.get("selector_run_id")},
            projection={"run_id": 1, "scheduled_for": 1, "langfuse_session_id": 1, "langfuse_trace_url": 1},
        ) if main.get("selector_run_id") else None
        return {
            "search_run": search_run,
            "scrape_run": scrape_run,
            "selector_run": selector_run,
        }

    def _compute_display_status(self, hit: dict[str, Any]) -> str:
        selection = hit.get("selection") or {}
        main = selection.get("main") or {}
        if main.get("status") == "completed" and main.get("decision") not in {None, "none"}:
            return str(main["decision"])
        for state in (selection.get("profiles") or {}).values():
            if isinstance(state, dict) and state.get("decision") == "profile_selected":
                return "profile_selected"
        scrape = hit.get("scrape") or {}
        if scrape.get("selector_handoff_status") == "written":
            return "selector_handoff_written"
        if scrape.get("status"):
            return str(scrape["status"])
        return str(hit.get("hit_status") or "discovered")

    def _build_hits_query(
        self,
        *,
        query_text: Optional[str],
        window: str,
        profile: Optional[str],
        region: Optional[str],
        scrape_status: Optional[str],
        main_decision: Optional[str],
        pool_status: Optional[str],
        failures_only: bool,
        cursor: Optional[str],
    ) -> dict[str, Any]:
        current_time = datetime.now(timezone.utc)
        query: dict[str, Any] = {
            "last_seen_at": {"$gte": current_time - _parse_window(window)},
        }
        if profile:
            query["search_profile"] = profile
        if region:
            query["search_region"] = region
        if scrape_status:
            query["scrape.status"] = scrape_status
        if main_decision:
            query["selection.main.decision"] = main_decision
        if pool_status:
            query["selection.pool.status"] = pool_status
        if failures_only:
            query["$and"] = query.get("$and", [])
            query["$and"].append(
                {
                    "$or": [
                        {"scrape.status": {"$in": ["retry_pending", "deadletter"]}},
                        {"selection.main.status": "failed"},
                    ]
                }
            )

        search_value = (query_text or "").strip()
        if search_value:
            exact_match = self._build_exact_match_query(search_value)
            if exact_match:
                query["$and"] = query.get("$and", [])
                query["$and"].append(exact_match)
            else:
                query["$and"] = query.get("$and", [])
                query["$and"].append({"$text": {"$search": search_value}})

        cursor_filter = _decode_cursor(cursor)
        if cursor_filter is not None:
            query["$and"] = query.get("$and", [])
            query["$and"].append(
                {
                    "$or": [
                        {"last_seen_at": {"$lt": cursor_filter["last_seen_at"]}},
                        {
                            "last_seen_at": cursor_filter["last_seen_at"],
                            "_id": {"$lt": cursor_filter["_id"]},
                        },
                    ]
                }
            )
        return query

    def _build_exact_match_query(self, query_text: str) -> Optional[dict[str, Any]]:
        if query_text.startswith(("hit:", "searchrun:", "scraperun:", "selectorrun:")):
            return {
                "$or": [
                    {"correlation_id": query_text},
                    {"run_id": query_text},
                    {"scrape.run_id": query_text},
                    {"selection.main.selector_run_id": query_text},
                ]
            }
        if re.fullmatch(r"\d{6,}", query_text):
            return {
                "$or": [
                    {"external_job_id": query_text},
                    {"raw_search_payload.job_id": query_text},
                    {"scrape.selector_payload.job_id": query_text},
                ]
            }
        if ObjectId.is_valid(query_text):
            return {"_id": ObjectId(query_text)}
        return None

    def _build_reason(
        self,
        *,
        last_seen_at: Optional[datetime],
        primary_metric: int,
        primary_label: str,
    ) -> str:
        if last_seen_at is None:
            return "No recent activity recorded yet"
        return f"{primary_metric} {primary_label}; last activity {_format_relative(last_seen_at)}"


def _results_projection() -> dict[str, int]:
    return {
        "title": 1,
        "company": 1,
        "location": 1,
        "search_profile": 1,
        "search_region": 1,
        "hit_status": 1,
        "last_seen_at": 1,
        "correlation_id": 1,
        "langfuse_session_id": 1,
        "run_id": 1,
        "external_job_id": 1,
        "scrape": 1,
        "selection": 1,
    }


def _peek_projection() -> dict[str, int]:
    return {
        **_results_projection(),
        "times_seen": 1,
    }


def _parse_window(value: str) -> timedelta:
    normalized = (value or f"{DEFAULT_WINDOW_HOURS}h").strip().lower()
    mapping = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "8h": timedelta(hours=8),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }
    return mapping.get(normalized, timedelta(hours=DEFAULT_WINDOW_HOURS))


def _encode_cursor(last_seen_at: Optional[datetime], hit_id: ObjectId) -> Optional[str]:
    normalized = _coerce_utc(last_seen_at)
    if normalized is None:
        return None
    return f"{normalized.isoformat()}|{str(hit_id)}"


def _decode_cursor(cursor: Optional[str]) -> Optional[dict[str, Any]]:
    if not cursor or "|" not in cursor:
        return None
    timestamp, object_id = cursor.split("|", 1)
    if not ObjectId.is_valid(object_id):
        return None
    try:
        return {
            "last_seen_at": datetime.fromisoformat(timestamp),
            "_id": ObjectId(object_id),
        }
    except ValueError:
        return None


def _regex_search(query_text: str) -> list[dict[str, Any]]:
    pattern = re.escape(query_text)
    return [
        {"title": {"$regex": pattern, "$options": "i"}},
        {"company": {"$regex": pattern, "$options": "i"}},
        {"location": {"$regex": pattern, "$options": "i"}},
        {"scrape.detected_role": {"$regex": pattern, "$options": "i"}},
    ]


def _extract_text_search(query: dict[str, Any]) -> Optional[str]:
    if "$text" in query:
        return str(query["$text"]["$search"])
    for clause in query.get("$and", []):
        if isinstance(clause, dict) and "$text" in clause:
            return str(clause["$text"]["$search"])
    return None


def _remove_text_search(query: dict[str, Any]) -> None:
    if "$text" in query:
        del query["$text"]
    if "$and" in query:
        query["$and"] = [clause for clause in query["$and"] if "$text" not in clause]


def _heartbeat_state(
    *,
    last_seen_at: Optional[datetime],
    ok_within: timedelta,
    warn_within: timedelta,
) -> str:
    normalized = _coerce_utc(last_seen_at)
    if normalized is None:
        return "red"
    age = datetime.now(timezone.utc) - normalized
    if age <= ok_within:
        return "green"
    if age <= warn_within:
        return "yellow"
    return "red"


def _format_relative(value: datetime) -> str:
    normalized = _coerce_utc(value)
    delta = datetime.now(timezone.utc) - normalized
    if delta < timedelta(minutes=1):
        return "just now"
    if delta < timedelta(hours=1):
        return f"{int(delta.total_seconds() // 60)}m ago"
    if delta < timedelta(days=1):
        return f"{int(delta.total_seconds() // 3600)}h ago"
    return f"{delta.days}d ago"


def _coerce_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
