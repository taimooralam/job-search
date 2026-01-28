"""
SSE Streaming Support for Pipeline Operations.

Provides Server-Sent Events streaming for smaller pipeline operations
(structure-jd, research-company, generate-cv) similar to how the full
pipeline streams logs.

Key Components:
- OperationState: In-memory state tracking for operation logs
- _operation_runs: Global dict for operation state
- Redis persistence for logs with 6-hour TTL
- Helper functions for log appending and SSE streaming

Multi-Runner Support:
- Each runner has a unique ID (hostname + PID)
- Log ownership tracked via logs:owner:{run_id} Redis key
- Heartbeat mechanism for dead runner detection
"""

import asyncio
import json
import logging
import os
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

# =============================================================================
# Multi-Runner Support
# =============================================================================

# Generate unique runner ID at module load (stable for process lifetime)
_RUNNER_ID = f"{socket.gethostname()}_{os.getpid()}"

# Heartbeat configuration
HEARTBEAT_INTERVAL_SECONDS = 10
HEARTBEAT_TTL_SECONDS = 30  # Runner considered dead if no heartbeat for 30s

# Redis key prefixes for multi-runner coordination
REDIS_OWNER_PREFIX = "logs:owner:"
REDIS_HEARTBEAT_PREFIX = "runners:heartbeat:"
REDIS_ACTIVE_RUNNERS_KEY = "runners:active"


def get_runner_id() -> str:
    """Get the unique ID for this runner instance."""
    return _RUNNER_ID

# Maximum logs to keep per operation (prevents unbounded memory growth)
# CV generation produces 200-300 logs, so 1000 provides ample headroom
MAX_LOG_BUFFER = 1000

# Redis key prefixes for log persistence
REDIS_LOG_PREFIX = "logs:"
REDIS_LOG_TTL = 21600  # 6 hours in seconds


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
    # Event for reactive SSE streaming - set when new logs are appended
    log_event: Optional[asyncio.Event] = None
    # LangSmith trace URL for debugging
    langsmith_url: Optional[str] = None


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
        log_event=asyncio.Event(),  # Initialize event for reactive SSE streaming
    )
    _operation_runs[run_id] = state

    # Persist to Redis (fire-and-forget, non-blocking)
    asyncio.create_task(_persist_operation_meta_to_redis(run_id, state))

    # Set log ownership for multi-runner support
    asyncio.create_task(_set_log_owner(run_id, _RUNNER_ID))

    logger.info(f"[{run_id[:16]}] Created operation run for {operation} on job {job_id} (runner={_RUNNER_ID})")
    return run_id


def get_operation_state(run_id: str) -> Optional[OperationState]:
    """Get operation state by run ID."""
    return _operation_runs.get(run_id)


def _is_main_thread_loop() -> bool:
    """
    Check if we're running in the main event loop thread.

    Returns True if:
    - There's a running event loop in this thread
    - It matches the stored main loop

    Returns False if we're in a worker thread (e.g., ThreadPoolExecutor).
    """
    try:
        current_loop = asyncio.get_running_loop()
        # Import here to avoid circular imports
        from runner_service.app import get_main_loop
        main_loop = get_main_loop()
        return main_loop is not None and current_loop is main_loop
    except RuntimeError:
        # No running loop in this thread = we're in a worker thread
        return False


def _schedule_async_task(coro) -> None:
    """
    Schedule an async coroutine for execution in a thread-safe manner.

    Works from both the main event loop thread and worker threads.
    """
    if _is_main_thread_loop():
        asyncio.create_task(coro)
    else:
        from runner_service.app import get_main_loop
        main_loop = get_main_loop()
        if main_loop and not main_loop.is_closed():
            asyncio.run_coroutine_threadsafe(coro, main_loop)


def _signal_log_event(state: OperationState) -> None:
    """
    Signal the log_event in a thread-safe manner.

    Works from both the main event loop thread and worker threads.
    """
    if not state.log_event:
        return

    if _is_main_thread_loop():
        state.log_event.set()
    else:
        from runner_service.app import get_main_loop
        main_loop = get_main_loop()
        if main_loop and not main_loop.is_closed():
            main_loop.call_soon_threadsafe(state.log_event.set)


