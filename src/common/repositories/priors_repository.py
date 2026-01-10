"""
Priors Repository Implementation

Repository pattern for the annotation_priors collection.
Enables dual-write support for VPS migration alongside the jobs collection.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from .base import WriteResult

logger = logging.getLogger(__name__)


class PriorsRepositoryInterface(ABC):
    """
    Abstract interface for annotation_priors collection operations.

    The priors collection stores a single document with:
    - Sentence embeddings for similarity matching
    - Skill priors (learned skill frequencies)
    - Learned annotation mappings
    - Usage statistics

    Implementations:
    - AtlasPriorsRepository: Atlas-only (Phase 1)
    - DualWritePriorsRepository: Atlas + VPS sync (Phase 3+)
    """

    @abstractmethod
    def find_one(self, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find the priors document.

        Args:
            filter: MongoDB query filter (typically {"_id": PRIORS_DOC_ID})

        Returns:
            Document dict if found, None otherwise
        """
        pass

    @abstractmethod
    def insert_one(self, document: Dict[str, Any]) -> WriteResult:
        """
        Insert a new priors document.

        Args:
            document: The document to insert

        Returns:
            WriteResult with insert status
        """
        pass

    @abstractmethod
    def replace_one(
        self,
        filter: Dict[str, Any],
        replacement: Dict[str, Any],
        upsert: bool = False,
    ) -> WriteResult:
        """
        Replace the priors document.

        Args:
            filter: MongoDB query filter
            replacement: The new document (replaces entire document)
            upsert: Create document if not found

        Returns:
            WriteResult with match/modify counts and sync status
        """
        pass


class AtlasPriorsRepository(PriorsRepositoryInterface):
    """
    Atlas-only repository for annotation_priors collection.

    Follows the same pattern as AtlasJobRepository:
    - Singleton connection pooling
    - Fail-fast error handling
    - WriteResult with sync status tracking

    Connection Management:
    - Uses singleton MongoClient for connection pooling
    - Client is created once and reused across requests
    """

    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None
    _collection: Optional[Collection] = None

    def __init__(
        self,
        mongodb_uri: str,
        database: str = "jobs",
        collection: str = "annotation_priors",
    ):
        """
        Initialize Atlas priors repository.

        Args:
            mongodb_uri: MongoDB connection string (Atlas URI)
            database: Database name (default: "jobs")
            collection: Collection name (default: "annotation_priors")
        """
        self._mongodb_uri = mongodb_uri
        self._database_name = database
        self._collection_name = collection

    def _get_collection(self) -> Collection:
        """
        Get the MongoDB collection, creating client if needed.

        Uses class-level singleton for connection pooling.
        Separate from AtlasJobRepository to allow independent collection access.

        Returns:
            MongoDB collection instance
        """
        if AtlasPriorsRepository._collection is None:
            AtlasPriorsRepository._client = MongoClient(self._mongodb_uri)
            AtlasPriorsRepository._db = AtlasPriorsRepository._client[self._database_name]
            AtlasPriorsRepository._collection = AtlasPriorsRepository._db[self._collection_name]
            logger.info(
                f"Atlas priors repository connected: {self._database_name}.{self._collection_name}"
            )
        return AtlasPriorsRepository._collection

    def find_one(self, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find the priors document."""
        collection = self._get_collection()
        return collection.find_one(filter)

    def insert_one(self, document: Dict[str, Any]) -> WriteResult:
        """Insert a new priors document."""
        collection = self._get_collection()
        result = collection.insert_one(document)

        return WriteResult(
            matched_count=0,
            modified_count=1 if result.inserted_id else 0,
            upserted_id=str(result.inserted_id) if result.inserted_id else None,
            atlas_success=True,
            vps_success=None,  # VPS not enabled in Phase 1
        )

    def replace_one(
        self,
        filter: Dict[str, Any],
        replacement: Dict[str, Any],
        upsert: bool = False,
    ) -> WriteResult:
        """
        Replace the priors document.

        Fail-fast behavior: exceptions propagate to caller.
        """
        collection = self._get_collection()
        result = collection.replace_one(filter, replacement, upsert=upsert)

        return WriteResult(
            matched_count=result.matched_count,
            modified_count=result.modified_count,
            upserted_id=str(result.upserted_id) if result.upserted_id else None,
            atlas_success=True,
            vps_success=None,  # VPS not enabled in Phase 1
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
        logger.info("Atlas priors repository connection reset")
