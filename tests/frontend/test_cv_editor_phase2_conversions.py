"""
Tests for CV Editor Phase 2 - Conversion Functions

Tests the TipTap JSON to HTML converter and Markdown to TipTap JSON migration.
"""

import pytest
import sys
import os

# Add frontend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../frontend'))

from app import tiptap_json_to_html, migrate_cv_text_to_editor_state


class TestTipTapJSONToHTML:
    """Test TipTap JSON to HTML conversion."""

    def test_heading_level_1(self):
        """Test h1 heading conversion."""
        tiptap_json = {
            "type": "doc",
            "content": [{
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": "Test Heading"}]
            }]
        }

        html = tiptap_json_to_html(tiptap_json)

        assert "<h1>Test Heading</h1>" in html

    def test_heading_level_2(self):
        """Test h2 heading conversion."""
        tiptap_json = {
            "type": "doc",
            "content": [{
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Subheading"}]
            }]
        }

        html = tiptap_json_to_html(tiptap_json)

        assert "<h2>Subheading</h2>" in html

    def test_paragraph(self):
        """Test paragraph conversion."""
        tiptap_json = {
            "type": "doc",
            "content": [{
                "type": "paragraph",
                "content": [{"type": "text", "text": "Simple paragraph."}]
            }]
        }

        html = tiptap_json_to_html(tiptap_json)

        assert "<p>Simple paragraph.</p>" in html

    def test_bold_text(self):
        """Test bold mark conversion."""
        tiptap_json = {
            "type": "doc",
            "content": [{
                "type": "paragraph",
                "content": [{
                    "type": "text",
                    "text": "Bold text",
                    "marks": [{"type": "bold"}]
                }]
            }]
        }

        html = tiptap_json_to_html(tiptap_json)

        assert "<strong>Bold text</strong>" in html

    def test_italic_text(self):
        """Test italic mark conversion."""
        tiptap_json = {
            "type": "doc",
            "content": [{
                "type": "paragraph",
                "content": [{
                    "type": "text",
                    "text": "Italic text",
                    "marks": [{"type": "italic"}]
                }]
            }]
        }

        html = tiptap_json_to_html(tiptap_json)

        assert "<em>Italic text</em>" in html

    def test_underline_text(self):
        """Test underline mark conversion."""
        tiptap_json = {
            "type": "doc",
            "content": [{
                "type": "paragraph",
                "content": [{
                    "type": "text",
                    "text": "Underlined text",
                    "marks": [{"type": "underline"}]
                }]
            }]
        }

        html = tiptap_json_to_html(tiptap_json)

        assert "<u>Underlined text</u>" in html

    def test_bullet_list(self):
        """Test bullet list conversion."""
        tiptap_json = {
            "type": "doc",
            "content": [{
                "type": "bulletList",
                "content": [{
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Item 1"}]
                    }]
                }]
            }]
        }

        html = tiptap_json_to_html(tiptap_json)

        assert "<ul>" in html
        assert "<li>" in html
        assert "Item 1" in html

    def test_ordered_list(self):
        """Test ordered list conversion."""
        tiptap_json = {
            "type": "doc",
            "content": [{
                "type": "orderedList",
                "content": [{
                    "type": "listItem",
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "First"}]
                    }]
                }]
            }]
        }

        html = tiptap_json_to_html(tiptap_json)

        assert "<ol>" in html
        assert "<li>" in html
        assert "First" in html

    def test_text_alignment_center(self):
        """Test centered text alignment."""
        tiptap_json = {
            "type": "doc",
            "content": [{
                "type": "paragraph",
                "attrs": {"textAlign": "center"},
                "content": [{"type": "text", "text": "Centered"}]
            }]
        }

        html = tiptap_json_to_html(tiptap_json)

        assert 'text-align: center' in html
        assert "Centered" in html

    def test_highlight_mark(self):
        """Test highlight/mark conversion."""
        tiptap_json = {
            "type": "doc",
            "content": [{
                "type": "paragraph",
                "content": [{
                    "type": "text",
                    "text": "Highlighted",
                    "marks": [{
                        "type": "highlight",
                        "attrs": {"color": "yellow"}
                    }]
                }]
            }]
        }

        html = tiptap_json_to_html(tiptap_json)

        assert "<mark" in html
        assert "yellow" in html
        assert "Highlighted" in html

    def test_empty_document(self):
        """Test empty TipTap document returns empty string."""
        tiptap_json = {
            "type": "doc",
            "content": []
        }

        html = tiptap_json_to_html(tiptap_json)

        assert html == ""

    def test_invalid_document_type(self):
        """Test invalid document type returns empty string."""
        tiptap_json = {
            "type": "invalid",
            "content": []
        }

        html = tiptap_json_to_html(tiptap_json)

        assert html == ""

    def test_mixed_formatting(self):
        """Test paragraph with bold and italic together."""
        tiptap_json = {
            "type": "doc",
            "content": [{
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Normal "},
                    {
                        "type": "text",
                        "text": "bold",
                        "marks": [{"type": "bold"}]
                    },
                    {"type": "text", "text": " and "},
                    {
                        "type": "text",
                        "text": "italic",
                        "marks": [{"type": "italic"}]
                    }
                ]
            }]
        }

        html = tiptap_json_to_html(tiptap_json)

        assert "Normal" in html
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html


