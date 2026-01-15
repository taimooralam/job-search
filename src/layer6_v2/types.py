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
    - Annotation influence for CV personalization (Phase 4)
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
    # Annotation traceability (Phase 4)
    annotation_influenced: bool = False         # Whether annotations affected selection
    annotation_ids: List[str] = field(default_factory=list)  # IDs of influencing annotations
    reframe_applied: Optional[str] = None       # Reframe note that was applied
    annotation_keywords_used: List[str] = field(default_factory=list)  # Keywords from annotations
    annotation_boost: float = 1.0               # Final boost multiplier applied

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
            # Annotation traceability (Phase 4)
            "annotation_influenced": self.annotation_influenced,
            "annotation_ids": self.annotation_ids,
            "reframe_applied": self.reframe_applied,
            "annotation_keywords_used": self.annotation_keywords_used,
            "annotation_boost": self.annotation_boost,
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

# ----- Header Generation V2 Types (Anti-Hallucination) -----


@dataclass
class AchievementSource:
    """
    Tracks the source of a key achievement bullet for traceability.

    V2 Header Generation: Each key achievement in the profile MUST trace back
    to a specific bullet in the master CV. This dataclass provides the proof.

    Anti-hallucination guarantee:
    - bullet_text: The exact text used in the CV
    - source_bullet: The original bullet from role_bullets_summary
    - source_role_id: Which role file it came from
    - match_confidence: How closely it matches (1.0 = exact, 0.8+ = tailored)
    """

    bullet_text: str                           # The text shown in CV key achievements
    source_bullet: str                         # Original bullet from master CV
    source_role_id: str                        # e.g., "01_seven_one_entertainment"
    source_role_title: str                     # e.g., "Head of Software Development"
    match_confidence: float = 1.0              # 1.0 = exact, 0.8+ = tailored version
    tailoring_applied: bool = False            # Whether LLM tailored the bullet
    tailoring_changes: Optional[str] = None    # Description of changes made
    scoring_breakdown: Dict[str, float] = field(default_factory=dict)  # pain_point: 2.0, keyword: 0.5, etc.

    @property
    def is_exact_match(self) -> bool:
        """Check if bullet is an exact match from source."""
        return self.match_confidence >= 0.99 and not self.tailoring_applied

    @property
    def total_score(self) -> float:
        """Total score from scoring breakdown."""
        return sum(self.scoring_breakdown.values())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "bullet_text": self.bullet_text,
            "source_bullet": self.source_bullet,
            "source_role_id": self.source_role_id,
            "source_role_title": self.source_role_title,
            "match_confidence": self.match_confidence,
            "tailoring_applied": self.tailoring_applied,
            "tailoring_changes": self.tailoring_changes,
            "scoring_breakdown": self.scoring_breakdown,
            "is_exact_match": self.is_exact_match,
            "total_score": self.total_score,
        }


@dataclass
class SkillsProvenance:
    """
    Tracks the provenance of skills in core competencies section.

    V2 Header Generation: Every skill in the final CV MUST exist in the
    candidate's whitelist (hard_skills + soft_skills from master CV).
    JD keywords are used for PRIORITIZATION only, not ADDITION.

    Anti-hallucination guarantee:
    - all_from_whitelist: True if every skill exists in candidate's whitelist
    - jd_matched_skills: Skills that matched JD keywords (prioritized)
    - whitelist_only_skills: Skills not in JD but in candidate whitelist
    - rejected_jd_skills: JD skills NOT in whitelist (prevented hallucination)
    """

    all_from_whitelist: bool = True            # Critical: must be True for valid CV
    whitelist_source: str = ""                 # "master_cv" | "role_skills_taxonomy"
    total_skills_selected: int = 0             # Total skills in final CV
    jd_matched_skills: List[str] = field(default_factory=list)      # Skills matching JD
    whitelist_only_skills: List[str] = field(default_factory=list)  # Skills not in JD
    rejected_jd_skills: List[str] = field(default_factory=list)     # JD skills we refused to add
    skills_by_section: Dict[str, List[str]] = field(default_factory=dict)  # section_name → skills

    @property
    def jd_match_ratio(self) -> float:
        """Ratio of skills that matched JD keywords."""
        if self.total_skills_selected == 0:
            return 0.0
        return len(self.jd_matched_skills) / self.total_skills_selected

    @property
    def hallucination_prevented_count(self) -> int:
        """Number of JD skills we prevented from being added."""
        return len(self.rejected_jd_skills)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "all_from_whitelist": self.all_from_whitelist,
            "whitelist_source": self.whitelist_source,
            "total_skills_selected": self.total_skills_selected,
            "jd_matched_skills": self.jd_matched_skills,
            "whitelist_only_skills": self.whitelist_only_skills,
            "rejected_jd_skills": self.rejected_jd_skills,
            "skills_by_section": self.skills_by_section,
            "jd_match_ratio": self.jd_match_ratio,
            "hallucination_prevented_count": self.hallucination_prevented_count,
        }


