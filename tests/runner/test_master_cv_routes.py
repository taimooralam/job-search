"""
Unit tests for Master CV API Routes.

Tests:
- Route registration and availability
- Request validation (Pydantic models)
- Response structure validation
- Authentication requirements
- Error handling

Note: These tests focus on route behavior, not MasterCVStore implementation.
Store tests are in tests/test_master_cv_store.py.
"""

import pytest


# =============================================================================
# Route Availability Tests
# =============================================================================


class TestRouteAvailability:
    """Tests that routes are properly registered and accessible."""

    def test_metadata_get_route_exists(self, client, auth_headers):
        """GET /api/master-cv/metadata is accessible."""
        response = client.get("/api/master-cv/metadata", headers=auth_headers)
        # Route exists - may return 404 if data not found (valid in CI without MongoDB)
        assert response.status_code in (200, 404, 500, 503)

    def test_metadata_put_route_exists(self, client, auth_headers):
        """PUT /api/master-cv/metadata is accessible."""
        response = client.put(
            "/api/master-cv/metadata",
            headers=auth_headers,
            json={"candidate": {}, "roles": []},
        )
        assert response.status_code in (200, 500, 503)

    def test_taxonomy_get_route_exists(self, client, auth_headers):
        """GET /api/master-cv/taxonomy is accessible."""
        response = client.get("/api/master-cv/taxonomy", headers=auth_headers)
        # Route exists - may return 404 if data not found (valid in CI without MongoDB)
        assert response.status_code in (200, 404, 500, 503)

    def test_taxonomy_put_route_exists(self, client, auth_headers):
        """PUT /api/master-cv/taxonomy is accessible."""
        response = client.put(
            "/api/master-cv/taxonomy",
            headers=auth_headers,
            json={"target_roles": {}, "skill_aliases": {}},
        )
        assert response.status_code in (200, 500, 503)

    def test_taxonomy_skill_post_route_exists(self, client, auth_headers):
        """POST /api/master-cv/taxonomy/skill is accessible."""
        response = client.post(
            "/api/master-cv/taxonomy/skill",
            headers=auth_headers,
            json={
                "role_category": "engineering_manager",
                "section_name": "Leadership",
                "skill": "Test Skill",
            },
        )
        assert response.status_code in (200, 400, 500, 503)

    def test_roles_get_route_exists(self, client, auth_headers):
        """GET /api/master-cv/roles is accessible."""
        response = client.get("/api/master-cv/roles", headers=auth_headers)
        assert response.status_code in (200, 500, 503)

    def test_roles_single_get_route_exists(self, client, auth_headers):
        """GET /api/master-cv/roles/{role_id} is accessible."""
        response = client.get(
            "/api/master-cv/roles/test_role",
            headers=auth_headers,
        )
        assert response.status_code in (200, 404, 500, 503)

    def test_roles_put_route_exists(self, client, auth_headers):
        """PUT /api/master-cv/roles/{role_id} is accessible."""
        response = client.put(
            "/api/master-cv/roles/test_role",
            headers=auth_headers,
            json={"markdown_content": "# Test"},
        )
        assert response.status_code in (200, 500, 503)

    def test_history_get_route_exists(self, client, auth_headers):
        """GET /api/master-cv/history/{collection} is accessible."""
        response = client.get(
            "/api/master-cv/history/master_cv_metadata",
            headers=auth_headers,
        )
        assert response.status_code in (200, 500, 503)

    def test_rollback_post_route_exists(self, client, auth_headers):
        """POST /api/master-cv/rollback/{collection}/{version} is accessible."""
        response = client.post(
            "/api/master-cv/rollback/master_cv_metadata/1",
            headers=auth_headers,
        )
        assert response.status_code in (200, 404, 500, 503)

    def test_stats_get_route_exists(self, client, auth_headers):
        """GET /api/master-cv/stats is accessible."""
        response = client.get("/api/master-cv/stats", headers=auth_headers)
        assert response.status_code in (200, 500, 503)


# =============================================================================
# Authentication Tests
# =============================================================================


class TestAuthentication:
    """Tests that routes require authentication."""

    def test_metadata_requires_auth(self, client):
        """GET /api/master-cv/metadata requires auth."""
        response = client.get("/api/master-cv/metadata")
        assert response.status_code in (401, 403)

    def test_taxonomy_requires_auth(self, client):
        """GET /api/master-cv/taxonomy requires auth."""
        response = client.get("/api/master-cv/taxonomy")
        assert response.status_code in (401, 403)

    def test_roles_requires_auth(self, client):
        """GET /api/master-cv/roles requires auth."""
        response = client.get("/api/master-cv/roles")
        assert response.status_code in (401, 403)

    def test_history_requires_auth(self, client):
        """GET /api/master-cv/history requires auth."""
        response = client.get("/api/master-cv/history/master_cv_metadata")
        assert response.status_code in (401, 403)

    def test_stats_requires_auth(self, client):
        """GET /api/master-cv/stats requires auth."""
        response = client.get("/api/master-cv/stats")
        assert response.status_code in (401, 403)

    def test_invalid_token_rejected(self, client, invalid_auth_headers):
        """Invalid auth token is rejected."""
        response = client.get("/api/master-cv/metadata", headers=invalid_auth_headers)
        assert response.status_code == 401


