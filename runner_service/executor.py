"""
Pipeline Executor Module

Handles subprocess execution of the job pipeline with:
- Real-time log streaming
- Timeout management
- Exit code capture
- Artifact discovery
- Error bubbling with full stack traces
"""

import asyncio
import json
import logging
import os
import traceback
from pathlib import Path
from typing import Dict, Optional

from .config import settings

logger = logging.getLogger(__name__)

# Use validated timeout from config
PIPELINE_TIMEOUT = settings.pipeline_timeout_seconds


async def execute_pipeline(
    job_id: str,
    profile_ref: Optional[str],
    log_callback,
    processing_tier: Optional[str] = "auto",
    process_callback: Optional[callable] = None,
) -> tuple[bool, Dict[str, str], Optional[Dict]]:
    """
    Execute the pipeline as a subprocess and stream logs.

    Args:
        job_id: Job identifier to process
        profile_ref: Optional profile path to pass to pipeline
        log_callback: Function to call with each log line (e.g., _append_log)
        processing_tier: Processing tier (auto, A, B, C, D) - GAP-045
        process_callback: Optional callback to receive process handle for cancellation support

    Returns:
        Tuple of (success: bool, artifacts: Dict[str, str], pipeline_state: Optional[Dict])
    """
    try:
        # Build command
        cmd = [
            "python",
            "scripts/run_pipeline.py",
            "--job-id",
            job_id,
        ]

        if profile_ref:
            cmd.extend(["--profile", profile_ref])

        # GAP-045: Add processing tier
        if processing_tier:
            cmd.extend(["--tier", processing_tier])

        log_callback(f"Executing: {' '.join(cmd)}")

        # Create subprocess with stdout/stderr piped
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
            env={**os.environ},  # Inherit environment variables
        )

        # Register process for cancellation support
        if process_callback:
            process_callback(process)

        # Stream output line by line
        if process.stdout:
            async for line in process.stdout:
                decoded_line = line.decode().strip()
                if decoded_line:  # Skip empty lines
                    log_callback(decoded_line)

        # Wait for process to complete with timeout
        try:
            await asyncio.wait_for(process.wait(), timeout=PIPELINE_TIMEOUT)
        except asyncio.TimeoutError:
            # Kill the process on timeout
            process.kill()
            await process.wait()
            log_callback(f"❌ Pipeline timed out after {PIPELINE_TIMEOUT}s")
            return False, {}, None

        # Check exit code
        if process.returncode == 0:
            log_callback("✅ Pipeline completed successfully")
            artifacts = discover_artifacts(job_id)
            # Load pipeline state for persistence to MongoDB
            pipeline_state = load_pipeline_state(job_id)
            if pipeline_state:
                log_callback(f"📊 Loaded pipeline state with {len(pipeline_state)} fields")
            return True, artifacts, pipeline_state
        else:
            log_callback(f"❌ Pipeline failed with exit code {process.returncode}")
            return False, {}, None

    except Exception as exc:
        # Capture full traceback for frontend display
        tb_str = traceback.format_exc()
        error_msg = f"{type(exc).__name__}: {str(exc)}"

        # Emit structured error log with traceback
        error_log = json.dumps({
            "event": "pipeline_error",
            "error": error_msg,
            "metadata": {
                "error_type": type(exc).__name__,
                "traceback": tb_str,
                "context": "Pipeline executor exception",
            }
        })
        log_callback(error_log)

        # Also emit human-readable message
        log_callback(f"❌ Pipeline execution error: {error_msg}")
        log_callback(f"📋 Traceback:\n{tb_str}")

        return False, {}, None


def discover_artifacts(job_id: str) -> Dict[str, str]:
    """
    Discover generated artifacts for a job.

    Scans the applications/<company>/<role>/ directory for generated files.

    Args:
        job_id: Job identifier

    Returns:
        Dictionary mapping artifact types to relative URLs
    """
    # The pipeline creates: applications/<company>/<role>/
    # We need to search for directories matching this job

    applications_dir = Path("applications")
    if not applications_dir.exists():
        return {}

    artifacts = {}

    # Search for job-specific directories
    # The pipeline typically creates a folder structure like:
    # applications/CompanyName/RoleName/
    # We'll search for common artifact files

    artifact_files = {
        "cv_md_url": "CV.md",
        "cv_docx_url": "CV.docx",
        "dossier_txt_url": "dossier.txt",
        "cover_letter_txt_url": "cover_letter.txt",
    }

    # Search all subdirectories for these files
    for company_dir in applications_dir.iterdir():
        if not company_dir.is_dir():
            continue

        for role_dir in company_dir.iterdir():
            if not role_dir.is_dir():
                continue

            # Check if any files in this directory reference our job_id
            # or if this is the most recent directory (for now, use simple heuristic)
            for artifact_key, filename in artifact_files.items():
                file_path = role_dir / filename
                if file_path.exists():
                    # Build relative URL for artifact endpoint
                    # Format: /artifacts/{run_id}/{filename}
                    # Store just the filename for the artifact endpoint
                    artifacts[artifact_key] = filename

    return artifacts


def load_pipeline_state(job_id: str) -> Optional[Dict]:
    """
    Load the pipeline state from the JSON file written by the pipeline.

    Args:
        job_id: Job identifier

    Returns:
        Dictionary with pipeline state or None if not found
    """
    import json

    state_file = Path(f".pipeline_state_{job_id}.json")
    if not state_file.exists():
        return None

    try:
        state_data = json.loads(state_file.read_text())
        # Clean up the state file after reading
        state_file.unlink()
        return state_data
    except Exception as e:
        logger.warning(f"Failed to load pipeline state for job {job_id}: {e}")
        return None


def get_artifact_path(job_id: str, filename: str) -> Optional[Path]:
    """
    Get the full path to a specific artifact file.

    Args:
        job_id: Job identifier
        filename: Name of the artifact file

    Returns:
        Path object if file exists, None otherwise
    """
    applications_dir = Path("applications")
    if not applications_dir.exists():
        return None

    # Search for the file in any company/role subdirectory
    for company_dir in applications_dir.iterdir():
        if not company_dir.is_dir():
            continue

        for role_dir in company_dir.iterdir():
            if not role_dir.is_dir():
                continue

            file_path = role_dir / filename
            if file_path.exists():
                return file_path.resolve()

    return None