@dataclass
class CoreCompetencySection:
    """
    A single core competency section in the V2 header format.

    V2 Header Generation: Each role category has exactly 4 static sections
    (not LLM-generated). Section names are pre-defined in role_skills_taxonomy.json.

    Example for engineering_manager:
    - Technical Leadership: skill1, skill2, ...
    - People Management: skill1, skill2, ...
    - Cloud & Platform: skill1, skill2, ...
    - Delivery & Process: skill1, skill2, ...
    """

    name: str                                  # Static section name (from taxonomy)
    skills: List[str]                          # Skills in priority order
    jd_matched_count: int = 0                  # How many matched JD keywords
    max_skills: int = 10                       # Maximum skills to include

    @property
    def skill_count(self) -> int:
        """Number of skills in this section."""
        return len(self.skills)

    @property
    def jd_match_ratio(self) -> float:
        """Ratio of skills that matched JD."""
        if self.skill_count == 0:
            return 0.0
        return self.jd_matched_count / self.skill_count

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "skills": self.skills,
            "jd_matched_count": self.jd_matched_count,
            "max_skills": self.max_skills,
            "skill_count": self.skill_count,
            "jd_match_ratio": self.jd_match_ratio,
        }

    def to_markdown(self) -> str:
        """Format as markdown for CV output."""
        skills_str = ", ".join(self.skills)
        return f"**{self.name}:** {skills_str}"


@dataclass
class SelectionResult:
    """
    Result of achievement bullet selection for V2 header generation.

    Tracks whether we found enough high-quality bullets and any warnings.
    """

    bullets_selected: int                      # Number of bullets selected
    target_count: int = 6                      # Target number (5-6)
    needs_review: bool = False                 # True if insufficient relevant bullets
    warning_message: Optional[str] = None      # e.g., "Only 4 relevant bullets found"
    lowest_score_selected: float = 0.0         # Score of lowest-scoring selected bullet

    @property
    def met_target(self) -> bool:
        """Check if we met the target count."""
        return self.bullets_selected >= self.target_count - 1  # Allow 5 for target 6

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "bullets_selected": self.bullets_selected,
            "target_count": self.target_count,
            "needs_review": self.needs_review,
            "warning_message": self.warning_message,
            "lowest_score_selected": self.lowest_score_selected,
            "met_target": self.met_target,
        }


