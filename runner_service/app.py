"""
FastAPI runner service for the job pipeline.

Provides endpoints for kicking off jobs, checking status, streaming logs,
and artifact retrieval. Concurrency is guarded via an asyncio semaphore
to keep the number of simultaneous runs under control (default 3).
"""

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    HealthResponse,
    RunBulkRequest,
    RunJobRequest,
    RunResponse,
    StatusResponse,
)
from .executor import execute_pipeline
from .persistence import persist_run_to_mongo
from .auth import verify_token


MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "3"))
LOG_BUFFER_LIMIT = int(os.getenv("LOG_BUFFER_LIMIT", "500"))

app = FastAPI(title="Pipeline Runner", version="0.1.0")

# Configure CORS
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")
if ALLOWED_ORIGINS and ALLOWED_ORIGINS[0]:  # Only add if configured
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@dataclass
class RunState:
    """In-memory tracking state for a run."""

    job_id: str
    status: str
    started_at: datetime
    updated_at: datetime
    artifacts: Dict[str, str] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)


_runs: Dict[str, RunState] = {}
_semaphore = asyncio.Semaphore(MAX_CONCURRENCY)


def _status_url(run_id: str) -> str:
    """Build relative status URL."""
    return f"/jobs/{run_id}/status"


def _log_stream_url(run_id: str) -> str:
    """Build relative log stream URL."""
    return f"/jobs/{run_id}/logs"


def _append_log(run_id: str, message: str) -> None:
    """Append a log line to the run buffer, trimming to the configured limit."""
    state = _runs.get(run_id)
    if not state:
        return
    state.logs.append(message)
    if len(state.logs) > LOG_BUFFER_LIMIT:
        # Keep the most recent portion to avoid unbounded growth.
        state.logs = state.logs[-LOG_BUFFER_LIMIT:]


def _update_status(run_id: str, status: str, artifacts: Optional[Dict[str, str]] = None) -> None:
    """Update run status and optional artifacts."""
    state = _runs.get(run_id)
    if not state:
        return
    state.status = status
    state.updated_at = datetime.utcnow()
    if artifacts:
        state.artifacts.update(artifacts)

    # Persist to MongoDB asynchronously (best effort)
    try:
        persist_run_to_mongo(
            job_id=state.job_id,
            run_id=run_id,
            status=status,
            started_at=state.started_at,
            updated_at=state.updated_at,
            artifacts=state.artifacts,
        )
    except Exception as e:
        # Log but don't fail on persistence errors
        print(f"Warning: MongoDB persistence failed: {e}")


async def _execute_pipeline_task(
    run_id: str, job_id: str, profile_ref: Optional[str]
) -> None:
    """
    Execute real pipeline as subprocess with log streaming.

    Args:
        run_id: Unique run identifier
        job_id: Job to process
        profile_ref: Optional profile path
    """
    try:
        _update_status(run_id, "running")
        _append_log(run_id, f"Starting pipeline for job {job_id}...")

        # Create log callback that captures run_id in closure
        def log_callback(message: str) -> None:
            _append_log(run_id, message)

        # Execute pipeline subprocess
        success, artifacts = await execute_pipeline(
            job_id=job_id,
            profile_ref=profile_ref,
            log_callback=log_callback,
        )

        # Update status based on result
        if success:
            _update_status(run_id, "completed", artifacts)
            _append_log(run_id, "✅ Pipeline execution complete")
        else:
            _update_status(run_id, "failed")
            _append_log(run_id, "❌ Pipeline execution failed")

    except asyncio.TimeoutError:
        _append_log(run_id, "❌ Pipeline timed out")
        _update_status(run_id, "failed")
    except Exception as exc:
        _append_log(run_id, f"❌ Unexpected error: {exc}")
        _update_status(run_id, "failed")
    finally:
        # Always release semaphore
        _semaphore.release()


