"""
Integration tests for CV Rich Text Editor - Phase 4: PDF Export via PDF Service

Tests cover:
- PDF generation endpoint (POST /api/jobs/<job_id>/cv-editor/pdf)
- PDF service integration
- Request payload formatting
- Error handling (job not found, service errors)
- Filename extraction
- Authentication handling

Phase 4 uses an external PDF service for rendering.
"""

import pytest
import json
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock, patch, Mock
from io import BytesIO


# ==============================================================================
# Test Class: PDF Generation Endpoint
# ==============================================================================

class TestPDFGenerationEndpoint:
    """Tests for POST /api/jobs/<job_id>/cv-editor/pdf endpoint."""

    @patch('app.requests.post')
    def test_pdf_endpoint_exists(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """POST /api/jobs/<job_id>/cv-editor/pdf endpoint should exist."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.return_value = Mock(
            status_code=200,
            content=b'%PDF-1.4 test pdf content',
            headers={'Content-Disposition': 'attachment; filename="CV.pdf"'}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code != 404  # Endpoint exists

    def test_pdf_generation_requires_authentication(self, client, mock_db, sample_job_with_editor_state):
        """PDF generation should require authentication."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])

        # Act
        response = client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert - API endpoints return 401 or 302 for unauthenticated requests
        assert response.status_code in [401, 302]

    def test_pdf_generation_validates_job_exists(self, authenticated_client, mock_db):
        """PDF generation should return 404 if job not found."""
        # Arrange
        job_id = str(ObjectId())
        mock_db.find_one.return_value = None  # Job not found

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data
        assert "not found" in data["error"].lower()

    def test_pdf_generation_validates_invalid_job_id(self, authenticated_client, mock_db):
        """PDF generation should return error for invalid job ID format."""
        # Arrange
        invalid_job_id = "invalid-id-format"

        # Act
        response = authenticated_client.post(f"/api/jobs/{invalid_job_id}/cv-editor/pdf")

        # Assert - invalid ObjectId causes 500 (exception caught), 400, or 404
        assert response.status_code in [400, 404, 500]

    @patch('app.requests.post')
    def test_pdf_generation_sends_tiptap_json(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF generation should send TipTap JSON to PDF service."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.return_value = Mock(
            status_code=200,
            content=b'%PDF-1.4 test pdf content',
            headers={'Content-Disposition': 'attachment; filename="CV.pdf"'}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 200
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        request_json = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        assert "tiptap_json" in request_json
        assert request_json["tiptap_json"]["type"] == "doc"


# ==============================================================================
# Test Class: PDF Service Integration
# ==============================================================================

class TestPDFServiceIntegration:
    """Tests for PDF service integration."""

    @patch('app.requests.post')
    def test_pdf_service_receives_document_styles(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF service should receive documentStyles in request."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.return_value = Mock(
            status_code=200,
            content=b'%PDF-1.4 test pdf content',
            headers={'Content-Disposition': 'attachment; filename="CV.pdf"'}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 200
        call_kwargs = mock_post.call_args
        request_json = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        assert "documentStyles" in request_json

    @patch('app.requests.post')
    def test_pdf_service_receives_company_and_role(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF service should receive company and role for filename."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["company"] = "TechCorp"
        sample_job_with_editor_state["title"] = "Senior Engineer"
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.return_value = Mock(
            status_code=200,
            content=b'%PDF-1.4 test pdf content',
            headers={'Content-Disposition': 'attachment; filename="CV_TechCorp_Senior_Engineer.pdf"'}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 200
        call_kwargs = mock_post.call_args
        request_json = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        assert request_json.get("company") == "TechCorp"
        assert request_json.get("role") == "Senior Engineer"

    @patch('app.requests.post')
    def test_pdf_service_authentication_header(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state, monkeypatch):
        """PDF service should receive authentication header when configured."""
        # Arrange
        monkeypatch.setenv("RUNNER_API_SECRET", "test-secret-token")
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.return_value = Mock(
            status_code=200,
            content=b'%PDF-1.4 test pdf content',
            headers={'Content-Disposition': 'attachment; filename="CV.pdf"'}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get('headers') or call_kwargs[1].get('headers')
        assert headers.get("Authorization") == "Bearer test-secret-token"


# ==============================================================================
# Test Class: PDF Download Response
# ==============================================================================

class TestPDFDownloadResponse:
    """Tests for PDF download response handling."""

    @patch('app.requests.post')
    def test_pdf_returns_binary_content(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF endpoint should return binary PDF content."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        pdf_content = b'%PDF-1.4 test pdf content binary'
        mock_post.return_value = Mock(
            status_code=200,
            content=pdf_content,
            headers={'Content-Disposition': 'attachment; filename="CV.pdf"'}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.data == pdf_content

    @patch('app.requests.post')
    def test_pdf_filename_from_service(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF endpoint should use filename from PDF service response."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.return_value = Mock(
            status_code=200,
            content=b'%PDF-1.4',
            headers={'Content-Disposition': 'attachment; filename="CV_TechCorp_Engineer.pdf"'}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 200
        content_disposition = response.headers.get('Content-Disposition', '')
        assert 'CV_TechCorp_Engineer.pdf' in content_disposition


# ==============================================================================
# Test Class: Error Handling
# ==============================================================================

class TestPDFErrorHandling:
    """Tests for PDF generation error handling."""

    @patch('app.requests.post')
    def test_pdf_service_error_returns_500(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF service error should return 500."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.return_value = Mock(
            status_code=500,
            json=lambda: {"detail": "PDF generation failed"},
            headers={}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 500

    @patch('app.requests.post')
    def test_pdf_service_auth_failure_returns_401(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF service auth failure should return 401."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.return_value = Mock(
            status_code=401,
            json=lambda: {"detail": "Authentication failed"},
            headers={}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 401

    def test_missing_editor_state_returns_400(self, authenticated_client, mock_db, sample_job):
        """Missing editor state should return 400."""
        # Arrange
        job_id = str(sample_job["_id"])
        sample_job["cv_editor_state"] = None
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_missing_tiptap_json_returns_400(self, authenticated_client, mock_db, sample_job_with_editor_state):
        """Missing tiptap_json in editor state should return 400."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["cv_editor_state"]["tiptap_json"] = None
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    @patch('app.requests.post')
    def test_pdf_service_timeout(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF service timeout should be handled gracefully."""
        # Arrange
        import requests
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.side_effect = requests.Timeout("Connection timed out")

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert - 504 Gateway Timeout or 500 Internal Server Error
        assert response.status_code in [500, 504]


# ==============================================================================
# Test Class: Document Styles
# ==============================================================================

class TestPDFDocumentStyles:
    """Tests for document style handling."""

    @patch('app.requests.post')
    def test_default_document_styles_sent(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """Default document styles should be sent if not specified."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        # Remove documentStyles to test defaults
        del sample_job_with_editor_state["cv_editor_state"]["documentStyles"]
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.return_value = Mock(
            status_code=200,
            content=b'%PDF-1.4',
            headers={'Content-Disposition': 'attachment; filename="CV.pdf"'}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 200
        call_kwargs = mock_post.call_args
        request_json = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        doc_styles = request_json.get("documentStyles", {})
        # Verify defaults are provided
        assert "fontFamily" in doc_styles
        assert "pageSize" in doc_styles

    @patch('app.requests.post')
    def test_custom_page_size_sent(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """Custom page size should be sent to PDF service."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["cv_editor_state"]["documentStyles"]["pageSize"] = "a4"
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.return_value = Mock(
            status_code=200,
            content=b'%PDF-1.4',
            headers={'Content-Disposition': 'attachment; filename="CV.pdf"'}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        call_kwargs = mock_post.call_args
        request_json = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        assert request_json["documentStyles"]["pageSize"] == "a4"

    @patch('app.requests.post')
    def test_custom_margins_sent(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """Custom margins should be sent to PDF service."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["cv_editor_state"]["documentStyles"]["margins"] = {
            "top": 0.5, "right": 0.75, "bottom": 0.5, "left": 0.75
        }
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_post.return_value = Mock(
            status_code=200,
            content=b'%PDF-1.4',
            headers={'Content-Disposition': 'attachment; filename="CV.pdf"'}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        call_kwargs = mock_post.call_args
        request_json = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        margins = request_json["documentStyles"]["margins"]
        assert margins["top"] == 0.5
        assert margins["right"] == 0.75


# ==============================================================================
# Test Class: End-to-End Workflow
# ==============================================================================

class TestPDFEndToEndWorkflow:
    """Tests for complete PDF generation workflow."""

    @patch('app.requests.post')
    def test_complete_pdf_workflow(self, mock_post, authenticated_client, mock_db, sample_job_with_editor_state):
        """Test complete PDF generation workflow."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["company"] = "Acme Corp"
        sample_job_with_editor_state["title"] = "Software Engineer"
        sample_job_with_editor_state["cv_editor_state"]["documentStyles"] = {
            "fontFamily": "Roboto",
            "fontSize": 11,
            "lineHeight": 1.15,
            "margins": {"top": 1.0, "right": 1.0, "bottom": 1.0, "left": 1.0},
            "pageSize": "letter"
        }
        mock_db.find_one.return_value = sample_job_with_editor_state

        pdf_content = b'%PDF-1.4 real pdf binary content here'
        mock_post.return_value = Mock(
            status_code=200,
            content=pdf_content,
            headers={'Content-Disposition': 'attachment; filename="CV_Acme_Corp_Software_Engineer.pdf"'}
        )

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.data == pdf_content

        # Verify request to PDF service
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        request_json = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        assert request_json["company"] == "Acme Corp"
        assert request_json["role"] == "Software Engineer"
        assert request_json["documentStyles"]["fontFamily"] == "Roboto"
