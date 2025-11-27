"""
Helper functions for PDF generation from CV editor state.

These functions convert TipTap JSON to HTML and generate complete
HTML documents for PDF rendering via Playwright.
"""

import re
from typing import Optional


def sanitize_for_path(text: str) -> str:
    """
    Sanitize text for use in filesystem paths.

    Removes special characters (except word chars, spaces, hyphens)
    and replaces spaces with underscores.

    Args:
        text: Raw text (company name, job title, etc.)

    Returns:
        Sanitized string safe for filesystem paths

    Example:
        >>> sanitize_for_path("Director of Engineering (Software)")
        "Director_of_Engineering__Software_"
    """
    # Remove special characters except word characters, spaces, and hyphens
    cleaned = re.sub(r'[^\w\s-]', '_', text)
    # Replace spaces with underscores
    return cleaned.replace(" ", "_")


def tiptap_json_to_html(tiptap_content: dict) -> str:
    """
    Convert TipTap JSON to HTML for display compatibility.

    Args:
        tiptap_content: TipTap document JSON

    Returns:
        HTML string
    """
    if not tiptap_content or tiptap_content.get("type") != "doc":
        return ""

    html_parts = []

    def process_node(node):
        node_type = node.get("type")
        content = node.get("content", [])
        attrs = node.get("attrs", {})
        marks = node.get("marks", [])

        # Process text nodes
        if node_type == "text":
            text = node.get("text", "")
            # Apply marks (bold, italic, etc.)
            for mark in marks:
                mark_type = mark.get("type")
                if mark_type == "bold":
                    text = f"<strong>{text}</strong>"
                elif mark_type == "italic":
                    text = f"<em>{text}</em>"
                elif mark_type == "underline":
                    text = f"<u>{text}</u>"
                elif mark_type == "textStyle":
                    # Handle font family, font size, color
                    style_parts = []
                    mark_attrs = mark.get("attrs", {})
                    if mark_attrs.get("fontFamily"):
                        style_parts.append(f"font-family: {mark_attrs['fontFamily']}")
                    if mark_attrs.get("fontSize"):
                        style_parts.append(f"font-size: {mark_attrs['fontSize']}")
                    if mark_attrs.get("color"):
                        style_parts.append(f"color: {mark_attrs['color']}")
                    if style_parts:
                        text = f"<span style='{'; '.join(style_parts)}'>{text}</span>"
                elif mark_type == "highlight":
                    color = mark.get("attrs", {}).get("color", "yellow")
                    text = f"<mark style='background-color: {color}'>{text}</mark>"
            return text

        # Process block nodes
        elif node_type == "paragraph":
            inner_html = "".join(process_node(child) for child in content)
            text_align = attrs.get("textAlign", "left")
            if text_align != "left":
                style_attr = f' style="text-align: {text_align};"'
                return f"<p{style_attr}>{inner_html}</p>"
            return f"<p>{inner_html}</p>"

        elif node_type == "heading":
            level = attrs.get("level", 1)
            inner_html = "".join(process_node(child) for child in content)
            text_align = attrs.get("textAlign", "left")
            if text_align != "left":
                style_attr = f' style="text-align: {text_align};"'
                return f"<h{level}{style_attr}>{inner_html}</h{level}>"
            return f"<h{level}>{inner_html}</h{level}>"

        elif node_type == "bulletList":
            items_html = "".join(process_node(child) for child in content)
            return f"<ul>{items_html}</ul>"

        elif node_type == "orderedList":
            items_html = "".join(process_node(child) for child in content)
            return f"<ol>{items_html}</ol>"

        elif node_type == "listItem":
            inner_html = "".join(process_node(child) for child in content)
            return f"<li>{inner_html}</li>"

        elif node_type == "hardBreak":
            return "<br>"

        elif node_type == "horizontalRule":
            return "<hr>"

        else:
            # Unknown node type, process children
            return "".join(process_node(child) for child in content)

    # Process all top-level nodes
    for node in tiptap_content.get("content", []):
        html_parts.append(process_node(node))

    return "".join(html_parts)


