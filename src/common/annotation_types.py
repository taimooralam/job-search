"""
Type definitions for JD Annotation System.

This module defines the data contracts for the annotation system that enables
manual marking of JD sections with match strength, reframe notes, STAR story
links, and keyword suggestions.

The annotation system improves CV, cover letter, and outreach personalization
with a feedback loop to master-cv data via MongoDB.
"""

from typing import TypedDict, List, Optional, Dict, Literal


# =============================================================================
# ENUMS / LITERAL TYPES
# =============================================================================

# Skill relevance levels (5 levels for granular matching)
SkillRelevance = Literal[
    "core_strength",      # Perfect match - this IS your core competency (3.0x boost)
    "extremely_relevant", # Very strong match - directly applicable (2.0x boost)
    "relevant",           # Good match - transferable with minor framing (1.5x boost)
    "tangential",         # Weak match - loosely related, needs reframing (1.0x boost)
    "gap"                 # No match - candidate lacks this skill/experience (0.3x penalty)
]

# Annotation type (primary classification)
AnnotationType = Literal[
    "skill_match",        # JD requirement matches candidate skill
    "reframe",            # Standalone reframe opportunity
    "highlight",          # General highlight for emphasis
    "comment",            # Free-form note/observation
    "concern"             # Red flag or dealbreaker
]

# Requirement type (recruiter filtering priority)
RequirementType = Literal[
    "must_have",          # Explicitly required - 1.5x boost
    "nice_to_have",       # Preferred but not required - 1.0x
    "disqualifier",       # Candidate explicitly doesn't want - 0.0x
    "neutral"             # Neither required nor preferred - 1.0x
]

# Annotation status (audit trail)
AnnotationStatus = Literal[
    "draft",              # Not yet reviewed
    "approved",           # Reviewed and approved
    "rejected",           # Reviewed and rejected
    "needs_review"        # Flagged for review
]

# Annotation source
AnnotationSource = Literal[
    "human",              # Created by user
    "pipeline_suggestion", # Suggested by LLM
    "preset"              # Created via quick-action preset
]

# Concern severity
ConcernSeverity = Literal[
    "blocker",            # Dealbreaker - do not apply
    "concern",            # Significant issue to address
    "preference"          # Minor preference mismatch
]

# Passion level (candidate enthusiasm for this aspect of the role)
PassionLevel = Literal[
    "love_it",            # Genuinely excited about this - highlight prominently (1.5x boost)
    "enjoy",              # Would enjoy doing this regularly (1.2x boost)
    "neutral",            # Neither excited nor dreading (1.0x - no boost)
    "tolerate",           # Can do it but would rather not (0.8x - slight penalty)
    "avoid"               # Would strongly prefer not to do this (0.5x - significant penalty)
]

# Identity level (how strongly this defines who you are professionally)
IdentityLevel = Literal[
    "core_identity",      # This IS who I am - use in introductions/headlines (2.0x boost)
    "strong_identity",    # Significant part of professional identity (1.5x boost)
    "developing",         # Growing into this identity (1.2x boost)
    "peripheral",         # Not central to identity but have experience (1.0x - no boost)
    "not_identity"        # Explicitly NOT how I want to be seen (0.3x penalty)
]

# Conflict resolution strategy
ConflictResolution = Literal[
    "max_boost",          # Use highest boost when multiple annotations overlap
    "avg_boost",          # Average all boosts
    "last_write"          # Most recent annotation wins
]


# =============================================================================
# CORE DATA STRUCTURES
# =============================================================================

class TextSpan(TypedDict):
    """
    Identifies a text selection within the JD for annotation targeting.
    Uses character offsets for stability across DOM changes.
    """
    section: str                    # Section ID: "responsibilities", "qualifications", etc.
    index: int                      # Item index within section (0-based)
    text: str                       # The selected text content
    char_start: int                 # Character offset start (within section)
    char_end: int                   # Character offset end (within section)


