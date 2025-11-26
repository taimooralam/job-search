"""
Tests for CV editing API endpoints (Module 2: Fix CV HTML Editing).

Tests the following routes:
- GET /api/jobs/<job_id>/cv - Get HTML CV
- PUT /api/jobs/<job_id>/cv - Update CV HTML content
- POST /api/jobs/<job_id>/cv/pdf - Generate PDF from HTML
- GET /api/jobs/<job_id>/cv/download - Download CV PDF

Note: These are basic smoke tests. Full integration tests with file I/O
should be run separately in integration test suites.
"""

import pytest
from bson import ObjectId
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Import the Flask app
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from frontend.app import app


@pytest.fixture
def client():
    """Create an authenticated test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        # Set up authenticated session
        with client.session_transaction() as sess:
            sess['authenticated'] = True
        yield client


@pytest.fixture
def mock_db():
    """Mock the MongoDB database."""
    with patch('frontend.app.get_db') as mock_get_db:
        mock_database = MagicMock()
        mock_collection = MagicMock()
        mock_database.__getitem__ = MagicMock(return_value=mock_collection)
        mock_get_db.return_value = mock_database
        yield mock_database


class TestGetJobCV:
    """Test GET /api/jobs/<job_id>/cv endpoint."""

    def test_get_cv_invalid_job_id(self, client, mock_db):
        """Get CV with invalid job ID returns 400."""
        response = client.get("/api/jobs/invalid-id/cv")

        assert response.status_code == 400
        assert b"Invalid job ID" in response.data

    def test_get_cv_job_not_found(self, client, mock_db):
        """Get CV for non-existent job returns 404."""
        mock_db["level-2"].find_one.return_value = None

        job_id = ObjectId()
        response = client.get(f"/api/jobs/{job_id}/cv")

        assert response.status_code == 404
        assert b"Job not found" in response.data

    def test_get_cv_missing_company_or_title(self, client, mock_db):
        """Get CV for job missing company/title returns 400."""
        job_id = ObjectId()
        mock_db["level-2"].find_one.return_value = {
            "_id": job_id,
            "company": "TechCorp"
            # Missing title
        }

        response = client.get(f"/api/jobs/{job_id}/cv")

        assert response.status_code == 400
        assert b"missing company or title" in response.data


class TestUpdateJobCV:
    """Test PUT /api/jobs/<job_id>/cv endpoint."""

    def test_update_cv_invalid_job_id(self, client, mock_db):
        """Update CV with invalid job ID returns 400."""
        response = client.put(
            "/api/jobs/invalid-id/cv",
            json={"html_content": "<html></html>"}
        )

        assert response.status_code == 400
        assert b"Invalid job ID" in response.data

    def test_update_cv_job_not_found(self, client, mock_db):
        """Update CV for non-existent job returns 404."""
        mock_db["level-2"].find_one.return_value = None

        job_id = ObjectId()
        response = client.put(
            f"/api/jobs/{job_id}/cv",
            json={"html_content": "<html></html>"}
        )

        assert response.status_code == 404
        assert b"Job not found" in response.data

    def test_update_cv_missing_content(self, client, mock_db):
        """Update CV without html_content returns 400."""
        job_id = ObjectId()
        mock_db["level-2"].find_one.return_value = {
            "_id": job_id,
            "company": "TechCorp",
            "title": "Senior Engineer"
        }

        response = client.put(f"/api/jobs/{job_id}/cv", json={})

        assert response.status_code == 400
        assert b"Missing html_content" in response.data


class TestGenerateCVPDF:
    """Test POST /api/jobs/<job_id>/cv/pdf endpoint."""

    def test_generate_pdf_invalid_job_id(self, client, mock_db):
        """Generate PDF with invalid job ID returns 400."""
        response = client.post("/api/jobs/invalid-id/cv/pdf")

        assert response.status_code == 400
        assert b"Invalid job ID" in response.data

    def test_generate_pdf_job_not_found(self, client, mock_db):
        """Generate PDF for non-existent job returns 404."""
        mock_db["level-2"].find_one.return_value = None

        job_id = ObjectId()
        response = client.post(f"/api/jobs/{job_id}/cv/pdf")

        assert response.status_code == 404
        assert b"Job not found" in response.data


class TestDownloadCVPDF:
    """Test GET /api/jobs/<job_id>/cv/download endpoint."""

    def test_download_pdf_invalid_job_id(self, client, mock_db):
        """Download PDF with invalid job ID returns 400."""
        response = client.get("/api/jobs/invalid-id/cv/download")

        assert response.status_code == 400
        assert b"Invalid job ID" in response.data

    def test_download_pdf_job_not_found(self, client, mock_db):
        """Download PDF for non-existent job returns 404."""
        mock_db["level-2"].find_one.return_value = None

        job_id = ObjectId()
        response = client.get(f"/api/jobs/{job_id}/cv/download")

        assert response.status_code == 404
        assert b"Job not found" in response.data
