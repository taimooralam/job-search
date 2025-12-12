"""
Comprehensive Unit Tests for Master CV API Routes.

Tests all 11 endpoints with:
- Happy path scenarios
- Error handling (404, 400, 500, 503)
- Authentication requirements
- Request/response validation
- MongoDB connection handling
- Store method mocking

Endpoints tested:
1. GET /api/master-cv/metadata
2. PUT /api/master-cv/metadata
3. PUT /api/master-cv/metadata/roles/{role_id}
4. GET /api/master-cv/taxonomy
5. PUT /api/master-cv/taxonomy
6. POST /api/master-cv/taxonomy/skill
7. GET /api/master-cv/roles
8. GET /api/master-cv/roles/{role_id}
9. PUT /api/master-cv/roles/{role_id}
10. GET /api/master-cv/history/{collection_name}
11. POST /api/master-cv/rollback/{collection_name}/{target_version}
12. GET /api/master-cv/stats
"""

import pytest
from unittest.mock import MagicMock, patch


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_store(mocker):
    """Mock the MasterCVStore instance returned by _get_store()."""
    mock_get_store = mocker.patch(
        "src.common.master_cv_store.get_store"
    )

    mock_store_instance = MagicMock()
    mock_get_store.return_value = mock_store_instance

    # Default: Store is connected
    mock_store_instance.is_connected.return_value = True

    return mock_store_instance


@pytest.fixture
def sample_metadata():
    """Sample metadata document."""
    return {
        "version": 1,
        "updated_at": "2025-12-12T10:00:00Z",
        "updated_by": "user",
        "candidate": {
            "name": "Test Candidate",
            "email": "test@example.com",
            "phone": "+1-555-0100",
        },
        "roles": [
            {
                "id": "software_engineer",
                "title": "Software Engineer",
                "keywords": ["Python", "FastAPI"],
            }
        ],
    }


@pytest.fixture
def sample_taxonomy():
    """Sample taxonomy document."""
    return {
        "version": 1,
        "updated_at": "2025-12-12T10:00:00Z",
        "updated_by": "user",
        "target_roles": {
            "engineering_manager": {
                "Technical Leadership": ["Architecture", "Code Review"],
                "People Management": ["1-on-1s", "Performance Reviews"],
            }
        },
        "skill_aliases": {
            "Python": ["python3", "py"],
        },
        "default_fallback_role": "engineering_manager",
    }


@pytest.fixture
def sample_role():
    """Sample role document."""
    return {
        "role_id": "01_test_company",
        "version": 1,
        "updated_at": "2025-12-12T10:00:00Z",
        "updated_by": "user",
        "markdown_content": "# Test Company\n\nAchievements go here.",
        "parsed": {
            "achievements": [
                {"situation": "S", "task": "T", "action": "A", "result": "R"}
            ]
        },
    }


# =============================================================================
# METADATA ENDPOINT TESTS
# =============================================================================