class JDAnnotation(TypedDict):
    """
    A single annotation on a JD text selection.

    Combines multiple attributes (relevance, requirement type, reframe, etc.)
    rather than using distinct annotation categories.
    """
    # === Identification ===
    id: str                                 # UUID
    target: TextSpan                        # Location in JD

    # === Audit Trail ===
    created_at: str                         # ISO timestamp
    created_by: AnnotationSource            # "human" | "pipeline_suggestion" | "preset"
    updated_at: str                         # ISO timestamp
    status: AnnotationStatus                # "draft" | "approved" | "rejected" | "needs_review"
    last_reviewed_by: Optional[str]         # Reviewer identifier (for team scenarios)
    review_note: Optional[str]              # Rationale for approval/rejection

    # === Primary Type ===
    annotation_type: AnnotationType         # "skill_match" | "reframe" | "highlight" | "comment" | "concern"

    # === Skill Match Attributes ===
    relevance: Optional[SkillRelevance]     # 5-level strength
    requirement_type: Optional[RequirementType]  # must_have/nice_to_have/disqualifier/neutral
    passion: Optional[str]                  # PassionLevel - candidate enthusiasm for this aspect
    identity: Optional[str]                 # IdentityLevel - how strongly this defines professional identity
    matching_skill: Optional[str]           # Which candidate skill matches

    # === Reframe Attributes (standalone OR on skill_match) ===
    has_reframe: bool                       # Whether reframe guidance exists
    reframe_note: Optional[str]             # How to frame/position this
    reframe_from: Optional[str]             # Original skill/experience to reframe
    reframe_to: Optional[str]               # Target framing for JD alignment

    # === Evidence Linking ===
    star_ids: List[str]                     # Linked STAR record IDs
    evidence_summary: Optional[str]         # Brief summary of supporting evidence

    # === Keywords & ATS ===
    suggested_keywords: List[str]           # Keywords to integrate in CV/outreach
    ats_variants: List[str]                 # Keyword variants (e.g., ["Kubernetes", "K8s", "k8s"])
    min_occurrences: Optional[int]          # Target: appear 2-3x in resume
    max_occurrences: Optional[int]          # Avoid keyword stuffing
    preferred_sections: List[str]           # ["skills", "experience"] - ATS weights sections
    exact_phrase_match: bool                # Must use exact JD phrasing

    # === Achievement Context (quantified impact) ===
    achievement_context: Optional[Dict]     # {"metric_type": "percentage", "target_format": "...", "min_impact_threshold": "20%"}

    # === Comment (when type=comment OR as additional note) ===
    comment: Optional[str]                  # Free-form observation/note

    # === Visual Styling ===
    highlight_color: Optional[str]          # Custom color override (hex)

    # === Pipeline Control ===
    is_active: bool                         # Toggle for CV/outreach generation
    priority: int                           # 1-5 (1 = highest priority)
    confidence: float                       # 0.0-1.0 confidence in assessment


class ConcernAnnotation(TypedDict):
    """
    Red flag or dealbreaker annotation for proactive handling.

    Concerns feed directly into cover letter paragraphs and
    interview preparation.
    """
    id: str                                 # UUID
    target: TextSpan                        # Location in JD
    concern: str                            # The concern text (e.g., "on-call rotation")
    severity: ConcernSeverity               # "blocker" | "concern" | "preference"
    mitigation_strategy: str                # How to address in cover letter
    discuss_in_interview: bool              # Flag for interview prep
    created_at: str
    updated_at: str


class SectionSummary(TypedDict):
    """
    Summary statistics for a JD section.
    """
    section_id: str                         # "responsibilities", "qualifications", etc.
    annotation_count: int                   # Total annotations in section
    core_strength_count: int                # Count of core_strength annotations
    gap_count: int                          # Count of gap annotations
    coverage_percentage: float              # 0.0-1.0 coverage estimate
    has_required_coverage: bool             # Meets minimum annotation threshold


class AnnotationSettings(TypedDict):
    """
    Per-job annotation settings.
    """
    job_priority: str                       # "critical" | "high" | "medium" | "low"
    deadline: Optional[str]                 # ISO date for application deadline
    require_full_section_coverage: bool     # Enforce annotation per JD section
    section_coverage: Dict[str, bool]       # {"responsibilities": True, "qualifications": False, ...}
    auto_approve_presets: bool              # Auto-approve preset annotations (vs draft)
    conflict_resolution: ConflictResolution # How to handle overlapping annotations


class JDAnnotations(TypedDict):
    """
    Complete annotation data for a job.

    Stored in job.jd_annotations field in MongoDB.
    """
    annotation_version: int                 # Schema version for migrations
    processed_jd_html: str                  # LLM-structured JD for display
    annotations: List[JDAnnotation]
    concerns: List[ConcernAnnotation]       # Red flags/dealbreakers
    settings: AnnotationSettings
    section_summaries: Dict[str, SectionSummary]

    # === Aggregate Stats ===
    relevance_counts: Dict[str, int]        # Count per relevance level
    type_counts: Dict[str, int]             # Count per annotation type
    reframe_count: int                      # Total reframe opportunities
    gap_count: int                          # Total gaps identified

    # === Validation State ===
    validation_passed: bool                 # All lints pass
    validation_errors: List[str]            # ["core_strength without STAR link", ...]
    ats_readiness_score: Optional[int]      # 0-100 based on keyword coverage


