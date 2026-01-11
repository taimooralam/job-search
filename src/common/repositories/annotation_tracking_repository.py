"""
Annotation Tracking Repository

Repository interface for the annotation_tracking collection.
Stores application tracking records for persona A/B testing and annotation effectiveness.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

logger = logging.getLogger(__name__)


class AnnotationTrackingRepositoryInterface(ABC):
    """
    Abstract interface for annotation tracking collection.

    The annotation_tracking collection stores:
    - Application tracking records with persona variants
    - Annotation outcomes linked to application outcomes
    - Data for effectiveness analysis and A/B testing
    """

    @abstractmethod
    def upsert_tracking(self, job_id: str, tracking_data: Dict[str, Any]) -> bool:
        """
        Upsert a tracking record by job_id.

        Args:
            job_id: The job identifier
            tracking_data: Complete tracking record data

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def find_by_job_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a tracking record by job_id.

        Args:
            job_id: The job identifier

        Returns:
            Tracking document or None
        """
        pass

    @abstractmethod
    def find_all(self) -> List[Dict[str, Any]]:
        """
        Find all tracking records.

        Returns:
            List of all tracking documents
        """
        pass


class AtlasAnnotationTrackingRepository(AnnotationTrackingRepositoryInterface):
    """
    Atlas MongoDB implementation of AnnotationTrackingRepository.
    """

    _client: Optional[MongoClient] = None

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        database: str = "jobs",
        collection: str = "annotation_tracking",
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
        if AtlasAnnotationTrackingRepository._client is None:
            AtlasAnnotationTrackingRepository._client = MongoClient(self._mongodb_uri)
            logger.info("Created new MongoDB client for annotation_tracking repository")
        return AtlasAnnotationTrackingRepository._client

    def _get_collection(self):
        """Get the annotation_tracking collection."""
        client = self._get_client()
        return client[self._database][self._collection_name]

    @classmethod
    def reset_connection(cls) -> None:
        """Reset the MongoDB client connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            logger.info("Annotation tracking repository connection reset")

    def upsert_tracking(self, job_id: str, tracking_data: Dict[str, Any]) -> bool:
        """Upsert a tracking record by job_id."""
        try:
            collection = self._get_collection()
            collection.update_one(
                {"job_id": job_id},
                {"$set": tracking_data},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"Error upserting tracking for job {job_id}: {e}")
            return False

    def find_by_job_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Find a tracking record by job_id."""
        collection = self._get_collection()
        return collection.find_one({"job_id": job_id})

    def find_all(self) -> List[Dict[str, Any]]:
        """Find all tracking records."""
        collection = self._get_collection()
        return list(collection.find())


# Singleton instance
_annotation_tracking_repository_instance: Optional[AnnotationTrackingRepositoryInterface] = None


def get_annotation_tracking_repository() -> AnnotationTrackingRepositoryInterface:
    """
    Get the annotation tracking repository instance (singleton).

    Returns:
        AnnotationTrackingRepositoryInterface implementation
    """
    global _annotation_tracking_repository_instance

    if _annotation_tracking_repository_instance is None:
        _annotation_tracking_repository_instance = AtlasAnnotationTrackingRepository()
        logger.info("Initialized annotation tracking repository")

    return _annotation_tracking_repository_instance


def reset_annotation_tracking_repository() -> None:
    """Reset the repository singleton."""
    global _annotation_tracking_repository_instance

    if _annotation_tracking_repository_instance is not None:
        if isinstance(_annotation_tracking_repository_instance, AtlasAnnotationTrackingRepository):
            AtlasAnnotationTrackingRepository.reset_connection()

    _annotation_tracking_repository_instance = None
    logger.info("Annotation tracking repository singleton reset")
