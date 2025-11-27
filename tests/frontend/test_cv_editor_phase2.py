"""
Integration tests for CV Rich Text Editor - Phase 2: Enhanced Text Formatting

Tests cover:
- Font family selector (60+ Google Fonts)
- Font size control (8-24pt)
- Text alignment (left/center/right/justify)
- Indentation controls (Tab/Shift+Tab + toolbar buttons)
- Highlight color picker
- Auto-save functionality
- Save indicator states
- Toolbar state updates
- API endpoints for loading/saving editor state

IMPORTANT: These tests address reported user issues:
1. CV content not loading in editor panel
2. Error displayed when opening editor
3. Save indicator unclear
"""

import pytest
import json
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock, patch


# ==============================================================================
# Test Class: API Endpoints (High Priority - Addresses Reported Issues)
# ==============================================================================

class TestCVEditorAPIEndpoints:
    """Tests for CV editor API endpoints - critical for debugging reported issues."""

    def test_get_cv_editor_state_returns_existing_state(self, authenticated_client, mock_db, sample_job_with_phase2_formatting):
        """GET /api/jobs/<job_id>/cv-editor should return existing editor state."""
        # Arrange
        job_id = str(sample_job_with_phase2_formatting["_id"])
        mock_db.find_one.return_value = sample_job_with_phase2_formatting

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "editor_state" in data
        assert data["editor_state"]["version"] == 1
        assert data["editor_state"]["content"]["type"] == "doc"
        assert len(data["editor_state"]["content"]["content"]) > 0

    def test_get_cv_editor_state_migrates_markdown_when_no_state_exists(self, authenticated_client, mock_db, sample_job):
        """Should migrate cv_text (markdown) to editor state when cv_editor_state is missing."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "editor_state" in data
        assert data["editor_state"]["content"]["type"] == "doc"
        # Should have migrated markdown headings and paragraphs
        assert len(data["editor_state"]["content"]["content"]) >= 2

    def test_get_cv_editor_state_returns_default_when_no_content(self, authenticated_client, mock_db):
        """Should return default empty state when job has no CV content."""
        # Arrange
        job_without_cv = {
            "_id": ObjectId(),
            "title": "Developer",
            "company": "TestCo"
        }
        job_id = str(job_without_cv["_id"])
        mock_db.find_one.return_value = job_without_cv

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["editor_state"]["content"]["type"] == "doc"
        assert data["editor_state"]["documentStyles"]["fontFamily"] == "Inter"
        assert data["editor_state"]["documentStyles"]["fontSize"] == 11

    def test_get_cv_editor_state_handles_invalid_job_id(self, authenticated_client, mock_db):
        """Should return 400 for invalid job ID format."""
        # Act
        response = authenticated_client.get("/api/jobs/invalid-id/cv-editor")

        # Assert
        assert response.status_code == 400
        assert b"Invalid job ID" in response.data

    def test_get_cv_editor_state_handles_job_not_found(self, authenticated_client, mock_db):
        """Should return 404 when job doesn't exist."""
        # Arrange
        job_id = str(ObjectId())
        mock_db.find_one.return_value = None

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 404
        assert b"Job not found" in response.data

    def test_save_cv_editor_state_success(self, authenticated_client, mock_db, sample_job):
        """PUT /api/jobs/<job_id>/cv-editor should save editor state with Phase 2 formatting."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 1, "textAlign": "center"},
                        "content": [
                            {
                                "type": "text",
                                "text": "John Doe",
                                "marks": [
                                    {"type": "textStyle", "attrs": {"fontFamily": "Playfair Display", "fontSize": "24pt"}}
                                ]
                            }
                        ]
                    },
                    {
                        "type": "paragraph",
                        "attrs": {"textAlign": "justify", "style": "margin-left: 0.5in"},
                        "content": [
                            {
                                "type": "text",
                                "text": "Highlighted text",
                                "marks": [
                                    {"type": "highlight", "attrs": {"color": "#ffff00"}}
                                ]
                            }
                        ]
                    }
                ]
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.4,
                "margins": {"top": 0.75, "right": 0.75, "bottom": 0.75, "left": 0.75},
                "pageSize": "letter"
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "savedAt" in data

        # Verify update_one was called with correct data
        mock_db.update_one.assert_called_once()
        call_args = mock_db.update_one.call_args
        assert call_args[0][0] == {"_id": sample_job["_id"]}
        update_data = call_args[0][1]["$set"]
        assert "cv_editor_state" in update_data
        assert update_data["cv_editor_state"]["version"] == 1
        assert "lastSavedAt" in update_data["cv_editor_state"]

    def test_save_cv_editor_state_missing_content_returns_400(self, authenticated_client, mock_db, sample_job):
        """Should return 400 when content is missing from request."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json={"version": 1},  # Missing content
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 400
        assert b"Missing content" in response.data

    def test_save_cv_editor_state_invalid_job_id(self, authenticated_client, mock_db):
        """Should return 400 for invalid job ID."""
        # Act
        response = authenticated_client.put(
            "/api/jobs/invalid-id/cv-editor",
            json={"version": 1, "content": {"type": "doc"}},
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 400

    def test_save_cv_editor_state_job_not_found(self, authenticated_client, mock_db):
        """Should return 404 when job doesn't exist."""
        # Arrange
        job_id = str(ObjectId())
        mock_db.find_one.return_value = None
        mock_db.update_one.return_value = MagicMock(matched_count=0)

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json={"version": 1, "content": {"type": "doc", "content": []}},
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 404


# ==============================================================================
# Test Class: Phase 2 Formatting Features
# ==============================================================================

class TestPhase2FontControls:
    """Tests for font family and font size selectors."""

    def test_font_family_selector_contains_60_plus_fonts(self, authenticated_client, mock_db, sample_job):
        """Font selector dropdown should have 60+ font options."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        # We're checking that the HTML template contains the font options
        # (This is an integration test, so we check the rendered HTML)
        html = response.data.decode('utf-8')

        # Check for representative fonts from each category
        assert 'Crimson Text' in html
        assert 'Playfair Display' in html
        assert 'Inter' in html
        assert 'Roboto' in html
        assert 'Fira Code' in html
        assert 'Bebas Neue' in html
        assert 'Roboto Condensed' in html
        assert 'Quicksand' in html

    def test_font_family_organized_by_category(self, authenticated_client, mock_db, sample_job):
        """Fonts should be organized into optgroups by category."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert '<optgroup label="Serif (Professional)">' in html
        assert '<optgroup label="Sans-Serif (Modern)">' in html
        assert '<optgroup label="Monospace (Technical)">' in html
        assert '<optgroup label="Display (Creative)">' in html
        assert '<optgroup label="Condensed (Space-Saving)">' in html
        assert '<optgroup label="Rounded (Friendly)">' in html

    def test_font_size_selector_has_12_options(self, authenticated_client, mock_db, sample_job):
        """Font size selector should have options from 8pt to 24pt."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        for size in ['8pt', '9pt', '10pt', '11pt', '12pt', '13pt', '14pt', '16pt', '18pt', '20pt', '22pt', '24pt']:
            assert f'value="{size}"' in html

    def test_default_font_is_inter(self, authenticated_client, mock_db, sample_job):
        """Default font family should be Inter."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'value="Inter" selected' in html

    def test_default_font_size_is_11pt(self, authenticated_client, mock_db, sample_job):
        """Default font size should be 11pt."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'value="11pt" selected' in html

    def test_font_formatting_persists_in_saved_state(self, authenticated_client, mock_db, sample_job):
        """Font family and size should persist in MongoDB after save."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "Roboto 14pt text",
                                "marks": [
                                    {"type": "textStyle", "attrs": {"fontFamily": "Roboto", "fontSize": "14pt"}}
                                ]
                            }
                        ]
                    }
                ]
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        saved_state = mock_db.update_one.call_args[0][1]["$set"]["cv_editor_state"]
        assert saved_state["content"]["content"][0]["content"][0]["marks"][0]["attrs"]["fontFamily"] == "Roboto"
        assert saved_state["content"]["content"][0]["content"][0]["marks"][0]["attrs"]["fontSize"] == "14pt"


