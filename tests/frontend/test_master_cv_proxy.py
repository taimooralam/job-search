"""
Unit Tests for Master CV Proxy Function.

Tests the proxy_master_cv_to_runner() function that proxies Master CV API
calls from the frontend to the runner service.

Tests:
- Successful proxy for GET/PUT/POST methods
- Timeout handling (504)
- Connection error handling (503)
- General exception handling (500)
- Proper header forwarding
- Response pass-through
"""

import pytest
import requests
from unittest.mock import MagicMock


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_requests(mocker):
    """Mock the requests module."""
    return {
        "get": mocker.patch("frontend.app.requests.get"),
        "put": mocker.patch("frontend.app.requests.put"),
        "post": mocker.patch("frontend.app.requests.post"),
    }


def create_mock_response(status_code, json_data):
    """Helper to create a mock Response object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.text = str(json_data)
    return mock_resp


# =============================================================================
# HAPPY PATH TESTS
# =============================================================================


class TestProxySuccessScenarios:
    """Tests for successful proxy operations."""

    def test_proxy_get_request_success(self, authenticated_client, mock_db, mock_requests):
        """Should successfully proxy GET request to runner."""
        # Arrange
        expected_response = {
            "success": True,
            "metadata": {"candidate": {"name": "Test"}},
        }
        mock_requests["get"].return_value = create_mock_response(200, expected_response)

        # Act
        response = authenticated_client.get("/api/master-cv/metadata")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "metadata" in data

        # Verify request was made correctly
        mock_requests["get"].assert_called_once()
        call_args = mock_requests["get"].call_args
        assert "/api/master-cv/metadata" in call_args[0][0]
        assert call_args[1]["timeout"] == 30

    def test_proxy_put_request_success(self, authenticated_client, mock_db, mock_requests):
        """Should successfully proxy PUT request with JSON body to runner."""
        # Arrange
        expected_response = {
            "success": True,
            "message": "Metadata updated",
            "version": 2,
        }
        mock_requests["put"].return_value = create_mock_response(200, expected_response)

        payload = {
            "candidate": {"name": "Updated Name"},
            "roles": [],
        }

        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata",
            json=payload,
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["version"] == 2

        # Verify request was made with correct body
        mock_requests["put"].assert_called_once()
        call_args = mock_requests["put"].call_args
        assert call_args[1]["json"] == payload
        assert call_args[1]["timeout"] == 30

    def test_proxy_post_request_success(self, authenticated_client, mock_db, mock_requests):
        """Should successfully proxy POST request with JSON body to runner."""
        # Arrange
        expected_response = {
            "success": True,
            "message": "Skill added",
        }
        mock_requests["post"].return_value = create_mock_response(200, expected_response)

        payload = {
            "role_category": "engineering_manager",
            "section_name": "Leadership",
            "skill": "Team Building",
        }

        # Act
        response = authenticated_client.post(
            "/api/master-cv/taxonomy/skill",
            json=payload,
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        # Verify request was made correctly
        mock_requests["post"].assert_called_once()
        call_args = mock_requests["post"].call_args
        assert call_args[1]["json"] == payload

    def test_proxy_passes_through_status_codes(self, authenticated_client, mock_db, mock_requests):
        """Should pass through non-200 status codes from runner."""
        # Arrange - Runner returns 404
        error_response = {
            "success": False,
            "detail": "Role not found",
        }
        mock_requests["get"].return_value = create_mock_response(404, error_response)

        # Act
        response = authenticated_client.get(
            "/api/master-cv/roles/nonexistent",
        )

        # Assert
        assert response.status_code == 404
        data = response.get_json()
        assert data["success"] is False
        assert "not found" in data["detail"]

    def test_proxy_handles_503_from_runner(self, authenticated_client, mock_db, mock_requests):
        """Should pass through 503 when runner MongoDB is disconnected."""
        # Arrange
        error_response = {
            "success": False,
            "detail": "MongoDB not connected",
        }
        mock_requests["put"].return_value = create_mock_response(503, error_response)

        payload = {
            "candidate": {},
            "roles": [],
        }

        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata",
            json=payload,
        )

        # Assert
        assert response.status_code == 503


# =============================================================================
# TIMEOUT HANDLING TESTS
# =============================================================================


class TestProxyTimeoutHandling:
    """Tests for timeout scenarios."""

    def test_proxy_timeout_returns_504(self, authenticated_client, mock_db, mock_requests):
        """Should return 504 Gateway Timeout when runner request times out."""
        # Arrange
        mock_requests["get"].side_effect = requests.exceptions.Timeout("Request timed out")

        # Act
        response = authenticated_client.get("/api/master-cv/metadata")

        # Assert
        assert response.status_code == 504
        data = response.get_json()
        assert data["success"] is False
        assert "timed out" in data["error"].lower()

    def test_proxy_timeout_on_put(self, authenticated_client, mock_db, mock_requests):
        """Should return 504 when PUT request times out."""
        # Arrange
        mock_requests["put"].side_effect = requests.exceptions.Timeout()

        payload = {"candidate": {}, "roles": []}

        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata",
            json=payload,
        )

        # Assert
        assert response.status_code == 504

    def test_proxy_timeout_on_post(self, authenticated_client, mock_db, mock_requests):
        """Should return 504 when POST request times out."""
        # Arrange
        mock_requests["post"].side_effect = requests.exceptions.Timeout()

        payload = {
            "role_category": "test",
            "section_name": "test",
            "skill": "test",
        }

        # Act
        response = authenticated_client.post(
            "/api/master-cv/taxonomy/skill",
            json=payload,
        )

        # Assert
        assert response.status_code == 504


# =============================================================================
# CONNECTION ERROR HANDLING TESTS
# =============================================================================


class TestProxyConnectionErrors:
    """Tests for connection error scenarios."""

    def test_proxy_connection_error_returns_503(self, authenticated_client, mock_db, mock_requests):
        """Should return 503 Service Unavailable when runner is unreachable."""
        # Arrange
        mock_requests["get"].side_effect = requests.exceptions.ConnectionError(
            "Cannot connect to runner service"
        )

        # Act
        response = authenticated_client.get("/api/master-cv/metadata")

        # Assert
        assert response.status_code == 503
        data = response.get_json()
        assert data["success"] is False
        assert "Cannot connect" in data["error"]

    def test_proxy_connection_refused(self, authenticated_client, mock_db, mock_requests):
        """Should return 503 when connection is refused."""
        # Arrange
        mock_requests["put"].side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata",
            json={"candidate": {}, "roles": []},
        )

        # Assert
        assert response.status_code == 503
        data = response.get_json()
        assert "try again later" in data["error"].lower()

    def test_proxy_dns_resolution_failure(self, authenticated_client, mock_db, mock_requests):
        """Should return 503 on DNS resolution failure."""
        # Arrange
        mock_requests["get"].side_effect = requests.exceptions.ConnectionError(
            "Name or service not known"
        )

        # Act
        response = authenticated_client.get("/api/master-cv/taxonomy")

        # Assert
        assert response.status_code == 503


# =============================================================================
# GENERAL EXCEPTION HANDLING TESTS
# =============================================================================


class TestProxyGeneralExceptions:
    """Tests for unexpected exception scenarios."""

    def test_proxy_unexpected_exception_returns_500(self, authenticated_client, mock_db, mock_requests):
        """Should return 500 for unexpected exceptions."""
        # Arrange
        mock_requests["get"].side_effect = ValueError("Unexpected error occurred")

        # Act
        response = authenticated_client.get("/api/master-cv/stats")

        # Assert
        assert response.status_code == 500
        data = response.get_json()
        assert data["success"] is False
        assert "Unexpected error" in data["error"]

    def test_proxy_json_decode_error(self, authenticated_client, mock_db, mock_requests):
        """Should handle JSON decode errors gracefully."""
        # Arrange
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_requests["get"].return_value = mock_resp

        # Act
        response = authenticated_client.get("/api/master-cv/metadata")

        # Assert
        assert response.status_code == 500

    def test_proxy_http_error(self, authenticated_client, mock_db, mock_requests):
        """Should handle requests.HTTPError exceptions."""
        # Arrange
        mock_requests["get"].side_effect = requests.exceptions.HTTPError("HTTP Error")

        # Act
        response = authenticated_client.get("/api/master-cv/roles")

        # Assert
        assert response.status_code == 500


# =============================================================================
# ENDPOINT-SPECIFIC PROXY TESTS
# =============================================================================


class TestSpecificEndpointProxying:
    """Tests for each Master CV endpoint proxy."""

    def test_proxy_metadata_get(self, authenticated_client, mock_db, mock_requests):
        """Should proxy GET /api/master-cv/metadata."""
        # Arrange
        mock_requests["get"].return_value = create_mock_response(
            200, {"success": True, "metadata": {}}
        )

        # Act
        response = authenticated_client.get("/api/master-cv/metadata")

        # Assert
        assert response.status_code == 200
        assert mock_requests["get"].called

    def test_proxy_metadata_put(self, authenticated_client, mock_db, mock_requests):
        """Should proxy PUT /api/master-cv/metadata."""
        # Arrange
        mock_requests["put"].return_value = create_mock_response(
            200, {"success": True, "version": 1}
        )

        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata",
            json={"candidate": {}, "roles": []},
        )

        # Assert
        assert response.status_code == 200
        assert mock_requests["put"].called

    def test_proxy_metadata_role_put(self, authenticated_client, mock_db, mock_requests):
        """Should proxy PUT /api/master-cv/metadata/roles/{role_id}."""
        # Arrange
        mock_requests["put"].return_value = create_mock_response(
            200, {"success": True}
        )

        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata/roles/software_engineer",
            json={"title": "Senior Engineer"},
        )

        # Assert
        assert response.status_code == 200
        call_args = mock_requests["put"].call_args
        assert "software_engineer" in call_args[0][0]

    def test_proxy_taxonomy_get(self, authenticated_client, mock_db, mock_requests):
        """Should proxy GET /api/master-cv/taxonomy."""
        # Arrange
        mock_requests["get"].return_value = create_mock_response(
            200, {"success": True, "taxonomy": {}}
        )

        # Act
        response = authenticated_client.get("/api/master-cv/taxonomy")

        # Assert
        assert response.status_code == 200

    def test_proxy_taxonomy_skill_post(self, authenticated_client, mock_db, mock_requests):
        """Should proxy POST /api/master-cv/taxonomy/skill."""
        # Arrange
        mock_requests["post"].return_value = create_mock_response(
            200, {"success": True}
        )

        # Act
        response = authenticated_client.post(
            "/api/master-cv/taxonomy/skill",
            json={
                "role_category": "engineering_manager",
                "section_name": "Leadership",
                "skill": "Coaching",
            },
        )

        # Assert
        assert response.status_code == 200

    def test_proxy_roles_get(self, authenticated_client, mock_db, mock_requests):
        """Should proxy GET /api/master-cv/roles."""
        # Arrange
        mock_requests["get"].return_value = create_mock_response(
            200, {"success": True, "roles": [], "count": 0}
        )

        # Act
        response = authenticated_client.get("/api/master-cv/roles")

        # Assert
        assert response.status_code == 200

    def test_proxy_role_get(self, authenticated_client, mock_db, mock_requests):
        """Should proxy GET /api/master-cv/roles/{role_id}."""
        # Arrange
        mock_requests["get"].return_value = create_mock_response(
            200, {"success": True, "role": {}}
        )

        # Act
        response = authenticated_client.get(
            "/api/master-cv/roles/01_test_company",
        )

        # Assert
        assert response.status_code == 200
        call_args = mock_requests["get"].call_args
        assert "01_test_company" in call_args[0][0]

    def test_proxy_role_put(self, authenticated_client, mock_db, mock_requests):
        """Should proxy PUT /api/master-cv/roles/{role_id}."""
        # Arrange
        mock_requests["put"].return_value = create_mock_response(
            200, {"success": True, "version": 1}
        )

        # Act
        response = authenticated_client.put(
            "/api/master-cv/roles/01_test_company",
            json={"markdown_content": "# Test"},
        )

        # Assert
        assert response.status_code == 200

    def test_proxy_history_get(self, authenticated_client, mock_db, mock_requests):
        """Should proxy GET /api/master-cv/history/{collection}."""
        # Arrange
        mock_requests["get"].return_value = create_mock_response(
            200, {"success": True, "history": [], "count": 0}
        )

        # Act
        response = authenticated_client.get(
            "/api/master-cv/history/master_cv_metadata?limit=5&doc_id=canonical",
        )

        # Assert
        assert response.status_code == 200
        call_args = mock_requests["get"].call_args
        assert "master_cv_metadata" in call_args[0][0]
        assert "limit=5" in call_args[0][0]

    def test_proxy_rollback_post(self, authenticated_client, mock_db, mock_requests):
        """Should proxy POST /api/master-cv/rollback/{collection}/{version}."""
        # Arrange
        mock_requests["post"].return_value = create_mock_response(
            200, {"success": True, "message": "Rolled back"}
        )

        # Act
        response = authenticated_client.post(
            "/api/master-cv/rollback/master_cv_metadata/1",
            json={"updated_by": "user"},
        )

        # Assert
        assert response.status_code == 200
        call_args = mock_requests["post"].call_args
        assert "rollback" in call_args[0][0]
        assert "master_cv_metadata/1" in call_args[0][0]

    def test_proxy_stats_get(self, authenticated_client, mock_db, mock_requests):
        """Should proxy GET /api/master-cv/stats."""
        # Arrange
        mock_requests["get"].return_value = create_mock_response(
            200, {"success": True, "stats": {}}
        )

        # Act
        response = authenticated_client.get("/api/master-cv/stats")

        # Assert
        assert response.status_code == 200


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestProxyEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_proxy_with_empty_json_body(self, authenticated_client, mock_db, mock_requests):
        """Should handle empty JSON body gracefully."""
        # Arrange
        mock_requests["put"].return_value = create_mock_response(
            400, {"error": "No data provided"}
        )

        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata",
            json={},
        )

        # Assert - Should pass through 400 from runner
        assert response.status_code == 400

    def test_proxy_with_large_json_payload(self, authenticated_client, mock_db, mock_requests):
        """Should handle large JSON payloads."""
        # Arrange
        mock_requests["put"].return_value = create_mock_response(
            200, {"success": True}
        )

        large_payload = {
            "candidate": {"name": "Test" * 1000},
            "roles": [{"id": f"role_{i}"} for i in range(100)],
        }

        # Act
        response = authenticated_client.put(
            "/api/master-cv/metadata",
            json=large_payload,
        )

        # Assert
        assert response.status_code == 200

    def test_proxy_authentication_required(self, client, mock_requests):
        """Should require authentication for all proxy endpoints."""
        # Act - No auth headers (using unauthenticated client)
        response = client.get("/api/master-cv/metadata")

        # Assert
        assert response.status_code in (302, 401, 403)  # Flask redirects to login or returns 401/403
        # Should NOT call runner if auth fails
        assert not mock_requests["get"].called

    def test_proxy_respects_timeout_setting(self, authenticated_client, mock_db, mock_requests):
        """Should use configured timeout value."""
        # Arrange
        mock_requests["get"].return_value = create_mock_response(
            200, {"success": True}
        )

        # Act
        authenticated_client.get("/api/master-cv/metadata")

        # Assert
        call_args = mock_requests["get"].call_args
        assert call_args[1]["timeout"] == 30  # MASTER_CV_REQUEST_TIMEOUT
