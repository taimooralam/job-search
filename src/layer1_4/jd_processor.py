"""
JD Processor: Structures raw job descriptions for annotation.

This module converts raw JD text into structured HTML with <section> tags
that enable precise annotation targeting. It's a critical dependency for
the annotation system - all UI and pipeline features depend on structured sections.

Processing steps:
1. Parse raw JD text (handles various formats from LinkedIn, Indeed, etc.)
2. Identify and tag semantic sections (responsibilities, qualifications, etc.)
3. Add stable character offsets for annotation persistence
4. Output HTML with <section> tags for TipTap annotation targeting
"""

import re
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import hashlib

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage

from src.common.config import Config
from src.common.llm_factory import create_tracked_llm
from src.common.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# SECTION TYPES
# =============================================================================

class JDSectionType(str, Enum):
    """Standard JD section types for annotation targeting."""
    RESPONSIBILITIES = "responsibilities"
    QUALIFICATIONS = "qualifications"
    NICE_TO_HAVE = "nice_to_have"
    TECHNICAL_SKILLS = "technical_skills"
    BENEFITS = "benefits"
    ABOUT_COMPANY = "about_company"
    ABOUT_ROLE = "about_role"
    REQUIREMENTS = "requirements"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    OTHER = "other"


# Section header patterns for detection
SECTION_PATTERNS: Dict[JDSectionType, List[str]] = {
    JDSectionType.RESPONSIBILITIES: [
        r"responsibilities",
        r"what you['']?ll do",
        r"your role",
        r"key responsibilities",
        r"the role",
        r"job duties",
        r"you will",
        r"day to day",
        r"in this role",
    ],
    JDSectionType.QUALIFICATIONS: [
        r"qualifications",
        r"requirements",
        r"what we['']?re looking for",
        r"who you are",
        r"your background",
        r"must have",
        r"required",
        r"you have",
        r"ideal candidate",
    ],
    JDSectionType.NICE_TO_HAVE: [
        r"nice to have",
        r"preferred",
        r"bonus",
        r"plus",
        r"ideally",
        r"it['']?s a plus",
        r"added advantage",
    ],
    JDSectionType.TECHNICAL_SKILLS: [
        r"technical skills",
        r"tech stack",
        r"technologies",
        r"tools",
        r"skills",
    ],
    JDSectionType.BENEFITS: [
        r"benefits",
        r"perks",
        r"what we offer",
        r"compensation",
        r"why join",
    ],
    JDSectionType.ABOUT_COMPANY: [
        r"about us",
        r"about the company",
        r"who we are",
        r"our company",
        r"company overview",
    ],
    JDSectionType.ABOUT_ROLE: [
        r"about the role",
        r"position overview",
        r"role overview",
        r"the opportunity",
    ],
    JDSectionType.EXPERIENCE: [
        r"experience",
        r"years of experience",
        r"background",
    ],
    JDSectionType.EDUCATION: [
        r"education",
        r"degree",
        r"academic",
    ],
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class JDSection:
    """A parsed section of the job description."""
    section_type: JDSectionType
    header: str                    # Original header text
    content: str                   # Section content (raw text)
    items: List[str]               # Individual items (bullet points)
    char_start: int                # Character offset start in original JD
    char_end: int                  # Character offset end in original JD
    index: int                     # Section index (0-based)


@dataclass
class ProcessedJD:
    """Result of JD processing."""
    raw_text: str                  # Original JD text
    sections: List[JDSection]      # Parsed sections
    html: str                      # Structured HTML for TipTap
    section_ids: List[str]         # List of section IDs in order
    content_hash: str              # Hash of content for change detection


class JDStructureModel(BaseModel):
    """Pydantic model for LLM-extracted JD structure."""

    sections: List[Dict[str, Any]] = Field(
        ...,
        description="List of sections with type, header, and items"
    )

    class Config:
        extra = "ignore"


# =============================================================================
# SECTION DETECTION (Rule-based)
# =============================================================================

def detect_section_type(header: str) -> JDSectionType:
    """
    Detect section type from header text using pattern matching.

    Args:
        header: The section header text

    Returns:
        Detected section type
    """
    header_lower = header.lower().strip()

    for section_type, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, header_lower, re.IGNORECASE):
                return section_type

    return JDSectionType.OTHER


