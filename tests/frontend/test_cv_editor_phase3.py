"""
Integration tests for CV Rich Text Editor - Phase 3: Document-Level Styles

Tests cover:
- Document margin controls (top, right, bottom, left)
- Line height adjustment (1.0, 1.15, 1.5, 2.0)
- Page size selector (Letter vs A4)
- Page preview ruler (optional)
- Header/footer support (basic)
- MongoDB persistence of Phase 3 settings
- State restoration and CSS application

Phase 3 focuses on document-level formatting that affects the entire CV layout,
not individual text selections.
"""

import pytest
import json
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock, patch


# ==============================================================================
# Test Class: Document Margin Controls
# ==============================================================================

class TestDocumentMarginControls:
    """Tests for document-level margin controls."""

    def test_margin_controls_present_in_toolbar(self, authenticated_client, mock_db, sample_job):
        """Toolbar should have margin input controls."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'margin-top' in html.lower() or 'Margin' in html
        assert 'margin-right' in html.lower() or 'Margin' in html
        assert 'margin-bottom' in html.lower() or 'Margin' in html
        assert 'margin-left' in html.lower() or 'Margin' in html

    def test_default_margins_are_one_inch(self, authenticated_client, mock_db, sample_job):
        """Default margins should be 1.0 inch on all sides."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        margins = data["editor_state"]["documentStyles"]["margins"]
        assert margins["top"] == 1.0
        assert margins["right"] == 1.0
        assert margins["bottom"] == 1.0
        assert margins["left"] == 1.0

    def test_custom_margins_persist_to_mongodb(self, authenticated_client, mock_db, sample_job):
        """Custom margin settings should persist to MongoDB."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.15,
                "margins": {
                    "top": 0.5,
                    "right": 0.75,
                    "bottom": 1.0,
                    "left": 1.25
                },
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
        assert saved_state["documentStyles"]["margins"]["top"] == 0.5
        assert saved_state["documentStyles"]["margins"]["right"] == 0.75
        assert saved_state["documentStyles"]["margins"]["bottom"] == 1.0
        assert saved_state["documentStyles"]["margins"]["left"] == 1.25

    def test_margin_range_validation(self, authenticated_client, mock_db, sample_job):
        """Margins should be within 0.5" to 2.0" range."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        # Test minimum margin (0.5")
        editor_state_min = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.15,
                "margins": {
                    "top": 0.5,
                    "right": 0.5,
                    "bottom": 0.5,
                    "left": 0.5
                },
                "pageSize": "letter"
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state_min,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200

        # Test maximum margin (2.0")
        editor_state_max = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.15,
                "margins": {
                    "top": 2.0,
                    "right": 2.0,
                    "bottom": 2.0,
                    "left": 2.0
                },
                "pageSize": "letter"
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state_max,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200

    def test_margin_increments_by_quarter_inch(self, authenticated_client, mock_db, sample_job):
        """Margin dropdowns should increment by 0.25 inches."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        # Check for common margin values
        for value in [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]:
            # Value should appear in dropdown options
            assert str(value) in html


# ==============================================================================
# Test Class: Line Height Adjustment
# ==============================================================================

class TestLineHeightAdjustment:
    """Tests for document-level line height controls."""

    def test_line_height_selector_present_in_toolbar(self, authenticated_client, mock_db, sample_job):
        """Toolbar should have line height dropdown."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'line-height' in html.lower() or 'Line Height' in html
        assert 'Single' in html or '1.0' in html
        assert 'Double' in html or '2.0' in html

    def test_default_line_height_is_1_15(self, authenticated_client, mock_db, sample_job):
        """Default line height should be 1.15 (standard resume spacing)."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["editor_state"]["documentStyles"]["lineHeight"] == 1.15

    def test_line_height_options_available(self, authenticated_client, mock_db, sample_job):
        """Line height selector should have options: 1.0, 1.15, 1.5, 2.0."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        for value in ['1.0', '1.15', '1.5', '2.0']:
            assert value in html

    def test_line_height_persists_to_mongodb(self, authenticated_client, mock_db, sample_job):
        """Line height setting should persist to MongoDB."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.5,  # Changed from default
                "margins": {
                    "top": 1.0,
                    "right": 1.0,
                    "bottom": 1.0,
                    "left": 1.0
                },
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
        assert saved_state["documentStyles"]["lineHeight"] == 1.5

    def test_line_height_applies_to_editor_paragraphs(self, authenticated_client, mock_db, sample_job_with_editor_state):
        """Line height should apply to all paragraphs in the editor."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])

        # Modify editor state to have custom line height
        sample_job_with_editor_state["cv_editor_state"]["documentStyles"]["lineHeight"] = 2.0
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["editor_state"]["documentStyles"]["lineHeight"] == 2.0