class TestPhase2TextAlignment:
    """Tests for text alignment controls."""

    def test_alignment_buttons_present_in_toolbar(self, authenticated_client, mock_db, sample_job):
        """Toolbar should have left/center/right/justify alignment buttons."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'data-align="left"' in html
        assert 'data-align="center"' in html
        assert 'data-align="right"' in html
        assert 'data-align="justify"' in html
        assert 'Align Left' in html
        assert 'Align Center' in html
        assert 'Align Right' in html
        assert 'Justify' in html

    def test_alignment_persists_in_saved_state(self, authenticated_client, mock_db, sample_job):
        """Text alignment should persist in paragraph attrs."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "attrs": {"textAlign": "center"},
                        "content": [{"type": "text", "text": "Centered text"}]
                    },
                    {
                        "type": "paragraph",
                        "attrs": {"textAlign": "justify"},
                        "content": [{"type": "text", "text": "Justified text"}]
                    }
                ]
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        saved_state = mock_db.update_one.call_args[0][1]["$set"]["cv_editor_state"]
        assert saved_state["content"]["content"][0]["attrs"]["textAlign"] == "center"
        assert saved_state["content"]["content"][1]["attrs"]["textAlign"] == "justify"

    def test_alignment_applies_to_paragraph_nodes(self, authenticated_client, mock_db, sample_job_with_phase2_formatting):
        """Alignment should be stored in paragraph attrs, not marks."""
        # Arrange
        job_id = str(sample_job_with_phase2_formatting["_id"])
        mock_db.find_one.return_value = sample_job_with_phase2_formatting

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        heading = data["editor_state"]["content"]["content"][0]
        assert heading["attrs"]["textAlign"] == "center"


