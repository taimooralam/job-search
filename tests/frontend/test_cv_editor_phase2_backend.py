"""
Unit tests for CV Rich Text Editor Phase 2 backend functions.

Tests the TipTap JSON to HTML conversion, markdown migration, and API endpoints.
"""

import pytest
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock, patch
import json


class TestTipTapJsonToHtml:
    """Tests for the tiptap_json_to_html function."""

    def test_converts_empty_document(self):
        """Should return empty string for empty document."""
        from app import tiptap_json_to_html

        tiptap_content = {"type": "doc", "content": []}
        result = tiptap_json_to_html(tiptap_content)

        assert result == ""

    def test_converts_simple_paragraph(self):
        """Should convert paragraph with plain text."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert result == "<p>Hello world</p>"

    def test_converts_heading_level_1(self):
        """Should convert h1 heading."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": "Main Title"}]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert result == "<h1>Main Title</h1>"

    def test_converts_heading_level_2(self):
        """Should convert h2 heading."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Section Title"}]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert result == "<h2>Section Title</h2>"

    def test_converts_heading_level_3(self):
        """Should convert h3 heading."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 3},
                    "content": [{"type": "text", "text": "Subsection"}]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert result == "<h3>Subsection</h3>"

    def test_converts_bold_text(self):
        """Should wrap bold text in <strong> tags."""
        from app import tiptap_json_to_html

        tiptap_content = {
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
        result = tiptap_json_to_html(tiptap_content)

        assert result == "<p><strong>Bold text</strong></p>"

    def test_converts_italic_text(self):
        """Should wrap italic text in <em> tags."""
        from app import tiptap_json_to_html

        tiptap_content = {
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
        result = tiptap_json_to_html(tiptap_content)

        assert result == "<p><em>Italic text</em></p>"

    def test_converts_underline_text(self):
        """Should wrap underlined text in <u> tags."""
        from app import tiptap_json_to_html

        tiptap_content = {
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
        result = tiptap_json_to_html(tiptap_content)

        assert result == "<p><u>Underlined text</u></p>"

    def test_converts_multiple_marks(self):
        """Should apply multiple marks (bold + italic)."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Bold and italic",
                            "marks": [{"type": "bold"}, {"type": "italic"}]
                        }
                    ]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert "<strong>" in result
        assert "<em>" in result
        assert "Bold and italic" in result

    def test_converts_font_family(self):
        """Should apply font-family style to text."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Custom font",
                            "marks": [
                                {
                                    "type": "textStyle",
                                    "attrs": {"fontFamily": "Playfair Display"}
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert "font-family: Playfair Display" in result
        assert "Custom font" in result

    def test_converts_font_size(self):
        """Should apply font-size style to text."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Large text",
                            "marks": [
                                {
                                    "type": "textStyle",
                                    "attrs": {"fontSize": "18pt"}
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert "font-size: 18pt" in result
        assert "Large text" in result

    def test_converts_text_color(self):
        """Should apply color style to text."""
        from app import tiptap_json_to_html

        tiptap_content = {
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
        result = tiptap_json_to_html(tiptap_content)

        assert "color: #ff0000" in result
        assert "Red text" in result

    def test_converts_combined_text_styles(self):
        """Should apply multiple textStyle attributes together."""
        from app import tiptap_json_to_html

        tiptap_content = {
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
                                        "fontFamily": "Roboto",
                                        "fontSize": "14pt",
                                        "color": "#0000ff"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert "font-family: Roboto" in result
        assert "font-size: 14pt" in result
        assert "color: #0000ff" in result
        assert "Styled text" in result

    def test_converts_highlight_with_default_color(self):
        """Should apply highlight with default yellow background."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Highlighted",
                            "marks": [{"type": "highlight"}]
                        }
                    ]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert "<mark style='background-color: yellow'>Highlighted</mark>" in result

    def test_converts_highlight_with_custom_color(self):
        """Should apply highlight with custom background color."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Green highlight",
                            "marks": [
                                {
                                    "type": "highlight",
                                    "attrs": {"color": "#00ff00"}
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert "background-color: #00ff00" in result
        assert "Green highlight" in result

    def test_converts_text_align_center(self):
        """Should apply center text alignment to paragraph."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"textAlign": "center"},
                    "content": [{"type": "text", "text": "Centered text"}]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert 'style="text-align: center;"' in result
        assert "Centered text" in result

    def test_converts_text_align_right(self):
        """Should apply right text alignment to paragraph."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"textAlign": "right"},
                    "content": [{"type": "text", "text": "Right-aligned"}]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert 'style="text-align: right;"' in result
        assert "Right-aligned" in result

    def test_converts_text_align_justify(self):
        """Should apply justify text alignment to paragraph."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"textAlign": "justify"},
                    "content": [{"type": "text", "text": "Justified text"}]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert 'style="text-align: justify;"' in result
        assert "Justified text" in result

    def test_converts_text_align_heading(self):
        """Should apply text alignment to heading."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1, "textAlign": "center"},
                    "content": [{"type": "text", "text": "Centered Title"}]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert '<h1 style="text-align: center;">Centered Title</h1>' in result

    def test_converts_bullet_list(self):
        """Should convert bullet list to <ul> with <li> items."""
        from app import tiptap_json_to_html

        tiptap_content = {
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
                                    "content": [{"type": "text", "text": "Item 1"}]
                                }
                            ]
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Item 2"}]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert result == "<ul><li><p>Item 1</p></li><li><p>Item 2</p></li></ul>"

    def test_converts_ordered_list(self):
        """Should convert ordered list to <ol> with <li> items."""
        from app import tiptap_json_to_html

        tiptap_content = {
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
                                    "content": [{"type": "text", "text": "First"}]
                                }
                            ]
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Second"}]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert result == "<ol><li><p>First</p></li><li><p>Second</p></li></ol>"

    def test_converts_hard_break(self):
        """Should convert hard break to <br> tag."""
        from app import tiptap_json_to_html

        tiptap_content = {
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
        result = tiptap_json_to_html(tiptap_content)

        assert result == "<p>Line 1<br>Line 2</p>"

    def test_converts_horizontal_rule(self):
        """Should convert horizontal rule to <hr> tag."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {"type": "horizontalRule"}
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        assert result == "<hr>"

    def test_converts_complex_nested_structure(self):
        """Should handle complex nested structures with mixed formatting."""
        from app import tiptap_json_to_html

        tiptap_content = {
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
                                {"type": "bold"},
                                {
                                    "type": "textStyle",
                                    "attrs": {"fontFamily": "Playfair Display", "fontSize": "24pt"}
                                }
                            ]
                        }
                    ]
                },
                {
                    "type": "paragraph",
                    "attrs": {"textAlign": "justify"},
                    "content": [
                        {"type": "text", "text": "Regular text with "},
                        {
                            "type": "text",
                            "text": "highlighted",
                            "marks": [{"type": "highlight", "attrs": {"color": "#ffff00"}}]
                        },
                        {"type": "text", "text": " and "},
                        {
                            "type": "text",
                            "text": "bold",
                            "marks": [{"type": "bold"}]
                        },
                        {"type": "text", "text": " parts."}
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
                                            "text": "Achievement with emphasis",
                                            "marks": [{"type": "italic"}]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        # Should contain all expected elements
        assert "<h1" in result
        assert "text-align: center" in result
        assert "Playfair Display" in result
        assert "<strong>" in result
        assert "<mark" in result
        assert "background-color: #ffff00" in result
        assert "<ul>" in result
        assert "<li>" in result
        assert "<em>" in result

    def test_handles_invalid_input_none(self):
        """Should return empty string for None input."""
        from app import tiptap_json_to_html

        result = tiptap_json_to_html(None)

        assert result == ""

    def test_handles_invalid_input_empty_dict(self):
        """Should return empty string for empty dict."""
        from app import tiptap_json_to_html

        result = tiptap_json_to_html({})

        assert result == ""

    def test_handles_invalid_input_wrong_type(self):
        """Should return empty string for non-doc type."""
        from app import tiptap_json_to_html

        result = tiptap_json_to_html({"type": "paragraph", "content": []})

        assert result == ""

    def test_handles_unknown_node_types_gracefully(self):
        """Should process children of unknown node types without errors."""
        from app import tiptap_json_to_html

        tiptap_content = {
            "type": "doc",
            "content": [
                {
                    "type": "unknownNodeType",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Nested content"}]
                        }
                    ]
                }
            ]
        }
        result = tiptap_json_to_html(tiptap_content)

        # Should still process nested children
        assert "<p>Nested content</p>" in result


