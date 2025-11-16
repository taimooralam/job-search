"""
State schema for the job intelligence pipeline.

This defines the simplified data contract for TODAY'S SCOPE (16 Nov vertical slice).
NOT the full Opportunity Dossier format - we'll build toward that iteratively.

Each layer reads from and writes to this shared state.
"""

from typing import TypedDict, List, Optional


class JobState(TypedDict):
    """
    Shared state for job processing pipeline - SIMPLIFIED VERSION.

    State flows through layers:
    INPUT → Layer 2 → Layer 3 → Layer 4 → SKIP Layer 5 → Layer 6 → Layer 7 → OUTPUT

    Each layer enriches the state by filling in its assigned fields.
    """

    # ===== INPUT: From MongoDB =====
    job_id: str                      # MongoDB _id or jobId
    title: str                       # Job title (e.g., "Senior Manager, YouTube Paid Performance")
    company: str                     # Company name (e.g., "Launch Potato")
    job_description: str             # Full job description text
    job_url: str                     # LinkedIn/Indeed job posting URL
    source: str                      # Job source (e.g., "linkedin", "indeed")

    # Candidate data (loaded from knowledge-base.md)
    candidate_profile: str           # Full text of candidate's profile/resume

    # ===== LAYER 2: Pain-Point Miner (SIMPLIFIED) =====
    # TODAY: Just 3-5 bullet points
    # FUTURE: Will expand to include strategic_needs, risks_if_unfilled, success_metrics
    pain_points: Optional[List[str]]

    # ===== LAYER 3: Company Researcher (SIMPLIFIED) =====
    # TODAY: Just a 2-3 sentence summary
    # FUTURE: Will expand to include signals, timing, industry, keywords
    company_summary: Optional[str]
    company_url: Optional[str]       # Scraped company website URL

    # ===== LAYER 4: Opportunity Mapper (SIMPLIFIED) =====
    # TODAY: Simple fit score + rationale
    # FUTURE: Will expand to include hiring_reasoning, timing_significance, signals
    fit_score: Optional[int]         # 0-100 overall fit rating
    fit_rationale: Optional[str]     # 2-3 sentence explanation of score

    # ===== LAYER 5: People Mapper =====
    # SKIPPED FOR TODAY - will add in Phase 4
    # people: Optional[List[Contact]]

    # ===== LAYER 6: Generator (SIMPLIFIED) =====
    # TODAY: Simple cover letter + basic CV
    # FUTURE: Will add per-person outreach templates
    cover_letter: Optional[str]      # 3-paragraph outreach draft
    cv_path: Optional[str]           # Path to generated tailored CV file

    # ===== LAYER 7: Publisher =====
    drive_folder_url: Optional[str]  # Google Drive folder URL for this job
    sheet_row_id: Optional[int]      # Row number in tracking sheet

    # ===== METADATA =====
    run_id: Optional[str]            # Unique pipeline run identifier (UUID)
    created_at: Optional[str]        # ISO timestamp when pipeline started
    errors: Optional[List[str]]      # Error messages from any layer

    # Processing flags
    status: Optional[str]            # "processing", "completed", "failed"
