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


class RunBulkRequest(BaseModel):
    """Request body for kicking off multiple job runs."""

    job_ids: List[str] = Field(..., min_items=1, description="Job identifiers to process.")
    profile_ref: Optional[str] = Field(None, description="Optional profile reference/path.")
    source: Optional[str] = Field(None, description="Origin of the request.")


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
