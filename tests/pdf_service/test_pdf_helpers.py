"""
Unit tests for PDF helper functions.

Tests TipTap JSON to HTML conversion and HTML template building.
"""

import pytest
from pdf_service.pdf_helpers import (
    sanitize_for_path,
    tiptap_json_to_html,
    build_pdf_html_template
)


class TestSanitizeForPath:
    """Tests for sanitize_for_path function."""

    def test_sanitize_removes_special_chars(self):
        """Test that special characters are replaced with underscores."""
        assert sanitize_for_path("Test & Co.") == "Test___Co_"
        assert sanitize_for_path("Director (Engineering)") == "Director__Engineering_"

    def test_sanitize_replaces_spaces(self):
        """Test that spaces are replaced with underscores."""
        assert sanitize_for_path("Senior Software Engineer") == "Senior_Software_Engineer"

    def test_sanitize_preserves_alphanumeric(self):
        """Test that alphanumeric characters are preserved."""
        assert sanitize_for_path("Test123ABC") == "Test123ABC"

    def test_sanitize_preserves_hyphens(self):
        """Test that hyphens are preserved."""
        assert sanitize_for_path("Test-Company") == "Test-Company"

    def test_sanitize_empty_string(self):
        """Test sanitization of empty string."""
        assert sanitize_for_path("") == ""


class TestTipTapJSONToHTML:
    """Tests for tiptap_json_to_html function."""

    def test_empty_document(self):
        """Test conversion of empty TipTap document."""
        doc = {"type": "doc", "content": []}
        assert tiptap_json_to_html(doc) == ""

    def test_invalid_document_type(self):
        """Test that invalid document type returns empty string."""
        doc = {"type": "invalid", "content": []}
        assert tiptap_json_to_html(doc) == ""

    def test_missing_type(self):
        """Test that missing type returns empty string."""
        doc = {"content": []}
        assert tiptap_json_to_html(doc) == ""

    def test_paragraph_conversion(self):
        """Test conversion of paragraph nodes."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello World"}
                    ]
                }
            ]
        }
        html = tiptap_json_to_html(doc)
        assert "<p>Hello World</p>" in html

    def test_heading_conversion(self):
        """Test conversion of heading nodes."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [
                        {"type": "text", "text": "Title"}
                    ]
                }
            ]
        }
        html = tiptap_json_to_html(doc)
        assert "<h1>Title</h1>" in html

    def test_bold_text(self):
        """Test conversion of bold text."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Bold",
                            "marks": [{"type": "bold"}]
                        }
                    ]
                }
            ]
        }
        html = tiptap_json_to_html(doc)
        assert "<strong>Bold</strong>" in html

    def test_italic_text(self):
        """Test conversion of italic text."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Italic",
                            "marks": [{"type": "italic"}]
                        }
                    ]
                }
            ]
        }
        html = tiptap_json_to_html(doc)
        assert "<em>Italic</em>" in html

    def test_underline_text(self):
        """Test conversion of underlined text."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Underline",
                            "marks": [{"type": "underline"}]
                        }
                    ]
                }
            ]
        }
        html = tiptap_json_to_html(doc)
        assert "<u>Underline</u>" in html

    def test_bullet_list(self):
        """Test conversion of bullet lists."""
        doc = {
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
        html = tiptap_json_to_html(doc)
        assert "<ul>" in html
        assert "<li>" in html
        assert "Item 1" in html
        assert "Item 2" in html

    def test_ordered_list(self):
        """Test conversion of ordered lists."""
        doc = {
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
                        }
                    ]
                }
            ]
        }
        html = tiptap_json_to_html(doc)
        assert "<ol>" in html
        assert "<li>" in html

    def test_hard_break(self):
        """Test conversion of hard breaks."""
        doc = {
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
        html = tiptap_json_to_html(doc)
        assert "Line 1<br>Line 2" in html

    def test_horizontal_rule(self):
        """Test conversion of horizontal rules."""
        doc = {
            "type": "doc",
            "content": [
                {"type": "horizontalRule"}
            ]
        }
        html = tiptap_json_to_html(doc)
        assert "<hr>" in html

    def test_text_alignment(self):
        """Test conversion of text alignment."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "attrs": {"textAlign": "center"},
                    "content": [{"type": "text", "text": "Centered"}]
                }
            ]
        }
        html = tiptap_json_to_html(doc)
        assert 'text-align: center' in html

    def test_text_style_with_font_family(self):
        """Test conversion of custom font family."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Custom Font",
                            "marks": [
                                {
                                    "type": "textStyle",
                                    "attrs": {"fontFamily": "Courier New"}
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        html = tiptap_json_to_html(doc)
        assert "font-family: Courier New" in html

    def test_highlight(self):
        """Test conversion of highlighted text."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "Highlighted",
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
        html = tiptap_json_to_html(doc)
        assert "<mark" in html
        assert "background-color: #ffff00" in html

    def test_max_depth_protection(self):
        """Test that deeply nested documents are protected."""
        # Create a document with depth > max_depth
        # The function should handle this gracefully
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Test"}]
                }
            ]
        }
        html = tiptap_json_to_html(doc, max_depth=1)
        # Should still produce output, just truncate deep nesting
        assert len(html) > 0