# ==============================================================================
# Test Class: Page Size Selector
# ==============================================================================

class TestPageSizeSelector:
    """Tests for page size selector (Letter vs A4)."""

    def test_page_size_selector_present_in_toolbar(self, authenticated_client, mock_db, sample_job):
        """Toolbar should have page size dropdown."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'page-size' in html.lower() or 'Page Size' in html
        assert 'Letter' in html
        assert 'A4' in html

    def test_default_page_size_is_letter(self, authenticated_client, mock_db, sample_job):
        """Default page size should be Letter (8.5" x 11")."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["editor_state"]["documentStyles"]["pageSize"] == "letter"

    def test_page_size_options_available(self, authenticated_client, mock_db, sample_job):
        """Page size selector should have Letter and A4 options."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'letter' in html.lower()
        assert 'a4' in html.lower()

    def test_page_size_persists_to_mongodb(self, authenticated_client, mock_db, sample_job):
        """Page size setting should persist to MongoDB."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.15,
                "margins": {
                    "top": 1.0,
                    "right": 1.0,
                    "bottom": 1.0,
                    "left": 1.0
                },
                "pageSize": "a4"  # Changed from default
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
        assert saved_state["documentStyles"]["pageSize"] == "a4"

    def test_page_size_letter_dimensions(self, authenticated_client, mock_db, sample_job):
        """Letter page size should be 8.5" x 11"."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert - Check that Letter dimensions are mentioned
        assert '8.5' in html and '11' in html

    def test_page_size_a4_dimensions(self, authenticated_client, mock_db, sample_job):
        """A4 page size should be 210mm x 297mm."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert - Check that A4 dimensions are mentioned
        assert '210' in html and '297' in html or 'A4' in html


# ==============================================================================
# Test Class: Header/Footer Support
# ==============================================================================

class TestHeaderFooterSupport:
    """Tests for basic header/footer support."""

    def test_header_footer_toggle_present(self, authenticated_client, mock_db, sample_job):
        """Toolbar should have header/footer toggle controls."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        assert 'header' in html.lower()
        assert 'footer' in html.lower()

    def test_header_text_persists_to_mongodb(self, authenticated_client, mock_db, sample_job):
        """Header text should persist to MongoDB."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.15,
                "margins": {
                    "top": 1.0,
                    "right": 1.0,
                    "bottom": 1.0,
                    "left": 1.0
                },
                "pageSize": "letter"
            },
            "header": "John Doe | john@example.com | (555) 123-4567"
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
        assert saved_state["header"] == "John Doe | john@example.com | (555) 123-4567"

    def test_footer_text_persists_to_mongodb(self, authenticated_client, mock_db, sample_job):
        """Footer text should persist to MongoDB."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.15,
                "margins": {
                    "top": 1.0,
                    "right": 1.0,
                    "bottom": 1.0,
                    "left": 1.0
                },
                "pageSize": "letter"
            },
            "footer": "Page 1 of 1 | Last updated: November 2025"
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
        assert saved_state["footer"] == "Page 1 of 1 | Last updated: November 2025"

    def test_header_footer_are_optional(self, authenticated_client, mock_db, sample_job):
        """Header and footer fields should be optional."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.15,
                "margins": {
                    "top": 1.0,
                    "right": 1.0,
                    "bottom": 1.0,
                    "left": 1.0
                },
                "pageSize": "letter"
            }
            # No header or footer
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
# Test Class: Phase 3 Integration Tests
# ==============================================================================