@dataclass
class ScoringWeights:
    """
    Configurable weights for achievement bullet scoring algorithm.

    V2 Header Generation: Bullets are scored to select the most relevant
    for the key achievements section. Higher scores = more relevant to JD.
    """

    pain_point_match: float = 2.0              # Per matched pain point
    annotation_suggested: float = 3.0          # If annotation recommends this bullet
    keyword_match: float = 0.5                 # Per JD keyword found in bullet
    core_strength: float = 1.5                 # Demonstrates candidate core strength
    emphasis_area: float = 1.5                 # Matches annotation emphasis area
    competency_weight: float = 1.0             # Matches JD competency dimension
    recency_current_role: float = 1.0          # Bullet is from current role
    recency_previous_role: float = 0.5         # Bullet is from previous role
    recency_old_role: float = 0.0              # Bullet is from older role
    variant_type_match: float = 1.0            # Bullet variant matches JD emphasis
    interview_defensible: float = 0.5          # Marked as interview-defensible

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "pain_point_match": self.pain_point_match,
            "annotation_suggested": self.annotation_suggested,
            "keyword_match": self.keyword_match,
            "core_strength": self.core_strength,
            "emphasis_area": self.emphasis_area,
            "competency_weight": self.competency_weight,
            "recency_current_role": self.recency_current_role,
            "recency_previous_role": self.recency_previous_role,
            "recency_old_role": self.recency_old_role,
            "variant_type_match": self.variant_type_match,
            "interview_defensible": self.interview_defensible,
        }


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

    Phase 4.5: Added annotation_boost to prioritize annotated skills.
    """

    skill: str                         # The skill being scored
    jd_match_score: float              # 1.0 if in JD keywords, else 0.0
    evidence_score: float              # Based on evidence frequency (0-1)
    recency_score: float               # Based on how recently used (0-1)
    annotation_boost: float = 1.0      # Phase 4.5: Annotation-based boost (1.0 = no boost, 3.0+ = core_strength)
    total_score: float = 0.0           # Weighted total score

    def __post_init__(self):
        """Calculate total score if not provided."""
        if self.total_score == 0.0:
            # Base weights: 40% JD match, 30% evidence, 30% recency
            base_score = (
                0.4 * self.jd_match_score +
                0.3 * self.evidence_score +
                0.3 * self.recency_score
            )
            # Phase 4.5: Apply annotation boost as multiplier
            # This ensures annotated skills (especially must-haves) rank higher
            self.total_score = base_score * self.annotation_boost

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "skill": self.skill,
            "jd_match_score": self.jd_match_score,
            "evidence_score": self.evidence_score,
            "recency_score": self.recency_score,
            "annotation_boost": self.annotation_boost,
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
    Hybrid Executive Summary for senior technical leadership.

    Based on research from 625 hiring managers and eye-tracking studies:
    - Profile receives 80% of initial attention
    - First 7.4 seconds determine continue/reject decision
    - Candidates with exact job title are 10.6x more likely to get interviews

    New Hybrid Structure:
    1. Headline: "[EXACT TITLE] | [X]+ Years Technology Leadership"
    2. Tagline: Persona-driven hook (15-25 words, max 200 chars, third-person absent voice)
    3. Key Achievements: 5-6 quantified bullets from experience
    4. Core Competencies: 6-8 ATS-optimized keywords

    The tagline and key_achievements must answer 4 questions:
    1. Who are you professionally? (Identity) - answered by tagline
    2. What problems can you solve? (Relevance) - answered by key_achievements
    3. What proof do you have? (Evidence) - answered by key_achievements with metrics
    4. Why should they call you? (Differentiation) - answered by tagline

    V2 Header Generation (now the only path - V1 removed):
    - value_proposition: Replaces tagline with role-specific formula
    - achievement_sources: Full traceability for each key achievement
    - skills_provenance: Proves all skills are from whitelist (anti-hallucination)
    - core_competencies_v2: Dict[str, List[str]] with static section names
    - summary_type: "executive_summary" (Director+) or "professional_summary" (others)
    """

    # Core content - Hybrid Executive Summary structure
    headline: str = ""                 # "[EXACT TITLE] | [YEARS] Years Technology Leadership"
    tagline: str = ""                  # NEW: Persona-driven hook (15-25 words, max 200 chars)
    key_achievements: List[str] = field(default_factory=list)  # NEW: 5-6 quantified bullets
    core_competencies: List[str] = field(default_factory=list)  # 6-8 ATS keyword bullets

    # DEPRECATED: Keep for backward compatibility during transition
    narrative: str = ""                # DEPRECATED: Use tagline + key_achievements instead

    # Grounding evidence
    highlights_used: List[str] = field(default_factory=list)  # Quantified achievements referenced
    keywords_integrated: List[str] = field(default_factory=list)  # JD keywords naturally included
    exact_title_used: str = ""         # The exact JD title incorporated in headline

    # Validation - tracks if all 4 questions are answered
    answers_who: bool = False          # Identity and level (tagline)
    answers_what_problems: bool = False  # Relevance to their needs (key_achievements)
    answers_proof: bool = False        # Evidence of impact (key_achievements with metrics)
    answers_why_you: bool = False      # Differentiation (tagline)

    # Configuration
    word_count: int = 0
    regional_variant: str = "us_eu"    # "us_eu" | "gulf"

    # Legacy field for backward compatibility
    _legacy_text: str = ""

    # Annotation traceability (Phase 4.5)
    # Note: HeaderProvenance is defined later in this file
    provenance: Optional[Any] = None           # HeaderProvenance for annotation tracing
    annotation_influenced: bool = False        # Whether annotations affected generation

    # ===== V2 HEADER GENERATION FIELDS (Anti-Hallucination) =====
    # These fields provide full traceability for anti-hallucination guarantees

    # V2: Value Proposition (replaces tagline)
    value_proposition: str = ""                # Role-specific: [Domain] + [Scale] + [Impact]

    # V2: Achievement traceability (proves each bullet exists in master CV)
    achievement_sources: List[Any] = field(default_factory=list)  # List[AchievementSource]

    # V2: Skills provenance (proves all skills from whitelist)
    skills_provenance: Optional[Any] = None    # SkillsProvenance

    # V2: Core competencies with static section names
    core_competencies_v2: Dict[str, List[str]] = field(default_factory=dict)  # section_name → skills

    # V2: Summary type based on role level
    summary_type: str = "professional_summary"  # "executive_summary" | "professional_summary"

    # V2: Selection result (for warnings about insufficient bullets)
    selection_result: Optional[Any] = None     # SelectionResult

    def __post_init__(self):
        """Calculate word count and ensure backward compatibility."""
        # Calculate word count from tagline + key_achievements (primary content)
        if self.word_count == 0:
            if self.tagline and self.key_achievements:
                total_words = len(self.tagline.split())
                total_words += sum(len(a.split()) for a in self.key_achievements)
                self.word_count = total_words
            elif self.narrative:
                self.word_count = len(self.narrative.split())
            elif self._legacy_text:
                self.word_count = len(self._legacy_text.split())

    @property
    def is_hybrid_format(self) -> bool:
        """Check if using new hybrid format vs legacy narrative."""
        return bool(self.tagline and self.key_achievements)

    @property
    def effective_summary_title(self) -> str:
        """Get the summary section title based on role level."""
        if self.summary_type == "executive_summary":
            return "EXECUTIVE SUMMARY"
        return "PROFESSIONAL SUMMARY"

    @property
    def formatted_summary(self) -> str:
        """Return the complete formatted executive summary."""
        lines = []
        if self.headline:
            lines.append(self.headline)
            lines.append("")
        if self.tagline:
            lines.append(self.tagline)
            lines.append("")
        if self.key_achievements:
            for achievement in self.key_achievements:
                lines.append(f"- {achievement}")
            lines.append("")
        if self.core_competencies:
            lines.append(f"Core: {' | '.join(self.core_competencies)}")
        return "\n".join(lines)

    @property
    def text(self) -> str:
        """Combined text for backward compatibility and word count."""
        if self.tagline and self.key_achievements:
            bullets_text = "\n".join(f"- {a}" for a in self.key_achievements)
            return f"{self.tagline}\n\n{bullets_text}"
        # Fallback to legacy narrative
        if self.narrative:
            return self.narrative
        return self._legacy_text

    @text.setter
    def text(self, value: str):
        """Allow setting text for backward compatibility."""
        self._legacy_text = value
        if not self.narrative and not self.tagline:
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
            "tagline": self.tagline,
            "key_achievements": self.key_achievements,
            "core_competencies": self.core_competencies,
            "narrative": self.narrative,
            "text": self.text,
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
            "is_hybrid_format": self.is_hybrid_format,
            # Phase 4.5 annotation traceability
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "annotation_influenced": self.annotation_influenced,
            # V2 fields (always included)
            "value_proposition": self.value_proposition,
            "summary_type": self.summary_type,
            "core_competencies_v2": self.core_competencies_v2,
            "effective_summary_title": self.effective_summary_title,
            # Achievement sources with full traceability
            "achievement_sources": [
                s.to_dict() if hasattr(s, 'to_dict') else s
                for s in self.achievement_sources
            ],
            # Skills provenance for anti-hallucination proof
            "skills_provenance": (
                self.skills_provenance.to_dict()
                if self.skills_provenance and hasattr(self.skills_provenance, 'to_dict')
                else self.skills_provenance
            ),
            # Selection result for warnings
            "selection_result": (
                self.selection_result.to_dict()
                if self.selection_result and hasattr(self.selection_result, 'to_dict')
                else self.selection_result
            ),
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


