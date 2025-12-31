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
    pdf_service_status: Optional[str] = None
    pdf_service_error: Optional[str] = None


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


# === Indeed Import Models ===

class IndeedImportRequest(BaseModel):
    """Request body for importing an Indeed job."""

    job_key_or_url: str = Field(..., description="Indeed job key or URL")


class IndeedImportResponse(BaseModel):
    """Response after importing an Indeed job."""

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


# === Bulk Operation Models ===


class BulkOperationRequest(BaseModel):
    """Request body for bulk operation execution (extraction, research, CV generation)."""

    job_ids: List[str] = Field(..., min_items=1, description="Job identifiers to process.")
    tier: str = Field(default="B", description="Processing tier: A (gold), B (silver), C (bronze)")
    # Operation-specific fields
    force_refresh: Optional[bool] = Field(
        default=False, description="Force refresh for company research (ignore cache)"
    )
    use_llm: Optional[bool] = Field(
        default=True, description="Use LLM for extraction (vs rule-based)"
    )


class BulkOperationRunInfo(BaseModel):
    """Information about a single run in a bulk operation."""

    run_id: str = Field(..., description="Unique run identifier for SSE streaming")
    job_id: str = Field(..., description="Job ID being processed")
    log_stream_url: str = Field(..., description="URL to stream logs via SSE")
    status: str = Field(default="queued", description="Initial status")


class BulkOperationResponse(BaseModel):
    """Response for bulk operation kickoff."""

    runs: List[BulkOperationRunInfo] = Field(..., description="List of runs created")
    total_count: int = Field(..., description="Total number of jobs queued")


# === Queue Operation Models (Detail Page Pipeline Buttons) ===


class QueueOperationRequest(BaseModel):
    """Request body for queuing a pipeline operation from the job detail page."""

    tier: str = Field(
        default="balanced",
        description="Model tier: 'fast', 'balanced', or 'quality'"
    )
    force_refresh: Optional[bool] = Field(
        default=False,
        description="Force refresh for company research (ignore cache)"
    )
    use_llm: Optional[bool] = Field(
        default=True,
        description="Use LLM for extraction (vs rule-based)"
    )
    use_annotations: Optional[bool] = Field(
        default=True,
        description="Whether to incorporate user annotations for CV generation"
    )


class QueueOperationResponse(BaseModel):
    """Response after queuing a pipeline operation."""

    success: bool = Field(..., description="Whether the operation was queued successfully")
    queue_id: str = Field(..., description="Unique queue entry ID")
    job_id: str = Field(..., description="MongoDB job ID")
    operation: str = Field(..., description="Operation type queued")
    status: str = Field(default="pending", description="Initial status (always 'pending')")
    position: int = Field(..., description="Position in queue (1-indexed)")
    estimated_wait_seconds: Optional[int] = Field(
        None,
        description="Estimated wait time in seconds (based on queue position)"
    )
    run_id: Optional[str] = Field(
        None,
        description="Operation run ID for SSE log streaming via /api/runner/operations/{run_id}/logs"
    )
    error: Optional[str] = Field(None, description="Error message if queuing failed")


class OperationQueueStatus(BaseModel):
    """Status of a single operation in the queue for a specific job."""

    status: str = Field(..., description="Operation status: pending, running, completed, failed, or null if never queued")
    queue_id: Optional[str] = Field(None, description="Queue item ID if queued")
    run_id: Optional[str] = Field(None, description="Run ID for log streaming if started")
    position: Optional[int] = Field(None, description="Queue position if pending")
    started_at: Optional[datetime] = Field(None, description="When operation started")
    completed_at: Optional[datetime] = Field(None, description="When operation completed")
    error: Optional[str] = Field(None, description="Error message if failed")


class JobQueueStatusResponse(BaseModel):
    """Response containing queue status for all operations on a specific job."""

    job_id: str = Field(..., description="MongoDB job ID")
    operations: Dict[str, Optional[OperationQueueStatus]] = Field(
        ...,
        description="Queue status for each operation type. None if never queued."
    )


# === Diagnostics Models ===


class ConnectionStatus(BaseModel):
    """Status for a service connection (MongoDB, Redis, PDF service)."""

    status: str = Field(..., description="Connection status: healthy, unhealthy, unknown")
    latency_ms: Optional[float] = Field(None, description="Round-trip latency in milliseconds")
    error: Optional[str] = Field(None, description="Error message if connection failed")
    details: Optional[Dict[str, str]] = Field(None, description="Additional connection details")


