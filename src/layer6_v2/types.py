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
    - The generated text optimized for the JD
    - The source text it was derived from (for hallucination QA)
    - Metrics and keywords used (for verification)
    - Pain points addressed (for JD alignment)
    """

    text: str                          # Generated bullet text (15-25 words)
    source_text: str                   # Original achievement from role file
    source_metric: Optional[str] = None       # Exact metric from source (for verification)
    jd_keyword_used: Optional[str] = None     # JD keyword integrated (or None)
    pain_point_addressed: Optional[str] = None  # Pain point addressed (or None)
    word_count: int = 0                # Word count of generated text

    def __post_init__(self):
        """Calculate word count if not provided."""
        if self.word_count == 0:
            self.word_count = len(self.text.split())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "source_text": self.source_text,
            "source_metric": self.source_metric,
            "jd_keyword_used": self.jd_keyword_used,
            "pain_point_addressed": self.pain_point_addressed,
            "word_count": self.word_count,
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed": self.passed,
            "flagged_bullets": self.flagged_bullets,
            "issues": self.issues,
            "verified_metrics": self.verified_metrics,
            "confidence": self.confidence,
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
            "bullet_count": self.bullet_count,
            "word_count": self.word_count,
        }

    def to_markdown(self) -> str:
        """Convert to markdown format for CV output."""
        lines = [
            f"### {self.company}",
            f"**{self.title}** | {self.location} | {self.period}",
            "",
        ]
        for bullet in self.bullets:
            lines.append(f"• {bullet}")
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
        """Convert to markdown format for CV output."""
        skill_names = ", ".join(self.skill_names)
        return f"**{self.category}**: {skill_names}"


@dataclass
class ProfileOutput:
    """
    Generated profile summary grounded in achievements.

    The profile should:
    - Lead with role-category-appropriate superpower
    - Include 1-2 quantified highlights from experience
    - Use top 3 JD keywords naturally
    - Be 2-3 sentences (50-80 words)
    """

    text: str                          # The profile text
    highlights_used: List[str]         # Quantified achievements referenced
    keywords_integrated: List[str]     # JD keywords naturally included
    word_count: int = 0

    def __post_init__(self):
        """Calculate word count if not provided."""
        if self.word_count == 0:
            self.word_count = len(self.text.split())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "highlights_used": self.highlights_used,
            "keywords_integrated": self.keywords_integrated,
            "word_count": self.word_count,
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
        """Convert to markdown format for CV header."""
        lines = []

        # Contact info header
        name = self.contact_info.get("name", "")
        email = self.contact_info.get("email", "")
        phone = self.contact_info.get("phone", "")
        linkedin = self.contact_info.get("linkedin", "")

        lines.append(f"# {name}")
        lines.append(f"{email} | {phone} | {linkedin}")
        lines.append("")

        # Profile
        lines.append("## Profile")
        lines.append(self.profile.text)
        lines.append("")

        # Skills
        lines.append("## Core Competencies")
        for section in self.skills_sections:
            lines.append(section.to_markdown())
        lines.append("")

        # Education
        lines.append("## Education")
        for edu in self.education:
            lines.append(f"- {edu}")

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