def split_into_items(content: str) -> List[str]:
    """
    Split section content into individual items.

    Handles various formats:
    - Bullet points (-, *, •)
    - Numbered lists (1., 2., etc.)
    - Paragraphs separated by newlines

    Args:
        content: Section content text

    Returns:
        List of individual items
    """
    items = []

    # Try bullet points first
    bullet_pattern = r'^[\s]*[-*•◦▪]\s*(.+)$'
    bullet_matches = re.findall(bullet_pattern, content, re.MULTILINE)

    if bullet_matches:
        items = [m.strip() for m in bullet_matches if m.strip()]
    else:
        # Try numbered lists
        number_pattern = r'^[\s]*\d+[\.)]\s*(.+)$'
        number_matches = re.findall(number_pattern, content, re.MULTILINE)

        if number_matches:
            items = [m.strip() for m in number_matches if m.strip()]
        else:
            # Fall back to line-by-line
            lines = content.strip().split('\n')
            items = [line.strip() for line in lines if line.strip() and len(line.strip()) > 10]

    return items


def parse_jd_sections_rule_based(jd_text: str) -> List[JDSection]:
    """
    Parse JD into sections using rule-based pattern matching.

    This is a fallback when LLM processing is not available or fails.

    Args:
        jd_text: Raw job description text

    Returns:
        List of parsed sections
    """
    sections = []

    # Common section header patterns - supports multiple formats:
    # - Title case: "What You'll Do"
    # - ALL CAPS: "RESPONSIBILITIES"
    # - Numbered: "1. Responsibilities"
    # - Markdown headers: "## Qualifications"
    # - Headers with colon: "Requirements:"
    # - Bold markers: "**What We're Looking For**"
    header_pattern = r"^[\s]*(?:\*{1,2})?(?:#{1,6}\s*)?(?:\d+[\.\)]\s*)?([A-Za-z][A-Za-z\s&/'\u2019\-]+)(?:\*{1,2})?[\s]*[:：]?\s*$"

    lines = jd_text.split('\n')
    current_section = None
    current_content = []
    current_start = 0

    for i, line in enumerate(lines):
        # Calculate character offset
        char_offset = sum(len(l) + 1 for l in lines[:i])

        # Check if line is a header
        header_match = re.match(header_pattern, line.strip())
        is_header = header_match and len(line.strip()) < 60

        if is_header:
            # Save previous section
            if current_section and current_content:
                content = '\n'.join(current_content)
                sections.append(JDSection(
                    section_type=detect_section_type(current_section),
                    header=current_section,
                    content=content,
                    items=split_into_items(content),
                    char_start=current_start,
                    char_end=char_offset,
                    index=len(sections),
                ))

            # Start new section
            current_section = header_match.group(1).strip()
            current_content = []
            current_start = char_offset
        elif current_section:
            current_content.append(line)
        elif line.strip():
            # Content before first header goes to "about_role"
            if not current_section:
                current_section = "About the Role"
                current_start = 0
            current_content.append(line)

    # Save last section
    if current_section and current_content:
        content = '\n'.join(current_content)
        sections.append(JDSection(
            section_type=detect_section_type(current_section),
            header=current_section,
            content=content,
            items=split_into_items(content),
            char_start=current_start,
            char_end=len(jd_text),
            index=len(sections),
        ))

    # If no sections found, create a single "other" section
    if not sections:
        sections.append(JDSection(
            section_type=JDSectionType.OTHER,
            header="Job Description",
            content=jd_text,
            items=split_into_items(jd_text),
            char_start=0,
            char_end=len(jd_text),
            index=0,
        ))

    return sections


# =============================================================================
# LLM-BASED SECTION PARSING
# =============================================================================

