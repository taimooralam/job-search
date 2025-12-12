"""
Canonical Types and Schemas for the Job Intelligence Pipeline

This module defines the canonical data structures used throughout the pipeline,
including the STARRecord schema for knowledge base management and job-related types.
"""

from typing import Any, Dict, List, Optional, TypedDict
from typing_extensions import NotRequired


class STARRecord(TypedDict):
    """
    Canonical STAR achievement record schema.

    This is the lossless representation of a CV bullet or achievement,
    designed for three distinct uses:
    1. Narrative grounding (background, STAR elements, impact)
    2. Retrieval & matching (domains, skills, keywords, metrics, pain points)
    3. Compression for generation (condensed version + key metrics)
    """
    # Basic identification
    id: str                            # Unique identifier (UUID)
    company: str                       # Company name
    role_title: str                    # Job title/role
    period: str                        # Time period (e.g., "2019-2022")

    # Content areas
    domain_areas: List[str]            # Domain/industry areas (e.g., ["AdTech", "Cloud", "Architecture"])
    background_context: str            # Rich narrative context and nuance
    situation: str                     # STAR - Situation (1-3 sentences)
    tasks: List[str]                   # STAR - Task(s) as atomic list
    actions: List[str]                 # STAR - Actions as atomic list
    results: List[str]                 # STAR - Results as atomic list

    # Summary fields
    impact_summary: str                # Overall impact and transformation achieved
    condensed_version: str             # Primary LLM input: "[Role] at [Company]: S/T → A → R with metrics"

    # Metadata for matching
    ats_keywords: List[str]            # ATS/SEO keywords for matching
    categories: List[str]              # High-level categories (e.g., ["Architecture", "Leadership"])
    hard_skills: List[str]             # Technical skills (e.g., ["AWS", "TypeScript", "Kubernetes"])
    soft_skills: List[str]             # Soft skills (e.g., ["Leadership", "Communication"])
    metrics: List[str]                 # Quantified achievements (e.g., ["reduced costs by 75%"])

    # Pain-point and outcome mapping (NEW)
    pain_points_addressed: List[str]   # 1-3 business/technical pains solved (hiring manager language)
    outcome_types: List[str]           # Outcome categories (e.g., ["cost_reduction", "risk_mitigation"])

    # Targeting and metadata
    target_roles: List[str]            # Target job titles this STAR supports
    metadata: Dict[str, Any]           # Seniority weights, sources, versioning, tags

    # Technical fields
    embedding: Optional[List[float]]   # Vector embedding for similarity search


class FormField(TypedDict):
    """Application form field extracted from job posting."""
    label: str                         # Field label/question
    field_type: str                    # Type: text, textarea, url, file, checkbox, select
    required: bool                     # Whether field is required
    limit: Optional[int]               # Character/word limit if applicable
    default_value: Optional[str]       # Default value or hint text
    options: Optional[List[str]]       # Options for select/checkbox fields


class PlannedAnswer(TypedDict):
    """Pre-planned answer for an application form question."""
    question: str                      # The question text
    answer: str                        # The prepared answer
    field_type: str                    # text | textarea | url | select | checkbox | file
    field_id: NotRequired[str]         # Optional form field identifier
    required: NotRequired[bool]        # Whether field is required
    max_length: NotRequired[int]       # Character limit if applicable
    source: NotRequired[str]           # "auto_generated" | "manual"


class JobState(TypedDict):
    """State object for a job as it flows through the pipeline."""
    # Job identification
    job_id: str
    company: str
    role: str
    job_url: str
    location: str

    # Job details
    description: str
    posted_at: str
    score: Optional[float]
    tier: Optional[str]

    # Layer outputs
    application_form_fields: Optional[List[FormField]]
    pain_points: Optional[List[str]]
    strategic_needs: Optional[List[str]]
    risks_if_unfilled: Optional[List[str]]
    success_metrics: Optional[List[str]]

    # Company research
    company_signals: Optional[Dict[str, Any]]
    role_specifics: Optional[Dict[str, Any]]

    # STAR selection
    selected_stars: Optional[List[str]]  # STAR IDs
    star_to_pain_mapping: Optional[Dict[str, List[str]]]
    star_selection_reasoning: Optional[str]

    # Generated content
    outreach_draft: Optional[str]
    cover_letter_draft: Optional[str]
    cv_draft: Optional[str]

    # Pipeline metadata
    pipeline_run_at: Optional[str]
    pipeline_status: Optional[str]
    error_messages: Optional[List[str]]


# Outcome type constants for validation
OUTCOME_TYPES = [
    "cost_reduction",
    "cost_avoidance",
    "risk_reduction",
    "risk_mitigation",
    "velocity_increase",
    "time_to_market",
    "quality_improvement",
    "reliability",
    "revenue_growth",
    "user_growth",
    "team_efficiency",
    "developer_experience",
    "compliance_achievement",
    "technical_debt_reduction",
    "innovation",
    "scalability",
    "security_improvement",
    "performance_optimization",
]