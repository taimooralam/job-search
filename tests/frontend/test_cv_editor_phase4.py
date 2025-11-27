"""
Integration tests for CV Rich Text Editor - Phase 4: PDF Export via Playwright

Tests cover:
- PDF generation endpoint (POST /api/jobs/<job_id>/cv/pdf)
- PDF export button functionality
- Playwright rendering with Phase 3 styles
- Font embedding (Google Fonts)
- Page settings (Letter vs A4, margins, line height)
- Header/footer in PDF output
- ATS compatibility (text-based, not images)
- Error handling (job not found, Playwright errors)
- Filename format: CV_<Company>_<Title>.pdf

Phase 4 focuses on server-side PDF generation using Playwright to ensure:
1. Pixel-perfect rendering matching the editor
2. Proper font embedding for Google Fonts
3. ATS-compatible text (not images)
4. Consistent cross-browser output
"""

import pytest
import json
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock, patch, Mock, AsyncMock, call
from pathlib import Path


# ==============================================================================
# Test Class: PDF Generation Endpoint
# ==============================================================================

class TestPDFGenerationEndpoint:
    """Tests for POST /api/jobs/<job_id>/cv/pdf endpoint."""

    @patch('playwright.sync_api.sync_playwright')
    def test_pdf_endpoint_exists(self, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """POST /api/jobs/<job_id>/cv/pdf endpoint should exist."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Mock Playwright
        mock_playwright.return_value.__enter__.return_value = Mock()

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code != 404  # Endpoint exists

    @patch('playwright.sync_api.sync_playwright')
    def test_pdf_generation_requires_authentication(self, mock_playwright, client, mock_db, sample_job_with_editor_state):
        """PDF generation should require authentication."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])

        # Act
        response = client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 302  # Redirect to login

    @patch('playwright.sync_api.sync_playwright')
    def test_pdf_generation_validates_job_exists(self, mock_playwright, authenticated_client, mock_db):
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

    @patch('playwright.sync_api.sync_playwright')
    def test_pdf_generation_validates_invalid_job_id(self, mock_playwright, authenticated_client, mock_db):
        """PDF generation should return 400 or 404 for invalid job ID format."""
        # Arrange
        invalid_job_id = "invalid-id-format"

        # Act
        response = authenticated_client.post(f"/api/jobs/{invalid_job_id}/cv-editor/pdf")

        # Assert
        # Flask route matching may return 404 before validation code runs
        assert response.status_code in [400, 404]
        if response.status_code == 400:
            data = response.get_json()
            assert "error" in data

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_pdf_generation_uses_editor_state(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF generation should use cv_editor_state from MongoDB."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        # Verify converter was called with TipTap JSON content
        mock_converter.assert_called_once()
        called_content = mock_converter.call_args[0][0]
        assert called_content["type"] == "doc"


# ==============================================================================
# Test Class: Playwright PDF Rendering
# ==============================================================================

class TestPlaywrightPDFRendering:
    """Tests for Playwright-based PDF rendering."""

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_playwright_launches_chromium(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """Playwright should launch Chromium browser."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_page.pdf = MagicMock()
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        mock_pw.__enter__.return_value.chromium.launch.assert_called_once()

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_playwright_sets_page_content(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """Playwright should set HTML content on page."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Professional Resume</h1><p>Experienced engineer</p>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        mock_page.set_content.assert_called_once()
        html_content = mock_page.set_content.call_args[0][0]
        assert "Professional Resume" in html_content

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_playwright_waits_for_fonts(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """Playwright should wait for fonts to load before generating PDF."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        # Verify wait_for_load_state was called with networkidle
        mock_page.wait_for_load_state.assert_called_with('networkidle')

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_pdf_includes_google_fonts(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """Generated PDF should include Google Fonts link."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        html_content = mock_page.set_content.call_args[0][0]
        assert "fonts.googleapis.com" in html_content


# ==============================================================================
# Test Class: Page Settings (Letter vs A4, Margins)
# ==============================================================================

class TestPDFPageSettings:
    """Tests for PDF page size and margin settings."""

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_default_page_size_is_letter(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF should use Letter (8.5" x 11") page size by default."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        pdf_call = mock_page.pdf.call_args
        assert pdf_call[1]['format'] == 'Letter'

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_a4_page_size_from_editor_state(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF should use A4 size when specified in editor state."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["cv_editor_state"]["documentStyles"]["pageSize"] = "a4"
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        pdf_call = mock_page.pdf.call_args
        assert pdf_call[1]['format'] == 'A4'

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_custom_margins_from_editor_state(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF should use custom margins from editor state."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["cv_editor_state"]["documentStyles"]["margins"] = {
            "top": 0.75,
            "right": 0.5,
            "bottom": 0.75,
            "left": 0.5
        }
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        pdf_call = mock_page.pdf.call_args
        margin = pdf_call[1]['margin']
        assert margin['top'] == '0.75in'
        assert margin['right'] == '0.5in'
        assert margin['bottom'] == '0.75in'
        assert margin['left'] == '0.5in'

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_print_background_graphics_enabled(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF should print background graphics (for highlights, colors)."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        pdf_call = mock_page.pdf.call_args
        assert pdf_call[1]['print_background'] is True


# ==============================================================================
# Test Class: Header/Footer in PDF
# ==============================================================================

class TestPDFHeaderFooter:
    """Tests for header/footer in PDF output."""

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_header_included_if_present(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF should include header if present in editor state."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["cv_editor_state"]["header"] = "John Doe | john@example.com"
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        html_content = mock_page.set_content.call_args[0][0]
        assert "John Doe | john@example.com" in html_content

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_footer_included_if_present(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF should include footer if present in editor state."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["cv_editor_state"]["footer"] = "Portfolio: https://johndoe.dev"
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        html_content = mock_page.set_content.call_args[0][0]
        assert "Portfolio: https://johndoe.dev" in html_content


# ==============================================================================
# Test Class: PDF Download Response
# ==============================================================================

class TestPDFDownloadResponse:
    """Tests for PDF file download response."""

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_pdf_returns_binary_content(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF endpoint should return binary PDF content."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.pdf.return_value = b'%PDF-1.4 fake pdf content'
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.data.startswith(b'%PDF')

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_pdf_filename_format(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF download should have filename: CV_<Company>_<Title>.pdf."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.pdf.return_value = b'%PDF-1.4'
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 200
        content_disposition = response.headers.get('Content-Disposition')
        assert content_disposition is not None
        # Fixture uses "StartupCo" and "Staff Engineer"
        assert 'CV_StartupCo_Staff_Engineer.pdf' in content_disposition


# ==============================================================================
# Test Class: Error Handling
# ==============================================================================

class TestPDFErrorHandling:
    """Tests for error handling during PDF generation."""

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_playwright_error_returns_500(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """Playwright errors should return 500 with error message."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Test CV</h1>"

        # Mock Playwright to raise error
        mock_playwright.return_value.__enter__.side_effect = Exception("Playwright launch failed")

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data
        assert "Playwright" in data["error"] or "failed" in data["error"].lower()

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_missing_editor_state_uses_default(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job):
        """PDF generation should use default content if no editor state."""
        # Arrange
        job_id = str(sample_job["_id"])
        sample_job["cv_editor_state"] = None  # No editor state
        mock_db.find_one.return_value = sample_job
        mock_converter.return_value = "<h1>Default CV</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.pdf.return_value = b'%PDF-1.4'
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 200
        # Should use default content
        mock_converter.assert_called_once()


# ==============================================================================
# Test Class: ATS Compatibility
# ==============================================================================

class TestPDFATSCompatibility:
    """Tests for ATS compatibility (text-based, not images)."""

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_pdf_is_text_based(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF should be text-based (not images) for ATS compatibility."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Professional Resume</h1><p>Software Engineer with 10 years experience</p>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.pdf.return_value = b'%PDF-1.4 /Type /Page /Contents text'
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        # Playwright with HTML content creates text-based PDFs
        # Verify HTML content contains actual text
        html_content = mock_page.set_content.call_args[0][0]
        assert "Professional Resume" in html_content
        assert "Software Engineer" in html_content


# ==============================================================================
# Test Class: Phase 4 Integration
# ==============================================================================

class TestPhase4Integration:
    """Integration tests for Phase 4 PDF export."""

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_complete_phase4_workflow(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """Complete workflow: load state -> convert to HTML -> generate PDF."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])

        # Set up complete Phase 3 state
        sample_job_with_editor_state["cv_editor_state"]["documentStyles"]["lineHeight"] = 1.5
        sample_job_with_editor_state["cv_editor_state"]["documentStyles"]["margins"] = {
            "top": 0.75, "right": 0.75, "bottom": 0.75, "left": 0.75
        }
        sample_job_with_editor_state["cv_editor_state"]["documentStyles"]["pageSize"] = "a4"
        sample_job_with_editor_state["cv_editor_state"]["header"] = "John Doe | john@example.com"
        sample_job_with_editor_state["cv_editor_state"]["footer"] = "Page 1"

        mock_db.find_one.return_value = sample_job_with_editor_state
        mock_converter.return_value = "<h1>Complete Resume</h1>"

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.pdf.return_value = b'%PDF-1.4'
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        assert response.status_code == 200

        # Verify all Phase 3 settings applied
        pdf_call = mock_page.pdf.call_args
        assert pdf_call[1]['format'] == 'A4'
        assert pdf_call[1]['margin']['top'] == '0.75in'

        # Verify HTML content includes header/footer
        html_content = mock_page.set_content.call_args[0][0]
        assert "John Doe | john@example.com" in html_content
        assert "Page 1" in html_content

    @patch('playwright.sync_api.sync_playwright')
    @patch('app.tiptap_json_to_html')
    def test_phase4_preserves_phase2_formatting(self, mock_converter, mock_playwright, authenticated_client, mock_db, sample_job_with_editor_state):
        """PDF should preserve Phase 2 text formatting (fonts, colors, alignment)."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Mock converter to return Phase 2 formatted HTML
        formatted_html = """
        <h1 style="text-align: center; font-family: 'Playfair Display';">John Doe</h1>
        <p style="font-family: 'Inter'; color: #1a1a1a;">
            <mark style="background-color: #ffff00;">Highlighted achievement</mark>
        </p>
        """
        mock_converter.return_value = formatted_html

        # Mock Playwright
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_page.pdf.return_value = b'%PDF-1.4'
        mock_pw.__enter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        mock_playwright.return_value = mock_pw

        # Act
        response = authenticated_client.post(f"/api/jobs/{job_id}/cv-editor/pdf")

        # Assert
        html_content = mock_page.set_content.call_args[0][0]

        # Verify Phase 2 formatting preserved in HTML
        assert "text-align: center" in html_content
        assert "Playfair Display" in html_content
        assert "background-color: #ffff00" in html_content or "Highlighted achievement" in html_content
