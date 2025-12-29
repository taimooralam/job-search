"""
Independent Pipeline Operation Endpoints

Provides button-triggered endpoints for individual pipeline operations:
- Structure JD: Parse and structure job description
- Research Company: Gather company and role intelligence
- Generate CV: Create tailored CV

Each endpoint:
- Validates job_id exists in MongoDB
- Accepts tier selection (fast/balanced/quality)
- Returns consistent response with success, data, cost_usd, run_id
- Logs execution start/end

Phase 3: Route scaffolding with stubbed implementations
Phase 4: Actual service logic
"""

import asyncio
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from typing import Any, AsyncIterator, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from pymongo import MongoClient

# Thread pool for running sync MongoDB operations without blocking the event loop
# Increased from 4 to 8 workers to handle concurrent streaming operations
_db_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="mongo_")

# Thread pool for running service operations that may internally block
# (e.g., services using run_async() which blocks with future.result())
# Using a separate pool to avoid starving MongoDB operations
_service_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="service_")


def _run_async_in_thread(coro) -> None:
    """
    Run an async coroutine in a separate thread with its own event loop.

    This solves the blocking issue where services internally use run_async()
    which blocks the event loop via future.result(). By running in a separate
    thread, the blocking only affects that thread while the main event loop
    remains responsive for log polling endpoints.

    IMPORTANT: The coroutine should NOT directly await Redis/aioredis operations
    because those are bound to the main event loop. Use run_on_main_loop() for
    any operations that need the main loop (e.g., queue manager calls).

    Args:
        coro: The coroutine to run (e.g., execute_extraction())
    """
    asyncio.run(coro)


def run_on_main_loop(coro):
    """
    Schedule a coroutine to run on the main event loop from a worker thread.

    This is essential for aioredis operations which are bound to the main loop.
    Call this from within _run_async_in_thread() when you need to interact with
    Redis queue manager or other main-loop-bound async resources.

    Args:
        coro: The coroutine to schedule on the main event loop

    Returns:
        The result of the coroutine (blocks until complete)

    Raises:
        RuntimeError: If main loop reference is not available
    """
    from runner_service.app import get_main_loop

    main_loop = get_main_loop()
    if main_loop is None:
        raise RuntimeError("Main event loop not available - startup may not be complete")

    # Schedule coroutine on main loop and wait for result
    future = asyncio.run_coroutine_threadsafe(coro, main_loop)
    return future.result(timeout=30)  # 30 second timeout for queue ops


async def run_service_in_executor(coro) -> None:
    """
    Schedule a service coroutine to run in the executor thread pool.

    This is the async wrapper that can be used with BackgroundTasks.
    It offloads the blocking async operation to a separate thread,
    keeping the main event loop responsive.

    Args:
        coro: The coroutine to run (will be executed in a separate thread)
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_service_executor, _run_async_in_thread, coro)


def submit_service_task(coro) -> None:
    """
    Submit a service coroutine to the executor thread pool (fire-and-forget).

    Unlike run_service_in_executor, this does NOT await completion.
    Tasks run in parallel up to the executor's max_workers limit.

    Use this for batch operations where you want multiple jobs to execute
    concurrently without the sequential blocking of BackgroundTasks.

    Args:
        coro: The coroutine to run (e.g., _execute_extraction_bulk_task(...))
    """
    _service_executor.submit(_run_async_in_thread, coro)


from src.common.model_tiers import (
    ModelTier,
    get_model_for_operation,
    get_tier_from_string,
    TIER_CONFIGS,
    OPERATION_TASK_TYPES,
)
from src.services.operation_base import OperationResult

from ..auth import verify_token
from ..models import (
    BulkOperationRequest,
    BulkOperationResponse,
    BulkOperationRunInfo,
    QueueOperationRequest,
    QueueOperationResponse,
    OperationQueueStatus,
    JobQueueStatusResponse,
)
from .operation_streaming import (
    create_operation_run,
    get_operation_state,
    get_operation_state_from_redis,
    append_operation_log,
    update_operation_status,
    update_layer_status,
    create_log_callback,
    create_layer_callback,
    stream_operation_logs,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["operations"])


# =============================================================================
# Thread-Safe Queue Operation Wrappers
# =============================================================================
# These functions safely call async Redis queue operations from worker threads
# by scheduling them on the main event loop where the aioredis client lives.


def _queue_start_item_threadsafe(queue_manager, queue_id: str, log_cb) -> bool:
    """
    Thread-safe wrapper to start a queue item from a worker thread.

    Schedules the async operation on the main event loop where the
    Redis client was created. Required because aioredis clients are
    bound to the event loop they were created on.

    Args:
        queue_manager: The QueueManager instance
        queue_id: Queue item ID to start
        log_cb: Logging callback function

    Returns:
        True if started successfully, False otherwise
    """
    async def _start():
        return await _start_queue_item(queue_manager, queue_id, log_cb)

    try:
        return run_on_main_loop(_start())
    except Exception as e:
        logger.warning(f"Failed to start queue item {queue_id}: {e}")
        return False


def _queue_complete_threadsafe(queue_manager, queue_id: str, success: bool = True) -> None:
    """
    Thread-safe wrapper to complete a queue item from a worker thread.

    Args:
        queue_manager: The QueueManager instance
        queue_id: Queue item ID to complete
        success: Whether the operation succeeded
    """
    async def _complete():
        await queue_manager.complete(queue_id, success=success)

    try:
        run_on_main_loop(_complete())
    except Exception as e:
        logger.warning(f"Failed to complete queue item {queue_id}: {e}")


def _queue_fail_threadsafe(queue_manager, queue_id: str, error: str) -> None:
    """
    Thread-safe wrapper to fail a queue item from a worker thread.

    Args:
        queue_manager: The QueueManager instance
        queue_id: Queue item ID to fail
        error: Error message describing the failure
    """
    async def _fail():
        await queue_manager.fail(queue_id, error)

    try:
        run_on_main_loop(_fail())
    except Exception as e:
        logger.warning(f"Failed to fail queue item {queue_id}: {e}")


# =============================================================================
# Request/Response Models
# =============================================================================


class StructureJDRequest(BaseModel):
    """Request body for structuring a job description."""

    tier: str = Field(
        default="balanced",
        description="Model tier: 'fast', 'balanced', or 'quality'",
    )
    use_llm: bool = Field(
        default=True,
        description="Whether to use LLM for intelligent structuring",
    )


class ResearchCompanyRequest(BaseModel):
    """Request body for company research."""

    tier: str = Field(
        default="balanced",
        description="Model tier: 'fast', 'balanced', or 'quality'",
    )
    force_refresh: bool = Field(
        default=False,
        description="Force refresh even if cached data exists",
    )


class GenerateCVRequest(BaseModel):
    """Request body for CV generation."""

    tier: str = Field(
        default="quality",
        description="Model tier: 'fast', 'balanced', or 'quality'",
    )
    use_annotations: bool = Field(
        default=True,
        description="Whether to incorporate user annotations",
    )


class FullExtractionRequest(BaseModel):
    """Request body for full JD extraction (Layer 1.4 + 2 + 4)."""

    tier: str = Field(
        default="balanced",
        description="Model tier: 'fast', 'balanced', or 'quality'",
    )
    use_llm: bool = Field(
        default=True,
        description="Whether to use LLM for processing",
    )


class OperationResponse(BaseModel):
    """Standard response for operation endpoints."""

    success: bool = Field(..., description="Whether the operation succeeded")
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Operation result data",
    )
    cost_usd: float = Field(
        default=0.0,
        description="Estimated cost in USD",
    )
    run_id: str = Field(..., description="Unique run identifier for tracking")
    error: Optional[str] = Field(
        default=None,
        description="Error message if operation failed",
    )
    model_used: Optional[str] = Field(
        default=None,
        description="Model that was used for the operation",
    )
    duration_ms: Optional[int] = Field(
        default=None,
        description="Operation duration in milliseconds",
    )


class CostEstimate(BaseModel):
    """Cost estimate for a single operation."""

    operation: str = Field(..., description="Operation name")
    cost_usd: float = Field(..., description="Estimated cost in USD")
    model: str = Field(..., description="Model that would be used")
    tier: str = Field(..., description="Selected tier")


class CostEstimateResponse(BaseModel):
    """Response for cost estimation endpoint."""

    estimates: List[CostEstimate] = Field(
        default_factory=list,
        description="Cost estimates per operation",
    )
    total_cost_usd: float = Field(
        default=0.0,
        description="Total estimated cost for all operations",
    )


# =============================================================================
# Helper Functions
# =============================================================================

# Singleton MongoDB client for connection pooling
# This avoids the 5-10 second connection overhead on each request
_mongo_client: Optional[MongoClient] = None


def _get_mongo_client() -> MongoClient:
    """
    Get singleton MongoDB client with connection pooling.

    Creates client once and reuses it for all validation calls.
    This avoids the 5-10 second connection overhead on each request.

    Returns:
        MongoClient instance with connection pooling configured
    """
    global _mongo_client

    if _mongo_client is None:
        mongo_uri = (
            os.getenv("MONGODB_URI")
            or os.getenv("MONGO_URI")
            or "mongodb://localhost:27017"
        )
        _mongo_client = MongoClient(
            mongo_uri,
            connectTimeoutMS=5000,
            socketTimeoutMS=10000,
            serverSelectionTimeoutMS=10000,
            maxPoolSize=10,  # Connection pool for concurrent requests
            minPoolSize=1,   # Keep at least 1 connection warm
        )

    return _mongo_client


def _validate_job_exists_sync(job_id: str) -> dict:
    """
    Synchronous validation that a job exists in MongoDB.

    Uses singleton client for connection pooling.

    Args:
        job_id: MongoDB ObjectId as string

    Returns:
        Job document if found

    Raises:
        HTTPException: If job_id is invalid or job not found
    """
    # Validate ObjectId format
    try:
        object_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    # Check job exists using pooled client
    client = _get_mongo_client()
    db = client[os.getenv("MONGO_DB_NAME", "jobs")]
    job = db["level-2"].find_one({"_id": object_id})

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


async def _validate_job_exists_async(job_id: str) -> dict:
    """
    Async validation that a job exists in MongoDB.

    Runs the sync MongoDB query in a thread pool to avoid blocking
    the FastAPI event loop.

    Args:
        job_id: MongoDB ObjectId as string

    Returns:
        Job document if found

    Raises:
        HTTPException: If job_id is invalid or job not found
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_db_executor, _validate_job_exists_sync, job_id)


# Alias for backwards compatibility with sync endpoints
def _validate_job_exists(job_id: str) -> dict:
    """Sync version for backwards compatibility with non-streaming endpoints."""
    return _validate_job_exists_sync(job_id)


def _validate_tier(tier_str: str) -> ModelTier:
    """
    Validate and convert tier string to ModelTier enum.

    Args:
        tier_str: Tier string ('fast', 'balanced', 'quality', 'A', 'B', 'C', 'auto')

    Returns:
        ModelTier enum value

    Raises:
        HTTPException: If tier is invalid
    """
    tier = get_tier_from_string(tier_str)
    if tier is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{tier_str}'. Must be 'fast'/'balanced'/'quality' or 'A'/'B'/'C'/'auto'",
        )
    return tier


def _generate_run_id(operation: str) -> str:
    """
    Generate unique run ID for operation tracking.

    Args:
        operation: Operation name

    Returns:
        Unique run ID in format "op_{operation}_{random_hex}"
    """
    return f"op_{operation}_{uuid.uuid4().hex[:12]}"