class TestPhase2Indentation:
    """Tests for indentation controls (Tab/Shift+Tab + toolbar buttons)."""

    def test_indent_buttons_present_in_toolbar(self, authenticated_client, mock_db, sample_job):
        """Toolbar should have indent/outdent buttons."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'Outdent' in html
        assert 'Indent' in html
        assert 'Decrease Indent' in html
        assert 'Increase Indent' in html

    def test_indentation_persists_as_inline_style(self, authenticated_client, mock_db, sample_job):
        """Indentation should persist as margin-left inline style."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "attrs": {"style": "margin-left: 0.5in"},
                        "content": [{"type": "text", "text": "Indented once"}]
                    },
                    {
                        "type": "paragraph",
                        "attrs": {"style": "margin-left: 1in"},
                        "content": [{"type": "text", "text": "Indented twice"}]
                    }
                ]
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        saved_state = mock_db.update_one.call_args[0][1]["$set"]["cv_editor_state"]
        assert "margin-left: 0.5in" in saved_state["content"]["content"][0]["attrs"]["style"]
        assert "margin-left: 1in" in saved_state["content"]["content"][1]["attrs"]["style"]

    def test_indentation_increments_by_half_inch(self, authenticated_client, mock_db, sample_job_with_phase2_formatting):
        """Each indent level should add 0.5 inches."""
        # Arrange
        job_id = str(sample_job_with_phase2_formatting["_id"])
        mock_db.find_one.return_value = sample_job_with_phase2_formatting

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        indented_para = data["editor_state"]["content"]["content"][1]
        assert indented_para["attrs"]["style"] == "margin-left: 0.5in"


class TestPhase2HighlightColor:
    """Tests for highlight color picker."""

    def test_highlight_color_picker_present_in_toolbar(self, authenticated_client, mock_db, sample_job):
        """Toolbar should have highlight color picker."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'cv-highlight-color' in html
        assert 'Highlight Color' in html
        assert 'Remove Highlight' in html

    def test_default_highlight_color_is_yellow(self, authenticated_client, mock_db, sample_job):
        """Default highlight color should be yellow (#ffff00)."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'value="#ffff00"' in html

    def test_highlight_persists_as_mark(self, authenticated_client, mock_db, sample_job):
        """Highlight should persist as a mark with color attribute."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "Important point",
                                "marks": [
                                    {"type": "highlight", "attrs": {"color": "#ffff00"}}
                                ]
                            }
                        ]
                    }
                ]
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        saved_state = mock_db.update_one.call_args[0][1]["$set"]["cv_editor_state"]
        marks = saved_state["content"]["content"][0]["content"][0]["marks"]
        assert any(mark["type"] == "highlight" and mark["attrs"]["color"] == "#ffff00" for mark in marks)

    def test_multiple_highlight_colors_supported(self, authenticated_client, mock_db, sample_job):
        """Different text segments can have different highlight colors."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "Yellow highlight",
                                "marks": [{"type": "highlight", "attrs": {"color": "#ffff00"}}]
                            },
                            {
                                "type": "text",
                                "text": " "
                            },
                            {
                                "type": "text",
                                "text": "Green highlight",
                                "marks": [{"type": "highlight", "attrs": {"color": "#00ff00"}}]
                            }
                        ]
                    }
                ]
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200


# ==============================================================================
# Test Class: Auto-Save and State Management
# ==============================================================================

