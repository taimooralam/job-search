"""
Unit tests for Master CV API endpoints.

Tests all the /api/master-cv/* endpoints that manage candidate info,
roles, taxonomy, version history, and rollback functionality.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_metadata():
    """Sample master-cv metadata document."""
    return {
        "version": 1,
        "candidate": {
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "+1-555-0100",
            "linkedin_url": "https://linkedin.com/in/johndoe",
            "github_url": "https://github.com/johndoe",
            "location": "San Francisco, CA",
            "languages": [
                {"name": "English", "proficiency": "Native"},
                {"name": "Spanish", "proficiency": "Professional"}
            ],
            "certifications": [
                {"name": "AWS Solutions Architect", "year": 2023},
                {"name": "Kubernetes Administrator", "year": 2022}
            ]
        },
        "roles": [
            {
                "id": "software_engineer",
                "title": "Software Engineer",
                "keywords": ["Python", "FastAPI", "MongoDB"],
                "last_updated": datetime(2025, 11, 1)
            },
            {
                "id": "engineering_manager",
                "title": "Engineering Manager",
                "keywords": ["Leadership", "Team Building", "Agile"],
                "last_updated": datetime(2025, 10, 15)
            }
        ]
    }


@pytest.fixture
def sample_taxonomy():
    """Sample skills taxonomy document."""
    return {
        "version": 1,
        "target_roles": {
            "software_engineer": {
                "Technical Skills": ["Python", "JavaScript", "SQL"],
                "Tools": ["Git", "Docker", "Kubernetes"]
            },
            "engineering_manager": {
                "Technical Leadership": ["Architecture", "Code Review"],
                "People Management": ["1-on-1s", "Performance Reviews"]
            }
        },
        "skill_aliases": {
            "Python": ["python3", "py"],
            "JavaScript": ["JS", "ECMAScript"]
        }
    }


@pytest.fixture
def sample_role():
    """Sample role document."""
    return {
        "role_id": "software_engineer",
        "version": 1,
        "markdown_content": "# Software Engineer\n\n## Experience\n\n- Built scalable APIs",
        "parsed": {
            "achievements": [
                {
                    "situation": "Legacy monolith",
                    "task": "Migrate to microservices",
                    "action": "Led architecture redesign",
                    "result": "Reduced latency by 40%"
                }
            ]
        },
        "last_updated": datetime(2025, 11, 1)
    }


@pytest.fixture
def mock_master_cv_store(mocker):
    """Mock the master_cv_store module."""
    mock_store = MagicMock()
    mocker.patch("src.common.master_cv_store.get_store", return_value=mock_store)
    return mock_store


# =============================================================================
# GET /api/master-cv/metadata
# =============================================================================


class TestGetMasterCVMetadata:
    """Tests for GET /api/master-cv/metadata endpoint."""

    def test_get_metadata_success(self, authenticated_client, mock_db, mock_master_cv_store, sample_metadata):
        """Should return metadata document."""
        # Arrange
        mock_master_cv_store.get_metadata.return_value = sample_metadata

        # Act
        response = authenticated_client.get("/api/master-cv/metadata")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "metadata" in data
        assert data["metadata"]["version"] == 1
        assert data["metadata"]["candidate"]["name"] == "John Doe"

    def test_get_metadata_not_found(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should return 404 when metadata doesn't exist."""
        # Arrange
        mock_master_cv_store.get_metadata.return_value = None

        # Act
        response = authenticated_client.get("/api/master-cv/metadata")

        # Assert
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data
        assert "not found" in data["error"].lower()

    def test_get_metadata_requires_authentication(self, client, mock_db):
        """Should redirect when not authenticated."""
        # Act
        response = client.get("/api/master-cv/metadata")

        # Assert
        assert response.status_code in [302, 401]


# =============================================================================
# PUT /api/master-cv/metadata
# =============================================================================