JD_STRUCTURE_SYSTEM_PROMPT = """You are a job description parser. Your task is to identify and structure the sections of a job description.

For each section, extract:
1. section_type: One of: responsibilities, qualifications, nice_to_have, technical_skills, benefits, about_company, about_role, requirements, experience, education, other
2. header: The original header text from the JD
3. items: List of individual items/bullet points in that section

Return a JSON object with a "sections" array. Each section should have:
- section_type (string)
- header (string)
- items (array of strings)

IMPORTANT:
- Preserve the exact text from the JD (do not paraphrase)
- Keep items as they appear (bullet points, requirements, etc.)
- If content doesn't fit a specific type, use "other"
- Maintain the order sections appear in the JD"""

JD_STRUCTURE_USER_TEMPLATE = """Parse this job description into structured sections:

---
{jd_text}
---

Return JSON with sections array. Each section needs: section_type, header, items."""


async def parse_jd_sections_with_llm(
    jd_text: str,
    model: str = "gpt-4o-mini",
) -> List[JDSection]:
    """
    Parse JD into sections using LLM for better accuracy.

    Args:
        jd_text: Raw job description text
        model: LLM model to use

    Returns:
        List of parsed sections
    """
    try:
        config = Config()
        llm = create_tracked_llm(
            provider="openai",
            model=model,
            temperature=0.1,
            run_id="jd_processor",
        )

        messages = [
            SystemMessage(content=JD_STRUCTURE_SYSTEM_PROMPT),
            HumanMessage(content=JD_STRUCTURE_USER_TEMPLATE.format(jd_text=jd_text[:8000])),
        ]

        response = await llm.ainvoke(messages)
        content = response.content

        # Parse JSON from response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            logger.warning("No JSON found in LLM response, falling back to rule-based")
            return parse_jd_sections_rule_based(jd_text)

        data = json.loads(json_match.group())
        sections_data = data.get("sections", [])

        sections = []
        char_offset = 0

        for i, section_data in enumerate(sections_data):
            section_type_str = section_data.get("section_type", "other")
            try:
                section_type = JDSectionType(section_type_str)
            except ValueError:
                section_type = JDSectionType.OTHER

            header = section_data.get("header", "")
            items = section_data.get("items", [])
            content = '\n'.join(f"• {item}" for item in items)

            # Calculate approximate character offsets
            # (exact offsets would require more complex text matching)
            header_pos = jd_text.lower().find(header.lower()[:30]) if header else -1
            if header_pos >= 0:
                char_start = header_pos
            else:
                char_start = char_offset

            content_len = len(header) + len(content) + 10
            char_end = char_start + content_len
            char_offset = char_end

            sections.append(JDSection(
                section_type=section_type,
                header=header,
                content=content,
                items=items,
                char_start=char_start,
                char_end=min(char_end, len(jd_text)),
                index=i,
            ))

        return sections if sections else parse_jd_sections_rule_based(jd_text)

    except Exception as e:
        logger.warning(f"LLM parsing failed: {e}, falling back to rule-based")
        return parse_jd_sections_rule_based(jd_text)


# =============================================================================
# HTML GENERATION
# =============================================================================

def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def generate_section_html(section: JDSection) -> str:
    """
    Generate HTML for a single section.

    Args:
        section: Parsed JD section

    Returns:
        HTML string with data attributes for annotation targeting
    """
    section_id = f"jd-section-{section.section_type.value}-{section.index}"

    html_parts = [
        f'<section id="{section_id}" '
        f'data-section-type="{section.section_type.value}" '
        f'data-section-index="{section.index}" '
        f'data-char-start="{section.char_start}" '
        f'data-char-end="{section.char_end}" '
        f'class="jd-section jd-section-{section.section_type.value}">'
    ]

    # Section header
    if section.header:
        html_parts.append(
            f'<h3 class="jd-section-header" data-header="true">'
            f'{escape_html(section.header)}</h3>'
        )

    # Section content as list
    if section.items:
        html_parts.append('<ul class="jd-section-items">')
        for i, item in enumerate(section.items):
            item_id = f"{section_id}-item-{i}"
            # Calculate item character offset within section
            item_start = section.char_start + section.content.find(item[:20]) if item else section.char_start + i * 50
            item_end = item_start + len(item)

            html_parts.append(
                f'<li id="{item_id}" '
                f'data-item-index="{i}" '
                f'data-char-start="{item_start}" '
                f'data-char-end="{item_end}" '
                f'class="jd-item">'
                f'{escape_html(item)}'
                f'</li>'
            )
        html_parts.append('</ul>')
    else:
        # Raw content if no items parsed
        html_parts.append(
            f'<div class="jd-section-content">'
            f'{escape_html(section.content)}'
            f'</div>'
        )

    html_parts.append('</section>')

    return '\n'.join(html_parts)


