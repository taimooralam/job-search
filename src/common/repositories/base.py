"""
Repository Interface Definitions

Defines the abstract interface for job repository operations.
This enables swapping implementations (Atlas-only, dual-write, VPS-primary)
without changing consumer code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class WriteResult:
    """
    Result of a write operation with sync status.

    Attributes:
        matched_count: Number of documents that matched the filter
        modified_count: Number of documents actually modified
        upserted_id: ID of upserted document (if any)
        atlas_success: Whether Atlas write succeeded
        vps_success: Whether VPS write succeeded (None if VPS disabled)
        vps_error: Error message if VPS write failed
    """
    matched_count: int
    modified_count: int
    upserted_id: Optional[str] = None
    atlas_success: bool = True
    vps_success: Optional[bool] = None
    vps_error: Optional[str] = None


class JobRepositoryInterface(ABC):
    """
    Abstract interface for level-2 job collection operations.

    Implementations:
    - AtlasJobRepository: Atlas-only (Phase 1)
    - DualWriteJobRepository: Atlas + VPS sync (Phase 3+)

    All methods follow fail-fast semantics for Atlas operations.
    VPS operations use fail-open with background reconciliation.
    """

    @abstractmethod
    def find_one(self, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find a single job document.

        Args:
            filter: MongoDB query filter (e.g., {"_id": ObjectId(...)})

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
        Find multiple job documents.

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
    def update_one(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> WriteResult:
        """
        Update a single document. Fail-fast on Atlas error.

        Args:
            filter: MongoDB query filter
            update: Update operations (e.g., {"$set": {...}})
            upsert: Create document if not found

        Returns:
            WriteResult with match/modify counts and sync status

        Raises:
            Exception: If Atlas write fails (fail-fast behavior)
        """
        pass

    @abstractmethod
    def update_many(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
    ) -> WriteResult:
        """
        Update multiple documents. Fail-fast on Atlas error.

        Args:
            filter: MongoDB query filter
            update: Update operations

        Returns:
            WriteResult with match/modify counts and sync status

        Raises:
            Exception: If Atlas write fails (fail-fast behavior)
        """
        pass

    @abstractmethod
    def delete_one(self, filter: Dict[str, Any]) -> WriteResult:
        """
        Delete a single document.

        Args:
            filter: MongoDB query filter

        Returns:
            WriteResult with delete count
        """
        pass

    @abstractmethod
    def delete_many(self, filter: Dict[str, Any]) -> WriteResult:
        """
        Delete multiple documents.

        Args:
            filter: MongoDB query filter

        Returns:
            WriteResult with delete count
        """
        pass

    @abstractmethod
    def insert_one(self, document: Dict[str, Any]) -> WriteResult:
        """
        Insert a single document.

        Args:
            document: Document to insert

        Returns:
            WriteResult with upserted_id set to the new document's _id
        """
        pass

    @abstractmethod
    def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run an aggregation pipeline.

        Args:
            pipeline: MongoDB aggregation pipeline stages

        Returns:
            List of aggregation result documents
        """
        pass
