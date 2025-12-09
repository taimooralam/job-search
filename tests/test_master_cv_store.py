"""
Unit tests for the Master-CV MongoDB Store.

Tests:
- File fallback when MongoDB unavailable
- CRUD operations for metadata, taxonomy, and roles
- Version history tracking
- Rollback functionality

Note: These tests use file fallback mode to avoid requiring a real MongoDB connection.
Integration tests would require a test database.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.common.master_cv_store import (
    DEFAULT_DATA_DIR,
    METADATA_FILE,
    ROLES_DIR,
    TAXONOMY_FILE,
    MasterCVStore,
    get_metadata,
    get_role,
    get_store,
    get_taxonomy,
)


class TestMasterCVStoreFileFallback:
    """Test MasterCVStore with file fallback (no MongoDB)."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary data directory with test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            # Create metadata file
            metadata = {
                "candidate": {
                    "name": "Test Candidate",
                    "title_base": "Test Engineer"
                },
                "roles": [
                    {
                        "id": "01_test_company",
                        "company": "Test Company",
                        "title": "Test Role",
                        "keywords": ["python", "testing"]
                    }
                ]
            }
            with open(data_dir / METADATA_FILE, "w") as f:
                json.dump(metadata, f)

            # Create taxonomy file
            taxonomy = {
                "version": "1.0",
                "target_roles": {
                    "engineering_manager": {
                        "display_name": "Engineering Manager",
                        "sections": [
                            {
                                "name": "Technical Leadership",
                                "priority": 1,
                                "skills": ["Leadership", "Architecture"]
                            }
                        ]
                    }
                },
                "skill_aliases": {
                    "leadership": ["Leadership", "Tech Leadership"]
                },
                "default_fallback_role": "engineering_manager"
            }
            with open(data_dir / TAXONOMY_FILE, "w") as f:
                json.dump(taxonomy, f)

            # Create roles directory with test role
            roles_dir = data_dir / ROLES_DIR
            roles_dir.mkdir()
            with open(roles_dir / "01_test_company.md", "w") as f:
                f.write("# Test Company\n\n## Achievements\n\n### Achievement 1\nTest achievement.")

            yield data_dir

    def test_file_fallback_get_metadata(self, temp_data_dir):
        """Test reading metadata from file when MongoDB unavailable."""
        store = MasterCVStore(use_mongodb=False, data_dir=temp_data_dir)

        metadata = store.get_metadata()

        assert metadata is not None
        assert metadata["candidate"]["name"] == "Test Candidate"
        assert len(metadata["roles"]) == 1
        assert metadata["roles"][0]["company"] == "Test Company"

    def test_file_fallback_get_taxonomy(self, temp_data_dir):
        """Test reading taxonomy from file when MongoDB unavailable."""
        store = MasterCVStore(use_mongodb=False, data_dir=temp_data_dir)

        taxonomy = store.get_taxonomy()

        assert taxonomy is not None
        assert "engineering_manager" in taxonomy["target_roles"]
        assert taxonomy["default_fallback_role"] == "engineering_manager"

    def test_file_fallback_get_role(self, temp_data_dir):
        """Test reading role markdown from file when MongoDB unavailable."""
        store = MasterCVStore(use_mongodb=False, data_dir=temp_data_dir)

        role = store.get_role("01_test_company")

        assert role is not None
        assert role["role_id"] == "01_test_company"
        assert "# Test Company" in role["markdown_content"]
        assert "Achievement 1" in role["markdown_content"]

    def test_file_fallback_get_all_roles(self, temp_data_dir):
        """Test reading all roles from file when MongoDB unavailable."""
        store = MasterCVStore(use_mongodb=False, data_dir=temp_data_dir)

        roles = store.get_all_roles()

        assert len(roles) == 1
        assert roles[0]["role_id"] == "01_test_company"

    def test_file_fallback_missing_file(self, temp_data_dir):
        """Test handling missing files gracefully."""
        # Delete metadata file
        (temp_data_dir / METADATA_FILE).unlink()

        store = MasterCVStore(use_mongodb=False, data_dir=temp_data_dir)
        metadata = store.get_metadata()

        assert metadata is None

    def test_file_fallback_missing_role(self, temp_data_dir):
        """Test handling missing role file gracefully."""
        store = MasterCVStore(use_mongodb=False, data_dir=temp_data_dir)

        role = store.get_role("nonexistent_role")

        assert role is None

    def test_is_connected_false_when_file_fallback(self, temp_data_dir):
        """Test is_connected returns False in file fallback mode."""
        store = MasterCVStore(use_mongodb=False, data_dir=temp_data_dir)

        assert store.is_connected() is False

    def test_update_fails_in_file_fallback_mode(self, temp_data_dir):
        """Test that updates fail gracefully in file fallback mode."""
        store = MasterCVStore(use_mongodb=False, data_dir=temp_data_dir)

        # Update operations should return False
        assert store.update_metadata({"candidate": {}}, "user") is False
        assert store.update_taxonomy({}, "user") is False
        assert store.update_role("test", "content", updated_by="user") is False

    def test_get_stats_file_fallback(self, temp_data_dir):
        """Test get_stats in file fallback mode."""
        store = MasterCVStore(use_mongodb=False, data_dir=temp_data_dir)

        stats = store.get_stats()

        assert stats["mongodb_connected"] is False
        assert stats["metadata_version"] == 1  # File fallback returns version 1
        assert stats["roles_count"] == 1
        assert stats["history_entries"] == 0