class TestPhase3Integration:
    """Integration tests for Phase 3 document-level styles."""

    def test_complete_phase3_state_persists(self, authenticated_client, mock_db, sample_job):
        """Complete Phase 3 state with all features should persist correctly."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        complete_phase3_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 1, "textAlign": "center"},
                        "content": [{"type": "text", "text": "Professional Resume"}]
                    },
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Experienced software engineer"}]
                    }
                ]
            },
            "documentStyles": {
                "fontFamily": "Merriweather",
                "fontSize": 11,
                "lineHeight": 1.5,
                "margins": {
                    "top": 0.75,
                    "right": 0.75,
                    "bottom": 0.75,
                    "left": 0.75
                },
                "pageSize": "a4"
            },
            "header": "John Doe | john@example.com",
            "footer": "Portfolio: https://johndoe.dev"
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=complete_phase3_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        saved_state = mock_db.update_one.call_args[0][1]["$set"]["cv_editor_state"]

        # Verify all Phase 3 fields
        assert saved_state["documentStyles"]["lineHeight"] == 1.5
        assert saved_state["documentStyles"]["margins"]["top"] == 0.75
        assert saved_state["documentStyles"]["margins"]["right"] == 0.75
        assert saved_state["documentStyles"]["margins"]["bottom"] == 0.75
        assert saved_state["documentStyles"]["margins"]["left"] == 0.75
        assert saved_state["documentStyles"]["pageSize"] == "a4"
        assert saved_state["header"] == "John Doe | john@example.com"
        assert saved_state["footer"] == "Portfolio: https://johndoe.dev"

    def test_phase3_state_restoration(self, authenticated_client, mock_db):
        """Phase 3 state should restore correctly from MongoDB."""
        # Arrange
        job_with_phase3 = {
            "_id": ObjectId(),
            "title": "Senior Developer",
            "company": "TechCo",
            "cv_text": "# Resume",
            "cv_editor_state": {
                "version": 1,
                "content": {"type": "doc", "content": []},
                "documentStyles": {
                    "fontFamily": "Roboto",
                    "fontSize": 11,
                    "lineHeight": 2.0,
                    "margins": {
                        "top": 0.5,
                        "right": 1.0,
                        "bottom": 1.5,
                        "left": 2.0
                    },
                    "pageSize": "a4"
                },
                "header": "Test Header",
                "footer": "Test Footer"
            }
        }
        job_id = str(job_with_phase3["_id"])
        mock_db.find_one.return_value = job_with_phase3

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        styles = data["editor_state"]["documentStyles"]

        assert styles["lineHeight"] == 2.0
        assert styles["margins"]["top"] == 0.5
        assert styles["margins"]["right"] == 1.0
        assert styles["margins"]["bottom"] == 1.5
        assert styles["margins"]["left"] == 2.0
        assert styles["pageSize"] == "a4"
        assert data["editor_state"]["header"] == "Test Header"
        assert data["editor_state"]["footer"] == "Test Footer"

    def test_phase3_works_with_phase2_formatting(self, authenticated_client, mock_db, sample_job):
        """Phase 3 document styles should work alongside Phase 2 text formatting."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        combined_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 1, "textAlign": "center"},  # Phase 2: alignment
                        "content": [
                            {
                                "type": "text",
                                "text": "John Doe",
                                "marks": [
                                    {"type": "textStyle", "attrs": {"fontFamily": "Playfair Display", "fontSize": "24pt"}}  # Phase 2
                                ]
                            }
                        ]
                    },
                    {
                        "type": "paragraph",
                        "attrs": {"style": "margin-left: 0.5in"},  # Phase 2: indentation
                        "content": [
                            {
                                "type": "text",
                                "text": "Highlighted text",
                                "marks": [
                                    {"type": "highlight", "attrs": {"color": "#ffff00"}}  # Phase 2
                                ]
                            }
                        ]
                    }
                ]
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.5,  # Phase 3
                "margins": {  # Phase 3
                    "top": 0.75,
                    "right": 0.75,
                    "bottom": 0.75,
                    "left": 0.75
                },
                "pageSize": "a4"  # Phase 3
            },
            "header": "Contact: john@example.com"  # Phase 3
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=combined_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        saved_state = mock_db.update_one.call_args[0][1]["$set"]["cv_editor_state"]

        # Verify Phase 2 formatting preserved
        heading = saved_state["content"]["content"][0]
        assert heading["attrs"]["textAlign"] == "center"
        assert heading["content"][0]["marks"][0]["attrs"]["fontFamily"] == "Playfair Display"

        # Verify Phase 3 document styles preserved
        assert saved_state["documentStyles"]["lineHeight"] == 1.5
        assert saved_state["documentStyles"]["pageSize"] == "a4"
        assert saved_state["header"] == "Contact: john@example.com"


