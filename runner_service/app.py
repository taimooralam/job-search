"""
FastAPI runner service skeleton for the job pipeline.

Provides stub endpoints for kicking off jobs, checking status, streaming logs,
and (placeholder) artifact retrieval. Concurrency is guarded via an asyncio
semaphore to keep the number of simultaneous runs under control (default 3).

This is a scaffold: hook `_simulate_run` up to the real pipeline/docker launch
logic and wire artifact storage/serving before production use.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "3"))
LOG_BUFFER_LIMIT = int(os.getenv("LOG_BUFFER_LIMIT", "500"))

app = FastAPI(title="Pipeline Runner", version="0.1.0")


class RunJobRequest(BaseModel):
    """Request body for kicking off a single job run."""

    job_id: str = Field(..., description="Job identifier to process.")
    profile_ref: Optional[str] = Field(
        None, description="Optional profile reference/path to pass to the pipeline."
    )
    source: Optional[str] = Field(None, description="Origin of the request.")


class RunBulkRequest(BaseModel):
    """Request body for kicking off multiple job runs."""

    job_ids: List[str] = Field(..., min_items=1, description="Job identifiers to process.")
    profile_ref: Optional[str] = Field(None, description="Optional profile reference/path.")
    source: Optional[str] = Field(None, description="Origin of the request.")


class RunResponse(BaseModel):
    """Response after enqueuing a job run."""

    run_id: str
    status_url: str
    log_stream_url: str


class StatusResponse(BaseModel):
    """Status payload for a job run."""

    run_id: str
    job_id: str
    status: str
    started_at: datetime
    updated_at: datetime
    artifacts: Dict[str, str]


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


async def _simulate_run(run_id: str) -> None:
    """
    Placeholder async task that simulates a pipeline run.

    Replace this with real pipeline execution (e.g., docker run scripts/run_pipeline.py)
    and wire log forwarding + artifact paths.
    """
    try:
        _update_status(run_id, "running")
        _append_log(run_id, "Starting pipeline (stub)...")
        await asyncio.sleep(0.5)
        _append_log(run_id, "Layer 2...done (stub)")
        await asyncio.sleep(0.3)
        _append_log(run_id, "Layer 3...done (stub)")
        await asyncio.sleep(0.3)
        _append_log(run_id, "Layer 4...done (stub)")
        await asyncio.sleep(0.3)
        _append_log(run_id, "Layer 6...done (stub)")
        await asyncio.sleep(0.3)
        _append_log(run_id, "Layer 7 (output)...done (stub)")
        _update_status(
            run_id,
            "completed",
            artifacts={
                "cv_md_url": f"/artifacts/{run_id}/cv.md",
                "cv_pdf_url": f"/artifacts/{run_id}/cv.pdf",
                "dossier_pdf_url": f"/artifacts/{run_id}/dossier.pdf",
            },
        )
        _append_log(run_id, "Pipeline complete (stub).")
    except Exception as exc:  # noqa: BLE001 - capture any failure for visibility
        _append_log(run_id, f"Run failed: {exc}")
        _update_status(run_id, "failed")
    finally:
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
    background_tasks.add_task(_simulate_run, run_id)
    return run_id


@app.post("/jobs/run", response_model=RunResponse)
async def run_job(request: RunJobRequest, background_tasks: BackgroundTasks) -> RunResponse:
    """Kick off a single job run."""
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


@app.post("/jobs/run-bulk")
async def run_jobs_bulk(
    request: RunBulkRequest, background_tasks: BackgroundTasks
) -> Dict[str, List[RunResponse]]:
    """Kick off multiple job runs; each gets its own run_id."""
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


@app.get("/artifacts/{run_id}/{filename}")
async def get_artifact(run_id: str, filename: str) -> None:
    """Placeholder artifact handler; implement file serving or signed URLs here."""
    raise HTTPException(status_code=501, detail="Artifact serving not implemented yet.")
