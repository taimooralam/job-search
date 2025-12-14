"""
FastAPI runner service for the job pipeline.

Provides endpoints for kicking off jobs, checking status, streaming logs,
and artifact retrieval. Concurrency is guarded via an asyncio semaphore
to keep the number of simultaneous runs under control (default 3).
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from io import BytesIO

from .models import (
    FireCrawlCreditsResponse,
    HealthResponse,
    LayerProgress,
    LinkedInImportRequest,
    LinkedInImportResponse,
    OpenRouterCreditsResponse,
    PipelineProgressResponse,
    PIPELINE_LAYERS,
    RunBulkRequest,
    RunJobRequest,
    RunResponse,
    StatusResponse,
)
from .executor import execute_pipeline
from .persistence import persist_run_to_mongo
from .auth import verify_token, verify_websocket_token
from .config import settings, validate_config_on_startup
from .routes import operations_router, contacts_router, master_cv_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Validate configuration at startup
validate_config_on_startup()

# Use validated settings (replaces raw os.getenv calls)
MAX_CONCURRENCY = settings.max_concurrency
LOG_BUFFER_LIMIT = settings.log_buffer_limit

app = FastAPI(title="Pipeline Runner", version="0.1.0")

# Configure CORS using validated settings
if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include modular route handlers
app.include_router(operations_router)
app.include_router(contacts_router)
app.include_router(master_cv_router)


@dataclass
class RunState:
    """In-memory tracking state for a run."""

    job_id: str
    status: str
    started_at: datetime
    updated_at: datetime
    artifacts: Dict[str, str] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)
    # Layer-level progress tracking (Gap #25)
    layers: Dict[str, Dict] = field(default_factory=dict)
    current_layer: Optional[str] = None


_runs: Dict[str, RunState] = {}
_processes: Dict[str, asyncio.subprocess.Process] = {}  # Track subprocesses for cancellation
_semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

# Queue management (Redis-backed, optional)
_queue_manager: Optional["QueueManager"] = None
_ws_manager: Optional["QueueWebSocketManager"] = None


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


def _update_status(
    run_id: str,
    status: str,
    artifacts: Optional[Dict[str, str]] = None,
    pipeline_state: Optional[Dict] = None
) -> None:
    """Update run status, optional artifacts, and pipeline state."""
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
            pipeline_state=pipeline_state,
        )
        logger.debug(f"[{run_id[:8]}] Persisted state to MongoDB (status={status})")
    except Exception as e:
        # Log but don't fail on persistence errors
        logger.error(f"[{run_id[:8]}] MongoDB persistence failed: {e}")


async def _execute_pipeline_task(
    run_id: str,
    job_id: str,
    profile_ref: Optional[str],
    processing_tier: Optional[str] = "auto",
    queue_id: Optional[str] = None,
) -> None:
    """
    Execute real pipeline as subprocess with log streaming.

    Args:
        run_id: Unique run identifier
        job_id: Job to process
        profile_ref: Optional profile path
        processing_tier: Processing tier (auto, A, B, C, D) - GAP-045
        queue_id: Queue item ID (if queue manager is enabled)
    """
    error_message = None

    try:
        logger.info(f"[{run_id[:8]}] Starting pipeline task for job {job_id} (tier={processing_tier})")
        _update_status(run_id, "running")
        _append_log(run_id, f"Starting pipeline for job {job_id} (tier={processing_tier})...")

        # Create log callback that captures run_id in closure
        def log_callback(message: str) -> None:
            _append_log(run_id, message)

        # Create process callback to register subprocess for cancellation
        def process_callback(process: asyncio.subprocess.Process) -> None:
            _processes[run_id] = process
            logger.debug(f"[{run_id[:8]}] Registered process {process.pid} for cancellation")

        # Execute pipeline subprocess
        success, artifacts, pipeline_state = await execute_pipeline(
            job_id=job_id,
            profile_ref=profile_ref,
            log_callback=log_callback,
            processing_tier=processing_tier,
            process_callback=process_callback,
        )

        # Check if cancelled during execution (don't update status or persist)
        state = _runs.get(run_id)
        if state and state.status == "cancelled":
            logger.info(f"[{run_id[:8]}] Pipeline was cancelled, skipping status update")
            return

        # Update status based on result
        if success:
            logger.info(f"[{run_id[:8]}] Pipeline completed successfully for job {job_id}")
            _update_status(run_id, "completed", artifacts, pipeline_state)
            _append_log(run_id, "✅ Pipeline execution complete")

            # Update queue item as completed
            if queue_id and _queue_manager:
                await _queue_manager.complete(queue_id, success=True)
        else:
            error_message = "Pipeline execution failed"
            logger.warning(f"[{run_id[:8]}] Pipeline failed for job {job_id}")
            _update_status(run_id, "failed")
            _append_log(run_id, "❌ Pipeline execution failed")

    except asyncio.TimeoutError:
        error_message = "Pipeline timed out"
        logger.error(f"[{run_id[:8]}] Pipeline timed out for job {job_id}")
        _append_log(run_id, "❌ Pipeline timed out")
        _update_status(run_id, "failed")
    except Exception as exc:
        error_message = str(exc)
        logger.exception(f"[{run_id[:8]}] Unexpected error for job {job_id}: {exc}")
        _append_log(run_id, f"❌ Unexpected error: {exc}")
        _update_status(run_id, "failed")
    finally:
        # Clean up process reference
        _processes.pop(run_id, None)

        # Update queue item as failed if there was an error
        if error_message and queue_id and _queue_manager:
            try:
                await _queue_manager.complete(queue_id, success=False, error=error_message)
                # Also update MongoDB to mark job as pipeline_failed
                from .persistence import update_job_pipeline_failed
                update_job_pipeline_failed(job_id, error_message)
            except Exception as e:
                logger.warning(f"[{run_id[:8]}] Failed to update queue item: {e}")

        # Always release semaphore (unless already released by cancel)
        try:
            _semaphore.release()
            logger.debug(f"[{run_id[:8]}] Released semaphore")
        except ValueError:
            # Semaphore was already released (e.g., by cancel endpoint)
            logger.debug(f"[{run_id[:8]}] Semaphore already released")


async def _enqueue_run(
    job_id: str,
    profile_ref: Optional[str],
    source: Optional[str],
    background_tasks: BackgroundTasks,
    processing_tier: Optional[str] = "auto",
    job_title: Optional[str] = None,
    company: Optional[str] = None,
) -> str:
    """
    Create a run record and start a background task respecting concurrency limits.

    If queue manager is available, also adds to Redis queue for persistence
    and real-time visibility.
    """
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    acquired = await _semaphore.acquire()
    if not acquired:  # pragma: no cover - defensive; acquire returns None
        logger.warning(f"Runner at capacity, rejecting job {job_id}")
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

    # Add to Redis queue if queue manager is available
    queue_id = None
    if _queue_manager:
        try:
            # Fetch job details if not provided
            if not job_title or not company:
                job_title, company = await _get_job_details(job_id)

            queue_item = await _queue_manager.enqueue(
                job_id=job_id,
                job_title=job_title or "Unknown Job",
                company=company or "Unknown Company",
                operation="full_pipeline",
                processing_tier=processing_tier or "auto",
            )
            queue_id = queue_item.queue_id

            # Immediately mark as running since we have the semaphore
            # and link the run_id
            if _queue_manager._redis:
                from .queue.models import QueueItemStatus
                await _queue_manager._redis.rpop(_queue_manager.PENDING_KEY)  # Remove from pending
                await _queue_manager._redis.sadd(_queue_manager.RUNNING_KEY, queue_id)
                queue_item.status = QueueItemStatus.RUNNING
                queue_item.started_at = now
                queue_item.run_id = run_id
                await _queue_manager._update_item(queue_item)
                await _queue_manager._publish_event("started", queue_item)

            logger.info(f"[{run_id[:8]}] Added to queue as {queue_id}")
        except Exception as e:
            logger.warning(f"[{run_id[:8]}] Failed to add to queue: {e}")
            queue_id = None

    logger.info(f"[{run_id[:8]}] Enqueued run for job {job_id} (source={source}, tier={processing_tier})")
    _append_log(run_id, f"Run created for job {job_id} (source={source}, tier={processing_tier}, profile={profile_ref})")
    background_tasks.add_task(
        _execute_pipeline_task, run_id, job_id, profile_ref, processing_tier, queue_id
    )
    return run_id


async def _get_job_details(job_id: str) -> tuple:
    """
    Fetch job title and company from MongoDB.

    Returns:
        Tuple of (job_title, company) or ("Unknown", "Unknown") if not found
    """
    try:
        from bson import ObjectId
        from pymongo import MongoClient

        mongodb_uri = os.getenv("MONGODB_URI")
        if not mongodb_uri:
            return ("Unknown Job", "Unknown Company")

        client = MongoClient(mongodb_uri)
        db = client["jobs"]

        try:
            object_id = ObjectId(job_id)
        except Exception:
            return ("Unknown Job", "Unknown Company")

        job = db["level-2"].find_one(
            {"_id": object_id},
            {"title": 1, "company": 1}
        )

        if job:
            return (job.get("title", "Unknown Job"), job.get("company", "Unknown Company"))

        return ("Unknown Job", "Unknown Company")

    except Exception as e:
        logger.warning(f"Failed to fetch job details for {job_id}: {e}")
        return ("Unknown Job", "Unknown Company")


@app.post("/jobs/run", response_model=RunResponse, dependencies=[Depends(verify_token)])
async def run_job(request: RunJobRequest, background_tasks: BackgroundTasks) -> RunResponse:
    """Kick off a single job run. Requires authentication."""
    run_id = await _enqueue_run(
        job_id=request.job_id,
        profile_ref=request.profile_ref,
        source=request.source,
        background_tasks=background_tasks,
        processing_tier=request.processing_tier,
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
            processing_tier=request.processing_tier,
        )
        responses.append(
            RunResponse(
                run_id=run_id,
                status_url=_status_url(run_id),
                log_stream_url=_log_stream_url(run_id),
            )
        )
    return {"runs": responses}


@app.post("/jobs/import-linkedin", response_model=LinkedInImportResponse, dependencies=[Depends(verify_token)])
async def import_linkedin_job(request: LinkedInImportRequest) -> LinkedInImportResponse:
    """
    Import a job from LinkedIn by ID or URL (GAP-065).

    This endpoint runs on the VPS runner service to avoid Vercel's timeout limits.
    It scrapes LinkedIn, optionally scores the job, and stores it in MongoDB.
    """
    from pymongo import MongoClient

    job_id_or_url = request.job_id_or_url.strip()

    if not job_id_or_url:
        raise HTTPException(status_code=400, detail="job_id_or_url is required")

    try:
        # Import the scraper
        from src.services.linkedin_scraper import (
            scrape_linkedin_job,
            linkedin_job_to_mongodb_doc,
            LinkedInScraperError,
            JobNotFoundError,
            RateLimitError,
        )

        # Scrape the job
        logger.info(f"Importing LinkedIn job: {job_id_or_url}")
        linkedin_data = scrape_linkedin_job(job_id_or_url)

        # Convert to MongoDB document
        mongo_doc = linkedin_job_to_mongodb_doc(linkedin_data)

        # Connect to MongoDB
        mongo_uri = os.getenv("MONGODB_URI")
        if not mongo_uri:
            raise HTTPException(status_code=500, detail="MONGODB_URI not configured")

        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGODB_DATABASE", "jobs")]
        level1_collection = db["level-1"]
        level2_collection = db["level-2"]

        # Check for duplicates
        existing_level2 = level2_collection.find_one({"dedupeKey": mongo_doc["dedupeKey"]})
        if existing_level2:
            logger.info(f"Job already exists in level-2: {existing_level2['_id']}")
            return LinkedInImportResponse(
                success=True,
                job_id=str(existing_level2["_id"]),
                title=existing_level2.get("title", ""),
                company=existing_level2.get("company", ""),
                location=existing_level2.get("location"),
                score=existing_level2.get("score"),
                tier=existing_level2.get("tier"),
                duplicate=True,
                error="Job already exists in database",
            )

        existing_level1 = level1_collection.find_one({"dedupeKey": mongo_doc["dedupeKey"]})
        if existing_level1:
            logger.info(f"Job already exists in level-1: {existing_level1['_id']}")
            return LinkedInImportResponse(
                success=True,
                job_id=str(existing_level1["_id"]),
                title=existing_level1.get("title", ""),
                company=existing_level1.get("company", ""),
                location=existing_level1.get("location"),
                score=existing_level1.get("score"),
                tier=existing_level1.get("tier"),
                duplicate=True,
                error="Job already exists in level-1 database",
            )

        # Quick score the job (optional)
        score = None
        score_rationale = None
        tier = None
        try:
            from src.services.quick_scorer import quick_score_job, derive_tier_from_score

            score, score_rationale = quick_score_job(
                title=linkedin_data.title,
                company=linkedin_data.company,
                location=linkedin_data.location,
                description=linkedin_data.description,
            )

            if score is not None:
                mongo_doc["score"] = score
                tier = derive_tier_from_score(score)
                mongo_doc["tier"] = tier
                mongo_doc["score_rationale"] = score_rationale
                logger.info(f"Quick scored job: {score} ({tier})")
        except Exception as score_err:
            logger.warning(f"Quick scoring failed (continuing without score): {score_err}")

        # Insert into both collections
        level1_doc = mongo_doc.copy()
        level1_collection.insert_one(level1_doc)

        level2_doc = mongo_doc.copy()
        level2_result = level2_collection.insert_one(level2_doc)
        job_id = str(level2_result.inserted_id)

        logger.info(f"Imported LinkedIn job {job_id}: {linkedin_data.title} at {linkedin_data.company}")

        return LinkedInImportResponse(
            success=True,
            job_id=job_id,
            title=linkedin_data.title,
            company=linkedin_data.company,
            location=linkedin_data.location,
            score=score,
            tier=tier,
            score_rationale=score_rationale,
        )

    except JobNotFoundError as e:
        logger.warning(f"LinkedIn job not found: {e}")
        raise HTTPException(status_code=404, detail=f"Job not found on LinkedIn: {str(e)}")

    except RateLimitError as e:
        logger.warning(f"LinkedIn rate limit: {e}")
        raise HTTPException(status_code=429, detail="LinkedIn rate limit hit. Please try again later.")

    except LinkedInScraperError as e:
        logger.error(f"LinkedIn scraper error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to scrape LinkedIn: {str(e)}")

    except ValueError as e:
        logger.warning(f"Invalid job ID: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.exception(f"Unexpected error importing LinkedIn job: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


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


@app.post("/jobs/{run_id}/cancel", dependencies=[Depends(verify_token)])
async def cancel_run(run_id: str) -> Dict[str, Any]:
    """
    Cancel a running pipeline immediately (SIGKILL).

    Discards all partial results - no MongoDB updates are made.
    The job document remains unchanged as if the pipeline never ran.

    Returns:
        JSON with success status and message
    """
    # 1. Validate run exists
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")

    # 2. Check if already in terminal state
    if state.status in {"completed", "failed", "cancelled"}:
        return {"success": False, "error": f"Run already {state.status}"}

    # 3. Kill subprocess if running
    process = _processes.get(run_id)
    if process and process.returncode is None:
        logger.info(f"[{run_id[:8]}] Killing process {process.pid} via SIGKILL")
        process.kill()
        try:
            await process.wait()
        except Exception as e:
            logger.warning(f"[{run_id[:8]}] Error waiting for killed process: {e}")

    # 4. Update status to cancelled (NO MongoDB persistence)
    state.status = "cancelled"
    state.updated_at = datetime.utcnow()
    _append_log(run_id, "⛔ Pipeline cancelled by user - all changes discarded")
    logger.info(f"[{run_id[:8]}] Pipeline cancelled by user")

    # 5. Release semaphore
    try:
        _semaphore.release()
        logger.debug(f"[{run_id[:8]}] Released semaphore after cancel")
    except ValueError:
        # Already released (shouldn't happen but handle gracefully)
        pass

    # 6. Clean up process reference
    _processes.pop(run_id, None)

    return {"success": True, "message": "Pipeline cancelled"}


@app.get("/jobs/{run_id}/progress", response_model=PipelineProgressResponse)
async def get_progress(run_id: str) -> PipelineProgressResponse:
    """
    Return layer-by-layer progress for a pipeline run (Gap #25).

    This endpoint provides detailed progress information that the frontend
    uses to render the step-by-step pipeline visualization.
    """
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="Run not found")

    # Build layer progress list from state or parse from logs
    layers = []
    completed_layers = 0

    for layer_def in PIPELINE_LAYERS:
        layer_id = layer_def["id"]
        layer_state = state.layers.get(layer_id, {})

        # Determine layer status
        if layer_state.get("completed_at"):
            status = "success" if not layer_state.get("error") else "failed"
            completed_layers += 1
        elif layer_state.get("started_at"):
            status = "executing"
        elif state.current_layer == layer_id:
            status = "executing"
        else:
            status = "pending"

        # Calculate duration if available
        duration_ms = None
        if layer_state.get("started_at") and layer_state.get("completed_at"):
            delta = layer_state["completed_at"] - layer_state["started_at"]
            duration_ms = int(delta.total_seconds() * 1000)

        layers.append(LayerProgress(
            layer=layer_id,
            status=status,
            started_at=layer_state.get("started_at"),
            completed_at=layer_state.get("completed_at"),
            duration_ms=duration_ms,
            error=layer_state.get("error"),
        ))

    # Calculate overall progress percentage
    total_layers = len(PIPELINE_LAYERS)
    progress_percent = int((completed_layers / total_layers) * 100) if total_layers > 0 else 0

    # If pipeline completed or failed, set progress appropriately
    if state.status == "completed":
        progress_percent = 100
    elif state.status == "failed":
        # Keep progress at last completed layer
        pass

    return PipelineProgressResponse(
        run_id=run_id,
        job_id=state.job_id,
        overall_status=state.status,
        progress_percent=progress_percent,
        layers=layers,
        current_layer=state.current_layer,
        started_at=state.started_at,
        updated_at=state.updated_at,
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

            if state.status in {"completed", "failed", "cancelled"}:
                yield f"event: end\ndata: {state.status}\n\n"
                break

            await asyncio.sleep(0.1)  # 100ms poll interval for responsive updates

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


# =============================================================================
# Queue Management (Redis-backed)
# =============================================================================


@app.on_event("startup")
async def startup_queue_manager():
    """Initialize queue manager on startup if Redis is configured."""
    global _queue_manager, _ws_manager

    if not settings.redis_url:
        logger.info("Redis not configured, queue persistence disabled")
        return

    try:
        from .queue import QueueManager, QueueWebSocketManager

        _queue_manager = QueueManager(settings.redis_url)
        await _queue_manager.connect()

        _ws_manager = QueueWebSocketManager(_queue_manager)

        # Subscribe to queue events for WebSocket broadcasting
        async def broadcast_event(event: dict):
            if _ws_manager:
                await _ws_manager.broadcast({
                    "type": "queue_update",
                    "payload": event
                })

        await _queue_manager.subscribe(broadcast_event)

        # Restore any interrupted runs from previous instance
        restored = await _queue_manager.restore_interrupted_runs()
        if restored:
            logger.info(f"Restored {len(restored)} interrupted runs to queue")

        logger.info("Queue manager initialized with Redis")

    except Exception as e:
        logger.error(f"Failed to initialize queue manager: {e}")
        _queue_manager = None
        _ws_manager = None


@app.on_event("shutdown")
async def shutdown_queue_manager():
    """Disconnect queue manager on shutdown."""
    global _queue_manager, _ws_manager

    if _queue_manager:
        await _queue_manager.disconnect()
        _queue_manager = None
        _ws_manager = None
        logger.info("Queue manager disconnected")


@app.websocket("/ws/queue")
async def queue_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time queue state updates.

    Provides:
    - Initial queue state on connect
    - Real-time updates as queue changes
    - Client commands: retry, cancel, dismiss, refresh

    Authentication:
    - Validates Bearer token from Authorization header
    - Uses same secret as REST API endpoints (RUNNER_API_SECRET)

    Note: WebSocket connections MUST call accept() before close() to avoid
    Uvicorn returning HTTP 403 Forbidden (per ASGI spec).
    """
    # Diagnostic logging for connection debugging
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info(f"[WS] WebSocket connection attempt from {client_host}")
    logger.debug(f"[WS] Headers: {dict(websocket.headers)}")
    logger.debug(f"[WS] Path: {websocket.url.path}")

    # Verify authentication BEFORE accepting (but must accept to send error)
    is_authenticated, auth_error = verify_websocket_token(websocket)

    if not is_authenticated:
        # CRITICAL: Must accept() before close() to avoid HTTP 403 response.
        # Per ASGI spec, closing without accepting results in 403 Forbidden.
        logger.warning(f"[WS] Authentication failed for {client_host}: {auth_error}")
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "payload": {
                "message": f"Authentication failed: {auth_error}",
                "code": "AUTH_FAILED"
            }
        })
        await websocket.close(code=1008, reason="Authentication failed")
        return

    logger.info(f"[WS] Queue manager configured: {_ws_manager is not None}")

    if not _ws_manager:
        # CRITICAL: Must accept() before close() to avoid HTTP 403 response.
        logger.warning(f"[WS] Queue not configured (Redis unavailable), sending error to client")
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "payload": {
                "message": "Queue service not configured. Redis may be unavailable.",
                "code": "QUEUE_NOT_CONFIGURED"
            }
        })
        await websocket.close(code=1011, reason="Queue not configured")
        return

    logger.info(f"[WS] Accepting authenticated WebSocket connection from {client_host}")
    await _ws_manager.run_connection(websocket)


