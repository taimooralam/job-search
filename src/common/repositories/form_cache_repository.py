"""
Form Cache Repository

Repository interface for the application_form_cache collection.
Stores cached scraped application form fields by URL.
"""

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

logger = logging.getLogger(__name__)


class FormCacheRepositoryInterface(ABC):
    """
    Abstract interface for application form cache collection.

    The application_form_cache collection stores:
    - Scraped form fields by application URL
    - Form type (workday, greenhouse, lever, etc.)
    - Form title
    - Scraped timestamp for cache freshness
    """

    @abstractmethod
    def find_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Find cached form data by application URL.

        Args:
            url: Application form URL

        Returns:
            Cached document or None if not found
        """
        pass

    @abstractmethod
    def upsert_cache(
        self,
        url: str,
        fields: List[Dict[str, Any]],
        form_type: str,
        form_title: Optional[str],
    ) -> bool:
        """
        Upsert form cache entry.

        Args:
            url: Application form URL
            fields: List of extracted form fields
            form_type: Type of ATS/form system
            form_title: Title of the form

        Returns:
            True if successful
        """
        pass


class AtlasFormCacheRepository(FormCacheRepositoryInterface):
    """
    Atlas MongoDB implementation of FormCacheRepository.
    """

    _client: Optional[MongoClient] = None

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        database: str = "jobs",
        collection: str = "application_form_cache",
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
        if AtlasFormCacheRepository._client is None:
            AtlasFormCacheRepository._client = MongoClient(self._mongodb_uri)
            logger.info("Created new MongoDB client for form_cache repository")
        return AtlasFormCacheRepository._client

    def _get_collection(self):
        """Get the application_form_cache collection."""
        client = self._get_client()
        return client[self._database][self._collection_name]

    @classmethod
    def reset_connection(cls) -> None:
        """Reset the MongoDB client connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            logger.info("Form cache repository connection reset")

    def find_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Find cached form data by application URL."""
        collection = self._get_collection()
        return collection.find_one({"url": url})

    def upsert_cache(
        self,
        url: str,
        fields: List[Dict[str, Any]],
        form_type: str,
        form_title: Optional[str],
    ) -> bool:
        """Upsert form cache entry."""
        try:
            collection = self._get_collection()
            doc = {
                "url": url,
                "fields": fields,
                "form_type": form_type,
                "form_title": form_title,
                "scraped_at": datetime.utcnow(),
            }
            collection.update_one(
                {"url": url},
                {"$set": doc},
                upsert=True,
            )
            logger.info(f"Cached {len(fields)} form fields for: {url[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Error upserting form cache for {url}: {e}")
            return False


# Singleton instance
_form_cache_repository_instance: Optional[FormCacheRepositoryInterface] = None


def get_form_cache_repository() -> FormCacheRepositoryInterface:
    """
    Get the form cache repository instance (singleton).

    Returns:
        FormCacheRepositoryInterface implementation
    """
    global _form_cache_repository_instance

    if _form_cache_repository_instance is None:
        _form_cache_repository_instance = AtlasFormCacheRepository()
        logger.info("Initialized form cache repository")

    return _form_cache_repository_instance


def reset_form_cache_repository() -> None:
    """Reset the repository singleton."""
    global _form_cache_repository_instance

    if _form_cache_repository_instance is not None:
        if isinstance(_form_cache_repository_instance, AtlasFormCacheRepository):
            AtlasFormCacheRepository.reset_connection()

    _form_cache_repository_instance = None
    logger.info("Form cache repository singleton reset")
