"""
Variant Parser for Enhanced Role Files.

Parses the structured achievement format with multiple variants per achievement,
enabling intelligent variant selection based on JD requirements.

The enhanced role file format:
    ### Achievement N: [Title]

    **Core Fact**: [Factual description]

    **Variants**:
    - **Technical**: [Technical depth emphasis]
    - **Architecture**: [System design emphasis]
    - **Impact**: [Business outcome emphasis]
    - **Leadership**: [People/team emphasis]
    - **Short**: [Concise version]

    **Keywords**: [comma-separated ATS keywords]

    **Interview Defensibility**: [verification notes]

Usage:
    parser = VariantParser()
    enhanced_role = parser.parse_role_file(Path("data/master-cv/roles/01_seven_one.md"))

    for achievement in enhanced_role.achievements:
        print(f"{achievement.title}: {len(achievement.variants)} variants")
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.common.logger import get_logger


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class AchievementVariant:
    """
    A single variant of an achievement bullet.

    Each variant emphasizes different aspects (technical depth, leadership,
    business impact) while describing the same underlying achievement.
    """

    variant_type: str  # "Technical", "Architecture", "Impact", "Leadership", "Short", etc.
    text: str

    @property
    def word_count(self) -> int:
        """Calculate word count of the variant text."""
        return len(self.text.split())

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "variant_type": self.variant_type,
            "text": self.text,
            "word_count": self.word_count,
        }


@dataclass
class Achievement:
    """
    A complete achievement with all its variants and metadata.

    This represents a single accomplishment that can be expressed in multiple
    ways depending on the target job description requirements.
    """

    id: str  # e.g., "achievement_1"
    title: str  # e.g., "Legacy Modernization & Platform Transformation"
    core_fact: str  # The factual description - source of truth
    variants: Dict[str, AchievementVariant]  # variant_type -> AchievementVariant
    keywords: List[str]  # ATS keywords for this achievement
    interview_defensibility: str = ""  # Notes on what can be explained in interview
    business_context: str = ""  # Optional business context for SITUATION

    @property
    def variant_types(self) -> List[str]:
        """Get list of available variant types."""
        return list(self.variants.keys())

    @property
    def has_all_standard_variants(self) -> bool:
        """Check if achievement has all standard variant types."""
        standard = {"Technical", "Architecture", "Impact", "Leadership", "Short"}
        return standard.issubset(set(self.variants.keys()))

    def get_variant(self, variant_type: str) -> Optional[AchievementVariant]:
        """Get a specific variant by type, with fallback to Technical."""
        if variant_type in self.variants:
            return self.variants[variant_type]
        # Fallback order: Technical -> Impact -> Short -> first available
        for fallback in ["Technical", "Impact", "Short"]:
            if fallback in self.variants:
                return self.variants[fallback]
        # Return first available if no standard types
        if self.variants:
            return next(iter(self.variants.values()))
        return None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "core_fact": self.core_fact,
            "variants": {k: v.to_dict() for k, v in self.variants.items()},
            "keywords": self.keywords,
            "interview_defensibility": self.interview_defensibility,
            "business_context": self.business_context,
            "variant_types": self.variant_types,
        }


@dataclass
class RoleMetadata:
    """
    Metadata extracted from the role file header.

    Contains role-level information like company, title, period, etc.
    """

    company: str
    title: str
    location: str
    period: str
    is_current: bool
    career_stage: str
    duration: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "company": self.company,
            "title": self.title,
            "location": self.location,
            "period": self.period,
            "is_current": self.is_current,
            "career_stage": self.career_stage,
            "duration": self.duration,
        }


@dataclass
class SelectionGuide:
    """
    Mapping from JD emphasis areas to recommended achievements.

    Extracted from the "Selection Guide by JD Type" section in role files.
    """

    mappings: Dict[str, List[str]]  # JD emphasis -> list of achievement IDs

    def get_recommended(self, jd_emphasis: str) -> List[str]:
        """Get recommended achievement IDs for a JD emphasis."""
        # Try exact match first
        if jd_emphasis in self.mappings:
            return self.mappings[jd_emphasis]
        # Try case-insensitive partial match
        jd_lower = jd_emphasis.lower()
        for key, value in self.mappings.items():
            if jd_lower in key.lower() or key.lower() in jd_lower:
                return value
        return []

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {"mappings": self.mappings}


@dataclass
class EnhancedRoleData:
    """
    Complete parsed data from an enhanced role file.

    Combines role metadata, structured achievements with variants,
    skills, and selection guide for intelligent CV generation.
    """

    id: str  # e.g., "01_seven_one_entertainment"
    metadata: RoleMetadata
    achievements: List[Achievement]
    hard_skills: List[str]
    soft_skills: List[str]
    selection_guide: Optional[SelectionGuide] = None
    raw_content: str = ""

    @property
    def achievement_count(self) -> int:
        """Get total number of achievements."""
        return len(self.achievements)

    @property
    def total_variants(self) -> int:
        """Get total number of variants across all achievements."""
        return sum(len(a.variants) for a in self.achievements)

    @property
    def all_keywords(self) -> List[str]:
        """Get all unique keywords from all achievements."""
        keywords = set()
        for achievement in self.achievements:
            keywords.update(achievement.keywords)
        return sorted(keywords)

    def get_achievement_by_id(self, achievement_id: str) -> Optional[Achievement]:
        """Get an achievement by its ID."""
        for achievement in self.achievements:
            if achievement.id == achievement_id:
                return achievement
        return None

    def get_achievement_by_number(self, number: int) -> Optional[Achievement]:
        """Get an achievement by its number (1-indexed)."""
        if 1 <= number <= len(self.achievements):
            return self.achievements[number - 1]
        return None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "metadata": self.metadata.to_dict(),
            "achievements": [a.to_dict() for a in self.achievements],
            "hard_skills": self.hard_skills,
            "soft_skills": self.soft_skills,
            "selection_guide": self.selection_guide.to_dict() if self.selection_guide else None,
            "achievement_count": self.achievement_count,
            "total_variants": self.total_variants,
            "all_keywords": self.all_keywords,
        }


# ============================================================================
# PARSER CLASS
# ============================================================================

class VariantParser:
    """
    Parses enhanced role files into structured EnhancedRoleData objects.

    Handles both the new variant-based format and falls back gracefully
    for legacy simple bullet format.
    """

    # Regex patterns for parsing
    ACHIEVEMENT_HEADER_PATTERN = re.compile(
        r"^###\s+Achievement\s+(\d+):\s*(.+)$", re.MULTILINE
    )
    CORE_FACT_PATTERN = re.compile(
        r"\*\*Core Fact\*\*:\s*(.+?)(?=\n\n|\n\*\*Variants\*\*|\Z)", re.DOTALL
    )
    VARIANTS_SECTION_PATTERN = re.compile(
        r"\*\*Variants\*\*:\s*\n((?:- \*\*\w+\*\*:.+?\n?)+)", re.DOTALL
    )
    VARIANT_LINE_PATTERN = re.compile(
        r"- \*\*(\w+)\*\*:\s*(.+?)(?=\n- \*\*|\n\n|\n\*\*|\Z)", re.DOTALL
    )
    KEYWORDS_PATTERN = re.compile(
        r"\*\*Keywords\*\*:\s*(.+?)(?=\n\n|\n\*\*|\Z)", re.DOTALL
    )
    INTERVIEW_DEFENSIBILITY_PATTERN = re.compile(
        r"\*\*Interview Defensibility\*\*:\s*(.+?)(?=\n\n|\n\*\*|\n---|\Z)", re.DOTALL
    )
    BUSINESS_CONTEXT_PATTERN = re.compile(
        r"\*\*Business Context\*\*:\s*(.+?)(?=\n\n|\n\*\*|\n---|\Z)", re.DOTALL
    )

    # Role metadata patterns
    ROLE_PATTERN = re.compile(r"\*\*Role\*\*:\s*(.+)")
    LOCATION_PATTERN = re.compile(r"\*\*Location\*\*:\s*(.+)")
    PERIOD_PATTERN = re.compile(r"\*\*Period\*\*:\s*(.+)")
    IS_CURRENT_PATTERN = re.compile(r"\*\*Is Current\*\*:\s*(true|false)", re.IGNORECASE)
    CAREER_STAGE_PATTERN = re.compile(r"\*\*Career Stage\*\*:\s*(.+)")
    DURATION_PATTERN = re.compile(r"\*\*Duration\*\*:\s*(.+)")

    # Skills patterns
    HARD_SKILLS_PATTERN = re.compile(r"\*\*Hard Skills\*\*:\s*(.+?)(?=\n|$)")
    SOFT_SKILLS_PATTERN = re.compile(r"\*\*Soft Skills\*\*:\s*(.+?)(?=\n|$)")

    # Selection guide pattern
    SELECTION_GUIDE_PATTERN = re.compile(
        r"## Selection Guide by JD Type\s*\n\n\|[^\n]+\|\s*\n\|[-\s|]+\|\s*\n((?:\|[^\n]+\|\s*\n?)+)",
        re.MULTILINE
    )

    def __init__(self):
        """Initialize the parser."""
        self._logger = get_logger(__name__)

    def parse_role_file(self, file_path: Path) -> EnhancedRoleData:
        """
        Parse an enhanced role file into structured data.

        Args:
            file_path: Path to the role markdown file

        Returns:
            EnhancedRoleData with all parsed information

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Role file not found: {file_path}")

        content = file_path.read_text(encoding="utf-8")
        role_id = file_path.stem  # e.g., "01_seven_one_entertainment"

        self._logger.debug(f"Parsing role file: {role_id}")

        # Check if this is an enhanced format file
        if not self._is_enhanced_format(content):
            self._logger.warning(
                f"Role file {role_id} is not in enhanced format. "
                "Falling back to legacy parsing."
            )
            return self._parse_legacy_format(content, role_id)

        # Parse enhanced format
        metadata = self._parse_metadata(content, role_id)
        achievements = self._parse_achievements(content)
        hard_skills, soft_skills = self._parse_skills(content)
        selection_guide = self._parse_selection_guide(content)

        enhanced_role = EnhancedRoleData(
            id=role_id,
            metadata=metadata,
            achievements=achievements,
            hard_skills=hard_skills,
            soft_skills=soft_skills,
            selection_guide=selection_guide,
            raw_content=content,
        )

        self._logger.info(
            f"Parsed {role_id}: {enhanced_role.achievement_count} achievements, "
            f"{enhanced_role.total_variants} total variants"
        )

        return enhanced_role

    def parse_content(self, content: str, role_id: str = "unknown") -> EnhancedRoleData:
        """
        Parse role content from a string (e.g., from MongoDB).

        This is the same as parse_role_file but accepts content directly
        instead of reading from a file path.

        Args:
            content: Markdown content string
            role_id: Optional role identifier for logging/metadata

        Returns:
            EnhancedRoleData with all parsed information

        Raises:
            ValueError: If content format is invalid
        """
        self._logger.debug(f"Parsing role content: {role_id}")

        # Check if this is an enhanced format file
        if not self._is_enhanced_format(content):
            self._logger.warning(
                f"Role content {role_id} is not in enhanced format. "
                "Falling back to legacy parsing."
            )
            return self._parse_legacy_format(content, role_id)

        # Parse enhanced format
        metadata = self._parse_metadata(content, role_id)
        achievements = self._parse_achievements(content)
        hard_skills, soft_skills = self._parse_skills(content)
        selection_guide = self._parse_selection_guide(content)

        enhanced_role = EnhancedRoleData(
            id=role_id,
            metadata=metadata,
            achievements=achievements,
            hard_skills=hard_skills,
            soft_skills=soft_skills,
            selection_guide=selection_guide,
            raw_content=content,
        )

        self._logger.info(
            f"Parsed {role_id}: {enhanced_role.achievement_count} achievements, "
            f"{enhanced_role.total_variants} total variants"
        )

        return enhanced_role

    def _is_enhanced_format(self, content: str) -> bool:
        """Check if content uses the enhanced variant format."""
        # Look for the characteristic pattern of enhanced format
        has_achievement_header = bool(self.ACHIEVEMENT_HEADER_PATTERN.search(content))
        has_variants = "**Variants**:" in content
        return has_achievement_header and has_variants

    def _parse_metadata(self, content: str, role_id: str) -> RoleMetadata:
        """Extract role metadata from the file header."""
        # Extract company name from H1 header
        company_match = re.search(r"^# (.+)$", content, re.MULTILINE)
        company = company_match.group(1).strip() if company_match else role_id

        # Extract other metadata fields
        role_match = self.ROLE_PATTERN.search(content)
        location_match = self.LOCATION_PATTERN.search(content)
        period_match = self.PERIOD_PATTERN.search(content)
        is_current_match = self.IS_CURRENT_PATTERN.search(content)
        career_stage_match = self.CAREER_STAGE_PATTERN.search(content)
        duration_match = self.DURATION_PATTERN.search(content)

        return RoleMetadata(
            company=company,
            title=role_match.group(1).strip() if role_match else "",
            location=location_match.group(1).strip() if location_match else "",
            period=period_match.group(1).strip() if period_match else "",
            is_current=is_current_match.group(1).lower() == "true" if is_current_match else False,
            career_stage=career_stage_match.group(1).strip() if career_stage_match else "",
            duration=duration_match.group(1).strip() if duration_match else "",
        )

    def _parse_achievements(self, content: str) -> List[Achievement]:
        """Parse all achievements with their variants from the content."""
        achievements = []

        # Find the Achievements section
        achievements_section_match = re.search(
            r"## Achievements\s*\n(.+?)(?=\n## (?!Achievement)|$)",
            content,
            re.DOTALL
        )
        if not achievements_section_match:
            self._logger.warning("No Achievements section found")
            return achievements

        achievements_content = achievements_section_match.group(1)

        # Split by achievement headers
        achievement_blocks = re.split(
            r"(?=^### Achievement \d+:)", achievements_content, flags=re.MULTILINE
        )

        for block in achievement_blocks:
            if not block.strip():
                continue

            achievement = self._parse_single_achievement(block)
            if achievement:
                achievements.append(achievement)

        return achievements

    def _parse_single_achievement(self, block: str) -> Optional[Achievement]:
        """Parse a single achievement block into an Achievement object."""
        # Extract achievement header
        header_match = self.ACHIEVEMENT_HEADER_PATTERN.search(block)
        if not header_match:
            return None

        achievement_num = header_match.group(1)
        achievement_title = header_match.group(2).strip()
        achievement_id = f"achievement_{achievement_num}"

        # Extract core fact
        core_fact_match = self.CORE_FACT_PATTERN.search(block)
        core_fact = core_fact_match.group(1).strip() if core_fact_match else ""

        # Extract variants
        variants = self._parse_variants(block)

        # Extract keywords
        keywords_match = self.KEYWORDS_PATTERN.search(block)
        keywords = []
        if keywords_match:
            keywords_text = keywords_match.group(1).strip()
            keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]

        # Extract interview defensibility
        defensibility_match = self.INTERVIEW_DEFENSIBILITY_PATTERN.search(block)
        interview_defensibility = ""
        if defensibility_match:
            interview_defensibility = defensibility_match.group(1).strip()

        # Extract business context
        context_match = self.BUSINESS_CONTEXT_PATTERN.search(block)
        business_context = ""
        if context_match:
            business_context = context_match.group(1).strip()

        return Achievement(
            id=achievement_id,
            title=achievement_title,
            core_fact=core_fact,
            variants=variants,
            keywords=keywords,
            interview_defensibility=interview_defensibility,
            business_context=business_context,
        )

    def _parse_variants(self, block: str) -> Dict[str, AchievementVariant]:
        """Parse the variants section of an achievement block."""
        variants = {}

        # Find the variants section start
        variants_start = block.find("**Variants**:")
        if variants_start == -1:
            return variants

        # Find where variants section ends (next ** section or --- or end)
        variants_section = block[variants_start:]

        # Find the end of the variants list by looking for next section marker
        end_markers = ["\n\n**Keywords**", "\n\n**Interview", "\n\n**Business", "\n---"]
        end_pos = len(variants_section)
        for marker in end_markers:
            pos = variants_section.find(marker)
            if pos != -1 and pos < end_pos:
                end_pos = pos

        variants_text = variants_section[:end_pos]

        # Parse each variant line: "- **Type**: text"
        # Use a simple line-by-line approach
        lines = variants_text.split("\n")
        current_variant_type = None
        current_variant_text = []

        for line in lines:
            line = line.strip()

            # Check if this is a new variant line
            variant_match = re.match(r"^-\s*\*\*(\w+)\*\*:\s*(.*)$", line)
            if variant_match:
                # Save previous variant if exists
                if current_variant_type and current_variant_text:
                    text = " ".join(current_variant_text).strip()
                    text = re.sub(r"\s+", " ", text)
                    variants[current_variant_type] = AchievementVariant(
                        variant_type=current_variant_type,
                        text=text,
                    )

                # Start new variant
                current_variant_type = variant_match.group(1)
                current_variant_text = [variant_match.group(2)] if variant_match.group(2) else []
            elif current_variant_type and line and not line.startswith("**"):
                # Continue current variant (multi-line support)
                current_variant_text.append(line)

        # Save last variant
        if current_variant_type and current_variant_text:
            text = " ".join(current_variant_text).strip()
            text = re.sub(r"\s+", " ", text)
            variants[current_variant_type] = AchievementVariant(
                variant_type=current_variant_type,
                text=text,
            )

        return variants

    def _parse_skills(self, content: str) -> Tuple[List[str], List[str]]:
        """Parse hard and soft skills from the Skills section."""
        hard_skills = []
        soft_skills = []

        # Find Skills section
        skills_section_match = re.search(
            r"## Skills\s*\n(.+?)(?=\n## |\Z)",
            content,
            re.DOTALL
        )
        if not skills_section_match:
            return hard_skills, soft_skills

        skills_content = skills_section_match.group(1)

        # Extract hard skills
        hard_match = self.HARD_SKILLS_PATTERN.search(skills_content)
        if hard_match:
            skills_text = hard_match.group(1).strip()
            hard_skills = [s.strip() for s in skills_text.split(",") if s.strip()]

        # Extract soft skills
        soft_match = self.SOFT_SKILLS_PATTERN.search(skills_content)
        if soft_match:
            skills_text = soft_match.group(1).strip()
            soft_skills = [s.strip() for s in skills_text.split(",") if s.strip()]

        return hard_skills, soft_skills

    def _parse_selection_guide(self, content: str) -> Optional[SelectionGuide]:
        """Parse the selection guide table from the content."""
        guide_match = self.SELECTION_GUIDE_PATTERN.search(content)
        if not guide_match:
            return None

        table_rows = guide_match.group(1)
        mappings = {}

        # Parse each row of the table
        for row_match in re.finditer(r"\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|", table_rows):
            jd_emphasis = row_match.group(1).strip()
            achievements_text = row_match.group(2).strip()

            # Skip header-like rows
            if jd_emphasis.startswith("-") or jd_emphasis == "JD Emphasis":
                continue

            # Parse achievement numbers (e.g., "1, 4" or "1, 2, 6")
            achievement_ids = []
            for num_match in re.finditer(r"(\d+)", achievements_text):
                achievement_ids.append(f"achievement_{num_match.group(1)}")

            if achievement_ids:
                mappings[jd_emphasis] = achievement_ids

        return SelectionGuide(mappings=mappings) if mappings else None

    def _parse_legacy_format(self, content: str, role_id: str) -> EnhancedRoleData:
        """
        Fallback parsing for legacy simple bullet format.

        Creates an EnhancedRoleData with a single "Original" variant per achievement.
        """
        metadata = self._parse_metadata(content, role_id)
        hard_skills, soft_skills = self._parse_skills(content)

        # Parse simple bullets from Achievements section
        achievements = []
        in_achievements = False
        achievement_num = 0

        for line in content.split("\n"):
            line = line.strip()

            if line == "## Achievements":
                in_achievements = True
                continue
            elif line.startswith("## "):
                in_achievements = False
                continue

            if in_achievements and line.startswith("•"):
                achievement_num += 1
                bullet_text = line[1:].strip()

                # Create a simple achievement with one variant
                achievement = Achievement(
                    id=f"achievement_{achievement_num}",
                    title=f"Achievement {achievement_num}",
                    core_fact=bullet_text,
                    variants={
                        "Original": AchievementVariant(
                            variant_type="Original",
                            text=bullet_text,
                        )
                    },
                    keywords=[],
                )
                achievements.append(achievement)

        return EnhancedRoleData(
            id=role_id,
            metadata=metadata,
            achievements=achievements,
            hard_skills=hard_skills,
            soft_skills=soft_skills,
            selection_guide=None,
            raw_content=content,
        )

    def parse_all_roles(self, roles_dir: Path) -> Dict[str, EnhancedRoleData]:
        """
        Parse all role files in a directory.

        Args:
            roles_dir: Path to the roles directory

        Returns:
            Dictionary mapping role_id to EnhancedRoleData
        """
        if not roles_dir.exists():
            raise FileNotFoundError(f"Roles directory not found: {roles_dir}")

        roles = {}
        for role_file in sorted(roles_dir.glob("*.md")):
            try:
                role_data = self.parse_role_file(role_file)
                roles[role_data.id] = role_data
            except Exception as e:
                self._logger.error(f"Failed to parse {role_file}: {e}")

        self._logger.info(f"Parsed {len(roles)} role files from {roles_dir}")
        return roles


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def parse_role_file(file_path: Path) -> EnhancedRoleData:
    """
    Convenience function to parse a single role file.

    Args:
        file_path: Path to the role markdown file

    Returns:
        EnhancedRoleData with all parsed information
    """
    parser = VariantParser()
    return parser.parse_role_file(file_path)


def parse_all_roles(roles_dir: Path = None) -> Dict[str, EnhancedRoleData]:
    """
    Convenience function to parse all role files.

    Args:
        roles_dir: Path to roles directory (defaults to data/master-cv/roles)

    Returns:
        Dictionary mapping role_id to EnhancedRoleData
    """
    if roles_dir is None:
        roles_dir = Path("data/master-cv/roles")

    parser = VariantParser()
    return parser.parse_all_roles(roles_dir)