class TestMarkdownMigration:
    """Test Markdown to TipTap JSON migration."""

    def test_single_h1_heading(self):
        """Test # heading migration."""
        markdown = "# Main Heading"

        result = migrate_cv_text_to_editor_state(markdown)

        assert result["content"]["type"] == "doc"
        assert len(result["content"]["content"]) == 1
        assert result["content"]["content"][0]["type"] == "heading"
        assert result["content"]["content"][0]["attrs"]["level"] == 1
        assert result["content"]["content"][0]["content"][0]["text"] == "Main Heading"

    def test_h2_heading(self):
        """Test ## heading migration."""
        markdown = "## Subheading"

        result = migrate_cv_text_to_editor_state(markdown)

        assert result["content"]["content"][0]["type"] == "heading"
        assert result["content"]["content"][0]["attrs"]["level"] == 2
        assert result["content"]["content"][0]["content"][0]["text"] == "Subheading"

    def test_h3_heading(self):
        """Test ### heading migration."""
        markdown = "### Minor Heading"

        result = migrate_cv_text_to_editor_state(markdown)

        assert result["content"]["content"][0]["type"] == "heading"
        assert result["content"]["content"][0]["attrs"]["level"] == 3

    def test_single_paragraph(self):
        """Test plain paragraph migration."""
        markdown = "This is a paragraph."

        result = migrate_cv_text_to_editor_state(markdown)

        assert result["content"]["content"][0]["type"] == "paragraph"
        assert result["content"]["content"][0]["content"][0]["text"] == "This is a paragraph."

    def test_bullet_list(self):
        """Test - bullet list migration."""
        markdown = "- Item 1\n- Item 2\n- Item 3"

        result = migrate_cv_text_to_editor_state(markdown)

        assert result["content"]["content"][0]["type"] == "bulletList"
        assert len(result["content"]["content"][0]["content"]) == 3
        assert result["content"]["content"][0]["content"][0]["type"] == "listItem"

    def test_multiple_headings(self):
        """Test multiple headings at different levels."""
        markdown = "# Title\n## Section\n### Subsection"

        result = migrate_cv_text_to_editor_state(markdown)

        assert len(result["content"]["content"]) == 3
        assert result["content"]["content"][0]["attrs"]["level"] == 1
        assert result["content"]["content"][1]["attrs"]["level"] == 2
        assert result["content"]["content"][2]["attrs"]["level"] == 3

    def test_mixed_content(self):
        """Test headings, paragraphs, and lists together."""
        markdown = "# CV\nExperience paragraph\n- Skill 1\n- Skill 2"

        result = migrate_cv_text_to_editor_state(markdown)

        content = result["content"]["content"]
        assert content[0]["type"] == "heading"
        assert content[1]["type"] == "paragraph"
        assert content[2]["type"] == "bulletList"

    def test_empty_lines_ignored(self):
        """Test empty lines don't create empty nodes."""
        markdown = "# Heading\n\nParagraph"

        result = migrate_cv_text_to_editor_state(markdown)

        # Should have 2 items: heading and paragraph (empty line ignored)
        assert len(result["content"]["content"]) == 2

    def test_document_structure(self):
        """Test migrated document has correct structure."""
        markdown = "# Test"

        result = migrate_cv_text_to_editor_state(markdown)

        assert "version" in result
        assert result["version"] == 1
        assert "content" in result
        assert "documentStyles" in result
        assert result["documentStyles"]["fontFamily"] == "Source Sans 3"
        assert result["documentStyles"]["fontSize"] == 11