@app.get("/queue/state")
async def get_queue_state():
    """
    Get current queue state (REST fallback for WebSocket).

    Returns queue state with pending, running, failed, and history items.
    """
    if not _queue_manager:
        return {
            "pending": [],
            "running": [],
            "failed": [],
            "history": [],
            "stats": {
                "total_pending": 0,
                "total_running": 0,
                "total_failed": 0,
                "total_completed_today": 0,
            },
            "queue_enabled": False,
        }

    state = await _queue_manager.get_state()
    result = state.to_dict()
    result["queue_enabled"] = True
    return result


@app.post("/queue/{queue_id}/retry", dependencies=[Depends(verify_token)])
async def retry_queue_item(queue_id: str):
    """
    Retry a failed queue item.

    Moves the item back to the pending queue for re-execution.
    """
    if not _queue_manager:
        raise HTTPException(status_code=503, detail="Queue not configured")

    item = await _queue_manager.retry(queue_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail="Queue item not found or not in failed state"
        )

    return {"success": True, "item": item.to_dict()}


@app.post("/queue/{queue_id}/cancel", dependencies=[Depends(verify_token)])
async def cancel_queue_item(queue_id: str):
    """
    Cancel a pending queue item.

    Removes the item from the queue without execution.
    """
    if not _queue_manager:
        raise HTTPException(status_code=503, detail="Queue not configured")

    success = await _queue_manager.cancel(queue_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Queue item not found or not in pending state"
        )

    return {"success": True}


