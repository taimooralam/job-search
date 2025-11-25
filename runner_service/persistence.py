"""
Persistence Module

Handles MongoDB and Redis persistence for run state and job status.
"""

import os
from datetime import datetime
from typing import Dict, Optional

from pymongo import MongoClient


def persist_run_to_mongo(
    job_id: str,
    run_id: str,
    status: str,
    started_at: datetime,
    updated_at: datetime,
    artifacts: Dict[str, str],
) -> None:
    """
    Update MongoDB with run status and artifact URLs.

    Persists to the level-2 collection for processed jobs.

    Args:
        job_id: Job identifier
        run_id: Pipeline run identifier
        status: Run status (queued, running, completed, failed)
        started_at: When the run started
        updated_at: Last update timestamp
        artifacts: Dictionary of artifact URLs
    """
    mongodb_uri = os.getenv("MONGODB_URI")
    if not mongodb_uri:
        # MongoDB not configured, skip persistence
        return

    try:
        client = MongoClient(mongodb_uri)
        db = client["jobs"]

        # Convert job_id to int if possible (schema uses int jobId)
        try:
            job_id_int = int(job_id)
        except ValueError:
            job_id_int = job_id

        # Build update document
        update_doc = {
            "$set": {
                "pipeline_run_id": run_id,
                "pipeline_status": status,
                "pipeline_started_at": started_at,
                "pipeline_updated_at": updated_at,
            }
        }

        # Only set completed_at when done
        if status in {"completed", "failed"}:
            update_doc["$set"]["pipeline_completed_at"] = updated_at

        # Add artifact URLs if present
        if artifacts:
            update_doc["$set"]["artifact_urls"] = artifacts

        # Update level-2 collection (processed jobs)
        result = db["level-2"].update_one(
            {"jobId": job_id_int},
            update_doc,
            upsert=False  # Don't create if doesn't exist
        )

        if result.matched_count == 0:
            # Job not in level-2, might be in level-1
            # For now, we only update level-2 jobs
            pass

    except Exception as e:
        # Log error but don't fail the run
        print(f"Warning: Failed to persist to MongoDB: {e}")


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
        print("Warning: redis package not installed, state persistence disabled")
        return None
    except Exception as e:
        print(f"Warning: Failed to connect to Redis: {e}")
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
        print(f"Warning: Failed to save state to Redis: {e}")


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
        print(f"Warning: Failed to load state from Redis: {e}")

    return None
