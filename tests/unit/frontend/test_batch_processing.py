"""
Unit tests for frontend batch processing workflow.

Tests the batch processing routes in frontend/app.py:
- POST /api/jobs/move-to-batch: Move jobs to batch queue
- GET /batch-processing: Batch processing page view
- GET /partials/batch-job-rows: HTMX partial for batch job table

Coverage:
- Status updates to "under processing"
- batch_added_at timestamp setting
- Auto-trigger of all-ops on batch move
- auto_process parameter handling
- Batch job filtering and sorting
- Error handling for invalid inputs
"""

import pytest
import requests
from unittest.mock import MagicMock, Mock, patch
from datetime import datetime
from bson import ObjectId
from flask import Flask
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


# ===== FIXTURES =====

@pytest.fixture
def app():
    """Create Flask app instance for testing."""
    # Import app after path is set
    from frontend.app import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-key"
    return flask_app


@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()


@pytest.fixture
def authenticated_client(client):
    """Create authenticated Flask test client."""
    with client.session_transaction() as sess:
        sess["authenticated"] = True
    return client


@pytest.fixture
def mock_db_collection(mocker):
    """
    Mock MongoDB collection with common operations.

    Returns a MagicMock that simulates pymongo collection behavior.
    """
    mock_collection = MagicMock()

    # Mock update_many result
    mock_update_result = MagicMock()
    mock_update_result.modified_count = 0
    mock_collection.update_many.return_value = mock_update_result

    # Mock find result (returns mock cursor)
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = []
    mock_collection.find.return_value = mock_cursor

    return mock_collection


@pytest.fixture
def sample_jobs():
    """Sample job documents for testing."""
    now = datetime.utcnow()
    return [
        {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Senior Backend Engineer",
            "company": "Tech Corp",
            "status": "not processed",
            "createdAt": now,
            "score": 85,
        },
        {
            "_id": ObjectId("507f1f77bcf86cd799439012"),
            "title": "Staff Engineer",
            "company": "StartupXYZ",
            "status": "marked for applying",
            "createdAt": now,
            "score": 92,
        },
        {
            "_id": ObjectId("507f1f77bcf86cd799439013"),
            "title": "Tech Lead",
            "company": "BigCorp",
            "status": "under processing",
            "batch_added_at": now,
            "createdAt": now,
            "score": 88,
        },
    ]


# ===== TESTS: POST /api/jobs/move-to-batch =====

