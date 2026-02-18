"""MongoDB storage layer for LinkedIn Intelligence.

Uses the existing `jobs` database on the VPS MongoDB instance.
Collections: linkedin_intel, linkedin_sessions, draft_content, linkedin_trends.
"""

import os
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from utils import setup_logging

logger = setup_logging("mongo-store")

# Singleton client — reused across calls within a process
_client: MongoClient | None = None


def get_db():
    """Return the `jobs` database handle, creating the client on first call."""
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI environment variable is not set")
        _client = MongoClient(uri)
    return _client["jobs"]


# ---------------------------------------------------------------------------
# linkedin_intel collection
# ---------------------------------------------------------------------------

def store_intel_item(item: dict) -> str:
    """Insert a new intel item. Returns 'inserted' or 'duplicate'.

    On duplicate (same dedupe_hash), updates `last_seen_at` instead.
    """
    db = get_db()
    item.setdefault("scraped_at", datetime.now(timezone.utc))
    item.setdefault("last_seen_at", datetime.now(timezone.utc))

    try:
        db.linkedin_intel.insert_one(item)
        return "inserted"
    except DuplicateKeyError:
        db.linkedin_intel.update_one(
            {"dedupe_hash": item["dedupe_hash"]},
            {"$set": {"last_seen_at": datetime.now(timezone.utc)}},
        )
        return "duplicate"


def get_unclassified_items(since: datetime | None = None) -> list[dict]:
    """Return items that have no classification yet."""
    db = get_db()
    query: dict = {"classification": {"$exists": False}}
    if since:
        query["scraped_at"] = {"$gte": since}
    return list(db.linkedin_intel.find(query).sort("scraped_at", -1))


def update_classification(item_id, classification: dict) -> None:
    """Attach classification results to an intel item."""
    db = get_db()
    db.linkedin_intel.update_one(
        {"_id": item_id},
        {"$set": {
            "classification": classification,
            "relevance_score": classification.get("relevance_score", 0),
            "classified_at": datetime.now(timezone.utc),
        }},
    )


def get_briefing_data(since: datetime) -> dict:
    """Aggregate stats and top items for the Telegram briefing."""
    db = get_db()
    col = db.linkedin_intel

    pipeline_counts = [
        {"$match": {"scraped_at": {"$gte": since}}},
        {"$group": {
            "_id": "$type",
            "count": {"$sum": 1},
        }},
    ]
    type_counts = {doc["_id"]: doc["count"] for doc in col.aggregate(pipeline_counts)}

    total = sum(type_counts.values())
    high_relevance = col.count_documents({
        "scraped_at": {"$gte": since},
        "relevance_score": {"$gte": 7},
    })

    top_jobs = list(col.find({
        "scraped_at": {"$gte": since},
        "type": "job",
        "relevance_score": {"$gte": 7},
    }).sort("relevance_score", -1).limit(5))

    posts_to_engage = list(col.find({
        "scraped_at": {"$gte": since},
        "type": {"$in": ["post", "article"]},
        "relevance_score": {"$gte": 7},
    }).sort("relevance_score", -1).limit(5))

    return {
        "total": total,
        "type_counts": type_counts,
        "high_relevance": high_relevance,
        "top_jobs": top_jobs,
        "posts_to_engage": posts_to_engage,
    }


# ---------------------------------------------------------------------------
# linkedin_sessions collection
# ---------------------------------------------------------------------------

def log_session(session: dict) -> None:
    """Record a scraping session with metadata."""
    db = get_db()
    session.setdefault("started_at", datetime.now(timezone.utc))
    db.linkedin_sessions.insert_one(session)


def get_today_call_count() -> int:
    """Sum API calls made today across all sessions."""
    db = get_db()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    pipeline = [
        {"$match": {"started_at": {"$gte": today_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$calls_made"}}},
    ]
    result = list(db.linkedin_sessions.aggregate(pipeline))
    return result[0]["total"] if result else 0


def get_first_session_date() -> datetime | None:
    """Return the date of the very first session (for warmup calculation)."""
    db = get_db()
    doc = db.linkedin_sessions.find_one(sort=[("started_at", 1)])
    return doc["started_at"] if doc else None


def get_cooldown_state() -> dict | None:
    """Return the current cooldown state, if any."""
    db = get_db()
    return db.linkedin_sessions.find_one(
        {"type": "cooldown", "expires_at": {"$gt": datetime.now(timezone.utc)}},
        sort=[("expires_at", -1)],
    )


def set_cooldown(status_code: int, hours: int) -> None:
    """Set a cooldown period after an error response."""
    db = get_db()
    db.linkedin_sessions.insert_one({
        "type": "cooldown",
        "status_code": status_code,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=hours),
    })


# ---------------------------------------------------------------------------
# draft_content collection
# ---------------------------------------------------------------------------

def store_draft(draft: dict) -> None:
    """Store a generated content draft."""
    db = get_db()
    draft.setdefault("created_at", datetime.now(timezone.utc))
    draft.setdefault("status", "draft")
    db.draft_content.insert_one(draft)


def get_drafts_for_briefing(since: datetime) -> list[dict]:
    """Return recent drafts for inclusion in the briefing."""
    db = get_db()
    return list(db.draft_content.find({
        "created_at": {"$gte": since},
        "status": "draft",
    }).sort("created_at", -1).limit(10))


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test MongoDB store operations")
    parser.add_argument("--test", action="store_true", help="Run basic CRUD test")
    args = parser.parse_args()

    if args.test:
        from bson import ObjectId

        db = get_db()
        logger.info("Connected to MongoDB: %s", db.name)
        logger.info("Collections: %s", db.list_collection_names())

        # Test insert + duplicate
        test_item = {
            "dedupe_hash": "test_hash_" + ObjectId().__str__(),
            "title": "Test Enterprise Architect Role",
            "source": "linkedin",
            "url": "https://linkedin.com/test",
            "type": "job",
        }
        result = store_intel_item(test_item)
        logger.info("Insert result: %s", result)

        # Clean up test data
        db.linkedin_intel.delete_one({"dedupe_hash": test_item["dedupe_hash"]})
        logger.info("Test cleanup complete")