@app.post("/queue/{queue_id}/dismiss", dependencies=[Depends(verify_token)])
async def dismiss_queue_item(queue_id: str):
    """
    Dismiss a failed queue item.

    Removes from failed list without retry, moves to history.
    """
    if not _queue_manager:
        raise HTTPException(status_code=503, detail="Queue not configured")

    success = await _queue_manager.dismiss_failed(queue_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Queue item not found or not in failed state"
        )

    return {"success": True}


@app.get("/queue/item/{job_id}")
async def get_queue_item_by_job(job_id: str):
    """
    Get queue item by job ID.

    Useful for checking if a job is currently queued or running.
    """
    if not _queue_manager:
        return {"found": False, "queue_enabled": False}

    item = await _queue_manager.get_item_by_job_id(job_id)
    if not item:
        return {"found": False, "queue_enabled": True}

    return {"found": True, "item": item.to_dict(), "queue_enabled": True}


@app.get("/firecrawl/credits", response_model=FireCrawlCreditsResponse)
async def get_firecrawl_credits() -> FireCrawlCreditsResponse:
    """
    Get FireCrawl API credit usage (GAP-070).

    Calls actual FireCrawl API to get token usage, falls back to local rate limiter.
    """
    import httpx
    from src.common.rate_limiter import get_rate_limiter

    # Try actual FireCrawl API first
    if settings.firecrawl_api_key:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.firecrawl.dev/v1/team/token-usage",
                    headers={"Authorization": f"Bearer {settings.firecrawl_api_key}"}
                )
                if response.status_code == 200:
                    data = response.json()
                    # Parse FireCrawl API response
                    # Expected fields: credits_used, credits_remaining, total_credits, etc.
                    total_credits = data.get("total_credits", 500)
                    credits_used = data.get("credits_used", 0)
                    credits_remaining = data.get("credits_remaining", total_credits - credits_used)

                    used_percent = (credits_used / total_credits * 100) if total_credits > 0 else 0

                    if used_percent >= 100:
                        status = "exhausted"
                    elif used_percent >= 90:
                        status = "critical"
                    elif used_percent >= 80:
                        status = "warning"
                    else:
                        status = "healthy"

                    return FireCrawlCreditsResponse(
                        provider="firecrawl",
                        daily_limit=total_credits,
                        used_today=credits_used,
                        remaining=credits_remaining,
                        used_percent=round(used_percent, 1),
                        requests_this_minute=0,
                        requests_per_minute_limit=10,
                        last_request_at=None,
                        daily_reset_at=None,
                        status=status,
                    )
        except Exception as e:
            logger.warning(f"FireCrawl API call failed, falling back to rate limiter: {e}")

    # Fallback to local rate limiter tracking
    limiter = get_rate_limiter("firecrawl")
    stats = limiter.get_stats()
    remaining = limiter.get_remaining_daily() or 0
    daily_limit = limiter.daily_limit or 600

    used_today = stats.requests_today
    used_percent = (used_today / daily_limit * 100) if daily_limit > 0 else 0

    if used_percent >= 100:
        status = "exhausted"
    elif used_percent >= 90:
        status = "critical"
    elif used_percent >= 80:
        status = "warning"
    else:
        status = "healthy"

    return FireCrawlCreditsResponse(
        provider="firecrawl",
        daily_limit=daily_limit,
        used_today=used_today,
        remaining=remaining,
        used_percent=round(used_percent, 1),
        requests_this_minute=stats.requests_this_minute,
        requests_per_minute_limit=limiter.requests_per_minute,
        last_request_at=stats.last_request_at,
        daily_reset_at=stats.daily_reset_at,
        status=status,
    )


