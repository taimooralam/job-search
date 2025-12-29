"""
Job Search Routes

Pull-on-demand job search API for searching Indeed, Bayt, and Himalayas
with caching and a searchable job index.

Endpoints:
    POST /job-search/search     - Execute search (or return cache)
    GET  /job-search/index      - Query job index with filters
    GET  /job-search/presets    - Get search presets
    GET  /job-search/{job_id}   - Get single job details
    POST /job-search/promote/{job_id}  - Promote to level-2
    POST /job-search/hide/{job_id}     - Hide from results
    POST /job-search/unhide/{job_id}   - Unhide a job
    DELETE /job-search/cache    - Clear cache (admin)
    GET  /job-search/stats      - Get index and cache stats
"""

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from pymongo import MongoClient

from ..auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/job-search", tags=["job-search"])


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

def get_db():
    """Get MongoDB database connection."""
    mongo_uri = os.getenv("MONGODB_URI")
    if not mongo_uri:
        raise HTTPException(status_code=500, detail="MONGODB_URI not configured")

    client = MongoClient(mongo_uri)
    return client[os.getenv("MONGO_DB_NAME", "jobs")]


def get_search_service():
    """Get JobSearchService instance."""
    # Import here to avoid circular imports
    from src.services.job_search_service import JobSearchService

    db = get_db()
    return JobSearchService(db)


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/search", response_model=SearchResponse, dependencies=[Depends(verify_token)])
async def search_jobs(request: SearchRequest):
    """
    Execute job search across specified sources.

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
    service = get_search_service()

    result = await service.search(
        job_titles=request.job_titles,
        regions=request.regions,
        sources=request.sources,
        remote_only=request.remote_only,
        use_cache=request.use_cache,
        max_results_per_source=request.max_results_per_source,
    )

    return SearchResponse(
        success=result.success,
        cache_hit=result.cache_hit,
        cache_key=result.cache_key,
        search_duration_ms=result.search_duration_ms,
        total_results=result.total_results,
        results_by_source=result.results_by_source,
        jobs=result.jobs,
        error=result.error,
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
