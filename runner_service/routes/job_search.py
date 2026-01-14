"""
Job Search Routes

Pull-on-demand job search API for searching Indeed, Bayt, and Himalayas
with caching and a searchable job index.

Endpoints:
    POST /job-search/search     - Execute search (async with livetail)
    GET  /job-search/index      - Query job index with filters
    GET  /job-search/presets    - Get search presets
    GET  /job-search/{job_id}   - Get single job details
    POST /job-search/promote/{job_id}  - Promote to level-2
    POST /job-search/hide/{job_id}     - Hide from results
    POST /job-search/unhide/{job_id}   - Unhide a job
    DELETE /job-search/cache    - Clear cache (admin)
    GET  /job-search/stats      - Get index and cache stats
"""

import json
import logging
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/job-search", tags=["job-search"])

# In-memory storage for search results (keyed by run_id)
_search_results: Dict[str, "SearchResponse"] = {}


def _emit_structured_log(
    log_callback: Callable[[str], None],
    event: str,
    message: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    Emit a structured JSON log entry to the operation log buffer.

    Args:
        log_callback: The log callback from create_log_callback
        event: Event type (e.g., "search_start", "source_complete")
        message: Optional human-readable message
        **kwargs: Additional fields (metadata, etc.)
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
    }
    if message:
        log_entry["message"] = message

    for key, value in kwargs.items():
        if value is not None:
            log_entry[key] = value

    log_callback(json.dumps(log_entry))


# =============================================================================
# Pydantic Models
# =============================================================================

class SearchRequest(BaseModel):
    """Request model for job search."""
    job_titles: List[str] = Field(
        ...,
        description="List of job title preset IDs or raw search terms",
        min_length=1,
        max_length=10,
    )
    regions: List[str] = Field(
        default=["gulf", "worldwide_remote"],
        description="List of region IDs: 'gulf', 'worldwide_remote'",
    )
    sources: List[str] = Field(
        default=["indeed", "bayt", "himalayas"],
        description="List of source IDs: 'indeed', 'bayt', 'himalayas'",
    )
    remote_only: bool = Field(
        default=False,
        description="Only return remote jobs",
    )
    use_cache: bool = Field(
        default=True,
        description="Use cached results if available",
    )
    max_results_per_source: Optional[int] = Field(
        default=None,
        le=50,
        description="Override max results per source (default: 25, max: 50)",
    )


class SearchStartResponse(BaseModel):
    """Response when starting async job search."""
    run_id: str
    status: str
    cache_hit: Optional[bool] = None
    cache_key: Optional[str] = None


class SearchResponse(BaseModel):
    """Response model for job search."""
    success: bool
    cache_hit: bool
    cache_key: str
    search_duration_ms: int
    total_results: int
    results_by_source: dict
    jobs: List[dict]
    error: Optional[str] = None


class SearchResultResponse(BaseModel):
    """Response when polling for search result."""
    run_id: str
    status: str  # "queued", "running", "completed", "failed"
    result: Optional[SearchResponse] = None
    error: Optional[str] = None


class IndexQueryResponse(BaseModel):
    """Response model for index queries."""
    success: bool = True
    jobs: List[dict]
    total: int
    facets: dict
    pagination: dict


class JobDetailResponse(BaseModel):
    """Response model for single job details."""
    success: bool
    job: Optional[dict] = None
    error: Optional[str] = None


class PromoteResponse(BaseModel):
    """Response model for job promotion."""
    success: bool
    index_job_id: Optional[str] = None
    level2_job_id: Optional[str] = None
    tier: Optional[str] = None
    error: Optional[str] = None


class ActionResponse(BaseModel):
    """Generic response for job actions."""
    success: bool
    job_id: Optional[str] = None
    hidden: Optional[bool] = None
    error: Optional[str] = None


class StatsResponse(BaseModel):
    """Response model for stats endpoint."""
    success: bool = True
    cache: dict
    index: dict


class PresetsResponse(BaseModel):
    """Response model for presets endpoint."""
    job_titles: List[dict]
    regions: List[dict]
    sources: List[dict]


# =============================================================================
# Dependencies
# =============================================================================

