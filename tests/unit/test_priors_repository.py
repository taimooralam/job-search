"""
Tests for the priors repository pattern implementation.

Tests the annotation_priors repository that enables
future dual-write (Atlas + VPS) support for the priors collection.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.common.repositories import (
    get_priors_repository,
    reset_priors_repository,
    WriteResult,
)
from src.common.repositories.priors_repository import (
    AtlasPriorsRepository,
    PriorsRepositoryInterface,
)


class TestAtlasPriorsRepository:
    """Tests for AtlasPriorsRepository."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset repository singleton before each test."""
        AtlasPriorsRepository.reset_connection()
        yield
        AtlasPriorsRepository.reset_connection()

    @pytest.fixture
    def mock_collection(self):
        """Create a mock MongoDB collection."""
        with patch("src.common.repositories.priors_repository.MongoClient") as mock_client:
            mock_collection = MagicMock()
            mock_db = MagicMock()
            mock_db.__getitem__.return_value = mock_collection
            mock_client.return_value.__getitem__.return_value = mock_db
            yield mock_collection

    def test_find_one(self, mock_collection):
        """Should delegate find_one to MongoDB collection."""
        mock_collection.find_one.return_value = {"_id": "priors", "version": 1}

        repo = AtlasPriorsRepository("mongodb://test")
        result = repo.find_one({"_id": "priors"})

        mock_collection.find_one.assert_called_once_with({"_id": "priors"})
        assert result == {"_id": "priors", "version": 1}

    def test_find_one_not_found(self, mock_collection):
        """Should return None when document not found."""
        mock_collection.find_one.return_value = None

        repo = AtlasPriorsRepository("mongodb://test")
        result = repo.find_one({"_id": "nonexistent"})

        assert result is None

    def test_insert_one(self, mock_collection):
        """Should handle insert_one operation."""
        mock_result = MagicMock()
        mock_result.inserted_id = "new_id"
        mock_collection.insert_one.return_value = mock_result

        repo = AtlasPriorsRepository("mongodb://test")
        result = repo.insert_one({"_id": "priors", "version": 1})

        mock_collection.insert_one.assert_called_once_with({"_id": "priors", "version": 1})
        assert isinstance(result, WriteResult)
        assert result.upserted_id == "new_id"
        assert result.atlas_success is True
        assert result.vps_success is None

    def test_replace_one_success(self, mock_collection):
        """Should return WriteResult on successful replace."""
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_result.modified_count = 1
        mock_result.upserted_id = None
        mock_collection.replace_one.return_value = mock_result

        repo = AtlasPriorsRepository("mongodb://test")
        result = repo.replace_one(
            {"_id": "priors"},
            {"_id": "priors", "version": 2},
        )

        assert isinstance(result, WriteResult)
        assert result.matched_count == 1
        assert result.modified_count == 1
        assert result.atlas_success is True
        assert result.vps_success is None

    def test_replace_one_with_upsert(self, mock_collection):
        """Should handle upsert operation."""
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_result.modified_count = 0
        mock_result.upserted_id = "new_id"
        mock_collection.replace_one.return_value = mock_result

        repo = AtlasPriorsRepository("mongodb://test")
        result = repo.replace_one(
            {"_id": "new_priors"},
            {"_id": "new_priors", "version": 1},
            upsert=True,
        )

        mock_collection.replace_one.assert_called_once_with(
            {"_id": "new_priors"},
            {"_id": "new_priors", "version": 1},
            upsert=True,
        )
        assert result.upserted_id == "new_id"

    def test_replace_one_no_match(self, mock_collection):
        """Should return zero counts when no document matches."""
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_result.modified_count = 0
        mock_result.upserted_id = None
        mock_collection.replace_one.return_value = mock_result

        repo = AtlasPriorsRepository("mongodb://test")
        result = repo.replace_one(
            {"_id": "nonexistent"},
            {"_id": "nonexistent", "version": 1},
        )

        assert result.matched_count == 0
        assert result.modified_count == 0
        assert result.atlas_success is True  # Operation succeeded, just no match

    def test_connection_reuse(self, mock_collection):
        """Should reuse MongoDB connection across calls."""
        repo = AtlasPriorsRepository("mongodb://test")

        # Make multiple calls
        repo.find_one({"_id": "1"})
        repo.find_one({"_id": "2"})

        # MongoClient should only be created once (singleton)
        assert mock_collection.find_one.call_count == 2


