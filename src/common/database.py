"""
MongoDB database utilities for the job intelligence pipeline.

Provides connection management, collection access, and index creation
for STAR records and job processing state.
"""

from typing import Optional, List, Dict, Any
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError
import logging

from .config import Config
from .types import STARRecord

logger = logging.getLogger(__name__)


class DatabaseClient:
    """
    MongoDB client for the job intelligence pipeline.

    Manages connections and provides typed access to collections.
    """

    _instance: Optional['DatabaseClient'] = None
    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None

    def __new__(cls):
        """Singleton pattern - only one database client instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the database client if not already initialized."""
        if self._client is None:
            self.connect()

    def connect(self) -> None:
        """
        Connect to MongoDB using configuration from Config.

        Raises:
            ValueError: If MONGODB_URI is not configured
        """
        if not Config.MONGODB_URI:
            raise ValueError("MONGODB_URI not configured in .env")

        self._client = MongoClient(Config.MONGODB_URI)
        # Use database from URI or default to "job_intelligence"
        try:
            self._db = self._client.get_database()
        except:
            self._db = self._client["job_intelligence"]
        logger.info(f"Connected to MongoDB: {self._db.name}")

    def disconnect(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("Disconnected from MongoDB")

    @property
    def db(self) -> Database:
        """Get the database instance."""
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    @property
    def star_records(self) -> Collection:
        """Get the star_records collection."""
        return self.db["star_records"]

    @property
    def jobs(self) -> Collection:
        """Get the jobs collection (for job postings)."""
        return self.db["jobs"]

    @property
    def pipeline_runs(self) -> Collection:
        """Get the pipeline_runs collection (for execution tracking)."""
        return self.db["pipeline_runs"]

    def ensure_indexes(self) -> None:
        """
        Create all required indexes for efficient querying.

        Called once during setup to ensure optimal performance.
        """
        logger.info("Creating indexes...")

        # STAR Records Indexes
        star_indexes = [
            # Unique constraint on STAR ID
            ("id", [("id", ASCENDING)], {"unique": True}),

            # Search by company/role
            ("company_role", [("company", ASCENDING), ("role_title", ASCENDING)], {}),

            # Search by domain areas (for skill-based matching)
            ("domain_areas", [("domain_areas", ASCENDING)], {}),

            # Search by categories (for theme-based matching)
            ("categories", [("categories", ASCENDING)], {}),

            # Search by pain points addressed (for job-pain mapping)
            ("pain_points", [("pain_points_addressed", ASCENDING)], {}),

            # Search by outcome types (for outcome-based matching)
            ("outcome_types", [("outcome_types", ASCENDING)], {}),

            # Search by hard skills
            ("hard_skills", [("hard_skills", ASCENDING)], {}),

            # Search by soft skills
            ("soft_skills", [("soft_skills", ASCENDING)], {}),

            # Search by target roles (for role-based matching)
            ("target_roles", [("target_roles", ASCENDING)], {}),

            # Full-text search on condensed version and impact summary
            ("text_search", [
                ("condensed_version", "text"),
                ("impact_summary", "text"),
                ("situation", "text")
            ], {})
        ]

        for name, keys, options in star_indexes:
            try:
                self.star_records.create_index(keys, name=name, **options)
                logger.info(f"✓ Created index: {name}")
            except Exception as e:
                logger.warning(f"Index {name} may already exist: {e}")

        # Jobs Collection Indexes
        job_indexes = [
            ("job_id", [("job_id", ASCENDING)], {"unique": True}),
            ("company", [("company", ASCENDING)], {}),
            ("created_at", [("created_at", DESCENDING)], {})
        ]

        for name, keys, options in job_indexes:
            try:
                self.jobs.create_index(keys, name=name, **options)
                logger.info(f"✓ Created index: {name}")
            except Exception as e:
                logger.warning(f"Index {name} may already exist: {e}")

        # Pipeline Runs Indexes
        run_indexes = [
            ("run_id", [("run_id", ASCENDING)], {"unique": True}),
            ("job_id", [("job_id", ASCENDING)], {}),
            ("created_at", [("created_at", DESCENDING)], {}),
            ("status", [("status", ASCENDING)], {})
        ]

        for name, keys, options in run_indexes:
            try:
                self.pipeline_runs.create_index(keys, name=name, **options)
                logger.info(f"✓ Created index: {name}")
            except Exception as e:
                logger.warning(f"Index {name} may already exist: {e}")

        logger.info("✓ All indexes created")

    def insert_star_record(self, record: STARRecord) -> bool:
        """
        Insert a single STAR record into the database.

        Args:
            record: STARRecord to insert

        Returns:
            True if inserted, False if duplicate (already exists)
        """
        try:
            # Convert TypedDict to regular dict for MongoDB
            doc = dict(record)
            self.star_records.insert_one(doc)
            logger.info(f"✓ Inserted STAR: {record['id']}")
            return True
        except DuplicateKeyError:
            logger.warning(f"⚠ STAR {record['id']} already exists, skipping")
            return False

    def bulk_insert_star_records(self, records: List[STARRecord]) -> Dict[str, int]:
        """
        Insert multiple STAR records in bulk.

        Args:
            records: List of STARRecord objects

        Returns:
            Dict with counts: {"inserted": N, "duplicates": M, "errors": K}
        """
        results = {"inserted": 0, "duplicates": 0, "errors": 0}

        for record in records:
            try:
                if self.insert_star_record(record):
                    results["inserted"] += 1
                else:
                    results["duplicates"] += 1
            except Exception as e:
                logger.error(f"✗ Error inserting {record.get('id', 'unknown')}: {e}")
                results["errors"] += 1

        return results

    def get_star_record(self, star_id: str) -> Optional[STARRecord]:
        """
        Retrieve a single STAR record by ID.

        Args:
            star_id: The STAR record ID

        Returns:
            STARRecord if found, None otherwise
        """
        doc = self.star_records.find_one({"id": star_id})
        if doc:
            # Remove MongoDB's _id field
            doc.pop("_id", None)
            return doc  # type: ignore
        return None

    def get_all_star_records(self) -> List[STARRecord]:
        """
        Retrieve all STAR records from the database.

        Returns:
            List of all STARRecord objects
        """
        docs = list(self.star_records.find({}))
        # Remove MongoDB's _id field from each document
        for doc in docs:
            doc.pop("_id", None)
        return docs  # type: ignore

    def search_stars_by_pain_points(self, pain_points: List[str]) -> List[STARRecord]:
        """
        Find STAR records that address specific pain points.

        Args:
            pain_points: List of pain point keywords/phrases

        Returns:
            List of matching STARRecord objects
        """
        query = {"pain_points_addressed": {"$in": pain_points}}
        docs = list(self.star_records.find(query))
        for doc in docs:
            doc.pop("_id", None)
        return docs  # type: ignore

    def search_stars_by_skills(self, skills: List[str]) -> List[STARRecord]:
        """
        Find STAR records that demonstrate specific skills.

        Args:
            skills: List of skill keywords

        Returns:
            List of matching STARRecord objects
        """
        query = {
            "$or": [
                {"hard_skills": {"$in": skills}},
                {"soft_skills": {"$in": skills}}
            ]
        }
        docs = list(self.star_records.find(query))
        for doc in docs:
            doc.pop("_id", None)
        return docs  # type: ignore

    def clear_star_records(self) -> int:
        """
        Delete all STAR records from the database.

        ⚠️ USE WITH CAUTION - This removes all data!

        Returns:
            Number of records deleted
        """
        result = self.star_records.delete_many({})
        logger.warning(f"⚠ Deleted {result.deleted_count} STAR records")
        return result.deleted_count


# Global database client instance
db = DatabaseClient()
