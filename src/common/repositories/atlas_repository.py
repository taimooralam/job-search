"""
Atlas-Only Job Repository

Phase 1 implementation that wraps Atlas MongoDB operations.
Proves the repository pattern works before adding dual-write complexity.
"""

import logging
from typing import Any, Dict, List, Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from .base import JobRepositoryInterface, WriteResult

logger = logging.getLogger(__name__)


class AtlasJobRepository(JobRepositoryInterface):
    """
    Atlas-only repository for Phase 1.

    Simple wrapper around direct MongoDB Atlas access.
    Provides consistent interface for later dual-write migration.

    Connection Management:
    - Uses singleton MongoClient for connection pooling
    - Client is created once and reused across requests
    - PyMongo handles connection pool internally

    Error Handling:
    - Fail-fast: All errors propagate to caller
    - No silent failures - consumers must handle exceptions
    """

    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None
    _collection: Optional[Collection] = None

    def __init__(self, mongodb_uri: str, database: str = "jobs", collection: str = "level-2"):
        """
        Initialize Atlas repository with connection parameters.

        Args:
            mongodb_uri: MongoDB connection string (Atlas URI)
            database: Database name (default: "jobs")
            collection: Collection name (default: "level-2")
        """
        self._mongodb_uri = mongodb_uri
        self._database_name = database
        self._collection_name = collection

    def _get_collection(self) -> Collection:
        """
        Get the MongoDB collection, creating client if needed.

        Uses class-level singleton for connection pooling.
        Thread-safe due to PyMongo's internal locking.

        Returns:
            MongoDB collection instance
        """
        if AtlasJobRepository._collection is None:
            AtlasJobRepository._client = MongoClient(self._mongodb_uri)
            AtlasJobRepository._db = AtlasJobRepository._client[self._database_name]
            AtlasJobRepository._collection = AtlasJobRepository._db[self._collection_name]
            logger.info(
                f"Atlas repository connected: {self._database_name}.{self._collection_name}"
            )
        return AtlasJobRepository._collection

    def find_one(self, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single job document."""
        collection = self._get_collection()
        return collection.find_one(filter)

    def find(
        self,
        filter: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        limit: int = 0,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """Find multiple job documents."""
        collection = self._get_collection()
        cursor = collection.find(filter, projection)

        if sort:
            cursor = cursor.sort(sort)
        if skip > 0:
            cursor = cursor.skip(skip)
        if limit > 0:
            cursor = cursor.limit(limit)

        return list(cursor)

    def count_documents(self, filter: Dict[str, Any]) -> int:
        """Count documents matching the filter."""
        collection = self._get_collection()
        return collection.count_documents(filter)

    def update_one(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> WriteResult:
        """
        Update a single document.

        Fail-fast behavior: exceptions propagate to caller.
        """
        collection = self._get_collection()
        result = collection.update_one(filter, update, upsert=upsert)

        return WriteResult(
            matched_count=result.matched_count,
            modified_count=result.modified_count,
            upserted_id=str(result.upserted_id) if result.upserted_id else None,
            atlas_success=True,
            vps_success=None,  # VPS not enabled in Phase 1
        )

    def update_many(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
    ) -> WriteResult:
        """
        Update multiple documents.

        Fail-fast behavior: exceptions propagate to caller.
        """
        collection = self._get_collection()
        result = collection.update_many(filter, update)

        return WriteResult(
            matched_count=result.matched_count,
            modified_count=result.modified_count,
            atlas_success=True,
            vps_success=None,
        )

    def delete_one(self, filter: Dict[str, Any]) -> WriteResult:
        """Delete a single document."""
        collection = self._get_collection()
        result = collection.delete_one(filter)

        return WriteResult(
            matched_count=result.deleted_count,
            modified_count=result.deleted_count,
            atlas_success=True,
            vps_success=None,
        )

    def delete_many(self, filter: Dict[str, Any]) -> WriteResult:
        """Delete multiple documents."""
        collection = self._get_collection()
        result = collection.delete_many(filter)

        return WriteResult(
            matched_count=result.deleted_count,
            modified_count=result.deleted_count,
            atlas_success=True,
            vps_success=None,
        )

    def insert_one(self, document: Dict[str, Any]) -> WriteResult:
        """Insert a single document."""
        collection = self._get_collection()
        result = collection.insert_one(document)

        return WriteResult(
            matched_count=0,
            modified_count=0,
            upserted_id=str(result.inserted_id) if result.inserted_id else None,
            atlas_success=True,
            vps_success=None,
        )

    @classmethod
    def reset_connection(cls) -> None:
        """
        Reset the connection pool.

        Used for testing or connection recovery.
        """
        if cls._client:
            cls._client.close()
        cls._client = None
        cls._db = None
        cls._collection = None
        logger.info("Atlas repository connection reset")
