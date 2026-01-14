"""
Job Ingestion Routes

On-demand job ingestion endpoint for fetching jobs from external sources
(Himalaya, etc.) and inserting them into MongoDB level-2 collection.

This endpoint runs on the VPS runner service, using Claude CLI for
scoring (free with Max subscription).

Supports real-time verbose logging via Redis + LogPoller infrastructure.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from ..auth import verify_token
from .operation_streaming import (
    create_operation_run,
    create_log_callback,
    update_operation_status,
    get_operation_state,
)
from src.common.repositories import get_system_state_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["ingestion"])


# =============================================================================
# Structured Log Helpers for Livetail
# =============================================================================


def _emit_structured_log(
    log_callback: Callable[[str], None],
    event: str,
    message: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    Emit a structured JSON log entry to the operation log buffer.

    This enables rich frontend display with backend attribution, cost tracking,
    and proper event parsing.

    Args:
        log_callback: The log callback from create_log_callback
        event: Event type (e.g., "llm_call_complete", "ingest_start")
        message: Optional human-readable message
        **kwargs: Additional fields (backend, cost_usd, duration_ms, metadata, etc.)
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
    }
    if message:
        log_entry["message"] = message

    # Add all additional fields
    for key, value in kwargs.items():
        if value is not None:
            log_entry[key] = value

    log_callback(json.dumps(log_entry))


def create_progress_callback(
    log_callback: Callable[[str], None],
) -> Callable[[str, str, Dict[str, Any]], None]:
    """
    Create a progress callback compatible with UnifiedLLM's progress_callback.

    This bridges the gap between UnifiedLLM's event system and the operation
    log buffer, enabling full cost tracking and backend attribution in the frontend.

    Args:
        log_callback: The log callback from create_log_callback

    Returns:
        A callback with signature (event_type, message, data) -> None
    """
    def callback(event_type: str, message: str, data: Dict[str, Any]) -> None:
        # Map UnifiedLLM event types to StructuredLogger events
        event_map = {
            "llm_start": "llm_call_start",
            "llm_complete": "llm_call_complete",
            "llm_error": "llm_call_error",
            "llm_fallback": "llm_call_fallback",
        }
        event = event_map.get(event_type, event_type)

        # Build structured log entry
        log_entry = {
            "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
            "event": event,
            "message": message,
            **{k: v for k, v in data.items() if k != "timestamp" and v is not None},
        }
        log_callback(json.dumps(log_entry))

    return callback

# In-memory storage for ingest results (keyed by run_id)
_ingest_results: Dict[str, "IngestResponse"] = {}


class IngestStartResponse(BaseModel):
    """Response when starting an async ingestion operation."""

    run_id: str
    status: str
    source: str


class IngestResultResponse(BaseModel):
    """Response when polling for ingestion result."""

    run_id: str
    status: str  # "queued", "running", "completed", "failed"
    result: Optional["IngestResponse"] = None
    error: Optional[str] = None


class IngestResponse(BaseModel):
    """Response model for ingestion endpoint."""

    success: bool
    source: str
    incremental: bool
    stats: dict
    last_fetch_at: Optional[str] = None
    jobs: List[dict] = Field(default_factory=list)
    error: Optional[str] = None


def _store_ingest_result(run_id: str, result: "IngestResponse") -> None:
    """Store ingestion result for later retrieval."""
    _ingest_results[run_id] = result


def _get_stored_ingest_result(run_id: str) -> Optional["IngestResponse"]:
    """Retrieve stored ingestion result."""
    return _ingest_results.get(run_id)


def get_default_keywords() -> List[str]:
    """
    Get default keywords from Indeed search terms config.

    Falls back to Himalaya keywords, then sensible defaults.
    """
    # Try Indeed search terms first (user preference)
    indeed_terms = os.getenv("INDEED_SEARCH_TERMS", "")
    if indeed_terms:
        return [term.strip() for term in indeed_terms.split(",") if term.strip()]

    # Fall back to Himalaya keywords
    himalaya_keywords = os.getenv("HIMALAYAS_KEYWORDS", "")
    if himalaya_keywords:
        return [kw.strip() for kw in himalaya_keywords.split(",") if kw.strip()]

    # Default fallback - senior/leadership engineering roles
    return [
        "engineering manager",
        "staff engineer",
        "technical lead",
        "tech lead",
        "team lead",
        "director of engineering",
        "head of engineering",
        "head of technology",
        "cto",
    ]


@router.post("/ingest/himalaya", response_model=IngestStartResponse, dependencies=[Depends(verify_token)])
async def ingest_himalaya_jobs(
    background_tasks: BackgroundTasks,
    keywords: Optional[List[str]] = Query(
        default=None,
        description="Keywords to filter jobs (defaults to INDEED_SEARCH_TERMS env var)"
    ),
    max_results: int = Query(
        default=100,
        le=100,
        description="Maximum jobs to fetch (max 100)"
    ),
    worldwide_only: bool = Query(
        default=True,
        description="Only fetch worldwide remote jobs"
    ),
    skip_scoring: bool = Query(
        default=False,
        description="Skip LLM scoring (faster, for testing)"
    ),
    incremental: bool = Query(
        default=True,
        description="Only fetch jobs newer than last run"
    ),
    score_threshold: int = Query(
        default=70,
        ge=0,
        le=100,
        description="Minimum score for ingestion (0-100)"
    ),
) -> IngestStartResponse:
    """
    Start Himalaya job ingestion (async with real-time logging).

    This endpoint returns immediately with a run_id. Use:
    - GET /jobs/ingest/{run_id}/logs for real-time SSE logs
    - GET /jobs/ingest/{run_id}/result for final result

    The ingestion process:
    1. Fetches remote jobs from Himalaya API
    2. Filters by keywords and worldwide availability
    3. Scores each job using Claude CLI (free with Max subscription)
    4. Inserts qualifying jobs into MongoDB level-2 collection
    5. Updates state for incremental fetching

    Returns:
        run_id for tracking the operation
    """
    # Use default keywords if not provided
    search_keywords = keywords or get_default_keywords()

    # Create operation run for log streaming
    run_id = create_operation_run(job_id="ingest", operation="ingest-himalaya")
    log_cb = create_log_callback(run_id)

    # Start background task
    background_tasks.add_task(
        _run_himalaya_ingestion,
        run_id=run_id,
        log_callback=log_cb,
        keywords=search_keywords,
        max_results=max_results,
        worldwide_only=worldwide_only,
        skip_scoring=skip_scoring,
        incremental=incremental,
        score_threshold=score_threshold,
    )

    return IngestStartResponse(run_id=run_id, status="queued", source="himalayas_auto")


async def _run_himalaya_ingestion(
    run_id: str,
    log_callback: Callable[[str], None],
    keywords: List[str],
    max_results: int,
    worldwide_only: bool,
    skip_scoring: bool,
    incremental: bool,
    score_threshold: int,
) -> None:
    """Background task for Himalaya ingestion with verbose logging."""
    try:
        update_operation_status(run_id, "running")

        # Emit structured start event
        _emit_structured_log(
            log_callback,
            event="ingest_start",
            message=f"Starting Himalayas ingestion",
            metadata={
                "source": "himalayas",
                "keywords": keywords,
                "max_results": max_results,
                "incremental": incremental,
                "worldwide_only": worldwide_only,
            },
        )

        # Import and initialize services
        from src.services.job_sources import HimalayasSource
        from src.services.job_ingest_service import IngestService

        # Fetch jobs from Himalaya
        _emit_structured_log(
            log_callback,
            event="fetch_start",
            message=f"Fetching from Himalayas API (max={max_results}, worldwide={worldwide_only})",
            metadata={"source": "himalayas", "max_results": max_results},
        )
        source = HimalayasSource(log_callback=log_callback)
        jobs = source.fetch_jobs({
            "keywords": keywords,
            "max_results": max_results,
            "worldwide_only": worldwide_only,
        })
        _emit_structured_log(
            log_callback,
            event="fetch_complete",
            message=f"Received {len(jobs)} jobs from Himalayas API",
            metadata={"source": "himalayas", "jobs_count": len(jobs)},
        )

        if not jobs:
            result = IngestResponse(
                success=True,
                source="himalayas_auto",
                incremental=incremental,
                stats={
                    "fetched": 0,
                    "ingested": 0,
                    "duplicates_skipped": 0,
                    "below_threshold": 0,
                    "errors": 0,
                    "duration_ms": 0,
                },
                jobs=[],
            )
            _store_ingest_result(run_id, result)
            update_operation_status(run_id, "completed", result=result.model_dump())
            _emit_structured_log(
                log_callback,
                event="ingest_complete",
                message="No jobs to ingest",
                status="success",
                metadata={"jobs_ingested": 0},
            )
            return

        # Initialize ingest service with Claude scorer and structured logging
        # Create progress callback for LLM cost tracking
        progress_cb = create_progress_callback(log_callback)
        ingest_service = IngestService(
            use_claude_scorer=True,
            log_callback=log_callback,
            progress_callback=progress_cb,
        )

        # Run ingestion
        _emit_structured_log(
            log_callback,
            event="scoring_start",
            message=f"Scoring and ingesting {len(jobs)} jobs (threshold={score_threshold})",
            metadata={"jobs_count": len(jobs), "score_threshold": score_threshold},
        )
        ingest_result = await ingest_service.ingest_jobs(
            jobs=jobs,
            source_name="himalayas_auto",
            score_threshold=score_threshold,
            skip_scoring=skip_scoring,
            incremental=incremental,
        )

        # Build response
        result = IngestResponse(**ingest_result.to_dict())
        _store_ingest_result(run_id, result)

        # Mark complete with structured log
        update_operation_status(run_id, "completed", result=result.model_dump())
        stats = result.stats
        _emit_structured_log(
            log_callback,
            event="ingest_complete",
            message=f"Ingestion complete: {stats.get('ingested', 0)} jobs ingested",
            status="success",
            duration_ms=stats.get("duration_ms", 0),
            metadata={
                "ingested": stats.get("ingested", 0),
                "duplicates_skipped": stats.get("duplicates_skipped", 0),
                "below_threshold": stats.get("below_threshold", 0),
                "errors": stats.get("errors", 0),
            },
        )

    except Exception as e:
        logger.exception(f"Himalaya ingestion failed: {e}")
        update_operation_status(run_id, "failed", error=str(e))
        _emit_structured_log(
            log_callback,
            event="ingest_error",
            message=str(e),
            error=str(e),
            status="error",
        )


@router.post("/ingest/indeed", response_model=IngestStartResponse, dependencies=[Depends(verify_token)])
async def ingest_indeed_jobs(
    background_tasks: BackgroundTasks,
    search_term: str = Query(
        ...,
        description="Job title/keywords to search (e.g., 'engineering manager')"
    ),
    location: Optional[str] = Query(
        default=None,
        description="Location to search (e.g., 'Remote', 'New York, NY')"
    ),
    country: str = Query(
        default="USA",
        description="Country code (USA, UK, Canada, Australia, Germany)"
    ),
    max_results: int = Query(
        default=50,
        le=100,
        description="Maximum jobs to fetch (max 100)"
    ),
    hours_old: Optional[int] = Query(
        default=None,
        description="Only jobs posted within N hours (optional)"
    ),
    skip_scoring: bool = Query(
        default=False,
        description="Skip LLM scoring (faster, for testing)"
    ),
    incremental: bool = Query(
        default=True,
        description="Only fetch jobs newer than last run"
    ),
    score_threshold: int = Query(
        default=70,
        ge=0,
        le=100,
        description="Minimum score for ingestion (0-100)"
    ),
) -> IngestStartResponse:
    """
    Start Indeed job ingestion (async with real-time logging).

    This endpoint returns immediately with a run_id. Use:
    - GET /jobs/ingest/{run_id}/logs for real-time SSE logs
    - GET /jobs/ingest/{run_id}/result for final result

    The ingestion process:
    1. Fetches jobs from Indeed using JobSpy scraper
    2. Filters by search term and optional location
    3. Scores each job using Claude CLI (free with Max subscription)
    4. Inserts qualifying jobs into MongoDB level-2 collection
    5. Updates state for incremental fetching

    Note: Uses web scraping - keep volume low (~50 jobs/run).

    Returns:
        run_id for tracking the operation
    """
    # Create operation run for log streaming
    run_id = create_operation_run(job_id="ingest", operation="ingest-indeed")
    log_cb = create_log_callback(run_id)

    # Build search config
    search_config = {
        "search_term": search_term,
        "location": location or "",
        "results_wanted": max_results,
        "country": country,
    }
    if hours_old:
        search_config["hours_old"] = hours_old

    # Start background task
    background_tasks.add_task(
        _run_indeed_ingestion,
        run_id=run_id,
        log_callback=log_cb,
        search_config=search_config,
        skip_scoring=skip_scoring,
        incremental=incremental,
        score_threshold=score_threshold,
    )

    return IngestStartResponse(run_id=run_id, status="queued", source="indeed_auto")


async def _run_indeed_ingestion(
    run_id: str,
    log_callback: Callable[[str], None],
    search_config: dict,
    skip_scoring: bool,
    incremental: bool,
    score_threshold: int,
) -> None:
    """Background task for Indeed ingestion with verbose logging."""
    try:
        update_operation_status(run_id, "running")

        # Emit structured start event
        _emit_structured_log(
            log_callback,
            event="ingest_start",
            message=f"Starting Indeed ingestion for '{search_config.get('search_term')}'",
            metadata={
                "source": "indeed",
                "search_term": search_config.get("search_term"),
                "location": search_config.get("location"),
                "country": search_config.get("country"),
                "max_results": search_config.get("results_wanted"),
                "incremental": incremental,
            },
        )

        # Import and initialize services
        from src.services.job_sources import IndeedSource
        from src.services.job_ingest_service import IngestService

        # Fetch jobs from Indeed
        _emit_structured_log(
            log_callback,
            event="fetch_start",
            message=f"Fetching from Indeed (max={search_config.get('results_wanted')})",
            metadata={"source": "indeed", "max_results": search_config.get("results_wanted")},
        )
        source = IndeedSource(log_callback=log_callback)
        jobs = source.fetch_jobs(search_config)
        _emit_structured_log(
            log_callback,
            event="fetch_complete",
            message=f"Received {len(jobs)} jobs from Indeed",
            metadata={"source": "indeed", "jobs_count": len(jobs)},
        )

        if not jobs:
            result = IngestResponse(
                success=True,
                source="indeed_auto",
                incremental=incremental,
                stats={
                    "fetched": 0,
                    "ingested": 0,
                    "duplicates_skipped": 0,
                    "below_threshold": 0,
                    "errors": 0,
                    "duration_ms": 0,
                },
                jobs=[],
            )
            _store_ingest_result(run_id, result)
            update_operation_status(run_id, "completed", result=result.model_dump())
            _emit_structured_log(
                log_callback,
                event="ingest_complete",
                message="No jobs to ingest",
                status="success",
                metadata={"jobs_ingested": 0},
            )
            return

        # Initialize ingest service with Claude scorer and structured logging
        progress_cb = create_progress_callback(log_callback)
        ingest_service = IngestService(
            use_claude_scorer=True,
            log_callback=log_callback,
            progress_callback=progress_cb,
        )

        # Run ingestion
        _emit_structured_log(
            log_callback,
            event="scoring_start",
            message=f"Scoring and ingesting {len(jobs)} jobs (threshold={score_threshold})",
            metadata={"jobs_count": len(jobs), "score_threshold": score_threshold},
        )
        ingest_result = await ingest_service.ingest_jobs(
            jobs=jobs,
            source_name="indeed_auto",
            score_threshold=score_threshold,
            skip_scoring=skip_scoring,
            incremental=incremental,
        )

        # Build response
        result = IngestResponse(**ingest_result.to_dict())
        _store_ingest_result(run_id, result)

        # Mark complete with structured log
        update_operation_status(run_id, "completed", result=result.model_dump())
        stats = result.stats
        _emit_structured_log(
            log_callback,
            event="ingest_complete",
            message=f"Ingestion complete: {stats.get('ingested', 0)} jobs ingested",
            status="success",
            duration_ms=stats.get("duration_ms", 0),
            metadata={
                "ingested": stats.get("ingested", 0),
                "duplicates_skipped": stats.get("duplicates_skipped", 0),
                "below_threshold": stats.get("below_threshold", 0),
                "errors": stats.get("errors", 0),
            },
        )

    except Exception as e:
        logger.exception(f"Indeed ingestion failed: {e}")
        update_operation_status(run_id, "failed", error=str(e))
        _emit_structured_log(
            log_callback,
            event="ingest_error",
            message=str(e),
            error=str(e),
            status="error",
        )


@router.post("/ingest/bayt", response_model=IngestStartResponse, dependencies=[Depends(verify_token)])
async def ingest_bayt_jobs(
    background_tasks: BackgroundTasks,
    search_term: str = Query(
        ...,
        description="Job title/keywords to search (e.g., 'software engineer')"
    ),
    max_results: int = Query(
        default=25,
        le=50,
        description="Maximum jobs to fetch (max 50 for Bayt)"
    ),
    skip_scoring: bool = Query(
        default=False,
        description="Skip LLM scoring (faster, for testing)"
    ),
    incremental: bool = Query(
        default=True,
        description="Only fetch jobs newer than last run"
    ),
    score_threshold: int = Query(
        default=70,
        ge=0,
        le=100,
        description="Minimum score for ingestion (0-100)"
    ),
) -> IngestStartResponse:
    """
    Start Bayt.com job ingestion (async with real-time logging).

    Bayt is the largest job board in the Gulf region (UAE, Saudi Arabia, Qatar, Kuwait).

    This endpoint returns immediately with a run_id. Use:
    - GET /jobs/ingest/{run_id}/logs for real-time SSE logs
    - GET /jobs/ingest/{run_id}/result for final result

    The ingestion process:
    1. Fetches jobs from Bayt using JobSpy scraper
    2. Scores each job using Claude CLI (free with Max subscription)
    3. Inserts qualifying jobs into MongoDB level-2 collection
    4. Updates state for incremental fetching

    Note: Bayt does not support location filtering - it searches all Gulf region jobs.
    Uses web scraping - keep volume low (~25 jobs/run).

    Returns:
        run_id for tracking the operation
    """
    # Create operation run for log streaming
    run_id = create_operation_run(job_id="ingest", operation="ingest-bayt")
    log_cb = create_log_callback(run_id)

    # Build search config (Bayt only supports search_term)
    search_config = {
        "search_term": search_term,
        "results_wanted": max_results,
    }

    # Start background task
    background_tasks.add_task(
        _run_bayt_ingestion,
        run_id=run_id,
        log_callback=log_cb,
        search_config=search_config,
        skip_scoring=skip_scoring,
        incremental=incremental,
        score_threshold=score_threshold,
    )

    return IngestStartResponse(run_id=run_id, status="queued", source="bayt")


async def _run_bayt_ingestion(
    run_id: str,
    log_callback: Callable[[str], None],
    search_config: dict,
    skip_scoring: bool,
    incremental: bool,
    score_threshold: int,
) -> None:
    """Background task for Bayt ingestion with verbose logging."""
    try:
        update_operation_status(run_id, "running")

        # Emit structured start event
        _emit_structured_log(
            log_callback,
            event="ingest_start",
            message=f"Starting Bayt ingestion for '{search_config.get('search_term')}'",
            metadata={
                "source": "bayt",
                "search_term": search_config.get("search_term"),
                "max_results": search_config.get("results_wanted"),
                "incremental": incremental,
            },
        )

        # Import and initialize services
        from src.services.job_sources import BaytSource
        from src.services.job_ingest_service import IngestService

        # Fetch jobs from Bayt
        _emit_structured_log(
            log_callback,
            event="fetch_start",
            message=f"Fetching from Bayt (max={search_config.get('results_wanted')})",
            metadata={"source": "bayt", "max_results": search_config.get("results_wanted")},
        )
        source = BaytSource(log_callback=log_callback)
        jobs = source.fetch_jobs(search_config)
        _emit_structured_log(
            log_callback,
            event="fetch_complete",
            message=f"Received {len(jobs)} jobs from Bayt",
            metadata={"source": "bayt", "jobs_count": len(jobs)},
        )

        if not jobs:
            result = IngestResponse(
                success=True,
                source="bayt",
                incremental=incremental,
                stats={
                    "fetched": 0,
                    "ingested": 0,
                    "duplicates_skipped": 0,
                    "below_threshold": 0,
                    "errors": 0,
                    "duration_ms": 0,
                },
                jobs=[],
            )
            _store_ingest_result(run_id, result)
            update_operation_status(run_id, "completed", result=result.model_dump())
            _emit_structured_log(
                log_callback,
                event="ingest_complete",
                message="No jobs to ingest",
                status="success",
                metadata={"jobs_ingested": 0},
            )
            return

        # Initialize ingest service with Claude scorer and structured logging
        progress_cb = create_progress_callback(log_callback)
        ingest_service = IngestService(
            use_claude_scorer=True,
            log_callback=log_callback,
            progress_callback=progress_cb,
        )

        # Run ingestion
        _emit_structured_log(
            log_callback,
            event="scoring_start",
            message=f"Scoring and ingesting {len(jobs)} jobs (threshold={score_threshold})",
            metadata={"jobs_count": len(jobs), "score_threshold": score_threshold},
        )
        ingest_result = await ingest_service.ingest_jobs(
            jobs=jobs,
            source_name="bayt",
            score_threshold=score_threshold,
            skip_scoring=skip_scoring,
            incremental=incremental,
        )

        # Build response
        result = IngestResponse(**ingest_result.to_dict())
        _store_ingest_result(run_id, result)

        # Mark complete with structured log
        update_operation_status(run_id, "completed", result=result.model_dump())
        stats = result.stats
        _emit_structured_log(
            log_callback,
            event="ingest_complete",
            message=f"Ingestion complete: {stats.get('ingested', 0)} jobs ingested",
            status="success",
            duration_ms=stats.get("duration_ms", 0),
            metadata={
                "ingested": stats.get("ingested", 0),
                "duplicates_skipped": stats.get("duplicates_skipped", 0),
                "below_threshold": stats.get("below_threshold", 0),
                "errors": stats.get("errors", 0),
            },
        )

    except Exception as e:
        logger.exception(f"Bayt ingestion failed: {e}")
        update_operation_status(run_id, "failed", error=str(e))
        _emit_structured_log(
            log_callback,
            event="ingest_error",
            message=str(e),
            error=str(e),
            status="error",
        )


@router.get("/ingest/state/{source}", dependencies=[Depends(verify_token)])
async def get_ingest_state(source: str) -> dict:
    """
    Get the current ingestion state for a source.

    Returns last fetch timestamp and stats from previous run.
    """
    try:
        state_repo = get_system_state_repository()
        state = state_repo.get_state(f"ingest_{source}")

        if not state:
            return {
                "source": source,
                "last_fetch_at": None,
                "last_run_stats": None,
                "message": "No ingestion history found",
            }

        return {
            "source": source,
            "last_fetch_at": state.get("last_fetch_at").isoformat() if state.get("last_fetch_at") else None,
            "updated_at": state.get("updated_at").isoformat() if state.get("updated_at") else None,
            "last_run_stats": state.get("last_run_stats"),
        }

    except Exception as e:
        logger.error(f"Error getting ingest state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/ingest/state/{source}", dependencies=[Depends(verify_token)])
async def reset_ingest_state(source: str) -> dict:
    """
    Reset the ingestion state for a source.

    Use this to force a full (non-incremental) fetch on next run.
    """
    try:
        state_repo = get_system_state_repository()
        deleted = state_repo.delete_state(f"ingest_{source}")

        if deleted:
            return {"success": True, "message": f"Reset ingestion state for {source}"}
        else:
            return {"success": True, "message": f"No state found for {source}"}

    except Exception as e:
        logger.error(f"Error resetting ingest state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ingest/history/{source}", dependencies=[Depends(verify_token)])
async def get_ingest_history(
    source: str,
    limit: int = Query(default=20, le=50, description="Number of runs to return")
) -> dict:
    """
    Get the ingestion run history for a source.

    Returns the last N runs with timestamps and stats.
    """
    try:
        state_repo = get_system_state_repository()
        state = state_repo.get_state(f"ingest_{source}")

        if not state:
            return {
                "source": source,
                "runs": [],
                "message": "No ingestion history found",
            }

        # Get run history, sorted by timestamp descending
        run_history = state.get("run_history", [])

        # Sort by timestamp descending and limit
        sorted_runs = sorted(
            run_history,
            key=lambda x: x.get("timestamp", datetime.min),
            reverse=True
        )[:limit]

        # Format timestamps for JSON
        formatted_runs = []
        for run in sorted_runs:
            formatted_run = {
                "timestamp": run.get("timestamp").isoformat() if run.get("timestamp") else None,
                "stats": run.get("stats", {}),
            }
            formatted_runs.append(formatted_run)

        return {
            "source": source,
            "runs": formatted_runs,
            "total_runs": len(run_history),
        }

    except Exception as e:
        logger.error(f"Error getting ingest history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Log Streaming and Result Endpoints for Async Ingestion
# =============================================================================


@router.get("/ingest/{run_id}/logs", dependencies=[Depends(verify_token)])
async def stream_ingest_logs(run_id: str):
    """
    Stream real-time logs for an ingestion operation via SSE.

    Returns Server-Sent Events with log messages as they are generated.
    Poll this endpoint after starting an ingestion operation.
    """
    from .operation_streaming import stream_operation_logs

    return await stream_operation_logs(run_id)


@router.get("/ingest/{run_id}/result", response_model=IngestResultResponse, dependencies=[Depends(verify_token)])
async def get_ingest_result(run_id: str) -> IngestResultResponse:
    """
    Get the result of an ingestion operation.

    Returns:
        - status: "queued", "running", "completed", or "failed"
        - result: The IngestResponse if completed
        - error: Error message if failed
    """
    state = get_operation_state(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")

    result = _get_stored_ingest_result(run_id)

    return IngestResultResponse(
        run_id=run_id,
        status=state.status,
        result=result,
        error=state.error,
    )
