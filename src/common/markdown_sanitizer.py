"""
Markdown Sanitizer (GAP-006 Fix).

Removes markdown formatting from CV text to ensure clean output.

Problem (Before):
- LLM outputs contain **bold**, *italic*, and other markdown
- to_markdown() methods add **text** syntax
- PDF and editor display raw markdown instead of formatting

Solution (After):
- Sanitize all markdown to plain text
- Convert markdown emphasis to uppercase or plain text
- Remove markdown headings, lists formatting while preserving content

Usage:
    from src.common.markdown_sanitizer import sanitize_markdown, sanitize_cv_text

    clean_text = sanitize_markdown("**Bold** and *italic* text")
    # Returns: "Bold and italic text"

    cv_text = sanitize_cv_text(generated_cv)
    # Returns CV with all markdown stripped
"""

import re
from typing import Optional


def sanitize_markdown(text: str) -> str:
    """
    Remove all markdown formatting from text.

    Handles:
    - Bold: **text** or __text__
    - Italic: *text* or _text_
    - Bold+Italic: ***text*** or ___text___
    - Strikethrough: ~~text~~
    - Code: `text` or ```text```
    - Links: [text](url) -> text
    - Images: ![alt](url) -> alt
    - Headers: # Header -> Header

    Args:
        text: Text potentially containing markdown

    Returns:
        Text with markdown formatting removed
    """
    if not text:
        return text

    # Order matters - process complex patterns first

    # Remove code blocks first (preserve content)
    text = re.sub(r'```[\s\S]*?```', lambda m: m.group(0).replace('```', '').strip(), text)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remove images (keep alt text)
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)

    # Remove links (keep link text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Remove bold+italic (***text*** or ___text___)
    text = re.sub(r'\*{3}([^*]+)\*{3}', r'\1', text)
    text = re.sub(r'_{3}([^_]+)_{3}', r'\1', text)

    # Remove bold (**text** or __text__)
    text = re.sub(r'\*{2}([^*]+)\*{2}', r'\1', text)
    text = re.sub(r'_{2}([^_]+)_{2}', r'\1', text)

    # Remove italic (*text* or _text_)
    # Be careful not to match underscores in variable_names
    text = re.sub(r'(?<!\w)\*([^*\n]+)\*(?!\w)', r'\1', text)
    text = re.sub(r'(?<!\w)_([^_\n]+)_(?!\w)', r'\1', text)

    # Remove strikethrough (~~text~~)
    text = re.sub(r'~~([^~]+)~~', r'\1', text)

    # Remove headers (# ## ### etc at start of line)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)

    return text


def sanitize_cv_text(cv_text: str) -> str:
    """
    Sanitize a complete CV text for PDF/display output.

    Applies markdown sanitization while preserving:
    - Line structure
    - Bullet points (• and -)
    - Section headers (converted from markdown)

    Args:
        cv_text: Full CV text with potential markdown

    Returns:
        Clean CV text ready for PDF generation
    """
    if not cv_text:
        return cv_text

    # Process line by line to preserve structure
    lines = cv_text.split('\n')
    sanitized_lines = []

    for line in lines:
        # Preserve empty lines
        if not line.strip():
            sanitized_lines.append(line)
            continue

        # Sanitize the line content
        clean_line = sanitize_markdown(line)

        # Convert bullet points to standard format
        clean_line = re.sub(r'^[-*+]\s+', '• ', clean_line)

        sanitized_lines.append(clean_line)

    return '\n'.join(sanitized_lines)


def sanitize_bullet_text(bullet: str) -> str:
    """
    Sanitize a single CV bullet point.

    Args:
        bullet: Single bullet text, may contain markdown

    Returns:
        Clean bullet text
    """
    if not bullet:
        return bullet

    clean = sanitize_markdown(bullet)

    # Remove leading bullet character if present (will be added back by template)
    clean = re.sub(r'^[•\-*]\s*', '', clean)

    return clean.strip()


def remove_bold_markers(text: str) -> str:
    """
    Remove only bold markers (**) from text.

    This is a targeted fix for the most common issue where
    LLM outputs include **emphasized** text.

    Args:
        text: Text with potential **bold** markers

    Returns:
        Text with bold markers removed
    """
    if not text:
        return text

    # Remove ** but preserve the content
    return re.sub(r'\*{2}([^*]+)\*{2}', r'\1', text)


def format_cv_section_header(text: str, uppercase: bool = True) -> str:
    """
    Format a CV section header without markdown.

    Instead of **SKILLS**, returns SKILLS (or Skills).

    Args:
        text: Section header text
        uppercase: Whether to uppercase the header

    Returns:
        Formatted plain text header
    """
    clean = sanitize_markdown(text)
    return clean.upper() if uppercase else clean


def format_cv_job_title(title: str, company: str, location: str, period: str) -> str:
    """
    Format a CV job title line without markdown.

    Instead of **Title** | Location | Period,
    returns plain formatted line suitable for PDF styling.

    Args:
        title: Job title
        company: Company name
        location: Job location
        period: Date range

    Returns:
        Plain formatted job title line
    """
    parts = [title]
    if company:
        parts.append(company)
    if location:
        parts.append(location)
    if period:
        parts.append(period)

    return " | ".join(parts)