# =============================================================================
# IMPROVEMENT SUGGESTIONS
# =============================================================================

class GapAnalysisResult(TypedDict):
    """
    Analysis of a skill/experience gap.
    """
    gap_id: str                             # UUID
    gap_type: str                           # "skill_gap" | "experience_gap" | "keyword_gap"
    severity: str                           # "critical" | "significant" | "minor"
    requirement_text: str                   # The JD requirement text
    closest_match: Optional[str]            # Nearest candidate skill/experience
    mitigation_strategy: str                # How to address the gap
    address_in_cv: bool                     # Toggle for CV generation
    discuss_in_interview: bool              # Flag for interview prep
    source_annotation_id: Optional[str]     # Link to gap annotation


class SkillsImprovementSuggestion(TypedDict):
    """
    Suggestion to add/modify skills taxonomy.
    """
    suggestion_id: str                      # UUID
    suggestion_type: str                    # "add_skill" | "add_alias" | "add_section"
    target_role: str                        # Role category (engineering_manager, etc.)
    target_section: Optional[str]           # Skills section name
    skill_name: str                         # Skill to add
    reason: str                             # Why this suggestion
    status: str                             # "pending" | "accepted" | "rejected"
    rejection_rationale: Optional[str]      # Why rejected (for LLM tuning)
    created_at: str
    updated_at: str


class RoleMetadataImprovementSuggestion(TypedDict):
    """
    Suggestion to add/modify role metadata.
    """
    suggestion_id: str                      # UUID
    suggestion_type: str                    # "add_keyword" | "add_competency" | "update_field"
    target_role_id: str                     # Role ID (e.g., "01_seven_one_entertainment")
    field_name: str                         # Field to modify (e.g., "keywords", "hard_skills")
    current_value: Optional[str]            # Current field value (if exists)
    suggested_value: str                    # Suggested new/additional value
    reason: str                             # Why this suggestion
    status: str                             # "pending" | "accepted" | "rejected"
    rejection_rationale: Optional[str]      # Why rejected (for LLM tuning)
    created_at: str
    updated_at: str


class RoleContentImprovementSuggestion(TypedDict):
    """
    Suggestion to add/modify role markdown content.
    """
    suggestion_id: str                      # UUID
    suggestion_type: str                    # "add_achievement" | "modify_achievement" | "add_variant"
    target_role_id: str                     # Role ID
    target_section: Optional[str]           # Section within role file
    current_content: Optional[str]          # Current content (for modifications)
    suggested_content: str                  # Suggested new/modified content
    reason: str                             # Why this suggestion
    status: str                             # "pending" | "accepted" | "rejected"
    rejection_rationale: Optional[str]      # Why rejected (for LLM tuning)
    created_at: str
    updated_at: str


class ImprovementSuggestions(TypedDict):
    """
    All improvement suggestions for a job.

    Stored in job.improvement_suggestions field in MongoDB.
    """
    gap_analysis: List[GapAnalysisResult]
    skills_taxonomy_suggestions: List[SkillsImprovementSuggestion]
    role_metadata_suggestions: List[RoleMetadataImprovementSuggestion]
    role_content_suggestions: List[RoleContentImprovementSuggestion]
    generated_at: str                       # ISO timestamp
    generated_by: str                       # Model used for generation


# =============================================================================
# INTERVIEW PREP
# =============================================================================

class InterviewQuestion(TypedDict):
    """
    Predicted interview question based on gaps/concerns.

    Enhanced for Phase 7 with:
    - source_type to track origin (gap/concern/general)
    - difficulty classification for practice prioritization
    - sample_answer_outline for answer prep guidance
    - practice_status tracking for user progress
    - user_notes for personal answer notes
    """
    question_id: str                        # UUID
    question: str                           # The predicted question
    source_annotation_id: str               # Gap/concern annotation that triggered this
    source_type: str                        # "gap" | "concern" | "general"
    question_type: str                      # "gap_probe" | "concern_probe" | "behavioral" | "technical" | "situational"
    difficulty: str                         # "easy" | "medium" | "hard"
    suggested_answer_approach: str          # How to approach answering
    sample_answer_outline: Optional[str]    # Brief answer structure (not full answer)
    relevant_star_ids: List[str]            # STAR stories to reference
    practice_status: str                    # "not_started" | "practiced" | "confident"
    user_notes: Optional[str]               # User's own answer notes
    created_at: str


