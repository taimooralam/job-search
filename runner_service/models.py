"""
Shared Pydantic models for the runner service.

These models define the structure for API requests, responses, and internal state.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RunJobRequest(BaseModel):
    """Request body for kicking off a single job run."""

    job_id: str = Field(..., description="Job identifier to process.")
    profile_ref: Optional[str] = Field(
        None, description="Optional profile reference/path to pass to the pipeline."
    )
    source: Optional[str] = Field(None, description="Origin of the request.")
    processing_tier: Optional[str] = Field(
        "auto",
        description="Processing tier: 'auto' (recommended), 'A' (gold), 'B' (silver), 'C' (bronze), 'D' (skip)"
    )


class RunBulkRequest(BaseModel):
    """Request body for kicking off multiple job runs."""

    job_ids: List[str] = Field(..., min_items=1, description="Job identifiers to process.")
    profile_ref: Optional[str] = Field(None, description="Optional profile reference/path.")
    source: Optional[str] = Field(None, description="Origin of the request.")
    processing_tier: Optional[str] = Field(
        "auto",
        description="Processing tier for all jobs: 'auto', 'A', 'B', 'C', 'D'"
    )


class RunResponse(BaseModel):
    """Response after enqueuing a job run."""

    run_id: str
    status_url: str
    log_stream_url: str


class StatusResponse(BaseModel):
    """Status payload for a job run."""

    run_id: str
    job_id: str
    status: str
    started_at: datetime
    updated_at: datetime
    artifacts: Dict[str, str]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    active_runs: int
    max_concurrency: int
    timestamp: datetime


# === Pipeline Progress Models (Gap #25) ===

class LayerProgress(BaseModel):
    """Progress state for a single pipeline layer."""

    layer: str = Field(..., description="Layer identifier (e.g., 'intake', 'pain_points')")
    status: str = Field(
        default="pending",
        description="Layer status: pending, executing, success, failed, skipped"
    )
    started_at: Optional[datetime] = Field(None, description="When layer started executing")
    completed_at: Optional[datetime] = Field(None, description="When layer completed")
    duration_ms: Optional[int] = Field(None, description="Execution duration in milliseconds")
    error: Optional[str] = Field(None, description="Error message if failed")


class PipelineProgressResponse(BaseModel):
    """Full pipeline progress with layer-by-layer status."""

    run_id: str
    job_id: str
    overall_status: str = Field(
        ..., description="Overall status: queued, running, completed, failed"
    )
    progress_percent: int = Field(
        ..., ge=0, le=100, description="Overall progress 0-100"
    )
    layers: List[LayerProgress] = Field(default_factory=list)
    current_layer: Optional[str] = Field(None, description="Currently executing layer")
    started_at: datetime
    updated_at: datetime


# === LinkedIn Import Models (GAP-065) ===

class LinkedInImportRequest(BaseModel):
    """Request body for importing a LinkedIn job."""

    job_id_or_url: str = Field(..., description="LinkedIn job ID or URL")


class LinkedInImportResponse(BaseModel):
    """Response after importing a LinkedIn job."""

    success: bool = True
    job_id: str = Field(..., description="MongoDB job ID")
    title: str
    company: str
    location: Optional[str] = None
    score: Optional[int] = None
    tier: Optional[str] = None
    score_rationale: Optional[str] = None
    duplicate: bool = False
    error: Optional[str] = None


# Pipeline layer definitions for progress tracking
PIPELINE_LAYERS = [
    {"id": "intake", "name": "Job Intake", "order": 1},
    {"id": "pain_points", "name": "Pain Point Mining", "order": 2},
    {"id": "company_research", "name": "Company Research", "order": 3},
    {"id": "role_research", "name": "Role Research", "order": 3},
    {"id": "opportunity_mapping", "name": "Opportunity Mapping", "order": 4},
    {"id": "people_mapping", "name": "People Mapping", "order": 5},
    {"id": "output_generation", "name": "Output Generation", "order": 6},
    {"id": "output_publishing", "name": "Output Publishing", "order": 7},
]


# === FireCrawl Credits Models (GAP-070) ===

class FireCrawlCreditsResponse(BaseModel):
    """Response for FireCrawl credit usage tracking."""

    provider: str = "firecrawl"
    daily_limit: int = Field(..., description="Maximum daily FireCrawl requests")
    used_today: int = Field(..., description="Requests made today")
    remaining: int = Field(..., description="Remaining requests today")
    used_percent: float = Field(..., description="Percentage of daily limit used")
    requests_this_minute: int = Field(0, description="Requests in current minute")
    requests_per_minute_limit: int = Field(10, description="Per-minute rate limit")
    last_request_at: Optional[datetime] = Field(None, description="Timestamp of last request")
    daily_reset_at: Optional[datetime] = Field(None, description="When daily counter resets")
    status: str = Field(
        "healthy",
        description="Status: healthy, warning (>80%), critical (>90%), exhausted (100%)"
    )


# === OpenRouter Credits Models ===

class OpenRouterCreditsResponse(BaseModel):
    """Response for OpenRouter credit balance tracking."""

    provider: str = "openrouter"
    credits_remaining: float = Field(..., description="Remaining credits in USD")
    credits_used: Optional[float] = Field(None, description="Credits used (if available)")
    status: str = Field(
        "healthy",
        description="Status: healthy, warning (<$5), critical (<$1), exhausted ($0)"
    )
    error: Optional[str] = Field(None, description="Error message if API call failed")
