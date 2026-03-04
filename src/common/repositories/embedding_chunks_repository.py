"""
Embedding Chunks Repository Implementation

Repository pattern for the embedding_chunks collection.
Stores sentence embeddings in chunks to avoid MongoDB's 16MB BSON limit.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from .base import WriteResult

logger = logging.getLogger(__name__)


class EmbeddingChunksRepositoryInterface(ABC):
    """
    Abstract interface for embedding_chunks collection operations.

    The embedding_chunks collection stores sentence embeddings in chunks,
    each chunk containing up to 1000 vectors (384-dim each, ~3.5MB per chunk).

    Chunk document schema:
    {
        "_id": ObjectId,
        "version": int,          # Rebuild version (matches priors.version)
        "chunk_index": int,      # 0-indexed position
        "embeddings": [[float]], # Up to 1000 vectors (384-dim each)
        "texts": [str],          # Corresponding annotation texts
        "metadata": [dict],      # Annotation values per text
        "count": int,            # Number of entries in this chunk
        "created_at": str,       # ISO timestamp
    }
    """

    @abstractmethod
    def find(
        self,
        filter: Dict[str, Any],
        sort: Optional[List[tuple]] = None,
    ) -> List[Dict[str, Any]]:
        """Find chunks matching filter, optionally sorted."""
        pass

    @abstractmethod
    def insert_many(self, documents: List[Dict[str, Any]]) -> WriteResult:
        """Insert multiple chunk documents."""
        pass

    @abstractmethod
    def delete_many(self, filter: Dict[str, Any]) -> int:
        """Delete chunks matching filter. Returns deleted count."""
        pass

    @abstractmethod
    def create_index(self, keys: List[tuple], **kwargs) -> str:
        """Create an index on the collection."""
        pass


class AtlasEmbeddingChunksRepository(EmbeddingChunksRepositoryInterface):
    """
    Atlas-only repository for embedding_chunks collection.

    Follows the same singleton pattern as AtlasPriorsRepository.
    """

    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None
    _collection: Optional[Collection] = None

    def __init__(
        self,
        mongodb_uri: str,
        database: str = "jobs",
        collection: str = "embedding_chunks",
    ):
        self._mongodb_uri = mongodb_uri
        self._database_name = database
        self._collection_name = collection

    def _get_collection(self) -> Collection:
        """Get the MongoDB collection, creating client if needed."""
        if AtlasEmbeddingChunksRepository._collection is None:
            AtlasEmbeddingChunksRepository._client = MongoClient(self._mongodb_uri)
            AtlasEmbeddingChunksRepository._db = (
                AtlasEmbeddingChunksRepository._client[self._database_name]
            )
            AtlasEmbeddingChunksRepository._collection = (
                AtlasEmbeddingChunksRepository._db[self._collection_name]
            )
            # Create compound index for efficient version-scoped queries
            AtlasEmbeddingChunksRepository._collection.create_index(
                [("version", 1), ("chunk_index", 1)],
                background=True,
            )
            logger.info(
                f"Atlas embedding chunks repository connected: "
                f"{self._database_name}.{self._collection_name}"
            )
        return AtlasEmbeddingChunksRepository._collection

    def find(
        self,
        filter: Dict[str, Any],
        sort: Optional[List[tuple]] = None,
    ) -> List[Dict[str, Any]]:
        """Find chunks matching filter, optionally sorted."""
        collection = self._get_collection()
        cursor = collection.find(filter)
        if sort:
            cursor = cursor.sort(sort)
        return list(cursor)

    def insert_many(self, documents: List[Dict[str, Any]]) -> WriteResult:
        """Insert multiple chunk documents."""
        collection = self._get_collection()
        result = collection.insert_many(documents)
        return WriteResult(
            matched_count=0,
            modified_count=len(result.inserted_ids),
            atlas_success=True,
            vps_success=None,
        )

    def delete_many(self, filter: Dict[str, Any]) -> int:
        """Delete chunks matching filter. Returns deleted count."""
        collection = self._get_collection()
        result = collection.delete_many(filter)
        return result.deleted_count

    def create_index(self, keys: List[tuple], **kwargs) -> str:
        """Create an index on the collection."""
        collection = self._get_collection()
        return collection.create_index(keys, **kwargs)

    @classmethod
    def reset_connection(cls) -> None:
        """Reset the connection pool."""
        if cls._client:
            cls._client.close()
        cls._client = None
        cls._db = None
        cls._collection = None
        logger.info("Atlas embedding chunks repository connection reset")
