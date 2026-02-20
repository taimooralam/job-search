"""One-time MongoDB index creation for URL Resolver.

Run once after deployment:
    python3 /home/node/skills/url-resolver/scripts/setup_indexes.py
"""

import sys
import os

# Ensure scripts/ is on the path for sibling imports
sys.path.insert(0, os.path.dirname(__file__))

from pymongo import ASCENDING, DESCENDING

from mongo_store import get_db
from utils import setup_logging

logger = setup_logging("url-resolver-setup")


def create_indexes() -> None:
    """Create indexes for efficient URL resolution queries."""
    db = get_db()
    col = db["level-2"]

    # Compound index for the main query:
    # status + application_url + url_resolution_attempts
    col.create_index(
        [
            ("status", ASCENDING),
            ("application_url", ASCENDING),
            ("url_resolution_attempts", ASCENDING),
        ],
        name="url_resolver_query_idx",
        background=True,
    )
    logger.info("Created compound index: url_resolver_query_idx")

    # Sparse index for tracking resolved URLs by time
    col.create_index(
        [("url_resolved_at", DESCENDING)],
        name="url_resolved_at_idx",
        sparse=True,
        background=True,
    )
    logger.info("Created sparse index: url_resolved_at_idx")

    logger.info("All indexes created successfully")


if __name__ == "__main__":
    create_indexes()
