"""
Unit tests for frontend/runner.py - Ingestion Proxy Routes

Tests the Flask proxy routes that forward ingestion requests to the runner service:
- POST /api/runner/jobs/ingest/himalaya
- GET /api/runner/jobs/ingest/state/<source>
- DELETE /api/runner/jobs/ingest/state/<source>
- GET /api/runner/jobs/ingest/history/<source>
"""

import pytest
import requests
from unittest.mock import MagicMock


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_requests_module(mocker):
    """Mock the requests module for all HTTP methods."""
    return {
        "post": mocker.patch("frontend.runner.requests.post"),
        "get": mocker.patch("frontend.runner.requests.get"),
        "delete": mocker.patch("frontend.runner.requests.delete"),
    }


def create_mock_response(status_code, json_data):
    """Helper to create a mock Response object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    return mock_resp


# =============================================================================
# HAPPY PATH TESTS - POST /api/runner/jobs/ingest/himalaya
# =============================================================================


class TestIngestHimalayaProxy:
    """Tests for Himalaya ingestion proxy endpoint."""

    def test_proxy_ingest_himalaya_default_params(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should proxy ingestion request with default parameters."""
        # Arrange
        expected_response = {
            "success": True,
            "source": "himalayas_auto",
            "incremental": True,
            "stats": {
                "fetched": 50,
                "ingested": 25,
                "duplicates_skipped": 10,
                "below_threshold": 15,
                "errors": 0,
                "duration_ms": 5000,
            },
            "last_fetch_at": "2025-01-15T10:00:00",
            "jobs": [],
            "error": None,
        }
        mock_requests_module["post"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.post("/api/runner/jobs/ingest/himalaya")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["source"] == "himalayas_auto"
        assert data["stats"]["ingested"] == 25

        # Verify request was made to runner
        mock_requests_module["post"].assert_called_once()
        call_args = mock_requests_module["post"].call_args
        assert "/jobs/ingest/himalaya" in call_args[0][0]
        assert call_args[1]["timeout"] == 120

    def test_proxy_ingest_himalaya_with_query_params(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should forward query parameters to runner."""
        # Arrange
        expected_response = {
            "success": True,
            "source": "himalayas_auto",
            "incremental": False,
            "stats": {"fetched": 10, "ingested": 5},
            "jobs": [],
        }
        mock_requests_module["post"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.post(
            "/api/runner/jobs/ingest/himalaya?"
            "keywords=python&keywords=engineer&"
            "max_results=10&"
            "worldwide_only=true&"
            "skip_scoring=true&"
            "incremental=false&"
            "score_threshold=80"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        # Verify params were forwarded
        call_args = mock_requests_module["post"].call_args
        params = call_args[1]["params"]
        assert "keywords" in params
        assert params["max_results"] == "10"
        assert params["skip_scoring"] == "true"
        assert params["incremental"] == "false"
        assert params["score_threshold"] == "80"

    def test_proxy_ingest_himalaya_with_multiple_keywords(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should handle multiple keyword parameters."""
        # Arrange
        expected_response = {"success": True, "stats": {}, "jobs": []}
        mock_requests_module["post"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.post(
            "/api/runner/jobs/ingest/himalaya?keywords=python&keywords=golang&keywords=rust"
        )

        # Assert
        assert response.status_code == 200

        # Verify keywords list was forwarded
        call_args = mock_requests_module["post"].call_args
        params = call_args[1]["params"]
        assert isinstance(params["keywords"], list)
        assert len(params["keywords"]) == 3


# =============================================================================
# ERROR HANDLING TESTS - POST /api/runner/jobs/ingest/himalaya
# =============================================================================


class TestIngestHimalayaProxyErrors:
    """Tests for error handling in Himalaya ingestion proxy."""

    def test_proxy_ingest_himalaya_timeout(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 504 on timeout."""
        # Arrange
        mock_requests_module["post"].side_effect = requests.exceptions.Timeout()

        # Act
        response = authenticated_client.post("/api/runner/jobs/ingest/himalaya")

        # Assert
        assert response.status_code == 504
        data = response.get_json()
        assert "timeout" in data["error"].lower()
        assert "may still be running" in data["error"]

    def test_proxy_ingest_himalaya_connection_error(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 503 on connection error."""
        # Arrange
        mock_requests_module["post"].side_effect = requests.exceptions.ConnectionError(
            "Cannot connect"
        )

        # Act
        response = authenticated_client.post("/api/runner/jobs/ingest/himalaya")

        # Assert
        assert response.status_code == 503
        data = response.get_json()
        assert "Cannot connect" in data["error"]

    def test_proxy_ingest_himalaya_general_exception(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 500 on unexpected exception."""
        # Arrange
        mock_requests_module["post"].side_effect = ValueError("Unexpected error")

        # Act
        response = authenticated_client.post("/api/runner/jobs/ingest/himalaya")

        # Assert
        assert response.status_code == 500
        data = response.get_json()
        assert "Unexpected error" in data["error"]

    def test_proxy_ingest_himalaya_runner_error_passthrough(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should pass through error status codes from runner."""
        # Arrange
        error_response = {
            "success": False,
            "detail": "Ingestion failed: MongoDB error",
        }
        mock_requests_module["post"].return_value = create_mock_response(
            500, error_response
        )

        # Act
        response = authenticated_client.post("/api/runner/jobs/ingest/himalaya")

        # Assert
        assert response.status_code == 500
        data = response.get_json()
        assert "MongoDB error" in data["detail"]


# =============================================================================
# HAPPY PATH TESTS - GET /api/runner/jobs/ingest/state/<source>
# =============================================================================


class TestGetIngestStateProxy:
    """Tests for ingestion state proxy endpoint."""

    def test_proxy_get_ingest_state_success(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should proxy get state request successfully."""
        # Arrange
        expected_response = {
            "source": "himalayas_auto",
            "last_fetch_at": "2025-01-15T10:00:00",
            "updated_at": "2025-01-15T10:05:00",
            "last_run_stats": {
                "fetched": 50,
                "ingested": 25,
            },
        }
        mock_requests_module["get"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/state/himalayas_auto")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["source"] == "himalayas_auto"
        assert data["last_fetch_at"] is not None
        assert data["last_run_stats"]["ingested"] == 25

        # Verify request was made to runner
        mock_requests_module["get"].assert_called_once()
        call_args = mock_requests_module["get"].call_args
        assert "/jobs/ingest/state/himalayas_auto" in call_args[0][0]
        assert call_args[1]["timeout"] == 30

    def test_proxy_get_ingest_state_no_history(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should handle no history response."""
        # Arrange
        expected_response = {
            "source": "new_source",
            "last_fetch_at": None,
            "last_run_stats": None,
            "message": "No ingestion history found",
        }
        mock_requests_module["get"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/state/new_source")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["last_fetch_at"] is None
        assert "No ingestion history" in data["message"]


# =============================================================================
# ERROR HANDLING TESTS - GET /api/runner/jobs/ingest/state/<source>
# =============================================================================


class TestGetIngestStateProxyErrors:
    """Tests for error handling in get state proxy."""

    def test_proxy_get_state_timeout(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 504 on timeout."""
        # Arrange
        mock_requests_module["get"].side_effect = requests.exceptions.Timeout()

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/state/himalayas_auto")

        # Assert
        assert response.status_code == 504
        data = response.get_json()
        assert "timeout" in data["error"].lower()

    def test_proxy_get_state_connection_error(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 503 on connection error."""
        # Arrange
        mock_requests_module["get"].side_effect = requests.exceptions.ConnectionError()

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/state/himalayas_auto")

        # Assert
        assert response.status_code == 503


# =============================================================================
# HAPPY PATH TESTS - DELETE /api/runner/jobs/ingest/state/<source>
# =============================================================================


class TestResetIngestStateProxy:
    """Tests for reset ingestion state proxy endpoint."""

    def test_proxy_reset_ingest_state_success(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should proxy reset state request successfully."""
        # Arrange
        expected_response = {
            "success": True,
            "message": "Reset ingestion state for himalayas_auto",
        }
        mock_requests_module["delete"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.delete("/api/runner/jobs/ingest/state/himalayas_auto")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "Reset" in data["message"]

        # Verify request was made to runner
        mock_requests_module["delete"].assert_called_once()
        call_args = mock_requests_module["delete"].call_args
        assert "/jobs/ingest/state/himalayas_auto" in call_args[0][0]
        assert call_args[1]["timeout"] == 30

    def test_proxy_reset_ingest_state_no_state_found(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should handle no state found response."""
        # Arrange
        expected_response = {
            "success": True,
            "message": "No state found for nonexistent",
        }
        mock_requests_module["delete"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.delete("/api/runner/jobs/ingest/state/nonexistent")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert "No state found" in data["message"]


# =============================================================================
# ERROR HANDLING TESTS - DELETE /api/runner/jobs/ingest/state/<source>
# =============================================================================


class TestResetIngestStateProxyErrors:
    """Tests for error handling in reset state proxy."""

    def test_proxy_reset_state_timeout(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 504 on timeout."""
        # Arrange
        mock_requests_module["delete"].side_effect = requests.exceptions.Timeout()

        # Act
        response = authenticated_client.delete("/api/runner/jobs/ingest/state/himalayas_auto")

        # Assert
        assert response.status_code == 504

    def test_proxy_reset_state_connection_error(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 503 on connection error."""
        # Arrange
        mock_requests_module["delete"].side_effect = requests.exceptions.ConnectionError()

        # Act
        response = authenticated_client.delete("/api/runner/jobs/ingest/state/himalayas_auto")

        # Assert
        assert response.status_code == 503


# =============================================================================
# HAPPY PATH TESTS - GET /api/runner/jobs/ingest/history/<source>
# =============================================================================


class TestGetIngestHistoryProxy:
    """Tests for ingestion history proxy endpoint."""

    def test_proxy_get_ingest_history_default_limit(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should proxy history request with default limit."""
        # Arrange
        expected_response = {
            "source": "himalayas_auto",
            "runs": [
                {
                    "timestamp": "2025-01-15T10:00:00",
                    "stats": {"fetched": 50, "ingested": 25},
                },
                {
                    "timestamp": "2025-01-14T10:00:00",
                    "stats": {"fetched": 40, "ingested": 20},
                },
            ],
            "total_runs": 2,
        }
        mock_requests_module["get"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/history/himalayas_auto")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["source"] == "himalayas_auto"
        assert len(data["runs"]) == 2
        assert data["total_runs"] == 2

        # Verify request was made to runner
        mock_requests_module["get"].assert_called_once()
        call_args = mock_requests_module["get"].call_args
        assert "/jobs/ingest/history/himalayas_auto" in call_args[0][0]

    def test_proxy_get_ingest_history_with_limit(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should forward limit parameter to runner."""
        # Arrange
        expected_response = {
            "source": "himalayas_auto",
            "runs": [{"timestamp": "2025-01-15T10:00:00", "stats": {}}],
            "total_runs": 50,
        }
        mock_requests_module["get"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.get(
            "/api/runner/jobs/ingest/history/himalayas_auto?limit=10"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["runs"]) == 1
        assert data["total_runs"] == 50

        # Verify limit was forwarded
        call_args = mock_requests_module["get"].call_args
        params = call_args[1]["params"]
        assert params["limit"] == "10"

    def test_proxy_get_ingest_history_no_history(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should handle no history response."""
        # Arrange
        expected_response = {
            "source": "new_source",
            "runs": [],
            "message": "No ingestion history found",
        }
        mock_requests_module["get"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/history/new_source")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["runs"] == []
        assert "No ingestion history" in data["message"]


# =============================================================================
# ERROR HANDLING TESTS - GET /api/runner/jobs/ingest/history/<source>
# =============================================================================


class TestGetIngestHistoryProxyErrors:
    """Tests for error handling in history proxy."""

    def test_proxy_get_history_timeout(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 504 on timeout."""
        # Arrange
        mock_requests_module["get"].side_effect = requests.exceptions.Timeout()

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/history/himalayas_auto")

        # Assert
        assert response.status_code == 504

    def test_proxy_get_history_connection_error(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 503 on connection error."""
        # Arrange
        mock_requests_module["get"].side_effect = requests.exceptions.ConnectionError()

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/history/himalayas_auto")

        # Assert
        assert response.status_code == 503

    def test_proxy_get_history_general_exception(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 500 on unexpected exception."""
        # Arrange
        mock_requests_module["get"].side_effect = ValueError("Unexpected error")

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/history/himalayas_auto")

        # Assert
        assert response.status_code == 500


# =============================================================================
# HAPPY PATH TESTS - GET /api/runner/jobs/ingest/<run_id>/result
# =============================================================================


class TestGetIngestResultProxy:
    """Tests for ingestion result proxy endpoint."""

    def test_proxy_get_ingest_result_success(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should proxy get result request successfully."""
        # Arrange
        expected_response = {
            "result": {
                "success": True,
                "stats": {
                    "fetched": 50,
                    "ingested": 25,
                    "duplicates_skipped": 10,
                    "below_threshold": 15,
                },
                "jobs": [{"id": "job1"}, {"id": "job2"}],
            }
        }
        mock_requests_module["get"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/test-run-id-123/result")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["result"]["success"] is True
        assert data["result"]["stats"]["ingested"] == 25

        # Verify request was made to runner
        mock_requests_module["get"].assert_called_once()
        call_args = mock_requests_module["get"].call_args
        assert "/jobs/ingest/test-run-id-123/result" in call_args[0][0]
        assert call_args[1]["timeout"] == 30

    def test_proxy_get_ingest_result_pending(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should handle pending result response."""
        # Arrange
        expected_response = {
            "status": "running",
            "message": "Ingestion still in progress",
        }
        mock_requests_module["get"].return_value = create_mock_response(
            200, expected_response
        )

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/run-123/result")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "running"

    def test_proxy_get_ingest_result_not_found(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should handle not found result response."""
        # Arrange
        expected_response = {"error": "Run not found"}
        mock_requests_module["get"].return_value = create_mock_response(
            404, expected_response
        )

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/nonexistent/result")

        # Assert
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data


# =============================================================================
# ERROR HANDLING TESTS - GET /api/runner/jobs/ingest/<run_id>/result
# =============================================================================


class TestGetIngestResultProxyErrors:
    """Tests for error handling in get result proxy."""

    def test_proxy_get_result_timeout(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 504 on timeout."""
        # Arrange
        mock_requests_module["get"].side_effect = requests.exceptions.Timeout()

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/run-123/result")

        # Assert
        assert response.status_code == 504
        data = response.get_json()
        assert "timeout" in data["error"].lower()

    def test_proxy_get_result_connection_error(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should return 503 on connection error."""
        # Arrange
        mock_requests_module["get"].side_effect = requests.exceptions.ConnectionError()

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/run-123/result")

        # Assert
        assert response.status_code == 503


# =============================================================================
# AUTHENTICATION TESTS
# =============================================================================
# Note: Authentication is handled at the runner service layer, not in the Flask proxy.
# The proxy forwards the RUNNER_API_SECRET header to the runner service.


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestIngestProxyEdgeCases:
    """Tests for edge cases in ingestion proxy routes."""

    def test_proxy_handles_runner_unavailable(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should handle case when runner service is down."""
        # Arrange
        mock_requests_module["post"].side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        # Act
        response = authenticated_client.post("/api/runner/jobs/ingest/himalaya")

        # Assert
        assert response.status_code == 503
        data = response.get_json()
        assert "Cannot connect" in data["error"]

    def test_proxy_respects_timeout_setting(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should use correct timeout for ingestion (120s)."""
        # Arrange
        mock_requests_module["post"].return_value = create_mock_response(
            200, {"success": True, "stats": {}, "jobs": []}
        )

        # Act
        authenticated_client.post("/api/runner/jobs/ingest/himalaya")

        # Assert
        call_args = mock_requests_module["post"].call_args
        assert call_args[1]["timeout"] == 120  # Longer timeout for ingestion

    def test_proxy_handles_malformed_runner_response(
        self, authenticated_client, mock_db, mock_requests_module
    ):
        """Should handle case when runner returns malformed JSON."""
        # Arrange
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_requests_module["get"].return_value = mock_resp

        # Act
        response = authenticated_client.get("/api/runner/jobs/ingest/state/himalayas_auto")

        # Assert
        assert response.status_code == 500
