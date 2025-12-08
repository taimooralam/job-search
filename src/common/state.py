"""
State schema for the job intelligence pipeline.

This defines the data contract for the 7-layer LangGraph pipeline.
Each layer reads from and writes to this shared state.
"""

from typing import TypedDict, List, Optional, Dict, Any, Literal

# Contact type classification for outreach tailoring
# Based on linkedin/outreach.md guide principles
ContactType = Literal[
    "hiring_manager",   # Direct decision-maker: Engineering Manager, Team Lead, Hiring Manager
    "recruiter",        # Talent Acquisition, Recruiter, Sourcer, HR Business Partner
    "vp_director",      # VP Engineering, Director of X, Head of, Department Head
    "executive",        # C-level: CEO, CTO, CFO, COO, Founder, Co-Founder
    "peer"              # Staff/Principal Engineers, Architects, Senior ICs
]

# Import canonical STARRecord and FormField from types.py (Phase 2.1)
# This is the 22-field schema with List-typed fields for tasks, actions, results, metrics, etc.
from src.common.types import STARRecord, FormField


class CompetencyWeights(TypedDict):
    """
    Competency mix for role-category-aware CV tailoring.

    Weights must sum to 100. Used to determine emphasis in CV generation:
    - High delivery: Feature shipping, product execution
    - High process: CI/CD, testing, quality standards
    - High architecture: System design, technical strategy
    - High leadership: People management, mentorship
    """
    delivery: int       # 0-100: Shipping features, building products
    process: int        # 0-100: CI/CD, testing, quality standards
    architecture: int   # 0-100: System design, technical strategy
    leadership: int     # 0-100: People management, team building


class ExtractedJD(TypedDict):
    """
    Structured job description extraction (Layer 1.4).

    Provides structured intelligence from JDs to enable precise CV tailoring.
    Inserted before Layer 2 (Pain Point Miner) to provide context.
    """
    # Basic Info
    title: str
    company: str
    location: str
    remote_policy: str  # "fully_remote" | "hybrid" | "onsite" | "not_specified"

    # Role Classification (from cv-guide.plan.md)
    role_category: str  # "engineering_manager" | "staff_principal_engineer" |
                        # "director_of_engineering" | "head_of_engineering" | "cto"
    seniority_level: str  # "senior" | "staff" | "principal" | "director" | "vp" | "c_level"

    # Competency Mix (for emphasis decisions)
    competency_weights: CompetencyWeights

    # Content Extraction
    responsibilities: List[str]    # 5-10 key responsibilities
    qualifications: List[str]      # Required qualifications
    nice_to_haves: List[str]       # Optional qualifications
    technical_skills: List[str]    # Specific technologies mentioned
    soft_skills: List[str]         # Leadership, communication, etc.

    # Pain Points (inferred)
    implied_pain_points: List[str]  # What problems is this hire solving?
    success_metrics: List[str]      # How success will be measured

    # ATS Keywords
    top_keywords: List[str]  # 15 most important keywords for ATS matching

    # Background Requirements
    industry_background: Optional[str]  # e.g., "AdTech", "FinTech"
    years_experience_required: Optional[int]
    education_requirements: Optional[str]


class Contact(TypedDict):
    """
    Contact person at target company (Phase 7).

    Identified by Layer 5 with personalized outreach messages.
    Enhanced with contact_type classification and dual-format LinkedIn outreach.

    Contact types (from linkedin/outreach.md):
    - hiring_manager: Skills + team fit, peer-level thinking
    - recruiter: Keywords matching JD, quantified achievements
    - vp_director: Strategic outcomes, 50-150 words max
    - executive: Extreme brevity, industry trends
    - peer: Technical credibility, collaborative tone
    """
    name: str
    role: str
    linkedin_url: str
    contact_type: str              # ContactType: hiring_manager, recruiter, vp_director, executive, peer
    why_relevant: str
    recent_signals: List[str]      # Recent posts, promotions, projects (Phase 7)

    # Dual LinkedIn formats (from linkedin/outreach.md)
    linkedin_connection_message: str   # ≤300 chars INCLUDING Calendly link
    linkedin_inmail_subject: str       # 25-30 chars for mobile display
    linkedin_inmail: str               # 400-600 chars, longer format

    # Email outreach
    email_subject: str             # 5-10 words, ≤100 chars, pain-focused
    email_body: str                # 95-205 words with 2-3 metrics

    # Metadata
    reasoning: str
    already_applied_frame: str     # "adding_context" | "value_add" | "specific_interest"

    # Legacy field (backward compatibility)
    linkedin_message: str          # Deprecated: Use linkedin_connection_message or linkedin_inmail