def append_operation_log(run_id: str, message: str) -> None:
    """
    Append a log message to an operation run.

    Thread-safe: Works correctly when called from either:
    - The main event loop thread (FastAPI handlers, background tasks)
    - Worker threads (ThreadPoolExecutor running blocking operations)

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

    # Signal SSE generator that new logs are available (reactive streaming)
    _signal_log_event(state)

    # Persist to Redis (fire-and-forget, non-blocking)
    _schedule_async_task(_persist_log_to_redis(run_id, message))


async def _update_operation_status_async(
    run_id: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """
    Async implementation of operation status update.

    When status is "completed" or "failed", flushes all in-memory logs to Redis
    BEFORE updating status. This ensures cross-runner log fetching works correctly.
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

    # Signal SSE generator that status changed (for immediate completion notification)
    _signal_log_event(state)

    # On completion/failure: flush ALL logs to Redis before updating status
    # This fixes the race condition where fire-and-forget writes haven't completed
    if status in {"completed", "failed"}:
        # Flush logs synchronously (await) to ensure they're in Redis
        await _flush_all_logs_to_redis(run_id, state.logs.copy())

    # Persist status update to Redis
    expected_log_count = len(state.logs) if status in {"completed", "failed"} else None
    await _persist_operation_meta_to_redis(run_id, state, expected_log_count)

    # Set TTL on completion/failure (logs expire after 24 hours)
    if status in {"completed", "failed"}:
        await _set_redis_log_ttl(run_id)


