"""
Data types for Layer 6 V2: Multi-Stage CV Generation.

These types represent the intermediate outputs of the CV generation pipeline:
- GeneratedBullet: A single tailored achievement bullet with traceability
- RoleBullets: All bullets for a role plus QA metadata
- QAResult: Hallucination detection results
- ATSResult: ATS keyword coverage metrics
- StitchedRole: A role after deduplication
- StitchedCV: The combined CV experience section
- DeduplicationResult: Report of what was deduplicated
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class GeneratedBullet:
    """
    A single generated CV bullet with full traceability.

    Each bullet tracks:
    - The generated text optimized for the JD (in STAR format)
    - The source text it was derived from (for hallucination QA)
    - Metrics and keywords used (for verification)
    - Pain points addressed (for JD alignment)
    - STAR components for structure validation (GAP-005)
    """

    text: str                          # Generated bullet text (20-35 words, STAR format)
    source_text: str                   # Original achievement from role file
    source_metric: Optional[str] = None       # Exact metric from source (for verification)
    jd_keyword_used: Optional[str] = None     # JD keyword integrated (or None)
    pain_point_addressed: Optional[str] = None  # Pain point addressed (or None)
    # STAR components (GAP-005)
    situation: Optional[str] = None    # Challenge/context that prompted the action
    action: Optional[str] = None       # What was done including skills/technologies
    result: Optional[str] = None       # Quantified outcome achieved
    word_count: int = 0                # Word count of generated text

    def __post_init__(self):
        """Calculate word count if not provided."""
        if self.word_count == 0:
            self.word_count = len(self.text.split())

    @property
    def has_star_components(self) -> bool:
        """Check if bullet has all STAR components populated."""
        return bool(self.situation and self.action and self.result)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "source_text": self.source_text,
            "source_metric": self.source_metric,
            "jd_keyword_used": self.jd_keyword_used,
            "pain_point_addressed": self.pain_point_addressed,
            "situation": self.situation,
            "action": self.action,
            "result": self.result,
            "word_count": self.word_count,
        }


@dataclass
class STARResult:
    """
    Result of STAR format validation for a role's bullets (GAP-005).

    Verifies that all generated bullets follow the STAR structure:
    - Situation: Context/challenge that prompted the action
    - Task: (implicit in action) What needed to be done
    - Action: What was done with skills/technologies
    - Result: Quantified outcome achieved
    """

    passed: bool                       # Overall pass/fail
    bullets_with_star: int             # Number of bullets with complete STAR
    bullets_without_star: int          # Number of bullets missing STAR elements
    missing_elements: List[str]        # Specific missing elements (e.g., "Bullet 1: missing situation")
    star_coverage: float               # Ratio of bullets with complete STAR (0-1)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "bullets_with_star": self.bullets_with_star,
            "bullets_without_star": self.bullets_without_star,
            "missing_elements": self.missing_elements,
            "star_coverage": self.star_coverage,
        }


@dataclass
class QAResult:
    """
    Result of hallucination QA check for a role.

    Verifies that all generated content is grounded in the source role file.
    """

    passed: bool                       # Overall pass/fail
    flagged_bullets: List[str]         # Bullets that failed verification
    issues: List[str]                  # Specific issues found (e.g., "Metric 75% not in source")
    verified_metrics: List[str]        # Metrics that were verified in source
    confidence: float                  # Confidence score 0-1
    star_result: Optional["STARResult"] = None  # STAR format validation result (GAP-005)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "flagged_bullets": self.flagged_bullets,
            "issues": self.issues,
            "verified_metrics": self.verified_metrics,
            "confidence": self.confidence,
            "star_result": self.star_result.to_dict() if self.star_result else None,
        }


@dataclass
class ATSResult:
    """
    Result of ATS keyword coverage check.

    Measures how many target JD keywords were naturally integrated.
    """

    keywords_found: List[str]          # Keywords present in bullets
    keywords_missing: List[str]        # Keywords not yet used
    coverage_ratio: float              # found / total (0-1)
    suggestions: List[str]             # Suggestions for missing keywords

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "keywords_found": self.keywords_found,
            "keywords_missing": self.keywords_missing,
            "coverage_ratio": self.coverage_ratio,
            "suggestions": self.suggestions,
        }


@dataclass
class RoleBullets:
    """
    Generated bullets for a single role with QA metadata.

    Represents the output of processing one role from the master CV,
    including generated bullets and quality assurance results.
    """

    role_id: str                       # e.g., "01_seven_one_entertainment"
    company: str                       # Company name
    title: str                         # Job title at that company
    period: str                        # Date range (e.g., "2020–Present")
    bullets: List[GeneratedBullet]     # Tailored achievement bullets
    location: str = ""                 # Location (e.g., "Munich, DE")
    word_count: int = 0                # Total words across all bullets
    keywords_integrated: List[str] = field(default_factory=list)  # JD keywords used
    hard_skills: List[str] = field(default_factory=list)  # Technical skills from role
    soft_skills: List[str] = field(default_factory=list)  # Soft skills from role
    qa_result: Optional[QAResult] = None      # Hallucination check result
    ats_result: Optional[ATSResult] = None    # ATS keyword check result

    def __post_init__(self):
        """Calculate total word count if not provided."""
        if self.word_count == 0:
            self.word_count = sum(b.word_count for b in self.bullets)

    @property
    def bullet_count(self) -> int:
        """Return number of bullets."""
        return len(self.bullets)

    @property
    def bullet_texts(self) -> List[str]:
        """Return just the bullet text strings."""
        return [b.text for b in self.bullets]

    @property
    def qa_passed(self) -> bool:
        """Check if QA passed (or not yet run)."""
        return self.qa_result is None or self.qa_result.passed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "role_id": self.role_id,
            "company": self.company,
            "title": self.title,
            "period": self.period,
            "location": self.location,
            "bullets": [b.to_dict() for b in self.bullets],
            "bullet_count": self.bullet_count,
            "word_count": self.word_count,
            "keywords_integrated": self.keywords_integrated,
            "hard_skills": self.hard_skills,
            "soft_skills": self.soft_skills,
            "qa_result": self.qa_result.to_dict() if self.qa_result else None,
            "ats_result": self.ats_result.to_dict() if self.ats_result else None,
        }


@dataclass
class CareerContext:
    """
    Career stage context for a role being processed.

    Provides guidance on how to emphasize the role based on its
    position in the candidate's career and the target role category.
    """

    role_index: int                    # 0-indexed position (0 = current role)
    total_roles: int                   # Total number of roles
    is_current: bool                   # Whether this is the current role
    career_stage: str                  # "recent" | "mid-career" | "early"
    target_role_category: str          # JD role category
    emphasis_guidance: str             # Specific guidance for this role

    @classmethod
    def build(
        cls,
        role_index: int,
        total_roles: int,
        is_current: bool,
        target_role_category: str,
    ) -> "CareerContext":
        """
        Build career context with appropriate emphasis guidance.

        Emphasis rules:
        - Current role (index 0): Maximum detail, strongest JD alignment
        - Recent roles (index 1-2): Good detail, moderate JD alignment
        - Early career (index 3+): Summarized, foundation-building focus
        """
        # Determine career stage
        if role_index == 0:
            career_stage = "recent"
        elif role_index <= 2:
            career_stage = "mid-career"
        else:
            career_stage = "early"

        # Build emphasis guidance based on stage and target category
        if career_stage == "recent":
            if "manager" in target_role_category or "director" in target_role_category:
                emphasis = (
                    "MAXIMUM emphasis on leadership, team impact, strategic outcomes. "
                    "Show progression to management. Include specific team sizes and "
                    "business metrics. This is your headline role."
                )
            elif "principal" in target_role_category or "staff" in target_role_category:
                emphasis = (
                    "MAXIMUM emphasis on technical depth, architecture decisions, "
                    "cross-team influence. Show IC leadership without management. "
                    "Include system scale and performance metrics."
                )
            else:  # CTO or head of engineering
                emphasis = (
                    "MAXIMUM emphasis on org building, technology vision, business "
                    "transformation. Show executive-level impact. Include company-wide "
                    "metrics and strategic outcomes."
                )
        elif career_stage == "mid-career":
            emphasis = (
                "MODERATE detail showing skill development and growing responsibility. "
                "Focus on achievements that build foundation for current role. "
                "3-4 strong bullets per role."
            )
        else:  # early career
            emphasis = (
                "BRIEF summary showing technical foundation. 2-3 bullets max. "
                "Focus on skills that remain relevant. OK to omit if space-constrained."
            )

        return cls(
            role_index=role_index,
            total_roles=total_roles,
            is_current=is_current,
            career_stage=career_stage,
            target_role_category=target_role_category,
            emphasis_guidance=emphasis,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "role_index": self.role_index,
            "total_roles": self.total_roles,
            "is_current": self.is_current,
            "career_stage": self.career_stage,
            "target_role_category": self.target_role_category,
            "emphasis_guidance": self.emphasis_guidance,
        }


# ===== PHASE 4: STITCHER TYPES =====

@dataclass
class DuplicatePair:
    """
    A pair of bullets detected as semantically similar.

    Used for deduplication decisions - keeps the more recent role's version.
    """

    bullet1_text: str                  # Bullet from earlier role
    bullet1_role_index: int            # Index of earlier role
    bullet2_text: str                  # Bullet from later role (kept)
    bullet2_role_index: int            # Index of later role (kept)
    similarity_score: float            # Similarity score (0-1)
    reason: str                        # Why they're similar

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "bullet1_text": self.bullet1_text,
            "bullet1_role_index": self.bullet1_role_index,
            "bullet2_text": self.bullet2_text,
            "bullet2_role_index": self.bullet2_role_index,
            "similarity_score": self.similarity_score,
            "reason": self.reason,
        }


@dataclass
class DeduplicationResult:
    """
    Report of cross-role deduplication.

    Tracks what was removed and why for transparency.
    """

    original_bullet_count: int         # Before deduplication
    final_bullet_count: int            # After deduplication
    removed_count: int                 # Number of bullets removed
    duplicate_pairs: List[DuplicatePair]  # Pairs that were deduplicated
    compression_applied: bool          # Whether word budget compression was needed

    @property
    def dedup_ratio(self) -> float:
        """Ratio of bullets removed."""
        if self.original_bullet_count == 0:
            return 0.0
        return self.removed_count / self.original_bullet_count

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "original_bullet_count": self.original_bullet_count,
            "final_bullet_count": self.final_bullet_count,
            "removed_count": self.removed_count,
            "dedup_ratio": self.dedup_ratio,
            "duplicate_pairs": [p.to_dict() for p in self.duplicate_pairs],
            "compression_applied": self.compression_applied,
        }


@dataclass
class StitchedRole:
    """
    A role after stitching and deduplication.

    Contains final bullet texts (not GeneratedBullet objects) for output.
    """

    role_id: str
    company: str
    title: str
    location: str
    period: str
    bullets: List[str]                 # Final bullet text strings
    skills: List[str] = field(default_factory=list)  # Combined skills for this role
    word_count: int = 0

    def __post_init__(self):
        """Calculate word count if not provided."""
        if self.word_count == 0:
            self.word_count = sum(len(b.split()) for b in self.bullets)

    @property
    def bullet_count(self) -> int:
        """Return number of bullets."""
        return len(self.bullets)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "role_id": self.role_id,
            "company": self.company,
            "title": self.title,
            "location": self.location,
            "period": self.period,
            "bullets": self.bullets,
            "skills": self.skills,
            "bullet_count": self.bullet_count,
            "word_count": self.word_count,
        }

    def to_markdown(self) -> str:
        """Convert to formatted text for CV output with bold company/title header."""
        lines = [
            f"**{self.company} • {self.title}** | {self.location} | {self.period}",
            "",
        ]
        for bullet in self.bullets:
            lines.append(f"• {bullet}")
        # Add skills line if available
        if self.skills:
            skills_str = ", ".join(self.skills[:8])  # Limit to 8 skills
            lines.append(f"**Skills:** {skills_str}")
        return "\n".join(lines)


@dataclass
class StitchedCV:
    """
    The combined CV experience section after stitching.

    Contains all roles in chronological order (most recent first),
    with deduplication applied and word budget enforced.
    """

    roles: List[StitchedRole]          # Roles in order (most recent first)
    total_word_count: int = 0          # Total words across all roles
    total_bullet_count: int = 0        # Total bullets across all roles
    keywords_coverage: List[str] = field(default_factory=list)  # Keywords present
    deduplication_result: Optional[DeduplicationResult] = None

    def __post_init__(self):
        """Calculate totals if not provided."""
        if self.total_word_count == 0:
            self.total_word_count = sum(r.word_count for r in self.roles)
        if self.total_bullet_count == 0:
            self.total_bullet_count = sum(r.bullet_count for r in self.roles)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "roles": [r.to_dict() for r in self.roles],
            "total_word_count": self.total_word_count,
            "total_bullet_count": self.total_bullet_count,
            "keywords_coverage": self.keywords_coverage,
            "deduplication_result": (
                self.deduplication_result.to_dict()
                if self.deduplication_result else None
            ),
        }

    def to_markdown(self) -> str:
        """Convert to markdown format for CV output."""
        sections = []
        for role in self.roles:
            sections.append(role.to_markdown())
        return "\n\n".join(sections)


# ===== PHASE 5: HEADER GENERATOR TYPES =====

# ----- Skills Taxonomy Types (Role-Based Skills Selection) -----

@dataclass
class TaxonomySection:
    """
    A pre-defined skill section from the role skills taxonomy.

    Each section represents a category of skills appropriate for a target role,
    with JD signals to help determine when to include this section.
    """

    name: str                          # Section name (e.g., "Technical Leadership")
    priority: int                      # Default priority (1 = highest)
    description: str                   # Description of what this section covers
    skills: List[str]                  # Pre-curated skills for this section
    jd_signals: List[str]              # Keywords that indicate this section is relevant

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "priority": self.priority,
            "description": self.description,
            "skills": self.skills,
            "jd_signals": self.jd_signals,
        }


@dataclass
class RoleSkillsTaxonomy:
    """
    Complete skills taxonomy for a target role.

    Contains multiple sections with their skills, plus configuration
    for how many sections/skills to include in the final CV.
    """

    role_category: str                 # e.g., "engineering_manager"
    display_name: str                  # e.g., "Engineering Manager"
    sections: List[TaxonomySection]    # Pre-defined sections for this role
    max_sections: int = 4              # Maximum sections to include in CV
    max_skills_per_section: int = 6    # Maximum skills per section
    lax_multiplier: float = 1.3        # Multiplier for "lax" generation (1.3 = 30% more)

    @property
    def all_skills(self) -> List[str]:
        """Return all skills across all sections."""
        skills = []
        for section in self.sections:
            skills.extend(section.skills)
        return skills

    @property
    def section_names(self) -> List[str]:
        """Return all section names."""
        return [s.name for s in self.sections]

    def get_section_by_name(self, name: str) -> Optional["TaxonomySection"]:
        """Get a section by its name (case-insensitive)."""
        for section in self.sections:
            if section.name.lower() == name.lower():
                return section
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "role_category": self.role_category,
            "display_name": self.display_name,
            "sections": [s.to_dict() for s in self.sections],
            "max_sections": self.max_sections,
            "max_skills_per_section": self.max_skills_per_section,
            "lax_multiplier": self.lax_multiplier,
        }


@dataclass
class SectionScore:
    """
    Score for a taxonomy section based on JD alignment.

    Used to rank sections for selection during skills generation.
    """

    section: TaxonomySection           # The section being scored
    jd_keyword_score: float            # Score from JD keyword overlap (0-1)
    responsibility_score: float        # Score from JD responsibility match (0-1)
    priority_score: float              # Score from section priority (0-1)
    total_score: float = 0.0           # Weighted total score

    def __post_init__(self):
        """Calculate total score if not provided."""
        if self.total_score == 0.0:
            # Weights: 50% keyword, 30% responsibility, 20% priority
            self.total_score = (
                0.5 * self.jd_keyword_score +
                0.3 * self.responsibility_score +
                0.2 * self.priority_score
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "section_name": self.section.name,
            "jd_keyword_score": self.jd_keyword_score,
            "responsibility_score": self.responsibility_score,
            "priority_score": self.priority_score,
            "total_score": self.total_score,
        }


@dataclass
class SkillScore:
    """
    Score for an individual skill based on JD alignment and evidence.

    Used to rank skills within a section for selection.
    """

    skill: str                         # The skill being scored
    jd_match_score: float              # 1.0 if in JD keywords, else 0.0
    evidence_score: float              # Based on evidence frequency (0-1)
    recency_score: float               # Based on how recently used (0-1)
    total_score: float = 0.0           # Weighted total score

    def __post_init__(self):
        """Calculate total score if not provided."""
        if self.total_score == 0.0:
            # Weights: 40% JD match, 30% evidence, 30% recency
            self.total_score = (
                0.4 * self.jd_match_score +
                0.3 * self.evidence_score +
                0.3 * self.recency_score
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "skill": self.skill,
            "jd_match_score": self.jd_match_score,
            "evidence_score": self.evidence_score,
            "recency_score": self.recency_score,
            "total_score": self.total_score,
        }


# ----- Original Header Generator Types -----

@dataclass
class SkillEvidence:
    """
    Maps a skill to the bullet(s) that evidence it.

    Ensures every skill in the final CV is grounded in achievements.
    """

    skill: str                         # The skill (e.g., "Kubernetes", "Team Leadership")
    evidence_bullets: List[str]        # Bullet text(s) that demonstrate this skill
    source_roles: List[str]            # Which roles the evidence comes from
    is_jd_keyword: bool = False        # Whether this is a JD target keyword

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "skill": self.skill,
            "evidence_bullets": self.evidence_bullets,
            "source_roles": self.source_roles,
            "is_jd_keyword": self.is_jd_keyword,
        }


@dataclass
class SkillsSection:
    """
    A category of skills with grounding evidence.

    Categories follow the CV guide:
    - Leadership: Team building, mentorship, hiring
    - Technical: Languages, frameworks, architectures
    - Platform: Cloud, DevOps, infrastructure
    - Delivery: Agile, processes, shipping
    """

    category: str                      # "Leadership" | "Technical" | "Platform" | "Delivery"
    skills: List[SkillEvidence]        # Skills in this category with evidence

    @property
    def skill_count(self) -> int:
        """Return number of skills in this category."""
        return len(self.skills)

    @property
    def skill_names(self) -> List[str]:
        """Return just the skill names."""
        return [s.skill for s in self.skills]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "category": self.category,
            "skills": [s.to_dict() for s in self.skills],
            "skill_count": self.skill_count,
        }

    def to_markdown(self) -> str:
        """Convert to formatted text for CV output with bold category titles."""
        skill_names = ", ".join(self.skill_names)
        return f"**{self.category}:** {skill_names}"


@dataclass
class ProfileOutput:
    """
    Research-aligned profile summary for senior technical leadership.

    Based on research from 625 hiring managers and eye-tracking studies:
    - Profile receives 80% of initial attention
    - First 7.4 seconds determine continue/reject decision
    - Candidates with exact job title are 10.6x more likely to get interviews

    Structure follows the hybrid approach:
    - Headline: "[EXACT TITLE] | [YEARS] Years Technology Leadership"
    - Narrative: 3-5 sentences (100-150 words) following 60/30/10 formula
    - Core Competencies: 6-8 ATS-optimized keyword bullets

    The narrative must answer 4 questions:
    1. Who are you professionally? (Identity)
    2. What problems can you solve? (Relevance)
    3. What proof do you have? (Evidence)
    4. Why should they call you? (Differentiation)
    """

    # Core content - new research-aligned structure
    headline: str = ""                 # "[EXACT TITLE] | [YEARS] Years Technology Leadership"
    narrative: str = ""                # 3-5 sentence paragraph (100-150 words)
    core_competencies: List[str] = field(default_factory=list)  # 6-8 ATS keyword bullets

    # Grounding evidence
    highlights_used: List[str] = field(default_factory=list)  # Quantified achievements referenced
    keywords_integrated: List[str] = field(default_factory=list)  # JD keywords naturally included
    exact_title_used: str = ""         # The exact JD title incorporated in headline

    # Validation - tracks if all 4 questions are answered
    answers_who: bool = False          # Identity and level
    answers_what_problems: bool = False  # Relevance to their needs
    answers_proof: bool = False        # Evidence of impact (metrics)
    answers_why_you: bool = False      # Differentiation

    # Configuration
    word_count: int = 0
    regional_variant: str = "us_eu"    # "us_eu" | "gulf"

    # Legacy field for backward compatibility
    _legacy_text: str = ""

    def __post_init__(self):
        """Calculate word count and ensure backward compatibility."""
        # Calculate word count from narrative (primary content)
        if self.word_count == 0 and self.narrative:
            self.word_count = len(self.narrative.split())
        # If no word count yet but legacy text exists, use that
        elif self.word_count == 0 and self._legacy_text:
            self.word_count = len(self._legacy_text.split())

    @property
    def text(self) -> str:
        """Combined text for backward compatibility."""
        if self.narrative:
            return self.narrative
        return self._legacy_text

    @text.setter
    def text(self, value: str):
        """Allow setting text for backward compatibility."""
        self._legacy_text = value
        if not self.narrative:
            self.narrative = value
        if self.word_count == 0:
            self.word_count = len(value.split())

    @property
    def all_four_questions_answered(self) -> bool:
        """Check if profile answers all 4 hiring manager questions."""
        return all([
            self.answers_who,
            self.answers_what_problems,
            self.answers_proof,
            self.answers_why_you,
        ])

    @property
    def formatted_header(self) -> str:
        """Return ATS-optimized header with Professional Summary title."""
        if not self.headline:
            return "PROFESSIONAL SUMMARY"
        return f"PROFESSIONAL SUMMARY\n{self.headline}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "headline": self.headline,
            "narrative": self.narrative,
            "core_competencies": self.core_competencies,
            "text": self.text,  # Legacy compatibility
            "highlights_used": self.highlights_used,
            "keywords_integrated": self.keywords_integrated,
            "exact_title_used": self.exact_title_used,
            "word_count": self.word_count,
            "regional_variant": self.regional_variant,
            "answers_who": self.answers_who,
            "answers_what_problems": self.answers_what_problems,
            "answers_proof": self.answers_proof,
            "answers_why_you": self.answers_why_you,
            "all_four_questions_answered": self.all_four_questions_answered,
        }

    @classmethod
    def from_legacy(
        cls,
        text: str,
        highlights_used: List[str],
        keywords_integrated: List[str],
    ) -> "ProfileOutput":
        """Create ProfileOutput from legacy format for backward compatibility."""
        return cls(
            narrative=text,
            _legacy_text=text,
            highlights_used=highlights_used,
            keywords_integrated=keywords_integrated,
            word_count=len(text.split()),
        )

    # ===== ATS OPTIMIZATION VALIDATION METHODS =====

    # Common acronyms that should have full form included (ATS guide requirement)
    ATS_ACRONYMS = {
        "AWS": "Amazon Web Services",
        "GCP": "Google Cloud Platform",
        "CI/CD": "Continuous Integration/Continuous Deployment",
        "SRE": "Site Reliability Engineering",
        "ML": "Machine Learning",
        "AI": "Artificial Intelligence",
        "API": "Application Programming Interface",
        "SDK": "Software Development Kit",
        "MVP": "Minimum Viable Product",
        "OKR": "Objectives and Key Results",
        "KPI": "Key Performance Indicator",
        "ETL": "Extract, Transform, Load",
        "SQL": "Structured Query Language",
        "NoSQL": "Not Only SQL",
        "REST": "Representational State Transfer",
        "IaC": "Infrastructure as Code",
        "VP": "Vice President",
        "CTO": "Chief Technology Officer",
        "CEO": "Chief Executive Officer",
        "COO": "Chief Operating Officer",
        "MBA": "Master of Business Administration",
        "PMP": "Project Management Professional",
        "SEO": "Search Engine Optimization",
    }

    def check_acronym_expansion(self) -> Dict[str, Any]:
        """
        Check if common acronyms have their full form included.

        ATS Guide Finding: Greenhouse, Lever, Taleo do NOT recognize
        abbreviations as equivalent to full terms. Always include both.

        Returns:
            Dict with 'expanded' (good), 'missing_expansion' (needs fix),
            and 'ats_score' (0-100)
        """
        import re
        combined_text = f"{self.headline} {self.narrative} {' '.join(self.core_competencies)}"

        expanded = []
        missing_expansion = []

        for acronym, full_form in self.ATS_ACRONYMS.items():
            # Check if acronym appears in text
            if re.search(rf'\b{re.escape(acronym)}\b', combined_text, re.IGNORECASE):
                # Check if full form also appears (or the pattern "Full Form (ACRONYM)")
                full_pattern = rf'{re.escape(full_form)}|{re.escape(full_form)}\s*\({re.escape(acronym)}\)'
                if re.search(full_pattern, combined_text, re.IGNORECASE):
                    expanded.append(acronym)
                else:
                    missing_expansion.append(acronym)

        total_acronyms = len(expanded) + len(missing_expansion)
        ats_score = 100 if total_acronyms == 0 else int((len(expanded) / total_acronyms) * 100)

        return {
            "expanded": expanded,
            "missing_expansion": missing_expansion,
            "ats_score": ats_score,
            "recommendation": (
                f"Add full forms for: {', '.join(missing_expansion)}"
                if missing_expansion else "All acronyms properly expanded"
            ),
        }

    def check_keyword_frequency(self, target_keywords: List[str]) -> Dict[str, Any]:
        """
        Check if target keywords appear with optimal frequency.

        ATS Guide Finding: Greenhouse ranks resumes with more mentions of
        a keyword higher. Aim for 2-3 natural repetitions of key terms.

        Args:
            target_keywords: List of keywords to check frequency for

        Returns:
            Dict with keyword counts and ATS optimization score
        """
        import re
        combined_text = f"{self.headline} {self.narrative} {' '.join(self.core_competencies)}"
        combined_lower = combined_text.lower()

        keyword_counts = {}
        optimal_count = 0  # Keywords appearing 2-3 times
        single_count = 0   # Keywords appearing only once
        missing_count = 0  # Keywords not appearing

        for keyword in target_keywords:
            count = len(re.findall(rf'\b{re.escape(keyword.lower())}\b', combined_lower))
            keyword_counts[keyword] = count

            if count >= 2:
                optimal_count += 1
            elif count == 1:
                single_count += 1
            else:
                missing_count += 1

        total = len(target_keywords)
        ats_score = 0 if total == 0 else int(
            ((optimal_count * 1.0 + single_count * 0.5) / total) * 100
        )

        return {
            "keyword_counts": keyword_counts,
            "optimal_frequency": [k for k, v in keyword_counts.items() if v >= 2],
            "single_mention": [k for k, v in keyword_counts.items() if v == 1],
            "missing": [k for k, v in keyword_counts.items() if v == 0],
            "ats_score": min(ats_score, 100),
        }

    def check_scale_metrics(self) -> Dict[str, Any]:
        """
        Check if profile includes quantifiable scale metrics.

        ATS Guide Finding: Numbers read perfectly to ATS AND recruiters.
        Include team sizes, revenue impact, user scale, budget responsibility.

        Returns:
            Dict with found metrics and recommendations
        """
        import re
        combined_text = f"{self.headline} {self.narrative}"

        # Patterns for different metric types
        patterns = {
            "team_size": r'\b(\d+)\+?\s*(?:engineers?|developers?|team members?|reports?|people)',
            "revenue": r'\$[\d,.]+[MBK]?\+?\s*(?:revenue|ARR|annual)',
            "users": r'[\d,.]+[MBK]?\+?\s*(?:users?|customers?|MAU|DAU)',
            "scale": r'[\d,.]+[MBK]?\+?\s*(?:requests?|transactions?|QPS|TPS|RPS)',
            "budget": r'\$[\d,.]+[MBK]?\+?\s*(?:budget|spend|investment)',
            "percentage": r'\d+(?:\.\d+)?%',
            "years": r'(\d+)\+?\s*years?',
        }

        found_metrics = {}
        for metric_type, pattern in patterns.items():
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            if matches:
                found_metrics[metric_type] = matches

        metric_types_found = len(found_metrics)
        ats_score = min(metric_types_found * 20, 100)  # 20 points per metric type, max 100

        recommendations = []
        if "team_size" not in found_metrics:
            recommendations.append("Add team size (e.g., 'team of 25+ engineers')")
        if "revenue" not in found_metrics and "budget" not in found_metrics:
            recommendations.append("Add revenue/budget impact (e.g., '$100M+ revenue')")
        if "percentage" not in found_metrics:
            recommendations.append("Add percentage improvements (e.g., '40% efficiency gain')")

        return {
            "found_metrics": found_metrics,
            "metric_types_count": metric_types_found,
            "ats_score": ats_score,
            "recommendations": recommendations if recommendations else ["Good metric coverage"],
        }

    def get_ats_optimization_report(self, target_keywords: List[str] = None) -> Dict[str, Any]:
        """
        Generate comprehensive ATS optimization report for the profile.

        Combines all ATS checks into a single actionable report.

        Args:
            target_keywords: Optional list of JD keywords to check frequency

        Returns:
            Dict with overall ATS score and detailed breakdowns
        """
        acronym_check = self.check_acronym_expansion()
        scale_check = self.check_scale_metrics()
        keyword_check = self.check_keyword_frequency(target_keywords or self.keywords_integrated)

        # Calculate overall ATS score (weighted average)
        overall_score = int(
            acronym_check["ats_score"] * 0.3 +
            scale_check["ats_score"] * 0.3 +
            keyword_check["ats_score"] * 0.4
        )

        return {
            "overall_ats_score": overall_score,
            "word_count": self.word_count,
            "word_count_optimal": 100 <= self.word_count <= 150,
            "four_questions_answered": self.all_four_questions_answered,
            "acronym_expansion": acronym_check,
            "scale_metrics": scale_check,
            "keyword_frequency": keyword_check,
            "headline_present": bool(self.headline),
            "core_competencies_count": len(self.core_competencies),
        }


@dataclass
class ValidationResult:
    """
    Result of skills grounding validation.

    Ensures no ungrounded skills appear in the final CV.
    """

    passed: bool                       # Whether all skills are grounded
    grounded_skills: List[str]         # Skills with evidence
    ungrounded_skills: List[str]       # Skills without evidence (should be removed)
    evidence_map: Dict[str, List[str]] # skill -> bullets that evidence it

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "grounded_skills": self.grounded_skills,
            "ungrounded_skills": self.ungrounded_skills,
            "evidence_map": self.evidence_map,
        }


@dataclass
class HeaderOutput:
    """
    Complete header output including profile, skills, and education.

    Represents the non-experience sections of the CV, all grounded
    in the stitched achievements section.
    """

    profile: ProfileOutput             # 2-3 sentence summary
    skills_sections: List[SkillsSection]  # Leadership, Technical, Platform, Delivery
    education: List[str]               # Education entries (from metadata)
    contact_info: Dict[str, str]       # name, email, phone, linkedin
    certifications: List[str] = field(default_factory=list)  # Professional certifications
    languages: List[str] = field(default_factory=list)       # Language proficiencies
    validation_result: Optional[ValidationResult] = None

    @property
    def total_skills_count(self) -> int:
        """Return total number of skills across all categories."""
        return sum(s.skill_count for s in self.skills_sections)

    @property
    def all_skill_names(self) -> List[str]:
        """Return all skill names across all categories."""
        names = []
        for section in self.skills_sections:
            names.extend(section.skill_names)
        return names

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "profile": self.profile.to_dict(),
            "skills_sections": [s.to_dict() for s in self.skills_sections],
            "education": self.education,
            "contact_info": self.contact_info,
            "certifications": self.certifications,
            "languages": self.languages,
            "total_skills_count": self.total_skills_count,
            "validation_result": (
                self.validation_result.to_dict()
                if self.validation_result else None
            ),
        }

    def to_markdown(self) -> str:
        """
        Convert to ATS-optimized plain text format for CV header.

        Research-aligned structure:
        - "PROFESSIONAL SUMMARY" header (ATS universal recognition)
        - Headline with exact job title + years (10.6x interview factor)
        - Narrative paragraph (100-150 words, 60/30/10 formula)
        - Core Competencies as keyword bullets (hybrid scannability)
        """
        lines = []

        # Contact info header
        name = self.contact_info.get("name", "")
        email = self.contact_info.get("email", "")
        phone = self.contact_info.get("phone", "")
        linkedin = self.contact_info.get("linkedin", "")
        location = self.contact_info.get("location", "")

        lines.append(name)
        contact_parts = [p for p in [email, phone, linkedin, location] if p]
        lines.append(" | ".join(contact_parts))
        lines.append("")

        # Professional Summary (ATS-optimized header)
        lines.append("PROFESSIONAL SUMMARY")

        # Add headline if available (research: exact title + years)
        if self.profile.headline:
            lines.append(self.profile.headline)
            lines.append("")

        # Narrative paragraph (100-150 words)
        lines.append(self.profile.text)
        lines.append("")

        # Core Competencies - inline format for ATS (from profile if available)
        if self.profile.core_competencies:
            competencies_str = " | ".join(self.profile.core_competencies)
            lines.append(f"Core Competencies: {competencies_str}")
            lines.append("")

        # Skills sections (detailed breakdown)
        lines.append("SKILLS & EXPERTISE")
        for section in self.skills_sections:
            lines.append(section.to_markdown())
        lines.append("")

        # Education
        if self.education:
            lines.append("EDUCATION")
            for edu in self.education:
                lines.append(f"• {edu}")
            lines.append("")

        # Certifications (if any)
        if self.certifications:
            lines.append("CERTIFICATIONS")
            for cert in self.certifications:
                lines.append(f"• {cert}")
            lines.append("")

        # Languages (if any)
        if self.languages:
            lines.append("LANGUAGES")
            lines.append(", ".join(self.languages))

        return "\n".join(lines)


# ===== PHASE 6: GRADER + IMPROVER TYPES =====

@dataclass
class DimensionScore:
    """
    Score for a single grading dimension.

    Each dimension is scored 1-10 with specific feedback.
    """

    dimension: str                     # e.g., "ats_optimization"
    score: float                       # 1-10 score
    weight: float                      # Weight in composite (0-1)
    feedback: str                      # Specific feedback for this dimension
    issues: List[str] = field(default_factory=list)  # Specific issues found
    strengths: List[str] = field(default_factory=list)  # What's working well

    @property
    def weighted_score(self) -> float:
        """Calculate weighted contribution to composite."""
        return self.score * self.weight

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "dimension": self.dimension,
            "score": self.score,
            "weight": self.weight,
            "weighted_score": self.weighted_score,
            "feedback": self.feedback,
            "issues": self.issues,
            "strengths": self.strengths,
        }


@dataclass
class GradeResult:
    """
    Complete grading result for a CV.

    Multi-dimensional grading with weighted composite score.
    Dimensions:
    - ats_optimization (20%): Keyword coverage, format, parsability
    - impact_clarity (25%): Metrics, action verbs, specificity
    - jd_alignment (25%): Pain point coverage, role match, terminology
    - executive_presence (15%): Strategic framing, leadership evidence
    - anti_hallucination (15%): Factual accuracy, grounding in source
    """

    dimension_scores: List[DimensionScore]  # Individual dimension scores
    composite_score: float = 0.0            # Weighted average (1-10)
    passed: bool = False                    # composite >= passing_threshold
    passing_threshold: float = 8.5          # Threshold for passing
    lowest_dimension: str = ""              # Dimension needing most improvement
    improvement_priority: List[str] = field(default_factory=list)  # Ordered list
    exemplary_sections: List[str] = field(default_factory=list)    # What's working

    def __post_init__(self):
        """Calculate composite score and determine lowest dimension."""
        if self.dimension_scores and self.composite_score == 0.0:
            self.composite_score = sum(d.weighted_score for d in self.dimension_scores)
            self.passed = self.composite_score >= self.passing_threshold

            # Find lowest scoring dimension
            if self.dimension_scores:
                sorted_dims = sorted(self.dimension_scores, key=lambda d: d.score)
                self.lowest_dimension = sorted_dims[0].dimension
                self.improvement_priority = [d.dimension for d in sorted_dims]

    @property
    def scores_by_dimension(self) -> Dict[str, float]:
        """Return scores indexed by dimension name."""
        return {d.dimension: d.score for d in self.dimension_scores}

    def get_dimension(self, name: str) -> Optional[DimensionScore]:
        """Get a specific dimension score by name."""
        for d in self.dimension_scores:
            if d.dimension == name:
                return d
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "dimension_scores": [d.to_dict() for d in self.dimension_scores],
            "composite_score": self.composite_score,
            "passed": self.passed,
            "passing_threshold": self.passing_threshold,
            "lowest_dimension": self.lowest_dimension,
            "improvement_priority": self.improvement_priority,
            "exemplary_sections": self.exemplary_sections,
        }


@dataclass
class ImprovementResult:
    """
    Result of CV improvement pass.

    Tracks what was improved and the before/after state.
    """

    improved: bool                     # Whether improvements were made
    target_dimension: str              # Dimension that was targeted
    changes_made: List[str]            # Description of changes
    original_score: float              # Score before improvement
    cv_text: str                       # The improved CV text
    improvement_summary: str = ""      # Brief summary of changes

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "improved": self.improved,
            "target_dimension": self.target_dimension,
            "changes_made": self.changes_made,
            "original_score": self.original_score,
            "improvement_summary": self.improvement_summary,
        }


@dataclass
class FinalCV:
    """
    The complete, final CV after all generation stages.

    Combines header and experience sections with grading results.
    """

    header: HeaderOutput               # Profile, skills, education, contact
    experience: StitchedCV             # Experience section with roles
    grade_result: Optional[GradeResult] = None  # Grading results
    improvement_result: Optional[ImprovementResult] = None  # Improvement results
    version: int = 1                   # Version number (increments with improvements)

    @property
    def total_word_count(self) -> int:
        """Total word count of the CV."""
        header_words = self.header.profile.word_count
        experience_words = self.experience.total_word_count
        return header_words + experience_words

    @property
    def is_passing(self) -> bool:
        """Whether the CV passed grading."""
        return self.grade_result is not None and self.grade_result.passed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "header": self.header.to_dict(),
            "experience": self.experience.to_dict(),
            "grade_result": self.grade_result.to_dict() if self.grade_result else None,
            "improvement_result": (
                self.improvement_result.to_dict()
                if self.improvement_result else None
            ),
            "version": self.version,
            "total_word_count": self.total_word_count,
            "is_passing": self.is_passing,
        }

    def to_markdown(self) -> str:
        """Convert to complete markdown CV."""
        header_md = self.header.to_markdown()
        experience_md = self.experience.to_markdown()

        return f"""{header_md}

## Professional Experience

{experience_md}
"""