def get_search_service():
    """Get JobSearchService instance (uses repository pattern internally)."""
    # Import here to avoid circular imports
    from src.services.job_search_service import JobSearchService

    return JobSearchService()


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/search", response_model=SearchStartResponse, dependencies=[Depends(verify_token)])
async def search_jobs(request: SearchRequest, background_tasks: BackgroundTasks):
    """
    Execute job search across specified sources (async with real-time logging).

    This endpoint returns immediately with a run_id. Use:
    - GET /api/logs/operations/{run_id} for real-time logs via polling
    - GET /job-search/result/{run_id} for final result

    Searches Indeed, Bayt, and/or Himalayas based on the request.
    Results are cached for 6 hours by default.

    **Example request:**
    ```json
    {
        "job_titles": ["senior_swe", "staff_swe"],
        "regions": ["gulf", "worldwide_remote"],
        "sources": ["indeed", "bayt", "himalayas"],
        "remote_only": false,
        "use_cache": true
    }
    ```
    """
    # Create operation run for log streaming
    run_id = create_operation_run(job_id="search", operation="job-search")
    log_cb = create_log_callback(run_id)

    # Start background task
    background_tasks.add_task(
        _run_job_search,
        run_id=run_id,
        log_callback=log_cb,
        job_titles=request.job_titles,
        regions=request.regions,
        sources=request.sources,
        remote_only=request.remote_only,
        use_cache=request.use_cache,
        max_results_per_source=request.max_results_per_source,
    )

    return SearchStartResponse(
        run_id=run_id,
        status="queued",
    )


async def _run_job_search(
    run_id: str,
    log_callback: Callable[[str], None],
    job_titles: List[str],
    regions: List[str],
    sources: List[str],
    remote_only: bool,
    use_cache: bool,
    max_results_per_source: Optional[int],
) -> None:
    """Background task for job search with verbose logging."""
    try:
        update_operation_status(run_id, "running")

        # Emit structured start event
        _emit_structured_log(
            log_callback,
            event="search_start",
            message=f"Starting job search: {', '.join(job_titles)}",
            metadata={
                "job_titles": job_titles,
                "regions": regions,
                "sources": sources,
                "remote_only": remote_only,
                "use_cache": use_cache,
            },
        )

        service = get_search_service()

        # Emit per-source progress
        _emit_structured_log(
            log_callback,
            event="search_sources",
            message=f"Searching {len(sources)} sources: {', '.join(sources)}",
            metadata={"sources": sources},
        )

        result = await service.search(
            job_titles=job_titles,
            regions=regions,
            sources=sources,
            remote_only=remote_only,
            use_cache=use_cache,
            max_results_per_source=max_results_per_source,
        )

        # Build response
        response = SearchResponse(
            success=result.success,
            cache_hit=result.cache_hit,
            cache_key=result.cache_key,
            search_duration_ms=result.search_duration_ms,
            total_results=result.total_results,
            results_by_source=result.results_by_source,
            jobs=result.jobs,
            error=result.error,
        )

        # Store result
        _search_results[run_id] = response

        # Emit per-source results
        for source, count in result.results_by_source.items():
            _emit_structured_log(
                log_callback,
                event="source_complete",
                message=f"{source}: {count} jobs found",
                metadata={"source": source, "jobs_count": count},
            )

        # Mark complete with structured log
        if response.success:
            update_operation_status(run_id, "completed", result=response.model_dump())
            _emit_structured_log(
                log_callback,
                event="search_complete",
                message=f"Search complete: {response.total_results} jobs found",
                status="success",
                duration_ms=response.search_duration_ms,
                metadata={
                    "total_results": response.total_results,
                    "cache_hit": response.cache_hit,
                    "results_by_source": response.results_by_source,
                },
            )
        else:
            update_operation_status(run_id, "failed", error=response.error)
            _emit_structured_log(
                log_callback,
                event="search_error",
                message=response.error or "Search failed",
                error=response.error,
                status="error",
            )

    except Exception as e:
        logger.exception(f"Job search failed: {e}")
        update_operation_status(run_id, "failed", error=str(e))
        _emit_structured_log(
            log_callback,
            event="search_error",
            message=str(e),
            error=str(e),
            status="error",
        )