def update_operation_status(
    run_id: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """
    Update operation status.

    Thread-safe: Works from both the main event loop and worker threads.

    When status is "completed" or "failed", this function ensures ALL in-memory
    logs are flushed to Redis BEFORE the status is updated. This eliminates the
    race condition where a different runner might see status="completed" but
    logs haven't been persisted yet.

    Args:
        run_id: Operation run ID
        status: New status (running, completed, failed)
        result: Optional result data on completion
        error: Optional error message on failure
    """
    # Schedule the async implementation
    coro = _update_operation_status_async(run_id, status, result, error)

    if _is_main_thread_loop():
        asyncio.create_task(coro)
    else:
        from runner_service.app import get_main_loop
        main_loop = get_main_loop()
        if main_loop and not main_loop.is_closed():
            # For completion status, we want to wait for the flush to complete
            # Use run_coroutine_threadsafe and wait for the result
            if status in {"completed", "failed"}:
                future = asyncio.run_coroutine_threadsafe(coro, main_loop)
                try:
                    # Wait up to 10 seconds for flush to complete
                    future.result(timeout=10.0)
                except Exception as e:
                    logger.warning(f"[{run_id[:16]}] Status update failed to await: {e}")
            else:
                asyncio.run_coroutine_threadsafe(coro, main_loop)


def update_layer_status(
    run_id: str,
    layer_key: str,
    status: str,
    message: Optional[str] = None,
) -> None:
    """
    Update layer-level progress for an operation.

    Thread-safe: Works from both the main event loop and worker threads.

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
    _schedule_async_task(_persist_layer_status_to_redis(run_id, state.layer_status))


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


def create_layer_callback(run_id: str) -> Callable[[str, str, Optional[str], Optional[Dict]], None]:
    """
    Create a layer status callback function bound to a specific run ID.

    Args:
        run_id: Operation run ID

    Returns:
        Callback function that updates layer status
    """
    def callback(
        layer_key: str,
        status: str,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        update_layer_status(run_id, layer_key, status, message)
        # Also append a log message for the layer transition
        status_emoji = {
            "pending": "⏳",
            "processing": "🔄",
            "success": "✅",
            "failed": "❌",
            "error": "❌",  # For structured error events from orchestrator
            "skipped": "⏭️",
        }.get(status, "•")

        # For errors, emit structured log with traceback if provided
        if status in {"failed", "error"} and metadata:
            # Build structured error log for frontend parsing
            structured_log = {
                "event": "layer_error",
                "layer_key": layer_key,
                "message": message or status,
                "metadata": metadata,
            }
            log_msg = f"{status_emoji} {layer_key}: {json.dumps(structured_log)}"
        else:
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

            # Reactive wait: block until new logs arrive OR timeout for status checks
            # This eliminates the 100ms polling delay - logs appear instantly
            if state.log_event:
                try:
                    await asyncio.wait_for(state.log_event.wait(), timeout=0.5)
                    state.log_event.clear()  # Reset for next batch of logs
                except asyncio.TimeoutError:
                    pass  # Timeout is normal - check status and continue
            else:
                # Fallback to polling if no event (e.g., Redis-restored state)
                await asyncio.sleep(0.1)

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
# Redis Log Persistence (6-hour TTL)
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


async def _flush_all_logs_to_redis(run_id: str, logs: List[str]) -> bool:
    """
    Flush ALL in-memory logs to Redis atomically.

    Called when operation completes/fails to ensure all logs are in Redis
    before the status is updated. This fixes the race condition where
    fire-and-forget log persistence might not complete before a different
    runner tries to fetch logs.

    Args:
        run_id: Operation run ID
        logs: Complete list of in-memory logs to persist

    Returns:
        True if flush succeeded, False otherwise
    """
    if not logs:
        return True

    try:
        redis = _get_redis_client()
        if not redis:
            logger.warning(f"[{run_id[:16]}] No Redis client for log flush")
            return False

        key = f"{REDIS_LOG_PREFIX}{run_id}:buffer"

        # Delete existing buffer and write all logs atomically using pipeline
        pipe = redis.pipeline()
        pipe.delete(key)
        for log in logs:
            pipe.rpush(key, log)
        await pipe.execute()

        logger.debug(f"[{run_id[:16]}] Flushed {len(logs)} logs to Redis")
        return True

    except Exception as e:
        logger.error(f"[{run_id[:16]}] Failed to flush logs to Redis: {e}")
        return False


async def _persist_operation_meta_to_redis(
    run_id: str,
    state: OperationState,
    expected_log_count: Optional[int] = None,
) -> None:
    """
    Persist operation metadata to Redis.

    Args:
        run_id: Operation run ID
        state: Operation state to persist
        expected_log_count: Total number of logs expected (set on completion/failure).
            This fixes a race condition where logs are persisted async, so the frontend
            might poll before all logs are in Redis. By including the expected count
            in metadata, the frontend knows to wait until it has fetched all logs.
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
            "langsmith_url": state.langsmith_url or "",
        }

        # Include expected_log_count when completing/failing
        # This tells the frontend how many logs to expect before stopping
        if expected_log_count is not None:
            meta["expected_log_count"] = str(expected_log_count)

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

        logger.debug(f"[{run_id[:16]}] Set 6h TTL on Redis logs")

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
        raw_meta = await redis.hgetall(meta_key)
        if not raw_meta:
            return None

        # Decode bytes to strings (redis-py returns bytes by default)
        meta = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw_meta.items()
        }

        # Get logs
        logs_key = f"{REDIS_LOG_PREFIX}{run_id}:buffer"
        logs = await redis.lrange(logs_key, 0, -1)

        # Get layer status
        layers_key = f"{REDIS_LOG_PREFIX}{run_id}:layers"
        layers_json = await redis.get(layers_key)
        # Decode bytes if needed
        if isinstance(layers_json, bytes):
            layers_json = layers_json.decode()
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
            langsmith_url=meta.get("langsmith_url") or None,
        )

        # Cache in memory for faster subsequent access
        _operation_runs[run_id] = state

        logger.info(f"[{run_id[:16]}] Restored operation state from Redis")
        return state

    except Exception as e:
        logger.warning(f"[{run_id[:16]}] Failed to restore from Redis: {e}")
        return None


# =============================================================================
# Multi-Runner Log Ownership & Heartbeat
# =============================================================================


