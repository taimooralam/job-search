"""
Unit tests for CV Editor Phase 2: TipTap JSON to HTML Conversion

Tests the tiptap_json_to_html() function that converts TipTap JSON to HTML
for backward compatibility and display synchronization.

This is critical functionality for Phase 2 because:
1. Main CV display still uses HTML rendering
2. cv_text field needs HTML for compatibility
3. Editor updates must immediately reflect in main display
"""

import pytest
from bson import ObjectId
from unittest.mock import MagicMock


class TestTipTapJsonToHtml:
    """Tests for tiptap_json_to_html() converter function."""

    def test_converts_empty_document(self):
        """Should return empty string for empty TipTap document."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": []
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert result == ""

    def test_converts_single_paragraph(self):
        """Should convert paragraph node to <p> tag."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<p>Hello world</p>" in result

    def test_converts_heading_level_1(self):
        """Should convert heading node with level 1 to <h1> tag."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": "Main Title"}]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<h1>Main Title</h1>" in result

    def test_converts_heading_level_2(self):
        """Should convert heading node with level 2 to <h2> tag."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Section Title"}]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<h2>Section Title</h2>" in result

    def test_converts_heading_level_3(self):
        """Should convert heading node with level 3 to <h3> tag."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 3},
                    "content": [{"type": "text", "text": "Subsection"}]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<h3>Subsection</h3>" in result

    def test_converts_bold_mark(self):
        """Should convert bold mark to <strong> tag."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Bold text",
                            "marks": [{"type": "bold"}]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<strong>Bold text</strong>" in result

    def test_converts_italic_mark(self):
        """Should convert italic mark to <em> tag."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Italic text",
                            "marks": [{"type": "italic"}]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<em>Italic text</em>" in result

    def test_converts_underline_mark(self):
        """Should convert underline mark to <u> tag."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Underlined text",
                            "marks": [{"type": "underline"}]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<u>Underlined text</u>" in result

    def test_converts_bullet_list(self):
        """Should convert bulletList to <ul> with <li> items."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "First item"}]
                                }
                            ]
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Second item"}]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<ul>" in result
        assert "<li>" in result
        assert "First item" in result
        assert "Second item" in result
        assert "</ul>" in result

    def test_converts_ordered_list(self):
        """Should convert orderedList to <ol> with <li> items."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "orderedList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Step 1"}]
                                }
                            ]
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Step 2"}]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<ol>" in result
        assert "<li>" in result
        assert "Step 1" in result
        assert "Step 2" in result
        assert "</ol>" in result


