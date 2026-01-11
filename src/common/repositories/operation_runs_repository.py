"""
Operation Runs Repository

Repository interface for the operation_runs collection.
Stores operation execution records for cost tracking and auditing.
"""

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

from .base import WriteResult

logger = logging.getLogger(__name__)


class OperationRunsRepositoryInterface(ABC):
    """
    Abstract interface for operation runs collection.

    The operation_runs collection stores:
    - Operation execution records (run_id, job_id, operation, success, cost, etc.)
    - Used for cost tracking and auditing
    """

    @abstractmethod
    def find_one(
        self, filter: Dict[str, Any], projection: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Find a single operation run document.

        Args:
            filter: MongoDB query filter
            projection: Fields to include/exclude (optional)

        Returns:
            Document dict if found, None otherwise
        """
        pass

    @abstractmethod
    def find(
        self,
        filter: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        limit: int = 0,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Find multiple operation run documents.

        Args:
            filter: MongoDB query filter
            projection: Fields to include/exclude
            sort: Sort order as list of (field, direction) tuples
            limit: Maximum documents to return (0 = no limit)
            skip: Number of documents to skip

        Returns:
            List of matching documents
        """
        pass

    @abstractmethod
    def insert_one(self, document: Dict[str, Any]) -> WriteResult:
        """
        Insert a new operation run record.

        Args:
            document: The operation run document

        Returns:
            WriteResult with insert status
        """
        pass

    @abstractmethod
    def update_one(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> WriteResult:
        """
        Update a single document.

        Args:
            filter: MongoDB query filter
            update: Update operations (e.g., {"$set": {...}})
            upsert: Create document if not found

        Returns:
            WriteResult with match/modify counts
        """
        pass

    @abstractmethod
    def count_documents(self, filter: Dict[str, Any]) -> int:
        """
        Count documents matching the filter.

        Args:
            filter: MongoDB query filter

        Returns:
            Count of matching documents
        """
        pass

    @abstractmethod
    def find_by_job_id(self, job_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Find operation runs for a specific job.

        Args:
            job_id: The job ID to search for
            limit: Maximum number of records to return

        Returns:
            List of operation run documents
        """
        pass

    @abstractmethod
    def find_by_run_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a specific operation run by run ID.

        Args:
            run_id: The operation run ID

        Returns:
            Operation run document or None
        """
        pass


class AtlasOperationRunsRepository(OperationRunsRepositoryInterface):
    """
    Atlas MongoDB implementation of OperationRunsRepository.
    """

    _client: Optional[MongoClient] = None
    _collection_name: str = "operation_runs"

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        database: str = "jobs",
        collection: str = "operation_runs",
    ):
        """
        Initialize the repository.

        Args:
            mongodb_uri: MongoDB connection string (defaults to MONGODB_URI env var)
            database: Database name
            collection: Collection name
        """
        self._mongodb_uri = mongodb_uri or os.getenv("MONGODB_URI")
        self._database = database
        self._collection_name = collection

        if not self._mongodb_uri:
            raise ValueError("MongoDB URI is required")

    def _get_client(self) -> MongoClient:
        """Get or create the MongoDB client (singleton)."""
        if AtlasOperationRunsRepository._client is None:
            AtlasOperationRunsRepository._client = MongoClient(self._mongodb_uri)
            logger.info("Created new MongoDB client for operation_runs repository")
        return AtlasOperationRunsRepository._client

    def _get_collection(self):
        """Get the operation_runs collection."""
        client = self._get_client()
        return client[self._database][self._collection_name]

    @classmethod
    def reset_connection(cls) -> None:
        """Reset the MongoDB client connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            logger.info("Operation runs repository connection reset")

    def find_one(
        self, filter: Dict[str, Any], projection: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find a single operation run document."""
        collection = self._get_collection()
        return collection.find_one(filter, projection)

    def find(
        self,
        filter: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        limit: int = 0,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """Find multiple operation run documents."""
        collection = self._get_collection()
        cursor = collection.find(filter, projection)

        if sort:
            cursor = cursor.sort(sort)
        if skip > 0:
            cursor = cursor.skip(skip)
        if limit > 0:
            cursor = cursor.limit(limit)

        return list(cursor)

    def insert_one(self, document: Dict[str, Any]) -> WriteResult:
        """Insert a new operation run record."""
        try:
            collection = self._get_collection()
            result = collection.insert_one(document)
            return WriteResult(
                matched_count=0,
                modified_count=0,
                upserted_id=result.inserted_id,
            )
        except Exception as e:
            logger.error(f"Error inserting operation run: {e}")
            raise

    def update_one(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> WriteResult:
        """Update a single document."""
        collection = self._get_collection()
        result = collection.update_one(filter, update, upsert=upsert)

        return WriteResult(
            matched_count=result.matched_count,
            modified_count=result.modified_count,
            upserted_id=str(result.upserted_id) if result.upserted_id else None,
            atlas_success=True,
            vps_success=None,
        )

    def count_documents(self, filter: Dict[str, Any]) -> int:
        """Count documents matching the filter."""
        collection = self._get_collection()
        return collection.count_documents(filter)

    def find_by_job_id(self, job_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Find operation runs for a specific job."""
        return self.find(
            filter={"job_id": job_id},
            sort=[("timestamp", -1)],
            limit=limit,
        )

    def find_by_run_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Find a specific operation run by run ID."""
        return self.find_one({"run_id": run_id})


# Singleton instance
_operation_runs_repository_instance: Optional[OperationRunsRepositoryInterface] = None


def get_operation_runs_repository() -> OperationRunsRepositoryInterface:
    """
    Get the operation runs repository instance (singleton).

    Returns:
        OperationRunsRepositoryInterface implementation
    """
    global _operation_runs_repository_instance

    if _operation_runs_repository_instance is None:
        _operation_runs_repository_instance = AtlasOperationRunsRepository()
        logger.info("Initialized operation runs repository")

    return _operation_runs_repository_instance


def reset_operation_runs_repository() -> None:
    """Reset the repository singleton."""
    global _operation_runs_repository_instance

    if _operation_runs_repository_instance is not None:
        if isinstance(_operation_runs_repository_instance, AtlasOperationRunsRepository):
            AtlasOperationRunsRepository.reset_connection()

    _operation_runs_repository_instance = None
    logger.info("Operation runs repository singleton reset")