@app.get("/openrouter/credits", response_model=OpenRouterCreditsResponse)
async def get_openrouter_credits() -> OpenRouterCreditsResponse:
    """
    Get OpenRouter API credit balance.

    Calls OpenRouter API to get remaining credits.
    """
    import httpx

    if not settings.openrouter_api_key:
        return OpenRouterCreditsResponse(
            credits_remaining=0.0,
            credits_used=None,
            status="exhausted",
            error="OpenRouter API key not configured"
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"}
            )
            if response.status_code == 200:
                data = response.json()
                # OpenRouter returns: {"data": {"limit": float, "usage": float, ...}}
                limit = data.get("data", {}).get("limit", 0)
                usage = data.get("data", {}).get("usage", 0)
                remaining = limit - usage if limit else 0

                if remaining <= 0:
                    status = "exhausted"
                elif remaining < 1:
                    status = "critical"
                elif remaining < 5:
                    status = "warning"
                else:
                    status = "healthy"

                return OpenRouterCreditsResponse(
                    credits_remaining=round(remaining, 2),
                    credits_used=round(usage, 2),
                    status=status,
                )
            else:
                return OpenRouterCreditsResponse(
                    credits_remaining=0.0,
                    status="exhausted",
                    error=f"API returned status {response.status_code}"
                )
    except Exception as e:
        logger.warning(f"OpenRouter API call failed: {e}")
        return OpenRouterCreditsResponse(
            credits_remaining=0.0,
            status="exhausted",
            error=str(e)
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


# ============================================================================
# PDF Generation Endpoint (Phase 4 - CV Editor)
# ============================================================================

def migrate_cv_text_to_editor_state(cv_text: str) -> dict:
    """
    Migrate markdown CV text to TipTap editor state.

    Converts markdown to TipTap JSON, parsing line-by-line to handle:
    - Headings (# ## ###)
    - Bullet lists (-)
    - Bold/italic text (**)
    - Regular paragraphs

    This function duplicates the migration logic from frontend/app.py to ensure
    consistent behavior when generating PDFs directly without opening the editor.

    Args:
        cv_text: Markdown CV content

    Returns:
        TipTap editor state dictionary
    """
    lines = cv_text.split('\n')
    content = []
    current_list = None
    i = 0

    def parse_inline_marks(text):
        """Parse bold and italic marks from text.

        GAP-012 Fix: Properly parse **bold** and *italic* markdown to TipTap marks.

        Supports:
        - **bold** → text with bold mark
        - *italic* → text with italic mark
        - ***bold+italic*** → text with both marks
        - Mixed text like "Hello **world** and *universe*"
        """
        import re

        if not text:
            return []

        result = []

        # Regex pattern for bold (**text**), italic (*text*), or bold+italic (***text***)
        # Order matters: check *** first, then **, then *
        pattern = r'(\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*([^*]+?)\*)'

        last_end = 0
        for match in re.finditer(pattern, text):
            # Add any plain text before this match
            if match.start() > last_end:
                plain_text = text[last_end:match.start()]
                if plain_text:
                    result.append({"type": "text", "text": plain_text})

            # Determine which group matched
            if match.group(2):  # ***bold+italic***
                result.append({
                    "type": "text",
                    "text": match.group(2),
                    "marks": [{"type": "bold"}, {"type": "italic"}]
                })
            elif match.group(3):  # **bold**
                result.append({
                    "type": "text",
                    "text": match.group(3),
                    "marks": [{"type": "bold"}]
                })
            elif match.group(4):  # *italic*
                result.append({
                    "type": "text",
                    "text": match.group(4),
                    "marks": [{"type": "italic"}]
                })

            last_end = match.end()

        # Add any remaining plain text after the last match
        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                result.append({"type": "text", "text": remaining})

        # If no matches found, return the original text as plain
        if not result:
            result.append({"type": "text", "text": text})

        return result

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            # Empty line closes current list
            if current_list:
                content.append(current_list)
                current_list = None
            i += 1
            continue

        # Heading level 1
        if line.startswith('# ') and not line.startswith('##'):
            if current_list:
                content.append(current_list)
                current_list = None
            content.append({
                "type": "heading",
                "attrs": {"level": 1},
                "content": parse_inline_marks(line[2:].strip())
            })

        # Heading level 2
        elif line.startswith('## ') and not line.startswith('###'):
            if current_list:
                content.append(current_list)
                current_list = None
            content.append({
                "type": "heading",
                "attrs": {"level": 2},
                "content": parse_inline_marks(line[3:].strip())
            })

        # Heading level 3
        elif line.startswith('### '):
            if current_list:
                content.append(current_list)
                current_list = None
            content.append({
                "type": "heading",
                "attrs": {"level": 3},
                "content": parse_inline_marks(line[4:].strip())
            })

        # Bullet point
        elif line.startswith('- '):
            list_item = {
                "type": "listItem",
                "content": [{
                    "type": "paragraph",
                    "content": parse_inline_marks(line[2:].strip())
                }]
            }

            if current_list is None:
                current_list = {
                    "type": "bulletList",
                    "content": [list_item]
                }
            else:
                current_list["content"].append(list_item)

        # Regular paragraph
        else:
            if current_list:
                content.append(current_list)
                current_list = None
            content.append({
                "type": "paragraph",
                "content": parse_inline_marks(line)
            })

        i += 1

    # Close any open list at end
    if current_list:
        content.append(current_list)

    return {
        "version": 1,
        "content": {
            "type": "doc",
            "content": content
        },
        "documentStyles": {
            "fontFamily": "Inter",
            "fontSize": 11,
            "lineHeight": 1.15,  # Phase 3: Standard resume spacing
            "margins": {
                "top": 1.0,  # Phase 3: Standard 1-inch margins
                "right": 1.0,
                "bottom": 1.0,
                "left": 1.0
            },
            "pageSize": "letter"
        }
    }


def sanitize_margins(margins: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """
    Sanitize margins dictionary to ensure all values are valid floats.

    Handles None, NaN, missing keys, and invalid types by falling back to defaults.
    This prevents the "Nonein" bug where None values get interpolated as strings.

    Args:
        margins: Margins dict from editor state (may contain None/null values)

    Returns:
        Dict with all margin values as valid floats (default 1.0 inches)
    """
    if not margins or not isinstance(margins, dict):
        return {"top": 1.0, "right": 1.0, "bottom": 1.0, "left": 1.0}

    defaults = {"top": 1.0, "right": 1.0, "bottom": 1.0, "left": 1.0}
    result = {}

    for key in ["top", "right", "bottom", "left"]:
        value = margins.get(key)
        # Handle None, null, NaN, or invalid types
        if value is None or not isinstance(value, (int, float)) or value != value:  # NaN check
            result[key] = defaults[key]
        else:
            result[key] = float(value)

    return result


@app.post("/api/jobs/{job_id}/cv-editor/pdf", dependencies=[Depends(verify_token)])
async def generate_cv_pdf(job_id: str):
    """
    Generate PDF from CV editor state via PDF service (Phase 6).

    This endpoint:
    1. Fetches cv_editor_state from MongoDB
    2. Sends TipTap JSON + styles to PDF service
    3. Returns PDF as downloadable attachment

    Args:
        job_id: MongoDB ObjectId of the job

    Returns:
        StreamingResponse with PDF binary data
    """
    import httpx
    from bson import ObjectId
    from pymongo import MongoClient

    # Get PDF service URL from environment
    pdf_service_url = os.getenv("PDF_SERVICE_URL", "http://pdf-service:8001")

    # Validate job_id format before attempting any database connections
    try:
        object_id = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    # Get MongoDB connection
    # IMPORTANT: Use MONGODB_URI to match persistence.py and frontend
    # Provide sensible default for local/test environments
    mongo_uri = (
        os.getenv("MONGODB_URI")
        or os.getenv("MONGO_URI")
        or "mongodb://localhost:27017"
    )
    if not os.getenv("MONGODB_URI"):
        logger.debug(
            "MONGODB_URI not set; defaulting to mongodb://localhost:27017 for CV PDF generation"
        )

    client = None

    try:
        client = MongoClient(mongo_uri)
        # Use "jobs" database to match persistence.py (not "job_search")
        db = client[os.getenv("MONGO_DB_NAME", "jobs")]
        collection = db["level-2"]

        job = collection.find_one({"_id": object_id})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get editor state (or migrate from cv_text if not present)
        editor_state = job.get("cv_editor_state")

        # Validate editor state structure
        is_valid_state = (
            editor_state
            and isinstance(editor_state, dict)
            and "content" in editor_state
            and isinstance(editor_state["content"], dict)
            and editor_state["content"].get("type") == "doc"
        )

        # If no valid editor state exists, migrate from cv_text (markdown)
        # This allows users to export PDF directly without opening the editor first
        if not is_valid_state and job.get("cv_text"):
            editor_state = migrate_cv_text_to_editor_state(job.get("cv_text"))

        # If still no state (no cv_text and no cv_editor_state), use empty default
        if not editor_state:
            editor_state = {
                "content": {"type": "doc", "content": []},
                "documentStyles": {
                    "fontFamily": "Inter",
                    "fontSize": 11,
                    "lineHeight": 1.15,
                    "margins": {"top": 1.0, "right": 1.0, "bottom": 1.0, "left": 1.0},
                    "pageSize": "letter"
                }
            }

        # Build request payload for PDF service
        pdf_request = {
            "tiptap_json": editor_state["content"],
            "documentStyles": editor_state.get("documentStyles", {}),
            "header": editor_state.get("header", ""),
            "footer": editor_state.get("footer", ""),
            "company": job.get("company", "Company"),
            "role": job.get("title", "Position")
        }

        # Sanitize margins to prevent None/NaN values from causing PDF generation errors
        if "documentStyles" in pdf_request:
            pdf_request["documentStyles"]["margins"] = sanitize_margins(
                pdf_request["documentStyles"].get("margins")
            )

        # Call PDF service with timeout and retry logic
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            try:
                response = await http_client.post(
                    f"{pdf_service_url}/cv-to-pdf",
                    json=pdf_request
                )
                response.raise_for_status()

                # Extract filename from response headers
                content_disposition = response.headers.get("Content-Disposition", "")
                filename = "CV.pdf"
                if "filename=" in content_disposition:
                    # Parse filename from Content-Disposition header
                    filename_part = content_disposition.split("filename=")[1]
                    filename = filename_part.strip('"')

                # Return PDF as streaming response
                from io import BytesIO
                return StreamingResponse(
                    BytesIO(response.content),
                    media_type='application/pdf',
                    headers={
                        'Content-Disposition': f'attachment; filename="{filename}"'
                    }
                )

            except httpx.TimeoutException:
                logger.error(f"PDF service timeout for job {job_id}")
                raise HTTPException(
                    status_code=504,
                    detail="PDF generation timed out. Please try again."
                )
            except httpx.HTTPStatusError as e:
                logger.error(f"PDF service returned error {e.response.status_code} for job {job_id}")
                # Try to parse error details from response
                try:
                    error_detail = e.response.json().get("detail", str(e))
                except Exception:
                    error_detail = str(e)
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"PDF generation failed: {error_detail}"
                )
            except httpx.RequestError as e:
                logger.error(f"PDF service connection failed for job {job_id}: {str(e)}")
                raise HTTPException(
                    status_code=503,
                    detail="PDF service unavailable. Please try again later."
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF generation failed for job {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass


# ============================================================================
# URL to PDF Endpoint (Phase 2 - Job Posting Export)
# ============================================================================

class URLToPDFRequest(BaseModel):
    """Request model for URL to PDF conversion."""
    url: str


@app.post("/api/url-to-pdf", dependencies=[Depends(verify_token)])
async def export_url_to_pdf(request: URLToPDFRequest):
    """
    Export a URL (job posting) to PDF.

    Proxies request to PDF service which uses Playwright to capture the page.

    Args:
        request: Contains URL to render

    Returns:
        StreamingResponse with PDF binary data
    """
    import httpx

    # Validate URL
    if not request.url or not request.url.strip():
        raise HTTPException(status_code=400, detail="URL is required")

    if not request.url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    # Get PDF service URL from environment
    pdf_service_url = os.getenv("PDF_SERVICE_URL", "http://pdf-service:8001")

    try:
        logger.info(f"Proxying URL-to-PDF request: {request.url[:100]}...")

        async with httpx.AsyncClient(timeout=60.0) as http_client:
            response = await http_client.post(
                f"{pdf_service_url}/url-to-pdf",
                json={"url": request.url}
            )
            response.raise_for_status()

            # Extract filename from response headers
            content_disposition = response.headers.get("Content-Disposition", "")
            filename = "job_posting.pdf"
            if "filename=" in content_disposition:
                filename_part = content_disposition.split("filename=")[1]
                filename = filename_part.strip('"')

            logger.info(f"URL-to-PDF completed: {filename}")

            return StreamingResponse(
                BytesIO(response.content),
                media_type='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"'
                }
            )

    except httpx.TimeoutException:
        logger.error(f"URL-to-PDF timed out: {request.url}")
        raise HTTPException(
            status_code=504,
            detail="PDF generation timed out. The site may be slow or blocking automation."
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"PDF service error: {e.response.status_code}")
        try:
            error_detail = e.response.json().get("detail", str(e))
        except Exception:
            error_detail = str(e)
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"PDF generation failed: {error_detail}"
        )
    except httpx.RequestError as e:
        logger.error(f"PDF service connection failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="PDF service unavailable. Please try again later."
        )


# ============================================================================
# PDF Service Proxy Endpoint (for dossier PDF export)
# ============================================================================

class RenderPDFRequest(BaseModel):
    """Request model for HTML to PDF conversion."""
    html: str
    css: Optional[str] = None
    pageSize: str = "letter"
    printBackground: bool = True


@app.post("/proxy/pdf/render-pdf", dependencies=[Depends(verify_token)])
async def proxy_render_pdf(request: RenderPDFRequest):
    """
    Proxy endpoint to forward HTML rendering requests to PDF service.

    Used by dossier PDF export from frontend. The frontend calls this
    endpoint which then forwards to the internal PDF service.

    Args:
        request: HTML content and rendering options

    Returns:
        StreamingResponse with PDF binary data
    """
    import httpx

    # Validate HTML
    if not request.html or not request.html.strip():
        raise HTTPException(status_code=400, detail="HTML content is required")

    # Get PDF service URL from environment
    pdf_service_url = os.getenv("PDF_SERVICE_URL", "http://pdf-service:8001")

    try:
        logger.info("Proxying render-pdf request to PDF service")

        async with httpx.AsyncClient(timeout=60.0) as http_client:
            response = await http_client.post(
                f"{pdf_service_url}/render-pdf",
                json={
                    "html": request.html,
                    "css": request.css,
                    "pageSize": request.pageSize,
                    "printBackground": request.printBackground
                }
            )
            response.raise_for_status()

            # Return PDF as streaming response
            return StreamingResponse(
                BytesIO(response.content),
                media_type='application/pdf',
                headers={
                    'Content-Disposition': response.headers.get(
                        "Content-Disposition",
                        'attachment; filename="document.pdf"'
                    )
                }
            )

    except httpx.TimeoutException:
        logger.error("Render-PDF proxy timed out")
        raise HTTPException(
            status_code=504,
            detail="PDF generation timed out. Please try again."
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"PDF service error: {e.response.status_code}")
        try:
            error_detail = e.response.json().get("detail", str(e))
        except Exception:
            error_detail = str(e)
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"PDF generation failed: {error_detail}"
        )
    except httpx.RequestError as e:
        logger.error(f"PDF service connection failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="PDF service unavailable. Please try again later."
        )


