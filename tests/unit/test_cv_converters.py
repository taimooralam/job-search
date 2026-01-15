"""Tests for CV markdown to TipTap converter bridge.

This module tests the frontend.cv_editor.converters.markdown_to_prosemirror
function which bridges to the existing migrate_cv_text_to_editor_state function.
"""
import pytest
from frontend.cv_editor.converters import markdown_to_prosemirror


class TestMarkdownToProsemirror:
    """Test the bridge function routes to working converter."""

    def test_empty_input(self):
        """Empty string should return valid empty doc structure."""
        result = markdown_to_prosemirror("")
        assert "content" in result
        assert result["content"]["type"] == "doc"
        assert result["content"]["content"] == []

    def test_h1_heading(self):
        """H1 heading (# text) should be converted to level 1 heading node."""
        result = markdown_to_prosemirror("# TAIMOOR ALAM")
        doc_content = result["content"]["content"]
        assert len(doc_content) >= 1
        assert doc_content[0]["type"] == "heading"
        assert doc_content[0]["attrs"]["level"] == 1
        assert doc_content[0]["content"][0]["text"] == "TAIMOOR ALAM"

    def test_h2_heading(self):
        """H2 heading (## text) should be converted to level 2 heading node."""
        result = markdown_to_prosemirror("## EXECUTIVE SUMMARY")
        doc_content = result["content"]["content"]
        assert doc_content[0]["type"] == "heading"
        assert doc_content[0]["attrs"]["level"] == 2

    def test_h3_heading(self):
        """H3 heading (### text) should be converted to level 3 heading node."""
        result = markdown_to_prosemirror("### Sub Section")
        doc_content = result["content"]["content"]
        assert doc_content[0]["type"] == "heading"
        assert doc_content[0]["attrs"]["level"] == 3

    def test_bold_text(self):
        """Bold text (**text**) should have bold mark."""
        result = markdown_to_prosemirror("**Senior Engineer**")
        doc_content = result["content"]["content"]
        text_node = doc_content[0]["content"][0]
        assert text_node["text"] == "Senior Engineer"
        assert {"type": "bold"} in text_node["marks"]

    def test_italic_text(self):
        """Italic text (*text*) should have italic mark."""
        result = markdown_to_prosemirror("*emphasis*")
        doc_content = result["content"]["content"]
        text_node = doc_content[0]["content"][0]
        assert text_node["text"] == "emphasis"
        assert {"type": "italic"} in text_node["marks"]

    def test_bold_italic_text(self):
        """Bold+italic text (***text***) should have both marks."""
        result = markdown_to_prosemirror("***important***")
        doc_content = result["content"]["content"]
        text_node = doc_content[0]["content"][0]
        assert text_node["text"] == "important"
        assert {"type": "bold"} in text_node["marks"]
        assert {"type": "italic"} in text_node["marks"]

    def test_bullet_list(self):
        """Bullet list (- item) should be converted to bulletList node."""
        result = markdown_to_prosemirror("- Item 1\n- Item 2\n- Item 3")
        doc_content = result["content"]["content"]
        assert doc_content[0]["type"] == "bulletList"
        assert len(doc_content[0]["content"]) == 3

    def test_bullet_list_with_unicode(self):
        """Bullet list with unicode bullet (• item) should also work."""
        result = markdown_to_prosemirror("• Item 1\n• Item 2")
        doc_content = result["content"]["content"]
        assert doc_content[0]["type"] == "bulletList"
        assert len(doc_content[0]["content"]) == 2

    def test_includes_document_styles(self):
        """Result should include professional documentStyles."""
        result = markdown_to_prosemirror("# Test")
        assert "documentStyles" in result
        assert result["documentStyles"]["fontFamily"] == "Source Sans 3"
        assert result["documentStyles"]["headingFont"] == "Playfair Display"
        assert result["documentStyles"]["fontSize"] == 11
        assert "colorText" in result["documentStyles"]
        assert "colorAccent" in result["documentStyles"]

    def test_includes_version(self):
        """Result should include version field."""
        result = markdown_to_prosemirror("# Test")
        assert "version" in result
        assert result["version"] == 1

    def test_full_cv_structure(self):
        """Full CV with multiple sections should be parsed correctly."""
        cv_text = """# TAIMOOR ALAM
Senior Software Engineer | Dubai, UAE

## EXECUTIVE SUMMARY
**Experienced engineer** with expertise in Python and cloud.

## SKILLS & EXPERTISE
- Python, FastAPI, Django
- AWS, GCP, Azure
- MongoDB, PostgreSQL"""

        result = markdown_to_prosemirror(cv_text)
        doc_content = result["content"]["content"]

        # Should have multiple elements: heading, paragraph, headings, lists
        assert len(doc_content) >= 5

        # First element should be H1
        assert doc_content[0]["type"] == "heading"
        assert doc_content[0]["attrs"]["level"] == 1
        assert "TAIMOOR ALAM" in doc_content[0]["content"][0]["text"]

    def test_mixed_inline_formatting(self):
        """Mixed inline formatting should be parsed correctly."""
        result = markdown_to_prosemirror("This has **bold** and *italic* text")
        doc_content = result["content"]["content"]
        paragraph_content = doc_content[0]["content"]

        # Should have multiple text nodes
        assert len(paragraph_content) >= 3

        # Find the bold node
        bold_node = next(
            (n for n in paragraph_content if n.get("marks") and {"type": "bold"} in n["marks"]),
            None
        )
        assert bold_node is not None
        assert bold_node["text"] == "bold"

        # Find the italic node
        italic_node = next(
            (n for n in paragraph_content if n.get("marks") and {"type": "italic"} in n["marks"]),
            None
        )
        assert italic_node is not None
        assert italic_node["text"] == "italic"

    def test_blank_lines_separate_paragraphs(self):
        """Blank lines should separate content blocks."""
        result = markdown_to_prosemirror("Paragraph 1\n\nParagraph 2")
        doc_content = result["content"]["content"]
        assert len(doc_content) == 2
        assert doc_content[0]["type"] == "paragraph"
        assert doc_content[1]["type"] == "paragraph"

    def test_all_caps_section_headers(self):
        """ALL CAPS section headers should be recognized as H2."""
        result = markdown_to_prosemirror("PROFESSIONAL EXPERIENCE")
        doc_content = result["content"]["content"]
        # Should be recognized as heading
        assert doc_content[0]["type"] == "heading"
        assert doc_content[0]["attrs"]["level"] == 2


class TestIntegrationWithCvService:
    """Test that the converter produces output compatible with CV generation."""

    def test_output_structure_matches_cv_editor_state(self):
        """Output should match expected cv_editor_state structure."""
        result = markdown_to_prosemirror("# Test CV")

        # Must have these top-level keys
        assert "version" in result
        assert "content" in result
        assert "documentStyles" in result

        # Content must be a valid TipTap doc
        assert result["content"]["type"] == "doc"
        assert "content" in result["content"]

    def test_output_has_margins(self):
        """Output documentStyles should include margins for PDF export."""
        result = markdown_to_prosemirror("# Test")
        margins = result["documentStyles"].get("margins", {})
        assert "top" in margins
        assert "right" in margins
        assert "bottom" in margins
        assert "left" in margins
