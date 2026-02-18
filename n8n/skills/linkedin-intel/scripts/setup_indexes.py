"""Create MongoDB indexes for the LinkedIn Intelligence collections.

Run once during initial setup, safe to re-run (createIndex is idempotent).
"""

from pymongo import ASCENDING, DESCENDING, TEXT, IndexModel

from mongo_store import get_db
from utils import setup_logging

logger = setup_logging("setup-indexes")


def create_indexes():
    """Create all required indexes on the jobs database."""
    db = get_db()

    # --- linkedin_intel ---
    intel = db.linkedin_intel
    intel_indexes = [
        IndexModel([("dedupe_hash", ASCENDING)], unique=True, name="dedupe_hash_unique"),
        IndexModel([("scraped_at", DESCENDING)], name="scraped_at_desc"),
        IndexModel(
            [("relevance_score", DESCENDING), ("scraped_at", DESCENDING)],
            name="relevance_score_scraped_at",
        ),
        IndexModel(
            [("type", ASCENDING), ("category", ASCENDING), ("scraped_at", DESCENDING)],
            name="type_category_scraped_at",
        ),
        IndexModel([("classification.tags", ASCENDING)], name="classification_tags"),
        IndexModel(
            [("title", TEXT), ("content_preview", TEXT), ("full_content", TEXT)],
            name="text_search",
        ),
    ]
    result = intel.create_indexes(intel_indexes)
    logger.info("linkedin_intel indexes: %s", result)

    # TTL index for auto-cleanup of low-relevance items after 90 days.
    # Note: MongoDB TTL indexes expire based on the field value + expireAfterSeconds.
    # We use a partial filter to only expire items with relevance_score < 5.
    try:
        intel.create_index(
            [("scraped_at", ASCENDING)],
            name="ttl_low_relevance_90d",
            expireAfterSeconds=90 * 24 * 3600,
            partialFilterExpression={"relevance_score": {"$lt": 5}},
        )
        logger.info("TTL index created for low-relevance items (90 days)")
    except Exception as e:
        # May already exist with different options — log and continue
        logger.warning("TTL index creation note: %s", e)

    # --- linkedin_sessions ---
    sessions = db.linkedin_sessions
    sessions_indexes = [
        IndexModel([("session_id", ASCENDING)], unique=True, sparse=True, name="session_id_unique"),
        IndexModel([("started_at", DESCENDING)], name="started_at_desc"),
        IndexModel([("type", ASCENDING), ("expires_at", DESCENDING)], name="cooldown_lookup"),
    ]
    result = sessions.create_indexes(sessions_indexes)
    logger.info("linkedin_sessions indexes: %s", result)

    # --- draft_content ---
    drafts = db.draft_content
    drafts_indexes = [
        IndexModel(
            [("status", ASCENDING), ("created_at", DESCENDING)],
            name="status_created_at",
        ),
        IndexModel([("source_intel_id", ASCENDING)], name="source_intel_id"),
    ]
    result = drafts.create_indexes(drafts_indexes)
    logger.info("draft_content indexes: %s", result)

    # --- linkedin_trends ---
    trends = db.linkedin_trends
    trends_indexes = [
        IndexModel(
            [("period", ASCENDING), ("date", DESCENDING)],
            name="period_date",
        ),
    ]
    result = trends.create_indexes(trends_indexes)
    logger.info("linkedin_trends indexes: %s", result)

    # --- lead_pipeline ---
    leads = db.lead_pipeline
    leads_indexes = [
        IndexModel([("source_intel_id", ASCENDING)], name="source_intel_id"),
        IndexModel(
            [("status", ASCENDING), ("created_at", DESCENDING)],
            name="status_created_at",
        ),
        IndexModel([("overall_score", DESCENDING)], name="overall_score_desc"),
    ]
    result = leads.create_indexes(leads_indexes)
    logger.info("lead_pipeline indexes: %s", result)

    # --- content_performance ---
    perf = db.content_performance
    perf_indexes = [
        IndexModel([("posted_at", DESCENDING)], name="posted_at_desc"),
        IndexModel([("topic_keywords", ASCENDING)], name="topic_keywords"),
    ]
    result = perf.create_indexes(perf_indexes)
    logger.info("content_performance indexes: %s", result)

    # --- tracked_authors ---
    authors = db.tracked_authors
    authors_indexes = [
        IndexModel(
            [("name", ASCENDING), ("source", ASCENDING)],
            unique=True,
            name="name_source_unique",
        ),
        IndexModel([("times_seen", DESCENDING)], name="times_seen_desc"),
        IndexModel([("last_seen_at", DESCENDING)], name="last_seen_at_desc"),
    ]
    result = authors.create_indexes(authors_indexes)
    logger.info("tracked_authors indexes: %s", result)

    # --- linkedin_intel: briefing index lookup ---
    try:
        intel.create_index(
            [("_briefing_index", ASCENDING), ("_briefing_date", ASCENDING)],
            name="briefing_index_date",
            sparse=True,
        )
        logger.info("Briefing index lookup created on linkedin_intel")
    except Exception as e:
        logger.warning("Briefing index note: %s", e)

    logger.info("All indexes created successfully")


if __name__ == "__main__":
    create_indexes()
