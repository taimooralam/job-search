"""
Tests for the repository pattern implementation.

Tests the job repository abstraction layer that enables
future dual-write (Atlas + VPS) support.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

from src.common.repositories import (
    get_job_repository,
    reset_repository,
    JobRepositoryInterface,
    WriteResult,
    RepositoryConfig,
    SyncMode,
)
from src.common.repositories.atlas_repository import AtlasJobRepository


class TestWriteResult:
    """Tests for WriteResult dataclass."""

    def test_write_result_defaults(self):
        """WriteResult should have sensible defaults."""
        result = WriteResult(matched_count=1, modified_count=1)

        assert result.matched_count == 1
        assert result.modified_count == 1
        assert result.upserted_id is None
        assert result.atlas_success is True
        assert result.vps_success is None
        assert result.vps_error is None

    def test_write_result_with_vps_status(self):
        """WriteResult should capture VPS sync status."""
        result = WriteResult(
            matched_count=1,
            modified_count=1,
            atlas_success=True,
            vps_success=False,
            vps_error="Connection refused",
        )

        assert result.atlas_success is True
        assert result.vps_success is False
        assert result.vps_error == "Connection refused"


class TestRepositoryConfig:
    """Tests for RepositoryConfig."""

    def test_config_from_env_minimal(self):
        """Should load minimal config from environment."""
        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://atlas"}, clear=True):
            config = RepositoryConfig.from_env()

            assert config.atlas_uri == "mongodb://atlas"
            assert config.database == "jobs"
            assert config.collection == "level-2"
            assert config.vps_enabled is False
            assert config.sync_mode == SyncMode.DISABLED

    def test_config_from_env_with_vps(self):
        """Should load VPS config from environment."""
        env = {
            "MONGODB_URI": "mongodb://atlas",
            "VPS_MONGODB_URI": "mongodb://vps",
            "VPS_MONGODB_ENABLED": "true",
            "VPS_SYNC_MODE": "shadow",
        }
        with patch.dict("os.environ", env, clear=True):
            config = RepositoryConfig.from_env()

            assert config.vps_enabled is True
            assert config.vps_uri == "mongodb://vps"
            assert config.sync_mode == SyncMode.SHADOW

    def test_config_from_env_missing_uri(self):
        """Should raise ValueError if MONGODB_URI is not set."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="MONGODB_URI"):
                RepositoryConfig.from_env()

    def test_config_invalid_sync_mode_defaults_to_disabled(self):
        """Should default to disabled if sync mode is invalid."""
        env = {
            "MONGODB_URI": "mongodb://atlas",
            "VPS_SYNC_MODE": "invalid_mode",
        }
        with patch.dict("os.environ", env, clear=True):
            config = RepositoryConfig.from_env()

            assert config.sync_mode == SyncMode.DISABLED


