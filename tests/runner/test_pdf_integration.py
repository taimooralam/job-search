"""
Integration tests for runner service → PDF service communication.

Tests that the runner service correctly proxies PDF requests to the PDF service.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import httpx


@pytest.fixture
def runner_client():
    """Create test client for runner service."""
    import os
    from runner_service.app import app
    from runner_service.auth import verify_token
    from fastapi.security import HTTPAuthorizationCredentials

    # Mock authentication for all tests
    async def mock_verify_token():
        # Return a dummy credential object
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-token")

    app.dependency_overrides[verify_token] = mock_verify_token
    client = TestClient(app)
    yield client
    # Clean up overrides after tests
    app.dependency_overrides.clear()


@pytest.fixture
def mock_mongodb():
    """Mock MongoDB connection for tests.

    IMPORTANT: Must patch MongoClient where it's USED (atlas_repository),
    not where it's DEFINED (pymongo). Python's `from X import Y` copies
    the name into the module's namespace, so patching the original has
    no effect on the copy.

    Also must reset the repository singleton before mocking, otherwise
    the class-level cached _collection will be used instead of creating
    a new (mocked) MongoClient.
    """
    from src.common.repositories import reset_repository
    from src.common.repositories.atlas_repository import AtlasJobRepository

    # Clear class-level singletons
    AtlasJobRepository._client = None
    AtlasJobRepository._db = None
    AtlasJobRepository._collection = None
    reset_repository()

    # Patch where MongoClient is USED, not where it's defined
    with patch("src.common.repositories.atlas_repository.MongoClient") as mock_client:
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.return_value.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        yield mock_collection

    # Clean up after test
    AtlasJobRepository._client = None
    AtlasJobRepository._db = None
    AtlasJobRepository._collection = None
    reset_repository()


class TestRunnerPDFProxyIntegration:
    """Tests for runner service PDF proxy to PDF service."""

    @patch("httpx.AsyncClient")
    def test_runner_calls_pdf_service_successfully(
        self, mock_httpx, runner_client, mock_mongodb
    ):
        """Test that runner successfully proxies to PDF service."""
        # Setup MongoDB mock
        mock_mongodb.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "company": "TechCorp",
            "title": "Senior Engineer",
            "cv_editor_state": {
                "content": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Test CV"}]
                        }
                    ]
                },
                "documentStyles": {
                    "fontFamily": "Inter",
                    "fontSize": 11,
                    "lineHeight": 1.15,
                    "margins": {"top": 1.0, "right": 1.0, "bottom": 1.0, "left": 1.0},
                    "pageSize": "letter"
                }
            }
        }

        # Setup httpx mock for PDF service call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4 fake pdf content"
        mock_response.headers = {
            "Content-Disposition": 'attachment; filename="CV_TechCorp_Senior_Engineer.pdf"'
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        mock_httpx.return_value = mock_http_client

        # Make request to runner
        response = runner_client.post(
            "/api/jobs/507f1f77bcf86cd799439011/cv-editor/pdf"
        )

        # Verify response
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "CV_TechCorp_Senior_Engineer.pdf" in response.headers.get("content-disposition", "")

    @patch("httpx.AsyncClient")
    def test_runner_handles_pdf_service_timeout(
        self, mock_httpx, runner_client, mock_mongodb
    ):
        """Test that runner handles PDF service timeouts gracefully."""
        # Setup MongoDB mock
        mock_mongodb.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "company": "TechCorp",
            "title": "Engineer",
            "cv_editor_state": {
                "content": {"type": "doc", "content": []},
                "documentStyles": {}
            }
        }

        # Setup httpx mock to raise timeout
        mock_http_client = AsyncMock()
        mock_http_client.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.TimeoutException("Request timed out")
        )
        mock_httpx.return_value = mock_http_client

        # Make request to runner
        response = runner_client.post(
            "/api/jobs/507f1f77bcf86cd799439011/cv-editor/pdf"
        )

        # Verify error response
        assert response.status_code == 504
        assert "timed out" in response.json()["detail"].lower()

    @patch("httpx.AsyncClient")
    def test_runner_handles_pdf_service_unavailable(
        self, mock_httpx, runner_client, mock_mongodb
    ):
        """Test that runner handles PDF service being unavailable."""
        # Setup MongoDB mock
        mock_mongodb.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "company": "TechCorp",
            "title": "Engineer",
            "cv_editor_state": {
                "content": {"type": "doc", "content": []},
                "documentStyles": {}
            }
        }

        # Setup httpx mock to raise connection error
        mock_http_client = AsyncMock()
        mock_http_client.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.RequestError("Connection refused")
        )
        mock_httpx.return_value = mock_http_client

        # Make request to runner
        response = runner_client.post(
            "/api/jobs/507f1f77bcf86cd799439011/cv-editor/pdf"
        )

        # Verify error response
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("httpx.AsyncClient")
    def test_runner_handles_pdf_service_400_error(
        self, mock_httpx, runner_client, mock_mongodb
    ):
        """Test that runner properly forwards PDF service errors."""
        # Setup MongoDB mock
        mock_mongodb.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "company": "TechCorp",
            "title": "Engineer",
            "cv_editor_state": {
                "content": {"type": "doc", "content": []},
                "documentStyles": {}
            }
        }

        # Setup httpx mock to return 400 error
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Invalid TipTap document format"}

        mock_http_client = AsyncMock()
        mock_http_client.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Bad request",
                request=MagicMock(),
                response=mock_response
            )
        )
        mock_httpx.return_value = mock_http_client

        # Make request to runner
        response = runner_client.post(
            "/api/jobs/507f1f77bcf86cd799439011/cv-editor/pdf"
        )

        # Verify error response
        assert response.status_code == 400
        assert "Invalid TipTap document format" in response.json()["detail"]

    @patch("httpx.AsyncClient")
    def test_runner_sends_correct_payload_to_pdf_service(
        self, mock_httpx, runner_client, mock_mongodb
    ):
        """Test that runner sends correct payload structure to PDF service."""
        # Setup MongoDB mock with specific data
        mock_mongodb.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "company": "TechCorp",
            "title": "Senior Engineer",
            "cv_editor_state": {
                "content": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "heading",
                            "attrs": {"level": 1},
                            "content": [{"type": "text", "text": "John Doe"}]
                        }
                    ]
                },
                "documentStyles": {
                    "fontFamily": "Merriweather",
                    "fontSize": 12,
                    "lineHeight": 1.5,
                    "margins": {"top": 0.75, "right": 0.75, "bottom": 0.75, "left": 0.75},
                    "pageSize": "a4"
                },
                "header": "John Doe - CV",
                "footer": "Page 1"
            }
        }

        # Setup httpx mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF"
        mock_response.headers = {"Content-Disposition": 'attachment; filename="CV.pdf"'}
        mock_response.raise_for_status = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        mock_http_client = AsyncMock()
        mock_http_client.__aenter__.return_value.post = mock_post
        mock_httpx.return_value = mock_http_client

        # Make request to runner
        response = runner_client.post(
            "/api/jobs/507f1f77bcf86cd799439011/cv-editor/pdf"
        )

        # Verify the call to PDF service
        assert mock_post.called
        call_args = mock_post.call_args

        # Check URL
        assert "/cv-to-pdf" in call_args[0][0]

        # Check payload structure
        payload = call_args[1]["json"]
        assert "tiptap_json" in payload
        assert payload["tiptap_json"]["type"] == "doc"
        assert "documentStyles" in payload
        assert payload["documentStyles"]["fontFamily"] == "Merriweather"
        assert payload["documentStyles"]["fontSize"] == 12
        assert payload["header"] == "John Doe - CV"
        assert payload["footer"] == "Page 1"
        assert payload["company"] == "TechCorp"
        assert payload["role"] == "Senior Engineer"

    def test_runner_handles_missing_job(self, runner_client, mock_mongodb):
        """Test that runner handles missing job gracefully."""
        # Setup MongoDB mock to return None (job not found)
        mock_mongodb.find_one.return_value = None

        # Make request to runner
        response = runner_client.post(
            "/api/jobs/507f1f77bcf86cd799439011/cv-editor/pdf"
        )

        # Verify error response
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_runner_handles_invalid_job_id(self, runner_client):
        """Test that runner validates job ID format."""
        # Make request with invalid job ID
        response = runner_client.post(
            "/api/jobs/invalid-id/cv-editor/pdf"
        )

        # Verify error response
        assert response.status_code == 400
        assert "Invalid job ID format" in response.json()["detail"]

    @patch("httpx.AsyncClient")
    def test_runner_uses_default_cv_state_when_missing(
        self, mock_httpx, runner_client, mock_mongodb
    ):
        """Test that runner provides default CV state when not in MongoDB."""
        # Setup MongoDB mock with job but no cv_editor_state
        mock_mongodb.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "company": "TechCorp",
            "title": "Engineer"
            # No cv_editor_state field
        }

        # Setup httpx mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF"
        mock_response.headers = {"Content-Disposition": 'attachment; filename="CV.pdf"'}
        mock_response.raise_for_status = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        mock_http_client = AsyncMock()
        mock_http_client.__aenter__.return_value.post = mock_post
        mock_httpx.return_value = mock_http_client

        # Make request to runner
        response = runner_client.post(
            "/api/jobs/507f1f77bcf86cd799439011/cv-editor/pdf"
        )

        # Verify successful response
        assert response.status_code == 200

        # Verify default state was used
        payload = mock_post.call_args[1]["json"]
        assert payload["tiptap_json"]["type"] == "doc"
        assert payload["documentStyles"]["fontFamily"] == "Inter"
        assert payload["documentStyles"]["fontSize"] == 11

    @patch("httpx.AsyncClient")
    def test_runner_migrates_cv_text_when_cv_editor_state_missing(
        self, mock_httpx, runner_client, mock_mongodb
    ):
        """Test that runner migrates cv_text (markdown) when cv_editor_state is missing.

        This allows users to export PDF directly from detail page without opening the editor first.
        The pipeline generates cv_text (markdown) but not cv_editor_state initially.
        """
        # Setup MongoDB mock with job that has cv_text but no cv_editor_state
        mock_mongodb.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "company": "TechCorp",
            "title": "Engineer",
            "cv_text": """# John Doe

## Experience

### Senior Engineer at TechCorp
- Built scalable systems
- Led team of 5 engineers

## Education

### BS Computer Science
Stanford University
"""
            # No cv_editor_state field
        }

        # Setup httpx mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF"
        mock_response.headers = {"Content-Disposition": 'attachment; filename="CV.pdf"'}
        mock_response.raise_for_status = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        mock_http_client = AsyncMock()
        mock_http_client.__aenter__.return_value.post = mock_post
        mock_httpx.return_value = mock_http_client

        # Make request to runner
        response = runner_client.post(
            "/api/jobs/507f1f77bcf86cd799439011/cv-editor/pdf"
        )

        # Verify successful response
        assert response.status_code == 200

        # Verify migrated state was used (not empty default)
        payload = mock_post.call_args[1]["json"]
        assert payload["tiptap_json"]["type"] == "doc"
        assert len(payload["tiptap_json"]["content"]) > 0  # Should have content from migration

        # Verify heading was migrated
        first_node = payload["tiptap_json"]["content"][0]
        assert first_node["type"] == "heading"
        assert first_node["attrs"]["level"] == 1
        assert first_node["content"][0]["text"] == "John Doe"