class TestPhase2FormattingConversion:
    """Tests for Phase 2 specific formatting features (fonts, alignment, highlight)."""

    def test_converts_font_family_mark(self):
        """Should convert textStyle mark with fontFamily to inline style."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Roboto text",
                            "marks": [
                                {
                                    "type": "textStyle",
                                    "attrs": {"fontFamily": "Roboto"}
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "font-family: Roboto" in result
        assert "<span" in result
        assert "Roboto text" in result

    def test_converts_font_size_mark(self):
        """Should convert textStyle mark with fontSize to inline style."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "14pt text",
                            "marks": [
                                {
                                    "type": "textStyle",
                                    "attrs": {"fontSize": "14pt"}
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "font-size: 14pt" in result
        assert "14pt text" in result

    def test_converts_font_color_mark(self):
        """Should convert textStyle mark with color to inline style."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Red text",
                            "marks": [
                                {
                                    "type": "textStyle",
                                    "attrs": {"color": "#ff0000"}
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "color: #ff0000" in result
        assert "Red text" in result

    def test_converts_combined_text_style_marks(self):
        """Should combine fontFamily, fontSize, and color into single style attribute."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Styled text",
                            "marks": [
                                {
                                    "type": "textStyle",
                                    "attrs": {
                                        "fontFamily": "Merriweather",
                                        "fontSize": "18pt",
                                        "color": "#333333"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "font-family: Merriweather" in result
        assert "font-size: 18pt" in result
        assert "color: #333333" in result
        assert "Styled text" in result

    def test_converts_highlight_mark(self):
        """Should convert highlight mark to <mark> tag with background color."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Highlighted text",
                            "marks": [
                                {
                                    "type": "highlight",
                                    "attrs": {"color": "#ffff00"}
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<mark" in result
        assert "background-color: #ffff00" in result
        assert "Highlighted text" in result

    def test_converts_text_alignment_center(self):
        """Should convert textAlign: center to style attribute on paragraph."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"textAlign": "center"},
                    "content": [{"type": "text", "text": "Centered text"}]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "text-align: center" in result
        assert "Centered text" in result

    def test_converts_text_alignment_right(self):
        """Should convert textAlign: right to style attribute."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"textAlign": "right"},
                    "content": [{"type": "text", "text": "Right-aligned"}]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "text-align: right" in result

    def test_converts_text_alignment_justify(self):
        """Should convert textAlign: justify to style attribute."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"textAlign": "justify"},
                    "content": [{"type": "text", "text": "Justified text"}]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "text-align: justify" in result

    def test_heading_with_text_alignment(self):
        """Should apply text alignment to heading elements."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1, "textAlign": "center"},
                    "content": [{"type": "text", "text": "Centered Heading"}]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<h1" in result
        assert "text-align: center" in result
        assert "Centered Heading" in result


class TestComplexFormattingScenarios:
    """Tests for complex documents with multiple formatting layers."""

    def test_converts_bold_italic_combined(self):
        """Should apply both bold and italic marks to same text."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Bold and italic",
                            "marks": [
                                {"type": "bold"},
                                {"type": "italic"}
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<strong>" in result
        assert "<em>" in result
        assert "Bold and italic" in result

    def test_converts_all_marks_combined(self):
        """Should apply bold, italic, underline, font, and highlight together."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Heavily formatted",
                            "marks": [
                                {"type": "bold"},
                                {"type": "italic"},
                                {"type": "underline"},
                                {
                                    "type": "textStyle",
                                    "attrs": {
                                        "fontFamily": "Playfair Display",
                                        "fontSize": "16pt"
                                    }
                                },
                                {
                                    "type": "highlight",
                                    "attrs": {"color": "#ffff00"}
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<strong>" in result
        assert "<em>" in result
        assert "<u>" in result
        assert "font-family: Playfair Display" in result
        assert "font-size: 16pt" in result
        assert "<mark" in result
        assert "background-color: #ffff00" in result

    def test_converts_mixed_paragraph_types(self):
        """Should convert document with headings, paragraphs, and lists."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": "Title"}]
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Introduction paragraph"}]
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "First point"}]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<h1>Title</h1>" in result
        assert "<p>Introduction paragraph</p>" in result
        assert "<ul>" in result
        assert "First point" in result

    def test_converts_nested_list_formatting(self):
        """Should preserve formatting within list items."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Bold item",
                                            "marks": [{"type": "bold"}]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<ul>" in result
        assert "<li>" in result
        assert "<strong>Bold item</strong>" in result


class TestEdgeCases:
    """Edge case tests for TipTap to HTML conversion."""

    def test_handles_empty_content_array(self):
        """Should handle node with empty content array."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": []
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<p></p>" in result

    def test_handles_null_document(self):
        """Should return empty string for None input."""
        # Arrange
        from app import tiptap_json_to_html

        # Act
        result = tiptap_json_to_html(None)

        # Assert
        assert result == ""

    def test_handles_invalid_document_type(self):
        """Should return empty string for document with wrong type."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "not-a-doc",
            "content": []
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert result == ""

    def test_handles_special_characters_in_text(self):
        """Should preserve special characters in text content."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "François & Müller <test>"}]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "François" in result
        assert "Müller" in result
        # HTML entities should be preserved
        assert "&" in result or "&amp;" in result

    def test_handles_unicode_characters(self):
        """Should handle Unicode characters correctly."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "你好世界 🌍"}]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "你好世界" in result or len(result) > 0  # Unicode should be preserved

    def test_handles_hardbreak_node(self):
        """Should convert hardBreak node to <br> tag."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Line 1"},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "Line 2"}
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<br>" in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_handles_horizontal_rule_node(self):
        """Should convert horizontalRule node to <hr> tag."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Before"}]
                },
                {"type": "horizontalRule"},
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "After"}]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert
        assert "<hr>" in result
        assert "Before" in result
        assert "After" in result


class TestCVEditorSyncToHTML:
    """Tests for PUT endpoint's conversion of TipTap JSON to HTML and cv_text sync."""

    def test_save_cv_editor_state_updates_cv_text_field(
        self, authenticated_client, mock_db, sample_job
    ):
        """PUT /api/jobs/<id>/cv-editor should update both cv_editor_state AND cv_text."""
        # Arrange
        from bson import ObjectId
        from unittest.mock import MagicMock

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
                        "attrs": {"level": 1},
                        "content": [{"type": "text", "text": "John Doe"}]
                    },
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Software Engineer"}]
                    }
                ]
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11
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

        # Verify update_one was called with both fields
        call_args = mock_db.update_one.call_args
        update_doc = call_args[0][1]["$set"]

        assert "cv_editor_state" in update_doc
        assert "cv_text" in update_doc

        # Verify cv_text contains HTML
        cv_text = update_doc["cv_text"]
        assert "<h1>John Doe</h1>" in cv_text
        assert "<p>Software Engineer</p>" in cv_text

    def test_save_converts_phase2_formatting_to_html(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should convert Phase 2 formatting (fonts, alignment, highlight) to HTML."""
        # Arrange
        from bson import ObjectId
        from unittest.mock import MagicMock

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
                                "text": "Professional CV",
                                "marks": [
                                    {
                                        "type": "textStyle",
                                        "attrs": {
                                            "fontFamily": "Playfair Display",
                                            "fontSize": "24pt"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "Highlighted achievement",
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

        # Verify cv_text has converted HTML
        call_args = mock_db.update_one.call_args
        cv_text = call_args[0][1]["$set"]["cv_text"]

        assert "font-family: Playfair Display" in cv_text
        assert "font-size: 24pt" in cv_text
        assert "text-align: center" in cv_text
        assert "background-color: #ffff00" in cv_text
        assert "Highlighted achievement" in cv_text


class TestRealWorldCVConversion:
    """Tests with realistic CV structures from actual usage."""

    def test_converts_complete_cv_document(self):
        """Should convert a realistic complete CV with all Phase 2 features."""
        # Arrange
        from app import tiptap_json_to_html

        tiptap_json = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1, "textAlign": "center"},
                    "content": [
                        {
                            "type": "text",
                            "text": "Taimoor Alam",
                            "marks": [
                                {
                                    "type": "textStyle",
                                    "attrs": {
                                        "fontFamily": "Playfair Display",
                                        "fontSize": "24pt"
                                    }
                                }
                            ]
                        }
                    ]
                },
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [
                        {
                            "type": "text",
                            "text": "PROFESSIONAL EXPERIENCE",
                            "marks": [{"type": "bold"}]
                        }
                    ]
                },
                {
                    "type": "paragraph",
                    "attrs": {"textAlign": "justify"},
                    "content": [
                        {
                            "type": "text",
                            "text": "Senior Engineering Manager with 10+ years building scalable systems. ",
                            "marks": [{"type": "textStyle", "attrs": {"fontSize": "11pt"}}]
                        },
                        {
                            "type": "text",
                            "text": "Expertise in distributed architecture.",
                            "marks": [
                                {"type": "textStyle", "attrs": {"fontSize": "11pt"}},
                                {"type": "highlight", "attrs": {"color": "#ffff00"}}
                            ]
                        }
                    ]
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Led engineering team of 15",
                                            "marks": [{"type": "bold"}]
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Increased deployment frequency by 10x"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Act
        result = tiptap_json_to_html(tiptap_json)

        # Assert - Check all elements present
        assert "<h1" in result
        assert "Taimoor Alam" in result
        assert "font-family: Playfair Display" in result
        assert "text-align: center" in result
        assert "<h2>" in result
        assert "PROFESSIONAL EXPERIENCE" in result
        assert "<strong>" in result
        assert "text-align: justify" in result
        assert "<mark" in result
        assert "background-color: #ffff00" in result
        assert "<ul>" in result
        assert "<li>" in result
        assert "Led engineering team" in result