class SystemHealthStatus(BaseModel):
    """Overall system health assessment."""

    status: str = Field(..., description="Overall status: healthy, degraded, unhealthy")
    issues: List[str] = Field(default_factory=list, description="Critical issues requiring attention")
    warnings: List[str] = Field(default_factory=list, description="Warnings that may need attention")


class CircuitBreakerSummary(BaseModel):
    """Summary of circuit breaker states across all services."""

    total: int = Field(..., description="Total number of circuit breakers")
    closed: int = Field(..., description="Breakers in closed (healthy) state")
    open: int = Field(..., description="Breakers in open (failing) state")
    half_open: int = Field(..., description="Breakers in half-open (recovering) state")
    by_service: Dict[str, Dict[str, str]] = Field(
        default_factory=dict, description="Per-service circuit breaker details"
    )


class RateLimitSummary(BaseModel):
    """Summary of rate limit status across all providers."""

    total_requests: int = Field(..., description="Total requests made across all providers")
    total_waits: int = Field(..., description="Total times we had to wait due to rate limits")
    by_provider: Dict[str, Dict[str, float]] = Field(
        default_factory=dict, description="Per-provider rate limit stats"
    )


class CapacityMetrics(BaseModel):
    """Runner capacity and queue metrics."""

    active_runs: int = Field(..., description="Currently executing pipeline runs")
    max_concurrency: int = Field(..., description="Maximum concurrent runs allowed")
    capacity_percent: float = Field(..., description="Percentage of capacity in use (0-100)")
    queue_depth: int = Field(..., description="Number of jobs waiting in queue")
    queue_running: int = Field(..., description="Number of jobs currently running from queue")
    queue_failed: int = Field(..., description="Number of failed jobs in queue")


class AlertEntry(BaseModel):
    """Single alert entry from alert history."""

    alert_id: str = Field(..., description="Unique alert identifier (MD5 hash)")
    level: str = Field(..., description="Alert level: info, warning, error, critical")
    message: str = Field(..., description="Alert message")
    source: str = Field(..., description="Component that raised the alert")
    timestamp: datetime = Field(..., description="When the alert was raised")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional context")


class ClaudeCodeStatus(BaseModel):
    """Status for Claude Code CLI availability.

    Used for parallel JD extraction via Claude Max subscription.
    """

    available: bool = Field(..., description="Whether Claude Code CLI is available and authenticated")
    model: str = Field(..., description="Configured Claude model (e.g., claude-opus-4-5-20251101)")
    auth_method: str = Field(
        ...,
        description="Authentication method: oauth_token, api_key, or none"
    )
    error: Optional[str] = Field(None, description="Error message if unavailable")


class DiagnosticsResponse(BaseModel):
    """Comprehensive diagnostics response for system health monitoring.

    This endpoint aggregates all diagnostic information for production debugging:
    - Service connections (MongoDB, Redis, PDF service)
    - API credit status (FireCrawl, OpenRouter)
    - Circuit breaker states
    - Rate limit status
    - Recent alerts
    - Capacity metrics
    """

    # System info
    timestamp: datetime = Field(..., description="Response timestamp")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    version: str = Field(..., description="Service version")
    environment: str = Field(..., description="Environment: development, staging, production")

    # Connection status
    mongodb: ConnectionStatus = Field(..., description="MongoDB connection status")
    redis: ConnectionStatus = Field(..., description="Redis queue connection status")
    pdf_service: ConnectionStatus = Field(..., description="PDF service connection status")

    # API credits
    firecrawl_credits: Optional[FireCrawlCreditsResponse] = Field(
        None, description="FireCrawl API credit status"
    )
    openrouter_credits: Optional[OpenRouterCreditsResponse] = Field(
        None, description="OpenRouter API credit status"
    )

    # Claude Code CLI status (for parallel JD extraction)
    claude_code: Optional[ClaudeCodeStatus] = Field(
        None, description="Claude Code CLI availability for JD extraction"
    )

    # System metrics
    system_health: SystemHealthStatus = Field(..., description="Overall system health")
    circuit_breakers: CircuitBreakerSummary = Field(..., description="Circuit breaker summary")
    rate_limits: RateLimitSummary = Field(..., description="Rate limit summary")
    capacity: CapacityMetrics = Field(..., description="Runner capacity metrics")

    # Alerts
    recent_alerts: List[AlertEntry] = Field(
        default_factory=list, description="Recent alerts (last 20)"
    )
    alert_stats: Dict[str, int] = Field(
        default_factory=dict, description="Alert statistics by level"
    )
