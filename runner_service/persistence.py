"""
Persistence Module

Handles MongoDB and Redis persistence for run state and job status.

Uses the repository pattern for MongoDB operations to enable
future dual-write (Atlas + VPS) support.
"""

import logging
import os
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def persist_run_to_mongo(
    job_id: str,
    run_id: str,
    status: str,
    started_at: datetime,
    updated_at: datetime,
    artifacts: Dict[str, str],
    pipeline_state: Optional[Dict] = None,
) -> None:
    """
    Update MongoDB with run status, artifact URLs, and pipeline results.

    Persists to the level-2 collection for processed jobs using the
    repository pattern for future dual-write support.

    Args:
        job_id: Job identifier (MongoDB ObjectId as string)
        run_id: Pipeline run identifier
        status: Run status (queued, running, completed, failed)
        started_at: When the run started
        updated_at: Last update timestamp
        artifacts: Dictionary of artifact URLs
        pipeline_state: Complete pipeline state with results (pain_points, fit_score, etc.)
    """
    try:
        from bson import ObjectId
        from src.common.repositories import get_job_repository

        repo = get_job_repository()

        # Convert job_id to ObjectId (new schema uses ObjectId _id)
        try:
            object_id = ObjectId(job_id)
        except Exception:
            # Fallback to string if conversion fails
            object_id = job_id

        # Build update document
        update_doc = {
            "$set": {
                "pipeline_run_id": run_id,
                "pipeline_status": status,
                "pipeline_started_at": started_at,
                "pipeline_updated_at": updated_at,
                "updatedAt": updated_at,
            }
        }

        # Only set completed_at when done
        if status in {"completed", "failed"}:
            update_doc["$set"]["pipeline_completed_at"] = updated_at

        # Update job status when pipeline completes successfully
        if status == "completed":
            update_doc["$set"]["status"] = "ready for applying"

        # Add artifact URLs if present
        if artifacts:
            update_doc["$set"]["artifact_urls"] = artifacts

        # Add pipeline results if provided (pain_points, fit_score, contacts, etc.)
        # Persist state fields when completed to capture final results
        if pipeline_state and status == "completed":
            # Extract relevant fields from pipeline state
            state_fields = {
                "pain_points": pipeline_state.get("pain_points"),
                "strategic_needs": pipeline_state.get("strategic_needs"),
                "risks_if_unfilled": pipeline_state.get("risks_if_unfilled"),
                "success_metrics": pipeline_state.get("success_metrics"),
                "fit_score": pipeline_state.get("fit_score"),
                "fit_rationale": pipeline_state.get("fit_rationale"),
                "fit_category": pipeline_state.get("fit_category"),
                "primary_contacts": pipeline_state.get("primary_contacts"),
                "secondary_contacts": pipeline_state.get("secondary_contacts"),
                "company_research": pipeline_state.get("company_research"),
                "role_research": pipeline_state.get("role_research"),
                "selected_stars": pipeline_state.get("selected_stars"),
                "star_to_pain_mapping": pipeline_state.get("star_to_pain_mapping"),
                "cover_letter": pipeline_state.get("cover_letter"),
                "cv_path": pipeline_state.get("cv_path"),
                "cv_text": pipeline_state.get("cv_text"),
                "cv_reasoning": pipeline_state.get("cv_reasoning"),
            }

            # Only add non-None values
            for key, value in state_fields.items():
                if value is not None:
                    update_doc["$set"][key] = value

        # Add boolean progress flags for UI indicators (JD/RS/CV)
        # These flags are set based on DATA PRESENCE, not just completion status.
        # This ensures the frontend indicators stay in sync with actual data,
        # even during intermediate pipeline states or partial completions.
        if pipeline_state:
            # Check if JD was processed (Layer 1-4 outputs)
            has_jd_data = bool(
                pipeline_state.get("pain_points") or pipeline_state.get("strategic_needs")
            )
            if has_jd_data:
                update_doc["$set"]["processed_jd"] = True

            # Check if research was completed (Layer 5 outputs)
            has_research_data = bool(
                pipeline_state.get("company_research") or pipeline_state.get("role_research")
            )
            if has_research_data:
                update_doc["$set"]["has_research"] = True

            # Check if CV was generated (Layer 6 outputs)
            has_cv_data = bool(
                pipeline_state.get("cv_text") or pipeline_state.get("cv_editor_state")
            )
            if has_cv_data:
                update_doc["$set"]["generated_cv"] = True

        # Update using repository (handles Atlas, later dual-write)
        result = repo.update_one(
            {"_id": object_id},
            update_doc,
            upsert=False  # Don't create if doesn't exist
        )

        if result.matched_count == 0:
            # Job not found with ObjectId, log warning
            logger.warning(f"Job {job_id} not found in level-2 collection")

    except ValueError as e:
        # MONGODB_URI not configured - skip persistence
        logger.debug(f"MongoDB not configured, skipping persistence: {e}")
    except Exception as e:
        # Log error but don't fail the run
        logger.exception(f"Failed to persist to MongoDB for job {job_id}: {e}")


def get_redis_connection():
    """
    Get Redis connection for state persistence.

    Returns None if Redis is not configured.
    """
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None

    try:
        import redis
        return redis.from_url(redis_url, decode_responses=True)
    except ImportError:
        logger.warning("redis package not installed, state persistence disabled")
        return None
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}")
        return None


def save_run_state_to_redis(run_id: str, state_data: dict) -> None:
    """
    Save run state to Redis for persistence across restarts.

    Args:
        run_id: Run identifier
        state_data: Dictionary with state information
    """
    redis_client = get_redis_connection()
    if not redis_client:
        return

    try:
        import json
        # Store as JSON with 24 hour expiry
        redis_client.setex(
            f"run:{run_id}",
            86400,  # 24 hours
            json.dumps(state_data, default=str)
        )
    except Exception as e:
        logger.warning(f"Failed to save state to Redis for run {run_id}: {e}")


def load_run_state_from_redis(run_id: str) -> Optional[dict]:
    """
    Load run state from Redis.

    Args:
        run_id: Run identifier

    Returns:
        State dictionary or None if not found
    """
    redis_client = get_redis_connection()
    if not redis_client:
        return None

    try:
        import json
        data = redis_client.get(f"run:{run_id}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Failed to load state from Redis for run {run_id}: {e}")

    return None


def update_job_pipeline_failed(job_id: str, error: str) -> None:
    """
    Update MongoDB job status to pipeline_failed.

    Called when a pipeline fails to persist the error state.
    Uses the repository pattern for future dual-write support.

    Args:
        job_id: Job identifier (MongoDB ObjectId as string)
        error: Error message describing the failure
    """
    try:
        from bson import ObjectId
        from src.common.repositories import get_job_repository

        repo = get_job_repository()

        # Convert job_id to ObjectId
        try:
            object_id = ObjectId(job_id)
        except Exception:
            object_id = job_id

        # Update the job document using repository
        result = repo.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "pipeline_status": "pipeline_failed",
                    "pipeline_error": error,
                    "pipeline_failed_at": datetime.utcnow(),
                    "updatedAt": datetime.utcnow(),
                }
            },
            upsert=False
        )

        if result.matched_count == 0:
            logger.warning(f"Job {job_id} not found when updating pipeline_failed status")
        else:
            logger.info(f"Updated job {job_id} to pipeline_failed: {error[:100]}")

    except ValueError as e:
        # MONGODB_URI not configured - skip persistence
        logger.debug(f"MongoDB not configured, skipping pipeline_failed update: {e}")
    except Exception as e:
        logger.exception(f"Failed to update pipeline_failed status for job {job_id}: {e}")