def generate_processed_html(sections: List[JDSection]) -> str:
    """
    Generate complete HTML for all sections.

    Args:
        sections: List of parsed sections

    Returns:
        Complete HTML string for TipTap rendering
    """
    html_parts = ['<div class="jd-processed">']

    for section in sections:
        html_parts.append(generate_section_html(section))

    html_parts.append('</div>')

    return '\n'.join(html_parts)


# =============================================================================
# MAIN PROCESSOR
# =============================================================================

def process_jd_sync(jd_text: str, use_llm: bool = False) -> ProcessedJD:
    """
    Process a job description into structured format (synchronous).

    Args:
        jd_text: Raw job description text
        use_llm: Whether to use LLM for parsing (default: rule-based)

    Returns:
        ProcessedJD with sections and HTML
    """
    # Parse sections
    sections = parse_jd_sections_rule_based(jd_text)

    # Generate HTML
    html = generate_processed_html(sections)

    # Generate section IDs
    section_ids = [s.section_type.value for s in sections]

    # Content hash for change detection
    content_hash = hashlib.md5(jd_text.encode()).hexdigest()

    return ProcessedJD(
        raw_text=jd_text,
        sections=sections,
        html=html,
        section_ids=section_ids,
        content_hash=content_hash,
    )


async def process_jd(
    jd_text: str,
    use_llm: bool = True,
    model: str = "gpt-4o-mini",
) -> ProcessedJD:
    """
    Process a job description into structured format (async with optional LLM).

    Args:
        jd_text: Raw job description text
        use_llm: Whether to use LLM for better parsing accuracy
        model: LLM model to use if use_llm=True

    Returns:
        ProcessedJD with sections and HTML
    """
    # Parse sections
    if use_llm:
        sections = await parse_jd_sections_with_llm(jd_text, model)
    else:
        sections = parse_jd_sections_rule_based(jd_text)

    # Generate HTML
    html = generate_processed_html(sections)

    # Generate section IDs
    section_ids = [s.section_type.value for s in sections]

    # Content hash for change detection
    content_hash = hashlib.md5(jd_text.encode()).hexdigest()

    return ProcessedJD(
        raw_text=jd_text,
        sections=sections,
        html=html,
        section_ids=section_ids,
        content_hash=content_hash,
    )


def processed_jd_to_dict(processed: ProcessedJD) -> Dict[str, Any]:
    """
    Convert ProcessedJD to dictionary for JSON serialization.

    Args:
        processed: ProcessedJD object

    Returns:
        Dictionary suitable for MongoDB storage
    """
    return {
        "raw_text": processed.raw_text,
        "html": processed.html,
        "section_ids": processed.section_ids,
        "content_hash": processed.content_hash,
        "sections": [
            {
                "section_type": s.section_type.value,
                "header": s.header,
                "content": s.content,
                "items": s.items,
                "char_start": s.char_start,
                "char_end": s.char_end,
                "index": s.index,
            }
            for s in processed.sections
        ],
    }


def dict_to_processed_jd(data: Dict[str, Any]) -> ProcessedJD:
    """
    Convert dictionary to ProcessedJD.

    Args:
        data: Dictionary from MongoDB

    Returns:
        ProcessedJD object
    """
    sections = [
        JDSection(
            section_type=JDSectionType(s["section_type"]),
            header=s["header"],
            content=s["content"],
            items=s["items"],
            char_start=s["char_start"],
            char_end=s["char_end"],
            index=s["index"],
        )
        for s in data.get("sections", [])
    ]

    return ProcessedJD(
        raw_text=data.get("raw_text", ""),
        sections=sections,
        html=data.get("html", ""),
        section_ids=data.get("section_ids", []),
        content_hash=data.get("content_hash", ""),
    )