class TestMigrateCvTextToEditorState:
    """Tests for the migrate_cv_text_to_editor_state function."""

    def test_migrates_empty_string(self):
        """Should handle empty string input."""
        from app import migrate_cv_text_to_editor_state

        result = migrate_cv_text_to_editor_state("")

        assert result["version"] == 1
        assert result["content"]["type"] == "doc"
        assert result["content"]["content"] == []

    def test_migrates_heading_level_1(self):
        """Should convert # markdown heading to h1."""
        from app import migrate_cv_text_to_editor_state

        markdown = "# Main Title"
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "heading"
        assert content[0]["attrs"]["level"] == 1
        assert content[0]["content"][0]["text"] == "Main Title"

    def test_migrates_heading_level_2(self):
        """Should convert ## markdown heading to h2."""
        from app import migrate_cv_text_to_editor_state

        markdown = "## Section Title"
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "heading"
        assert content[0]["attrs"]["level"] == 2
        assert content[0]["content"][0]["text"] == "Section Title"

    def test_migrates_heading_level_3(self):
        """Should convert ### markdown heading to h3."""
        from app import migrate_cv_text_to_editor_state

        markdown = "### Subsection"
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "heading"
        assert content[0]["attrs"]["level"] == 3
        assert content[0]["content"][0]["text"] == "Subsection"

    def test_migrates_bullet_list_single_item(self):
        """Should convert single bullet point to bulletList."""
        from app import migrate_cv_text_to_editor_state

        markdown = "- First item"
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "bulletList"
        assert len(content[0]["content"]) == 1
        assert content[0]["content"][0]["type"] == "listItem"
        assert content[0]["content"][0]["content"][0]["content"][0]["text"] == "First item"

    def test_migrates_bullet_list_multiple_items(self):
        """Should group consecutive bullet points into single bulletList."""
        from app import migrate_cv_text_to_editor_state

        markdown = """- First item
- Second item
- Third item"""
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "bulletList"
        assert len(content[0]["content"]) == 3
        assert content[0]["content"][0]["content"][0]["content"][0]["text"] == "First item"
        assert content[0]["content"][1]["content"][0]["content"][0]["text"] == "Second item"
        assert content[0]["content"][2]["content"][0]["content"][0]["text"] == "Third item"

    def test_migrates_bullet_list_separated_by_empty_line(self):
        """Should create separate bulletLists when separated by empty line."""
        from app import migrate_cv_text_to_editor_state

        markdown = """- First item
- Second item

- Third item"""
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert len(content) == 2  # Two separate bullet lists
        assert content[0]["type"] == "bulletList"
        assert len(content[0]["content"]) == 2
        assert content[1]["type"] == "bulletList"
        assert len(content[1]["content"]) == 1

    def test_migrates_regular_paragraph(self):
        """Should convert plain text to paragraph."""
        from app import migrate_cv_text_to_editor_state

        markdown = "This is a regular paragraph."
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "paragraph"
        assert content[0]["content"][0]["text"] == "This is a regular paragraph."

    def test_migrates_multiple_paragraphs(self):
        """Should create separate paragraphs for each non-empty line."""
        from app import migrate_cv_text_to_editor_state

        markdown = """First paragraph.
Second paragraph.
Third paragraph."""
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert len(content) == 3
        assert all(item["type"] == "paragraph" for item in content)
        assert content[0]["content"][0]["text"] == "First paragraph."
        assert content[1]["content"][0]["text"] == "Second paragraph."
        assert content[2]["content"][0]["text"] == "Third paragraph."

    def test_migrates_mixed_content(self):
        """Should handle mixed headings, lists, and paragraphs."""
        from app import migrate_cv_text_to_editor_state

        markdown = """# John Doe

Software Engineer

## Experience

- 5 years Python development
- 3 years FastAPI experience

Passionate about building scalable systems."""
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert len(content) == 5
        assert content[0]["type"] == "heading"
        assert content[0]["attrs"]["level"] == 1
        assert content[1]["type"] == "paragraph"
        assert content[2]["type"] == "heading"
        assert content[2]["attrs"]["level"] == 2
        assert content[3]["type"] == "bulletList"
        assert len(content[3]["content"]) == 2
        assert content[4]["type"] == "paragraph"

    def test_migrates_strips_whitespace(self):
        """Should strip leading/trailing whitespace from lines."""
        from app import migrate_cv_text_to_editor_state

        markdown = "   # Heading with spaces   "
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert content[0]["content"][0]["text"] == "Heading with spaces"

    def test_migrates_empty_lines_do_not_create_content(self):
        """Should skip empty lines without creating empty paragraphs."""
        from app import migrate_cv_text_to_editor_state

        markdown = """First paragraph


Second paragraph"""
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert len(content) == 2
        assert content[0]["content"][0]["text"] == "First paragraph"
        assert content[1]["content"][0]["text"] == "Second paragraph"

    def test_includes_default_document_styles(self):
        """Should include default documentStyles in output."""
        from app import migrate_cv_text_to_editor_state

        markdown = "# CV"
        result = migrate_cv_text_to_editor_state(markdown)

        assert "documentStyles" in result
        styles = result["documentStyles"]
        assert styles["fontFamily"] == "Inter"
        assert styles["fontSize"] == 11
        assert styles["lineHeight"] == 1.15  # Phase 3 default: standard resume spacing
        assert styles["pageSize"] == "letter"
        assert "margins" in styles
        assert styles["margins"]["top"] == 1.0  # Phase 3 default: 1-inch margins

    def test_migrates_heading_not_mistaken_for_h2(self):
        """Should not mistake # for ## due to startswith logic."""
        from app import migrate_cv_text_to_editor_state

        markdown = "# Level 1"
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert content[0]["attrs"]["level"] == 1

    def test_migrates_heading_with_extra_hashes(self):
        """Should correctly identify heading levels with multiple #."""
        from app import migrate_cv_text_to_editor_state

        markdown = "### Level 3 Heading"
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert content[0]["type"] == "heading"
        assert content[0]["attrs"]["level"] == 3
        assert content[0]["content"][0]["text"] == "Level 3 Heading"

    def test_migrates_list_followed_by_heading(self):
        """Should properly close list when heading appears."""
        from app import migrate_cv_text_to_editor_state

        markdown = """- Item 1
- Item 2
## New Section"""
        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "bulletList"
        assert len(content[0]["content"]) == 2
        assert content[1]["type"] == "heading"
        assert content[1]["attrs"]["level"] == 2


