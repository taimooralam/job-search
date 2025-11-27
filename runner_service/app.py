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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


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
        logger.info(f"[{run_id[:8]}] Starting pipeline task for job {job_id}")
        _update_status(run_id, "running")
        _append_log(run_id, f"Starting pipeline for job {job_id}...")

        # Create log callback that captures run_id in closure
        def log_callback(message: str) -> None:
            _append_log(run_id, message)

        # Execute pipeline subprocess
        success, artifacts, pipeline_state = await execute_pipeline(
            job_id=job_id,
            profile_ref=profile_ref,
            log_callback=log_callback,
        )

        # Update status based on result
        if success:
            logger.info(f"[{run_id[:8]}] Pipeline completed successfully for job {job_id}")
            _update_status(run_id, "completed", artifacts, pipeline_state)
            _append_log(run_id, "✅ Pipeline execution complete")
        else:
            logger.warning(f"[{run_id[:8]}] Pipeline failed for job {job_id}")
            _update_status(run_id, "failed")
            _append_log(run_id, "❌ Pipeline execution failed")

    except asyncio.TimeoutError:
        logger.error(f"[{run_id[:8]}] Pipeline timed out for job {job_id}")
        _append_log(run_id, "❌ Pipeline timed out")
        _update_status(run_id, "failed")
    except Exception as exc:
        logger.exception(f"[{run_id[:8]}] Unexpected error for job {job_id}: {exc}")
        _append_log(run_id, f"❌ Unexpected error: {exc}")
        _update_status(run_id, "failed")
    finally:
        # Always release semaphore
        _semaphore.release()
        logger.debug(f"[{run_id[:8]}] Released semaphore")


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

    logger.info(f"[{run_id[:8]}] Enqueued run for job {job_id} (source={source})")
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


# ============================================================================
# PDF Generation Endpoint (Phase 4 - CV Editor)
# ============================================================================

@app.post("/api/jobs/{job_id}/cv-editor/pdf", dependencies=[Depends(verify_token)])
async def generate_cv_pdf(job_id: str):
    """
    Generate PDF from CV editor state using Playwright (Phase 4).

    This endpoint:
    1. Fetches cv_editor_state from MongoDB
    2. Converts TipTap JSON to HTML with Phase 2+3 styles
    3. Generates PDF using Playwright with proper page settings
    4. Returns PDF as downloadable attachment

    Args:
        job_id: MongoDB ObjectId of the job

    Returns:
        StreamingResponse with PDF binary data
    """
    from io import BytesIO
    from playwright.sync_api import sync_playwright
    from bson import ObjectId
    from pymongo import MongoClient
    from .pdf_helpers import (
        tiptap_json_to_html,
        build_pdf_html_template,
        sanitize_for_path
    )

    # Get MongoDB connection
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise HTTPException(status_code=500, detail="MongoDB not configured")

    try:
        client = MongoClient(mongo_uri)
        db = client[os.getenv("MONGO_DB_NAME", "job_search")]
        collection = db["level-2"]

        # Validate and fetch job
        try:
            object_id = ObjectId(job_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid job ID format")

        job = collection.find_one({"_id": object_id})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get editor state (or use default if not present)
        editor_state = job.get("cv_editor_state")
        if not editor_state or not editor_state.get("content"):
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

        # Convert TipTap JSON to HTML with recursion protection
        try:
            html_content = tiptap_json_to_html(editor_state["content"])
        except RecursionError as e:
            logger.error(f"Recursion error in PDF generation for job {job_id}: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="CV document structure is too deeply nested. Please simplify the document structure and try again."
            )
        except Exception as e:
            logger.error(f"Error converting TipTap JSON to HTML for job {job_id}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process CV content: {str(e)}"
            )

        # Get document styles
        doc_styles = editor_state.get("documentStyles", {})
        page_size = doc_styles.get("pageSize", "letter")
        margins = doc_styles.get("margins", {"top": 1.0, "right": 1.0, "bottom": 1.0, "left": 1.0})
        line_height = doc_styles.get("lineHeight", 1.15)
        font_family = doc_styles.get("fontFamily", "Inter")
        font_size = doc_styles.get("fontSize", 11)

        # Get header and footer
        header_text = editor_state.get("header", "")
        footer_text = editor_state.get("footer", "")

        # Build complete HTML document with styles
        full_html = build_pdf_html_template(
            html_content,
            font_family,
            font_size,
            line_height,
            header_text,
            footer_text
        )

        # Generate PDF using Playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            # Set HTML content
            page.set_content(full_html, wait_until='networkidle')

            # Wait for fonts to load
            page.wait_for_load_state('networkidle')

            # Generate PDF with settings from Phase 3
            pdf_format = 'A4' if page_size == 'a4' else 'Letter'
            pdf_bytes = page.pdf(
                format=pdf_format,
                print_background=True,
                margin={
                    'top': f"{margins.get('top', 1.0)}in",
                    'right': f"{margins.get('right', 1.0)}in",
                    'bottom': f"{margins.get('bottom', 1.0)}in",
                    'left': f"{margins.get('left', 1.0)}in"
                }
            )

            browser.close()

        # Build filename: CV_<Company>_<Title>.pdf
        company_clean = sanitize_for_path(job.get("company", "Company"))
        title_clean = sanitize_for_path(job.get("title", "Position"))
        filename = f"CV_{company_clean}_{title_clean}.pdf"

        # Return PDF as streaming response
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF generation failed for job {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")