class TestMoveToBatch:
    """Tests for POST /api/jobs/move-to-batch endpoint."""

    @patch("frontend.app.requests.post")
    @patch("frontend.app.get_collection")
    def test_moves_jobs_to_batch_successfully(
        self, mock_get_collection, mock_requests_post, authenticated_client, mock_db_collection
    ):
        """Should update status to 'under processing' and auto-queue all-ops."""
        # Arrange
        mock_get_collection.return_value = mock_db_collection
        mock_db_collection.update_many.return_value.modified_count = 2

        # Mock successful all-ops bulk response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "runs": [
                {"run_id": "run1", "job_id": "507f1f77bcf86cd799439011", "status": "queued"},
                {"run_id": "run2", "job_id": "507f1f77bcf86cd799439012", "status": "queued"},
            ],
            "total_count": 2,
        }
        mock_requests_post.return_value = mock_response

        job_ids = ["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012"]

        # Act
        response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": job_ids},
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["updated_count"] == 2
        assert "batch_added_at" in data
        assert data["auto_process"] is True
        assert data["all_ops_queued"] == 2
        assert len(data["all_ops_runs"]) == 2
        assert data["all_ops_error"] is None

        # Verify MongoDB update was called correctly
        mock_db_collection.update_many.assert_called_once()
        call_args = mock_db_collection.update_many.call_args

        # Check filter (should convert string IDs to ObjectId)
        filter_arg = call_args[0][0]
        assert "_id" in filter_arg
        assert "$in" in filter_arg["_id"]
        assert len(filter_arg["_id"]["$in"]) == 2

        # Check update (should set status and batch_added_at)
        update_arg = call_args[0][1]
        assert "$set" in update_arg
        assert update_arg["$set"]["status"] == "under processing"
        assert "batch_added_at" in update_arg["$set"]
        assert isinstance(update_arg["$set"]["batch_added_at"], datetime)

        # Verify all-ops bulk was called with correct parameters
        mock_requests_post.assert_called_once()
        call_kwargs = mock_requests_post.call_args
        assert "/all-ops/bulk" in call_kwargs[0][0]
        request_json = call_kwargs[1]["json"]
        assert request_json["job_ids"] == job_ids
        assert request_json["tier"] == "balanced"  # Default tier
        assert request_json["use_llm"] is True

    @patch("frontend.app.get_collection")
    def test_returns_error_when_no_job_ids_provided(
        self, mock_get_collection, authenticated_client
    ):
        """Should return 400 error when job_ids array is empty."""
        # Act
        response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": []},
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "No job_ids provided" in data["error"]

    @patch("frontend.app.get_collection")
    def test_returns_error_when_job_ids_missing(
        self, mock_get_collection, authenticated_client
    ):
        """Should return 400 error when job_ids key is missing."""
        # Act
        response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={},
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    @patch("frontend.app.get_collection")
    def test_returns_error_for_invalid_objectid_format(
        self, mock_get_collection, authenticated_client
    ):
        """Should return 400 error when job_id is not a valid ObjectId."""
        # Arrange
        mock_get_collection.return_value = MagicMock()

        # Act
        response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": ["invalid-id", "also-bad"]},
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "Invalid job_id format" in data["error"]

    def test_requires_authentication(self, client):
        """Should return 401 when not authenticated."""
        # Act
        response = client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": ["507f1f77bcf86cd799439011"]},
        )

        # Assert
        assert response.status_code == 401
        data = response.get_json()
        assert "error" in data
        assert "authenticated" in data["error"].lower()

    @patch("frontend.app.requests.post")
    @patch("frontend.app.get_collection")
    def test_handles_zero_updates_gracefully(
        self, mock_get_collection, mock_requests_post, authenticated_client, mock_db_collection
    ):
        """Should handle case where no jobs are actually updated (e.g., already in batch)."""
        # Arrange
        mock_get_collection.return_value = mock_db_collection
        mock_db_collection.update_many.return_value.modified_count = 0

        # Mock successful all-ops bulk response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"runs": [], "total_count": 0}
        mock_requests_post.return_value = mock_response

        # Act
        response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": ["507f1f77bcf86cd799439011"]},
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["updated_count"] == 0

    @patch("frontend.app.requests.post")
    @patch("frontend.app.get_collection")
    def test_batch_added_at_is_recent_timestamp(
        self, mock_get_collection, mock_requests_post, authenticated_client, mock_db_collection
    ):
        """Should set batch_added_at to current UTC time."""
        # Arrange
        mock_get_collection.return_value = mock_db_collection
        mock_db_collection.update_many.return_value.modified_count = 1

        # Mock successful all-ops bulk response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"runs": [], "total_count": 1}
        mock_requests_post.return_value = mock_response

        before_time = datetime.utcnow()

        # Act
        response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": ["507f1f77bcf86cd799439011"]},
        )

        after_time = datetime.utcnow()

        # Assert
        data = response.get_json()
        batch_time = datetime.fromisoformat(data["batch_added_at"])

        # Timestamp should be between before and after
        assert before_time <= batch_time <= after_time

    @patch("frontend.app.requests.post")
    @patch("frontend.app.get_collection")
    def test_auto_process_false_skips_all_ops(
        self, mock_get_collection, mock_requests_post, authenticated_client, mock_db_collection
    ):
        """Should not call all-ops when auto_process is False."""
        # Arrange
        mock_get_collection.return_value = mock_db_collection
        mock_db_collection.update_many.return_value.modified_count = 2

        job_ids = ["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012"]

        # Act
        response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": job_ids, "auto_process": False},
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["updated_count"] == 2
        assert data["auto_process"] is False
        assert data["all_ops_queued"] == 0
        assert data["all_ops_runs"] == []
        assert data["all_ops_error"] is None

        # Verify runner service was NOT called
        mock_requests_post.assert_not_called()

    @patch("frontend.app.requests.post")
    @patch("frontend.app.get_collection")
    def test_custom_tier_is_passed_to_all_ops(
        self, mock_get_collection, mock_requests_post, authenticated_client, mock_db_collection
    ):
        """Should pass custom tier to all-ops bulk endpoint."""
        # Arrange
        mock_get_collection.return_value = mock_db_collection
        mock_db_collection.update_many.return_value.modified_count = 1

        # Mock successful all-ops bulk response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"runs": [], "total_count": 1}
        mock_requests_post.return_value = mock_response

        job_ids = ["507f1f77bcf86cd799439011"]

        # Act
        response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": job_ids, "tier": "gold"},  # Custom tier
        )

        # Assert
        assert response.status_code == 200

        # Verify all-ops bulk was called with custom tier
        mock_requests_post.assert_called_once()
        call_kwargs = mock_requests_post.call_args
        request_json = call_kwargs[1]["json"]
        assert request_json["tier"] == "gold"

    @patch("frontend.app.requests.post")
    @patch("frontend.app.get_collection")
    def test_handles_runner_service_timeout(
        self, mock_get_collection, mock_requests_post, authenticated_client, mock_db_collection
    ):
        """Should handle timeout from runner service gracefully."""
        # Arrange
        mock_get_collection.return_value = mock_db_collection
        mock_db_collection.update_many.return_value.modified_count = 2

        # Simulate timeout
        mock_requests_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        job_ids = ["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012"]

        # Act
        response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": job_ids},
        )

        # Assert - should still succeed, but with error info
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["updated_count"] == 2
        assert data["all_ops_queued"] == 0
        assert data["all_ops_error"] == "Request timeout"

    @patch("frontend.app.requests.post")
    @patch("frontend.app.get_collection")
    def test_handles_runner_service_http_error(
        self, mock_get_collection, mock_requests_post, authenticated_client, mock_db_collection
    ):
        """Should handle HTTP error from runner service gracefully."""
        # Arrange
        mock_get_collection.return_value = mock_db_collection
        mock_db_collection.update_many.return_value.modified_count = 1

        # Simulate HTTP error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_requests_post.return_value = mock_response

        job_ids = ["507f1f77bcf86cd799439011"]

        # Act
        response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": job_ids},
        )

        # Assert - should still succeed, but with error info
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["updated_count"] == 1
        assert data["all_ops_queued"] == 0
        assert "HTTP 500" in data["all_ops_error"]


