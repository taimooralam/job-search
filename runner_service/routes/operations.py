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


@router.post(
    "/{job_id}/research-company/stream",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start company research with SSE streaming",
    description="Start company research and return run_id for SSE log streaming",
)
async def research_company_stream(
    job_id: str,
    request: ResearchCompanyRequest,
    background_tasks: BackgroundTasks,
) -> StreamingOperationResponse:
    """
    Start company research with SSE streaming support.

    Returns immediately with run_id. Use the log_stream_url to connect
    to SSE and receive real-time progress updates.

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

    # Add to background tasks
    background_tasks.add_task(execute_research)

    return StreamingOperationResponse(
        run_id=run_id,
        log_stream_url=f"/api/jobs/operations/{run_id}/logs",
        status="queued",
    )


@router.post(
    "/{job_id}/generate-cv/stream",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start CV generation with SSE streaming",
    description="Start CV generation and return run_id for SSE log streaming",
)
async def generate_cv_stream(
    job_id: str,
    request: GenerateCVRequest,
    background_tasks: BackgroundTasks,
) -> StreamingOperationResponse:
    """
    Start CV generation with SSE streaming support.

    Returns immediately with run_id. Use the log_stream_url to connect
    to SSE and receive real-time progress updates.

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

    # Add to background tasks
    background_tasks.add_task(execute_cv_generation)

    return StreamingOperationResponse(
        run_id=run_id,
        log_stream_url=f"/api/jobs/operations/{run_id}/logs",
        status="queued",
    )


@router.post(
    "/{job_id}/full-extraction/stream",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start full extraction with SSE streaming",
    description="Start full JD extraction and return run_id for SSE log streaming",
)
async def full_extraction_stream(
    job_id: str,
    request: FullExtractionRequest,
    background_tasks: BackgroundTasks,
) -> StreamingOperationResponse:
    """
    Start full JD extraction with SSE streaming support.

    Returns immediately with run_id. Use the log_stream_url to connect
    to SSE and receive real-time progress updates.

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

    # Add to background tasks
    background_tasks.add_task(execute_extraction)

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
    "/{job_id}/scrape-form-answers/stream",
    response_model=StreamingOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Scrape application form and generate answers with SSE streaming",
    description="Scrape the application form URL, extract fields, and generate personalized answers",
)
async def scrape_form_answers_stream(
    job_id: str,
    request: ScrapeFormAnswersRequest,
    background_tasks: BackgroundTasks,
) -> StreamingOperationResponse:
    """
    Scrape application form and generate personalized answers with SSE streaming.

    This endpoint:
    1. Fetches the application_url from the job document
    2. Scrapes the form page using FireCrawl
    3. Extracts form fields using LLM
    4. Generates personalized answers for each field
    5. Saves results to MongoDB

    Returns immediately with run_id. Use the log_stream_url to connect
    to SSE and receive real-time progress updates.
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

    # Add to background tasks
    background_tasks.add_task(execute_scrape_and_generate)

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

        # Run async synthesis
        persona = await builder.synthesize(jd_annotations)

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
            cost_usd=0.001,  # Approximate cost for Haiku synthesis
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
    description="Fetch logs from Redis persistence (24h TTL) for completed runs",
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
            detail="Logs not found in Redis. They may have expired (24h TTL) or were never persisted.",
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

# Valid operations that can be queued from the detail page
VALID_QUEUE_OPERATIONS = {
    "structure-jd",
    "full-extraction",
    "research-company",
    "generate-cv",
}

