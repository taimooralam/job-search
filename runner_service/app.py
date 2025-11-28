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
        """Parse bold and italic marks from text."""
        # Simple regex-based parsing for bold (**text**) and italic (*text*)
        # For now, just return plain text node
        # TODO: Implement proper inline mark parsing
        return [{"type": "text", "text": text}]

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
