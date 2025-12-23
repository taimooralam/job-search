"""
Job Ingestion Routes

On-demand job ingestion endpoint for fetching jobs from external sources
(Himalaya, etc.) and inserting them into MongoDB level-2 collection.

This endpoint runs on the VPS runner service, using Claude CLI for
scoring (free with Max subscription).
"""

import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from pymongo import MongoClient

from ..auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["ingestion"])


class IngestResponse(BaseModel):
    """Response model for ingestion endpoint."""

    success: bool
    source: str
    incremental: bool
    stats: dict
    last_fetch_at: Optional[str] = None
    jobs: List[dict] = Field(default_factory=list)
    error: Optional[str] = None


def get_db():
    """Get MongoDB database connection."""
    mongo_uri = os.getenv("MONGODB_URI")
    if not mongo_uri:
        raise HTTPException(status_code=500, detail="MONGODB_URI not configured")

    client = MongoClient(mongo_uri)
    return client[os.getenv("MONGO_DB_NAME", "jobs")]


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

    # Default fallback
    return ["engineering manager", "staff engineer", "technical lead", "director of engineering"]


@router.post("/ingest/himalaya", response_model=IngestResponse, dependencies=[Depends(verify_token)])
async def ingest_himalaya_jobs(
    keywords: Optional[List[str]] = Query(
        default=None,
        description="Keywords to filter jobs (defaults to INDEED_SEARCH_TERMS env var)"
    ),
    max_results: int = Query(
        default=50,
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
) -> IngestResponse:
    """
    Fetch and ingest jobs from Himalaya on-demand.

    This endpoint:
    1. Fetches remote jobs from Himalaya API
    2. Filters by keywords and worldwide availability
    3. Scores each job using Claude CLI (free with Max subscription)
    4. Inserts qualifying jobs into MongoDB level-2 collection
    5. Updates state for incremental fetching

    Jobs are inserted with the same schema as LinkedIn/Indeed imports,
    ready for Layer 1.4 (JD Extraction) and beyond.

    Returns:
        Ingestion statistics and list of ingested jobs
    """
    try:
        # Use default keywords if not provided
        search_keywords = keywords or get_default_keywords()

        logger.info(
            f"Starting Himalaya ingestion: keywords={search_keywords}, "
            f"max_results={max_results}, worldwide_only={worldwide_only}, "
            f"incremental={incremental}"
        )

        # Get MongoDB connection
        db = get_db()

        # Import and initialize services
        from src.services.job_sources import HimalayasSource
        from src.services.job_ingest_service import IngestService

        # Fetch jobs from Himalaya
        source = HimalayasSource()
        jobs = source.fetch_jobs({
            "keywords": search_keywords,
            "max_results": max_results,
            "worldwide_only": worldwide_only,
        })

        logger.info(f"Fetched {len(jobs)} jobs from Himalaya API")

        if not jobs:
            return IngestResponse(
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

        # Initialize ingest service with Claude scorer
        ingest_service = IngestService(db, use_claude_scorer=True)

        # Run ingestion
        result = await ingest_service.ingest_jobs(
            jobs=jobs,
            source_name="himalayas_auto",
            score_threshold=score_threshold,
            skip_scoring=skip_scoring,
            incremental=incremental,
        )

        return IngestResponse(**result.to_dict())

    except Exception as e:
        logger.exception(f"Himalaya ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.get("/ingest/state/{source}", dependencies=[Depends(verify_token)])
async def get_ingest_state(source: str) -> dict:
    """
    Get the current ingestion state for a source.

    Returns last fetch timestamp and stats from previous run.
    """
    try:
        db = get_db()
        state = db["system_state"].find_one({"_id": f"ingest_{source}"})

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
        db = get_db()
        result = db["system_state"].delete_one({"_id": f"ingest_{source}"})

        if result.deleted_count > 0:
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
        db = get_db()
        state = db["system_state"].find_one({"_id": f"ingest_{source}"})

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