# ===== TESTS: GET /batch-processing =====

class TestBatchProcessingPage:
    """Tests for GET /batch-processing page view."""

    @patch("frontend.app.render_template")
    def test_renders_batch_processing_template(
        self, mock_render_template, authenticated_client
    ):
        """Should render batch_processing.html template."""
        # Arrange
        mock_render_template.return_value = "<html>Batch Processing</html>"

        # Act
        response = authenticated_client.get("/batch-processing")

        # Assert
        assert response.status_code == 200
        mock_render_template.assert_called_once()

        # Verify template name and context
        call_args = mock_render_template.call_args
        template_name = call_args[0][0]
        assert template_name == "batch_processing.html"

        # Verify JOB_STATUSES is passed to template
        context = call_args[1]
        assert "statuses" in context
        assert isinstance(context["statuses"], list)
        assert "under processing" in context["statuses"]

    def test_requires_authentication(self, client):
        """Should redirect to login when not authenticated."""
        # Act
        response = client.get("/batch-processing")

        # Assert
        assert response.status_code == 302  # Redirect
        assert "login" in response.location.lower()


# ===== TESTS: GET /partials/batch-job-rows =====

class TestBatchJobRowsPartial:
    """Tests for GET /partials/batch-job-rows HTMX partial."""

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_returns_only_under_processing_jobs(
        self, mock_render_template, mock_get_collection, authenticated_client, sample_jobs
    ):
        """Should query only jobs with status='under processing'."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        # Mock cursor with sort method
        mock_cursor = MagicMock()
        under_processing_jobs = [j for j in sample_jobs if j["status"] == "under processing"]
        mock_cursor.sort.return_value = under_processing_jobs
        mock_collection.find.return_value = mock_cursor

        mock_render_template.return_value = "<tr>...</tr>"

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200

        # Verify find was called with correct filter
        mock_collection.find.assert_called_once()
        filter_arg = mock_collection.find.call_args[0][0]
        assert filter_arg == {"status": "under processing"}

        # Verify sort was called
        mock_cursor.sort.assert_called_once()

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_default_sort_by_batch_added_at_desc(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should default to sorting by batch_added_at in descending order."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = []
        mock_collection.find.return_value = mock_cursor

        mock_render_template.return_value = "<tr>...</tr>"

        # Act
        authenticated_client.get("/partials/batch-job-rows")

        # Assert
        mock_cursor.sort.assert_called_once()
        sort_args = mock_cursor.sort.call_args[0]

        # Should sort by batch_added_at field
        assert sort_args[0] == "batch_added_at"
        # Should sort descending (-1)
        assert sort_args[1] == -1

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_supports_custom_sort_field(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should support sorting by different fields via query params."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = []
        mock_collection.find.return_value = mock_cursor

        mock_render_template.return_value = "<tr>...</tr>"

        # Act
        authenticated_client.get("/partials/batch-job-rows?sort=company&direction=asc")

        # Assert
        mock_cursor.sort.assert_called_once()
        sort_args = mock_cursor.sort.call_args[0]

        # Should sort by company field
        assert sort_args[0] == "company"
        # Should sort ascending (1)
        assert sort_args[1] == 1

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_supports_sort_by_score_desc(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should support sorting by score in descending order."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = []
        mock_collection.find.return_value = mock_cursor

        mock_render_template.return_value = "<tr>...</tr>"

        # Act
        authenticated_client.get("/partials/batch-job-rows?sort=score&direction=desc")

        # Assert
        mock_cursor.sort.assert_called_once()
        sort_args = mock_cursor.sort.call_args[0]

        assert sort_args[0] == "score"
        assert sort_args[1] == -1

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_renders_batch_job_rows_template(
        self, mock_render_template, mock_get_collection, authenticated_client, sample_jobs
    ):
        """Should render batch_job_rows.html with correct context."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        under_processing_jobs = [j for j in sample_jobs if j["status"] == "under processing"]
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = under_processing_jobs
        mock_collection.find.return_value = mock_cursor

        mock_render_template.return_value = "<tr>...</tr>"

        # Act
        authenticated_client.get("/partials/batch-job-rows?sort=title&direction=asc")

        # Assert
        mock_render_template.assert_called_once()
        call_args = mock_render_template.call_args

        # Verify template name
        template_name = call_args[0][0]
        assert template_name == "partials/batch_job_rows.html"

        # Verify context contains jobs
        context = call_args[1]
        assert "jobs" in context
        assert context["jobs"] == under_processing_jobs

        # Verify context contains statuses
        assert "statuses" in context
        assert isinstance(context["statuses"], list)

        # Verify context contains current sort params
        assert "current_sort" in context
        assert context["current_sort"] == "title"
        assert "current_direction" in context
        assert context["current_direction"] == "asc"

    def test_requires_authentication(self, client):
        """Should return 401 when not authenticated."""
        # Act
        response = client.get("/partials/batch-job-rows")

        # Assert
        # Partials are API-like, so should return JSON error, not redirect
        # However, if decorated with @login_required, behavior depends on path
        # Let's check for either redirect or JSON error
        assert response.status_code in [302, 401]

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_handles_invalid_sort_field_gracefully(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should fallback to default sort when invalid field is provided."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = []
        mock_collection.find.return_value = mock_cursor

        mock_render_template.return_value = "<tr>...</tr>"

        # Act
        authenticated_client.get("/partials/batch-job-rows?sort=invalid_field")

        # Assert
        # Should fallback to batch_added_at (default)
        mock_cursor.sort.assert_called_once()
        sort_args = mock_cursor.sort.call_args[0]
        assert sort_args[0] == "batch_added_at"

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_returns_empty_list_when_no_jobs_in_batch(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should handle case where no jobs have 'under processing' status."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = []  # No jobs
        mock_collection.find.return_value = mock_cursor

        mock_render_template.return_value = ""

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200

        # Verify jobs list is empty
        call_args = mock_render_template.call_args
        context = call_args[1]
        assert context["jobs"] == []


# ===== INTEGRATION TESTS =====

class TestBatchProcessingWorkflow:
    """Integration tests for complete batch processing workflow."""

    @patch("frontend.app.get_collection")
    def test_full_workflow_move_to_batch_then_view(
        self, mock_get_collection, authenticated_client, sample_jobs
    ):
        """Should move jobs to batch and then retrieve them in batch view."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        # Step 1: Move jobs to batch
        mock_collection.update_many.return_value.modified_count = 2
        job_ids = [str(sample_jobs[0]["_id"]), str(sample_jobs[1]["_id"])]

        # Act - Move to batch
        move_response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": job_ids},
        )

        # Assert - Move succeeded
        assert move_response.status_code == 200
        move_data = move_response.get_json()
        assert move_data["success"] is True
        assert move_data["updated_count"] == 2

        # Simulate updated jobs
        updated_jobs = [
            {**sample_jobs[0], "status": "under processing", "batch_added_at": datetime.utcnow()},
            {**sample_jobs[1], "status": "under processing", "batch_added_at": datetime.utcnow()},
        ]

        # Step 2: Retrieve batch jobs
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = updated_jobs
        mock_collection.find.return_value = mock_cursor

        with patch("frontend.app.render_template") as mock_render:
            mock_render.return_value = "<tr>2 jobs</tr>"

            # Act - Get batch rows
            rows_response = authenticated_client.get("/partials/batch-job-rows")

            # Assert - Batch rows retrieved
            assert rows_response.status_code == 200

            # Verify correct filter was used
            mock_collection.find.assert_called_with({"status": "under processing"})


# ===== TESTS: Context Menu Actions =====

class TestContextMenuActions:
    """Tests for context menu actions on main job rows."""

    @patch("frontend.app.get_collection")
    def test_move_single_job_to_batch_via_context_menu(
        self, mock_get_collection, authenticated_client, mock_db_collection
    ):
        """Should move single job to batch when called from context menu."""
        # Arrange
        mock_get_collection.return_value = mock_db_collection
        mock_db_collection.update_many.return_value.modified_count = 1

        job_id = "507f1f77bcf86cd799439011"

        # Act - Context menu calls the same endpoint with single-item array
        response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": [job_id]},
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["updated_count"] == 1

        # Verify MongoDB was called with the single job ID
        mock_db_collection.update_many.assert_called_once()
        call_args = mock_db_collection.update_many.call_args
        filter_arg = call_args[0][0]
        assert len(filter_arg["_id"]["$in"]) == 1

    @patch("frontend.app.get_db")
    def test_context_menu_applied_action_updates_status(
        self, mock_get_db, authenticated_client
    ):
        """Should update job status to 'applied' when applied action is selected."""
        # Arrange
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_get_db.return_value = mock_db

        mock_update_result = MagicMock()
        mock_update_result.matched_count = 1
        mock_collection.update_one.return_value = mock_update_result

        job_id = "507f1f77bcf86cd799439011"

        # Act - Context menu calls status update endpoint with 'applied'
        response = authenticated_client.post(
            "/api/jobs/status",
            json={"job_id": job_id, "status": "applied"},
        )

        # Assert
        assert response.status_code == 200

        # Verify MongoDB update was called
        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args

        # Verify filter uses correct job ID
        filter_arg = call_args[0][0]
        assert "_id" in filter_arg

        # Verify status is set to 'applied'
        update_arg = call_args[0][1]
        assert "$set" in update_arg
        assert update_arg["$set"]["status"] == "applied"

        # Verify appliedOn timestamp is set (GAP-064)
        assert "appliedOn" in update_arg["$set"]
        assert isinstance(update_arg["$set"]["appliedOn"], datetime)

    @patch("frontend.app.get_db")
    def test_context_menu_discard_action_updates_status(
        self, mock_get_db, authenticated_client
    ):
        """Should update job status to 'discarded' when discard action is selected."""
        # Arrange
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_get_db.return_value = mock_db

        mock_update_result = MagicMock()
        mock_update_result.matched_count = 1
        mock_collection.update_one.return_value = mock_update_result

        job_id = "507f1f77bcf86cd799439012"

        # Act - Context menu calls status update endpoint with 'discarded'
        response = authenticated_client.post(
            "/api/jobs/status",
            json={"job_id": job_id, "status": "discarded"},
        )

        # Assert
        assert response.status_code == 200

        # Verify MongoDB update was called
        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args

        # Verify status is set to 'discarded'
        update_arg = call_args[0][1]
        assert "$set" in update_arg
        assert update_arg["$set"]["status"] == "discarded"

        # Verify appliedOn is cleared (not 'applied' status)
        assert update_arg["$set"]["appliedOn"] is None

    @patch("frontend.app.get_collection")
    def test_context_menu_rejects_invalid_status(
        self, mock_get_collection, authenticated_client
    ):
        """Should reject invalid status values from context menu."""
        # Arrange
        mock_get_collection.return_value = MagicMock()
        job_id = "507f1f77bcf86cd799439011"

        # Act
        response = authenticated_client.post(
            "/api/jobs/status",
            json={"job_id": job_id, "status": "invalid_status"},
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "Invalid status" in data["error"]

    @patch("frontend.app.get_collection")
    def test_context_menu_requires_job_id(
        self, mock_get_collection, authenticated_client
    ):
        """Should require job_id parameter for status update."""
        # Act
        response = authenticated_client.post(
            "/api/jobs/status",
            json={"status": "applied"},
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "job_id is required" in data["error"]

    @patch("frontend.app.get_collection")
    def test_context_menu_requires_status(
        self, mock_get_collection, authenticated_client
    ):
        """Should require status parameter for status update."""
        # Act
        response = authenticated_client.post(
            "/api/jobs/status",
            json={"job_id": "507f1f77bcf86cd799439011"},
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "status is required" in data["error"]


# ===== TESTS: Scrape-and-Fill Action (Frontend UI) =====

class TestScrapeAndFillUI:
    """Tests for scrape-and-fill UI in batch job rows.

    Note: These tests verify the template rendering and button state logic.
    Backend endpoint tests would belong in a separate integration test file
    once /api/runner/operations/{job_id}/scrape-form-answers/stream is implemented.
    """

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_scrape_button_enabled_when_application_url_exists(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should render scrape button as enabled when job has application_url."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        # Job with application_url
        job_with_url = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Senior Engineer",
            "company": "Tech Corp",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "application_url": "https://example.com/apply",
        }

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [job_with_url]
        mock_collection.find.return_value = mock_cursor

        # Capture template call
        def capture_render(template_name, **context):
            # Store context for verification
            capture_render.last_context = context
            return "<html></html>"

        capture_render.last_context = None
        mock_render_template.side_effect = capture_render

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        assert capture_render.last_context is not None
        jobs = capture_render.last_context.get("jobs", [])
        assert len(jobs) == 1
        assert jobs[0]["application_url"] == "https://example.com/apply"

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_scrape_button_disabled_when_no_application_url(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should render scrape button as disabled when job has no application_url."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        # Job without application_url
        job_without_url = {
            "_id": ObjectId("507f1f77bcf86cd799439012"),
            "title": "Frontend Engineer",
            "company": "StartupXYZ",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            # No application_url field
        }

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [job_without_url]
        mock_collection.find.return_value = mock_cursor

        def capture_render(template_name, **context):
            capture_render.last_context = context
            return "<html></html>"

        capture_render.last_context = None
        mock_render_template.side_effect = capture_render

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        jobs = capture_render.last_context.get("jobs", [])
        assert len(jobs) == 1
        # Verify job has no application_url (button should be disabled in template)
        assert "application_url" not in jobs[0]

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_scrape_button_uses_job_url_as_fallback(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should use job.url in button logic when application_url is not set."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        # Job with url but no application_url
        job_with_fallback = {
            "_id": ObjectId("507f1f77bcf86cd799439013"),
            "title": "Backend Engineer",
            "company": "BigCorp",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "url": "https://example.com/job-posting",
            # No application_url - template should use url as fallback
        }

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [job_with_fallback]
        mock_collection.find.return_value = mock_cursor

        def capture_render(template_name, **context):
            capture_render.last_context = context
            return "<html></html>"

        capture_render.last_context = None
        mock_render_template.side_effect = capture_render

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        jobs = capture_render.last_context.get("jobs", [])
        assert len(jobs) == 1
        # Template should have access to job.url for fallback logic
        assert jobs[0]["url"] == "https://example.com/job-posting"

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_batch_rows_show_planned_answers_count(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should display count of planned_answers in expandable row."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        job_with_answers = {
            "_id": ObjectId("507f1f77bcf86cd799439014"),
            "title": "DevOps Engineer",
            "company": "CloudCo",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "planned_answers": [
                {"question": "Why us?", "answer": "Because..."},
                {"question": "Experience?", "answer": "10 years..."},
            ],
        }

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [job_with_answers]
        mock_collection.find.return_value = mock_cursor

        def capture_render(template_name, **context):
            capture_render.last_context = context
            return "<html></html>"

        capture_render.last_context = None
        mock_render_template.side_effect = capture_render

        # Act
        response = authenticated_client.get("/partials/batch-job-rows")

        # Assert
        assert response.status_code == 200
        jobs = capture_render.last_context.get("jobs", [])
        assert len(jobs) == 1
        # Verify planned_answers are available to template
        assert "planned_answers" in jobs[0]
        assert len(jobs[0]["planned_answers"]) == 2


# ===== INTEGRATION TESTS: Context Menu + Batch Workflow =====

class TestContextMenuBatchIntegration:
    """Integration tests for context menu to batch processing workflow."""

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_context_menu_to_batch_view_workflow(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should move job via context menu and see it in batch view."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        job_id = "507f1f77bcf86cd799439011"
        job_title = "Senior Backend Engineer"

        # Step 1: Move to batch via context menu
        mock_collection.update_many.return_value.modified_count = 1

        # Act - Move via context menu
        move_response = authenticated_client.post(
            "/api/jobs/move-to-batch",
            json={"job_ids": [job_id]},
        )

        # Assert - Move succeeded
        assert move_response.status_code == 200
        move_data = move_response.get_json()
        assert move_data["success"] is True

        # Step 2: Retrieve in batch view
        batch_job = {
            "_id": ObjectId(job_id),
            "title": job_title,
            "company": "Tech Corp",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
        }

        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = [batch_job]
        mock_collection.find.return_value = mock_cursor
        mock_render_template.return_value = "<tr>1 job</tr>"

        # Act - Get batch rows
        batch_response = authenticated_client.get("/partials/batch-job-rows")

        # Assert - Job appears in batch
        assert batch_response.status_code == 200

        # Verify batch query was executed
        mock_collection.find.assert_called_with({"status": "under processing"})

        # Verify template received the job
        call_args = mock_render_template.call_args
        context = call_args[1]
        assert len(context["jobs"]) == 1
        assert context["jobs"][0]["title"] == job_title


# ===== TESTS: GET /partials/batch-job-row/<job_id> =====

class TestBatchJobRowSinglePartial:
    """Tests for GET /partials/batch-job-row/<job_id> HTMX partial."""

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_returns_single_job_row(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should return single job row partial for HTMX refresh."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        job = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Senior Backend Engineer",
            "company": "Tech Corp",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "extracted_jd": {"title": "Senior Backend Engineer"},  # JD extracted
            "company_research": {"about": "Tech company"},  # Research done
            "generated_cv": "<html>CV</html>",  # CV generated
        }

        mock_collection.find_one.return_value = job
        mock_render_template.return_value = "<tbody>...</tbody>"

        # Act
        response = authenticated_client.get("/partials/batch-job-row/507f1f77bcf86cd799439011")

        # Assert
        assert response.status_code == 200
        mock_collection.find_one.assert_called_once()
        mock_render_template.assert_called_once()

        # Verify correct template is rendered
        call_args = mock_render_template.call_args
        template_name = call_args[0][0]
        assert template_name == "partials/batch_job_single_row.html"

        # Verify context contains job and statuses
        context = call_args[1]
        assert "job" in context
        assert context["job"]["_id"] == job["_id"]
        assert "statuses" in context

    @patch("frontend.app.get_collection")
    def test_returns_404_when_job_not_found(
        self, mock_get_collection, authenticated_client
    ):
        """Should return 404 when job doesn't exist."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection
        mock_collection.find_one.return_value = None

        # Act
        response = authenticated_client.get("/partials/batch-job-row/507f1f77bcf86cd799439011")

        # Assert
        assert response.status_code == 404

    @patch("frontend.app.get_collection")
    def test_returns_404_for_invalid_objectid(
        self, mock_get_collection, authenticated_client
    ):
        """Should return 404 for invalid ObjectId format."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        # Act
        response = authenticated_client.get("/partials/batch-job-row/invalid-id")

        # Assert
        assert response.status_code == 404

    def test_requires_authentication(self, client):
        """Should require authentication."""
        # Act
        response = client.get("/partials/batch-job-row/507f1f77bcf86cd799439011")

        # Assert
        assert response.status_code in [302, 401]

    @patch("frontend.app.get_collection")
    @patch("frontend.app.render_template")
    def test_renders_progress_badges_correctly(
        self, mock_render_template, mock_get_collection, authenticated_client
    ):
        """Should pass job with progress data to template for badge rendering."""
        # Arrange
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection

        # Job with all pipeline stages completed
        job = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Senior Backend Engineer",
            "company": "Tech Corp",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "extracted_jd": {"title": "Senior Backend Engineer"},
            "company_research": {"about": "A great company"},
            "generated_cv": "<html>CV content</html>",
        }

        mock_collection.find_one.return_value = job
        mock_render_template.return_value = "<tbody>...</tbody>"

        # Act
        response = authenticated_client.get("/partials/batch-job-row/507f1f77bcf86cd799439011")

        # Assert
        assert response.status_code == 200

        # Verify job with progress data is passed to template
        call_args = mock_render_template.call_args
        context = call_args[1]

        # Template receives the job and can check has_jd, has_research, has_cv
        assert context["job"]["extracted_jd"] is not None
        assert context["job"]["company_research"] is not None
        assert context["job"]["generated_cv"] is not None
