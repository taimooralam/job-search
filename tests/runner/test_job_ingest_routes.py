"""
Unit tests for runner_service/routes/job_ingest.py

Tests the runner service ingestion endpoints:
- POST /jobs/ingest/himalaya
- GET /jobs/ingest/state/{source}
- DELETE /jobs/ingest/state/{source}
- GET /jobs/ingest/history/{source}
- GET /jobs/ingest/{run_id}/result

NOTE: The ingestion endpoints are now async - they return immediately with a
run_id and status="queued". The actual ingestion runs in a background task.
Error handling for the ingestion process is tested via the result endpoint.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from bson import ObjectId


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db(mocker):
    """Mock MongoDB database and collections."""
    mock_collection = MagicMock()
    mock_system_state = MagicMock()

    mock_db_instance = MagicMock()
    mock_db_instance.__getitem__.side_effect = lambda name: {
        "level-2": mock_collection,
        "system_state": mock_system_state,
    }[name]

    # Mock MongoClient
    mocker.patch("runner_service.routes.job_ingest.get_db", return_value=mock_db_instance)

    return {
        "db": mock_db_instance,
        "level2": mock_collection,
        "system_state": mock_system_state,
    }


@pytest.fixture
def mock_himalaya_source(mocker):
    """Mock HimalayasSource for job fetching."""
    mock_source = MagicMock()
    mock_source.fetch_jobs.return_value = [
        MagicMock(
            company="TestCorp",
            title="Software Engineer",
            location="Remote",
            url="https://example.com/job1",
            description="Great job",
            salary="$120k-150k",
            job_type="Full-time",
            posted_date=datetime.utcnow(),
            source_id="test_001",
        ),
        MagicMock(
            company="StartupCo",
            title="Senior Engineer",
            location="Worldwide",
            url="https://example.com/job2",
            description="Amazing opportunity",
            salary="$150k-180k",
            job_type="Full-time",
            posted_date=datetime.utcnow(),
            source_id="test_002",
        ),
    ]

    # Patch at the source module level since it's imported inside the function
    mocker.patch(
        "src.services.job_sources.HimalayasSource",
        return_value=mock_source,
    )

    return mock_source


@pytest.fixture
def mock_ingest_service(mocker):
    """Mock IngestService."""
    mock_service = MagicMock()

    # Mock the ingest_jobs method to return a successful result
    mock_result = MagicMock()
    mock_result.to_dict.return_value = {
        "success": True,
        "source": "himalayas_auto",
        "incremental": True,
        "stats": {
            "fetched": 2,
            "ingested": 2,
            "duplicates_skipped": 0,
            "below_threshold": 0,
            "errors": 0,
            "duration_ms": 1500,
        },
        "last_fetch_at": datetime.utcnow().isoformat(),
        "jobs": [
            {
                "job_id": str(ObjectId()),
                "title": "Software Engineer",
                "company": "TestCorp",
                "score": 85,
                "tier": "A",
            },
        ],
        "error": None,
    }
    mock_service.ingest_jobs = AsyncMock(return_value=mock_result)

    # Patch at the source module level since it's imported inside the function
    mocker.patch(
        "src.services.job_ingest_service.IngestService",
        return_value=mock_service,
    )

    return mock_service


@pytest.fixture
def mock_operation_streaming(mocker):
    """Mock operation streaming functions for async endpoints."""
    mocker.patch(
        "runner_service.routes.job_ingest.create_operation_run",
        return_value="op_ingest-himalaya_abc123",
    )
    mocker.patch(
        "runner_service.routes.job_ingest.create_log_callback",
        return_value=lambda msg: None,
    )
    mocker.patch(
        "runner_service.routes.job_ingest.update_operation_status",
    )
    mocker.patch(
        "runner_service.routes.job_ingest.get_operation_state",
        return_value=MagicMock(status="queued"),
    )


# =============================================================================
# HAPPY PATH TESTS - POST /jobs/ingest/himalaya (Async API)
# =============================================================================


class TestIngestHimalayaJobs:
    """Tests for the Himalaya job ingestion endpoint (async API)."""

    @pytest.mark.asyncio
    async def test_ingest_himalaya_returns_run_id(
        self, client, auth_headers, mock_db, mock_himalaya_source, mock_ingest_service, mock_operation_streaming
    ):
        """Should return run_id and queued status immediately."""
        # Act
        response = client.post("/jobs/ingest/himalaya", headers=auth_headers)

        # Assert - Async API returns immediately with run_id
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "queued"
        assert data["source"] == "himalayas_auto"

    @pytest.mark.asyncio
    async def test_ingest_himalaya_with_custom_keywords(
        self, client, auth_headers, mock_db, mock_himalaya_source, mock_ingest_service, mock_operation_streaming
    ):
        """Should accept custom keywords and return run_id."""
        # Act
        response = client.post(
            "/jobs/ingest/himalaya?keywords=python&keywords=engineer",
            headers=auth_headers,
        )

        # Assert - Async API returns immediately
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "queued"
        assert data["source"] == "himalayas_auto"

    @pytest.mark.asyncio
    async def test_ingest_himalaya_with_max_results(
        self, client, auth_headers, mock_db, mock_himalaya_source, mock_ingest_service, mock_operation_streaming
    ):
        """Should accept max_results parameter and return run_id."""
        # Act
        response = client.post(
            "/jobs/ingest/himalaya?max_results=10",
            headers=auth_headers,
        )

        # Assert - Async API returns immediately
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "queued"

    @pytest.mark.asyncio
    async def test_ingest_himalaya_skip_scoring(
        self, client, auth_headers, mock_db, mock_himalaya_source, mock_ingest_service, mock_operation_streaming
    ):
        """Should accept skip_scoring parameter and return run_id."""
        # Act
        response = client.post(
            "/jobs/ingest/himalaya?skip_scoring=true",
            headers=auth_headers,
        )

        # Assert - Async API returns immediately
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "queued"

    @pytest.mark.asyncio
    async def test_ingest_himalaya_non_incremental(
        self, client, auth_headers, mock_db, mock_himalaya_source, mock_ingest_service, mock_operation_streaming
    ):
        """Should accept incremental=false parameter and return run_id."""
        # Act
        response = client.post(
            "/jobs/ingest/himalaya?incremental=false",
            headers=auth_headers,
        )

        # Assert - Async API returns immediately
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "queued"

    @pytest.mark.asyncio
    async def test_ingest_himalaya_custom_threshold(
        self, client, auth_headers, mock_db, mock_himalaya_source, mock_ingest_service, mock_operation_streaming
    ):
        """Should accept custom score threshold and return run_id."""
        # Act
        response = client.post(
            "/jobs/ingest/himalaya?score_threshold=80",
            headers=auth_headers,
        )

        # Assert - Async API returns immediately
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "queued"

    @pytest.mark.asyncio
    async def test_ingest_himalaya_worldwide_only_false(
        self, client, auth_headers, mock_db, mock_himalaya_source, mock_ingest_service, mock_operation_streaming
    ):
        """Should accept worldwide_only=false parameter and return run_id."""
        # Act
        response = client.post(
            "/jobs/ingest/himalaya?worldwide_only=false",
            headers=auth_headers,
        )

        # Assert - Async API returns immediately
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "queued"


# =============================================================================
# VALIDATION TESTS - POST /jobs/ingest/himalaya
# =============================================================================


class TestIngestHimalayaValidation:
    """Tests for parameter validation in Himalaya ingestion."""

    @pytest.mark.asyncio
    async def test_ingest_himalaya_max_results_exceeds_limit(
        self, client, auth_headers, mock_db, mock_himalaya_source, mock_ingest_service, mock_operation_streaming
    ):
        """Should reject max_results > 100."""
        # Act
        response = client.post(
            "/jobs/ingest/himalaya?max_results=150",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_ingest_himalaya_invalid_score_threshold(
        self, client, auth_headers, mock_db, mock_himalaya_source, mock_ingest_service, mock_operation_streaming
    ):
        """Should reject score_threshold outside 0-100 range."""
        # Act
        response = client.post(
            "/jobs/ingest/himalaya?score_threshold=150",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 422  # Validation error


# =============================================================================
# ERROR TESTS - Background Task Errors (via result endpoint)
#
# NOTE: Since errors now happen in background tasks, the initial POST always
# returns 200 with a run_id. Error handling is tested via the result endpoint.
# =============================================================================


class TestIngestResultEndpoint:
    """Tests for the ingestion result endpoint."""

    def test_get_ingest_result_completed(self, client, auth_headers, mocker):
        """Should return completed result with data."""
        # Arrange
        from runner_service.routes.job_ingest import IngestResponse

        mock_result = IngestResponse(
            success=True,
            source="himalayas_auto",
            incremental=True,
            stats={"fetched": 5, "ingested": 3},
            last_fetch_at="2025-01-15T10:00:00",
            jobs=[{"title": "Test Job"}],
            error=None,
        )

        mocker.patch(
            "runner_service.routes.job_ingest.get_operation_state",
            return_value=MagicMock(status="completed", error=None),
        )
        mocker.patch(
            "runner_service.routes.job_ingest._get_stored_ingest_result",
            return_value=mock_result,
        )

        # Act
        response = client.get(
            "/jobs/ingest/op_test123/result",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "op_test123"
        assert data["status"] == "completed"
        assert data["result"]["success"] is True
        assert data["result"]["stats"]["ingested"] == 3

    def test_get_ingest_result_failed(self, client, auth_headers, mocker):
        """Should return failed status with error message."""
        # Arrange
        from runner_service.routes.job_ingest import IngestResponse

        mock_result = IngestResponse(
            success=False,
            source="himalayas_auto",
            incremental=True,
            stats={"fetched": 0, "ingested": 0},
            last_fetch_at=None,
            jobs=[],
            error="API timeout",
        )

        mocker.patch(
            "runner_service.routes.job_ingest.get_operation_state",
            return_value=MagicMock(status="failed", error="API timeout"),
        )
        mocker.patch(
            "runner_service.routes.job_ingest._get_stored_ingest_result",
            return_value=mock_result,
        )

        # Act
        response = client.get(
            "/jobs/ingest/op_test123/result",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "op_test123"
        assert data["status"] == "failed"
        assert data["result"]["success"] is False
        assert data["result"]["error"] == "API timeout"

    def test_get_ingest_result_still_running(self, client, auth_headers, mocker):
        """Should return running status when operation not complete."""
        # Arrange
        mocker.patch(
            "runner_service.routes.job_ingest.get_operation_state",
            return_value=MagicMock(status="running", error=None),
        )
        mocker.patch(
            "runner_service.routes.job_ingest._get_stored_ingest_result",
            return_value=None,
        )

        # Act
        response = client.get(
            "/jobs/ingest/op_test123/result",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "op_test123"
        assert data["status"] == "running"
        assert data["result"] is None

    def test_get_ingest_result_not_found(self, client, auth_headers, mocker):
        """Should return 404 when run_id not found."""
        # Arrange
        mocker.patch(
            "runner_service.routes.job_ingest.get_operation_state",
            return_value=None,
        )

        # Act
        response = client.get(
            "/jobs/ingest/op_nonexistent/result",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 404


# =============================================================================
# HAPPY PATH TESTS - GET /jobs/ingest/state/{source}
# =============================================================================


class TestGetIngestState:
    """Tests for getting ingestion state."""

    def test_get_ingest_state_success(self, client, auth_headers, mock_db):
        """Should return ingestion state for a source."""
        # Arrange
        mock_db["system_state"].find_one.return_value = {
            "_id": "ingest_himalayas_auto",
            "last_fetch_at": datetime(2025, 1, 15, 10, 0, 0),
            "updated_at": datetime(2025, 1, 15, 10, 5, 0),
            "last_run_stats": {
                "fetched": 50,
                "ingested": 25,
                "duplicates_skipped": 15,
                "below_threshold": 10,
            },
        }

        # Act
        response = client.get(
            "/jobs/ingest/state/himalayas_auto",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "himalayas_auto"
        assert data["last_fetch_at"] is not None
        assert data["last_run_stats"]["ingested"] == 25
        mock_db["system_state"].find_one.assert_called_once_with(
            {"_id": "ingest_himalayas_auto"}
        )

    def test_get_ingest_state_no_history(self, client, auth_headers, mock_db):
        """Should return message when no history exists."""
        # Arrange
        mock_db["system_state"].find_one.return_value = None

        # Act
        response = client.get(
            "/jobs/ingest/state/new_source",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "new_source"
        assert data["last_fetch_at"] is None
        assert "No ingestion history" in data["message"]

    def test_get_ingest_state_mongodb_error(self, client, auth_headers, mock_db):
        """Should return 500 on database error."""
        # Arrange
        mock_db["system_state"].find_one.side_effect = Exception("DB error")

        # Act
        response = client.get(
            "/jobs/ingest/state/himalayas_auto",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 500


# =============================================================================
# HAPPY PATH TESTS - DELETE /jobs/ingest/state/{source}
# =============================================================================


class TestResetIngestState:
    """Tests for resetting ingestion state."""

    def test_reset_ingest_state_success(self, client, auth_headers, mock_db):
        """Should delete ingestion state successfully."""
        # Arrange
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_db["system_state"].delete_one.return_value = mock_result

        # Act
        response = client.delete(
            "/jobs/ingest/state/himalayas_auto",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Reset" in data["message"]
        mock_db["system_state"].delete_one.assert_called_once_with(
            {"_id": "ingest_himalayas_auto"}
        )

    def test_reset_ingest_state_no_state_found(self, client, auth_headers, mock_db):
        """Should return success even if no state exists."""
        # Arrange
        mock_result = MagicMock()
        mock_result.deleted_count = 0
        mock_db["system_state"].delete_one.return_value = mock_result

        # Act
        response = client.delete(
            "/jobs/ingest/state/nonexistent",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "No state found" in data["message"]

    def test_reset_ingest_state_mongodb_error(self, client, auth_headers, mock_db):
        """Should return 500 on database error."""
        # Arrange
        mock_db["system_state"].delete_one.side_effect = Exception("DB error")

        # Act
        response = client.delete(
            "/jobs/ingest/state/himalayas_auto",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 500


# =============================================================================
# HAPPY PATH TESTS - GET /jobs/ingest/history/{source}
# =============================================================================


class TestGetIngestHistory:
    """Tests for getting ingestion run history."""

    def test_get_ingest_history_success(self, client, auth_headers, mock_db):
        """Should return ingestion history with default limit."""
        # Arrange
        mock_db["system_state"].find_one.return_value = {
            "_id": "ingest_himalayas_auto",
            "run_history": [
                {
                    "timestamp": datetime(2025, 1, 15, 10, 0, 0),
                    "stats": {"fetched": 50, "ingested": 25},
                },
                {
                    "timestamp": datetime(2025, 1, 14, 10, 0, 0),
                    "stats": {"fetched": 40, "ingested": 20},
                },
                {
                    "timestamp": datetime(2025, 1, 13, 10, 0, 0),
                    "stats": {"fetched": 30, "ingested": 15},
                },
            ],
        }

        # Act
        response = client.get(
            "/jobs/ingest/history/himalayas_auto",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "himalayas_auto"
        assert len(data["runs"]) == 3
        assert data["total_runs"] == 3
        # Verify sorted by timestamp descending
        assert data["runs"][0]["timestamp"] > data["runs"][1]["timestamp"]

    def test_get_ingest_history_with_limit(self, client, auth_headers, mock_db):
        """Should respect limit parameter."""
        # Arrange
        runs = [
            {
                "timestamp": datetime(2025, 1, i, 10, 0, 0),
                "stats": {"fetched": i * 10, "ingested": i * 5},
            }
            for i in range(1, 26)  # 25 runs
        ]
        mock_db["system_state"].find_one.return_value = {
            "_id": "ingest_himalayas_auto",
            "run_history": runs,
        }

        # Act
        response = client.get(
            "/jobs/ingest/history/himalayas_auto?limit=10",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["runs"]) == 10
        assert data["total_runs"] == 25

    def test_get_ingest_history_limit_max(self, client, auth_headers, mock_db):
        """Should enforce maximum limit of 50."""
        # Arrange
        mock_db["system_state"].find_one.return_value = {
            "_id": "ingest_himalayas_auto",
            "run_history": [],
        }

        # Act
        response = client.get(
            "/jobs/ingest/history/himalayas_auto?limit=100",
            headers=auth_headers,
        )

        # Assert - Should reject limit > 50
        assert response.status_code == 422

    def test_get_ingest_history_no_history(self, client, auth_headers, mock_db):
        """Should return empty list when no history exists."""
        # Arrange
        mock_db["system_state"].find_one.return_value = None

        # Act
        response = client.get(
            "/jobs/ingest/history/new_source",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "new_source"
        assert data["runs"] == []
        assert "No ingestion history" in data["message"]

    def test_get_ingest_history_empty_run_history(self, client, auth_headers, mock_db):
        """Should handle state with empty run_history array."""
        # Arrange
        mock_db["system_state"].find_one.return_value = {
            "_id": "ingest_himalayas_auto",
            "run_history": [],
        }

        # Act
        response = client.get(
            "/jobs/ingest/history/himalayas_auto",
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["runs"] == []
        assert data["total_runs"] == 0


# =============================================================================
# AUTHENTICATION TESTS
# =============================================================================


class TestIngestAuthenticationRequired:
    """Tests that all endpoints require authentication."""

    def test_ingest_himalaya_requires_auth(self, client):
        """Should reject request without valid token."""
        # Act
        response = client.post("/jobs/ingest/himalaya")

        # Assert
        assert response.status_code == 401

    def test_get_state_requires_auth(self, client):
        """Should reject request without valid token."""
        # Act
        response = client.get("/jobs/ingest/state/himalayas_auto")

        # Assert
        assert response.status_code == 401

    def test_reset_state_requires_auth(self, client):
        """Should reject request without valid token."""
        # Act
        response = client.delete("/jobs/ingest/state/himalayas_auto")

        # Assert
        assert response.status_code == 401

    def test_get_history_requires_auth(self, client):
        """Should reject request without valid token."""
        # Act
        response = client.get("/jobs/ingest/history/himalayas_auto")

        # Assert
        assert response.status_code == 401

    def test_get_result_requires_auth(self, client):
        """Should reject request without valid token."""
        # Act
        response = client.get("/jobs/ingest/op_test123/result")

        # Assert
        assert response.status_code == 401