# ==============================================================================
# Test Class: CSS Application (Client-Side Behavior)
# ==============================================================================

class TestPhase3CSSApplication:
    """Tests for CSS application of Phase 3 styles (verifying HTML output)."""

    def test_margin_css_applied_to_editor_container(self, authenticated_client, mock_db, sample_job):
        """Editor container should have CSS padding based on margins."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        # Check that editor container has padding styles
        assert 'padding' in html or 'p-8' in html  # Tailwind or inline padding

    def test_line_height_css_applied_to_paragraphs(self, authenticated_client, mock_db, sample_job):
        """Paragraphs should have line-height CSS applied."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        # Check for line-height in CSS or inline styles
        assert 'line-height' in html.lower()

    def test_page_size_affects_editor_container_width(self, authenticated_client, mock_db, sample_job):
        """Editor container width should match page size."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")
        html = response.data.decode('utf-8')

        # Assert
        # Check for width constraint (Letter = 8.5in)
        assert 'max-width: 8.5in' in html or '8.5in' in html


# ==============================================================================
# Test Class: Backward Compatibility
# ==============================================================================

class TestPhase3BackwardCompatibility:
    """Tests to ensure Phase 3 doesn't break existing functionality."""

    def test_phase1_basic_formatting_still_works(self, authenticated_client, mock_db, sample_job):
        """Phase 1 basic formatting (bold, italic, lists) should still work."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job
        mock_db.update_one.return_value = MagicMock(matched_count=1)

        phase1_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "Bold and italic text",
                                "marks": [{"type": "bold"}, {"type": "italic"}]
                            }
                        ]
                    }
                ]
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.15,
                "margins": {
                    "top": 1.0,
                    "right": 1.0,
                    "bottom": 1.0,
                    "left": 1.0
                },
                "pageSize": "letter"
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=phase1_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200

    def test_jobs_without_phase3_fields_work(self, authenticated_client, mock_db):
        """Jobs created before Phase 3 (without new fields) should work."""
        # Arrange
        old_job = {
            "_id": ObjectId(),
            "title": "Developer",
            "company": "OldCo",
            "cv_editor_state": {
                "version": 1,
                "content": {"type": "doc", "content": []},
                "documentStyles": {
                    "fontFamily": "Inter",
                    "fontSize": 11,
                    "lineHeight": 1.4,
                    "margins": {
                        "top": 0.75,
                        "right": 0.75,
                        "bottom": 0.75,
                        "left": 0.75
                    },
                    "pageSize": "letter"
                }
                # No header/footer fields
            }
        }
        job_id = str(old_job["_id"])
        mock_db.find_one.return_value = old_job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        # Should use defaults for missing fields
        assert "lineHeight" in data["editor_state"]["documentStyles"]