class InterviewPrep(TypedDict):
    """
    Interview preparation data for a job.

    Enhanced for Phase 7 with:
    - company_context for key company facts
    - role_context for key role insights
    - generated_by to track model used
    """
    predicted_questions: List[InterviewQuestion]
    gap_summary: str                        # Summary of gaps to address
    concerns_summary: str                   # Summary of concerns to address
    company_context: str                    # Key company facts for interview
    role_context: str                       # Key role insights
    generated_at: str
    generated_by: str                       # Model used for generation


# =============================================================================
# OUTCOME TRACKING
# =============================================================================

class AnnotationOutcome(TypedDict):
    """
    Tracks outcomes for annotation effectiveness analysis.
    """
    job_id: str

    # Annotation profile
    annotation_count: int
    core_strength_count: int
    extremely_relevant_count: int
    relevant_count: int
    tangential_count: int
    gap_count: int
    reframe_count: int
    concern_count: int
    section_coverage: float                 # 0.0-1.0

    # Outcomes (updated manually or via integration)
    applied: bool
    applied_at: Optional[str]
    response_received: bool
    response_at: Optional[str]
    interview_scheduled: bool
    interview_at: Optional[str]
    offer_received: bool
    offer_at: Optional[str]

    # Computed metrics
    days_to_response: Optional[int]
    days_to_interview: Optional[int]


# Outcome Status Constants (Phase 7)
OutcomeStatus = Literal[
    "not_applied",                          # Default state
    "applied",                              # Application submitted
    "response_received",                    # Got a response (any type)
    "screening_scheduled",                  # Phone/video screen scheduled
    "interview_scheduled",                  # Interview scheduled
    "interviewing",                         # In interview process
    "offer_received",                       # Got an offer
    "offer_accepted",                       # Accepted the offer
    "rejected",                             # Application rejected
    "withdrawn",                            # User withdrew
]


class ApplicationOutcome(TypedDict):
    """
    Tracks application outcome for a specific job (Phase 7).

    Stored in job document for per-job tracking.
    Enables annotation effectiveness analysis via OutcomeTracker.
    """
    status: str                             # OutcomeStatus value
    applied_at: Optional[str]               # ISO timestamp
    applied_via: Optional[str]              # "linkedin" | "website" | "email" | "referral"
    response_at: Optional[str]
    response_type: Optional[str]            # "rejection" | "interest" | "screening"
    screening_at: Optional[str]
    interview_at: Optional[str]
    interview_rounds: int                   # Number of interview rounds
    offer_at: Optional[str]
    offer_details: Optional[str]            # Brief notes about offer
    final_status_at: Optional[str]          # When final status was set
    notes: Optional[str]                    # User notes

    # Computed for analytics
    days_to_response: Optional[int]
    days_to_interview: Optional[int]
    days_to_offer: Optional[int]


# =============================================================================
# ATS READINESS
# =============================================================================

class KeywordDensityResult(TypedDict):
    """
    Keyword density analysis for ATS optimization.
    """
    keyword: str
    current_count: int
    target_min: int
    target_max: int
    status: str                             # "pass" | "low" | "high"
    sections_found: List[str]               # Which CV sections contain it
    variants_used: List[str]                # Which variants appear


class ATSReadinessReport(TypedDict):
    """
    ATS submission readiness analysis.
    """
    overall_ready: bool
    overall_score: int                      # 0-100

    # Component scores
    keywords_score: int                     # Keyword coverage
    keywords_status: str                    # "pass" | "warn" | "fail"
    sections_score: int                     # Required sections present
    sections_status: str
    variants_score: int                     # Keyword variants coverage
    variants_status: str
    lints_score: int                        # Validation rules pass
    lints_status: str

    # Details
    keyword_results: List[KeywordDensityResult]
    missing_variants: List[Dict[str, str]]  # [{"keyword": "Kubernetes", "missing": "K8s"}]
    missing_sections: List[str]
    lint_errors: List[str]

    # Recommendations
    recommendations: List[str]


# =============================================================================
# BOOST CALCULATION CONSTANTS
# =============================================================================

# Relevance multipliers (from plan)
RELEVANCE_MULTIPLIERS: Dict[str, float] = {
    "core_strength": 3.0,
    "extremely_relevant": 2.0,
    "relevant": 1.5,
    "tangential": 1.0,
    "gap": 0.3,
}

# Requirement type multipliers
REQUIREMENT_MULTIPLIERS: Dict[str, float] = {
    "must_have": 1.5,
    "nice_to_have": 1.0,
    "disqualifier": 0.0,
    "neutral": 1.0,
}

