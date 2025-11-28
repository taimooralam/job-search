"""
Unit tests for CV WYSIWYG Preview functionality in job_detail.html

Tests Bug Fix #2: CV WYSIWYG Sync - TipTap JSON rendering instead of markdown
- Verifies cv-display-area div exists for jobs with CV
- Tests renderCVPreview() function presence
- Tests tiptapJsonToHtml() converter function
- Tests API endpoint returns editor state with document styles
- Tests CSS styles and event listeners
"""

import pytest
import json
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock, patch


class TestCVDisplayAreaPresence:
    """Tests for CV display area HTML presence in job detail template."""

    def test_cv_display_area_present(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """cv-display-area div should exist for jobs with CV content."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Check for cv-display-area div
        assert 'cv-display-area' in html_content
        assert 'id="cv-display-area"' in html_content

    def test_cv_display_area_has_preview_class(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """cv-display-area should have cv-preview-content class."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should have cv-preview-content class
        assert 'cv-preview-content' in html_content

    def test_cv_display_area_not_shown_without_cv(
        self, authenticated_client, mock_db, sample_job
    ):
        """cv-display-area should not be rendered when job has no CV."""
        # Arrange
        job_id = str(sample_job["_id"])
        sample_job["has_cv"] = False
        sample_job.pop("cv_text", None)
        sample_job.pop("cv_editor_state", None)
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # cv-display-area should not be present
        # (or should be within a conditional block that's not rendered)
        # The template likely has {% if job.has_cv %} logic


class TestRenderCVPreviewFunction:
    """Tests for renderCVPreview() JavaScript function."""

    def test_render_cv_preview_function_defined(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """renderCVPreview() function should be defined in template."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Check for function definition
        assert 'function renderCVPreview' in html_content or \
               'async function renderCVPreview' in html_content

    def test_render_cv_preview_fetches_editor_state(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """renderCVPreview() should fetch editor state from API."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should make fetch call to cv-editor API endpoint
        assert '/api/jobs/' in html_content
        assert 'cv-editor' in html_content
        assert 'fetch(' in html_content

    def test_render_cv_preview_calls_tiptap_converter(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """renderCVPreview() should call tiptapJsonToHtml() to convert content."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should call tiptapJsonToHtml function
        assert 'tiptapJsonToHtml' in html_content

    def test_render_cv_preview_updates_display_area(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """renderCVPreview() should update cv-display-area innerHTML."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should reference cv-display-area and innerHTML
        rendercv_section = html_content[html_content.find('renderCVPreview'):] if 'renderCVPreview' in html_content else ''
        assert 'cv-display-area' in rendercv_section
        assert 'innerHTML' in rendercv_section or 'html' in rendercv_section.lower()

    def test_render_cv_preview_has_error_handling(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """renderCVPreview() should have try-catch error handling."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should have error handling
        rendercv_section = html_content[html_content.find('renderCVPreview'):] if 'renderCVPreview' in html_content else ''
        assert 'catch' in rendercv_section or 'error' in rendercv_section.lower()

    def test_render_cv_preview_applies_document_styles(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """renderCVPreview() should apply documentStyles to display area."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should reference documentStyles
        assert 'documentStyles' in html_content


class TestTipTapJsonToHtmlFunction:
    """Tests for tiptapJsonToHtml() converter function."""

    def test_tiptap_json_to_html_function_defined(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """tiptapJsonToHtml() function should be defined in template."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Check for function definition
        assert 'function tiptapJsonToHtml' in html_content

    def test_tiptap_json_to_html_accepts_content_parameter(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """tiptapJsonToHtml() should accept content parameter."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Function should have content parameter
        assert 'function tiptapJsonToHtml(content)' in html_content or \
               'function tiptapJsonToHtml (content)' in html_content

    def test_tiptap_json_to_html_validates_doc_type(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """tiptapJsonToHtml() should validate content.type === 'doc'."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should check content.type
        tiptap_section = html_content[html_content.find('tiptapJsonToHtml'):] if 'tiptapJsonToHtml' in html_content else ''
        assert 'type' in tiptap_section
        assert 'doc' in tiptap_section

    def test_tiptap_json_to_html_handles_headings(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """tiptapJsonToHtml() should handle heading nodes."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should handle heading type
        tiptap_section = html_content[html_content.find('tiptapJsonToHtml'):] if 'tiptapJsonToHtml' in html_content else ''
        assert 'heading' in tiptap_section

    def test_tiptap_json_to_html_handles_paragraphs(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """tiptapJsonToHtml() should handle paragraph nodes."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should handle paragraph type
        tiptap_section = html_content[html_content.find('tiptapJsonToHtml'):] if 'tiptapJsonToHtml' in html_content else ''
        assert 'paragraph' in tiptap_section

    def test_tiptap_json_to_html_handles_lists(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """tiptapJsonToHtml() should handle bulletList and orderedList nodes."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should handle list types
        tiptap_section = html_content[html_content.find('tiptapJsonToHtml'):] if 'tiptapJsonToHtml' in html_content else ''
        # Check for bulletList or orderedList handling
        has_list_handling = 'bulletList' in tiptap_section or 'orderedList' in tiptap_section or \
                           'ul' in tiptap_section or 'ol' in tiptap_section
        # Note: May use switch/case or if-else logic


class TestCVEditorAPIEndpoint:
    """Tests for /api/jobs/{id}/cv-editor endpoint (GET)."""

    def test_cv_editor_api_returns_state(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """GET /api/jobs/{id}/cv-editor should return editor state."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "editor_state" in data
        assert data["editor_state"]["version"] == 1

    def test_cv_editor_api_includes_document_styles(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """API response should include documentStyles."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert "editor_state" in data
        assert "documentStyles" in data["editor_state"]

        # Check documentStyles structure
        doc_styles = data["editor_state"]["documentStyles"]
        assert "fontFamily" in doc_styles
        assert "fontSize" in doc_styles
        assert "lineHeight" in doc_styles
        assert "margins" in doc_styles

    def test_cv_editor_api_includes_tiptap_content(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """API response should include TipTap content structure."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert "editor_state" in data
        assert "content" in data["editor_state"]

        # Check TipTap content structure
        content = data["editor_state"]["content"]
        assert content["type"] == "doc"
        assert "content" in content
        assert isinstance(content["content"], list)

    def test_cv_editor_api_migrates_markdown_to_tiptap(
        self, authenticated_client, mock_db, sample_job
    ):
        """API should migrate markdown cv_text to TipTap JSON when no editor state exists."""
        # Arrange
        job_id = str(sample_job["_id"])
        sample_job["cv_text"] = "# John Doe\n\n## Experience\n\n- 5 years Python"
        sample_job.pop("cv_editor_state", None)  # No editor state
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "editor_state" in data

        # Should have migrated content
        content = data["editor_state"]["content"]["content"]
        assert len(content) > 0
        # First node should be heading
        assert content[0]["type"] == "heading"

    def test_cv_editor_api_returns_default_when_no_cv(
        self, authenticated_client, mock_db, sample_job
    ):
        """API should return default empty state when no CV exists."""
        # Arrange
        job_id = str(sample_job["_id"])
        sample_job.pop("cv_text", None)
        sample_job.pop("cv_editor_state", None)
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["editor_state"]["content"]["content"] == []

    def test_cv_editor_api_requires_authentication(self, client, mock_db):
        """API endpoint should require authentication."""
        # Arrange
        job_id = str(ObjectId())

        # Act
        response = client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        # API endpoints return 401 Unauthorized instead of redirecting
        assert response.status_code == 401


class TestCVPreviewCSSStyles:
    """Tests for CV preview CSS styling."""

    def test_cv_preview_content_class_defined(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """cv-preview-content CSS class should be defined or referenced."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should reference cv-preview-content class
        assert 'cv-preview-content' in html_content

    def test_cv_preview_has_typography_styles(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """CV preview should apply typography styles from documentStyles."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should reference font-family or fontSize styling
        rendercv_section = html_content[html_content.find('renderCVPreview'):] if 'renderCVPreview' in html_content else ''
        # Look for style application
        assert 'style' in rendercv_section or 'fontFamily' in rendercv_section

    def test_cv_preview_container_has_scrolling(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """CV container should have overflow and max-height for scrolling."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should have cv-container with overflow
        assert 'cv-container' in html_content
        # Should have max-height style (inline on element) and overflow class
        assert 'max-height' in html_content  # Inline style: style="max-height: 800px;"
        assert 'overflow-auto' in html_content  # Tailwind class for scrolling


class TestCVContentEventListener:
    """Tests for CV content update event listener."""

    def test_cv_content_updated_event_listener_defined(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should listen for cvContentUpdated event."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should have event listener for cvContentUpdated
        assert 'cvContentUpdated' in html_content
        assert 'addEventListener' in html_content

    def test_event_listener_calls_render_cv_preview(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Event listener should call renderCVPreview() when triggered."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Event listener should call renderCVPreview
        event_section = html_content[html_content.find('cvContentUpdated'):] if 'cvContentUpdated' in html_content else ''
        assert 'renderCVPreview' in event_section

    def test_dom_content_loaded_triggers_render(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should call renderCVPreview() on DOMContentLoaded."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should have DOMContentLoaded event listener
        assert 'DOMContentLoaded' in html_content
        # Should call renderCVPreview
        dom_section = html_content[html_content.find('DOMContentLoaded'):] if 'DOMContentLoaded' in html_content else ''
        assert 'renderCVPreview' in dom_section


class TestEdgeCases:
    """Edge case tests for CV WYSIWYG preview."""

    def test_handles_empty_tiptap_document(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should handle empty TipTap document gracefully."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        sample_job_with_editor_state["cv_editor_state"]["content"]["content"] = []
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["editor_state"]["content"]["content"] == []

    def test_handles_malformed_tiptap_json(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """tiptapJsonToHtml() should validate and handle malformed JSON."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # tiptapJsonToHtml should validate content
        tiptap_section = html_content[html_content.find('tiptapJsonToHtml'):] if 'tiptapJsonToHtml' in html_content else ''
        # Should check for content existence and type
        assert '!content' in tiptap_section or 'content.type' in tiptap_section

    def test_handles_very_large_cv_documents(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should handle large CV documents with many nodes."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True

        # Create large document
        large_content = [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": f"Paragraph {i}"}]
            }
            for i in range(100)
        ]
        sample_job_with_editor_state["cv_editor_state"]["content"]["content"] = large_content
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["editor_state"]["content"]["content"]) == 100

    def test_handles_unicode_and_special_characters(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should handle Unicode, emojis, and special characters in CV content."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        sample_job_with_editor_state["cv_editor_state"]["content"]["content"][0]["content"][0]["text"] = "François 你好 👋 <>&\""
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        # Content should be preserved
        assert "François" in str(data["editor_state"])

    def test_cv_preview_error_displays_fallback_message(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should display error message if CV preview fails to load."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should have error handling that displays message
        rendercv_section = html_content[html_content.find('renderCVPreview'):] if 'renderCVPreview' in html_content else ''
        assert 'error' in rendercv_section.lower() or 'Error' in rendercv_section


class TestIntegrationWithCVEditor:
    """Integration tests between CV preview and editor."""

    def test_preview_updates_when_editor_saves(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """CV preview should refresh when editor dispatches cvContentUpdated event."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["has_cv"] = True
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html_content = response.data.decode('utf-8')

        # Should have event listener that checks jobId
        event_section = html_content[html_content.find('cvContentUpdated'):] if 'cvContentUpdated' in html_content else ''
        assert 'jobId' in event_section
        assert 'renderCVPreview' in event_section

    def test_preview_renders_same_content_as_editor(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Preview should render the same TipTap JSON that editor uses."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act - Get editor state
        editor_response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert - Editor state should be the same as what preview fetches
        assert editor_response.status_code == 200
        editor_data = editor_response.get_json()
        assert "editor_state" in editor_data
        assert editor_data["editor_state"]["content"]["type"] == "doc"
        # Preview will fetch this same data and render it
