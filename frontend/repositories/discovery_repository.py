"""Repository for discovery and native scrape pipeline visibility."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from pymongo import DESCENDING, MongoClient

logger = logging.getLogger(__name__)


class DiscoveryRepository:
    """Access search, scrape, and queue state for the discovery dashboard."""

    _instance: Optional["DiscoveryRepository"] = None

    def __init__(self, mongodb_uri: str, database: str = "jobs"):
        self.client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[database]
        self.search_runs = self.db["search_runs"]
        self.search_hits = self.db["scout_search_hits"]
        self.scrape_runs = self.db["scrape_runs"]
        self.work_items = self.db["work_items"]

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

    def get_stats(self, since: datetime) -> dict[str, int]:
        """Return top-level stats for the discovery dashboard."""
        return {
            "search_runs_last_24h": self.search_runs.count_documents({"started_at": {"$gte": since}}),
            "discoveries_last_24h": self.search_hits.count_documents({"first_seen_at": {"$gte": since}}),
            "pending_scrapes": self.search_hits.count_documents({"scrape.status": {"$in": ["pending", "leased", "retry_pending"]}}),
            "selector_handoffs_written": self.search_hits.count_documents({"scrape.selector_handoff_status": "written"}),
            "failures_deadletters": self.search_hits.count_documents({"scrape.status": {"$in": ["retry_pending", "deadletter"]}}),
        }

    def get_hits(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent discovery hits with their related work-item state."""
        hits = list(self.search_hits.find().sort([("last_seen_at", DESCENDING)]).limit(limit))
        for hit in hits:
            hit["related_work_item"] = self.get_related_work_item(str(hit["_id"]))
            hit["display_status"] = self._compute_display_status(hit)
        return hits

    def get_recent_search_runs(self, limit: int = 8) -> list[dict[str, Any]]:
        """Return recent search runs."""
        return list(self.search_runs.find().sort([("started_at", DESCENDING)]).limit(limit))

    def get_recent_scrape_runs(self, limit: int = 8) -> list[dict[str, Any]]:
        """Return recent scrape worker runs."""
        return list(self.scrape_runs.find().sort([("started_at", DESCENDING)]).limit(limit))

    def get_recent_failures(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return recent retry-pending or deadletter scrape failures."""
        failures = list(
            self.search_hits.find(
                {"scrape.status": {"$in": ["retry_pending", "deadletter"]}},
                {
                    "title": 1,
                    "company": 1,
                    "scrape.status": 1,
                    "scrape.last_error": 1,
                    "scrape.attempt_count": 1,
                    "correlation_id": 1,
                    "updated_at": 1,
                },
            )
            .sort([("updated_at", DESCENDING)])
            .limit(limit)
        )
        return failures

    def get_queue_snapshot(self) -> dict[str, Any]:
        """Return queue counts grouped by scrape consumer mode."""
        base_query = {"task_type": "scrape.hit"}

        def _counts(extra: dict[str, Any]) -> dict[str, int]:
            counts = {
                status: self.work_items.count_documents({**base_query, **extra, "status": status})
                for status in ("pending", "leased", "done", "failed", "deadletter")
            }
            counts["total"] = sum(counts.values())
            return counts

        native = _counts({"consumer_mode": "native_scrape"})
        legacy = _counts({"consumer_mode": "legacy_jsonl"})
        return {
            "native": native,
            "legacy": legacy,
            "all": _counts({}),
        }

    def get_hit_detail(self, hit_id: str) -> Optional[dict[str, Any]]:
        """Return one hit plus its related work-item."""
        document = self.search_hits.find_one({"_id": ObjectId(hit_id)})
        if document is None:
            return None
        document["related_work_item"] = self.get_related_work_item(hit_id)
        document["display_status"] = self._compute_display_status(document)
        return document

    def get_related_work_item(self, hit_id: str) -> Optional[dict[str, Any]]:
        """Return the most relevant work-item for one search hit."""
        return self.work_items.find_one(
            {
                "task_type": "scrape.hit",
                "subject_type": "search_hit",
                "subject_id": hit_id,
            },
            sort=[("updated_at", DESCENDING)],
        )

    def get_langfuse_panel(self) -> dict[str, Any]:
        """Return optional Langfuse metadata for the UI."""
        latest_search_run = self.search_runs.find_one(sort=[("started_at", DESCENDING)])
        latest_scrape_run = self.scrape_runs.find_one(sort=[("started_at", DESCENDING)])
        latest_hit = self.search_hits.find_one(sort=[("last_seen_at", DESCENDING)])
        return {
            "public_url": os.getenv("LANGFUSE_PUBLIC_URL"),
            "latest_search_run_session_id": latest_search_run.get("langfuse_session_id") if latest_search_run else None,
            "latest_scrape_run_session_id": latest_scrape_run.get("langfuse_session_id") if latest_scrape_run else None,
            "latest_hit_session_id": latest_hit.get("langfuse_session_id") if latest_hit else None,
        }

    def _compute_display_status(self, hit: dict[str, Any]) -> str:
        scrape = hit.get("scrape") or {}
        if scrape.get("selector_handoff_status") == "written":
            return "selector_handoff_written"
        if scrape.get("status"):
            return str(scrape["status"])
        return str(hit.get("hit_status") or "discovered")