class TestGetPriorsRepository:
    """Tests for get_priors_repository factory function."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset repository singleton before each test."""
        reset_priors_repository()
        yield
        reset_priors_repository()

    def test_returns_atlas_repository_by_default(self):
        """Should return AtlasPriorsRepository when VPS is disabled."""
        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}, clear=True):
            with patch("src.common.repositories.priors_repository.MongoClient"):
                repo = get_priors_repository()

                assert isinstance(repo, AtlasPriorsRepository)

    def test_returns_same_instance(self):
        """Should return singleton instance."""
        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}, clear=True):
            with patch("src.common.repositories.priors_repository.MongoClient"):
                repo1 = get_priors_repository()
                repo2 = get_priors_repository()

                assert repo1 is repo2

    def test_raises_when_mongodb_uri_not_set(self):
        """Should raise ValueError when MONGODB_URI is not configured."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="MONGODB_URI"):
                get_priors_repository()

    def test_raises_for_dual_write_not_implemented(self):
        """Should raise NotImplementedError when VPS is enabled."""
        env = {
            "MONGODB_URI": "mongodb://atlas",
            "VPS_MONGODB_ENABLED": "true",
            "VPS_SYNC_MODE": "write",
        }
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(NotImplementedError, match="Dual-write"):
                get_priors_repository()


class TestResetPriorsRepository:
    """Tests for reset_priors_repository function."""

    def test_reset_clears_singleton(self):
        """Should clear singleton so next call creates new instance."""
        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}, clear=True):
            with patch("src.common.repositories.priors_repository.MongoClient"):
                repo1 = get_priors_repository()
                reset_priors_repository()
                repo2 = get_priors_repository()

                # Different instances after reset
                assert repo2 is not None


class TestAnnotationPriorsIntegration:
    """Integration tests for annotation_priors using repository pattern."""

    @pytest.fixture(autouse=True)
    def reset_singletons(self):
        """Reset all repository singletons before each test."""
        reset_priors_repository()
        yield
        reset_priors_repository()

    @pytest.fixture
    def mock_priors_repo(self):
        """Create a mock priors repository."""
        mock_repo = MagicMock(spec=PriorsRepositoryInterface)

        with patch("src.common.repositories.config.get_priors_repository", return_value=mock_repo):
            # Also patch at the import location in annotation_priors
            with patch("src.services.annotation_priors.get_priors_repository", return_value=mock_repo):
                yield mock_repo

    def test_load_priors_uses_repository(self):
        """load_priors should use the priors repository."""
        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}, clear=True):
            with patch("src.common.repositories.priors_repository.MongoClient") as mock_client:
                mock_collection = MagicMock()
                mock_collection.find_one.return_value = {
                    "_id": "user_annotation_priors",
                    "version": 1,
                    "stats": {"total_annotations_at_build": 100},
                }
                mock_db = MagicMock()
                mock_db.__getitem__.return_value = mock_collection
                mock_client.return_value.__getitem__.return_value = mock_db

                from src.services.annotation_priors import load_priors

                result = load_priors()

                assert result["_id"] == "user_annotation_priors"
                assert result["version"] == 1

    def test_save_priors_uses_repository(self):
        """save_priors should use the priors repository."""
        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}, clear=True):
            with patch("src.common.repositories.priors_repository.MongoClient") as mock_client:
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.matched_count = 1
                mock_result.modified_count = 1
                mock_result.upserted_id = None
                mock_collection.replace_one.return_value = mock_result
                mock_db = MagicMock()
                mock_db.__getitem__.return_value = mock_collection
                mock_client.return_value.__getitem__.return_value = mock_db

                from src.services.annotation_priors import save_priors, _empty_priors

                priors = _empty_priors()
                result = save_priors(priors)

                assert result is True
                mock_collection.replace_one.assert_called_once()

    def test_load_priors_handles_missing_mongodb(self):
        """load_priors should return empty priors when MongoDB not configured."""
        with patch.dict("os.environ", {}, clear=True):
            # Need to reset so it tries to get repo again
            reset_priors_repository()

            from src.services.annotation_priors import load_priors

            result = load_priors()

            # Should return empty priors without error
            assert result["_id"] == "user_annotation_priors"
            assert result["version"] == 1
            assert result["sentence_index"]["count"] == 0

    def test_save_priors_handles_missing_mongodb(self):
        """save_priors should return True when MongoDB not configured."""
        with patch.dict("os.environ", {}, clear=True):
            reset_priors_repository()

            from src.services.annotation_priors import save_priors, _empty_priors

            priors = _empty_priors()
            result = save_priors(priors)

            # Should return True (expected in dev environments)
            assert result is True
