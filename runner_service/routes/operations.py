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

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo import MongoClient

from src.common.model_tiers import (
    ModelTier,
    get_model_for_operation,
    get_tier_from_string,
    TIER_CONFIGS,
    OPERATION_TASK_TYPES,
)
from src.services.operation_base import OperationResult

from ..auth import verify_token

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


def _get_db_client() -> MongoClient:
    """
    Get MongoDB client for job validation.

    Returns:
        MongoClient instance

    Raises:
        HTTPException: If MongoDB is not configured
    """
    mongo_uri = (
        os.getenv("MONGODB_URI")
        or os.getenv("MONGO_URI")
        or "mongodb://localhost:27017"
    )
    return MongoClient(mongo_uri)


def _validate_job_exists(job_id: str) -> dict:
    """
    Validate that a job exists in MongoDB.

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

    # Check job exists
    client = _get_db_client()
    try:
        db = client[os.getenv("MONGO_DB_NAME", "jobs")]
        job = db["level-2"].find_one({"_id": object_id})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    finally:
        client.close()


def _validate_tier(tier_str: str) -> ModelTier:
    """
    Validate and convert tier string to ModelTier enum.

    Args:
        tier_str: Tier string ('fast', 'balanced', 'quality')

    Returns:
        ModelTier enum value

    Raises:
        HTTPException: If tier is invalid
    """
    tier = get_tier_from_string(tier_str)
    if tier is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{tier_str}'. Must be 'fast', 'balanced', or 'quality'",
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
    operation = "structure-jd"
    run_id = _generate_run_id(operation)

    logger.info(f"[{run_id[:16]}] Starting {operation} for job {job_id}")

    try:
        # Validate inputs
        job = _validate_job_exists(job_id)
        tier = _validate_tier(request.tier)
        model = get_model_for_operation(tier, operation)

        logger.info(
            f"[{run_id[:16]}] Using tier={tier.value}, model={model}, use_llm={request.use_llm}"
        )

        # Phase 4: Actual implementation
        # For now, return stubbed success response
        estimated_cost = _estimate_operation_cost(tier, operation)

        # Stub data - Phase 4 will replace with actual extraction
        stub_data = {
            "status": "stubbed",
            "message": "Phase 4 will implement actual JD structuring",
            "job_title": job.get("title", "Unknown"),
            "company": job.get("company", "Unknown"),
            "has_jd_text": bool(job.get("jd_text") or job.get("description")),
        }

        logger.info(f"[{run_id[:16]}] Completed {operation} (stubbed)")

        return OperationResponse(
            success=True,
            data=stub_data,
            cost_usd=estimated_cost,
            run_id=run_id,
            model_used=model,
            duration_ms=100,  # Stubbed duration
        )

    except HTTPException:
        raise
    except Exception as e:
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
    - Tech stack and engineering culture
    - Role-specific requirements and expectations
    - Key people and team structure
    - Interview process insights

    Args:
        job_id: MongoDB ObjectId of the job
        request: Research request parameters

    Returns:
        OperationResponse with research data
    """
    operation = "research-company"
    run_id = _generate_run_id(operation)

    logger.info(f"[{run_id[:16]}] Starting {operation} for job {job_id}")

    try:
        # Validate inputs
        job = _validate_job_exists(job_id)
        tier = _validate_tier(request.tier)
        model = get_model_for_operation(tier, operation)

        logger.info(
            f"[{run_id[:16]}] Using tier={tier.value}, model={model}, force_refresh={request.force_refresh}"
        )

        # Phase 4: Actual implementation
        estimated_cost = _estimate_operation_cost(tier, operation)

        # Stub data - Phase 4 will replace with actual research
        stub_data = {
            "status": "stubbed",
            "message": "Phase 4 will implement actual company research",
            "company": job.get("company", "Unknown"),
            "has_existing_research": bool(job.get("company_research")),
            "force_refresh": request.force_refresh,
        }

        logger.info(f"[{run_id[:16]}] Completed {operation} (stubbed)")

        return OperationResponse(
            success=True,
            data=stub_data,
            cost_usd=estimated_cost,
            run_id=run_id,
            model_used=model,
            duration_ms=150,  # Stubbed duration
        )

    except HTTPException:
        raise
    except Exception as e:
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
    run_id = _generate_run_id(operation)

    logger.info(f"[{run_id[:16]}] Starting {operation} for job {job_id}")

    try:
        # Validate inputs
        job = _validate_job_exists(job_id)
        tier = _validate_tier(request.tier)
        model = get_model_for_operation(tier, operation)

        logger.info(
            f"[{run_id[:16]}] Using tier={tier.value}, model={model}, use_annotations={request.use_annotations}"
        )

        # Phase 4: Actual implementation
        estimated_cost = _estimate_operation_cost(tier, operation)

        # Stub data - Phase 4 will replace with actual CV generation
        stub_data = {
            "status": "stubbed",
            "message": "Phase 4 will implement actual CV generation",
            "job_title": job.get("title", "Unknown"),
            "company": job.get("company", "Unknown"),
            "has_annotations": bool(job.get("jd_annotations")),
            "use_annotations": request.use_annotations,
        }

        logger.info(f"[{run_id[:16]}] Completed {operation} (stubbed)")

        return OperationResponse(
            success=True,
            data=stub_data,
            cost_usd=estimated_cost,
            run_id=run_id,
            model_used=model,
            duration_ms=500,  # Stubbed duration
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[{run_id[:16]}] {operation} failed: {e}")
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
