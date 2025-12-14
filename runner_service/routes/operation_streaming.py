"""
SSE Streaming Support for Pipeline Operations.

Provides Server-Sent Events streaming for smaller pipeline operations
(structure-jd, research-company, generate-cv) similar to how the full
pipeline streams logs.

Key Components:
- OperationState: In-memory state tracking for operation logs
- _operation_runs: Global dict for operation state
- Redis persistence for logs with 24-hour TTL
- Helper functions for log appending and SSE streaming
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

# Maximum logs to keep per operation (prevents unbounded memory growth)
MAX_LOG_BUFFER = 100

# Redis key prefixes for log persistence
REDIS_LOG_PREFIX = "logs:"
REDIS_LOG_TTL = 86400  # 24 hours in seconds


@dataclass
class OperationState:
    """In-memory state for a single operation run."""

    job_id: str
    operation: str
    status: str  # queued, running, completed, failed
    started_at: datetime
    updated_at: datetime
    logs: List[str] = field(default_factory=list)
    layer_status: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    current_layer: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# Global operation state storage (in-memory, similar to _runs in app.py)
_operation_runs: Dict[str, OperationState] = {}


def create_operation_run(job_id: str, operation: str) -> str:
    """
    Create a new operation run and return its ID.

    Args:
        job_id: MongoDB job ID
        operation: Operation name (structure-jd, research-company, generate-cv)

    Returns:
        Unique run ID
    """
    run_id = f"op_{operation}_{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow()

    state = OperationState(
        job_id=job_id,
        operation=operation,
        status="queued",
        started_at=now,
        updated_at=now,
    )
    _operation_runs[run_id] = state

    # Persist to Redis (fire-and-forget, non-blocking)
    asyncio.create_task(_persist_operation_meta_to_redis(run_id, state))

    logger.info(f"[{run_id[:16]}] Created operation run for {operation} on job {job_id}")
    return run_id


def get_operation_state(run_id: str) -> Optional[OperationState]:
    """Get operation state by run ID."""
    return _operation_runs.get(run_id)


def append_operation_log(run_id: str, message: str) -> None:
    """
    Append a log message to an operation run.

    Args:
        run_id: Operation run ID
        message: Log message to append
    """
    state = _operation_runs.get(run_id)
    if not state:
        return

    state.logs.append(message)
    state.updated_at = datetime.utcnow()

    # Trim logs if exceeding buffer limit
    if len(state.logs) > MAX_LOG_BUFFER:
        state.logs = state.logs[-MAX_LOG_BUFFER:]

    # Persist to Redis (fire-and-forget, non-blocking)
    asyncio.create_task(_persist_log_to_redis(run_id, message))


def update_operation_status(
    run_id: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """
    Update operation status.

    Args:
        run_id: Operation run ID
        status: New status (running, completed, failed)
        result: Optional result data on completion
        error: Optional error message on failure
    """
    state = _operation_runs.get(run_id)
    if not state:
        return

    state.status = status
    state.updated_at = datetime.utcnow()

    if result is not None:
        state.result = result
    if error is not None:
        state.error = error

    # Persist status update to Redis
    asyncio.create_task(_persist_operation_meta_to_redis(run_id, state))

    # Set TTL on completion/failure (logs expire after 24 hours)
    if status in {"completed", "failed"}:
        asyncio.create_task(_set_redis_log_ttl(run_id))


def update_layer_status(
    run_id: str,
    layer_key: str,
    status: str,
    message: Optional[str] = None,
) -> None:
    """
    Update layer-level progress for an operation.

    Args:
        run_id: Operation run ID
        layer_key: Layer identifier (e.g., 'fetch_job', 'company_research')
        status: Layer status ('pending', 'processing', 'success', 'failed')
        message: Optional status message
    """
    state = _operation_runs.get(run_id)
    if not state:
        return

    state.layer_status[layer_key] = {
        "status": status,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }
    state.current_layer = layer_key if status == "processing" else state.current_layer
    state.updated_at = datetime.utcnow()

    # Persist layer status to Redis (fire-and-forget, non-blocking)
    asyncio.create_task(_persist_layer_status_to_redis(run_id, state.layer_status))


def create_log_callback(run_id: str) -> Callable[[str], None]:
    """
    Create a log callback function bound to a specific run ID.

    Args:
        run_id: Operation run ID

    Returns:
        Callback function that appends logs to the run
    """
    def callback(message: str) -> None:
        append_operation_log(run_id, message)
    return callback


def create_layer_callback(run_id: str) -> Callable[[str, str, Optional[str]], None]:
    """
    Create a layer status callback function bound to a specific run ID.

    Args:
        run_id: Operation run ID

    Returns:
        Callback function that updates layer status
    """
    def callback(layer_key: str, status: str, message: Optional[str] = None) -> None:
        update_layer_status(run_id, layer_key, status, message)
        # Also append a log message for the layer transition
        status_emoji = {
            "pending": "⏳",
            "processing": "🔄",
            "success": "✅",
            "failed": "❌",
            "skipped": "⏭️",
        }.get(status, "•")
        log_msg = f"{status_emoji} {layer_key}: {message or status}"
        append_operation_log(run_id, log_msg)
    return callback


async def stream_operation_logs(run_id: str) -> StreamingResponse:
    """
    Stream logs for an operation via SSE.

    This mimics the full pipeline's /jobs/{run_id}/logs endpoint
    but for smaller operations.

    Fallback order:
    1. In-memory state (for active/recent operations)
    2. Redis persisted state (for operations after restart, up to 24h TTL)

    Args:
        run_id: Operation run ID

    Returns:
        StreamingResponse with SSE events
    """
    # First try in-memory state
    state = _operation_runs.get(run_id)

    # Fallback to Redis if not in memory (e.g., after runner restart)
    if not state:
        state = await get_operation_state_from_redis(run_id)

    if not state:
        raise HTTPException(status_code=404, detail="Operation run not found")

    async def event_generator() -> AsyncIterator[str]:
        last_index = 0

        while True:
            # Check memory first, then Redis fallback (state cached in memory after first Redis fetch)
            state = _operation_runs.get(run_id)
            if not state:
                yield f"event: error\ndata: Run not found\n\n"
                break

            # Yield any new logs
            logs = state.logs
            while last_index < len(logs):
                line = logs[last_index]
                last_index += 1
                yield f"data: {line}\n\n"

            # Yield layer status updates as special events
            if state.layer_status:
                yield f"event: layer_status\ndata: {json.dumps(state.layer_status)}\n\n"

            # Check if operation completed
            if state.status in {"completed", "failed"}:
                # Send final result
                if state.result:
                    yield f"event: result\ndata: {json.dumps(state.result)}\n\n"

                yield f"event: end\ndata: {state.status}\n\n"
                break

            await asyncio.sleep(0.1)  # 100ms poll interval for responsive updates

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


def cleanup_old_runs(max_age_seconds: int = 3600) -> int:
    """
    Clean up operation runs older than max_age_seconds.

    Call periodically to prevent memory leaks.

    Args:
        max_age_seconds: Maximum age of runs to keep (default 1 hour)

    Returns:
        Number of runs cleaned up
    """
    now = datetime.utcnow()
    to_remove = []

    for run_id, state in _operation_runs.items():
        age = (now - state.updated_at).total_seconds()
        if age > max_age_seconds and state.status in {"completed", "failed"}:
            to_remove.append(run_id)

    for run_id in to_remove:
        del _operation_runs[run_id]

    if to_remove:
        logger.info(f"Cleaned up {len(to_remove)} old operation runs")

    return len(to_remove)


# =============================================================================
# Redis Log Persistence (24-hour TTL)
# =============================================================================


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


async def _persist_log_to_redis(run_id: str, message: str) -> None:
    """
    Persist a log message to Redis (non-blocking, best-effort).

    Args:
        run_id: Operation run ID
        message: Log message to persist
    """
    try:
        redis = _get_redis_client()
        if not redis:
            return

        key = f"{REDIS_LOG_PREFIX}{run_id}:buffer"
        await redis.rpush(key, message)

        # Trim to max buffer size
        await redis.ltrim(key, -MAX_LOG_BUFFER, -1)

    except Exception as e:
        # Don't fail operation if Redis write fails
        logger.debug(f"[{run_id[:16]}] Redis log persist failed: {e}")


async def _persist_operation_meta_to_redis(run_id: str, state: OperationState) -> None:
    """
    Persist operation metadata to Redis.

    Args:
        run_id: Operation run ID
        state: Operation state to persist
    """
    try:
        redis = _get_redis_client()
        if not redis:
            return

        key = f"{REDIS_LOG_PREFIX}{run_id}:meta"
        meta = {
            "job_id": state.job_id,
            "operation": state.operation,
            "status": state.status,
            "started_at": state.started_at.isoformat(),
            "updated_at": state.updated_at.isoformat(),
            "error": state.error or "",
        }
        await redis.hset(key, mapping=meta)

    except Exception as e:
        logger.debug(f"[{run_id[:16]}] Redis meta persist failed: {e}")


async def _persist_layer_status_to_redis(run_id: str, layer_status: Dict[str, Any]) -> None:
    """
    Persist layer status to Redis.

    Args:
        run_id: Operation run ID
        layer_status: Layer status dict to persist
    """
    try:
        redis = _get_redis_client()
        if not redis:
            return

        key = f"{REDIS_LOG_PREFIX}{run_id}:layers"
        await redis.set(key, json.dumps(layer_status))

    except Exception as e:
        logger.debug(f"[{run_id[:16]}] Redis layer status persist failed: {e}")


async def _set_redis_log_ttl(run_id: str) -> None:
    """
    Set 24-hour TTL on all Redis keys for a run (called on completion).

    Args:
        run_id: Operation run ID
    """
    try:
        redis = _get_redis_client()
        if not redis:
            return

        # Set TTL on all keys for this run
        keys = [
            f"{REDIS_LOG_PREFIX}{run_id}:buffer",
            f"{REDIS_LOG_PREFIX}{run_id}:meta",
            f"{REDIS_LOG_PREFIX}{run_id}:layers",
        ]
        for key in keys:
            await redis.expire(key, REDIS_LOG_TTL)

        logger.debug(f"[{run_id[:16]}] Set 24h TTL on Redis logs")

    except Exception as e:
        logger.debug(f"[{run_id[:16]}] Redis TTL set failed: {e}")


async def get_operation_state_from_redis(run_id: str) -> Optional[OperationState]:
    """
    Restore operation state from Redis if not in memory.

    This is called when a client requests logs for a run that's
    not in memory (e.g., after runner restart).

    Args:
        run_id: Operation run ID

    Returns:
        OperationState or None if not found
    """
    try:
        redis = _get_redis_client()
        if not redis:
            return None

        # Get metadata
        meta_key = f"{REDIS_LOG_PREFIX}{run_id}:meta"
        meta = await redis.hgetall(meta_key)
        if not meta:
            return None

        # Get logs
        logs_key = f"{REDIS_LOG_PREFIX}{run_id}:buffer"
        logs = await redis.lrange(logs_key, 0, -1)

        # Get layer status
        layers_key = f"{REDIS_LOG_PREFIX}{run_id}:layers"
        layers_json = await redis.get(layers_key)
        layer_status = json.loads(layers_json) if layers_json else {}

        # Reconstruct state
        def parse_datetime(value: str) -> datetime:
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                return datetime.utcnow()

        state = OperationState(
            job_id=meta.get("job_id", ""),
            operation=meta.get("operation", ""),
            status=meta.get("status", "completed"),
            started_at=parse_datetime(meta.get("started_at", "")),
            updated_at=parse_datetime(meta.get("updated_at", "")),
            logs=[log if isinstance(log, str) else log.decode() for log in logs],
            layer_status=layer_status,
            error=meta.get("error") or None,
        )

        # Cache in memory for faster subsequent access
        _operation_runs[run_id] = state

        logger.info(f"[{run_id[:16]}] Restored operation state from Redis")
        return state

    except Exception as e:
        logger.warning(f"[{run_id[:16]}] Failed to restore from Redis: {e}")
        return None