def build_pdf_html_template(
    content_html: str,
    font_family: str,
    font_size: int,
    line_height: float,
    header_text: str = "",
    footer_text: str = ""
) -> str:
    """
    Build complete HTML document for PDF generation with embedded styles.

    Includes:
    - Google Fonts link for font embedding
    - CSS styles for formatting
    - Header/footer if present
    - Content HTML from TipTap

    Args:
        content_html: HTML content from TipTap JSON
        font_family: Font family name (e.g., "Inter", "Merriweather")
        font_size: Font size in points
        line_height: Line height multiplier (e.g., 1.15, 1.5)
        header_text: Optional header text
        footer_text: Optional footer text

    Returns:
        Complete HTML document string
    """
    # Build Google Fonts URL (support multiple fonts)
    # Common Phase 2 fonts that need embedding
    all_fonts = [
        font_family,
        'Inter',  # Default body font
        'Roboto', 'Open Sans', 'Lato', 'Montserrat',  # Sans-serif
        'Merriweather', 'Playfair Display', 'Lora',  # Serif
    ]
    fonts_param = '|'.join(set(all_fonts))  # Deduplicate
    google_fonts_url = f"https://fonts.googleapis.com/css2?family={fonts_param.replace(' ', '+')}:wght@400;700&display=swap"

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CV</title>

    <!-- Google Fonts for embedding -->
    <link href="{google_fonts_url}" rel="stylesheet">

    <style>
        @page {{
            size: Letter;
            margin: 0;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: '{font_family}', sans-serif;
            font-size: {font_size}pt;
            line-height: {line_height};
            color: #1a1a1a;
            background: white;
        }}

        .page-container {{
            width: 100%;
            height: 100%;
            padding: 0;
            margin: 0;
        }}

        .header {{
            text-align: center;
            font-size: 9pt;
            color: #666;
            padding: 8px 0;
            border-bottom: 1px solid #ddd;
        }}

        .footer {{
            text-align: center;
            font-size: 9pt;
            color: #666;
            padding: 8px 0;
            border-top: 1px solid #ddd;
            position: fixed;
            bottom: 0;
            width: 100%;
        }}

        .content {{
            padding: 0;
        }}

        /* Typography */
        h1, h2, h3, h4, h5, h6 {{
            font-weight: 700;
            margin-top: 16px;
            margin-bottom: 8px;
        }}

        h1 {{ font-size: {font_size * 1.8}pt; }}
        h2 {{ font-size: {font_size * 1.5}pt; }}
        h3 {{ font-size: {font_size * 1.3}pt; }}

        p {{
            margin-bottom: 8px;
        }}

        ul, ol {{
            margin-left: 20px;
            margin-bottom: 8px;
        }}

        li {{
            margin-bottom: 4px;
        }}

        /* Preserve TipTap formatting */
        strong {{ font-weight: 700; }}
        em {{ font-style: italic; }}
        u {{ text-decoration: underline; }}

        mark {{
            background-color: #ffff00;
            padding: 2px 4px;
        }}

        /* Text alignment */
        .text-left {{ text-align: left; }}
        .text-center {{ text-align: center; }}
        .text-right {{ text-align: right; }}
        .text-justify {{ text-align: justify; }}
    </style>
</head>
<body>
    <div class="page-container">
        """

    # Add header if present
    if header_text:
        html += f"""
        <div class="header">
            {header_text}
        </div>
        """

    # Add main content
    html += f"""
        <div class="content">
            {content_html}
        </div>
        """

    # Add footer if present
    if footer_text:
        html += f"""
        <div class="footer">
            {footer_text}
        </div>
        """

    html += """
    </div>
</body>
</html>
    """

    return html