# ===== ENSEMBLE GENERATION TYPES (Tiered Multi-Pass) =====


@dataclass
class ValidationFlags:
    """
    Flags for content that may need human review (flag & keep approach).

    Instead of removing ungrounded content, we flag it for review
    while preserving the content in the output.
    """

    ungrounded_metrics: List[str] = field(default_factory=list)
    """Metrics mentioned that don't appear in source bullets."""

    ungrounded_skills: List[str] = field(default_factory=list)
    """Skills/keywords not in the whitelist or experience."""

    flagged_claims: List[str] = field(default_factory=list)
    """Narrative claims that may need verification."""

    @property
    def has_flags(self) -> bool:
        """Check if any content has been flagged."""
        return bool(
            self.ungrounded_metrics
            or self.ungrounded_skills
            or self.flagged_claims
        )

    @property
    def total_flags(self) -> int:
        """Total number of flagged items."""
        return (
            len(self.ungrounded_metrics)
            + len(self.ungrounded_skills)
            + len(self.flagged_claims)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "ungrounded_metrics": self.ungrounded_metrics,
            "ungrounded_skills": self.ungrounded_skills,
            "flagged_claims": self.flagged_claims,
            "has_flags": self.has_flags,
            "total_flags": self.total_flags,
        }


@dataclass
class EnsembleMetadata:
    """
    Metadata tracking the ensemble generation process.

    Records which tier was used, how many passes were executed,
    and validation flags for human review.
    """

    tier_used: str = ""
    """Processing tier: 'GOLD', 'SILVER', 'BRONZE', or 'SKIP'."""

    passes_executed: int = 1
    """Number of persona passes executed (1-3)."""

    personas_used: List[str] = field(default_factory=list)
    """List of personas used: 'metric', 'narrative', 'keyword'."""

    synthesis_model: str = ""
    """Model used for synthesis step (if any)."""

    synthesis_applied: bool = False
    """Whether synthesis was applied to combine outputs."""

    validation_flags: Optional[ValidationFlags] = None
    """Flags for content needing review (Gold tier only)."""

    generation_time_ms: int = 0
    """Total generation time in milliseconds."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tier_used": self.tier_used,
            "passes_executed": self.passes_executed,
            "personas_used": self.personas_used,
            "synthesis_model": self.synthesis_model,
            "synthesis_applied": self.synthesis_applied,
            "validation_flags": (
                self.validation_flags.to_dict()
                if self.validation_flags else None
            ),
            "generation_time_ms": self.generation_time_ms,
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
    ensemble_metadata: Optional[EnsembleMetadata] = None     # Tier/ensemble tracking

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
            "ensemble_metadata": (
                self.ensemble_metadata.to_dict()
                if self.ensemble_metadata else None
            ),
        }

    def to_markdown(self) -> str:
        """
        Convert to ATS-optimized format for CV header.

        Uses Hybrid Executive Summary structure:
        - EXECUTIVE SUMMARY header
        - Headline with job title + years (10.6x interview factor)
        - Tagline (persona-driven hook, 15-25 words)
        - Key Achievements (5-6 quantified bullets)
        - Core Competencies line
        - Skills & Expertise sections
        """
        lines = []

        # Contact info header
        name = self.contact_info.get("name", "")
        email = self.contact_info.get("email", "")
        phone = self.contact_info.get("phone", "")
        linkedin = self.contact_info.get("linkedin", "")
        nationality = self.contact_info.get("nationality", "")

        lines.append(name)
        contact_parts = [p for p in [email, phone, linkedin, nationality] if p]
        lines.append(" | ".join(contact_parts))
        lines.append("")

        # Executive Summary (new format)
        lines.append("EXECUTIVE SUMMARY")

        # Headline with job title + years (bold for emphasis)
        if self.profile.headline:
            lines.append(f"**{self.profile.headline}**")
            lines.append("")

        # Tagline (new hybrid format) or fallback to narrative
        if self.profile.tagline:
            lines.append(self.profile.tagline)
            lines.append("")
        elif self.profile.narrative:
            # Fallback to legacy narrative
            lines.append(self.profile.narrative)
            lines.append("")

        # Key Achievements (new hybrid format)
        if self.profile.key_achievements:
            for achievement in self.profile.key_achievements:
                lines.append(f"- {achievement}")
            lines.append("")

        # Core Competencies - inline format for ATS
        if self.profile.core_competencies:
            competencies_str = " | ".join(self.profile.core_competencies)
            lines.append(f"**Core:** {competencies_str}")
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


# ===== PHASE 4.5: ANNOTATION-DRIVEN HEADER TYPES =====

# Import annotation types for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.common.annotation_types import SkillRelevance, RequirementType


@dataclass
class ATSRequirement:
    """
    ATS requirements for a keyword in the generated header/summary/skills.

    Based on research from cv-guide.plan.md and ats-guide.md:
    - Greenhouse ranks resumes with more keyword mentions higher
    - Target 2-4 repetitions of key terms across header/summary/skills
    - Always include both acronym AND full form (ATS don't recognize abbreviations)
    """

    min_occurrences: int = 2                   # Target: appear at least 2x
    max_occurrences: int = 4                   # Avoid keyword stuffing
    variants: List[str] = field(default_factory=list)  # e.g., ["Kubernetes", "K8s", "k8s"]
    preferred_sections: List[str] = field(default_factory=list)  # ["skills", "summary"]
    exact_phrase: bool = False                 # Must use exact JD phrasing

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "min_occurrences": self.min_occurrences,
            "max_occurrences": self.max_occurrences,
            "variants": self.variants,
            "preferred_sections": self.preferred_sections,
            "exact_phrase": self.exact_phrase,
        }


@dataclass
class AnnotationPriority:
    """
    A single priority extracted from JD annotations for header/summary/skills generation.

    This represents one "thing the recruiter cares about" ranked by importance.
    Used to guide what appears in the critical 6-7 second scan zone (header/summary).

    Ranking formula (from plan):
    priority_score = (
        RELEVANCE_WEIGHT[relevance] * 0.4 +      # core_strength=5, extremely_relevant=4, ...
        REQUIREMENT_WEIGHT[requirement_type] * 0.3 +  # must_have=5, nice_to_have=3, ...
        (6 - user_priority) * 0.2 +              # User priority 1-5 inverted (1 is highest)
        has_star_evidence * 0.1                  # +1 if STAR linked
    )

    Enhanced with passion and identity dimensions:
    - passion: How excited the candidate is about this aspect (love_it → avoid)
    - identity: How strongly this defines professional identity (core_identity → not_identity)
    """

    rank: int                                  # 1 = highest priority
    jd_text: str                               # Original JD requirement text
    matching_skill: Optional[str] = None       # Candidate skill that matches (if any)
    relevance: str = "relevant"                # SkillRelevance: core_strength → gap
    requirement_type: str = "neutral"          # RequirementType: must_have → neutral
    passion: str = "neutral"                   # PassionLevel: love_it → avoid (enthusiasm)
    identity: str = "peripheral"               # IdentityLevel: core_identity → not_identity
    reframe_note: Optional[str] = None         # Reframe guidance (e.g., "Frame as 'platform modernization'")
    reframe_from: Optional[str] = None         # Original skill/experience to reframe
    reframe_to: Optional[str] = None           # Target framing for JD alignment
    ats_variants: List[str] = field(default_factory=list)  # Keyword variants ["K8s", "Kubernetes"]
    star_snippets: List[str] = field(default_factory=list)  # One-line metric statements from linked STARs
    annotation_ids: List[str] = field(default_factory=list)  # Source annotation IDs for traceability
    priority_score: float = 0.0                # Calculated priority score

    @property
    def has_star_evidence(self) -> bool:
        """Check if this priority has linked STAR evidence."""
        return len(self.star_snippets) > 0

    @property
    def has_reframe(self) -> bool:
        """Check if this priority has reframe guidance."""
        return self.reframe_note is not None

    @property
    def is_gap(self) -> bool:
        """Check if this is a gap (candidate doesn't have the skill)."""
        return self.relevance == "gap"

    @property
    def is_must_have(self) -> bool:
        """Check if this is a must-have requirement."""
        return self.requirement_type == "must_have"

    @property
    def is_core_strength(self) -> bool:
        """Check if this matches a core strength."""
        return self.relevance == "core_strength"

    @property
    def is_passion(self) -> bool:
        """Check if candidate is passionate about this (love_it or enjoy)."""
        return self.passion in ("love_it", "enjoy")

    @property
    def is_avoid(self) -> bool:
        """Check if candidate wants to avoid this."""
        return self.passion == "avoid"

    @property
    def is_core_identity(self) -> bool:
        """Check if this is core to professional identity."""
        return self.identity == "core_identity"

    @property
    def is_not_identity(self) -> bool:
        """Check if candidate explicitly doesn't identify with this."""
        return self.identity == "not_identity"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "rank": self.rank,
            "jd_text": self.jd_text,
            "matching_skill": self.matching_skill,
            "relevance": self.relevance,
            "requirement_type": self.requirement_type,
            "passion": self.passion,
            "identity": self.identity,
            "reframe_note": self.reframe_note,
            "reframe_from": self.reframe_from,
            "reframe_to": self.reframe_to,
            "ats_variants": self.ats_variants,
            "star_snippets": self.star_snippets,
            "annotation_ids": self.annotation_ids,
            "priority_score": self.priority_score,
            "has_star_evidence": self.has_star_evidence,
            "has_reframe": self.has_reframe,
            "is_gap": self.is_gap,
            "is_must_have": self.is_must_have,
            "is_core_strength": self.is_core_strength,
            "is_passion": self.is_passion,
            "is_avoid": self.is_avoid,
            "is_core_identity": self.is_core_identity,
            "is_not_identity": self.is_not_identity,
        }


@dataclass
class HeaderGenerationContext:
    """
    Context passed to header generation with annotation data.

    This bridges the JD annotation system with the header/summary/skills generators.
    Contains prioritized requirements, reframes, ATS targets, and gap handling.

    Enhanced with passion and identity dimensions:
    - passion_priorities: Items candidate is excited about (use in cover letter hooks)
    - identity_priorities: Items that define professional identity (use in headlines)
    - avoid_priorities: Items to de-emphasize (don't highlight in CV)

    Used by:
    - HeaderGenerator to emphasize must-have skills in headline/tagline
    - ProfileOutput generation to include STAR proof and apply reframes
    - TaxonomyBasedSkillsGenerator to prioritize annotated skills
    - Cover letter generator to show authentic enthusiasm
    """

    priorities: List[AnnotationPriority] = field(default_factory=list)  # Ranked priority list
    gap_mitigation: Optional[str] = None       # Pre-generated gap mitigation clause
    gap_mitigation_annotation_id: Optional[str] = None  # Which gap annotation was used
    reframe_map: Dict[str, str] = field(default_factory=dict)  # skill → reframe_note
    ats_requirements: Dict[str, ATSRequirement] = field(default_factory=dict)  # skill → ATS config
    keyword_coverage_target: Dict[str, int] = field(default_factory=dict)  # keyword → target count

    @property
    def must_have_priorities(self) -> List[AnnotationPriority]:
        """Get only must-have priorities."""
        return [p for p in self.priorities if p.is_must_have]

    @property
    def core_strength_priorities(self) -> List[AnnotationPriority]:
        """Get only core strength priorities."""
        return [p for p in self.priorities if p.is_core_strength]

    @property
    def gap_priorities(self) -> List[AnnotationPriority]:
        """Get only gap priorities."""
        return [p for p in self.priorities if p.is_gap]

    @property
    def passion_priorities(self) -> List[AnnotationPriority]:
        """Get priorities candidate is passionate about (love_it or enjoy).

        Use these in cover letter hooks and to show authentic enthusiasm.
        """
        return [p for p in self.priorities if p.is_passion]

    @property
    def avoid_priorities(self) -> List[AnnotationPriority]:
        """Get priorities candidate wants to avoid.

        De-emphasize these in CV/cover letter - don't highlight even if relevant.
        """
        return [p for p in self.priorities if p.is_avoid]

    @property
    def identity_priorities(self) -> List[AnnotationPriority]:
        """Get priorities that are core to professional identity.

        Use these in headlines, taglines, and opening statements.
        """
        return [p for p in self.priorities if p.is_core_identity]

    @property
    def not_identity_priorities(self) -> List[AnnotationPriority]:
        """Get priorities candidate explicitly doesn't identify with.

        Avoid using these in introductions even if technically relevant.
        """
        return [p for p in self.priorities if p.is_not_identity]

    @property
    def top_keywords(self) -> List[str]:
        """Get top keywords from priorities (for tagline/headline)."""
        keywords = []
        for p in self.priorities[:5]:  # Top 5 priorities
            if p.matching_skill:
                keywords.append(p.matching_skill)
            elif p.ats_variants and len(p.ats_variants) > 0:
                keywords.append(p.ats_variants[0])
        return keywords

    @property
    def identity_keywords(self) -> List[str]:
        """Get keywords from core identity priorities (for headline/intro).

        These are the terms that define who the candidate IS.
        """
        keywords = []
        for p in self.identity_priorities[:3]:  # Top 3 identity items
            if p.matching_skill:
                keywords.append(p.matching_skill)
            elif p.ats_variants and len(p.ats_variants) > 0:
                keywords.append(p.ats_variants[0])
        return keywords

    @property
    def passion_keywords(self) -> List[str]:
        """Get keywords from passion priorities (for cover letter hooks).

        These show authentic enthusiasm and interest.
        """
        keywords = []
        for p in self.passion_priorities[:3]:  # Top 3 passion items
            if p.matching_skill:
                keywords.append(p.matching_skill)
            elif p.ats_variants and len(p.ats_variants) > 0:
                keywords.append(p.ats_variants[0])
        return keywords

    @property
    def has_annotations(self) -> bool:
        """Check if any annotation data is present."""
        return len(self.priorities) > 0

    def get_reframe(self, skill: str) -> Optional[str]:
        """Get reframe note for a skill if available."""
        return self.reframe_map.get(skill)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "priorities": [p.to_dict() for p in self.priorities],
            "gap_mitigation": self.gap_mitigation,
            "gap_mitigation_annotation_id": self.gap_mitigation_annotation_id,
            "reframe_map": self.reframe_map,
            "ats_requirements": {k: v.to_dict() for k, v in self.ats_requirements.items()},
            "keyword_coverage_target": self.keyword_coverage_target,
            "has_annotations": self.has_annotations,
            "must_have_count": len(self.must_have_priorities),
            "gap_count": len(self.gap_priorities),
            "passion_count": len(self.passion_priorities),
            "identity_count": len(self.identity_priorities),
            "avoid_count": len(self.avoid_priorities),
        }