class TestMasterCVStoreMongoDB:
    """Test MasterCVStore with mocked MongoDB."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database with collections."""
        mock_database = MagicMock()

        # Mock collections
        mock_database["master_cv_metadata"] = MagicMock()
        mock_database["master_cv_taxonomy"] = MagicMock()
        mock_database["master_cv_roles"] = MagicMock()
        mock_database["master_cv_history"] = MagicMock()

        return mock_database

    @pytest.fixture
    def store_with_mock_db(self, mock_db):
        """Create a store with mocked MongoDB."""
        with patch("src.common.master_cv_store.database_client") as mock_client:
            mock_client.db = mock_db
            store = MasterCVStore(use_mongodb=True)
            store._db = mock_db
            yield store, mock_db

    def test_get_metadata_from_mongodb(self, store_with_mock_db):
        """Test reading metadata from MongoDB."""
        store, mock_db = store_with_mock_db

        mock_db["master_cv_metadata"].find_one.return_value = {
            "_id": "canonical",
            "version": 3,
            "candidate": {"name": "Test"},
            "roles": []
        }

        metadata = store.get_metadata()

        assert metadata is not None
        assert metadata["version"] == 3
        assert "_id" not in metadata  # _id should be removed

    def test_update_metadata_creates_history(self, store_with_mock_db):
        """Test that updating metadata saves version history."""
        store, mock_db = store_with_mock_db

        # Mock current document
        mock_db["master_cv_metadata"].find_one.return_value = {
            "_id": "canonical",
            "version": 1,
            "candidate": {"name": "Old"},
            "roles": []
        }

        result = store.update_metadata(
            {"candidate": {"name": "New"}, "roles": []},
            updated_by="user",
            change_summary="Updated name"
        )

        assert result is True

        # Verify history was saved
        mock_db["master_cv_history"].insert_one.assert_called_once()
        history_call = mock_db["master_cv_history"].insert_one.call_args[0][0]
        assert history_call["collection"] == "master_cv_metadata"
        assert history_call["version"] == 1

        # Verify update was made
        mock_db["master_cv_metadata"].replace_one.assert_called_once()

    def test_get_taxonomy_from_mongodb(self, store_with_mock_db):
        """Test reading taxonomy from MongoDB."""
        store, mock_db = store_with_mock_db

        mock_db["master_cv_taxonomy"].find_one.return_value = {
            "_id": "canonical",
            "version": 2,
            "target_roles": {"engineering_manager": {}},
            "skill_aliases": {},
            "default_fallback_role": "engineering_manager"
        }

        taxonomy = store.get_taxonomy()

        assert taxonomy is not None
        assert taxonomy["version"] == 2
        assert "engineering_manager" in taxonomy["target_roles"]

    def test_add_skill_to_taxonomy(self, store_with_mock_db):
        """Test adding a skill to taxonomy section."""
        store, mock_db = store_with_mock_db

        # Mock current taxonomy
        mock_db["master_cv_taxonomy"].find_one.return_value = {
            "_id": "canonical",
            "version": 1,
            "target_roles": {
                "engineering_manager": {
                    "sections": [
                        {"name": "Technical Leadership", "skills": ["Leadership"]}
                    ]
                }
            },
            "skill_aliases": {},
            "default_fallback_role": "engineering_manager"
        }

        result = store.add_skill_to_taxonomy(
            "engineering_manager",
            "Technical Leadership",
            "Architecture",
            updated_by="user"
        )

        assert result is True

    def test_get_role_from_mongodb(self, store_with_mock_db):
        """Test reading a role from MongoDB."""
        store, mock_db = store_with_mock_db

        mock_db["master_cv_roles"].find_one.return_value = {
            "_id": "01_test",
            "role_id": "01_test",
            "version": 1,
            "markdown_content": "# Test Role",
            "parsed": None
        }

        role = store.get_role("01_test")

        assert role is not None
        assert role["role_id"] == "01_test"
        assert "_id" not in role

    def test_update_role_creates_history(self, store_with_mock_db):
        """Test that updating a role saves version history."""
        store, mock_db = store_with_mock_db

        mock_db["master_cv_roles"].find_one.return_value = {
            "role_id": "01_test",
            "version": 1,
            "markdown_content": "# Old Content",
            "parsed": None
        }

        result = store.update_role(
            "01_test",
            "# New Content",
            parsed={"achievements": []},
            updated_by="user",
            change_summary="Updated content"
        )

        assert result is True

        # Verify history was saved
        mock_db["master_cv_history"].insert_one.assert_called_once()

    def test_get_history(self, store_with_mock_db):
        """Test getting version history."""
        store, mock_db = store_with_mock_db

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = [
            {
                "_id": "history1",
                "collection": "master_cv_metadata",
                "doc_id": "canonical",
                "version": 1,
                "timestamp": "2025-01-01T00:00:00Z"
            }
        ]
        mock_db["master_cv_history"].find.return_value = mock_cursor

        history = store.get_history("master_cv_metadata", limit=10)

        assert len(history) == 1
        assert "_id" not in history[0]

    def test_rollback_to_previous_version(self, store_with_mock_db):
        """Test rolling back to a previous version."""
        store, mock_db = store_with_mock_db

        # Mock history entry
        mock_db["master_cv_history"].find_one.return_value = {
            "_id": "history1",
            "collection": "master_cv_metadata",
            "doc_id": "canonical",
            "version": 1,
            "data": {
                "candidate": {"name": "Old"},
                "roles": []
            }
        }

        # Mock current document for the update
        mock_db["master_cv_metadata"].find_one.return_value = {
            "_id": "canonical",
            "version": 2,
            "candidate": {"name": "New"},
            "roles": []
        }

        result = store.rollback(
            "master_cv_metadata",
            "canonical",
            target_version=1,
            updated_by="user"
        )

        assert result is True

    def test_rollback_nonexistent_version(self, store_with_mock_db):
        """Test rollback fails for nonexistent version."""
        store, mock_db = store_with_mock_db

        mock_db["master_cv_history"].find_one.return_value = None

        result = store.rollback(
            "master_cv_metadata",
            "canonical",
            target_version=999,
            updated_by="user"
        )

        assert result is False


