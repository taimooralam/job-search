"""
State schema for the job intelligence pipeline.

This defines the data contract for the 7-layer LangGraph pipeline.
Each layer reads from and writes to this shared state.
"""

from typing import TypedDict, List, Optional, Dict

# Import canonical STARRecord from types.py (Phase 2.1)
# This is the 22-field schema with List-typed fields for tasks, actions, results, metrics, etc.
from src.common.types import STARRecord


class Contact(TypedDict):
    """
    Contact person at target company (Phase 7).

    Identified by Layer 5 with personalized outreach messages.
    Enhanced with recent_signals for context-aware outreach.
    """
    name: str
    role: str
    linkedin_url: str
    why_relevant: str
    recent_signals: List[str]      # Recent posts, promotions, projects (Phase 7)
    linkedin_message: str
    email_subject: str
    email_body: str
    reasoning: str


class OutreachPackage(TypedDict):
    """
    Per-contact outreach package (Phase 7/9).

    Structured outreach for a specific contact across channels.
    Used by Layer 6b for per-lead personalization.
    """
    contact_name: str
    contact_role: str
    linkedin_url: str
    channel: str                   # "linkedin" or "email"
    message: str                   # Main outreach message
    subject: Optional[str]         # Email subject (None for LinkedIn)
    reasoning: str                 # Why this approach works for this contact


class CompanySignal(TypedDict):
    """
    Company signal extracted from research (Phase 5).

    Represents a business event or milestone (funding, acquisition, leadership change, etc.)
    with source attribution to prevent hallucination.
    """
    type: str           # "funding", "acquisition", "leadership_change", "product_launch", "partnership", "growth"
    description: str    # Brief description of the signal
    date: str          # ISO date or "unknown" if not found in scraped content
    source: str        # URL where this signal was found


class CompanyResearch(TypedDict):
    """
    Structured company research output (Phase 5.1).

    Enhanced version of company_summary with structured signals and source attribution.
    Replaces simple text summary with JSON-validated structured data.
    """
    summary: str                    # 2-3 sentence company summary
    signals: List[CompanySignal]   # Business signals with dates and sources
    url: str                       # Primary company URL


class RoleResearch(TypedDict):
    """
    Role-specific research output (Phase 5.2).

    Analyzes the specific role's business impact and timing significance.
    Links to company signals to explain "why now" for this hire.
    """
    summary: str                   # 2-3 sentence role summary (ownership, scope, team)
    business_impact: List[str]    # 3-5 bullets on how role drives business outcomes
    why_now: str                  # 1-2 sentences linking to company signals


class JobState(TypedDict):
    """
    Shared state for job processing pipeline.

    State flows through layers:
    INPUT → Layer 2 → Layer 2.5 → Layer 3 → Layer 4 → Layer 5 → Layer 6 → Layer 7 → OUTPUT

    Each layer enriches the state by filling in its assigned fields.
    Layer 2.5 (STAR Selector) added in Phase 1.3 to enable hyper-personalization.
    """

    # ===== INPUT: From MongoDB =====
    job_id: str                      # MongoDB _id or jobId
    title: str                       # Job title (e.g., "Senior Manager, YouTube Paid Performance")
    company: str                     # Company name (e.g., "Launch Potato")
    job_description: str             # Full job description text
    scraped_job_posting: Optional[str]  # Scraped job posting markdown (from job_url)
    job_url: str                     # LinkedIn/Indeed job posting URL
    source: str                      # Job source (e.g., "linkedin", "indeed")

    # Candidate data (loaded from knowledge-base.md)
    candidate_profile: str           # Full text of candidate's profile/resume

    # ===== LAYER 2: Pain-Point Miner (JSON Mode - Phase 1.3) =====
    # Returns 4 arrays analyzing the underlying business drivers
    pain_points: Optional[List[str]]              # Specific problems they need solved
    strategic_needs: Optional[List[str]]          # Why this role matters strategically
    risks_if_unfilled: Optional[List[str]]        # Consequences if role stays empty
    success_metrics: Optional[List[str]]          # How they'll measure success

    # ===== LAYER 2.5: STAR Selector (Phase 1.3) =====
    # Selects 2-3 best-fit STAR records for this job
    # Enables hyper-personalization by mapping pain points to specific achievements
    selected_stars: Optional[List[STARRecord]]                # 2-3 most relevant STAR achievements
    star_to_pain_mapping: Optional[Dict[str, List[str]]]     # pain_point -> [star_ids with score >= 7]
    all_stars: Optional[List[STARRecord]]                     # Phase 8.2: Full STAR library for CV generation

    # ===== LAYER 3: Company & Role Researcher (Phase 5) =====
    # Phase 5.1: Enhanced Company Researcher with structured signals
    company_research: Optional[CompanyResearch]  # Structured company research with signals

    # Legacy fields (backward compatibility - populated from company_research)
    company_summary: Optional[str]   # Deprecated: Use company_research.summary
    company_url: Optional[str]       # Deprecated: Use company_research.url

    # Phase 5.2: Role Researcher analyzes business impact and timing
    role_research: Optional[RoleResearch]  # Role analysis with "why now" context

    # ===== LAYER 4: Opportunity Mapper (Phase 6) =====
    fit_score: Optional[int]         # 0-100 overall fit rating
    fit_rationale: Optional[str]     # 2-3 sentence explanation of score with STAR citations + metrics
    fit_category: Optional[str]      # "exceptional" | "strong" | "good" | "moderate" | "weak"

    # ===== LAYER 5: People Mapper (Phase 7) =====
    # Phase 7: Enhanced with primary/secondary classification and multi-source discovery
    primary_contacts: Optional[List[Contact]]    # 4-6 hiring-related contacts (manager, recruiter, etc.)
    secondary_contacts: Optional[List[Contact]]  # 4-6 cross-functional/peer contacts
    people: Optional[List[Contact]]              # Legacy field (deprecated, use primary_contacts + secondary_contacts)
    outreach_packages: Optional[List[OutreachPackage]]  # Per-contact outreach (Phase 7/9)
    fallback_cover_letters: Optional[List[str]]  # Fallback when no contacts discovered

    # ===== LAYER 6: Generator (SIMPLIFIED) =====
    # TODAY: Simple cover letter + basic CV
    # FUTURE: Will add per-person outreach templates
    cover_letter: Optional[str]      # 3-paragraph outreach draft
    cv_path: Optional[str]           # Path to generated tailored CV file
    cv_text: Optional[str]           # Full CV content (markdown) for MongoDB persistence
    cv_reasoning: Optional[str]      # Phase 8.2: Rationale for STAR selection, competency mix, gap mitigation

    # ===== LAYER 7: Publisher =====
    drive_folder_url: Optional[str]  # Google Drive folder URL for this job
    sheet_row_id: Optional[int]      # Row number in tracking sheet

    # ===== METADATA =====
    run_id: Optional[str]            # Unique pipeline run identifier (UUID)
    created_at: Optional[str]        # ISO timestamp when pipeline started
    errors: Optional[List[str]]      # Error messages from any layer

    # Processing flags
    status: Optional[str]            # "processing", "completed", "failed"
