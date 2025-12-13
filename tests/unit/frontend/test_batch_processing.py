"""
Unit tests for frontend batch processing workflow.

Tests the batch processing routes in frontend/app.py:
- POST /api/jobs/move-to-batch: Move jobs to batch queue
- GET /batch-processing: Batch processing page view
- GET /partials/batch-job-rows: HTMX partial for batch job table

Coverage:
- Status updates to "under processing"
- batch_added_at timestamp setting
- Batch job filtering and sorting
- Error handling for invalid inputs
"""

import pytest
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

    @patch("frontend.app.get_collection")
    def test_moves_jobs_to_batch_successfully(
        self, mock_get_collection, authenticated_client, mock_db_collection
    ):
        """Should update status to 'under processing' and set batch_added_at."""
        # Arrange
        mock_get_collection.return_value = mock_db_collection
        mock_db_collection.update_many.return_value.modified_count = 2

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

    @patch("frontend.app.get_collection")
    def test_handles_zero_updates_gracefully(
        self, mock_get_collection, authenticated_client, mock_db_collection
    ):
        """Should handle case where no jobs are actually updated (e.g., already in batch)."""
        # Arrange
        mock_get_collection.return_value = mock_db_collection
        mock_db_collection.update_many.return_value.modified_count = 0

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

    @patch("frontend.app.get_collection")
    def test_batch_added_at_is_recent_timestamp(
        self, mock_get_collection, authenticated_client, mock_db_collection
    ):
        """Should set batch_added_at to current UTC time."""
        # Arrange
        mock_get_collection.return_value = mock_db_collection
        mock_db_collection.update_many.return_value.modified_count = 1

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
