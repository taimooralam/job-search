"""
Company Cache Repository

Repository interface for the company_cache collection.
Stores cached company research data with TTL.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pymongo import MongoClient

logger = logging.getLogger(__name__)


class CompanyCacheRepositoryInterface(ABC):
    """
    Abstract interface for company cache collection.

    The company_cache collection stores:
    - Cached company research results with TTL (7 days default)
    - Company summaries, URLs, and structured research data
    """

    @abstractmethod
    def find_by_company_key(self, company_key: str) -> Optional[Dict[str, Any]]:
        """
        Find cached company data by normalized key.

        Args:
            company_key: Normalized company name (lowercase, stripped)

        Returns:
            Cached document or None
        """
        pass

    @abstractmethod
    def upsert_cache(self, company_key: str, cache_data: Dict[str, Any]) -> bool:
        """
        Upsert company cache entry.

        Args:
            company_key: Normalized company name
            cache_data: Cache document to store

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def ensure_indexes(self) -> None:
        """Ensure required indexes exist (including TTL index)."""
        pass


class AtlasCompanyCacheRepository(CompanyCacheRepositoryInterface):
    """
    Atlas MongoDB implementation of CompanyCacheRepository.
    """

    _client: Optional[MongoClient] = None
    # TTL in seconds (7 days)
    CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        database: str = "jobs",
        collection: str = "company_cache",
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
        if AtlasCompanyCacheRepository._client is None:
            AtlasCompanyCacheRepository._client = MongoClient(self._mongodb_uri)
            logger.info("Created new MongoDB client for company_cache repository")
        return AtlasCompanyCacheRepository._client

    def _get_collection(self):
        """Get the company_cache collection."""
        client = self._get_client()
        return client[self._database][self._collection_name]

    @classmethod
    def reset_connection(cls) -> None:
        """Reset the MongoDB client connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            logger.info("Company cache repository connection reset")

    def find_by_company_key(self, company_key: str) -> Optional[Dict[str, Any]]:
        """Find cached company data by normalized key."""
        collection = self._get_collection()
        return collection.find_one({"company_key": company_key})

    def upsert_cache(self, company_key: str, cache_data: Dict[str, Any]) -> bool:
        """Upsert company cache entry."""
        try:
            collection = self._get_collection()
            collection.update_one(
                {"company_key": company_key},
                {"$set": cache_data},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"Error upserting company cache for {company_key}: {e}")
            return False

    def ensure_indexes(self) -> None:
        """Ensure required indexes exist (including TTL index)."""
        try:
            collection = self._get_collection()
            # TTL index for automatic expiration
            collection.create_index(
                "cached_at",
                expireAfterSeconds=self.CACHE_TTL_SECONDS,
                background=True,
            )
            logger.info("Company cache indexes ensured")
        except Exception as e:
            logger.warning(f"Error creating company cache indexes: {e}")


# Singleton instance
_company_cache_repository_instance: Optional[CompanyCacheRepositoryInterface] = None


def get_company_cache_repository() -> CompanyCacheRepositoryInterface:
    """
    Get the company cache repository instance (singleton).

    Returns:
        CompanyCacheRepositoryInterface implementation
    """
    global _company_cache_repository_instance

    if _company_cache_repository_instance is None:
        _company_cache_repository_instance = AtlasCompanyCacheRepository()
        logger.info("Initialized company cache repository")

    return _company_cache_repository_instance


def reset_company_cache_repository() -> None:
    """Reset the repository singleton."""
    global _company_cache_repository_instance

    if _company_cache_repository_instance is not None:
        if isinstance(_company_cache_repository_instance, AtlasCompanyCacheRepository):
            AtlasCompanyCacheRepository.reset_connection()

    _company_cache_repository_instance = None
    logger.info("Company cache repository singleton reset")
