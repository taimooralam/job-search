"""
SSE Streaming Support for Pipeline Operations.

Provides Server-Sent Events streaming for smaller pipeline operations
(structure-jd, research-company, generate-cv) similar to how the full
pipeline streams logs.

Key Components:
- OperationState: In-memory state tracking for operation logs
- _operation_runs: Global dict for operation state
- Helper functions for log appending and SSE streaming
"""

import asyncio
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

    _operation_runs[run_id] = OperationState(
        job_id=job_id,
        operation=operation,
        status="queued",
        started_at=now,
        updated_at=now,
    )

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

    Args:
        run_id: Operation run ID

    Returns:
        StreamingResponse with SSE events
    """
    state = _operation_runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Operation run not found")

    async def event_generator() -> AsyncIterator[str]:
        last_index = 0

        while True:
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
                import json
                yield f"event: layer_status\ndata: {json.dumps(state.layer_status)}\n\n"

            # Check if operation completed
            if state.status in {"completed", "failed"}:
                # Send final result
                if state.result:
                    import json
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
