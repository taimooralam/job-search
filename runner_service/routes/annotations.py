"""
Annotation Suggestion Endpoints

Provides API endpoints for the self-correcting annotation suggestion system:
- Generate annotations for a job's structured JD
- Get/rebuild priors
- Capture feedback from user edits

Endpoints:
- POST /jobs/{job_id}/generate-annotations: Generate annotations for a job
- GET /user/annotation-priors: Get priors stats
- POST /user/annotation-priors/rebuild: Rebuild priors from all annotations
- POST /user/annotation-feedback: Capture feedback from user edit/delete
"""

import logging
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["annotations"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class GenerateAnnotationsResponse(BaseModel):
    """Response from generate-annotations endpoint."""
    success: bool
    created: int = 0
    skipped: int = 0
    annotations: list = Field(default_factory=list)
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


class FeedbackRequest(BaseModel):
    """Request body for annotation feedback."""
    annotation_id: str
    action: str  # "save" | "delete"
    original_values: Dict[str, Any] = Field(default_factory=dict)
    final_values: Optional[Dict[str, Any]] = None  # Only for "save"


class FeedbackResponse(BaseModel):
    """Response from annotation feedback endpoint."""
    success: bool
    prior_updated: Optional[str] = None
    confidence_change: Optional[float] = None
    error: Optional[str] = None


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/jobs/{job_id}/generate-annotations", response_model=GenerateAnnotationsResponse)
async def generate_annotations(job_id: str) -> GenerateAnnotationsResponse:
    """
    Generate annotations for a job's structured JD.

    Generates annotations only for JD items that match the user's profile
    (skills, responsibilities, identity, passion, qualifications).

    Uses sentence embeddings and keyword priors to match against
    historical annotation patterns.

    Args:
        job_id: MongoDB ObjectId of the job

    Returns:
        GenerateAnnotationsResponse with created/skipped counts and annotations
    """
    try:
        # Validate job_id format
        try:
            ObjectId(job_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid job_id format")

        # Import here to avoid circular imports
        from src.services.annotation_suggester import generate_annotations_for_job

        logger.info(f"Generating annotations for job {job_id}")
        result = generate_annotations_for_job(job_id)

        return GenerateAnnotationsResponse(
            success=result.get("success", False),
            created=result.get("created", 0),
            skipped=result.get("skipped", 0),
            annotations=result.get("annotations", []),
            error=result.get("error"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate annotations: {e}", exc_info=True)
        return GenerateAnnotationsResponse(
            success=False,
            error=str(e),
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

        if request.action not in ("save", "delete"):
            raise HTTPException(
                status_code=400,
                detail="action must be 'save' or 'delete'"
            )

        # Build annotation dict from request
        annotation = {
            "id": request.annotation_id,
            "source": "auto_generated",
            "original_values": request.original_values,
            "feedback_captured": False,
        }

        # Add final values for save action
        if request.action == "save" and request.final_values:
            annotation.update(request.final_values)

        # Load priors and capture feedback
        priors = load_priors()
        old_priors = dict(priors)  # Shallow copy for comparison

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
