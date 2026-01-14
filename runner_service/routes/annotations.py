"""
Annotation Suggestion Endpoints

Provides API endpoints for the self-correcting annotation suggestion system:
- Generate annotations for a job's structured JD
- Get/rebuild priors
- Capture feedback from user edits

Endpoints:
- POST /jobs/{job_id}/generate-annotations: Generate annotations for a job (async with livetail)
- GET /user/annotation-priors: Get priors stats
- POST /user/annotation-priors/rebuild: Rebuild priors from all annotations
- POST /user/annotation-feedback: Capture feedback from user edit/delete
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from .operation_streaming import (
    create_operation_run,
    create_log_callback,
    update_operation_status,
    get_operation_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["annotations"])


# In-memory storage for annotation results (keyed by run_id)
_annotation_results: Dict[str, "GenerateAnnotationsResponse"] = {}


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
        event: Event type (e.g., "annotation_start", "annotation_complete")
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


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class GenerateAnnotationsStartResponse(BaseModel):
    """Response when starting async annotation generation."""
    run_id: str
    status: str
    job_id: str


class GenerateAnnotationsResponse(BaseModel):
    """Response from generate-annotations endpoint."""
    success: bool
    created: int = 0
    skipped: int = 0
    annotations: list = Field(default_factory=list)
    error: Optional[str] = None


class AnnotationResultResponse(BaseModel):
    """Response when polling for annotation result."""
    run_id: str
    status: str  # "queued", "running", "completed", "failed"
    result: Optional[GenerateAnnotationsResponse] = None
    error: Optional[str] = None


class PriorsStatsResponse(BaseModel):
    """Response from annotation-priors endpoint."""
    success: bool
    stats: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class RebuildPriorsResponse(BaseModel):
    """Response from rebuild priors endpoint."""
    success: bool
    rebuilt: bool = False
    annotations_indexed: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None


class FeedbackTarget(BaseModel):
    """Target info from annotation for context-aware feedback."""
    section: Optional[str] = None
    text: Optional[str] = None


class ManualAnnotationValues(BaseModel):
    """Values for manually created annotations."""
    relevance: Optional[str] = None
    passion: Optional[str] = None
    identity: Optional[str] = None
    requirement_type: Optional[str] = None


class FeedbackRequest(BaseModel):
    """Request body for annotation feedback."""
    annotation_id: str
    action: str  # "save" | "delete" | "manual_create"
    original_values: Dict[str, Any] = Field(default_factory=dict)
    final_values: Optional[Dict[str, Any]] = None  # Only for "save"
    target: Optional[FeedbackTarget] = None  # For context-aware deletion
    values: Optional[ManualAnnotationValues] = None  # For "manual_create"


class FeedbackResponse(BaseModel):
    """Response from annotation feedback endpoint."""
    success: bool
    prior_updated: Optional[str] = None
    confidence_change: Optional[float] = None
    error: Optional[str] = None


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/jobs/{job_id}/generate-annotations", response_model=GenerateAnnotationsStartResponse)
async def generate_annotations(
    job_id: str,
    background_tasks: BackgroundTasks,
    sync: bool = Query(default=False, description="Run synchronously (for backward compat)"),
) -> GenerateAnnotationsStartResponse:
    """
    Generate annotations for a job's structured JD (async with real-time logging).

    This endpoint returns immediately with a run_id. Use:
    - GET /api/logs/operations/{run_id} for real-time logs via polling
    - GET /jobs/{job_id}/annotations/result/{run_id} for final result

    Generates annotations only for JD items that match the user's profile
    (skills, responsibilities, identity, passion, qualifications).

    Uses sentence embeddings and keyword priors to match against
    historical annotation patterns.

    Args:
        job_id: MongoDB ObjectId of the job
        sync: If True, run synchronously and return result directly (for backward compat)

    Returns:
        GenerateAnnotationsStartResponse with run_id for tracking
    """
    # Validate job_id format
    try:
        ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job_id format")

    # Create operation run for log streaming
    run_id = create_operation_run(job_id=job_id, operation="generate-annotations")
    log_cb = create_log_callback(run_id)

    # Start background task
    background_tasks.add_task(
        _run_annotation_generation,
        run_id=run_id,
        job_id=job_id,
        log_callback=log_cb,
    )

    return GenerateAnnotationsStartResponse(
        run_id=run_id,
        status="queued",
        job_id=job_id,
    )


async def _run_annotation_generation(
    run_id: str,
    job_id: str,
    log_callback: Callable[[str], None],
) -> None:
    """Background task for annotation generation with verbose logging."""
    import time

    try:
        update_operation_status(run_id, "running")
        start_time = time.time()

        # Emit structured start event
        _emit_structured_log(
            log_callback,
            event="annotation_start",
            message=f"Starting annotation generation for job {job_id[:12]}...",
            metadata={"job_id": job_id},
        )

        # Import here to avoid circular imports
        from src.services.annotation_suggester import generate_annotations_for_job

        _emit_structured_log(
            log_callback,
            event="annotation_processing",
            message="Loading embeddings and matching patterns...",
        )

        # Run the annotation generation
        result = generate_annotations_for_job(job_id)

        duration_ms = int((time.time() - start_time) * 1000)

        # Build response
        response = GenerateAnnotationsResponse(
            success=result.get("success", False),
            created=result.get("created", 0),
            skipped=result.get("skipped", 0),
            annotations=result.get("annotations", []),
            error=result.get("error"),
        )

        # Store result
        _annotation_results[run_id] = response

        # Mark complete with structured log
        if response.success:
            update_operation_status(run_id, "completed", result=response.model_dump())
            _emit_structured_log(
                log_callback,
                event="annotation_complete",
                message=f"Generated {response.created} annotations ({response.skipped} skipped)",
                status="success",
                duration_ms=duration_ms,
                metadata={
                    "created": response.created,
                    "skipped": response.skipped,
                    "total_annotations": len(response.annotations),
                },
            )
        else:
            update_operation_status(run_id, "failed", error=response.error)
            _emit_structured_log(
                log_callback,
                event="annotation_error",
                message=response.error or "Unknown error",
                error=response.error,
                status="error",
                duration_ms=duration_ms,
            )

    except Exception as e:
        logger.exception(f"Annotation generation failed for job {job_id}: {e}")
        update_operation_status(run_id, "failed", error=str(e))
        _emit_structured_log(
            log_callback,
            event="annotation_error",
            message=str(e),
            error=str(e),
            status="error",
        )


@router.get("/jobs/{job_id}/annotations/result/{run_id}", response_model=AnnotationResultResponse)
async def get_annotation_result(job_id: str, run_id: str) -> AnnotationResultResponse:
    """
    Get the result of an annotation generation operation.

    Args:
        job_id: MongoDB ObjectId of the job
        run_id: Operation run ID from generate-annotations

    Returns:
        AnnotationResultResponse with status and result if completed
    """
    state = get_operation_state(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")

    result = _annotation_results.get(run_id)

    return AnnotationResultResponse(
        run_id=run_id,
        status=state.status,
        result=result,
        error=state.error,
    )


@router.get("/user/annotation-priors", response_model=PriorsStatsResponse)
async def get_annotation_priors() -> PriorsStatsResponse:
    """
    Get statistics about the annotation priors.

    Returns accuracy, coverage, and health metrics for the
    annotation suggestion system.

    Returns:
        PriorsStatsResponse with priors statistics
    """
    try:
        from src.services.annotation_priors import load_priors, get_priors_stats

        priors = load_priors()
        stats = get_priors_stats(priors)

        return PriorsStatsResponse(
            success=True,
            stats=stats,
        )

    except Exception as e:
        logger.error(f"Failed to get priors stats: {e}", exc_info=True)
        return PriorsStatsResponse(
            success=False,
            error=str(e),
        )


@router.post("/user/annotation-priors/rebuild", response_model=RebuildPriorsResponse)
async def rebuild_annotation_priors() -> RebuildPriorsResponse:
    """
    Rebuild the annotation priors from all historical annotations.

    This re-computes sentence embeddings for all annotations and
    rebuilds skill priors. Takes ~15-30 seconds for 3000 annotations.

    Returns:
        RebuildPriorsResponse with rebuild status and metrics
    """
    import time

    try:
        from src.services.annotation_priors import (
            load_priors,
            rebuild_priors,
            save_priors,
        )

        logger.info("Starting priors rebuild via API")
        start_time = time.time()

        priors = load_priors()
        priors = rebuild_priors(priors)
        save_priors(priors)

        duration = time.time() - start_time
        annotations_indexed = priors.get("sentence_index", {}).get("count", 0)

        logger.info(f"Priors rebuild complete: {annotations_indexed} annotations in {duration:.1f}s")

        return RebuildPriorsResponse(
            success=True,
            rebuilt=True,
            annotations_indexed=annotations_indexed,
            duration_seconds=round(duration, 1),
        )

    except Exception as e:
        logger.error(f"Failed to rebuild priors: {e}", exc_info=True)
        return RebuildPriorsResponse(
            success=False,
            error=str(e),
        )


@router.post("/user/annotation-feedback", response_model=FeedbackResponse)
async def capture_annotation_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """
    Capture feedback from user editing or deleting an auto-generated annotation.

    This updates the skill priors based on whether the user accepted,
    edited, or deleted the suggestion.

    Args:
        request: FeedbackRequest with annotation_id, action, and values

    Returns:
        FeedbackResponse with updated prior info
    """
    try:
        from src.services.annotation_priors import (
            load_priors,
            capture_feedback,
            save_priors,
        )

        if request.action not in ("save", "delete", "manual_create"):
            raise HTTPException(
                status_code=400,
                detail="action must be 'save', 'delete', or 'manual_create'"
            )

        # Load priors
        priors = load_priors()
        old_priors = dict(priors)  # Shallow copy for comparison

        # Handle manual_create action (positive signal from user-created annotation)
        if request.action == "manual_create":
            from src.services.annotation_priors import capture_manual_annotation

            # Build manual annotation dict
            manual_annotation = {
                "id": request.annotation_id,
                "source": "manual",
                "target": {
                    "section": request.target.section if request.target else None,
                    "text": request.target.text if request.target else None,
                },
            }
            # Add user's chosen values
            if request.values:
                manual_annotation.update({
                    "relevance": request.values.relevance,
                    "passion": request.values.passion,
                    "identity": request.values.identity,
                    "requirement_type": request.values.requirement_type,
                })

            priors = capture_manual_annotation(manual_annotation, priors)
            save_priors(priors)

            return FeedbackResponse(
                success=True,
                prior_updated=f"manual:{request.target.text[:30] if request.target and request.target.text else 'unknown'}...",
            )

        # Build annotation dict from request (for save/delete actions)
        annotation = {
            "id": request.annotation_id,
            "source": "auto_generated",
            "original_values": request.original_values,
            "feedback_captured": False,
        }

        # Add target info for context-aware deletion learning
        if request.target:
            annotation["target"] = {
                "section": request.target.section,
                "text": request.target.text,
            }

        # Add final values for save action
        if request.action == "save" and request.final_values:
            annotation.update(request.final_values)

        priors = capture_feedback(annotation, request.action, priors)
        save_priors(priors)

        # Determine what changed
        prior_updated = None
        confidence_change = None

        # Find which skill was updated (simplified)
        matched_keyword = request.original_values.get("matched_keyword")
        if matched_keyword:
            prior_updated = matched_keyword
            old_conf = old_priors.get("skill_priors", {}).get(matched_keyword.lower(), {}).get("relevance", {}).get("confidence", 0.5)
            new_conf = priors.get("skill_priors", {}).get(matched_keyword.lower(), {}).get("relevance", {}).get("confidence", 0.5)
            confidence_change = round(new_conf - old_conf, 3)

        return FeedbackResponse(
            success=True,
            prior_updated=prior_updated,
            confidence_change=confidence_change,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to capture feedback: {e}", exc_info=True)
        return FeedbackResponse(
            success=False,
            error=str(e),
        )