@dataclass
class HeaderProvenance:
    """
    Traceability for header generation - tracks which annotations influenced what.

    This enables:
    1. Debugging: Why did this keyword appear in the headline?
    2. Optimization: Which annotations correlate with successful applications?
    3. Audit: Full trace from JD annotation → CV content
    """

    title_source: str = ""                     # "jd_mapping" | "candidate_metadata" | "annotation_match"
    title_annotation_id: Optional[str] = None  # Annotation that influenced title selection
    tagline_keywords: List[str] = field(default_factory=list)  # Keywords used in tagline
    tagline_annotation_ids: List[str] = field(default_factory=list)  # Annotations that influenced tagline

    summary_annotation_ids: List[str] = field(default_factory=list)  # Annotations that influenced summary
    summary_star_ids: List[str] = field(default_factory=list)  # STARs used for proof lines
    reframes_applied: List[str] = field(default_factory=list)  # Reframe annotation IDs applied
    gap_mitigation_annotation_id: Optional[str] = None  # Gap annotation used for mitigation

    skills_annotation_ids: List[str] = field(default_factory=list)  # Annotations that influenced skill selection
    skills_prioritized: List[str] = field(default_factory=list)  # Skills that were prioritized by annotations

    # ATS tracking
    keyword_coverage_achieved: Dict[str, int] = field(default_factory=dict)  # keyword → actual count
    ats_validation_passed: bool = True
    ats_validation_warnings: List[str] = field(default_factory=list)

    @property
    def total_annotations_used(self) -> int:
        """Total number of unique annotations that influenced generation."""
        all_ids = set()
        all_ids.update(self.tagline_annotation_ids)
        all_ids.update(self.summary_annotation_ids)
        all_ids.update(self.skills_annotation_ids)
        if self.title_annotation_id:
            all_ids.add(self.title_annotation_id)
        if self.gap_mitigation_annotation_id:
            all_ids.add(self.gap_mitigation_annotation_id)
        return len(all_ids)

    @property
    def has_annotation_influence(self) -> bool:
        """Check if annotations influenced the generation."""
        return self.total_annotations_used > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "title_source": self.title_source,
            "title_annotation_id": self.title_annotation_id,
            "tagline_keywords": self.tagline_keywords,
            "tagline_annotation_ids": self.tagline_annotation_ids,
            "summary_annotation_ids": self.summary_annotation_ids,
            "summary_star_ids": self.summary_star_ids,
            "reframes_applied": self.reframes_applied,
            "gap_mitigation_annotation_id": self.gap_mitigation_annotation_id,
            "skills_annotation_ids": self.skills_annotation_ids,
            "skills_prioritized": self.skills_prioritized,
            "keyword_coverage_achieved": self.keyword_coverage_achieved,
            "ats_validation_passed": self.ats_validation_passed,
            "ats_validation_warnings": self.ats_validation_warnings,
            "total_annotations_used": self.total_annotations_used,
            "has_annotation_influence": self.has_annotation_influence,
        }


