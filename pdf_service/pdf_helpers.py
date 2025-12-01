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


def tiptap_json_to_html(tiptap_content: dict, max_depth: int = 50) -> str:
    """
    Convert TipTap JSON to HTML for display compatibility.

    Uses iterative approach to avoid Python's recursion limit.

    Args:
        tiptap_content: TipTap document JSON
        max_depth: Maximum nesting depth to prevent excessive processing (default 50)

    Returns:
        HTML string
    """
    if not tiptap_content or tiptap_content.get("type") != "doc":
        return ""

    def process_node_iterative(node):
        """
        Iterative node processing using a stack to avoid recursion.

        This prevents hitting Python's recursion limit (~1000 frames)
        which can occur with deeply nested document structures.
        """
        # Stack entries: (node, depth, mode)
        # mode: 'open' = start processing, 'close' = finish processing
        stack = [(node, 0, 'open')]
        result_stack = []

        while stack:
            current_node, depth, mode = stack.pop()

            if depth > max_depth:
                if mode == 'open':
                    result_stack.append("<!-- Maximum nesting depth exceeded -->")
                continue

            node_type = current_node.get("type")
            content = current_node.get("content", [])
            attrs = current_node.get("attrs", {})
            marks = current_node.get("marks", [])

            # Process text nodes
            if node_type == "text":
                text = current_node.get("text", "")
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
                result_stack.append(text)

            # Process block nodes
            elif node_type == "paragraph":
                text_align = attrs.get("textAlign", "left")
                if mode == 'open':
                    # Push close marker
                    stack.append((current_node, depth, 'close'))
                    # Push children in reverse order
                    for child in reversed(content):
                        stack.append((child, depth + 1, 'open'))
                    # Push opening tag
                    if text_align != "left":
                        result_stack.append(f'<p style="text-align: {text_align};">')
                    else:
                        result_stack.append('<p>')
                else:  # mode == 'close'
                    result_stack.append('</p>')

            elif node_type == "heading":
                level = attrs.get("level", 1)
                text_align = attrs.get("textAlign", "left")
                if mode == 'open':
                    stack.append((current_node, depth, 'close'))
                    for child in reversed(content):
                        stack.append((child, depth + 1, 'open'))
                    if text_align != "left":
                        result_stack.append(f'<h{level} style="text-align: {text_align};">')
                    else:
                        result_stack.append(f'<h{level}>')
                else:
                    result_stack.append(f'</h{level}>')

            elif node_type == "bulletList":
                if mode == 'open':
                    stack.append((current_node, depth, 'close'))
                    for child in reversed(content):
                        stack.append((child, depth + 1, 'open'))
                    result_stack.append('<ul>')
                else:
                    result_stack.append('</ul>')

            elif node_type == "orderedList":
                if mode == 'open':
                    stack.append((current_node, depth, 'close'))
                    for child in reversed(content):
                        stack.append((child, depth + 1, 'open'))
                    result_stack.append('<ol>')
                else:
                    result_stack.append('</ol>')

            elif node_type == "listItem":
                if mode == 'open':
                    stack.append((current_node, depth, 'close'))
                    for child in reversed(content):
                        stack.append((child, depth + 1, 'open'))
                    result_stack.append('<li>')
                else:
                    result_stack.append('</li>')

            elif node_type == "hardBreak":
                result_stack.append("<br>")

            elif node_type == "horizontalRule":
                result_stack.append("<hr>")

            else:
                # Unknown node type, process children
                if mode == 'open' and content:
                    stack.append((current_node, depth, 'close'))
                    for child in reversed(content):
                        stack.append((child, depth + 1, 'open'))

        return "".join(result_stack)

    # Process all top-level nodes
    html_parts = []
    for node in tiptap_content.get("content", []):
        html_parts.append(process_node_iterative(node))

    return "".join(html_parts)