class TestBuildPDFHTMLTemplate:
    """Tests for build_pdf_html_template function."""

    def test_basic_template_structure(self):
        """Test that template contains required HTML structure."""
        html = build_pdf_html_template(
            content_html="<p>Test</p>",
            font_family="Inter",
            font_size=11,
            line_height=1.15
        )

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "<p>Test</p>" in html

    def test_google_fonts_link(self):
        """Test that Google Fonts link is included."""
        html = build_pdf_html_template(
            content_html="<p>Test</p>",
            font_family="Merriweather",
            font_size=11,
            line_height=1.15
        )

        assert "fonts.googleapis.com" in html
        assert "Merriweather" in html

    def test_page_size_letter(self):
        """Test that Letter page size is set correctly."""
        html = build_pdf_html_template(
            content_html="<p>Test</p>",
            font_family="Inter",
            font_size=11,
            line_height=1.15,
            page_size="letter"
        )

        assert "size: Letter" in html

    def test_page_size_a4(self):
        """Test that A4 page size is set correctly."""
        html = build_pdf_html_template(
            content_html="<p>Test</p>",
            font_family="Inter",
            font_size=11,
            line_height=1.15,
            page_size="a4"
        )

        assert "size: A4" in html

    def test_margins(self):
        """Test that margins are applied correctly."""
        html = build_pdf_html_template(
            content_html="<p>Test</p>",
            font_family="Inter",
            font_size=11,
            line_height=1.15,
            margins={"top": 0.5, "right": 0.75, "bottom": 1.0, "left": 1.25}
        )

        assert "margin: 0.5in 0.75in 1.0in 1.25in" in html

    def test_default_margins(self):
        """Test that default margins are used when not provided."""
        html = build_pdf_html_template(
            content_html="<p>Test</p>",
            font_family="Inter",
            font_size=11,
            line_height=1.15
        )

        assert "margin: 1.0in 1.0in 1.0in 1.0in" in html

    def test_header_included(self):
        """Test that header is included when provided."""
        html = build_pdf_html_template(
            content_html="<p>Test</p>",
            font_family="Inter",
            font_size=11,
            line_height=1.15,
            header_text="My CV Header"
        )

        assert "My CV Header" in html
        assert 'class="header"' in html

    def test_footer_included(self):
        """Test that footer is included when provided."""
        html = build_pdf_html_template(
            content_html="<p>Test</p>",
            font_family="Inter",
            font_size=11,
            line_height=1.15,
            footer_text="Page 1"
        )

        assert "Page 1" in html
        assert 'class="footer"' in html

    def test_font_styles(self):
        """Test that font family and size are applied."""
        html = build_pdf_html_template(
            content_html="<p>Test</p>",
            font_family="Roboto",
            font_size=12,
            line_height=1.5
        )

        assert "font-family: 'Roboto'" in html
        assert "font-size: 12pt" in html
        assert "line-height: 1.5" in html

    def test_heading_font_sizes(self):
        """Test that heading font sizes are calculated correctly."""
        html = build_pdf_html_template(
            content_html="<p>Test</p>",
            font_family="Inter",
            font_size=10,
            line_height=1.15
        )

        # h1 should be 1.8x base font size
        assert "h1 { font-size: 18.0pt; }" in html
        # h2 should be 1.5x base font size
        assert "h2 { font-size: 15.0pt; }" in html
        # h3 should be 1.3x base font size
        assert "h3 { font-size: 13.0pt; }" in html