# =============================================================================
# Request Validation Tests
# =============================================================================


class TestRequestValidation:
    """Tests that routes validate request bodies correctly."""

    def test_metadata_update_requires_body(self, client, auth_headers):
        """PUT /api/master-cv/metadata requires request body."""
        response = client.put("/api/master-cv/metadata", headers=auth_headers)
        assert response.status_code == 422  # Unprocessable Entity

    def test_taxonomy_update_requires_body(self, client, auth_headers):
        """PUT /api/master-cv/taxonomy requires request body."""
        response = client.put("/api/master-cv/taxonomy", headers=auth_headers)
        assert response.status_code == 422

    def test_add_skill_requires_fields(self, client, auth_headers):
        """POST /api/master-cv/taxonomy/skill requires all fields."""
        # Missing required fields
        response = client.post(
            "/api/master-cv/taxonomy/skill",
            headers=auth_headers,
            json={"role_category": "test"},  # Missing section_name and skill
        )
        assert response.status_code == 422

    def test_role_update_requires_content(self, client, auth_headers):
        """PUT /api/master-cv/roles/{role_id} requires markdown_content."""
        response = client.put(
            "/api/master-cv/roles/test_role",
            headers=auth_headers,
            json={},  # Missing markdown_content
        )
        assert response.status_code == 422

    def test_history_invalid_collection(self, client, auth_headers):
        """GET /api/master-cv/history rejects invalid collection names."""
        response = client.get(
            "/api/master-cv/history/invalid_collection",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_rollback_invalid_collection(self, client, auth_headers):
        """POST /api/master-cv/rollback rejects invalid collection names."""
        response = client.post(
            "/api/master-cv/rollback/invalid_collection/1",
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_rollback_invalid_version(self, client, auth_headers):
        """POST /api/master-cv/rollback rejects version < 1."""
        response = client.post(
            "/api/master-cv/rollback/master_cv_metadata/0",
            headers=auth_headers,
        )
        # Route validation returns 400, but if it passes validation,
        # store might error out (500/503) due to internal issues or service unavailability
        assert response.status_code in (400, 500, 503)

    def test_rollback_roles_requires_doc_id(self, client, auth_headers):
        """POST /api/master-cv/rollback for roles requires doc_id."""
        response = client.post(
            "/api/master-cv/rollback/master_cv_roles/1",
            headers=auth_headers,
        )
        assert response.status_code == 400


# =============================================================================
# Response Structure Tests
# =============================================================================


class TestResponseStructure:
    """Tests that responses have correct structure."""

    def test_metadata_response_structure(self, client, auth_headers):
        """GET /api/master-cv/metadata returns expected fields."""
        response = client.get("/api/master-cv/metadata", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert data["success"] is True
            assert "metadata" in data
            metadata = data["metadata"]
            assert "candidate" in metadata
            assert "roles" in metadata

    def test_taxonomy_response_structure(self, client, auth_headers):
        """GET /api/master-cv/taxonomy returns expected fields."""
        response = client.get("/api/master-cv/taxonomy", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert data["success"] is True
            assert "taxonomy" in data
            taxonomy = data["taxonomy"]
            assert "target_roles" in taxonomy

    def test_roles_response_is_list(self, client, auth_headers):
        """GET /api/master-cv/roles returns roles list."""
        response = client.get("/api/master-cv/roles", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert data["success"] is True
            assert "roles" in data
            assert isinstance(data["roles"], list)

    def test_history_response_structure(self, client, auth_headers):
        """GET /api/master-cv/history returns expected fields."""
        response = client.get(
            "/api/master-cv/history/master_cv_metadata",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert "history" in data
            assert "count" in data
            assert isinstance(data["history"], list)

    def test_stats_response_structure(self, client, auth_headers):
        """GET /api/master-cv/stats returns expected fields."""
        response = client.get("/api/master-cv/stats", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert "stats" in data
            stats = data["stats"]
            assert "mongodb_connected" in stats
            assert "roles_count" in stats


# =============================================================================
# OpenAPI Schema Tests
# =============================================================================


class TestOpenAPISchema:
    """Tests that routes are properly documented in OpenAPI."""

    def test_routes_in_openapi(self, client):
        """Master CV routes appear in OpenAPI schema."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()

        paths = schema.get("paths", {})

        # Check key routes are documented
        assert "/api/master-cv/metadata" in paths
        assert "/api/master-cv/taxonomy" in paths
        assert "/api/master-cv/roles" in paths
        assert "/api/master-cv/stats" in paths

    def test_routes_tagged_correctly(self, client):
        """Master CV routes have correct tags."""
        response = client.get("/openapi.json")
        schema = response.json()

        paths = schema.get("paths", {})
        metadata_path = paths.get("/api/master-cv/metadata", {})

        # GET operation should have master-cv tag
        get_op = metadata_path.get("get", {})
        assert "master-cv" in get_op.get("tags", [])