class OutreachPackage(TypedDict):
    """
    Per-contact outreach package (Phase 7/9).

    Structured outreach for a specific contact across channels.
    Used by Layer 6b for per-lead personalization.

    Channels:
    - linkedin_connection: ≤300 chars with Calendly (connection request)
    - linkedin_inmail: 400-600 chars with subject (InMail/DM)
    - email: Full email with subject and body
    """
    contact_name: str
    contact_role: str
    contact_type: str              # ContactType for tailored approach
    linkedin_url: str
    channel: str                   # "linkedin_connection" | "linkedin_inmail" | "email"
    message: str                   # Main outreach message
    subject: Optional[str]         # Email/InMail subject (None for connection request)
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
    company_type: str              # "employer" | "recruitment_agency" | "unknown"


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

    # ===== LAYER 1.4: JD Extractor (CV Gen V2) =====
    # Extracts structured intelligence from job descriptions
    extracted_jd: Optional[ExtractedJD]  # Structured JD extraction for CV tailoring

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

    # ===== LAYER 1.5: Application Form Extractor =====
    # Extracts form fields from job application pages for pre-filling
    application_form_fields: Optional[List[FormField]]  # Form fields with labels, types, requirements

    # ===== LAYER 4: Opportunity Mapper (Phase 6) =====
    fit_score: Optional[int]         # 0-100 overall fit rating
    fit_rationale: Optional[str]     # 2-3 sentence explanation of score with STAR citations + metrics
    fit_category: Optional[str]      # "exceptional" | "strong" | "good" | "moderate" | "weak"
    tier: Optional[str]              # Job priority tier: "A" (85+), "B" (70-84), "C" (50-69), "D" (<50)

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
    dossier_path: Optional[str]      # Path to generated dossier file (local or Drive)
    drive_folder_url: Optional[str]  # Google Drive folder URL for this job
    sheet_row_id: Optional[int]      # Row number in tracking sheet

    # ===== METADATA =====
    run_id: Optional[str]            # Unique pipeline run identifier (UUID)
    created_at: Optional[str]        # ISO timestamp when pipeline started
    errors: Optional[List[str]]      # Error messages from any layer

    # Processing flags
    status: Optional[str]            # "processing", "completed", "failed"

    # ===== DISTRIBUTED TRACING (Gap OB-3) =====
    trace_url: Optional[str]         # LangSmith trace URL for debugging/analysis

    # ===== TOKEN TRACKING (Gap BG-1) =====
    # Tracks token usage per provider and layer for budget enforcement
    token_usage: Optional[Dict[str, Dict]]  # {"openai": {"input": X, "output": Y, "cost": Z}, ...}
    total_tokens: Optional[int]      # Total tokens used across all providers
    total_cost_usd: Optional[float]  # Estimated cost in USD

    # ===== TIERED PROCESSING (Gap 045) =====
    # Controls which models and features are used based on job fit/priority
    processing_tier: Optional[str]   # "A" (gold), "B" (silver), "C" (bronze), "D" (skip)
    tier_config: Optional[Dict[str, Any]]  # Full tier configuration (models, limits, etc.)

    # ===== PIPELINE RUN HISTORY =====
    # Tracks each pipeline run with cost and tier for historical analysis
    # Each entry: {"run_id": str, "tier": str, "cost_usd": float, "timestamp": str, "status": str}
    pipeline_runs: Optional[List[Dict[str, Any]]]

    # ===== DEBUG MODE (API debug=true) =====
    # When enabled, verbose logging throughout the pipeline
    debug_mode: Optional[bool]  # True enables DEBUG level logging across all layers
