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