# Passion level multipliers
PASSION_MULTIPLIERS: Dict[str, float] = {
    "love_it": 1.5,       # Highlight prominently - shows authentic enthusiasm
    "enjoy": 1.2,         # Boost slightly - enjoyable aspects
    "neutral": 1.0,       # No modification
    "tolerate": 0.8,      # Slight penalty - can do but don't want to emphasize
    "avoid": 0.5,         # Significant penalty - de-emphasize in applications
}

# Identity level multipliers
IDENTITY_MULTIPLIERS: Dict[str, float] = {
    "core_identity": 2.0,     # Use prominently in headlines/introductions
    "strong_identity": 1.5,   # Significant part of identity - emphasize
    "developing": 1.2,        # Growing into this - mention with growth framing
    "peripheral": 1.0,        # Not central - include if relevant
    "not_identity": 0.3,      # Explicitly NOT how to be seen - avoid in intros
}

# Priority multipliers
PRIORITY_MULTIPLIERS: Dict[int, float] = {
    1: 1.5,
    2: 1.3,
    3: 1.0,
    4: 0.8,
    5: 0.6,
}

# Annotation type modifiers
TYPE_MODIFIERS: Dict[str, float] = {
    "skill_match": 1.0,
    "reframe": 1.2,
    "highlight": 0.8,
    "comment": 0.5,
    "concern": 0.0,
}

# Source multipliers (annotation origin weighting)
# Human annotations are gold standard, preset selections show intentionality,
# LLM suggestions are baseline that need human validation
SOURCE_MULTIPLIERS: Dict[str, float] = {
    "human": 1.2,              # Human annotations are gold standard
    "preset": 1.1,             # User-selected presets are intentional
    "pipeline_suggestion": 1.0,  # LLM suggestions are baseline
}

# Relevance level colors (for UI)
RELEVANCE_COLORS: Dict[str, Dict[str, str]] = {
    "core_strength": {"bg": "bg-green-500/20", "border": "border-green-500", "badge": "badge-green", "hex": "#22c55e"},
    "extremely_relevant": {"bg": "bg-teal-500/20", "border": "border-teal-500", "badge": "badge-teal", "hex": "#14b8a6"},
    "relevant": {"bg": "bg-blue-500/20", "border": "border-blue-500", "badge": "badge-blue", "hex": "#3b82f6"},
    "tangential": {"bg": "bg-yellow-500/20", "border": "border-yellow-500", "badge": "badge-yellow", "hex": "#eab308"},
    "gap": {"bg": "bg-red-500/20", "border": "border-red-500", "badge": "badge-red", "hex": "#ef4444"},
}

# Passion level colors (for UI) - using purple/pink spectrum to differentiate from relevance
PASSION_COLORS: Dict[str, Dict[str, str]] = {
    "love_it": {"bg": "bg-pink-500/20", "border": "border-pink-500", "badge": "badge-pink", "hex": "#ec4899", "emoji": "🔥"},
    "enjoy": {"bg": "bg-purple-500/20", "border": "border-purple-500", "badge": "badge-purple", "hex": "#a855f7", "emoji": "😊"},
    "neutral": {"bg": "bg-gray-500/20", "border": "border-gray-500", "badge": "badge-gray", "hex": "#6b7280", "emoji": "😐"},
    "tolerate": {"bg": "bg-slate-500/20", "border": "border-slate-500", "badge": "badge-slate", "hex": "#64748b", "emoji": "😕"},
    "avoid": {"bg": "bg-stone-500/20", "border": "border-stone-500", "badge": "badge-stone", "hex": "#78716c", "emoji": "🚫"},
}

# Identity level colors (for UI) - using indigo/cyan spectrum for professional identity
IDENTITY_COLORS: Dict[str, Dict[str, str]] = {
    "core_identity": {"bg": "bg-indigo-500/20", "border": "border-indigo-500", "badge": "badge-indigo", "hex": "#6366f1", "emoji": "⭐"},
    "strong_identity": {"bg": "bg-violet-500/20", "border": "border-violet-500", "badge": "badge-violet", "hex": "#8b5cf6", "emoji": "💪"},
    "developing": {"bg": "bg-cyan-500/20", "border": "border-cyan-500", "badge": "badge-cyan", "hex": "#06b6d4", "emoji": "🌱"},
    "peripheral": {"bg": "bg-gray-500/20", "border": "border-gray-500", "badge": "badge-gray", "hex": "#6b7280", "emoji": "○"},
    "not_identity": {"bg": "bg-zinc-500/20", "border": "border-zinc-500", "badge": "badge-zinc", "hex": "#71717a", "emoji": "✗"},
}