# =============================================================================
# Metrics/Budget/Alert Endpoints (GAP-061 fix)
# =============================================================================


@app.get("/api/metrics/budget")
async def get_budget_metrics():
    """
    Return budget metrics from all token trackers.

    Used by frontend to display budget monitoring widget.
    """
    try:
        from src.common.metrics import get_metrics_collector

        collector = get_metrics_collector()
        budget_metrics = collector.get_budget_metrics()
        return budget_metrics.to_dict()
    except ImportError as e:
        logger.warning(f"Metrics module not available: {e}")
        return {
            "error": "Metrics module not available",
            "total_used_usd": 0,
            "total_budget_usd": None,
            "by_tracker": {},
        }
    except Exception as e:
        logger.error(f"Error getting budget metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics/alerts")
async def get_alert_history(limit: int = 50, level: str = None, source: str = None):
    """
    Return alert history with optional filtering.

    Args:
        limit: Max number of alerts to return (default 50)
        level: Filter by alert level (critical, error, warning, info)
        source: Filter by alert source

    Used by frontend to display alert history widget.
    """
    try:
        from src.common.alerting import get_alert_manager

        manager = get_alert_manager()
        alerts = manager.get_history(limit=limit)

        # Apply filters
        if level:
            alerts = [a for a in alerts if a.level.value == level]
        if source:
            alerts = [a for a in alerts if a.source == source]

        return {
            "alerts": [a.to_dict() for a in alerts],
            "stats": manager.get_stats(),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except ImportError as e:
        logger.warning(f"Alerting module not available: {e}")
        return {
            "error": "Alerting module not available",
            "alerts": [],
            "stats": {"history_count": 0, "by_level": {}, "by_source": {}},
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting alert history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics/cost-history")
async def get_cost_history(period: str = "hourly", count: int = 24):
    """
    Return cost history for sparkline visualization.

    Args:
        period: Time period (hourly, daily)
        count: Number of data points

    Used by frontend to display cost trends sparkline.
    """
    try:
        from src.common.metrics import get_metrics_collector

        collector = get_metrics_collector()
        history = collector.get_cost_history(period=period, count=count)
        history["timestamp"] = datetime.utcnow().isoformat()
        return history
    except ImportError as e:
        logger.warning(f"Metrics module not available: {e}")
        return {
            "error": "Metrics module not available",
            "costs": [],
            "sparkline_svg": "",
            "summary": {"total": 0, "avg": 0, "max": 0, "min": 0},
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting cost history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
