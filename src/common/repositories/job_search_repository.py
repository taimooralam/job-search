"""
Job Search Repository

Repository interface for the job_search_cache and job_search_index collections.
Used by JobSearchService for pull-on-demand job search functionality.
"""

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING

logger = logging.getLogger(__name__)


class JobSearchRepositoryInterface(ABC):
    """
    Abstract interface for job search collections.

    Manages two collections:
        - job_search_cache: Stores search result caches with TTL
        - job_search_index: Stores discovered jobs from searches
    """

    # =========================================================================
    # Cache Collection Operations
    # =========================================================================

    @abstractmethod
    def cache_find_one(self, filter_query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a cache entry by filter."""
        pass

    @abstractmethod
    def cache_upsert(self, cache_key: str, document: Dict[str, Any]) -> bool:
        """Upsert a cache entry by cache_key."""
        pass

    @abstractmethod
    def cache_delete_all(self) -> int:
        """Delete all cache entries. Returns count of deleted documents."""
        pass

    @abstractmethod
    def cache_count(self, filter_query: Optional[Dict[str, Any]] = None) -> int:
        """Count cache entries matching filter."""
        pass

    @abstractmethod
    def cache_ensure_indexes(self) -> None:
        """Ensure required indexes exist on cache collection."""
        pass

    # =========================================================================
    # Index Collection Operations
    # =========================================================================

    @abstractmethod
    def index_find(
        self,
        filter_query: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Find jobs in the index with filtering, sorting, and pagination."""
        pass

    @abstractmethod
    def index_find_one(self, filter_query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single job in the index."""
        pass

    @abstractmethod
    def index_find_by_ids(
        self,
        ids: List[ObjectId],
        projection: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Find jobs by their ObjectIds."""
        pass

    @abstractmethod
    def index_upsert(
        self,
        dedupe_key: str,
        set_fields: Dict[str, Any],
        set_on_insert: Dict[str, Any],
        inc_fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Upsert a job by dedupe_key.

        Returns the updated/inserted document.
        """
        pass

    @abstractmethod
    def index_update_one(
        self,
        filter_query: Dict[str, Any],
        update: Dict[str, Any],
    ) -> int:
        """Update a single job. Returns modified count."""
        pass

    @abstractmethod
    def index_count(self, filter_query: Optional[Dict[str, Any]] = None) -> int:
        """Count jobs matching filter."""
        pass

    @abstractmethod
    def index_aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run aggregation pipeline on index."""
        pass

    @abstractmethod
    def index_ensure_indexes(self) -> None:
        """Ensure required indexes exist on index collection."""
        pass


class AtlasJobSearchRepository(JobSearchRepositoryInterface):
    """
    Atlas MongoDB implementation of JobSearchRepository.
    """

    _client: Optional[MongoClient] = None

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        database: str = "jobs",
        cache_collection: str = "job_search_cache",
        index_collection: str = "job_search_index",
    ):
        """
        Initialize the repository.

        Args:
            mongodb_uri: MongoDB connection string (defaults to MONGODB_URI env var)
            database: Database name
            cache_collection: Cache collection name
            index_collection: Index collection name
        """
        self._mongodb_uri = mongodb_uri or os.getenv("MONGODB_URI")
        self._database = database
        self._cache_collection_name = cache_collection
        self._index_collection_name = index_collection

        if not self._mongodb_uri:
            raise ValueError("MongoDB URI is required")

    def _get_client(self) -> MongoClient:
        """Get or create the MongoDB client (singleton)."""
        if AtlasJobSearchRepository._client is None:
            AtlasJobSearchRepository._client = MongoClient(self._mongodb_uri)
            logger.info("Created new MongoDB client for job_search repository")
        return AtlasJobSearchRepository._client

    def _get_cache_collection(self):
        """Get the cache collection."""
        client = self._get_client()
        return client[self._database][self._cache_collection_name]

    def _get_index_collection(self):
        """Get the index collection."""
        client = self._get_client()
        return client[self._database][self._index_collection_name]

    @classmethod
    def reset_connection(cls) -> None:
        """Reset the MongoDB client connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            logger.info("Job search repository connection reset")

    # =========================================================================
    # Cache Collection Operations
    # =========================================================================

    def cache_find_one(self, filter_query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a cache entry by filter."""
        return self._get_cache_collection().find_one(filter_query)

    def cache_upsert(self, cache_key: str, document: Dict[str, Any]) -> bool:
        """Upsert a cache entry by cache_key."""
        try:
            self._get_cache_collection().update_one(
                {"cache_key": cache_key},
                {"$set": document},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"Error upserting cache entry: {e}")
            return False

    def cache_delete_all(self) -> int:
        """Delete all cache entries."""
        result = self._get_cache_collection().delete_many({})
        return result.deleted_count

    def cache_count(self, filter_query: Optional[Dict[str, Any]] = None) -> int:
        """Count cache entries matching filter."""
        return self._get_cache_collection().count_documents(filter_query or {})

    def cache_ensure_indexes(self) -> None:
        """Ensure required indexes exist on cache collection."""
        cache = self._get_cache_collection()
        try:
            cache.create_index("expires_at", expireAfterSeconds=0, background=True)
            cache.create_index("cache_key", unique=True, background=True)
            logger.info("Job search cache indexes ensured")
        except Exception as e:
            logger.warning(f"Error creating cache indexes: {e}")

    # =========================================================================
    # Index Collection Operations
    # =========================================================================

    def index_find(
        self,
        filter_query: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Find jobs in the index with filtering, sorting, and pagination."""
        cursor = self._get_index_collection().find(filter_query, projection)
        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.skip(skip).limit(limit)
        return list(cursor)

    def index_find_one(self, filter_query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single job in the index."""
        return self._get_index_collection().find_one(filter_query)

    def index_find_by_ids(
        self,
        ids: List[ObjectId],
        projection: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Find jobs by their ObjectIds."""
        return list(self._get_index_collection().find(
            {"_id": {"$in": ids}},
            projection,
        ))

    def index_upsert(
        self,
        dedupe_key: str,
        set_fields: Dict[str, Any],
        set_on_insert: Dict[str, Any],
        inc_fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Upsert a job by dedupe_key."""
        update = {
            "$set": set_fields,
            "$setOnInsert": set_on_insert,
        }
        if inc_fields:
            update["$inc"] = inc_fields

        return self._get_index_collection().find_one_and_update(
            {"dedupeKey": dedupe_key},
            update,
            upsert=True,
            return_document=True,
        )

    def index_update_one(
        self,
        filter_query: Dict[str, Any],
        update: Dict[str, Any],
    ) -> int:
        """Update a single job."""
        result = self._get_index_collection().update_one(filter_query, update)
        return result.modified_count

    def index_count(self, filter_query: Optional[Dict[str, Any]] = None) -> int:
        """Count jobs matching filter."""
        return self._get_index_collection().count_documents(filter_query or {})

    def index_aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run aggregation pipeline on index."""
        return list(self._get_index_collection().aggregate(pipeline))

    def index_ensure_indexes(self) -> None:
        """Ensure required indexes exist on index collection."""
        index = self._get_index_collection()
        try:
            index.create_index("dedupeKey", unique=True, background=True)
            index.create_index(
                [("source", ASCENDING), ("region", ASCENDING), ("discovered_at", DESCENDING)],
                background=True,
            )
            index.create_index(
                [("title", "text"), ("company", "text"), ("description", "text")],
                background=True,
            )
            index.create_index("promoted_to_level2", background=True)
            index.create_index("hidden", background=True)
            index.create_index("quick_score", background=True)
            logger.info("Job search index indexes ensured")
        except Exception as e:
            logger.warning(f"Error creating index indexes: {e}")


# Singleton instance
_job_search_repository_instance: Optional[JobSearchRepositoryInterface] = None


def get_job_search_repository() -> JobSearchRepositoryInterface:
    """
    Get the job search repository instance (singleton).

    Returns:
        JobSearchRepositoryInterface implementation
    """
    global _job_search_repository_instance

    if _job_search_repository_instance is None:
        _job_search_repository_instance = AtlasJobSearchRepository()
        logger.info("Initialized job search repository")

    return _job_search_repository_instance


def reset_job_search_repository() -> None:
    """Reset the repository singleton."""
    global _job_search_repository_instance

    if _job_search_repository_instance is not None:
        if isinstance(_job_search_repository_instance, AtlasJobSearchRepository):
            AtlasJobSearchRepository.reset_connection()

    _job_search_repository_instance = None
    logger.info("Job search repository singleton reset")