# Estimated seconds per operation (for wait time estimation)
OPERATION_TIME_ESTIMATES = {
    "structure-jd": 15,
    "full-extraction": 45,
    "research-company": 60,
    "generate-cv": 30,
}


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

    Args:
        job_id: MongoDB ObjectId of the job
        operation: Operation type (structure-jd, full-extraction, research-company, generate-cv)
        request: Queue operation request parameters
        background_tasks: FastAPI background tasks for async execution

    Returns:
        QueueOperationResponse with queue_id and position
    """
    # Validate operation type
    if operation not in VALID_QUEUE_OPERATIONS:
        return QueueOperationResponse(
            success=False,
            queue_id="",
            job_id=job_id,
            operation=operation,
            status="failed",
            position=0,
            error=f"Invalid operation: {operation}. Valid: {', '.join(sorted(VALID_QUEUE_OPERATIONS))}",
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

        # Add background task to execute the operation
        background_tasks.add_task(
            _execute_queued_operation,
            queue_id=queue_item.queue_id,
            run_id=run_id,
            job_id=job_id,
            operation=operation,
            tier=tier,
            force_refresh=request.force_refresh or False,
            use_llm=request.use_llm if request.use_llm is not None else True,
            use_annotations=request.use_annotations if request.use_annotations is not None else True,
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
        if queue_id:
            await _start_queue_item(queue_manager, queue_id, log_cb)

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
                await queue_manager.fail(queue_id, e.detail)
            return

        # Execute the appropriate operation
        result = None

        if operation == "structure-jd":
            from src.services.structure_jd_service import StructureJDService
            service = StructureJDService()
            result = await service.execute(
                job_id=job_id,
                tier=tier,
                use_llm=use_llm,
            )

        elif operation == "full-extraction":
            from src.services.full_extraction_service import FullExtractionService
            service = FullExtractionService()
            result = await service.execute(
                job_id=job_id,
                tier=tier,
                use_llm=use_llm,
                progress_callback=layer_cb,
            )

        elif operation == "research-company":
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

        elif operation == "generate-cv":
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
            if queue_id and queue_manager and queue_manager.is_connected:
                try:
                    if result.success:
                        await queue_manager.complete(queue_id, success=True)
                    else:
                        await queue_manager.fail(queue_id, result.error or "Operation failed")
                except Exception as e:
                    logger.warning(f"[{run_id[:16]}] Failed to complete queue item: {e}")

    except Exception as e:
        logger.exception(f"[{run_id[:16]}] Queued {operation} failed: {e}")
        log_cb(f"Error: {str(e)}")
        update_operation_status(run_id, "failed", error=str(e))
        if queue_id and queue_manager and queue_manager.is_connected:
            try:
                await queue_manager.fail(queue_id, str(e))
            except Exception:
                pass


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


@router.post(
    "/full-extraction/bulk",
    response_model=BulkOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start full extraction for multiple jobs",
    description="Queue multiple jobs for extraction (Layer 1.4 + 2 + 4). Returns run_ids for individual log streams.",
)
async def full_extraction_bulk(
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

        # Add background task for execution
        background_tasks.add_task(
            _execute_extraction_bulk_task,
            run_id=run_id,
            job_id=job_id,
            tier=tier,
            use_llm=request.use_llm,
            queue_id=queue_id,
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
        if queue_id:
            await _start_queue_item(queue_manager, queue_id, log_cb)

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
                await queue_manager.fail(queue_id, e.detail)
            return

        # Execute extraction
        service = FullExtractionService()
        result = await service.execute(
            job_id=job_id,
            tier=tier,
            use_llm=use_llm,
            progress_callback=layer_cb,
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

        # Complete queue item (broadcasts WebSocket event)
        if queue_id and queue_manager and queue_manager.is_connected:
            try:
                if result.success:
                    await queue_manager.complete(queue_id, success=True)
                else:
                    await queue_manager.fail(queue_id, result.error or "Extraction failed")
            except Exception as e:
                logger.warning(f"[{run_id[:16]}] Failed to complete queue item: {e}")

    except Exception as e:
        logger.exception(f"[{run_id[:16]}] Bulk extraction failed: {e}")
        log_cb(f"❌ Error: {str(e)}")
        update_operation_status(run_id, "failed", error=str(e))
        if queue_id and queue_manager and queue_manager.is_connected:
            try:
                await queue_manager.fail(queue_id, str(e))
            except Exception:
                pass


@router.post(
    "/research-company/bulk",
    response_model=BulkOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start company research for multiple jobs",
    description="Queue multiple jobs for company research. Returns run_ids for individual log streams.",
)
async def research_company_bulk(
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

        # Add background task for execution
        background_tasks.add_task(
            _execute_research_bulk_task,
            run_id=run_id,
            job_id=job_id,
            tier=tier,
            force_refresh=request.force_refresh or False,
            queue_id=queue_id,
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
        if queue_id:
            await _start_queue_item(queue_manager, queue_id, log_cb)

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
                await queue_manager.fail(queue_id, e.detail)
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

            # Complete queue item
            if queue_id and queue_manager and queue_manager.is_connected:
                try:
                    if result.success:
                        await queue_manager.complete(queue_id, success=True)
                    else:
                        await queue_manager.fail(queue_id, result.error or "Research failed")
                except Exception as e:
                    logger.warning(f"[{run_id[:16]}] Failed to complete queue item: {e}")

        finally:
            service.close()

    except Exception as e:
        logger.exception(f"[{run_id[:16]}] Bulk research failed: {e}")
        log_cb(f"❌ Error: {str(e)}")
        update_operation_status(run_id, "failed", error=str(e))
        if queue_id and queue_manager and queue_manager.is_connected:
            try:
                await queue_manager.fail(queue_id, str(e))
            except Exception:
                pass


@router.post(
    "/generate-cv/bulk",
    response_model=BulkOperationResponse,
    dependencies=[Depends(verify_token)],
    summary="Start CV generation for multiple jobs",
    description="Queue multiple jobs for CV generation. Returns run_ids for individual log streams.",
)
async def generate_cv_bulk(
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

        # Add background task for execution
        background_tasks.add_task(
            _execute_cv_bulk_task,
            run_id=run_id,
            job_id=job_id,
            tier=tier,
            queue_id=queue_id,
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
        if queue_id:
            await _start_queue_item(queue_manager, queue_id, log_cb)

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
                await queue_manager.fail(queue_id, e.detail)
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

        # Complete queue item
        if queue_id and queue_manager and queue_manager.is_connected:
            try:
                if result.success:
                    await queue_manager.complete(queue_id, success=True)
                else:
                    await queue_manager.fail(queue_id, result.error or "CV generation failed")
            except Exception as e:
                logger.warning(f"[{run_id[:16]}] Failed to complete queue item: {e}")

    except Exception as e:
        logger.exception(f"[{run_id[:16]}] Bulk CV generation failed: {e}")
        log_cb(f"❌ Error: {str(e)}")
        update_operation_status(run_id, "failed", error=str(e))
        if queue_id and queue_manager and queue_manager.is_connected:
            try:
                await queue_manager.fail(queue_id, str(e))
            except Exception:
                pass