def _estimate_operation_cost(tier: ModelTier, operation: str) -> float:
    """
    Estimate cost for an operation based on tier and typical token usage.

    Args:
        tier: Model tier
        operation: Operation name

    Returns:
        Estimated cost in USD
    """
    # Typical token estimates per operation
    TOKEN_ESTIMATES = {
        "structure-jd": {"input": 2000, "output": 1500},
        "research-company": {"input": 3000, "output": 2000},
        "generate-cv": {"input": 5000, "output": 3000},
    }

    estimates = TOKEN_ESTIMATES.get(operation, {"input": 2000, "output": 1500})
    config = TIER_CONFIGS[tier]

    input_cost = (estimates["input"] / 1000) * config.cost_per_1k_input
    output_cost = (estimates["output"] / 1000) * config.cost_per_1k_output

    return round(input_cost + output_cost, 4)


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/{job_id}/structure-jd",
    response_model=OperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Structure job description",
    description="Parse and structure a job description with intelligent extraction",
)
async def structure_jd(
    job_id: str,
    request: StructureJDRequest,
) -> OperationResponse:
    """
    Structure/parse a job description.

    Extracts key information from the raw JD text:
    - Required skills and qualifications
    - Responsibilities
    - Company culture signals
    - Pain points and challenges
    - Benefits and perks

    Args:
        job_id: MongoDB ObjectId of the job
        request: Structure JD request parameters

    Returns:
        OperationResponse with structured JD data
    """
    from src.services.structure_jd_service import StructureJDService

    operation = "structure-jd"

    logger.info(f"Starting {operation} for job {job_id}")

    try:
        # Validate inputs first (fast fail for bad inputs)
        _validate_job_exists(job_id)  # Raises HTTPException if not found
        tier = _validate_tier(request.tier)

        logger.info(
            f"Executing {operation}: tier={tier.value}, use_llm={request.use_llm}"
        )

        # Execute via service
        service = StructureJDService()
        result = await service.execute(
            job_id=job_id,
            tier=tier,
            use_llm=request.use_llm,
        )

        logger.info(
            f"[{result.run_id[:16]}] Completed {operation}: "
            f"success={result.success}, cost=${result.cost_usd:.4f}"
        )

        return OperationResponse(
            success=result.success,
            data=result.data,
            cost_usd=result.cost_usd,
            run_id=result.run_id,
            error=result.error,
            model_used=result.model_used,
            duration_ms=result.duration_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        run_id = _generate_run_id(operation)
        logger.exception(f"[{run_id[:16]}] {operation} failed: {e}")
        return OperationResponse(
            success=False,
            data={},
            cost_usd=0.0,
            run_id=run_id,
            error=str(e),
        )


@router.post(
    "/{job_id}/research-company",
    response_model=OperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Research company and role",
    description="Gather intelligence about the company, role, and hiring context",
)
async def research_company(
    job_id: str,
    request: ResearchCompanyRequest,
) -> OperationResponse:
    """
    Research company and role.

    Gathers intelligence including:
    - Company overview and recent news
    - Business signals (funding, acquisitions, leadership changes)
    - Role-specific requirements and business impact
    - "Why now" timing analysis based on company signals

    Args:
        job_id: MongoDB ObjectId of the job
        request: Research request parameters

    Returns:
        OperationResponse with research data
    """
    from src.services.company_research_service import CompanyResearchService

    operation = "research-company"

    logger.info(f"Starting {operation} for job {job_id}")

    try:
        # Validate inputs first (fast fail for bad inputs)
        _validate_job_exists(job_id)  # Raises HTTPException if not found
        tier = _validate_tier(request.tier)

        logger.info(
            f"Executing {operation}: tier={tier.value}, force_refresh={request.force_refresh}"
        )

        # Execute via service
        service = CompanyResearchService()
        try:
            result = await service.execute(
                job_id=job_id,
                tier=tier,
                force_refresh=request.force_refresh,
            )
        finally:
            service.close()

        logger.info(
            f"[{result.run_id[:16]}] Completed {operation}: "
            f"success={result.success}, cost=${result.cost_usd:.4f}"
        )

        return OperationResponse(
            success=result.success,
            data=result.data,
            cost_usd=result.cost_usd,
            run_id=result.run_id,
            error=result.error,
            model_used=result.model_used,
            duration_ms=result.duration_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        run_id = _generate_run_id(operation)
        logger.exception(f"[{run_id[:16]}] {operation} failed: {e}")
        return OperationResponse(
            success=False,
            data={},
            cost_usd=0.0,
            run_id=run_id,
            error=str(e),
        )


@router.post(
    "/{job_id}/generate-cv",
    response_model=OperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Generate tailored CV",
    description="Generate a CV tailored to the specific job requirements",
)
async def generate_cv(
    job_id: str,
    request: GenerateCVRequest,
) -> OperationResponse:
    """
    Generate a tailored CV.

    Creates a CV customized for the job:
    - Highlights relevant experience
    - Incorporates user annotations
    - Matches company tone and keywords
    - Optimizes for ATS parsing
    - Includes quantified achievements

    Args:
        job_id: MongoDB ObjectId of the job
        request: CV generation request parameters

    Returns:
        OperationResponse with generated CV data
    """
    operation = "generate-cv"

    logger.info(f"Starting {operation} for job {job_id}")

    try:
        # Validate inputs
        _validate_job_exists(job_id)
        tier = _validate_tier(request.tier)

        logger.info(
            f"Using tier={tier.value}, use_annotations={request.use_annotations}"
        )

        # Phase 4: Use CVGenerationService for actual implementation
        from src.services.cv_generation_service import CVGenerationService

        service = CVGenerationService()
        result = await service.execute(
            job_id=job_id,
            tier=tier,
            use_annotations=request.use_annotations,
        )

        # Persist the operation run for tracking
        service.persist_run(result, job_id, tier)

        logger.info(
            f"[{result.run_id[:16]}] Completed {operation}, "
            f"success={result.success}, duration={result.duration_ms}ms"
        )

        return OperationResponse(
            success=result.success,
            data=result.data,
            cost_usd=result.cost_usd,
            run_id=result.run_id,
            model_used=result.model_used,
            duration_ms=result.duration_ms,
            error=result.error,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"{operation} failed: {e}")
        run_id = _generate_run_id(operation)
        return OperationResponse(
            success=False,
            data={},
            cost_usd=0.0,
            run_id=run_id,
            error=str(e),
        )


@router.post(
    "/{job_id}/full-extraction",
    response_model=OperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Run full JD extraction",
    description="Run complete extraction pipeline: Layer 1.4 (JD structuring) + Layer 2 (pain points) + Layer 4 (fit scoring)",
)
async def full_extraction(
    job_id: str,
    request: FullExtractionRequest,
) -> OperationResponse:
    """
    Run full JD extraction (Layer 1.4 + Layer 2 + Layer 4).

    This is the expanded "Structure JD" button that runs all extraction layers
    and combines results into a single badge showing:
    - Section count (Layer 1.4)
    - Pain point count (Layer 2)
    - Fit score and category (Layer 4)

    Args:
        job_id: MongoDB ObjectId of the job
        request: Full extraction request parameters

    Returns:
        OperationResponse with combined extraction data
    """
    from src.services.full_extraction_service import FullExtractionService

    operation = "full-extraction"

    logger.info(f"Starting {operation} for job {job_id}")

    try:
        # Validate inputs
        _validate_job_exists(job_id)
        tier = _validate_tier(request.tier)

        logger.info(
            f"Executing {operation}: tier={tier.value}, use_llm={request.use_llm}"
        )

        # Execute via service
        service = FullExtractionService()
        result = await service.execute(
            job_id=job_id,
            tier=tier,
            use_llm=request.use_llm,
        )

        logger.info(
            f"[{result.run_id[:16]}] Completed {operation}: "
            f"success={result.success}, cost=${result.cost_usd:.4f}"
        )

        return OperationResponse(
            success=result.success,
            data=result.data,
            cost_usd=result.cost_usd,
            run_id=result.run_id,
            error=result.error,
            model_used=result.model_used,
            duration_ms=result.duration_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"{operation} failed: {e}")
        run_id = _generate_run_id(operation)
        return OperationResponse(
            success=False,
            data={},
            cost_usd=0.0,
            run_id=run_id,
            error=str(e),
        )


@router.get(
    "/{job_id}/estimate-cost",
    response_model=CostEstimateResponse,
    dependencies=[Depends(verify_token)],
    summary="Estimate operation costs",
    description="Get cost estimates for one or more operations",
)
async def estimate_cost(
    job_id: str,
    operations: str = Query(
        ...,
        description="Comma-separated operation names: structure-jd,research-company,generate-cv",
    ),
    tier: str = Query(
        default="balanced",
        description="Model tier: 'fast', 'balanced', or 'quality'",
    ),
) -> CostEstimateResponse:
    """
    Estimate costs for specified operations.

    Useful for showing users expected costs before running operations.

    Args:
        job_id: MongoDB ObjectId of the job (validated but not used in estimation)
        operations: Comma-separated list of operation names
        tier: Model tier for cost calculation

    Returns:
        CostEstimateResponse with per-operation and total estimates
    """
    logger.info(f"Estimating costs for job {job_id}: operations={operations}, tier={tier}")

    try:
        # Validate job exists (ensures job_id is valid)
        _validate_job_exists(job_id)

        # Validate tier
        model_tier = _validate_tier(tier)

        # Parse operations
        operation_list = [op.strip() for op in operations.split(",") if op.strip()]

        valid_operations = {"structure-jd", "research-company", "generate-cv"}
        invalid_ops = set(operation_list) - valid_operations
        if invalid_ops:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid operations: {', '.join(invalid_ops)}. Valid: {', '.join(valid_operations)}",
            )

        # Calculate estimates
        estimates = []
        total_cost = 0.0

        for op in operation_list:
            cost = _estimate_operation_cost(model_tier, op)
            model = get_model_for_operation(model_tier, op)
            estimates.append(
                CostEstimate(
                    operation=op,
                    cost_usd=cost,
                    model=model,
                    tier=tier,
                )
            )
            total_cost += cost

        return CostEstimateResponse(
            estimates=estimates,
            total_cost_usd=round(total_cost, 4),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Cost estimation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Streaming Operation Endpoints (SSE Support)
# =============================================================================


class StreamingOperationResponse(BaseModel):
    """Response for streaming operation kickoff."""

    run_id: str = Field(..., description="Unique run identifier for SSE streaming")
    log_stream_url: str = Field(..., description="URL to stream logs via SSE")
    status: str = Field(default="queued", description="Initial status")


class OperationStatusResponse(BaseModel):
    """Response for operation status check."""

    run_id: str = Field(..., description="Operation run ID")
    status: str = Field(..., description="Current status")
    layer_status: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = Field(default=None)
    error: Optional[str] = Field(default=None)
    logs: List[str] = Field(default_factory=list, description="Accumulated log lines")
    langsmith_url: Optional[str] = Field(default=None, description="LangSmith trace URL for debugging")
    job_id: Optional[str] = Field(default=None, description="Associated job ID")
    started_at: Optional[str] = Field(default=None, description="Run start time (ISO format)")
    operation: Optional[str] = Field(default=None, description="Operation type")


# =============================================================================
# Deprecation Helper for /stream -> /start Migration
# =============================================================================


def _log_stream_deprecation(job_id: str, operation: str) -> None:
    """Log deprecation warning when /stream endpoint is used instead of /start."""
    logger.warning(
        f"DEPRECATED: /{job_id}/{operation}/stream called. "
        f"Use /{job_id}/{operation}/start instead. "
        "The /stream endpoint will be removed in a future version."
    )


def _log_bulk_deprecation(operation: str) -> None:
    """Log deprecation warning when /bulk endpoint is used instead of /batch."""
    logger.warning(
        f"DEPRECATED: /{operation}/bulk called. "
        f"Use /{operation}/batch instead. "
        "The /bulk endpoint will be removed in a future version."
    )


# =============================================================================
# Streaming Operation Endpoints - New Canonical Names (/start)
# =============================================================================


@router.post(
    "/{job_id}/research-company/start",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start company research operation",
    description="Start company research and return run_id for log polling",
)
@router.post(
    "/{job_id}/research-company/stream",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="[DEPRECATED] Start company research - use /start instead",
    description="DEPRECATED: Use /start endpoint. Start company research and return run_id for log polling",
    deprecated=True,
)
async def research_company_start(
    job_id: str,
    request: ResearchCompanyRequest,
    background_tasks: BackgroundTasks,
) -> StreamingOperationResponse:
    """
    Start company research operation.

    Returns immediately with run_id. Poll /api/logs/{run_id} for progress
    updates at 200ms intervals using LogPoller on the frontend.

    NOTE: This does NOT use Server-Sent Events (SSE) streaming.
    The name "stream" was misleading - this endpoint initiates a background
    operation and returns a run_id for HTTP polling. Use /start endpoint
    going forward; /stream is deprecated.

    NOTE: Job validation happens in the background task, not here.
    This allows sub-second response times for the kickoff.
    """
    operation = "research-company"

    # Validate tier synchronously (fast, no I/O)
    tier = _validate_tier(request.tier)

    # Create operation run for streaming IMMEDIATELY (no MongoDB yet)
    run_id = create_operation_run(job_id, operation)
    append_operation_log(run_id, f"Starting {operation} for job {job_id}")
    append_operation_log(run_id, f"Tier: {tier.value}, Force refresh: {request.force_refresh}")

    # Define the background task (validation happens HERE, not before response)
    async def execute_research():
        from src.services.company_research_service import CompanyResearchService

        log_cb = create_log_callback(run_id)
        layer_cb = create_layer_callback(run_id)

        try:
            update_operation_status(run_id, "running")

            # Validate job exists IN THE BACKGROUND TASK
            log_cb("🔍 Validating job exists...")
            try:
                await _validate_job_exists_async(job_id)
                log_cb("✅ Job validated")
            except HTTPException as e:
                log_cb(f"❌ Job validation failed: {e.detail}")
                update_operation_status(run_id, "failed", error=e.detail)
                return

            service = CompanyResearchService()
            try:
                # Execute the research with progress callback for real-time updates
                # The service emits progress for: fetch_job, cache_check, company_research,
                # role_research, people_research, save_results
                result = await service.execute(
                    job_id=job_id,
                    tier=tier,
                    force_refresh=request.force_refresh,
                    progress_callback=layer_cb,  # Pass layer_cb for real-time progress
                )

                update_operation_status(run_id, "completed" if result.success else "failed", result={
                    "success": result.success,
                    "data": result.data,
                    "cost_usd": result.cost_usd,
                    "run_id": result.run_id,
                    "model_used": result.model_used,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                })
                log_cb("✅ Research complete" if result.success else f"❌ Research failed: {result.error}")

            finally:
                service.close()

        except Exception as e:
            logger.exception(f"[{run_id[:16]}] {operation} failed: {e}")
            log_cb(f"❌ Error: {str(e)}")
            update_operation_status(run_id, "failed", error=str(e))

    # Add to background tasks - run in executor to avoid blocking the event loop
    background_tasks.add_task(run_service_in_executor, execute_research())

    return StreamingOperationResponse(
        run_id=run_id,
        log_stream_url=f"/api/jobs/operations/{run_id}/logs",
        status="queued",
    )


@router.post(
    "/{job_id}/generate-cv/start",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start CV generation operation",
    description="Start CV generation and return run_id for log polling",
)
@router.post(
    "/{job_id}/generate-cv/stream",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="[DEPRECATED] Start CV generation - use /start instead",
    description="DEPRECATED: Use /start endpoint. Start CV generation and return run_id for log polling",
    deprecated=True,
)
async def generate_cv_start(
    job_id: str,
    request: GenerateCVRequest,
    background_tasks: BackgroundTasks,
) -> StreamingOperationResponse:
    """
    Start CV generation operation.

    Returns immediately with run_id. Poll /api/logs/{run_id} for progress
    updates at 200ms intervals using LogPoller on the frontend.

    NOTE: This does NOT use Server-Sent Events (SSE) streaming.
    The name "stream" was misleading - this endpoint initiates a background
    operation and returns a run_id for HTTP polling. Use /start endpoint
    going forward; /stream is deprecated.

    NOTE: Job validation happens in the background task, not here.
    This allows sub-second response times for the kickoff.
    """
    operation = "generate-cv"

    # Validate tier synchronously (fast, no I/O)
    tier = _validate_tier(request.tier)

    # Create operation run for streaming IMMEDIATELY (no MongoDB yet)
    run_id = create_operation_run(job_id, operation)
    append_operation_log(run_id, f"Starting {operation} for job {job_id}")
    append_operation_log(run_id, f"Tier: {tier.value}, Use annotations: {request.use_annotations}")

    # Define the background task (validation happens HERE, not before response)
    async def execute_cv_generation():
        from src.services.cv_generation_service import CVGenerationService

        log_cb = create_log_callback(run_id)
        layer_cb = create_layer_callback(run_id)

        try:
            update_operation_status(run_id, "running")

            # Validate job exists IN THE BACKGROUND TASK
            log_cb("🔍 Validating job exists...")
            try:
                await _validate_job_exists_async(job_id)
                log_cb("✅ Job validated")
            except HTTPException as e:
                log_cb(f"❌ Job validation failed: {e.detail}")
                update_operation_status(run_id, "failed", error=e.detail)
                return

            service = CVGenerationService()

            # Execute CV generation with progress callback for real-time updates
            # The service emits progress for: fetch_job, validate, build_state,
            # cv_generator, persist
            result = await service.execute(
                job_id=job_id,
                tier=tier,
                use_annotations=request.use_annotations,
                progress_callback=layer_cb,  # Pass layer_cb for real-time progress
            )

            if result.success:
                # Persist the operation run for tracking
                service.persist_run(result, job_id, tier)

            update_operation_status(run_id, "completed" if result.success else "failed", result={
                "success": result.success,
                "data": result.data,
                "cost_usd": result.cost_usd,
                "run_id": result.run_id,
                "model_used": result.model_used,
                "duration_ms": result.duration_ms,
                "error": result.error,
            })
            log_cb("✅ CV generation complete" if result.success else f"❌ CV generation failed: {result.error}")

        except Exception as e:
            logger.exception(f"[{run_id[:16]}] {operation} failed: {e}")
            log_cb(f"❌ Error: {str(e)}")
            update_operation_status(run_id, "failed", error=str(e))

    # Add to background tasks - run in executor to avoid blocking the event loop
    background_tasks.add_task(run_service_in_executor, execute_cv_generation())

    return StreamingOperationResponse(
        run_id=run_id,
        log_stream_url=f"/api/jobs/operations/{run_id}/logs",
        status="queued",
    )


@router.post(
    "/{job_id}/full-extraction/start",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start full extraction operation",
    description="Start full JD extraction and return run_id for log polling",
)
@router.post(
    "/{job_id}/full-extraction/stream",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="[DEPRECATED] Start full extraction - use /start instead",
    description="DEPRECATED: Use /start endpoint. Start full JD extraction and return run_id for log polling",
    deprecated=True,
)
async def full_extraction_start(
    job_id: str,
    request: FullExtractionRequest,
    background_tasks: BackgroundTasks,
) -> StreamingOperationResponse:
    """
    Start full JD extraction operation.

    Returns immediately with run_id. Poll /api/logs/{run_id} for progress
    updates at 200ms intervals using LogPoller on the frontend.

    NOTE: This does NOT use Server-Sent Events (SSE) streaming.
    The name "stream" was misleading - this endpoint initiates a background
    operation and returns a run_id for HTTP polling. Use /start endpoint
    going forward; /stream is deprecated.

    NOTE: Job validation happens in the background task, not here.
    This allows sub-second response times for the kickoff.
    """
    operation = "full-extraction"

    # Validate tier synchronously (fast, no I/O)
    tier = _validate_tier(request.tier)

    # Create operation run for streaming IMMEDIATELY (no MongoDB yet)
    run_id = create_operation_run(job_id, operation)
    append_operation_log(run_id, f"Starting {operation} for job {job_id}")
    append_operation_log(run_id, f"Tier: {tier.value}, Use LLM: {request.use_llm}")

    # Define the background task (validation happens HERE, not before response)
    async def execute_extraction():
        from src.services.full_extraction_service import FullExtractionService

        log_cb = create_log_callback(run_id)
        layer_cb = create_layer_callback(run_id)

        try:
            update_operation_status(run_id, "running")

            # Validate job exists IN THE BACKGROUND TASK
            log_cb("🔍 Validating job exists...")
            try:
                await _validate_job_exists_async(job_id)
                log_cb("✅ Job validated")
            except HTTPException as e:
                log_cb(f"❌ Job validation failed: {e.detail}")
                update_operation_status(run_id, "failed", error=e.detail)
                return

            service = FullExtractionService()

            # Execute extraction with progress callback for real-time updates
            result = await service.execute(
                job_id=job_id,
                tier=tier,
                use_llm=request.use_llm,
                progress_callback=layer_cb,  # Pass layer_cb for real-time progress
                log_callback=log_cb,  # Pass log_cb for LLM backend visibility
            )

            # Final layer statuses are already emitted by the service via progress_callback
            # Only emit any additional statuses not covered by the service
            layer_status = result.data.get("layer_status", {}) if result.data else {}
            for layer_key, status_info in layer_status.items():
                # Service emits: jd_processor, jd_extractor, pain_points, fit_scoring, save_results
                # Only emit if not already covered
                if layer_key not in {"jd_processor", "jd_extractor", "pain_points", "fit_scoring", "save_results"}:
                    layer_cb(layer_key, status_info.get("status", "success"), status_info.get("message"))

            update_operation_status(run_id, "completed" if result.success else "failed", result={
                "success": result.success,
                "data": result.data,
                "cost_usd": result.cost_usd,
                "run_id": result.run_id,
                "model_used": result.model_used,
                "duration_ms": result.duration_ms,
                "error": result.error,
            })
            log_cb("✅ Extraction complete" if result.success else f"❌ Extraction failed: {result.error}")

        except Exception as e:
            logger.exception(f"[{run_id[:16]}] {operation} failed: {e}")
            log_cb(f"❌ Error: {str(e)}")
            update_operation_status(run_id, "failed", error=str(e))

    # Add to background tasks - run in executor to avoid blocking the event loop
    # The service.execute() internally uses run_async() which blocks with future.result()
    # By running in a separate thread, the main event loop stays responsive for log polling
    background_tasks.add_task(run_service_in_executor, execute_extraction())

    return StreamingOperationResponse(
        run_id=run_id,
        log_stream_url=f"/api/jobs/operations/{run_id}/logs",
        status="queued",
    )


# =============================================================================
# All-Ops Endpoint (Phase 1: JD Extraction + Company Research in Parallel)
# =============================================================================


class AllOpsRequest(BaseModel):
    """Request body for running all Phase 1 operations."""

    tier: str = Field(
        default="balanced",
        description="Model tier: 'fast', 'balanced', or 'quality'",
    )
    use_llm: bool = Field(
        default=True,
        description="Whether to use LLM for extraction processing",
    )
    force_refresh: bool = Field(
        default=False,
        description="Force refresh for company research (ignore cache)",
    )


@router.post(
    "/{job_id}/all-ops/start",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start all Phase 1 operations",
    description="Start JD extraction and company research in parallel with real-time progress updates",
)
@router.post(
    "/{job_id}/all-ops/stream",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="[DEPRECATED] Start all Phase 1 operations - use /start instead",
    description="DEPRECATED: Use /start endpoint. Start JD extraction and company research in parallel",
    deprecated=True,
)
async def all_ops_start(
    job_id: str,
    request: AllOpsRequest,
    background_tasks: BackgroundTasks,
) -> StreamingOperationResponse:
    """
    Start all Phase 1 operations (JD extraction + company research) in parallel.

    This is the "All Ops" button that combines:
    - Full Extraction: Layer 1.4 (JD parsing) + Layer 2 (pain points) + Layer 4 (fit scoring)
    - Company Research: Layer 3 (company) + Layer 3.5 (role) + Layer 5 (people contacts)

    Both operations run concurrently for faster execution.
    If one fails, the other's results are still returned (partial success).

    Returns immediately with run_id. Poll /api/logs/{run_id} for progress
    updates at 200ms intervals using LogPoller on the frontend.

    NOTE: This does NOT use Server-Sent Events (SSE) streaming.
    The name "stream" was misleading. Use /start endpoint going forward.
    """
    operation = "all-ops"

    # Validate tier synchronously (fast, no I/O)
    tier = _validate_tier(request.tier)

    # Create operation run for streaming IMMEDIATELY (no MongoDB yet)
    run_id = create_operation_run(job_id, operation)
    append_operation_log(run_id, f"Starting {operation} for job {job_id}")
    append_operation_log(run_id, f"Tier: {tier.value}, Use LLM: {request.use_llm}, Force refresh: {request.force_refresh}")

    # Define the background task (validation happens HERE, not before response)
    async def execute_all_ops():
        from src.services.all_ops_service import AllOpsService

        log_cb = create_log_callback(run_id)
        layer_cb = create_layer_callback(run_id)

        try:
            update_operation_status(run_id, "running")

            # Validate job exists IN THE BACKGROUND TASK
            log_cb("Validating job exists...")
            try:
                await _validate_job_exists_async(job_id)
                log_cb("Job validated")
            except HTTPException as e:
                log_cb(f"Job validation failed: {e.detail}")
                update_operation_status(run_id, "failed", error=e.detail)
                return

            service = AllOpsService()
            try:
                # Execute all operations with progress callback for real-time updates
                result = await service.execute(
                    job_id=job_id,
                    tier=tier,
                    use_llm=request.use_llm,
                    force_refresh=request.force_refresh,
                    progress_callback=layer_cb,
                    log_callback=log_cb,
                )

                # Determine final status based on result
                if result.success:
                    if result.data.get("phase1_complete"):
                        final_status = "completed"
                        log_cb("All operations completed successfully")
                    else:
                        # Partial success - some operations completed
                        final_status = "completed"
                        log_cb("Partial success - some operations completed")
                else:
                    final_status = "failed"
                    log_cb(f"All operations failed: {result.error}")

                update_operation_status(run_id, final_status, result={
                    "success": result.success,
                    "data": result.data,
                    "cost_usd": result.cost_usd,
                    "run_id": result.run_id,
                    "model_used": result.model_used,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                })

            finally:
                service.close()

        except Exception as e:
            logger.exception(f"[{run_id[:16]}] {operation} failed: {e}")
            log_cb(f"Error: {str(e)}")
            update_operation_status(run_id, "failed", error=str(e))

    # Add to background tasks - run in executor to avoid blocking the event loop
    background_tasks.add_task(run_service_in_executor, execute_all_ops())

    return StreamingOperationResponse(
        run_id=run_id,
        log_stream_url=f"/api/jobs/operations/{run_id}/logs",
        status="queued",
    )


# =============================================================================
# Form Scraping and Answer Generation Endpoint
# =============================================================================


class ScrapeFormAnswersRequest(BaseModel):
    """Request body for form scraping and answer generation."""

    tier: str = Field(
        default="balanced",
        description="Model tier: 'fast', 'balanced', or 'quality'",
    )
    force_refresh: bool = Field(
        default=False,
        description="Force re-scrape even if form is cached",
    )


@router.post(
    "/{job_id}/scrape-form-answers/start",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start form scraping and answer generation",
    description="Scrape the application form URL, extract fields, and generate personalized answers",
)
@router.post(
    "/{job_id}/scrape-form-answers/stream",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="[DEPRECATED] Start form scraping - use /start instead",
    description="DEPRECATED: Use /start endpoint. Scrape form and generate answers",
    deprecated=True,
)
async def scrape_form_answers_start(
    job_id: str,
    request: ScrapeFormAnswersRequest,
    background_tasks: BackgroundTasks,
) -> StreamingOperationResponse:
    """
    Start form scraping and personalized answer generation.

    This endpoint:
    1. Fetches the application_url from the job document
    2. Scrapes the form page using FireCrawl
    3. Extracts form fields using LLM
    4. Generates personalized answers for each field
    5. Saves results to MongoDB

    Returns immediately with run_id. Poll /api/logs/{run_id} for progress
    updates at 200ms intervals using LogPoller on the frontend.

    NOTE: This does NOT use Server-Sent Events (SSE) streaming.
    Use /start endpoint going forward; /stream is deprecated.
    """
    operation = "scrape-form-answers"

    # Validate tier synchronously (fast, no I/O)
    tier = _validate_tier(request.tier)

    # Create operation run for streaming IMMEDIATELY (no MongoDB yet)
    run_id = create_operation_run(job_id, operation)
    append_operation_log(run_id, f"Starting {operation} for job {job_id}")
    append_operation_log(run_id, f"Tier: {tier.value}, Force refresh: {request.force_refresh}")

    # Define the background task
    async def execute_scrape_and_generate():
        from src.services.form_scraper_service import FormScraperService

        log_cb = create_log_callback(run_id)
        layer_cb = create_layer_callback(run_id)

        try:
            update_operation_status(run_id, "running")

            # Validate job exists IN THE BACKGROUND TASK
            log_cb("Validating job exists...")
            try:
                job = await _validate_job_exists_async(job_id)
                log_cb("Job validated")
            except HTTPException as e:
                log_cb(f"Job validation failed: {e.detail}")
                update_operation_status(run_id, "failed", error=e.detail)
                return

            # Get application URL from job
            application_url = job.get("application_url")
            if not application_url:
                error_msg = "No application URL found for this job. Please add an application URL first."
                log_cb(f"Error: {error_msg}")
                update_operation_status(run_id, "failed", error=error_msg)
                return

            log_cb(f"Application URL: {application_url[:60]}...")

            # Execute form scraping and answer generation
            service = FormScraperService()
            result = await service.scrape_and_generate_answers(
                job_id=job_id,
                application_url=application_url,
                force_refresh=request.force_refresh,
                progress_callback=layer_cb,
            )

            if result.get("success"):
                fields_count = len(result.get("fields", []))
                answers_count = len(result.get("planned_answers", []))
                update_operation_status(run_id, "completed", result={
                    "success": True,
                    "fields_count": fields_count,
                    "answers_count": answers_count,
                    "form_type": result.get("form_type"),
                    "form_title": result.get("form_title"),
                    "from_cache": result.get("from_cache", False),
                })
                log_cb(f"Complete: {fields_count} fields, {answers_count} answers generated")
            else:
                error_msg = result.get("error", "Unknown error")
                update_operation_status(run_id, "failed", error=error_msg)
                log_cb(f"Failed: {error_msg}")

        except Exception as e:
            logger.exception(f"[{run_id[:16]}] {operation} failed: {e}")
            log_cb(f"Error: {str(e)}")
            update_operation_status(run_id, "failed", error=str(e))

    # Add to background tasks - run in executor to avoid blocking the event loop
    background_tasks.add_task(run_service_in_executor, execute_scrape_and_generate())

    return StreamingOperationResponse(
        run_id=run_id,
        log_stream_url=f"/api/jobs/operations/{run_id}/logs",
        status="queued",
    )


# =============================================================================
# Persona Synthesis Endpoint
# =============================================================================


@router.post(
    "/{job_id}/synthesize-persona",
    response_model=OperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Synthesize persona from identity annotations",
    description="Synthesize a coherent persona statement from identity annotations using LLM",
)
async def synthesize_persona(job_id: str) -> OperationResponse:
    """
    Synthesize persona from identity annotations using LLM.

    Extracts identity annotations (core_identity, strong_identity, developing)
    and synthesizes them into a coherent persona statement.

    Args:
        job_id: MongoDB ObjectId of the job

    Returns:
        OperationResponse with synthesized persona data
    """
    from src.common.persona_builder import PersonaBuilder

    operation = "synthesize-persona"

    logger.info(f"Starting {operation} for job {job_id}")

    try:
        # Validate job exists
        job = _validate_job_exists(job_id)
        jd_annotations = job.get("jd_annotations", {})

        builder = PersonaBuilder()

        # Check if there are identity annotations
        if not builder.has_identity_annotations(jd_annotations):
            return OperationResponse(
                success=True,
                data={"persona": None, "message": "No identity annotations found"},
                cost_usd=0.0,
                run_id=str(uuid.uuid4()),
            )

        # Run async synthesis with Claude CLI Opus
        persona = await builder.synthesize(jd_annotations, job_id=job_id)

        if not persona:
            return OperationResponse(
                success=True,
                data={"persona": None, "message": "Failed to synthesize persona"},
                cost_usd=0.0,
                run_id=str(uuid.uuid4()),
            )

        logger.info(f"Successfully synthesized persona for job {job_id}")

        return OperationResponse(
            success=True,
            data={
                "persona": persona.persona_statement,
                "primary": persona.primary_identity,
                "secondary": persona.secondary_identities,
                "source_annotations": persona.source_annotations,
            },
            cost_usd=0.015,  # Approximate cost for Opus synthesis
            run_id=str(uuid.uuid4()),
        )

    except Exception as e:
        logger.exception(f"Error synthesizing persona for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")


@router.get(
    "/operations/{run_id}/logs",
    dependencies=[Depends(verify_token)],
    summary="Stream operation logs via SSE",
    description="Stream real-time logs for an operation run",
)
async def stream_operation_logs_endpoint(run_id: str) -> StreamingResponse:
    """
    Stream logs for an operation via Server-Sent Events.

    Connects to the operation's log buffer and streams updates in real-time.
    The stream closes when the operation completes or fails.
    """
    return await stream_operation_logs(run_id)


@router.get(
    "/operations/{run_id}/status",
    response_model=OperationStatusResponse,
    dependencies=[Depends(verify_token)],
    summary="Get operation status",
    description="Get current status of an operation run",
)
async def get_operation_status(run_id: str) -> OperationStatusResponse:
    """
    Get current status of an operation run.

    Useful for polling-based status checks as fallback to SSE.
    Uses Redis fallback if in-memory state is not found (e.g., after runner restart).
    """
    state = get_operation_state(run_id)
    if not state:
        # Try Redis fallback - logs persist for 24 hours even after runner restart
        state = await get_operation_state_from_redis(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Operation run not found")

    return OperationStatusResponse(
        run_id=run_id,
        status=state.status,
        layer_status=state.layer_status,
        result=state.result,
        error=state.error,
        logs=state.logs,  # Include accumulated logs for polling fallback
        langsmith_url=state.langsmith_url,
        job_id=state.job_id,
        started_at=state.started_at.isoformat() if state.started_at else None,
        operation=state.operation,
    )


@router.get(
    "/operations/{run_id}/logs/redis",
    response_model=OperationStatusResponse,
    dependencies=[Depends(verify_token)],
    summary="Get operation logs from Redis",
    description="Fetch logs from Redis persistence (6h TTL) for completed runs",
)
async def get_operation_redis_logs(run_id: str) -> OperationStatusResponse:
    """
    Fetch operation logs from Redis persistence.

    This endpoint is used when in-memory logs are unavailable but Redis
    cache still has them. Logs persist in Redis for 24 hours after completion.

    Useful for:
    - Viewing logs after runner service restart
    - Refreshing logs for completed runs
    - Recovering logs when in-memory buffer is cleared
    """
    # Only try Redis - don't fall back to in-memory
    state = await get_operation_state_from_redis(run_id)

    if not state:
        raise HTTPException(
            status_code=404,
            detail="Logs not found in Redis. They may have expired (6h TTL) or were never persisted.",
        )

    return OperationStatusResponse(
        run_id=run_id,
        status=state.status,
        layer_status=state.layer_status,
        result=state.result,
        error=state.error,
        logs=state.logs,
        langsmith_url=state.langsmith_url,
        job_id=state.job_id,
        started_at=state.started_at.isoformat() if state.started_at else None,
        operation=state.operation,
    )


# =============================================================================
# Strength Suggestion Endpoint
# =============================================================================


class SuggestStrengthsRequest(BaseModel):
    """Request body for strength suggestions."""

    include_identity: bool = Field(
        default=True,
        description="Whether to suggest identity levels",
    )
    include_passion: bool = Field(
        default=True,
        description="Whether to suggest passion levels",
    )
    include_defaults: bool = Field(
        default=True,
        description="Whether to apply hardcoded defaults",
    )
    tier: str = Field(
        default="balanced",
        description="Model tier: 'fast', 'balanced', or 'quality'",
    )


class StrengthSuggestionItem(BaseModel):
    """A single strength suggestion."""

    target_text: str
    target_section: Optional[str] = None
    suggested_relevance: str
    suggested_requirement: str
    suggested_passion: Optional[str] = None
    suggested_identity: Optional[str] = None
    matching_skill: str
    matching_role: Optional[str] = None
    evidence_summary: Optional[str] = None
    reframe_note: Optional[str] = None
    suggested_keywords: List[str] = []
    confidence: float
    source: str


class SuggestStrengthsResponse(BaseModel):
    """Response for strength suggestions."""

    success: bool
    suggestions: List[StrengthSuggestionItem] = []
    defaults_applied: int = 0
    model_used: Optional[str] = None
    error: Optional[str] = None


@router.post(
    "/{job_id}/suggest-strengths",
    response_model=SuggestStrengthsResponse,
    dependencies=[Depends(verify_token)],
    summary="Suggest annotation strengths",
    description="Generate strength suggestions by analyzing JD against candidate profile",
)
async def suggest_strengths(
    job_id: str,
    request: SuggestStrengthsRequest,
) -> SuggestStrengthsResponse:
    """
    Generate strength suggestions by analyzing JD against candidate profile.

    This identifies skills/experience the candidate HAS that match the JD.
    Suggestions include recommended relevance, passion, and identity levels.

    Args:
        job_id: MongoDB ObjectId of the job
        request: Strength suggestion parameters

    Returns:
        SuggestStrengthsResponse with list of suggestions
    """
    from src.common.master_cv_store import MasterCVStore
    from src.services.strength_suggestion_service import StrengthSuggestionService

    operation = "suggest-strengths"

    logger.info(f"Starting {operation} for job {job_id}")

    try:
        # Validate job exists and get JD text
        job = _validate_job_exists(job_id)

        # Extract JD text
        jd_text = job.get("job_description") or job.get("description", "")
        if not jd_text:
            extracted = job.get("extracted_jd", {})
            jd_text = extracted.get("raw_text", "")

        if not jd_text:
            return SuggestStrengthsResponse(
                success=False,
                error="No job description found",
            )

        # Load candidate profile from MasterCVStore
        cv_store = MasterCVStore()
        candidate_profile = cv_store.get_profile_for_suggestions()

        # Get existing annotations to avoid duplicates
        jd_annotations = job.get("jd_annotations", {})
        existing_annotations = jd_annotations.get("annotations", [])

        # Select model based on tier
        tier = _validate_tier(request.tier)
        model_map = {
            "fast": "anthropic/claude-3-haiku-20240307",
            "balanced": "anthropic/claude-3-haiku-20240307",
            "quality": "anthropic/claude-3-5-sonnet-latest",
        }
        model_name = model_map.get(request.tier, "anthropic/claude-3-haiku-20240307")

        # Initialize LLM
        import os

        llm = ChatOpenAI(
            model=model_name,
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            temperature=0.3,
        )

        # Generate suggestions
        service = StrengthSuggestionService(llm=llm, model_name=model_name)
        suggestions = service.suggest_strengths(
            jd_text=jd_text,
            candidate_profile=candidate_profile,
            existing_annotations=existing_annotations,
            include_identity=request.include_identity,
            include_passion=request.include_passion,
            include_defaults=request.include_defaults,
        )

        # Count hardcoded defaults
        defaults_count = len(
            [s for s in suggestions if s.get("source") == "hardcoded_default"]
        )

        logger.info(
            f"Generated {len(suggestions)} strength suggestions for job {job_id} "
            f"({defaults_count} from defaults)"
        )

        return SuggestStrengthsResponse(
            success=True,
            suggestions=[StrengthSuggestionItem(**s) for s in suggestions],
            defaults_applied=defaults_count,
            model_used=model_name,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"{operation} failed: {e}")
        return SuggestStrengthsResponse(
            success=False,
            error=str(e),
        )


# =============================================================================
# Queue-Based Operation Endpoints (Job Detail Page)
# =============================================================================

# =============================================================================
# Operation Naming System
# =============================================================================
#
# Canonical operation names (new naming convention):
#   analyze-job          - JD extraction + pain points + fit scoring (was: full-extraction)
#   prepare-annotations  - JD parsing for annotation editor (was: structure-jd)
#   research-company     - Company + role research (unchanged)
#   discover-contacts    - Contact discovery (was bundled in research-company)
#   generate-cv          - CV generation (unchanged)
#   generate-cover-letter - Cover letter generation (was bundled in generate-cv)
#   generate-outreach    - Outreach message generation (new)
#   full-analysis        - All Phase 1 operations in parallel (was: all-ops)
#
# Legacy operation names are supported via OPERATION_ALIASES for backward compatibility.
# Using a legacy name will log a deprecation warning.
# =============================================================================

# Canonical operation names (new naming convention)
VALID_QUEUE_OPERATIONS = {
    # Analysis operations
    "analyze-job",           # JD extraction + pain points + fit scoring
    "prepare-annotations",   # JD parsing for annotation editor only
    # Research operations
    "research-company",      # Company + role research
    "discover-contacts",     # Contact discovery (separated from research)
    # Generation operations
    "generate-cv",           # CV generation
    "generate-cover-letter", # Cover letter generation (separated from CV)
    "generate-outreach",     # Outreach message generation
    # Combo operations
    "full-analysis",         # All Phase 1 operations in parallel
    # Legacy names (still valid for backward compatibility, but aliases are preferred)
    "structure-jd",
    "full-extraction",
    "extract",               # Primary JD extraction via Claude Code CLI
    "all-ops",               # Phase 1: JD extraction + company research in parallel
}

# Aliases for backward compatibility (legacy name -> canonical name)
# When a legacy name is used, it gets resolved to the canonical name
# and a deprecation warning is logged
OPERATION_ALIASES = {
    "full-extraction": "analyze-job",
    "structure-jd": "prepare-annotations",
    "all-ops": "full-analysis",
    "process-jd": "analyze-job",  # Duplicate operation that was removed
}

# Temporary routing for new operations that don't have their own services yet
# These route to existing parent services until the services are fully decoupled
OPERATION_ROUTING = {
    # New operations that route to existing services
    "discover-contacts": "research-company",     # Until discover_contacts_service.py exists
    "generate-cover-letter": "generate-cv",      # Until cover_letter_service.py exists
    "generate-outreach": "research-company",     # Until outreach_service.py exists
}

# Estimated seconds per operation (for wait time estimation)
OPERATION_TIME_ESTIMATES = {
    # Canonical names
    "analyze-job": 45,
    "prepare-annotations": 15,
    "research-company": 60,
    "discover-contacts": 30,
    "generate-cv": 30,
    "generate-cover-letter": 20,
    "generate-outreach": 25,
    "full-analysis": 90,
    # Legacy names (same times as their canonical equivalents)
    "structure-jd": 15,
    "full-extraction": 45,
    "extract": 20,  # Claude CLI typically 5-15s, buffer for queue overhead
    "all-ops": 90,  # Parallel but includes both extraction and research
}


def resolve_operation_alias(operation: str) -> str:
    """
    Resolve an operation name to its canonical form.

    If the operation is an alias (legacy name), logs a deprecation warning
    and returns the canonical name. Otherwise returns the operation unchanged.

    Args:
        operation: The operation name (may be alias or canonical)

    Returns:
        The canonical operation name
    """
    if operation in OPERATION_ALIASES:
        canonical = OPERATION_ALIASES[operation]
        logger.warning(
            f"DEPRECATED: Operation '{operation}' is deprecated. "
            f"Use '{canonical}' instead. "
            f"Legacy names will be removed in a future version."
        )
        return canonical
    return operation


def get_routed_operation(operation: str) -> str:
    """
    Get the actual operation to execute for a given operation name.

    Some new operations don't have their own services yet and are
    temporarily routed to existing parent services.

    Args:
        operation: The canonical operation name

    Returns:
        The operation name to actually execute (may be same or parent service)
    """
    return OPERATION_ROUTING.get(operation, operation)


@router.post(
    "/{job_id}/operations/{operation}/queue",
    response_model=QueueOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Queue a pipeline operation for background execution",
    description="Add a pipeline operation to the Redis queue instead of executing directly. Status updates via WebSocket.",
)
async def queue_operation(
    job_id: str,
    operation: str,
    request: QueueOperationRequest,
    background_tasks: BackgroundTasks,
) -> QueueOperationResponse:
    """
    Queue a pipeline operation for background execution.

    Instead of executing immediately, adds to Redis queue.
    Status updates are broadcast via WebSocket.

    This is the new queue-first approach for the job detail page:
    - Button click -> queue operation -> WebSocket status updates
    - User can view logs on-demand via "View Logs" button

    Supports both canonical and legacy operation names:
    - Canonical: analyze-job, prepare-annotations, full-analysis, etc.
    - Legacy: full-extraction, structure-jd, all-ops (deprecated, logs warning)

    Args:
        job_id: MongoDB ObjectId of the job
        operation: Operation type (canonical or legacy name)
        request: Queue operation request parameters
        background_tasks: FastAPI background tasks for async execution

    Returns:
        QueueOperationResponse with queue_id and position
    """
    # Resolve operation alias (logs deprecation warning if legacy name used)
    original_operation = operation
    operation = resolve_operation_alias(operation)

    # Get the actual operation to execute (for new ops that route to parent services)
    routed_operation = get_routed_operation(operation)

    # Validate operation type
    if operation not in VALID_QUEUE_OPERATIONS and original_operation not in VALID_QUEUE_OPERATIONS:
        # Show canonical names in error message (not legacy names)
        canonical_ops = sorted([
            op for op in VALID_QUEUE_OPERATIONS
            if op not in {"structure-jd", "full-extraction", "extract", "all-ops"}
        ])
        return QueueOperationResponse(
            success=False,
            queue_id="",
            job_id=job_id,
            operation=original_operation,
            status="failed",
            position=0,
            error=f"Invalid operation: {original_operation}. Valid: {', '.join(canonical_ops)}",
        )

    # Validate tier
    try:
        tier = _validate_tier(request.tier)
    except HTTPException as e:
        return QueueOperationResponse(
            success=False,
            queue_id="",
            job_id=job_id,
            operation=operation,
            status="failed",
            position=0,
            error=e.detail,
        )

    # Get queue manager
    queue_manager = _get_queue_manager()
    if not queue_manager or not queue_manager.is_connected:
        return QueueOperationResponse(
            success=False,
            queue_id="",
            job_id=job_id,
            operation=operation,
            status="failed",
            position=0,
            error="Queue service unavailable. Please try again later.",
        )

    try:
        # Fetch job details for queue display (async to avoid blocking)
        job_title, company = await _get_job_details_for_bulk(job_id)

        # Enqueue the operation
        queue_item = await queue_manager.enqueue(
            job_id=job_id,
            job_title=job_title,
            company=company,
            operation=operation,
            processing_tier=tier.value,
        )

        # Get position in queue
        position = await queue_manager.get_position(queue_item.queue_id)

        # Create operation run for log tracking (links to queue item)
        run_id = create_operation_run(job_id, operation)
        append_operation_log(run_id, f"Queued {operation} for job {job_id}")
        append_operation_log(run_id, f"Queue position: #{position}")

        # Link run_id to queue item (enables "View Logs" button)
        await queue_manager.link_run_id(queue_item.queue_id, run_id)

        # Calculate estimated wait time
        # Rough estimate: position * average operation time
        avg_time = OPERATION_TIME_ESTIMATES.get(operation, 30)
        estimated_wait = (position - 1) * avg_time if position > 1 else 0

        # Add background task to execute the operation - run in executor to avoid blocking
        # Use routed_operation for execution (may differ from canonical name for new ops)
        background_tasks.add_task(
            run_service_in_executor,
            _execute_queued_operation(
                queue_id=queue_item.queue_id,
                run_id=run_id,
                job_id=job_id,
                operation=routed_operation,  # Use routed operation for actual execution
                tier=tier,
                force_refresh=request.force_refresh or False,
                use_llm=request.use_llm if request.use_llm is not None else True,
                use_annotations=request.use_annotations if request.use_annotations is not None else True,
            )
        )

        logger.info(
            f"Queued {operation} for job {job_id} as {queue_item.queue_id} (position #{position})"
        )

        return QueueOperationResponse(
            success=True,
            queue_id=queue_item.queue_id,
            job_id=job_id,
            operation=operation,
            status="pending",
            position=position,
            estimated_wait_seconds=estimated_wait,
            run_id=run_id,
        )

    except Exception as e:
        logger.exception(f"Failed to queue {operation} for job {job_id}: {e}")
        return QueueOperationResponse(
            success=False,
            queue_id="",
            job_id=job_id,
            operation=operation,
            status="failed",
            position=0,
            error=str(e),
        )


async def _execute_queued_operation(
    queue_id: str,
    run_id: str,
    job_id: str,
    operation: str,
    tier: ModelTier,
    force_refresh: bool,
    use_llm: bool,
    use_annotations: bool,
):
    """
    Execute a queued operation in the background.

    This is the worker function that runs after queuing.
    Updates both operation state and queue state with progress.

    NOTE: This function runs in a worker thread via run_service_in_executor().
    All Redis queue operations MUST use the thread-safe wrappers
    (_queue_start_item_threadsafe, _queue_complete_threadsafe, _queue_fail_threadsafe)
    to avoid "Future attached to different loop" errors.

    Args:
        queue_id: Queue item ID
        run_id: Operation run ID (for log streaming)
        job_id: MongoDB job ID
        operation: Operation type
        tier: Model tier
        force_refresh: Whether to force refresh (for company research)
        use_llm: Whether to use LLM (for extraction)
        use_annotations: Whether to use annotations (for CV generation)
    """
    log_cb = create_log_callback(run_id)
    layer_cb = create_layer_callback(run_id)
    queue_manager = _get_queue_manager()

    try:
        # Move from PENDING -> RUNNING (broadcasts WebSocket event)
        # Use thread-safe wrapper since we're running in executor thread
        if queue_id:
            _queue_start_item_threadsafe(queue_manager, queue_id, log_cb)

        update_operation_status(run_id, "running")

        # Validate job exists
        log_cb("Validating job exists...")
        try:
            await _validate_job_exists_async(job_id)
            log_cb("Job validated")
        except HTTPException as e:
            log_cb(f"Job validation failed: {e.detail}")
            update_operation_status(run_id, "failed", error=e.detail)
            if queue_id and queue_manager and queue_manager.is_connected:
                _queue_fail_threadsafe(queue_manager, queue_id, e.detail)
            return

        # Execute the appropriate operation
        # Note: Both canonical names and legacy names are supported here.
        # The operation name may have been resolved through OPERATION_ALIASES,
        # but we still accept both for backward compatibility with direct calls.
        result = None

        if operation in ("structure-jd", "prepare-annotations"):
            # Legacy: structure-jd | Canonical: prepare-annotations
            from src.services.structure_jd_service import StructureJDService
            service = StructureJDService()
            result = await service.execute(
                job_id=job_id,
                tier=tier,
                use_llm=use_llm,
                progress_callback=layer_cb,
                log_callback=log_cb,  # Pass log_cb for LLM backend visibility
            )

        elif operation in ("full-extraction", "analyze-job"):
            # Legacy: full-extraction | Canonical: analyze-job
            from src.services.full_extraction_service import FullExtractionService
            service = FullExtractionService()
            result = await service.execute(
                job_id=job_id,
                tier=tier,
                use_llm=use_llm,
                progress_callback=layer_cb,
                log_callback=log_cb,  # Pass log_cb for LLM backend visibility
            )

        elif operation in ("research-company", "discover-contacts", "generate-outreach"):
            from src.services.company_research_service import CompanyResearchService
            service = CompanyResearchService()
            try:
                result = await service.execute(
                    job_id=job_id,
                    tier=tier,
                    force_refresh=force_refresh,
                    progress_callback=layer_cb,
                )
            finally:
                service.close()

        elif operation in ("generate-cv", "generate-cover-letter"):
            # Canonical: generate-cv, generate-cover-letter (both use CV service for now)
            from src.services.cv_generation_service import CVGenerationService
            service = CVGenerationService()
            result = await service.execute(
                job_id=job_id,
                tier=tier,
                use_annotations=use_annotations,
                progress_callback=layer_cb,
            )
            if result.success:
                service.persist_run(result, job_id, tier)

        elif operation == "extract":
            # Primary JD extraction via Claude Code CLI
            from src.layer1_4.claude_jd_extractor import JDExtractor
            from src.services.operation_base import OperationResult

            log_cb("Starting JD extraction...")
            layer_cb("extract", "running", "Initializing extractor")

            # Get job details for extraction
            job = _validate_job_exists_sync(job_id)
            title = job.get("title", "Unknown")
            company = job.get("company", "Unknown")
            job_description = job.get("job_description", "")

            if not job_description:
                layer_cb("extract", "failed", "No job description found")
                result = OperationResult(
                    success=False,
                    run_id=run_id,
                    operation="extract",
                    data={},
                    cost_usd=0.0,
                    error="No job description found for extraction",
                )
            else:
                log_cb(f"Extracting JD for: {title} at {company}")
                layer_cb("extract", "running", f"Extracting: {title[:30]}...")

                # Run extraction (sync operation in thread pool)
                extractor = JDExtractor()
                loop = asyncio.get_event_loop()
                extraction_result = await loop.run_in_executor(
                    None,
                    lambda: extractor.extract(
                        job_id=job_id,
                        title=title,
                        company=company,
                        job_description=job_description,
                    )
                )

                if extraction_result.success and extraction_result.extracted_jd:
                    # Save to MongoDB
                    log_cb("Saving extraction to MongoDB...")
                    client = _get_mongo_client()
                    db = client[os.getenv("MONGO_DB_NAME", "jobs")]
                    collection = db["level-2"]
                    collection.update_one(
                        {"_id": ObjectId(job_id)},
                        {
                            "$set": {
                                "extracted_jd": extraction_result.extracted_jd,
                                "extracted_jd_metadata": {
                                    "model": extraction_result.model,
                                    "extracted_at": extraction_result.extracted_at,
                                    "duration_ms": extraction_result.duration_ms,
                                    "extractor": "claude-code-cli",
                                }
                            }
                        }
                    )
                    layer_cb("extract", "completed", f"Extracted in {extraction_result.duration_ms}ms")
                    result = OperationResult(
                        success=True,
                        run_id=run_id,
                        operation="extract",
                        data={"extracted_jd": extraction_result.extracted_jd},
                        cost_usd=0.0,  # Claude Max subscription = $0 marginal cost
                        model_used=extraction_result.model,
                        duration_ms=extraction_result.duration_ms,
                    )
                else:
                    layer_cb("extract", "failed", extraction_result.error or "Extraction failed")
                    result = OperationResult(
                        success=False,
                        run_id=run_id,
                        operation="extract",
                        data={},
                        cost_usd=0.0,
                        error=extraction_result.error or "Extraction failed",
                        model_used=extraction_result.model,
                        duration_ms=extraction_result.duration_ms,
                    )

        elif operation in ("all-ops", "full-analysis"):
            # Legacy: all-ops | Canonical: full-analysis
            # Phase 1: JD extraction + company research in parallel
            from src.services.all_ops_service import AllOpsService
            service = AllOpsService()
            try:
                result = await service.execute(
                    job_id=job_id,
                    tier=tier,
                    force_refresh=force_refresh,
                    use_llm=use_llm,
                    progress_callback=layer_cb,
                    log_callback=log_cb,
                )
            finally:
                service.close()

        # Update operation status
        if result:
            update_operation_status(
                run_id,
                "completed" if result.success else "failed",
                result={
                    "success": result.success,
                    "data": result.data,
                    "cost_usd": result.cost_usd,
                    "run_id": result.run_id,
                    "model_used": result.model_used,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                }
            )
            log_cb(f"Operation complete" if result.success else f"Operation failed: {result.error}")

            # Complete queue item (broadcasts WebSocket event)
            # Use thread-safe wrapper since we're running in executor thread
            if queue_id and queue_manager and queue_manager.is_connected:
                try:
                    if result.success:
                        _queue_complete_threadsafe(queue_manager, queue_id, success=True)
                    else:
                        _queue_fail_threadsafe(queue_manager, queue_id, result.error or "Operation failed")
                except Exception as e:
                    logger.warning(f"[{run_id[:16]}] Failed to complete queue item: {e}")

    except Exception as e:
        logger.exception(f"[{run_id[:16]}] Queued {operation} failed: {e}")
        log_cb(f"Error: {str(e)}")
        update_operation_status(run_id, "failed", error=str(e))
        # Use thread-safe wrapper since we're running in executor thread
        if queue_id and queue_manager and queue_manager.is_connected:
            try:
                _queue_fail_threadsafe(queue_manager, queue_id, str(e))
            except Exception:
                pass


async def _get_last_operation_run(job_id: str, operation: str) -> Optional[Dict[str, Any]]:
    """
    Get the most recent operation run from MongoDB for a job+operation.

    This is used as a fallback when no queue item exists (after queue cleanup).
    Allows viewing logs from previously completed/failed operations.

    Args:
        job_id: MongoDB job ID
        operation: Operation type (full-extraction, research-company, etc.)

    Returns:
        Dict with run details or None if no runs found
    """
    try:
        client = _get_mongo_client()
        if not client:
            return None

        db = client[os.getenv("MONGO_DB_NAME", "jobs")]
        collection = db["operation_runs"]

        # Find the most recent run for this job+operation
        def sync_find():
            return collection.find_one(
                {"job_id": job_id, "operation": operation},
                sort=[("timestamp", -1)],  # Most recent first
            )

        result = await asyncio.get_event_loop().run_in_executor(
            _db_executor, sync_find
        )

        return result

    except Exception as e:
        logger.warning(f"Failed to get last operation run for {operation} on job {job_id}: {e}")
        return None


@router.get(
    "/{job_id}/queue-status",
    response_model=JobQueueStatusResponse,
    dependencies=[Depends(verify_token)],
    summary="Get queue status for all operations on a job",
    description="Get the queue status for each pipeline operation on a specific job. Used by the pipelines panel.",
)
async def get_job_queue_status(job_id: str) -> JobQueueStatusResponse:
    """
    Get queue status for all operations on a specific job.

    Used by the frontend pipelines panel to show current status
    of each operation type (full-extraction, research-company, generate-cv).

    First checks the in-memory queue for active/pending items.
    If no queue item exists, falls back to querying operation_runs
    for previously completed runs (allows viewing historical logs).

    Args:
        job_id: MongoDB ObjectId of the job

    Returns:
        JobQueueStatusResponse with status for each operation
    """
    queue_manager = _get_queue_manager()

    operations: Dict[str, Optional[OperationQueueStatus]] = {}

    for op in VALID_QUEUE_OPERATIONS:
        item = None
        if queue_manager and queue_manager.is_connected:
            try:
                item = await queue_manager.get_item_by_job_id_and_operation(job_id, op)
            except Exception as e:
                logger.warning(f"Failed to get queue status for {op} on job {job_id}: {e}")

        if item:
            # Queue item exists (pending, running, or recently completed)
            operations[op] = OperationQueueStatus(
                status=item.status.value,
                queue_id=item.queue_id,
                run_id=item.run_id,
                position=item.position if item.position > 0 else None,
                started_at=item.started_at,
                completed_at=item.completed_at,
                error=item.error,
            )
        else:
            # No queue item - check operation_runs for historical data
            last_run = await _get_last_operation_run(job_id, op)
            if last_run:
                # Found a previous run - return its status so user can view logs
                operations[op] = OperationQueueStatus(
                    status="completed" if last_run.get("success") else "failed",
                    queue_id=None,  # No queue_id for historical runs
                    run_id=last_run.get("run_id"),
                    position=None,
                    started_at=last_run.get("timestamp"),
                    completed_at=last_run.get("timestamp"),
                    error=last_run.get("error"),
                )
            else:
                operations[op] = None

    return JobQueueStatusResponse(job_id=job_id, operations=operations)


# =============================================================================
# Bulk Operation Endpoints (Batch Processing)
# =============================================================================


async def _get_job_details_for_bulk(job_id: str) -> tuple:
    """
    Fetch job title and company from MongoDB for bulk operations.

    Returns:
        Tuple of (job_title, company) or ("Unknown Job", "Unknown Company") if not found
    """
    try:
        # Validate ObjectId format first
        if not job_id or len(job_id) != 24:
            logger.warning(f"Invalid job_id format for bulk lookup: {job_id}")
            return ("Unknown Job", "Unknown Company")

        try:
            oid = ObjectId(job_id)
        except Exception as e:
            logger.warning(f"Failed to convert job_id to ObjectId: {job_id} - {e}")
            return ("Unknown Job", "Unknown Company")

        client = _get_mongo_client()
        if not client:
            logger.error("MongoDB client not available for bulk job lookup")
            return ("Unknown Job", "Unknown Company")

        db = client[os.getenv("MONGO_DB_NAME", "jobs")]
        collection = db["level-2"]

        # Use asyncio.to_thread for modern async pattern (Python 3.9+)
        def sync_find():
            return collection.find_one(
                {"_id": oid},
                {"title": 1, "company_name": 1, "company": 1}
            )

        job = await asyncio.to_thread(sync_find)

        if not job:
            logger.debug(f"Job not found in MongoDB for bulk lookup: {job_id}")
            return ("Unknown Job", "Unknown Company")

        title = job.get("title") or "Unknown Job"
        company = job.get("company_name") or job.get("company") or "Unknown Company"

        logger.debug(f"Bulk lookup for {job_id}: title='{title}', company='{company}'")
        return (title, company)

    except Exception as e:
        logger.exception(f"Failed to fetch job details for {job_id}: {e}")
        return ("Unknown Job", "Unknown Company")


def _get_queue_manager():
    """Get the queue manager instance from the app module."""
    try:
        from runner_service.app import _queue_manager
        return _queue_manager
    except ImportError:
        return None


# =============================================================================
# Batch Operation Endpoints - New Canonical Names (/batch)
# =============================================================================


@router.post(
    "/full-extraction/batch",
    response_model=BulkOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start full extraction for multiple jobs",
    description="Queue multiple jobs for extraction (Layer 1.4 + 2 + 4). Returns run_ids for log polling.",
)
@router.post(
    "/full-extraction/bulk",
    response_model=BulkOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="[DEPRECATED] Start full extraction batch - use /batch instead",
    description="DEPRECATED: Use /batch endpoint. Queue multiple jobs for extraction.",
    deprecated=True,
)
async def full_extraction_batch(
    request: BulkOperationRequest,
    background_tasks: BackgroundTasks,
) -> BulkOperationResponse:
    """
    Start full extraction for multiple jobs with queue integration.

    Each job is added to the Redis queue (appears in Pipeline Queue UI),
    and executes asynchronously. Returns immediately with run_ids.
    """
    operation = "full-extraction"
    tier = _validate_tier(request.tier)
    responses: List[BulkOperationRunInfo] = []
    queue_manager = _get_queue_manager()

    for job_id in request.job_ids:
        # Create operation run for log tracking
        run_id = create_operation_run(job_id, operation)
        append_operation_log(run_id, f"Starting {operation} for job {job_id}")
        append_operation_log(run_id, f"Tier: {tier.value}, Use LLM: {request.use_llm}")

        # Add to Redis queue if available (shows in Pipeline Queue UI)
        queue_id = None
        if queue_manager and queue_manager.is_connected:
            try:
                job_title, company = await _get_job_details_for_bulk(job_id)
                queue_item = await queue_manager.enqueue(
                    job_id=job_id,
                    job_title=job_title,
                    company=company,
                    operation=operation,
                    processing_tier=tier.value,
                )
                queue_id = queue_item.queue_id

                # Link run_id to queue item (enables "View Logs" button)
                await queue_manager.link_run_id(queue_id, run_id)
                append_operation_log(run_id, f"📋 Queued as {queue_id}")
            except Exception as e:
                logger.warning(f"[{run_id[:16]}] Failed to add to queue: {e}")
                append_operation_log(run_id, f"⚠️ Queue unavailable: {e}")

        # Submit directly to executor for true parallel execution (fire-and-forget)
        # Unlike BackgroundTasks which runs async tasks sequentially, this runs them in parallel
        submit_service_task(
            _execute_extraction_bulk_task(
                run_id=run_id,
                job_id=job_id,
                tier=tier,
                use_llm=request.use_llm,
                queue_id=queue_id,
            )
        )

        responses.append(BulkOperationRunInfo(
            run_id=run_id,
            job_id=job_id,
            log_stream_url=f"/api/jobs/operations/{run_id}/logs",
            status="queued",
        ))

    logger.info(f"Bulk {operation}: queued {len(responses)} jobs")
    return BulkOperationResponse(runs=responses, total_count=len(responses))


async def _start_queue_item(queue_manager, queue_id: str, log_cb) -> bool:
    """Move queue item from pending to running and broadcast WebSocket event."""
    from runner_service.queue.models import QueueItemStatus

    try:
        if not queue_manager or not queue_manager.is_connected:
            return False

        item = await queue_manager.get_item(queue_id)
        if not item:
            return False

        # Remove from pending queue
        await queue_manager._redis.lrem(queue_manager.PENDING_KEY, 1, queue_id)

        # Add to running set
        await queue_manager._redis.sadd(queue_manager.RUNNING_KEY, queue_id)

        # Update item status
        item.status = QueueItemStatus.RUNNING
        item.started_at = datetime.utcnow()
        item.position = 0
        await queue_manager._update_item(item)

        # Publish WebSocket event
        await queue_manager._publish_event("started", item)

        log_cb("🚀 Started processing")
        return True

    except Exception as e:
        logger.warning(f"Failed to start queue item {queue_id}: {e}")
        return False


async def _execute_extraction_bulk_task(
    run_id: str,
    job_id: str,
    tier: ModelTier,
    use_llm: bool,
    queue_id: Optional[str],
):
    """Execute extraction with queue status updates."""
    from src.services.full_extraction_service import FullExtractionService

    log_cb = create_log_callback(run_id)
    layer_cb = create_layer_callback(run_id)
    queue_manager = _get_queue_manager()

    try:
        # Move from PENDING → RUNNING (broadcasts WebSocket event)
        # Use thread-safe wrapper since we're running in a worker thread
        if queue_id:
            _queue_start_item_threadsafe(queue_manager, queue_id, log_cb)

        update_operation_status(run_id, "running")

        # Validate job exists
        log_cb("🔍 Validating job exists...")
        try:
            await _validate_job_exists_async(job_id)
            log_cb("✅ Job validated")
        except HTTPException as e:
            log_cb(f"❌ Job validation failed: {e.detail}")
            update_operation_status(run_id, "failed", error=e.detail)
            if queue_id and queue_manager and queue_manager.is_connected:
                _queue_fail_threadsafe(queue_manager, queue_id, e.detail)
            return

        # Execute extraction
        service = FullExtractionService()
        result = await service.execute(
            job_id=job_id,
            tier=tier,
            use_llm=use_llm,
            progress_callback=layer_cb,
            log_callback=log_cb,  # Pass log_cb for LLM backend visibility
        )

        # Update status
        update_operation_status(run_id, "completed" if result.success else "failed", result={
            "success": result.success,
            "data": result.data,
            "cost_usd": result.cost_usd,
            "run_id": result.run_id,
            "model_used": result.model_used,
            "duration_ms": result.duration_ms,
            "error": result.error,
        })
        log_cb("✅ Extraction complete" if result.success else f"❌ Extraction failed: {result.error}")

        # Complete queue item using thread-safe wrapper
        if queue_id and queue_manager and queue_manager.is_connected:
            if result.success:
                _queue_complete_threadsafe(queue_manager, queue_id, success=True)
            else:
                _queue_fail_threadsafe(queue_manager, queue_id, result.error or "Extraction failed")

    except Exception as e:
        logger.exception(f"[{run_id[:16]}] Bulk extraction failed: {e}")
        log_cb(f"❌ Error: {str(e)}")
        update_operation_status(run_id, "failed", error=str(e))
        if queue_id and queue_manager and queue_manager.is_connected:
            _queue_fail_threadsafe(queue_manager, queue_id, str(e))


@router.post(
    "/research-company/batch",
    response_model=BulkOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start company research for multiple jobs",
    description="Queue multiple jobs for company research. Returns run_ids for log polling.",
)
@router.post(
    "/research-company/bulk",
    response_model=BulkOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="[DEPRECATED] Start company research batch - use /batch instead",
    description="DEPRECATED: Use /batch endpoint. Queue multiple jobs for company research.",
    deprecated=True,
)
async def research_company_batch(
    request: BulkOperationRequest,
    background_tasks: BackgroundTasks,
) -> BulkOperationResponse:
    """
    Start company research for multiple jobs with queue integration.

    Each job is added to the Redis queue (appears in Pipeline Queue UI),
    and executes asynchronously. Returns immediately with run_ids.
    """
    operation = "research-company"
    tier = _validate_tier(request.tier)
    responses: List[BulkOperationRunInfo] = []
    queue_manager = _get_queue_manager()

    for job_id in request.job_ids:
        # Create operation run for log tracking
        run_id = create_operation_run(job_id, operation)
        append_operation_log(run_id, f"Starting {operation} for job {job_id}")
        append_operation_log(run_id, f"Tier: {tier.value}, Force refresh: {request.force_refresh}")

        # Add to Redis queue if available
        queue_id = None
        if queue_manager and queue_manager.is_connected:
            try:
                job_title, company = await _get_job_details_for_bulk(job_id)
                queue_item = await queue_manager.enqueue(
                    job_id=job_id,
                    job_title=job_title,
                    company=company,
                    operation=operation,
                    processing_tier=tier.value,
                )
                queue_id = queue_item.queue_id
                await queue_manager.link_run_id(queue_id, run_id)
                append_operation_log(run_id, f"📋 Queued as {queue_id}")
            except Exception as e:
                logger.warning(f"[{run_id[:16]}] Failed to add to queue: {e}")
                append_operation_log(run_id, f"⚠️ Queue unavailable: {e}")

        # Submit directly to executor for true parallel execution (fire-and-forget)
        # Unlike BackgroundTasks which runs async tasks sequentially, this runs them in parallel
        submit_service_task(
            _execute_research_bulk_task(
                run_id=run_id,
                job_id=job_id,
                tier=tier,
                force_refresh=request.force_refresh or False,
                queue_id=queue_id,
            )
        )

        responses.append(BulkOperationRunInfo(
            run_id=run_id,
            job_id=job_id,
            log_stream_url=f"/api/jobs/operations/{run_id}/logs",
            status="queued",
        ))

    logger.info(f"Bulk {operation}: queued {len(responses)} jobs")
    return BulkOperationResponse(runs=responses, total_count=len(responses))


async def _execute_research_bulk_task(
    run_id: str,
    job_id: str,
    tier: ModelTier,
    force_refresh: bool,
    queue_id: Optional[str],
):
    """Execute company research with queue status updates."""
    from src.services.company_research_service import CompanyResearchService

    log_cb = create_log_callback(run_id)
    layer_cb = create_layer_callback(run_id)
    queue_manager = _get_queue_manager()

    try:
        # Move from PENDING → RUNNING (broadcasts WebSocket event)
        # Use thread-safe wrapper since we're running in a worker thread
        if queue_id:
            _queue_start_item_threadsafe(queue_manager, queue_id, log_cb)

        update_operation_status(run_id, "running")

        # Validate job exists
        log_cb("🔍 Validating job exists...")
        try:
            await _validate_job_exists_async(job_id)
            log_cb("✅ Job validated")
        except HTTPException as e:
            log_cb(f"❌ Job validation failed: {e.detail}")
            update_operation_status(run_id, "failed", error=e.detail)
            if queue_id and queue_manager and queue_manager.is_connected:
                _queue_fail_threadsafe(queue_manager, queue_id, e.detail)
            return

        # Execute research
        service = CompanyResearchService()
        try:
            result = await service.execute(
                job_id=job_id,
                tier=tier,
                force_refresh=force_refresh,
                progress_callback=layer_cb,
            )

            update_operation_status(run_id, "completed" if result.success else "failed", result={
                "success": result.success,
                "data": result.data,
                "cost_usd": result.cost_usd,
                "run_id": result.run_id,
                "model_used": result.model_used,
                "duration_ms": result.duration_ms,
                "error": result.error,
            })
            log_cb("✅ Research complete" if result.success else f"❌ Research failed: {result.error}")

            # Complete queue item using thread-safe wrapper
            if queue_id and queue_manager and queue_manager.is_connected:
                if result.success:
                    _queue_complete_threadsafe(queue_manager, queue_id, success=True)
                else:
                    _queue_fail_threadsafe(queue_manager, queue_id, result.error or "Research failed")

        finally:
            service.close()

    except Exception as e:
        logger.exception(f"[{run_id[:16]}] Bulk research failed: {e}")
        log_cb(f"❌ Error: {str(e)}")
        update_operation_status(run_id, "failed", error=str(e))
        if queue_id and queue_manager and queue_manager.is_connected:
            _queue_fail_threadsafe(queue_manager, queue_id, str(e))


@router.post(
    "/generate-cv/batch",
    response_model=BulkOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start CV generation for multiple jobs",
    description="Queue multiple jobs for CV generation. Returns run_ids for log polling.",
)
@router.post(
    "/generate-cv/bulk",
    response_model=BulkOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="[DEPRECATED] Start CV generation batch - use /batch instead",
    description="DEPRECATED: Use /batch endpoint. Queue multiple jobs for CV generation.",
    deprecated=True,
)
async def generate_cv_batch(
    request: BulkOperationRequest,
    background_tasks: BackgroundTasks,
) -> BulkOperationResponse:
    """
    Start CV generation for multiple jobs with queue integration.

    Each job is added to the Redis queue (appears in Pipeline Queue UI),
    and executes asynchronously. Returns immediately with run_ids.
    """
    operation = "generate-cv"
    tier = _validate_tier(request.tier)
    responses: List[BulkOperationRunInfo] = []
    queue_manager = _get_queue_manager()

    for job_id in request.job_ids:
        # Create operation run for log tracking
        run_id = create_operation_run(job_id, operation)
        append_operation_log(run_id, f"Starting {operation} for job {job_id}")
        append_operation_log(run_id, f"Tier: {tier.value}")

        # Add to Redis queue if available
        queue_id = None
        if queue_manager and queue_manager.is_connected:
            try:
                job_title, company = await _get_job_details_for_bulk(job_id)
                queue_item = await queue_manager.enqueue(
                    job_id=job_id,
                    job_title=job_title,
                    company=company,
                    operation=operation,
                    processing_tier=tier.value,
                )
                queue_id = queue_item.queue_id
                await queue_manager.link_run_id(queue_id, run_id)
                append_operation_log(run_id, f"📋 Queued as {queue_id}")
            except Exception as e:
                logger.warning(f"[{run_id[:16]}] Failed to add to queue: {e}")
                append_operation_log(run_id, f"⚠️ Queue unavailable: {e}")

        # Submit directly to executor for true parallel execution (fire-and-forget)
        # Unlike BackgroundTasks which runs async tasks sequentially, this runs them in parallel
        submit_service_task(
            _execute_cv_bulk_task(
                run_id=run_id,
                job_id=job_id,
                tier=tier,
                queue_id=queue_id,
            )
        )

        responses.append(BulkOperationRunInfo(
            run_id=run_id,
            job_id=job_id,
            log_stream_url=f"/api/jobs/operations/{run_id}/logs",
            status="queued",
        ))

    logger.info(f"Bulk {operation}: queued {len(responses)} jobs")
    return BulkOperationResponse(runs=responses, total_count=len(responses))


async def _execute_cv_bulk_task(
    run_id: str,
    job_id: str,
    tier: ModelTier,
    queue_id: Optional[str],
):
    """Execute CV generation with queue status updates."""
    from src.services.cv_generation_service import CVGenerationService

    log_cb = create_log_callback(run_id)
    layer_cb = create_layer_callback(run_id)
    queue_manager = _get_queue_manager()

    try:
        # Move from PENDING → RUNNING (broadcasts WebSocket event)
        # Use thread-safe wrapper since we're running in a worker thread
        if queue_id:
            _queue_start_item_threadsafe(queue_manager, queue_id, log_cb)

        update_operation_status(run_id, "running")

        # Validate job exists
        log_cb("🔍 Validating job exists...")
        try:
            await _validate_job_exists_async(job_id)
            log_cb("✅ Job validated")
        except HTTPException as e:
            log_cb(f"❌ Job validation failed: {e.detail}")
            update_operation_status(run_id, "failed", error=e.detail)
            if queue_id and queue_manager and queue_manager.is_connected:
                _queue_fail_threadsafe(queue_manager, queue_id, e.detail)
            return

        # Execute CV generation
        service = CVGenerationService()
        result = await service.execute(
            job_id=job_id,
            tier=tier,
            progress_callback=layer_cb,
        )

        update_operation_status(run_id, "completed" if result.success else "failed", result={
            "success": result.success,
            "data": result.data,
            "cost_usd": result.cost_usd,
            "run_id": result.run_id,
            "model_used": result.model_used,
            "duration_ms": result.duration_ms,
            "error": result.error,
        })
        log_cb("✅ CV generation complete" if result.success else f"❌ CV generation failed: {result.error}")

        # Complete queue item using thread-safe wrapper
        if queue_id and queue_manager and queue_manager.is_connected:
            if result.success:
                _queue_complete_threadsafe(queue_manager, queue_id, success=True)
            else:
                _queue_fail_threadsafe(queue_manager, queue_id, result.error or "CV generation failed")

    except Exception as e:
        logger.exception(f"[{run_id[:16]}] Bulk CV generation failed: {e}")
        log_cb(f"❌ Error: {str(e)}")
        update_operation_status(run_id, "failed", error=str(e))
        if queue_id and queue_manager and queue_manager.is_connected:
            _queue_fail_threadsafe(queue_manager, queue_id, str(e))


@router.post(
    "/all-ops/batch",
    response_model=BulkOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start all Phase 1 operations for multiple jobs",
    description="Queue multiple jobs for parallel JD extraction and company research. Returns run_ids for log polling.",
)
@router.post(
    "/all-ops/bulk",
    response_model=BulkOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="[DEPRECATED] Start all Phase 1 ops batch - use /batch instead",
    description="DEPRECATED: Use /batch endpoint. Queue multiple jobs for parallel JD extraction and company research.",
    deprecated=True,
)
async def all_ops_batch(
    request: BulkOperationRequest,
    background_tasks: BackgroundTasks,
) -> BulkOperationResponse:
    """
    Start all Phase 1 operations for multiple jobs with queue integration.

    Each job is added to the Redis queue (appears in Pipeline Queue UI),
    and executes asynchronously with both extraction and research running
    in parallel for each job.

    Phase 1 includes:
    - Full Extraction: JD parsing + pain points + fit scoring
    - Company Research: Company + role research + people contacts

    Returns immediately with run_ids.
    """
    operation = "all-ops"
    tier = _validate_tier(request.tier)
    responses: List[BulkOperationRunInfo] = []
    queue_manager = _get_queue_manager()

    for job_id in request.job_ids:
        # Create operation run for log tracking
        run_id = create_operation_run(job_id, operation)
        append_operation_log(run_id, f"Starting {operation} for job {job_id}")
        append_operation_log(run_id, f"Tier: {tier.value}, Use LLM: {request.use_llm}, Force refresh: {request.force_refresh}")

        # Add to Redis queue if available
        queue_id = None
        if queue_manager and queue_manager.is_connected:
            try:
                job_title, company = await _get_job_details_for_bulk(job_id)
                queue_item = await queue_manager.enqueue(
                    job_id=job_id,
                    job_title=job_title,
                    company=company,
                    operation=operation,
                    processing_tier=tier.value,
                )
                queue_id = queue_item.queue_id
                await queue_manager.link_run_id(queue_id, run_id)
                append_operation_log(run_id, f"Queued as {queue_id}")
            except Exception as e:
                logger.warning(f"[{run_id[:16]}] Failed to add to queue: {e}")
                append_operation_log(run_id, f"Queue unavailable: {e}")

        # Submit directly to executor for true parallel execution (fire-and-forget)
        # Unlike BackgroundTasks which runs async tasks sequentially, this runs them in parallel
        submit_service_task(
            _execute_all_ops_bulk_task(
                run_id=run_id,
                job_id=job_id,
                tier=tier,
                use_llm=request.use_llm if request.use_llm is not None else True,
                force_refresh=request.force_refresh or False,
                queue_id=queue_id,
            )
        )

        responses.append(BulkOperationRunInfo(
            run_id=run_id,
            job_id=job_id,
            log_stream_url=f"/api/jobs/operations/{run_id}/logs",
            status="queued",
        ))

    logger.info(f"Bulk {operation}: queued {len(responses)} jobs")
    return BulkOperationResponse(runs=responses, total_count=len(responses))


async def _execute_all_ops_bulk_task(
    run_id: str,
    job_id: str,
    tier: ModelTier,
    use_llm: bool,
    force_refresh: bool,
    queue_id: Optional[str],
):
    """Execute all Phase 1 operations with queue status updates."""
    from src.services.all_ops_service import AllOpsService

    log_cb = create_log_callback(run_id)
    layer_cb = create_layer_callback(run_id)
    queue_manager = _get_queue_manager()

    try:
        # Move from PENDING -> RUNNING (broadcasts WebSocket event)
        # Use thread-safe wrapper since we're running in a worker thread
        if queue_id:
            _queue_start_item_threadsafe(queue_manager, queue_id, log_cb)

        update_operation_status(run_id, "running")

        # Validate job exists
        log_cb("Validating job exists...")
        try:
            await _validate_job_exists_async(job_id)
            log_cb("Job validated")
        except HTTPException as e:
            log_cb(f"Job validation failed: {e.detail}")
            update_operation_status(run_id, "failed", error=e.detail)
            if queue_id and queue_manager and queue_manager.is_connected:
                _queue_fail_threadsafe(queue_manager, queue_id, e.detail)
            return

        # Execute all operations
        service = AllOpsService()
        try:
            result = await service.execute(
                job_id=job_id,
                tier=tier,
                use_llm=use_llm,
                force_refresh=force_refresh,
                progress_callback=layer_cb,
                log_callback=log_cb,
            )

            # Determine final status
            if result.success:
                if result.data.get("phase1_complete"):
                    log_cb("All operations completed successfully")
                else:
                    log_cb("Partial success - some operations completed")
            else:
                log_cb(f"All operations failed: {result.error}")

            update_operation_status(run_id, "completed" if result.success else "failed", result={
                "success": result.success,
                "data": result.data,
                "cost_usd": result.cost_usd,
                "run_id": result.run_id,
                "model_used": result.model_used,
                "duration_ms": result.duration_ms,
                "error": result.error,
            })

            # Complete queue item using thread-safe wrapper
            if queue_id and queue_manager and queue_manager.is_connected:
                if result.success:
                    _queue_complete_threadsafe(queue_manager, queue_id, success=True)
                else:
                    _queue_fail_threadsafe(queue_manager, queue_id, result.error or "All-ops failed")

        finally:
            service.close()

    except Exception as e:
        logger.exception(f"[{run_id[:16]}] Bulk all-ops failed: {e}")
        log_cb(f"Error: {str(e)}")
        update_operation_status(run_id, "failed", error=str(e))
        if queue_id and queue_manager and queue_manager.is_connected:
            _queue_fail_threadsafe(queue_manager, queue_id, str(e))


# ============================================================================
# Google Drive Upload Endpoint
# ============================================================================


class GDriveUploadResponse(BaseModel):
    """Response model for Google Drive upload."""

    success: bool
    uploaded_at: Optional[str] = None
    message: str
    gdrive_file_id: Optional[str] = None
    gdrive_folder_id: Optional[str] = None


@router.post(
    "/{job_id}/cv/upload-drive",
    response_model=GDriveUploadResponse,
    dependencies=[Depends(verify_token)],
    summary="Upload CV PDF to Google Drive",
    description="Generate CV PDF and upload to Google Drive via n8n webhook. Creates company/role folder hierarchy.",
)
async def upload_cv_to_gdrive(job_id: str) -> GDriveUploadResponse:
    """
    Upload CV PDF to Google Drive via n8n webhook.

    This endpoint:
    1. Fetches job from MongoDB (company, title, cv_editor_state)
    2. Generates PDF via PDF service
    3. POSTs to n8n webhook with company_name, role_name, and PDF binary
    4. Updates MongoDB with gdrive_uploaded_at timestamp

    Args:
        job_id: MongoDB ObjectId of the job

    Returns:
        GDriveUploadResponse with success status and timestamp
    """
    import httpx
    from io import BytesIO

    # Get n8n webhook URL from environment
    n8n_webhook_url = os.getenv(
        "N8N_WEBHOOK_CV_UPLOAD",
        "https://n8n.srv1112039.hstgr.cloud/webhook/cv-upload",
    )
    pdf_service_url = os.getenv("PDF_SERVICE_URL", "http://pdf-service:8001")

    # Validate and fetch job
    job = _validate_job_exists_sync(job_id)
    company_name = job.get("company", "Unknown Company")
    role_name = job.get("title", "Unknown Role")

    # Get editor state for PDF generation
    editor_state = job.get("cv_editor_state")

    # If no editor state, try to migrate from cv_text
    if not editor_state and job.get("cv_text"):
        # Import migration function from app.py
        from ..app import migrate_cv_text_to_editor_state

        editor_state = migrate_cv_text_to_editor_state(job.get("cv_text"))

    if not editor_state:
        raise HTTPException(
            status_code=400,
            detail="No CV content available. Please generate or edit a CV first.",
        )

    # Build PDF request payload
    pdf_request = {
        "tiptap_json": editor_state.get("content", {"type": "doc", "content": []}),
        "documentStyles": editor_state.get("documentStyles", {}),
        "header": editor_state.get("header", ""),
        "footer": editor_state.get("footer", ""),
        "company": company_name,
        "role": role_name,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            # Step 1: Generate PDF
            logger.info(f"Generating PDF for job {job_id} for Google Drive upload")
            pdf_response = await http_client.post(
                f"{pdf_service_url}/cv-to-pdf",
                json=pdf_request,
            )
            pdf_response.raise_for_status()
            pdf_content = pdf_response.content

            # Step 2: Upload to n8n webhook
            logger.info(
                f"Uploading PDF to Google Drive: company={company_name}, role={role_name}"
            )

            # Prepare multipart form data
            # n8n expects: data (PDF file), company_name, role_name
            files = {
                "data": (
                    "Taimoor Alam Resume.pdf",
                    BytesIO(pdf_content),
                    "application/pdf",
                ),
            }
            form_data = {
                "company_name": company_name,
                "role_name": role_name,
            }

            upload_response = await http_client.post(
                n8n_webhook_url,
                files=files,
                data=form_data,
                timeout=30.0,
            )
            upload_response.raise_for_status()

            # Parse n8n response
            n8n_result = upload_response.json()
            logger.info(f"Google Drive upload successful: {n8n_result}")

            # Step 3: Update MongoDB with upload timestamp
            uploaded_at = datetime.utcnow()
            client = _get_mongo_client()
            db = client[os.getenv("MONGO_DB_NAME", "jobs")]
            db["level-2"].update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"gdrive_uploaded_at": uploaded_at}},
            )

            return GDriveUploadResponse(
                success=True,
                uploaded_at=uploaded_at.isoformat() + "Z",
                message="CV uploaded to Google Drive successfully",
                gdrive_file_id=n8n_result.get("file_id"),
                gdrive_folder_id=n8n_result.get("role_folder"),
            )

    except httpx.TimeoutException as e:
        logger.error(f"Timeout during Google Drive upload for job {job_id}: {e}")
        raise HTTPException(
            status_code=504,
            detail="Upload timed out. Please try again.",
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error during Google Drive upload for job {job_id}: {e.response.status_code}"
        )
        try:
            error_detail = e.response.json().get("detail", str(e))
        except Exception:
            error_detail = str(e)
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Upload failed: {error_detail}",
        )
    except Exception as e:
        logger.error(f"Google Drive upload failed for job {job_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}",
        )
