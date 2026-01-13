"""
Repository Interface Definitions

Defines the abstract interface for job repository operations.
This enables swapping implementations (Atlas-only, dual-write, VPS-primary)
without changing consumer code.

NOTE: This is a copy for frontend/Vercel deployment.
Keep in sync with src/common/repositories/base.py
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
    def find_one(
        self, filter: Dict[str, Any], projection: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find a single job document."""
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
        """Find multiple job documents."""
        pass

    @abstractmethod
    def count_documents(self, filter: Dict[str, Any]) -> int:
        """Count documents matching the filter."""
        pass

    @abstractmethod
    def update_one(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> WriteResult:
        """Update a single document."""
        pass

    @abstractmethod
    def update_many(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
    ) -> WriteResult:
        """Update multiple documents."""
        pass

    @abstractmethod
    def delete_one(self, filter: Dict[str, Any]) -> WriteResult:
        """Delete a single document."""
        pass

    @abstractmethod
    def delete_many(self, filter: Dict[str, Any]) -> WriteResult:
        """Delete multiple documents."""
        pass

    @abstractmethod
    def insert_one(self, document: Dict[str, Any]) -> WriteResult:
        """Insert a single document."""
        pass

    @abstractmethod
    def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run an aggregation pipeline."""
        pass
