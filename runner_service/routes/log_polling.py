"""
Log Polling Endpoint for Pipeline Operations.

Provides HTTP polling endpoint for fetching logs from Redis.
Enables the "replay + live tail" pattern:
1. Client fetches all past logs (since=0)
2. Client polls at 200ms intervals for new logs
3. On completion, client stops polling

This replaces SSE streaming for better reliability during long operations.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _parse_log_entry(log: str, index: int) -> Dict[str, Any]:
    """
    Parse a log entry string into a structured log object.

    Logs from StructuredLogger are JSON-formatted with fields like:
    - message: Human-readable log text
    - backend: LLM backend ("claude_cli" or "langchain")
    - tier: Tier level ("low", "middle", "high")
    - cost_usd: Estimated cost in USD
    - event: Event type (layer_start, llm_call_complete, etc.)

    For non-JSON logs (plain text), returns just the message.

    Args:
        log: Raw log string (may be JSON or plain text)
        index: Log index for ordering

    Returns:
        Dict with index, message, and optional backend/tier/cost_usd fields
    """
    log_obj: Dict[str, Any] = {"index": index}

    # Try to parse as JSON (structured log from StructuredLogger)
    if log.strip().startswith("{"):
        try:
            parsed = json.loads(log)

            # Build human-readable message from structured log
            # Priority: explicit message > layer event > event type
            if "message" in parsed:
                log_obj["message"] = parsed["message"]
            elif parsed.get("event") in ("layer_start", "layer_complete", "layer_error"):
                layer_name = parsed.get("layer_name", f"layer_{parsed.get('layer', '?')}")
                status = parsed.get("status", "")
                duration = parsed.get("duration_ms")
                duration_str = f" ({duration}ms)" if duration else ""
                log_obj["message"] = f"{layer_name}: {parsed['event']}{duration_str}"
            elif parsed.get("event") in ("llm_call_start", "llm_call_complete", "llm_call_error", "llm_call_fallback"):
                step = parsed.get("step_name", "llm_call")
                status = parsed.get("status", "")
                backend = parsed.get("backend", "")
                duration = parsed.get("duration_ms")
                duration_str = f" ({duration}ms)" if duration else ""
                backend_str = f" [{backend}]" if backend else ""
                log_obj["message"] = f"{step}: {status}{backend_str}{duration_str}"
            else:
                # Fallback: use event type or raw log
                log_obj["message"] = parsed.get("event", log)

            # Extract LLM attribution fields for frontend backend stats
            if parsed.get("backend"):
                log_obj["backend"] = parsed["backend"]
            if parsed.get("tier"):
                log_obj["tier"] = parsed["tier"]
            if parsed.get("cost_usd") is not None:
                log_obj["cost_usd"] = parsed["cost_usd"]

            # Include event type for frontend filtering/display
            if parsed.get("event"):
                log_obj["event"] = parsed["event"]

            # Include model info if available
            if parsed.get("model"):
                log_obj["model"] = parsed["model"]

        except json.JSONDecodeError:
            # Not valid JSON, treat as plain text
            log_obj["message"] = log
    else:
        # Plain text log
        log_obj["message"] = log

    return log_obj

# Redis key prefixes (must match operation_streaming.py)
REDIS_LOG_PREFIX = "logs:"


def _get_redis_client():
    """
    Get Redis client from queue manager (reuse existing connection).

    Returns:
        Redis client or None if unavailable
    """
    try:
        from runner_service.app import _queue_manager
        if _queue_manager and _queue_manager.is_connected:
            return _queue_manager._redis
        return None
    except ImportError:
        return None


@router.get("/{run_id}")
async def poll_logs(
    run_id: str,
    since: int = Query(0, ge=0, description="Index to start from (0 = all logs)"),
    limit: int = Query(100, ge=1, le=500, description="Max logs to return"),
) -> Dict[str, Any]:
    """
    Poll logs for a pipeline operation.

    Enables the "replay + live tail" pattern:
    - First request: since=0 to get all past logs
    - Subsequent requests: since=next_index to get only new logs
    - Poll every 200ms during active viewing for near-instant updates

    Args:
        run_id: Operation run ID (e.g., "op_generate-cv_abc123")
        since: Index to start from (0 = beginning)
        limit: Maximum logs to return per request

    Returns:
        - logs[]: Array of log entries with index and message
        - next_index: Starting index for next poll
        - total_count: Total logs available
        - status: Operation status (running/completed/failed)
        - layer_status: Layer-level progress (if available)

    Example response:
        {
            "logs": [
                {"index": 0, "message": "Starting pipeline..."},
                {"index": 1, "message": "Fetching job data..."}
            ],
            "next_index": 2,
            "total_count": 2,
            "status": "running",
            "layer_status": {"fetch_job": {"status": "success"}}
        }
    """
    redis = _get_redis_client()

    if not redis:
        raise HTTPException(
            status_code=503,
            detail="Log service unavailable (Redis not connected)"
        )

    # Build Redis keys
    logs_key = f"{REDIS_LOG_PREFIX}{run_id}:buffer"
    meta_key = f"{REDIS_LOG_PREFIX}{run_id}:meta"
    layers_key = f"{REDIS_LOG_PREFIX}{run_id}:layers"

    # Check if run exists
    exists = await redis.exists(logs_key) or await redis.exists(meta_key)
    if not exists:
        # Check in-memory state as fallback
        try:
            from runner_service.routes.operation_streaming import get_operation_state
            state = get_operation_state(run_id)
            if state:
                # Return from in-memory state (also parse for structured data)
                logs_slice = state.logs[since:since + limit]
                return {
                    "logs": [
                        _parse_log_entry(msg, since + i)
                        for i, msg in enumerate(logs_slice)
                    ],
                    "next_index": since + len(logs_slice),
                    "total_count": len(state.logs),
                    "status": state.status,
                    "layer_status": state.layer_status or {},
                    "error": state.error,
                    "langsmith_url": state.langsmith_url,
                }
        except ImportError:
            pass

        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id} not found"
        )

    # Fetch logs from Redis (LRANGE with 0-indexed bounds)
    end_index = since + limit - 1
    logs_raw = await redis.lrange(logs_key, since, end_index)

    # Parse logs (they may be bytes or strings depending on Redis encoding)
    logs: List[Dict[str, Any]] = []
    for i, log in enumerate(logs_raw):
        if isinstance(log, bytes):
            log = log.decode("utf-8")

        log_obj = _parse_log_entry(log, since + i)
        logs.append(log_obj)

    # Get total count
    total_count = await redis.llen(logs_key)

    # Get metadata
    meta = await redis.hgetall(meta_key)
    status = meta.get("status", "unknown") if meta else "unknown"
    error = meta.get("error") or None if meta else None
    langsmith_url = meta.get("langsmith_url") or None if meta else None

    # Get layer status
    layers_json = await redis.get(layers_key)
    layer_status = {}
    if layers_json:
        try:
            layer_status = json.loads(layers_json)
        except json.JSONDecodeError:
            pass

    return {
        "logs": logs,
        "next_index": since + len(logs),
        "total_count": total_count,
        "status": status,
        "layer_status": layer_status,
        "error": error,
        "langsmith_url": langsmith_url,
    }


@router.get("/{run_id}/status")
async def get_log_status(run_id: str) -> Dict[str, Any]:
    """
    Get just the status of an operation (lightweight endpoint).

    Useful for quick status checks without fetching logs.

    Args:
        run_id: Operation run ID

    Returns:
        - status: Operation status
        - layer_status: Layer-level progress
        - error: Error message if failed
    """
    redis = _get_redis_client()

    if not redis:
        raise HTTPException(
            status_code=503,
            detail="Log service unavailable (Redis not connected)"
        )

    meta_key = f"{REDIS_LOG_PREFIX}{run_id}:meta"
    layers_key = f"{REDIS_LOG_PREFIX}{run_id}:layers"

    # Check if run exists
    meta = await redis.hgetall(meta_key)

    if not meta:
        # Check in-memory state as fallback
        try:
            from runner_service.routes.operation_streaming import get_operation_state
            state = get_operation_state(run_id)
            if state:
                return {
                    "status": state.status,
                    "layer_status": state.layer_status or {},
                    "error": state.error,
                    "langsmith_url": state.langsmith_url,
                }
        except ImportError:
            pass

        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id} not found"
        )

    # Get layer status
    layers_json = await redis.get(layers_key)
    layer_status = {}
    if layers_json:
        try:
            layer_status = json.loads(layers_json)
        except json.JSONDecodeError:
            pass

    return {
        "status": meta.get("status", "unknown"),
        "layer_status": layer_status,
        "error": meta.get("error") or None,
        "langsmith_url": meta.get("langsmith_url") or None,
    }
