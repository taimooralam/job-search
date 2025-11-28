"""
Persistence Module

Handles MongoDB and Redis persistence for run state and job status.
"""

import logging
import os
from datetime import datetime
from typing import Dict, Optional

from pymongo import MongoClient

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

    Persists to the level-2 collection for processed jobs.

    Args:
        job_id: Job identifier (MongoDB ObjectId as string)
        run_id: Pipeline run identifier
        status: Run status (queued, running, completed, failed)
        started_at: When the run started
        updated_at: Last update timestamp
        artifacts: Dictionary of artifact URLs
        pipeline_state: Complete pipeline state with results (pain_points, fit_score, etc.)
    """
    mongodb_uri = os.getenv("MONGODB_URI")
    if not mongodb_uri:
        # MongoDB not configured, skip persistence
        return

    try:
        from bson import ObjectId

        client = MongoClient(mongodb_uri)
        db = client["jobs"]

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

        # Update level-2 collection (processed jobs) using _id
        result = db["level-2"].update_one(
            {"_id": object_id},
            update_doc,
            upsert=False  # Don't create if doesn't exist
        )

        if result.matched_count == 0:
            # Job not found with ObjectId, log warning
            logger.warning(f"Job {job_id} not found in level-2 collection")

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