@router.get("/result/{run_id}", response_model=SearchResultResponse, dependencies=[Depends(verify_token)])
async def get_search_result(run_id: str) -> SearchResultResponse:
    """
    Get the result of a job search operation.

    Args:
        run_id: Operation run ID from /search

    Returns:
        SearchResultResponse with status and result if completed
    """
    state = get_operation_state(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")

    result = _search_results.get(run_id)

    return SearchResultResponse(
        run_id=run_id,
        status=state.status,
        result=result,
        error=state.error,
    )


@router.get("/index", response_model=IndexQueryResponse, dependencies=[Depends(verify_token)])
async def query_index(
    q: Optional[str] = Query(None, description="Full-text search query"),
    sources: Optional[str] = Query(None, description="Comma-separated sources to filter"),
    regions: Optional[str] = Query(None, description="Comma-separated regions to filter"),
    remote_only: bool = Query(False, description="Only remote jobs"),
    promoted: Optional[bool] = Query(None, description="Filter by promotion status"),
    include_hidden: bool = Query(False, description="Include hidden jobs"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Minimum quick score"),
    sort_by: str = Query("discovered_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
):
    """
    Query the job search index with filters.

    Returns paginated results with facets for filtering.
    """
    service = get_search_service()

    # Parse comma-separated lists
    source_list = sources.split(",") if sources else None
    region_list = regions.split(",") if regions else None

    result = service.query_index(
        query=q,
        sources=source_list,
        regions=region_list,
        remote_only=remote_only,
        promoted=promoted,
        include_hidden=include_hidden,
        min_score=min_score,
        sort_by=sort_by,
        sort_order=sort_order,
        offset=offset,
        limit=limit,
    )

    return IndexQueryResponse(
        jobs=result["jobs"],
        total=result["total"],
        facets=result["facets"],
        pagination=result["pagination"],
    )


@router.get("/presets", response_model=PresetsResponse)
async def get_presets():
    """
    Get available search presets.

    Returns job titles, regions, and sources that can be used in search requests.
    This endpoint does not require authentication.
    """
    from src.common.job_search_config import JobSearchConfig

    config = JobSearchConfig.from_env()
    presets = config.get_presets()

    return PresetsResponse(**presets)


@router.get("/{job_id}", response_model=JobDetailResponse, dependencies=[Depends(verify_token)])
async def get_job(job_id: str):
    """
    Get full details for a single job from the index.
    """
    service = get_search_service()
    job = service.get_job(job_id)

    if not job:
        return JobDetailResponse(success=False, error="Job not found")

    return JobDetailResponse(success=True, job=job)


@router.post("/promote/{job_id}", response_model=PromoteResponse, dependencies=[Depends(verify_token)])
async def promote_job(
    job_id: str,
    tier: Optional[str] = Query(None, description="Optional tier override"),
):
    """
    Promote a job from the index to level-2 for pipeline processing.

    Once promoted, the job will appear in the main job list and can be
    processed through the pipeline.
    """
    service = get_search_service()
    result = service.promote_job(job_id, tier=tier)

    return PromoteResponse(**result)


@router.post("/hide/{job_id}", response_model=ActionResponse, dependencies=[Depends(verify_token)])
async def hide_job(job_id: str):
    """
    Hide a job from future search results.

    Hidden jobs will not appear in index queries unless include_hidden=true.
    """
    service = get_search_service()
    result = service.hide_job(job_id)

    return ActionResponse(**result)


@router.post("/unhide/{job_id}", response_model=ActionResponse, dependencies=[Depends(verify_token)])
async def unhide_job(job_id: str):
    """
    Unhide a previously hidden job.
    """
    service = get_search_service()
    result = service.unhide_job(job_id)

    return ActionResponse(**result)


@router.delete("/cache", response_model=ActionResponse, dependencies=[Depends(verify_token)])
async def clear_cache():
    """
    Clear all cache entries (admin endpoint).

    This forces fresh searches for all future requests.
    """
    service = get_search_service()
    result = service.clear_cache()

    return ActionResponse(
        success=result.get("success", False),
        error=result.get("error"),
    )


@router.get("/stats", response_model=StatsResponse, dependencies=[Depends(verify_token)])
async def get_stats():
    """
    Get cache and index statistics.
    """
    service = get_search_service()

    return StatsResponse(
        cache=service.get_cache_stats(),
        index=service.get_index_stats(),
    )