# ===== PHASE 6: ATS VALIDATION TYPES =====

@dataclass
class ATSValidationResult:
    """
    Post-generation ATS keyword validation result for the full CV.

    Phase 6 (GAP-089): Validates that must-have and nice-to-have keywords
    from JD annotations appear with appropriate frequency in the final CV.

    Based on ATS guide research:
    - Greenhouse ranks resumes with more keyword mentions higher
    - Target 2-4 repetitions of key terms
    - Avoid keyword stuffing (max 5-6 mentions)
    """

    passed: bool = True                                # Overall pass/fail
    violations: List[str] = field(default_factory=list)  # e.g., "Kubernetes: 1/2 (too few)"
    ats_score: int = 100                               # 0-100 score
    keyword_coverage: Dict[str, int] = field(default_factory=dict)  # keyword → actual count
    keywords_met: List[str] = field(default_factory=list)    # Keywords meeting requirements
    keywords_under: List[str] = field(default_factory=list)  # Keywords below minimum
    keywords_over: List[str] = field(default_factory=list)   # Keywords above maximum
    total_keywords_checked: int = 0

    @property
    def coverage_ratio(self) -> float:
        """Ratio of keywords meeting requirements."""
        if self.total_keywords_checked == 0:
            return 1.0
        return len(self.keywords_met) / self.total_keywords_checked

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "violations": self.violations,
            "ats_score": self.ats_score,
            "keyword_coverage": self.keyword_coverage,
            "keywords_met": self.keywords_met,
            "keywords_under": self.keywords_under,
            "keywords_over": self.keywords_over,
            "total_keywords_checked": self.total_keywords_checked,
            "coverage_ratio": self.coverage_ratio,
        }


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
class TailoringResult:
    """
    Result of CV tailoring pass (Phase 6.5).

    Final pass for keyword emphasis - ensures must-have and identity keywords
    appear in prominent locations (headline, first 50 words, competencies).

    Key Constraints:
    - Keyword emphasis ONLY (no reframe transformations)
    - Preserve ATS constraints (min 2, max 5 mentions per keyword)
    - Maintain readability
    - Single LLM call for targeted edits

    Anti-Hallucination Guarantees:
    - No keyword addition (only reposition existing)
    - No format changes (preserve markdown structure)
    - No metric changes (all numbers stay identical)
    - Post-validation required (ATS constraints checked after tailoring)
    """

    tailored: bool                     # Whether tailoring was applied
    cv_text: str                       # The tailored CV text
    changes_made: List[str]            # Description of changes
    keywords_repositioned: List[str]   # Keywords that were moved to prominent positions
    tailoring_summary: str = ""        # Brief summary
    keyword_placement_score: int = 0   # Score after tailoring (0-100)
    ats_validation_passed: bool = True # ATS constraints still met after tailoring

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tailored": self.tailored,
            "cv_text": self.cv_text,
            "changes_made": self.changes_made,
            "keywords_repositioned": self.keywords_repositioned,
            "tailoring_summary": self.tailoring_summary,
            "keyword_placement_score": self.keyword_placement_score,
            "ats_validation_passed": self.ats_validation_passed,
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