class TestAutoSaveFunctionality:
    """Tests for auto-save after 3 seconds of inactivity."""

    def test_autosave_includes_all_phase2_formatting(self, authenticated_client, mock_db, sample_job):
        """Auto-save should persist all Phase 2 formatting attributes."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 1, "textAlign": "center"},
                        "content": [
                            {
                                "type": "text",
                                "text": "John Doe",
                                "marks": [
                                    {"type": "textStyle", "attrs": {"fontFamily": "Playfair Display", "fontSize": "24pt"}}
                                ]
                            }
                        ]
                    },
                    {
                        "type": "paragraph",
                        "attrs": {"textAlign": "justify", "style": "margin-left: 1in"},
                        "content": [
                            {
                                "type": "text",
                                "text": "Highlighted summary",
                                "marks": [
                                    {"type": "textStyle", "attrs": {"fontSize": "11pt"}},
                                    {"type": "highlight", "attrs": {"color": "#ffff00"}}
                                ]
                            }
                        ]
                    }
                ]
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.4,
                "margins": {"top": 0.75, "right": 0.75, "bottom": 0.75, "left": 0.75},
                "pageSize": "letter"
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        saved_state = mock_db.update_one.call_args[0][1]["$set"]["cv_editor_state"]

        # Verify font family and size
        heading = saved_state["content"]["content"][0]
        assert heading["content"][0]["marks"][0]["attrs"]["fontFamily"] == "Playfair Display"
        assert heading["content"][0]["marks"][0]["attrs"]["fontSize"] == "24pt"

        # Verify alignment
        assert heading["attrs"]["textAlign"] == "center"

        # Verify indentation
        para = saved_state["content"]["content"][1]
        assert para["attrs"]["style"] == "margin-left: 1in"

        # Verify highlight
        assert any(mark["type"] == "highlight" for mark in para["content"][0]["marks"])

    def test_autosave_updates_timestamp(self, authenticated_client, mock_db, sample_job):
        """Auto-save should update lastSavedAt timestamp."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []}
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        saved_state = mock_db.update_one.call_args[0][1]["$set"]["cv_editor_state"]
        assert "lastSavedAt" in saved_state
        # Verify it's a datetime object
        assert isinstance(saved_state["lastSavedAt"], datetime)


class TestSaveIndicator:
    """Tests for save indicator states (addresses user issue #3)."""

    def test_save_indicator_element_present(self, authenticated_client, mock_db, sample_job):
        """Save indicator element should be present in HTML."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'id="cv-save-indicator"' in html

    def test_save_indicator_shows_saved_state_by_default(self, authenticated_client, mock_db, sample_job):
        """Initial save indicator should show 'Saved' state."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert '● Saved' in html or 'Saved' in html

    # Note: Testing unsaved/saving states requires JavaScript execution
    # which is handled by integration/E2E tests with Selenium/Playwright


# ==============================================================================
# Test Class: Markdown Migration
# ==============================================================================

class TestMarkdownMigration:
    """Tests for migrating cv_text (markdown) to TipTap editor state."""

    def test_migration_converts_h1_headings(self, authenticated_client, mock_db):
        """Markdown # headings should convert to TipTap heading level 1."""
        # Arrange
        job = {
            "_id": ObjectId(),
            "title": "Dev",
            "company": "Co",
            "cv_text": "# John Doe\n\nSoftware Engineer"
        }
        job_id = str(job["_id"])
        mock_db.find_one.return_value = job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        content = data["editor_state"]["content"]["content"]

        # First node should be heading level 1
        assert content[0]["type"] == "heading"
        assert content[0]["attrs"]["level"] == 1
        assert content[0]["content"][0]["text"] == "John Doe"

    def test_migration_converts_h2_headings(self, authenticated_client, mock_db):
        """Markdown ## headings should convert to TipTap heading level 2."""
        # Arrange
        job = {
            "_id": ObjectId(),
            "title": "Dev",
            "company": "Co",
            "cv_text": "## Experience\n\nSenior Engineer"
        }
        job_id = str(job["_id"])
        mock_db.find_one.return_value = job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        content = data["editor_state"]["content"]["content"]

        # First node should be heading level 2
        assert content[0]["type"] == "heading"
        assert content[0]["attrs"]["level"] == 2

    def test_migration_converts_bullet_lists(self, authenticated_client, mock_db):
        """Markdown bullet lists should convert to TipTap bulletList."""
        # Arrange
        job = {
            "_id": ObjectId(),
            "title": "Dev",
            "company": "Co",
            "cv_text": "## Skills\n\n- Python\n- JavaScript\n- SQL"
        }
        job_id = str(job["_id"])
        mock_db.find_one.return_value = job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        content = data["editor_state"]["content"]["content"]

        # Should have heading + bulletList
        assert any(node["type"] == "bulletList" for node in content)

    def test_migration_converts_paragraphs(self, authenticated_client, mock_db):
        """Regular markdown text should convert to TipTap paragraphs."""
        # Arrange
        job = {
            "_id": ObjectId(),
            "title": "Dev",
            "company": "Co",
            "cv_text": "This is a paragraph.\n\nThis is another paragraph."
        }
        job_id = str(job["_id"])
        mock_db.find_one.return_value = job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        content = data["editor_state"]["content"]["content"]

        # Should have multiple paragraph nodes
        paragraphs = [node for node in content if node["type"] == "paragraph"]
        assert len(paragraphs) >= 2


