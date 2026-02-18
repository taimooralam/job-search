"""Repository for LinkedIn Intelligence collections on VPS MongoDB.

Standalone pymongo class — does NOT extend JobRepositoryInterface
(different data model). Uses the same MONGODB_URI as the job repository
since both live in the same 'jobs' database on VPS MongoDB.

Singleton pattern matches existing config.py approach.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo import DESCENDING, MongoClient

logger = logging.getLogger(__name__)

class IntelRepository:
    """Access linkedin_intel, linkedin_sessions, draft_content, and related collections on VPS MongoDB."""

    _instance: Optional["IntelRepository"] = None

    def __init__(self, mongodb_uri: str, database: str = "jobs"):
        self.client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[database]
        self.intel = self.db["linkedin_intel"]
        self.sessions = self.db["linkedin_sessions"]
        self.drafts = self.db["draft_content"]
        self.trends = self.db["linkedin_trends"]
        self.leads = self.db["lead_pipeline"]
        self.performance = self.db["content_performance"]
        self.authors = self.db["tracked_authors"]

    @classmethod
    def get_instance(cls) -> "IntelRepository":
        if cls._instance is None:
            uri = os.getenv("MONGODB_URI")
            if not uri:
                raise ValueError("MONGODB_URI required for intel dashboard")
            cls._instance = cls(uri)
            logger.info("Initialized IntelRepository (VPS MongoDB)")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        if cls._instance is not None:
            cls._instance.client.close()
            cls._instance = None

    # ------------------------------------------------------------------
    # Dashboard overview
    # ------------------------------------------------------------------

    def get_stats(self, since: datetime) -> dict:
        """Count new items, jobs, posts, leads since a given time."""
        col = self.intel
        pipeline = [
            {"$match": {"scraped_at": {"$gte": since}}},
            {"$group": {"_id": "$type", "count": {"$sum": 1}}},
        ]
        type_counts = {doc["_id"]: doc["count"] for doc in col.aggregate(pipeline)}
        total = sum(type_counts.values())
        high_relevance = col.count_documents({
            "scraped_at": {"$gte": since},
            "relevance_score": {"$gte": 7},
        })
        drafts_pending = self.drafts.count_documents({"status": "draft"})
        leads_count = self.leads.count_documents({
            "created_at": {"$gte": since},
        })
        return {
            "total": total,
            "type_counts": type_counts,
            "high_relevance": high_relevance,
            "drafts_pending": drafts_pending,
            "leads": leads_count,
        }

    def get_recent_sessions(self, limit: int = 5) -> list[dict]:
        """Latest scrape runs with stats."""
        return list(
            self.sessions.find(
                {"type": {"$ne": "cooldown"}},
                sort=[("started_at", DESCENDING)],
                limit=limit,
            )
        )

    def get_top_opportunities(self, since: datetime, min_score: int = 7, limit: int = 10) -> list[dict]:
        """High-relevance items sorted by score."""
        return list(
            self.intel.find(
                {"scraped_at": {"$gte": since}, "relevance_score": {"$gte": min_score}},
                sort=[("relevance_score", DESCENDING), ("scraped_at", DESCENDING)],
                limit=limit,
            )
        )

    # ------------------------------------------------------------------
    # Opportunities page
    # ------------------------------------------------------------------

    def get_intel_items(
        self,
        filters: dict[str, Any] | None = None,
        sort_field: str = "scraped_at",
        sort_dir: int = DESCENDING,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict], int]:
        """Paginated, filterable intel items. Returns (items, total_count)."""
        query: dict[str, Any] = {}
        if filters:
            if filters.get("type"):
                query["type"] = filters["type"]
            if filters.get("min_score"):
                query["relevance_score"] = {"$gte": int(filters["min_score"])}
            if filters.get("category"):
                query["classification.category"] = filters["category"]
            if filters.get("since"):
                query["scraped_at"] = {"$gte": filters["since"]}
            if filters.get("search"):
                query["$text"] = {"$search": filters["search"]}
            if filters.get("acted_on") is not None:
                query["acted_on"] = filters["acted_on"]

        total = self.intel.count_documents(query)
        skip = (page - 1) * per_page
        items = list(
            self.intel.find(query)
            .sort(sort_field, sort_dir)
            .skip(skip)
            .limit(per_page)
        )
        return items, total

    def get_item_detail(self, item_id: str | ObjectId) -> dict | None:
        """Single item with full content."""
        if isinstance(item_id, str):
            item_id = ObjectId(item_id)
        return self.intel.find_one({"_id": item_id})

    def update_item_action(self, item_id: str | ObjectId, action: str, data: dict | None = None) -> None:
        """Mark an intel item as acted_on, skipped, or saved."""
        if isinstance(item_id, str):
            item_id = ObjectId(item_id)
        update: dict[str, Any] = {
            "$set": {
                "acted_on": True,
                "acted_action": action,
                "acted_at": datetime.now(timezone.utc),
            }
        }
        if data:
            update["$set"].update(data)
        self.intel.update_one({"_id": item_id}, update)

    # ------------------------------------------------------------------
    # Drafts
    # ------------------------------------------------------------------

    def get_drafts(self, status: str = "draft", limit: int = 20) -> list[dict]:
        """Pending drafts."""
        return list(
            self.drafts.find({"status": status})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )

    def get_draft(self, draft_id: str | ObjectId) -> dict | None:
        if isinstance(draft_id, str):
            draft_id = ObjectId(draft_id)
        return self.drafts.find_one({"_id": draft_id})

    def update_draft(self, draft_id: str | ObjectId, updates: dict) -> None:
        if isinstance(draft_id, str):
            draft_id = ObjectId(draft_id)
        updates["updated_at"] = datetime.now(timezone.utc)
        self.drafts.update_one({"_id": draft_id}, {"$set": updates})

    def mark_draft_posted(self, draft_id: str | ObjectId, url: str) -> None:
        if isinstance(draft_id, str):
            draft_id = ObjectId(draft_id)
        self.drafts.update_one(
            {"_id": draft_id},
            {"$set": {
                "status": "posted",
                "posted_url": url,
                "posted_at": datetime.now(timezone.utc),
            }},
        )

    # ------------------------------------------------------------------
    # Sessions / Health
    # ------------------------------------------------------------------

    def get_session_history(self, days: int = 7) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        return list(
            self.sessions.find(
                {"started_at": {"$gte": since}, "type": {"$ne": "cooldown"}},
                sort=[("started_at", DESCENDING)],
            )
        )

    def get_api_usage(self, days: int = 7) -> dict:
        """Daily call counts from sessions."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        pipeline = [
            {"$match": {"started_at": {"$gte": since}, "calls_made": {"$exists": True}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$started_at"}},
                "total_calls": {"$sum": "$calls_made"},
                "sessions": {"$sum": 1},
            }},
            {"$sort": {"_id": -1}},
        ]
        results = list(self.sessions.aggregate(pipeline))
        return {
            "daily": results,
            "total_calls": sum(r["total_calls"] for r in results),
            "total_sessions": sum(r["sessions"] for r in results),
        }

    def get_cookie_health(self) -> dict:
        """Latest session's cookie status."""
        latest = self.sessions.find_one(
            {"type": {"$ne": "cooldown"}},
            sort=[("started_at", DESCENDING)],
        )
        cooldown = self.sessions.find_one(
            {"type": "cooldown", "expires_at": {"$gt": datetime.now(timezone.utc)}},
            sort=[("expires_at", DESCENDING)],
        )
        return {
            "last_session": latest,
            "active_cooldown": cooldown,
            "status": "cooldown" if cooldown else ("ok" if latest else "unknown"),
        }

    # ------------------------------------------------------------------
    # Pipeline bridge
    # ------------------------------------------------------------------

    def mark_pushed_to_pipeline(self, item_id: str | ObjectId, job_id: str) -> None:
        """Flag intel item as pushed to the job pipeline."""
        if isinstance(item_id, str):
            item_id = ObjectId(item_id)
        self.intel.update_one(
            {"_id": item_id},
            {"$set": {
                "acted_on": True,
                "acted_action": "pipeline",
                "pipeline_job_id": job_id,
                "acted_at": datetime.now(timezone.utc),
            }},
        )

    # ------------------------------------------------------------------
    # Briefing indexes (for Telegram command lookups)
    # ------------------------------------------------------------------

    def get_by_briefing_index(self, index: int, date: str) -> dict | None:
        """Look up an intel item by its briefing index and date."""
        return self.intel.find_one({
            "_briefing_index": index,
            "_briefing_date": date,
        })

    def get_unread_high_relevance(self, limit: int = 3) -> list[dict]:
        """Next N unread high-relevance items."""
        return list(
            self.intel.find({
                "relevance_score": {"$gte": 7},
                "acted_on": {"$ne": True},
            })
            .sort("relevance_score", DESCENDING)
            .limit(limit)
        )

    # ------------------------------------------------------------------
    # Lead pipeline
    # ------------------------------------------------------------------

    def create_lead(self, lead: dict) -> ObjectId:
        lead.setdefault("created_at", datetime.now(timezone.utc))
        lead.setdefault("status", "new")
        result = self.leads.insert_one(lead)
        return result.inserted_id

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------

    def get_trending_keywords(self, days: int = 7) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        return list(
            self.trends.find({"date": {"$gte": since}})
            .sort("date", DESCENDING)
            .limit(20)
        )