class TestUpdateMasterCVMetadata:
    """Tests for PUT /api/master-cv/metadata endpoint."""

    def test_update_metadata_success(self, authenticated_client, mock_db, mock_master_cv_store, sample_metadata):
        """Should update metadata successfully."""
        # Arrange
        mock_master_cv_store.update_metadata.return_value = True
        mock_master_cv_store.get_metadata.return_value = sample_metadata

        update_payload = {
            "candidate": sample_metadata["candidate"],
            "roles": sample_metadata["roles"]
        }

        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata",
            json=update_payload,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "Metadata updated" in data["message"]

        # Verify the store method was called
        mock_master_cv_store.update_metadata.assert_called_once()

    def test_update_metadata_with_empty_payload(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should handle empty payload gracefully."""
        # Arrange
        # Empty payload (API will check if update succeeds)
        mock_master_cv_store.update_metadata.return_value = True
        mock_master_cv_store.get_metadata.return_value = {"version": 2}

        invalid_payload = {
            "roles": []
            # Minimal valid payload
        }

        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata",
            json=invalid_payload,
            content_type="application/json"
        )

        # Assert
        # The API doesn't validate structure, just passes to store
        assert response.status_code == 200

    def test_update_metadata_requires_authentication(self, client, mock_db):
        """Should redirect when not authenticated."""
        # Arrange
        payload = {"candidate": {}, "roles": []}

        # Act
        response = client.put(
            "/api/master-cv/metadata",
            json=payload,
            content_type="application/json"
        )

        # Assert
        assert response.status_code in [302, 401]


# =============================================================================
# GET /api/master-cv/taxonomy
# =============================================================================


class TestGetMasterCVTaxonomy:
    """Tests for GET /api/master-cv/taxonomy endpoint."""

    def test_get_taxonomy_success(self, authenticated_client, mock_db, mock_master_cv_store, sample_taxonomy):
        """Should return taxonomy document."""
        # Arrange
        mock_master_cv_store.get_taxonomy.return_value = sample_taxonomy

        # Act
        response = authenticated_client.get("/api/master-cv/taxonomy")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "taxonomy" in data
        assert "target_roles" in data["taxonomy"]
        assert "skill_aliases" in data["taxonomy"]

    def test_get_taxonomy_not_found(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should return 404 when taxonomy doesn't exist."""
        # Arrange
        mock_master_cv_store.get_taxonomy.return_value = None

        # Act
        response = authenticated_client.get("/api/master-cv/taxonomy")

        # Assert
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data

    def test_get_taxonomy_requires_authentication(self, client, mock_db):
        """Should redirect when not authenticated."""
        # Act
        response = client.get("/api/master-cv/taxonomy")

        # Assert
        assert response.status_code in [302, 401]


# =============================================================================
# PUT /api/master-cv/taxonomy
# =============================================================================


class TestUpdateMasterCVTaxonomy:
    """Tests for PUT /api/master-cv/taxonomy endpoint."""

    def test_update_taxonomy_success(self, authenticated_client, mock_db, mock_master_cv_store, sample_taxonomy):
        """Should update taxonomy successfully."""
        # Arrange
        mock_master_cv_store.update_taxonomy.return_value = True
        mock_master_cv_store.get_taxonomy.return_value = sample_taxonomy

        update_payload = {
            "target_roles": sample_taxonomy["target_roles"],
            "skill_aliases": sample_taxonomy["skill_aliases"]
        }

        # Act
        response = authenticated_client.put(
            "/api/master-cv/taxonomy",
            json=update_payload,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "Taxonomy updated" in data["message"]

        # Verify store was called
        mock_master_cv_store.update_taxonomy.assert_called_once()

    def test_update_taxonomy_with_minimal_payload(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should handle minimal payload."""
        # Arrange
        mock_master_cv_store.update_taxonomy.return_value = True
        mock_master_cv_store.get_taxonomy.return_value = {"version": 2}

        minimal_payload = {
            "skill_aliases": {}
            # Minimal valid payload
        }

        # Act
        response = authenticated_client.put(
            "/api/master-cv/taxonomy",
            json=minimal_payload,
            content_type="application/json"
        )

        # Assert
        # The API doesn't validate structure, just passes to store
        assert response.status_code == 200

    def test_update_taxonomy_requires_authentication(self, client, mock_db):
        """Should redirect when not authenticated."""
        # Arrange
        payload = {"target_roles": {}, "skill_aliases": {}}

        # Act
        response = client.put(
            "/api/master-cv/taxonomy",
            json=payload,
            content_type="application/json"
        )

        # Assert
        assert response.status_code in [302, 401]


# =============================================================================
# GET /api/master-cv/roles
# =============================================================================


class TestGetMasterCVRoles:
    """Tests for GET /api/master-cv/roles endpoint."""

    def test_get_all_roles_success(self, authenticated_client, mock_db, mock_master_cv_store, sample_role):
        """Should return list of all role documents."""
        # Arrange
        roles = [sample_role, {**sample_role, "role_id": "engineering_manager"}]
        mock_master_cv_store.get_all_roles.return_value = roles

        # Act
        response = authenticated_client.get("/api/master-cv/roles")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "roles" in data
        assert data["count"] == 2
        assert len(data["roles"]) == 2

    def test_get_all_roles_empty_list(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should return empty list when no roles exist."""
        # Arrange
        mock_master_cv_store.get_all_roles.return_value = []

        # Act
        response = authenticated_client.get("/api/master-cv/roles")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["count"] == 0
        assert data["roles"] == []

    def test_get_all_roles_requires_authentication(self, client, mock_db):
        """Should redirect when not authenticated."""
        # Act
        response = client.get("/api/master-cv/roles")

        # Assert
        assert response.status_code in [302, 401]


# =============================================================================
# GET /api/master-cv/roles/<role_id>
# =============================================================================


class TestGetMasterCVRole:
    """Tests for GET /api/master-cv/roles/<role_id> endpoint."""

    def test_get_role_success(self, authenticated_client, mock_db, mock_master_cv_store, sample_role):
        """Should return specific role document."""
        # Arrange
        role_id = "software_engineer"
        mock_master_cv_store.get_role.return_value = sample_role

        # Act
        response = authenticated_client.get(f"/api/master-cv/roles/{role_id}")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "role" in data
        assert data["role"]["role_id"] == role_id

        # Verify store was called with correct ID
        mock_master_cv_store.get_role.assert_called_once_with(role_id)

    def test_get_role_not_found(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should return 404 when role doesn't exist."""
        # Arrange
        role_id = "nonexistent_role"
        mock_master_cv_store.get_role.return_value = None

        # Act
        response = authenticated_client.get(f"/api/master-cv/roles/{role_id}")

        # Assert
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data
        assert role_id in data["error"]

    def test_get_role_requires_authentication(self, client, mock_db):
        """Should redirect when not authenticated."""
        # Act
        response = client.get("/api/master-cv/roles/software_engineer")

        # Assert
        assert response.status_code in [302, 401]


# =============================================================================
# PUT /api/master-cv/roles/<role_id>
# =============================================================================


class TestUpdateMasterCVRole:
    """Tests for PUT /api/master-cv/roles/<role_id> endpoint."""

    def test_update_role_success(self, authenticated_client, mock_db, mock_master_cv_store, sample_role):
        """Should update role document successfully."""
        # Arrange
        role_id = "software_engineer"
        mock_master_cv_store.update_role.return_value = True
        mock_master_cv_store.get_role.return_value = sample_role

        update_payload = {
            "markdown_content": "# Updated content",
            "parsed": {"achievements": []}
        }

        # Act
        response = authenticated_client.put(
            f"/api/master-cv/roles/{role_id}",
            json=update_payload,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert role_id in data["message"]

        # Verify store was called
        mock_master_cv_store.update_role.assert_called_once()

    def test_update_role_missing_markdown_content(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should return 400 when markdown_content is missing."""
        # Arrange
        role_id = "software_engineer"
        invalid_payload = {
            "parsed": {}
            # Missing "markdown_content"
        }

        # Act
        response = authenticated_client.put(
            f"/api/master-cv/roles/{role_id}",
            json=invalid_payload,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_update_role_requires_authentication(self, client, mock_db):
        """Should redirect when not authenticated."""
        # Arrange
        payload = {"markdown_content": "# Test"}

        # Act
        response = client.put(
            "/api/master-cv/roles/software_engineer",
            json=payload,
            content_type="application/json"
        )

        # Assert
        assert response.status_code in [302, 401]


# =============================================================================
# GET /api/master-cv/history/<collection_name>
# =============================================================================


class TestGetMasterCVHistory:
    """Tests for GET /api/master-cv/history/<collection_name> endpoint."""

    def test_get_history_success(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should return version history for a collection."""
        # Arrange
        collection_name = "master_cv_metadata"  # Full collection name
        history_entries = [
            {
                "version": 2,
                "timestamp": datetime(2025, 11, 26, 12, 0, 0),
                "changes": "Updated candidate email"
            },
            {
                "version": 1,
                "timestamp": datetime(2025, 11, 25, 10, 0, 0),
                "changes": "Initial version"
            }
        ]
        mock_master_cv_store.get_history.return_value = history_entries

        # Act
        response = authenticated_client.get(f"/api/master-cv/history/{collection_name}")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "history" in data
        assert data["count"] == 2
        assert len(data["history"]) == 2

    def test_get_history_with_doc_id_filter(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should filter history by doc_id query parameter."""
        # Arrange
        collection_name = "master_cv_roles"  # Full collection name
        doc_id = "software_engineer"
        history_entries = [
            {"version": 1, "doc_id": doc_id, "timestamp": datetime(2025, 11, 26)}
        ]
        mock_master_cv_store.get_history.return_value = history_entries

        # Act
        response = authenticated_client.get(
            f"/api/master-cv/history/{collection_name}?doc_id={doc_id}"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["count"] == 1

        # Verify store was called with doc_id filter
        mock_master_cv_store.get_history.assert_called_once()
        call_kwargs = mock_master_cv_store.get_history.call_args[1]
        assert call_kwargs["doc_id"] == doc_id

    def test_get_history_with_limit(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should limit history results based on query parameter."""
        # Arrange
        collection_name = "master_cv_metadata"  # Full collection name
        limit = 5
        history_entries = [{"version": i} for i in range(limit)]
        mock_master_cv_store.get_history.return_value = history_entries

        # Act
        response = authenticated_client.get(
            f"/api/master-cv/history/{collection_name}?limit={limit}"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["count"] == limit

        # Verify store was called with limit
        call_kwargs = mock_master_cv_store.get_history.call_args[1]
        assert call_kwargs["limit"] == limit

    def test_get_history_empty(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should return empty list when no history exists."""
        # Arrange
        collection_name = "master_cv_taxonomy"  # Full collection name
        mock_master_cv_store.get_history.return_value = []

        # Act
        response = authenticated_client.get(f"/api/master-cv/history/{collection_name}")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["count"] == 0
        assert data["history"] == []

    def test_get_history_requires_authentication(self, client, mock_db):
        """Should redirect when not authenticated."""
        # Act
        response = client.get("/api/master-cv/history/metadata")

        # Assert
        assert response.status_code in [302, 401]


# =============================================================================
# POST /api/master-cv/rollback/<collection_name>/<target_version>
# =============================================================================


class TestRollbackMasterCV:
    """Tests for POST /api/master-cv/rollback/<collection_name>/<target_version> endpoint."""

    def test_rollback_metadata_success(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should rollback metadata to specified version."""
        # Arrange
        collection_name = "master_cv_metadata"  # Full collection name
        target_version = 5
        mock_master_cv_store.rollback.return_value = True

        # Act
        response = authenticated_client.post(
            f"/api/master-cv/rollback/{collection_name}/{target_version}",
            json={},
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert str(target_version) in data["message"]

        # Verify rollback was called
        mock_master_cv_store.rollback.assert_called_once()

    def test_rollback_role_with_doc_id(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should rollback specific role to specified version."""
        # Arrange
        collection_name = "master_cv_roles"  # Full collection name
        target_version = 3
        doc_id = "software_engineer"
        mock_master_cv_store.rollback.return_value = True

        # Act
        response = authenticated_client.post(
            f"/api/master-cv/rollback/{collection_name}/{target_version}",
            json={"doc_id": doc_id},
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert collection_name in data["message"]
        assert doc_id in data["message"]

    def test_rollback_role_missing_doc_id(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should return 400 when rolling back role without doc_id."""
        # Arrange
        collection_name = "master_cv_roles"  # Full collection name
        target_version = 2

        # Act
        response = authenticated_client.post(
            f"/api/master-cv/rollback/{collection_name}/{target_version}",
            json={},
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "doc_id" in data["error"].lower()

    def test_rollback_fails(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should return 500 when rollback fails."""
        # Arrange
        collection_name = "master_cv_metadata"  # Full collection name
        target_version = 99
        mock_master_cv_store.rollback.return_value = False

        # Act
        response = authenticated_client.post(
            f"/api/master-cv/rollback/{collection_name}/{target_version}",
            json={},
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data
        assert "Failed to rollback" in data["error"]

    def test_rollback_requires_authentication(self, client, mock_db):
        """Should redirect when not authenticated."""
        # Act
        response = client.post(
            "/api/master-cv/rollback/metadata/1",
            json={},
            content_type="application/json"
        )

        # Assert
        assert response.status_code in [302, 401]


# =============================================================================
# GET /api/master-cv/stats
# =============================================================================


class TestGetMasterCVStats:
    """Tests for GET /api/master-cv/stats endpoint."""

    def test_get_stats_success(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should return statistics about master-cv data."""
        # Arrange
        stats = {
            "total_roles": 5,
            "total_achievements": 42,
            "last_updated": datetime(2025, 11, 26),
            "taxonomy_skills_count": 120
        }
        mock_master_cv_store.get_stats.return_value = stats

        # Act
        response = authenticated_client.get("/api/master-cv/stats")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "stats" in data
        assert data["stats"]["total_roles"] == 5

    def test_get_stats_requires_authentication(self, client, mock_db):
        """Should redirect when not authenticated."""
        # Act
        response = client.get("/api/master-cv/stats")

        # Assert
        assert response.status_code in [302, 401]


# =============================================================================
# EDGE CASES
# =============================================================================


class TestMasterCVAPIEdgeCases:
    """Edge case tests for Master CV API endpoints."""

    def test_handles_large_role_document(self, authenticated_client, mock_db, mock_master_cv_store):
        """Should handle large role documents (100+ achievements)."""
        # Arrange
        role_id = "software_engineer"
        large_parsed = {
            "achievements": [
                {
                    "situation": f"Situation {i}",
                    "task": f"Task {i}",
                    "action": f"Action {i}",
                    "result": f"Result {i}"
                }
                for i in range(150)
            ]
        }
        mock_master_cv_store.update_role.return_value = True
        mock_master_cv_store.get_role.return_value = {"role_id": role_id, "version": 1}

        payload = {
            "markdown_content": "# Large role content",
            "parsed": large_parsed
        }

        # Act
        response = authenticated_client.put(
            f"/api/master-cv/roles/{role_id}",
            json=payload,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200

    def test_handles_special_characters_in_candidate_data(
        self, authenticated_client, mock_db, mock_master_cv_store, sample_metadata
    ):
        """Should handle Unicode and special characters in candidate info."""
        # Arrange
        sample_metadata["candidate"]["name"] = "François Müller 你好"
        sample_metadata["candidate"]["location"] = "São Paulo, Brazil"
        mock_master_cv_store.update_metadata.return_value = True
        mock_master_cv_store.get_metadata.return_value = sample_metadata

        payload = {
            "candidate": sample_metadata["candidate"],
            "roles": sample_metadata["roles"]
        }

        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata",
            json=payload,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200

    def test_handles_malformed_json(self, authenticated_client, mock_db):
        """Should return 400 for malformed JSON."""
        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata",
            data="not valid json",
            content_type="text/plain"
        )

        # Assert
        assert response.status_code in [400, 415]

    def test_handles_database_error_gracefully(self, authenticated_client, mock_db, mocker):
        """Should handle database errors and return 500."""
        # Arrange
        mocker.patch(
            "src.common.master_cv_store.get_store",
            side_effect=Exception("Database connection failed")
        )

        # Act & Assert
        try:
            response = authenticated_client.get("/api/master-cv/metadata")
            # If no exception, should be 500 or 503
            assert response.status_code in [500, 503]
        except Exception as e:
            # Expected behavior - error propagates
            assert "Database connection failed" in str(e)