# ==============================================================================
# Test Class: Error Handling (Addresses Reported Issues)
# ==============================================================================

class TestErrorHandling:
    """Tests for error scenarios - critical for debugging user-reported issues."""

    def test_handles_malformed_json_in_editor_state(self, authenticated_client, mock_db):
        """Should handle job with malformed cv_editor_state gracefully."""
        # Arrange
        job_with_bad_state = {
            "_id": ObjectId(),
            "title": "Dev",
            "company": "Co",
            "cv_editor_state": "not valid json"  # Malformed
        }
        job_id = str(job_with_bad_state["_id"])
        mock_db.find_one.return_value = job_with_bad_state

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        # Should return default state instead of crashing
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_handles_missing_content_type_in_save(self, authenticated_client, mock_db, sample_job):
        """Should handle PUT request without proper content type."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            data=json.dumps({"version": 1, "content": {"type": "doc"}}),
            # No content_type header
        )

        # Assert
        # Should handle gracefully (either 400 or 415)
        assert response.status_code in [400, 415]

    def test_unauthenticated_access_redirects_to_login(self, client, mock_db, sample_job):
        """Unauthenticated requests should redirect to login."""
        # Arrange
        job_id = str(sample_job["_id"])

        # Act
        response = client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 302  # Redirect
        assert b"login" in response.data.lower() or response.headers.get("Location", "").endswith("/login")


# ==============================================================================
# Test Class: Integration Tests
# ==============================================================================

class TestCVEditorIntegration:
    """End-to-end integration tests for the CV editor."""

    def test_full_workflow_open_edit_save(self, authenticated_client, mock_db, sample_job):
        """Test complete workflow: open editor -> load content -> edit -> save."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        # Step 1: Load editor state (simulates opening editor panel)
        load_response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")
        assert load_response.status_code == 200
        loaded_state = load_response.get_json()["editor_state"]

        # Step 2: Modify content (simulates user editing)
        loaded_state["content"]["content"].append({
            "type": "paragraph",
            "attrs": {"textAlign": "center"},
            "content": [
                {
                    "type": "text",
                    "text": "New paragraph with formatting",
                    "marks": [
                        {"type": "textStyle", "attrs": {"fontFamily": "Roboto", "fontSize": "12pt"}},
                        {"type": "bold"}
                    ]
                }
            ]
        })

        # Step 3: Save modified state (simulates auto-save)
        save_response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=loaded_state,
            content_type="application/json"
        )
        assert save_response.status_code == 200

        # Step 4: Verify saved content persists
        saved_state = mock_db.update_one.call_args[0][1]["$set"]["cv_editor_state"]
        assert len(saved_state["content"]["content"]) > len(sample_job.get("cv_editor_state", {}).get("content", {}).get("content", []))

    def test_concurrent_formatting_attributes(self, authenticated_client, mock_db, sample_job):
        """Test that multiple formatting attributes can coexist on same text."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        # Text with bold + italic + font family + font size + highlight
        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "attrs": {"textAlign": "right", "style": "margin-left: 0.5in"},
                        "content": [
                            {
                                "type": "text",
                                "text": "Heavily formatted text",
                                "marks": [
                                    {"type": "bold"},
                                    {"type": "italic"},
                                    {"type": "underline"},
                                    {"type": "textStyle", "attrs": {"fontFamily": "Merriweather", "fontSize": "18pt"}},
                                    {"type": "highlight", "attrs": {"color": "#00ffff"}}
                                ]
                            }
                        ]
                    }
                ]
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        saved_state = mock_db.update_one.call_args[0][1]["$set"]["cv_editor_state"]
        marks = saved_state["content"]["content"][0]["content"][0]["marks"]

        # Verify all marks are preserved
        assert any(mark["type"] == "bold" for mark in marks)
        assert any(mark["type"] == "italic" for mark in marks)
        assert any(mark["type"] == "underline" for mark in marks)
        assert any(mark["type"] == "highlight" for mark in marks)
        assert any(mark.get("attrs", {}).get("fontFamily") == "Merriweather" for mark in marks)