async def _set_log_owner(run_id: str, runner_id: str) -> None:
    """
    Set this runner as the owner of logs for the given run_id.

    This enables log routing in multi-runner deployments: when a client
    polls for logs, the system can serve from in-memory (if we own it)
    or from Redis (if another runner owns it).

    Args:
        run_id: Operation run ID
        runner_id: This runner's unique ID
    """
    try:
        redis = _get_redis_client()
        if not redis:
            return

        key = f"{REDIS_OWNER_PREFIX}{run_id}"
        # Set owner with 24-hour TTL (matches log TTL)
        await redis.setex(key, 86400, runner_id)
        logger.debug(f"[{run_id[:16]}] Set log owner to {runner_id}")

    except Exception as e:
        logger.debug(f"[{run_id[:16]}] Failed to set log owner: {e}")


async def get_log_owner(run_id: str) -> Optional[str]:
    """
    Get the runner ID that owns logs for the given run_id.

    Args:
        run_id: Operation run ID

    Returns:
        Runner ID string or None if not found/expired
    """
    try:
        redis = _get_redis_client()
        if not redis:
            return None

        key = f"{REDIS_OWNER_PREFIX}{run_id}"
        owner = await redis.get(key)
        if owner:
            return owner if isinstance(owner, str) else owner.decode()
        return None

    except Exception as e:
        logger.debug(f"[{run_id[:16]}] Failed to get log owner: {e}")
        return None


def is_log_owner(run_id: str) -> bool:
    """
    Check if this runner owns the logs for the given run_id (sync, in-memory check).

    This is a fast check that doesn't hit Redis - it just checks if the run
    exists in our in-memory state, which means we created it.

    Args:
        run_id: Operation run ID

    Returns:
        True if this runner owns the logs
    """
    return run_id in _operation_runs


async def send_heartbeat() -> None:
    """
    Send a heartbeat to Redis indicating this runner is alive.

    Called periodically by the heartbeat loop in app.py.
    """
    try:
        redis = _get_redis_client()
        if not redis:
            return

        # Set heartbeat with TTL
        heartbeat_key = f"{REDIS_HEARTBEAT_PREFIX}{_RUNNER_ID}"
        await redis.setex(heartbeat_key, HEARTBEAT_TTL_SECONDS, "alive")

        # Add to active runners set
        await redis.sadd(REDIS_ACTIVE_RUNNERS_KEY, _RUNNER_ID)

        logger.debug(f"Heartbeat sent for runner {_RUNNER_ID}")

    except Exception as e:
        logger.warning(f"Heartbeat send failed: {e}")


async def remove_runner_from_active() -> None:
    """
    Remove this runner from the active runners set on shutdown.
    """
    try:
        redis = _get_redis_client()
        if not redis:
            return

        # Remove from active set
        await redis.srem(REDIS_ACTIVE_RUNNERS_KEY, _RUNNER_ID)

        # Delete heartbeat key
        heartbeat_key = f"{REDIS_HEARTBEAT_PREFIX}{_RUNNER_ID}"
        await redis.delete(heartbeat_key)

        logger.info(f"Runner {_RUNNER_ID} removed from active set")

    except Exception as e:
        logger.warning(f"Failed to remove runner from active set: {e}")


async def get_active_runners() -> List[str]:
    """
    Get list of active runner IDs.

    Returns:
        List of runner ID strings
    """
    try:
        redis = _get_redis_client()
        if not redis:
            return [_RUNNER_ID]  # Just us if no Redis

        members = await redis.smembers(REDIS_ACTIVE_RUNNERS_KEY)
        return [m if isinstance(m, str) else m.decode() for m in members]

    except Exception as e:
        logger.warning(f"Failed to get active runners: {e}")
        return [_RUNNER_ID]


async def check_runner_alive(runner_id: str) -> bool:
    """
    Check if a specific runner is alive (has recent heartbeat).

    Args:
        runner_id: Runner ID to check

    Returns:
        True if runner has a valid heartbeat
    """
    try:
        redis = _get_redis_client()
        if not redis:
            return runner_id == _RUNNER_ID  # Only we exist if no Redis

        heartbeat_key = f"{REDIS_HEARTBEAT_PREFIX}{runner_id}"
        return await redis.exists(heartbeat_key) > 0

    except Exception as e:
        logger.warning(f"Failed to check runner heartbeat: {e}")
        return False