class TestMetadataEndpoints:
    """Tests for metadata GET and PUT endpoints."""

    def test_get_metadata_success(self, client, auth_headers, mock_store, sample_metadata):
        """Should return metadata when store has data."""
        # Arrange
        mock_store.get_metadata.return_value = sample_metadata

        # Act
        response = client.get("/api/master-cv/metadata", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["metadata"] == sample_metadata
        mock_store.get_metadata.assert_called_once()

    def test_get_metadata_not_found(self, client, auth_headers, mock_store):
        """Should return 404 when metadata doesn't exist."""
        # Arrange
        mock_store.get_metadata.return_value = None

        # Act
        response = client.get("/api/master-cv/metadata", headers=auth_headers)

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "Metadata not found" in data["detail"]

    def test_get_metadata_store_error(self, client, auth_headers, mock_store):
        """Should return 500 when store raises exception."""
        # Arrange
        mock_store.get_metadata.side_effect = Exception("Database connection failed")

        # Act
        response = client.get("/api/master-cv/metadata", headers=auth_headers)

        # Assert
        assert response.status_code == 500
        data = response.json()
        assert "Database connection failed" in data["detail"]

    def test_get_metadata_requires_auth(self, client):
        """Should return 401/403 when no auth provided."""
        # Act
        response = client.get("/api/master-cv/metadata")

        # Assert
        assert response.status_code in (401, 403)

    def test_update_metadata_success(self, client, auth_headers, mock_store, sample_metadata):
        """Should update metadata and return new version."""
        # Arrange
        mock_store.update_metadata.return_value = True
        mock_store.get_metadata.return_value = sample_metadata

        payload = {
            "candidate": {"name": "Updated Name"},
            "roles": [],
            "updated_by": "user",
            "change_summary": "Updated candidate name",
        }

        # Act
        response = client.put(
            "/api/master-cv/metadata",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Metadata updated"
        assert data["version"] == 1
        mock_store.update_metadata.assert_called_once()

    def test_update_metadata_disconnected(self, client, auth_headers, mock_store):
        """Should return 503 when MongoDB is not connected."""
        # Arrange
        mock_store.is_connected.return_value = False

        payload = {
            "candidate": {},
            "roles": [],
        }

        # Act
        response = client.put(
            "/api/master-cv/metadata",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 503
        data = response.json()
        assert "MongoDB not connected" in data["detail"]

    def test_update_metadata_store_failure(self, client, auth_headers, mock_store):
        """Should return 500 when store update fails."""
        # Arrange
        mock_store.update_metadata.return_value = False

        payload = {
            "candidate": {},
            "roles": [],
        }

        # Act
        response = client.put(
            "/api/master-cv/metadata",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 500
        data = response.json()
        assert "Failed to update metadata" in data["detail"]

    def test_update_metadata_role_success(self, client, auth_headers, mock_store):
        """Should update a specific role within metadata."""
        # Arrange
        mock_store.update_metadata_role.return_value = True

        payload = {
            "title": "Senior Software Engineer",
            "keywords": ["Python", "FastAPI", "MongoDB"],
        }

        # Act
        response = client.put(
            "/api/master-cv/metadata/roles/software_engineer",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "software_engineer updated" in data["message"]
        mock_store.update_metadata_role.assert_called_once_with(
            "software_engineer",
            {"title": "Senior Software Engineer", "keywords": ["Python", "FastAPI", "MongoDB"]},
            updated_by="user",
            change_summary="Updated role software_engineer",
        )

    def test_update_metadata_role_disconnected(self, client, auth_headers, mock_store):
        """Should return 503 when MongoDB disconnected."""
        # Arrange
        mock_store.is_connected.return_value = False

        # Act
        response = client.put(
            "/api/master-cv/metadata/roles/software_engineer",
            headers=auth_headers,
            json={"title": "Updated Title"},
        )

        # Assert
        assert response.status_code == 503


# =============================================================================
# TAXONOMY ENDPOINT TESTS
# =============================================================================


class TestTaxonomyEndpoints:
    """Tests for taxonomy GET, PUT, and skill POST endpoints."""

    def test_get_taxonomy_success(self, client, auth_headers, mock_store, sample_taxonomy):
        """Should return taxonomy when store has data."""
        # Arrange
        mock_store.get_taxonomy.return_value = sample_taxonomy

        # Act
        response = client.get("/api/master-cv/taxonomy", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["taxonomy"] == sample_taxonomy

    def test_get_taxonomy_not_found(self, client, auth_headers, mock_store):
        """Should return 404 when taxonomy doesn't exist."""
        # Arrange
        mock_store.get_taxonomy.return_value = None

        # Act
        response = client.get("/api/master-cv/taxonomy", headers=auth_headers)

        # Assert
        assert response.status_code == 404

    def test_update_taxonomy_success(self, client, auth_headers, mock_store, sample_taxonomy):
        """Should update taxonomy and return new version."""
        # Arrange
        mock_store.update_taxonomy.return_value = True
        mock_store.get_taxonomy.return_value = sample_taxonomy

        payload = {
            "target_roles": sample_taxonomy["target_roles"],
            "skill_aliases": sample_taxonomy["skill_aliases"],
            "default_fallback_role": "engineering_manager",
            "updated_by": "user",
            "change_summary": "Added new skills",
        }

        # Act
        response = client.put(
            "/api/master-cv/taxonomy",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["version"] == 1

    def test_update_taxonomy_disconnected(self, client, auth_headers, mock_store):
        """Should return 503 when MongoDB not connected."""
        # Arrange
        mock_store.is_connected.return_value = False

        payload = {
            "target_roles": {},
            "skill_aliases": {},
        }

        # Act
        response = client.put(
            "/api/master-cv/taxonomy",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 503

    def test_add_skill_to_taxonomy_success(self, client, auth_headers, mock_store):
        """Should add a skill to a specific taxonomy section."""
        # Arrange
        mock_store.add_skill_to_taxonomy.return_value = True

        payload = {
            "role_category": "engineering_manager",
            "section_name": "Technical Leadership",
            "skill": "System Design",
            "updated_by": "user",
        }

        # Act
        response = client.post(
            "/api/master-cv/taxonomy/skill",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "System Design" in data["message"]
        mock_store.add_skill_to_taxonomy.assert_called_once_with(
            role_category="engineering_manager",
            section_name="Technical Leadership",
            skill="System Design",
            updated_by="user",
        )

    def test_add_skill_missing_fields(self, client, auth_headers, mock_store):
        """Should return 422 when required fields are missing."""
        # Arrange
        payload = {
            "role_category": "engineering_manager",
            # Missing section_name and skill
        }

        # Act
        response = client.post(
            "/api/master-cv/taxonomy/skill",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 422

    def test_add_skill_disconnected(self, client, auth_headers, mock_store):
        """Should return 503 when MongoDB not connected."""
        # Arrange
        mock_store.is_connected.return_value = False

        payload = {
            "role_category": "engineering_manager",
            "section_name": "Leadership",
            "skill": "Test Skill",
        }

        # Act
        response = client.post(
            "/api/master-cv/taxonomy/skill",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 503


# =============================================================================
# ROLE ENDPOINT TESTS
# =============================================================================


class TestRoleEndpoints:
    """Tests for role GET and PUT endpoints."""

    def test_get_all_roles_success(self, client, auth_headers, mock_store, sample_role):
        """Should return list of all roles."""
        # Arrange
        mock_store.get_all_roles.return_value = [sample_role]

        # Act
        response = client.get("/api/master-cv/roles", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["roles"]) == 1
        assert data["count"] == 1
        assert data["roles"][0]["role_id"] == "01_test_company"

    def test_get_all_roles_empty(self, client, auth_headers, mock_store):
        """Should return empty list when no roles exist."""
        # Arrange
        mock_store.get_all_roles.return_value = []

        # Act
        response = client.get("/api/master-cv/roles", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["roles"] == []

    def test_get_role_success(self, client, auth_headers, mock_store, sample_role):
        """Should return a specific role by ID."""
        # Arrange
        mock_store.get_role.return_value = sample_role

        # Act
        response = client.get(
            "/api/master-cv/roles/01_test_company",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["role"]["role_id"] == "01_test_company"
        assert "markdown_content" in data["role"]

    def test_get_role_not_found(self, client, auth_headers, mock_store):
        """Should return 404 when role doesn't exist."""
        # Arrange
        mock_store.get_role.return_value = None

        # Act
        response = client.get(
            "/api/master-cv/roles/nonexistent_role",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]

    def test_update_role_success(self, client, auth_headers, mock_store, sample_role):
        """Should update role content and return new version."""
        # Arrange
        mock_store.update_role.return_value = True
        mock_store.get_role.return_value = sample_role

        payload = {
            "markdown_content": "# Updated Content\n\nNew achievements",
            "parsed": {"achievements": []},
            "updated_by": "user",
            "change_summary": "Updated achievements",
        }

        # Act
        response = client.put(
            "/api/master-cv/roles/01_test_company",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "01_test_company updated" in data["message"]
        assert data["version"] == 1
        mock_store.update_role.assert_called_once()

    def test_update_role_missing_content(self, client, auth_headers, mock_store):
        """Should return 422 when markdown_content is missing."""
        # Arrange
        payload = {
            "parsed": {},
        }

        # Act
        response = client.put(
            "/api/master-cv/roles/01_test_company",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 422

    def test_update_role_disconnected(self, client, auth_headers, mock_store):
        """Should return 503 when MongoDB not connected."""
        # Arrange
        mock_store.is_connected.return_value = False

        payload = {
            "markdown_content": "# Test",
        }

        # Act
        response = client.put(
            "/api/master-cv/roles/01_test_company",
            headers=auth_headers,
            json=payload,
        )

        # Assert
        assert response.status_code == 503


# =============================================================================
# HISTORY & ROLLBACK TESTS
# =============================================================================


class TestHistoryAndRollback:
    """Tests for version history and rollback endpoints."""

    def test_get_history_metadata_success(self, client, auth_headers, mock_store):
        """Should return version history for metadata collection."""
        # Arrange
        history_entries = [
            {
                "collection": "master_cv_metadata",
                "doc_id": "canonical",
                "version": 2,
                "timestamp": "2025-12-12T10:00:00Z",
                "data": {"candidate": {"name": "Test"}},
            },
            {
                "collection": "master_cv_metadata",
                "doc_id": "canonical",
                "version": 1,
                "timestamp": "2025-12-11T10:00:00Z",
                "data": {"candidate": {"name": "Old Name"}},
            },
        ]
        mock_store.get_history.return_value = history_entries

        # Act
        response = client.get(
            "/api/master-cv/history/master_cv_metadata",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 2
        assert len(data["history"]) == 2
        mock_store.get_history.assert_called_once_with(
            collection_name="master_cv_metadata",
            doc_id=None,
            limit=10,
        )

    def test_get_history_with_filters(self, client, auth_headers, mock_store):
        """Should pass doc_id and limit filters to store."""
        # Arrange
        mock_store.get_history.return_value = []

        # Act
        response = client.get(
            "/api/master-cv/history/master_cv_roles?doc_id=01_test&limit=5",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        mock_store.get_history.assert_called_once_with(
            collection_name="master_cv_roles",
            doc_id="01_test",
            limit=5,
        )

    def test_get_history_invalid_collection(self, client, auth_headers):
        """Should return 400 for invalid collection name."""
        # Act
        response = client.get(
            "/api/master-cv/history/invalid_collection",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "Invalid collection" in data["detail"]

    def test_rollback_metadata_success(self, client, auth_headers, mock_store):
        """Should rollback metadata to a previous version."""
        # Arrange
        mock_store.rollback.return_value = True

        # Act
        response = client.post(
            "/api/master-cv/rollback/master_cv_metadata/1",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "version 1" in data["message"]
        mock_store.rollback.assert_called_once_with(
            collection_name="master_cv_metadata",
            doc_id="canonical",
            target_version=1,
            updated_by="user",
        )

    def test_rollback_roles_requires_doc_id(self, client, auth_headers):
        """Should return 400 when rolling back role without doc_id."""
        # Act
        response = client.post(
            "/api/master-cv/rollback/master_cv_roles/1",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "doc_id required" in data["detail"]

    def test_rollback_invalid_collection(self, client, auth_headers):
        """Should return 400 for invalid collection name."""
        # Act
        response = client.post(
            "/api/master-cv/rollback/invalid_collection/1",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 400

    def test_rollback_disconnected(self, client, auth_headers, mock_store):
        """Should return 503 when MongoDB not connected."""
        # Arrange
        mock_store.is_connected.return_value = False

        # Act
        response = client.post(
            "/api/master-cv/rollback/master_cv_metadata/1",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 503


# =============================================================================
# STATS ENDPOINT TESTS
# =============================================================================


class TestStatsEndpoint:
    """Tests for the stats endpoint."""

    def test_get_stats_success(self, client, auth_headers, mock_store):
        """Should return Master CV statistics."""
        # Arrange
        stats = {
            "mongodb_connected": True,
            "metadata_version": 5,
            "taxonomy_version": 3,
            "roles_count": 12,
            "history_entries": 45,
        }
        mock_store.get_stats.return_value = stats

        # Act
        response = client.get("/api/master-cv/stats", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["stats"]["mongodb_connected"] is True
        assert data["stats"]["roles_count"] == 12

    def test_get_stats_disconnected(self, client, auth_headers, mock_store):
        """Should still return stats even if MongoDB disconnected."""
        # Arrange
        stats = {
            "mongodb_connected": False,
            "metadata_version": None,
            "taxonomy_version": None,
            "roles_count": 0,
            "history_entries": 0,
        }
        mock_store.get_stats.return_value = stats

        # Act
        response = client.get("/api/master-cv/stats", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["stats"]["mongodb_connected"] is False


# =============================================================================
# STORE INITIALIZATION ERROR TESTS
# =============================================================================


class TestStoreInitializationErrors:
    """Tests for _get_store() error handling."""

    def test_import_error(self, client, auth_headers, mocker):
        """Should return 500 when master_cv_store cannot be imported."""
        # Arrange
        mocker.patch(
            "src.common.master_cv_store.get_store",
            side_effect=ImportError("Module not found"),
        )

        # Act
        response = client.get("/api/master-cv/metadata", headers=auth_headers)

        # Assert
        assert response.status_code == 500
        data = response.json()
        assert "not available" in data["detail"]

    def test_general_exception(self, client, auth_headers, mocker):
        """Should return 500 when store initialization fails."""
        # Arrange
        mocker.patch(
            "src.common.master_cv_store.get_store",
            side_effect=Exception("Database init failed"),
        )

        # Act
        response = client.get("/api/master-cv/metadata", headers=auth_headers)

        # Assert
        assert response.status_code == 500
        data = response.json()
        assert "Failed to initialize store" in data["detail"]
