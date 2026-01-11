"""
System State Repository

Repository interface for the system_state collection.
Stores ingestion state, run history, and other system-level state.
"""

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

from pymongo import MongoClient

logger = logging.getLogger(__name__)


class SystemStateRepositoryInterface(ABC):
    """
    Abstract interface for system state operations.

    The system_state collection stores:
    - Ingestion state (last_fetch_at, run history)
    - Other system-level state keyed by _id
    """

    @abstractmethod
    def get_state(self, state_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a state document by ID.

        Args:
            state_id: The state document ID (e.g., "ingest_himalayas_auto")

        Returns:
            State document or None if not found
        """
        pass

    @abstractmethod
    def set_state(self, state_id: str, data: Dict[str, Any], upsert: bool = True) -> bool:
        """
        Set/update a state document.

        Args:
            state_id: The state document ID
            data: Fields to set (uses $set operator)
            upsert: Create if doesn't exist (default True)

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def push_to_array(
        self,
        state_id: str,
        array_field: str,
        value: Any,
        max_size: Optional[int] = None
    ) -> bool:
        """
        Push a value to an array field with optional size limit.

        Args:
            state_id: The state document ID
            array_field: Name of the array field
            value: Value to push
            max_size: Optional max array size (uses $slice)

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def delete_state(self, state_id: str) -> bool:
        """
        Delete a state document.

        Args:
            state_id: The state document ID

        Returns:
            True if deleted, False if not found
        """
        pass


class AtlasSystemStateRepository(SystemStateRepositoryInterface):
    """
    Atlas MongoDB implementation of SystemStateRepository.
    """

    _client: Optional[MongoClient] = None
    _collection_name: str = "system_state"

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        database: str = "jobs",
        collection: str = "system_state",
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
        if AtlasSystemStateRepository._client is None:
            AtlasSystemStateRepository._client = MongoClient(self._mongodb_uri)
            logger.info("Created new MongoDB client for system_state repository")
        return AtlasSystemStateRepository._client

    def _get_collection(self):
        """Get the system_state collection."""
        client = self._get_client()
        return client[self._database][self._collection_name]

    @classmethod
    def reset_connection(cls) -> None:
        """Reset the MongoDB client connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            logger.info("System state repository connection reset")

    def get_state(self, state_id: str) -> Optional[Dict[str, Any]]:
        """Get a state document by ID."""
        collection = self._get_collection()
        return collection.find_one({"_id": state_id})

    def set_state(self, state_id: str, data: Dict[str, Any], upsert: bool = True) -> bool:
        """Set/update a state document."""
        try:
            collection = self._get_collection()
            result = collection.update_one(
                {"_id": state_id},
                {"$set": data},
                upsert=upsert,
            )
            return result.modified_count > 0 or result.upserted_id is not None
        except Exception as e:
            logger.error(f"Error setting state {state_id}: {e}")
            return False

    def push_to_array(
        self,
        state_id: str,
        array_field: str,
        value: Any,
        max_size: Optional[int] = None
    ) -> bool:
        """Push a value to an array field with optional size limit."""
        try:
            collection = self._get_collection()

            if max_size is not None:
                # Use $push with $each and $slice for size limit
                update = {
                    "$push": {
                        array_field: {
                            "$each": [value],
                            "$slice": -max_size,  # Keep last N items
                        }
                    }
                }
            else:
                update = {"$push": {array_field: value}}

            result = collection.update_one({"_id": state_id}, update)
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error pushing to array {array_field} in {state_id}: {e}")
            return False

    def delete_state(self, state_id: str) -> bool:
        """Delete a state document."""
        try:
            collection = self._get_collection()
            result = collection.delete_one({"_id": state_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting state {state_id}: {e}")
            return False


# Singleton instance
_system_state_repository_instance: Optional[SystemStateRepositoryInterface] = None


def get_system_state_repository() -> SystemStateRepositoryInterface:
    """
    Get the system state repository instance (singleton).

    Returns:
        SystemStateRepositoryInterface implementation
    """
    global _system_state_repository_instance

    if _system_state_repository_instance is None:
        _system_state_repository_instance = AtlasSystemStateRepository()
        logger.info("Initialized system state repository")

    return _system_state_repository_instance


def reset_system_state_repository() -> None:
    """Reset the repository singleton."""
    global _system_state_repository_instance

    if _system_state_repository_instance is not None:
        if isinstance(_system_state_repository_instance, AtlasSystemStateRepository):
            AtlasSystemStateRepository.reset_connection()

    _system_state_repository_instance = None
    logger.info("System state repository singleton reset")