def build_pdf_html_template(
    content_html: str,
    font_family: str,
    font_size: int,
    line_height: float,
    header_text: str = "",
    footer_text: str = "",
    page_size: str = "letter",
    margins: dict = None
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
        page_size: Page size ("letter" or "a4")
        margins: Margins dict with top, right, bottom, left in inches

    Returns:
        Complete HTML document string
    """
    # Default margins if not provided
    if margins is None:
        margins = {"top": 1.0, "right": 1.0, "bottom": 1.0, "left": 1.0}
    # Build Google Fonts URL (API v2 format)
    # Each font needs its own "family=" parameter with weight variants
    # Critical fonts for CV styling that must be loaded
    essential_fonts = [
        ('Playfair Display', '400;600;700'),  # Serif for h1/h2/h3 headings
        ('Inter', '400;600;700'),  # Sans-serif body (default)
        ('Source Sans 3', '400;600;700'),  # Professional humanist sans
    ]

    # Add the user-selected font if different
    if font_family and font_family not in ['Playfair Display', 'Inter', 'Source Sans 3']:
        essential_fonts.append((font_family, '400;600;700'))

    # Build Google Fonts URL with correct API v2 format
    # Format: family=Font+Name:wght@400;700&family=Other+Font:wght@400;700
    font_params = '&'.join([
        f"family={font.replace(' ', '+')}:wght@{weights}"
        for font, weights in essential_fonts
    ])
    google_fonts_url = f"https://fonts.googleapis.com/css2?{font_params}&display=swap"

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
        /* Professional CV Design System */
        :root {{
            --font-heading: 'Playfair Display', 'Cormorant Garamond', serif;
            --font-body: '{font_family}', 'Source Sans 3', 'Work Sans', system-ui, sans-serif;
            --color-text: #1f2a38;
            --color-muted: #4b5563;
            --color-accent: #475569;  /* slate-600 - professional dark blue-gray */
        }}

        @page {{
            size: {page_size.upper() if page_size.lower() == 'a4' else 'Letter'};
            margin: {margins['top']}in {margins['right']}in {margins['bottom']}in {margins['left']}in;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: var(--font-body);
            font-size: {font_size}pt;
            line-height: {line_height};
            color: var(--color-text);
            background: white;
            max-width: 720px;
            margin: 0 auto;
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
            color: var(--color-muted);
            padding: 8px 0;
            border-bottom: 1px solid #e5e7eb;
        }}

        .footer {{
            text-align: center;
            font-size: 9pt;
            color: var(--color-muted);
            padding: 8px 0;
            border-top: 1px solid #e5e7eb;
            position: fixed;
            bottom: 0;
            width: 100%;
        }}

        .content {{
            padding: 0;
        }}

        /* Typography Hierarchy - Match editor line-height inheritance */
        h1, h2, h3, h4, h5, h6 {{
            font-family: var(--font-heading);
            color: var(--color-accent);
            font-weight: 700;
            line-height: inherit; /* Match editor: inherit from document settings */
        }}

        h1 {{
            font-size: 32px;
            font-weight: 700;
            margin: 0 0 8px 0; /* GAP-026: 20% tighter spacing */
            letter-spacing: 0.02em; /* Refined letter-spacing for elegance */
            text-transform: uppercase; /* Executive styling - uppercase name */
            color: #1e293b; /* slate-800 - darker for executive presence */
        }}

        h2 {{
            font-size: 20px;
            font-weight: 700;
            margin: 12px 0 8px; /* GAP-026: 20% tighter spacing */
            padding-top: 6px;
            border-top: 1px solid #e5e7eb;
        }}

        h2:first-child {{
            border-top: none;
            padding-top: 0;
            margin-top: 0;
        }}

        h3 {{
            font-size: 16px;
            font-weight: 600;
            margin: 10px 0 6px; /* GAP-026: 20% tighter spacing */
        }}

        /* Paragraphs - GAP-026: 20% tighter (0.4em vs 0.5em) */
        p {{
            margin: 0.4em 0;
            line-height: inherit;
        }}

        p:first-child {{
            margin-top: 0;
        }}

        p:last-child {{
            margin-bottom: 0;
        }}

        /* List Styling - GAP-026: 20% tighter (0.4em vs 0.5em) */
        ul, ol {{
            padding-left: 1.5em;
            margin: 0.4em 0;
            list-style-position: outside;
        }}

        /* List items - GAP-026: 20% tighter (0.2em vs 0.25em) */
        li {{
            margin: 0.2em 0;
            line-height: inherit;
        }}

        li > p {{
            margin: 0;
        }}

        ul li {{
            list-style-type: disc;
        }}

        /* Links - Accent color, underline on hover */
        a {{
            color: var(--color-accent);
            text-decoration: none;
        }}

        a:hover {{
            text-decoration: underline;
        }}

        /* Preserve TipTap formatting */
        strong {{ font-weight: 700; }}
        em {{ font-style: italic; }}
        u {{ text-decoration: underline; }}

        mark {{
            background-color: #fef3c7;
            padding: 2px 4px;
        }}

        /* Metadata styling (location, dates, etc.) */
        .meta {{
            font-size: 10px;
            color: var(--color-muted);
            letter-spacing: 0.3px;
            text-transform: uppercase;
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