class TestCvEditorApiEndpoints:
    """Tests for CV editor API endpoints."""

    def test_get_cv_editor_state_with_existing_state(self, authenticated_client, mock_db, sample_job_with_editor_state):
        """Should return existing editor state from database."""
        # Setup mock
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Make request
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert response
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "editor_state" in data
        assert data["editor_state"]["version"] == 1
        assert data["editor_state"]["content"]["type"] == "doc"

    def test_get_cv_editor_state_migrates_from_cv_text(self, authenticated_client, mock_db, sample_job):
        """Should migrate from cv_text markdown when no editor state exists."""
        # Setup mock
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Make request
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert response
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "editor_state" in data

        # Should have migrated markdown to TipTap structure
        content = data["editor_state"]["content"]["content"]
        assert len(content) > 0

        # Note: GET doesn't persist the migration to avoid unnecessary writes
        # Migration happens on-demand and is cheap
        # Persistence happens when user saves via PUT endpoint
        mock_db.update_one.assert_not_called()

    def test_get_cv_editor_state_returns_default_for_empty_job(self, authenticated_client, mock_db):
        """Should return default empty state when job has no cv_text."""
        # Setup mock for job with no cv_text or editor_state
        job_id = str(ObjectId())
        mock_db.find_one.return_value = {
            "_id": ObjectId(job_id),
            "title": "Test Job"
        }

        # Make request
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert response
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["editor_state"]["content"]["content"] == []
        assert "documentStyles" in data["editor_state"]

    def test_get_cv_editor_state_invalid_job_id(self, authenticated_client, mock_db):
        """Should return 400 for invalid ObjectId format."""
        response = authenticated_client.get("/api/jobs/invalid-id/cv-editor")

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "Invalid job ID" in data["error"]

    def test_get_cv_editor_state_job_not_found(self, authenticated_client, mock_db):
        """Should return 404 when job doesn't exist."""
        # Setup mock to return None (job not found)
        job_id = str(ObjectId())
        mock_db.find_one.return_value = None

        # Make request
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert response
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data
        assert "not found" in data["error"].lower()

    def test_get_cv_editor_state_requires_authentication(self, client):
        """Should require authentication to access endpoint."""
        job_id = str(ObjectId())
        response = client.get(f"/api/jobs/{job_id}/cv-editor")

        # Should redirect to login or return 401
        assert response.status_code in [302, 401]

    def test_put_cv_editor_state_saves_successfully(self, authenticated_client, mock_db):
        """Should save editor state and convert to HTML."""
        # Setup mock
        job_id = str(ObjectId())
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        # Prepare request data
        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 1},
                        "content": [{"type": "text", "text": "Updated CV"}]
                    }
                ]
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11
            }
        }

        # Make request
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert response
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "savedAt" in data

        # Verify update_one was called
        mock_db.update_one.assert_called_once()

        # Verify the update contains cv_editor_state and cv_text
        call_args = mock_db.update_one.call_args
        update_data = call_args[0][1]["$set"]
        assert "cv_editor_state" in update_data
        assert "cv_text" in update_data
        assert "updatedAt" in update_data

        # Verify HTML conversion occurred
        assert "<h1>Updated CV</h1>" in update_data["cv_text"]

    def test_put_cv_editor_state_invalid_job_id(self, authenticated_client, mock_db):
        """Should return 400 for invalid ObjectId format."""
        response = authenticated_client.put(
            "/api/jobs/invalid-id/cv-editor",
            json={"content": {"type": "doc", "content": []}},
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_put_cv_editor_state_missing_content(self, authenticated_client, mock_db):
        """Should return 400 when content is missing from request."""
        job_id = str(ObjectId())

        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json={"version": 1},
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "Missing content" in data["error"]

    def test_put_cv_editor_state_job_not_found(self, authenticated_client, mock_db):
        """Should return 404 when job doesn't exist."""
        # Setup mock to return matched_count = 0
        job_id = str(ObjectId())
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_db.update_one.return_value = mock_result

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {"fontFamily": "Inter"}
        }

        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data

    def test_put_cv_editor_state_requires_authentication(self, client):
        """Should require authentication to save editor state."""
        job_id = str(ObjectId())

        response = client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json={"content": {"type": "doc", "content": []}},
            content_type="application/json"
        )

        # Should redirect to login or return 401
        assert response.status_code in [302, 401]

    def test_put_cv_editor_state_with_phase2_formatting(self, authenticated_client, mock_db):
        """Should save Phase 2 formatted content with fonts, alignment, highlights."""
        # Setup mock
        job_id = str(ObjectId())
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        # Phase 2 formatted content
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
                                            "fontSize": "22pt"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "paragraph",
                        "attrs": {"textAlign": "justify"},
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
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11
            }
        }

        # Make request
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert response
        assert response.status_code == 200

        # Verify HTML contains Phase 2 formatting
        call_args = mock_db.update_one.call_args
        html = call_args[0][1]["$set"]["cv_text"]

        assert "text-align: center" in html
        assert "Playfair Display" in html
        assert "22pt" in html
        assert "background-color: #ffff00" in html
        assert "text-align: justify" in html