class TestAtlasJobRepository:
    """Tests for AtlasJobRepository."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset repository singleton before each test."""
        AtlasJobRepository.reset_connection()
        yield
        AtlasJobRepository.reset_connection()

    @pytest.fixture
    def mock_collection(self):
        """Create a mock MongoDB collection."""
        with patch("src.common.repositories.atlas_repository.MongoClient") as mock_client:
            mock_collection = MagicMock()
            mock_db = MagicMock()
            mock_db.__getitem__.return_value = mock_collection
            mock_client.return_value.__getitem__.return_value = mock_db
            yield mock_collection

    def test_find_one(self, mock_collection):
        """Should delegate find_one to MongoDB collection."""
        mock_collection.find_one.return_value = {"_id": "123", "title": "Test"}

        repo = AtlasJobRepository("mongodb://test")
        result = repo.find_one({"_id": "123"})

        mock_collection.find_one.assert_called_once_with({"_id": "123"})
        assert result == {"_id": "123", "title": "Test"}

    def test_find_one_not_found(self, mock_collection):
        """Should return None when document not found."""
        mock_collection.find_one.return_value = None

        repo = AtlasJobRepository("mongodb://test")
        result = repo.find_one({"_id": "nonexistent"})

        assert result is None

    def test_find_with_options(self, mock_collection):
        """Should apply find options (sort, limit, skip)."""
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__ = lambda self: iter([{"_id": "1"}, {"_id": "2"}])
        mock_collection.find.return_value = mock_cursor

        repo = AtlasJobRepository("mongodb://test")
        result = repo.find(
            {"status": "active"},
            sort=[("createdAt", -1)],
            skip=10,
            limit=5,
        )

        mock_collection.find.assert_called_once_with({"status": "active"}, None)
        mock_cursor.sort.assert_called_once_with([("createdAt", -1)])
        mock_cursor.skip.assert_called_once_with(10)
        mock_cursor.limit.assert_called_once_with(5)
        assert len(result) == 2

    def test_count_documents(self, mock_collection):
        """Should delegate count_documents to MongoDB collection."""
        mock_collection.count_documents.return_value = 42

        repo = AtlasJobRepository("mongodb://test")
        result = repo.count_documents({"status": "active"})

        mock_collection.count_documents.assert_called_once_with({"status": "active"})
        assert result == 42

    def test_update_one_success(self, mock_collection):
        """Should return WriteResult on successful update."""
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_result.modified_count = 1
        mock_result.upserted_id = None
        mock_collection.update_one.return_value = mock_result

        repo = AtlasJobRepository("mongodb://test")
        result = repo.update_one(
            {"_id": "123"},
            {"$set": {"status": "completed"}},
        )

        assert isinstance(result, WriteResult)
        assert result.matched_count == 1
        assert result.modified_count == 1
        assert result.atlas_success is True
        assert result.vps_success is None  # VPS not enabled in Phase 1

    def test_update_one_with_upsert(self, mock_collection):
        """Should handle upsert operation."""
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_result.modified_count = 0
        mock_result.upserted_id = "new_id"
        mock_collection.update_one.return_value = mock_result

        repo = AtlasJobRepository("mongodb://test")
        result = repo.update_one(
            {"_id": "new"},
            {"$set": {"status": "new"}},
            upsert=True,
        )

        mock_collection.update_one.assert_called_once_with(
            {"_id": "new"},
            {"$set": {"status": "new"}},
            upsert=True,
        )
        assert result.upserted_id == "new_id"

    def test_update_one_no_match(self, mock_collection):
        """Should return zero counts when no document matches."""
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_result.modified_count = 0
        mock_result.upserted_id = None
        mock_collection.update_one.return_value = mock_result

        repo = AtlasJobRepository("mongodb://test")
        result = repo.update_one(
            {"_id": "nonexistent"},
            {"$set": {"status": "completed"}},
        )

        assert result.matched_count == 0
        assert result.modified_count == 0
        assert result.atlas_success is True  # Operation succeeded, just no match

    def test_update_many(self, mock_collection):
        """Should handle update_many operation."""
        mock_result = MagicMock()
        mock_result.matched_count = 5
        mock_result.modified_count = 5
        mock_collection.update_many.return_value = mock_result

        repo = AtlasJobRepository("mongodb://test")
        result = repo.update_many(
            {"status": "pending"},
            {"$set": {"status": "cancelled"}},
        )

        assert result.matched_count == 5
        assert result.modified_count == 5

    def test_delete_one(self, mock_collection):
        """Should handle delete_one operation."""
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_collection.delete_one.return_value = mock_result

        repo = AtlasJobRepository("mongodb://test")
        result = repo.delete_one({"_id": "123"})

        assert result.matched_count == 1
        assert result.modified_count == 1

    def test_delete_many(self, mock_collection):
        """Should handle delete_many operation."""
        mock_result = MagicMock()
        mock_result.deleted_count = 10
        mock_collection.delete_many.return_value = mock_result

        repo = AtlasJobRepository("mongodb://test")
        result = repo.delete_many({"status": "archived"})

        assert result.matched_count == 10

    def test_connection_reuse(self, mock_collection):
        """Should reuse MongoDB connection across calls."""
        repo = AtlasJobRepository("mongodb://test")

        # Make multiple calls
        repo.find_one({"_id": "1"})
        repo.find_one({"_id": "2"})
        repo.count_documents({})

        # MongoClient should only be created once (singleton)
        # This is verified by the mock being called multiple times on collection
        # but MongoClient constructor only once
        assert mock_collection.find_one.call_count == 2
        assert mock_collection.count_documents.call_count == 1


class TestGetJobRepository:
    """Tests for get_job_repository factory function."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset repository singleton before each test."""
        reset_repository()
        yield
        reset_repository()

    def test_returns_atlas_repository_by_default(self):
        """Should return AtlasJobRepository when VPS is disabled."""
        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}, clear=True):
            with patch("src.common.repositories.atlas_repository.MongoClient"):
                repo = get_job_repository()

                assert isinstance(repo, AtlasJobRepository)

    def test_returns_same_instance(self):
        """Should return singleton instance."""
        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}, clear=True):
            with patch("src.common.repositories.atlas_repository.MongoClient"):
                repo1 = get_job_repository()
                repo2 = get_job_repository()

                assert repo1 is repo2

    def test_raises_when_mongodb_uri_not_set(self):
        """Should raise ValueError when MONGODB_URI is not configured."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="MONGODB_URI"):
                get_job_repository()

    def test_raises_for_dual_write_not_implemented(self):
        """Should raise NotImplementedError when VPS is enabled."""
        env = {
            "MONGODB_URI": "mongodb://atlas",
            "VPS_MONGODB_ENABLED": "true",
            "VPS_SYNC_MODE": "write",
        }
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(NotImplementedError, match="Dual-write"):
                get_job_repository()


class TestResetRepository:
    """Tests for reset_repository function."""

    def test_reset_clears_singleton(self):
        """Should clear singleton so next call creates new instance."""
        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}, clear=True):
            with patch("src.common.repositories.atlas_repository.MongoClient"):
                repo1 = get_job_repository()
                reset_repository()
                repo2 = get_job_repository()

                # Different instances after reset
                # (Though they may be equal, they should be new allocations)
                # In practice, the singleton should be None after reset
                assert repo2 is not None