class TestMasterCVStoreHelpers:
    """Test module-level convenience functions."""

    def test_get_store_returns_singleton(self):
        """Test that get_store returns a singleton instance."""
        # Clear any existing instance
        import src.common.master_cv_store as store_module
        store_module._default_store = None

        with patch.object(MasterCVStore, "__init__", return_value=None):
            store1 = get_store(use_mongodb=False)
            store2 = get_store(use_mongodb=False)

            # Both should be the same instance
            assert store1 is store2


class TestMasterCVStoreVersioning:
    """Test version tracking functionality."""

    def test_version_increments_on_update(self):
        """Test that version number increments on each update."""
        with patch("src.common.master_cv_store.database_client") as mock_client:
            mock_db = MagicMock()
            mock_client.db = mock_db

            store = MasterCVStore(use_mongodb=True)
            store._db = mock_db

            # First update (no existing document)
            mock_db["master_cv_metadata"].find_one.return_value = None

            store.update_metadata(
                {"candidate": {}, "roles": []},
                updated_by="user"
            )

            # Get the document that was saved
            call_args = mock_db["master_cv_metadata"].replace_one.call_args
            saved_doc = call_args[0][1]

            assert saved_doc["version"] == 1

    def test_timestamp_format(self):
        """Test that timestamps are in ISO format."""
        with patch("src.common.master_cv_store.database_client") as mock_client:
            mock_db = MagicMock()
            mock_client.db = mock_db

            store = MasterCVStore(use_mongodb=True)
            store._db = mock_db

            mock_db["master_cv_metadata"].find_one.return_value = None

            store.update_metadata(
                {"candidate": {}, "roles": []},
                updated_by="user"
            )

            call_args = mock_db["master_cv_metadata"].replace_one.call_args
            saved_doc = call_args[0][1]

            # Verify timestamp is valid ISO format
            timestamp = saved_doc["updated_at"]
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


class TestDefaultDataDir:
    """Test default data directory configuration."""

    def test_default_data_dir_exists(self):
        """Test that default data directory path is configured correctly."""
        # The default should point to data/master-cv relative to project root
        assert "data" in str(DEFAULT_DATA_DIR)
        assert "master-cv" in str(DEFAULT_DATA_DIR)


class TestMasterCVStoreMetadataRoleUpdate:
    """Test updating individual roles within metadata."""

    def test_update_existing_role(self):
        """Test updating an existing role in metadata."""
        with patch("src.common.master_cv_store.database_client") as mock_client:
            mock_db = MagicMock()
            mock_client.db = mock_db

            store = MasterCVStore(use_mongodb=True)
            store._db = mock_db

            # Mock existing metadata with one role
            mock_db["master_cv_metadata"].find_one.return_value = {
                "_id": "canonical",
                "version": 1,
                "candidate": {"name": "Test"},
                "roles": [
                    {"id": "01_test", "company": "Old Company"}
                ]
            }

            result = store.update_metadata_role(
                "01_test",
                {"id": "01_test", "company": "New Company"},
                updated_by="user"
            )

            assert result is True

    def test_add_new_role_via_update(self):
        """Test adding a new role via update_metadata_role."""
        with patch("src.common.master_cv_store.database_client") as mock_client:
            mock_db = MagicMock()
            mock_client.db = mock_db

            store = MasterCVStore(use_mongodb=True)
            store._db = mock_db

            # Mock existing metadata with no roles
            mock_db["master_cv_metadata"].find_one.return_value = {
                "_id": "canonical",
                "version": 1,
                "candidate": {"name": "Test"},
                "roles": []
            }

            result = store.update_metadata_role(
                "new_role",
                {"id": "new_role", "company": "New Company"},
                updated_by="user"
            )

            assert result is True