async def _enqueue_run(
    job_id: str,
    profile_ref: Optional[str],
    source: Optional[str],
    background_tasks: BackgroundTasks,
) -> str:
    """Create a run record and start a background task (stub) respecting concurrency limits."""
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    acquired = await _semaphore.acquire()
    if not acquired:  # pragma: no cover - defensive; acquire returns None
        raise HTTPException(status_code=429, detail="Runner busy")

    run_id = uuid.uuid4().hex
    now = datetime.utcnow()
    _runs[run_id] = RunState(
        job_id=job_id,
        status="queued",
        started_at=now,
        updated_at=now,
        artifacts={},
    )

    _append_log(run_id, f"Run created for job {job_id} (source={source}, profile={profile_ref})")
    background_tasks.add_task(_execute_pipeline_task, run_id, job_id, profile_ref)
    return run_id


@app.post("/jobs/run", response_model=RunResponse, dependencies=[Depends(verify_token)])
async def run_job(request: RunJobRequest, background_tasks: BackgroundTasks) -> RunResponse:
    """Kick off a single job run. Requires authentication."""
    run_id = await _enqueue_run(
        job_id=request.job_id,
        profile_ref=request.profile_ref,
        source=request.source,
        background_tasks=background_tasks,
    )
    return RunResponse(
        run_id=run_id,
        status_url=_status_url(run_id),
        log_stream_url=_log_stream_url(run_id),
    )


@app.post("/jobs/run-bulk", dependencies=[Depends(verify_token)])
async def run_jobs_bulk(
    request: RunBulkRequest, background_tasks: BackgroundTasks
) -> Dict[str, List[RunResponse]]:
    """Kick off multiple job runs; each gets its own run_id. Requires authentication."""
    responses: List[RunResponse] = []
    for job_id in request.job_ids:
        run_id = await _enqueue_run(
            job_id=job_id,
            profile_ref=request.profile_ref,
            source=request.source,
            background_tasks=background_tasks,
        )
        responses.append(
            RunResponse(
                run_id=run_id,
                status_url=_status_url(run_id),
                log_stream_url=_log_stream_url(run_id),
            )
        )
    return {"runs": responses}


@app.get("/jobs/{run_id}/status", response_model=StatusResponse)
async def get_status(run_id: str) -> StatusResponse:
    """Return status for a given run_id."""
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")
    return StatusResponse(
        run_id=run_id,
        job_id=state.job_id,
        status=state.status,
        started_at=state.started_at,
        updated_at=state.updated_at,
        artifacts=state.artifacts,
    )


@app.get("/jobs/{run_id}/logs")
async def stream_logs(run_id: str) -> StreamingResponse:
    """Stream logs for a run via SSE-style events (stub, in-memory buffer)."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator() -> AsyncIterator[str]:
        last_index = 0
        while True:
            state = _runs.get(run_id)
            if not state:
                break

            logs = state.logs
            while last_index < len(logs):
                line = logs[last_index]
                last_index += 1
                yield f"data: {line}\n\n"

            if state.status in {"completed", "failed"}:
                yield f"event: end\ndata: {state.status}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint for container orchestration.

    Returns service status and capacity information.
    """
    return HealthResponse(
        status="healthy",
        active_runs=MAX_CONCURRENCY - _semaphore._value,
        max_concurrency=MAX_CONCURRENCY,
        timestamp=datetime.utcnow(),
    )


@app.get("/artifacts/{run_id}/{filename}")
async def get_artifact(run_id: str, filename: str):
    """
    Serve artifact files with path validation.

    Security:
    - Validates run_id exists
    - Ensures file path is within applications/ directory
    - Prevents path traversal attacks
    """
    from pathlib import Path
    from fastapi.responses import FileResponse

    # Verify run exists
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get job ID from state
    job_id = state.job_id

    # Construct safe path within applications directory
    applications_dir = Path("applications").resolve()

    # Search for the file in job-specific directories
    target_file = None
    for company_dir in applications_dir.iterdir():
        if not company_dir.is_dir():
            continue
        for role_dir in company_dir.iterdir():
            if not role_dir.is_dir():
                continue

            candidate_file = role_dir / filename
            if candidate_file.exists():
                # Security: Ensure file is within allowed directory
                try:
                    candidate_file.resolve().relative_to(applications_dir)
                    target_file = candidate_file
                    break
                except ValueError:
                    # File is outside applications/ directory
                    raise HTTPException(status_code=403, detail="Access denied")

        if target_file:
            break

    if not target_file or not target_file.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")

    return FileResponse(
        target_file,
        filename=filename,
        media_type="application/octet-stream"
    )
