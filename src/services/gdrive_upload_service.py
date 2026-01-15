"""
Google Drive Upload Service

Provides reusable functions for uploading CV and dossier PDFs to Google Drive
via n8n webhook. These functions are designed to be called from both:
- Standalone HTTP endpoints (runner_service/routes/operations.py)
- BatchPipelineService (for unified logging with parent run_id)

Key differences from endpoint versions:
- Accept log_callback for streaming logs to parent's run_id
- Return dict instead of raising HTTPException
- No FastAPI dependencies

Usage:
    result = await upload_cv_to_gdrive(job_id, log_callback=log_cb)
    if result["success"]:
        print(f"Uploaded: {result['gdrive_file_id']}")
    else:
        print(f"Error: {result['error']}")
"""

import html as html_module
import logging
import os
from datetime import datetime
from io import BytesIO
from typing import Any, Callable, Dict, Optional

from bson import ObjectId

from src.common.repositories import get_job_repository

logger = logging.getLogger(__name__)


async def upload_cv_to_gdrive(
    job_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Upload CV PDF to Google Drive via n8n webhook.

    This function:
    1. Fetches job from MongoDB (company, title, cv_editor_state)
    2. Generates PDF via PDF service
    3. POSTs to n8n webhook with company_name, role_name, and PDF binary
    4. Updates MongoDB with gdrive_uploaded_at timestamp

    Args:
        job_id: MongoDB ObjectId of the job
        log_callback: Optional callback for logging (uses parent's run_id)

    Returns:
        Dict with: success, error, gdrive_file_id, gdrive_folder_id, uploaded_at
    """
    import httpx

    def _log(message: str) -> None:
        """Emit log to callback if provided."""
        logger.info(message)
        if log_callback:
            try:
                log_callback(message)
            except Exception as e:
                logger.warning(f"Log callback error: {e}")

    _log(f"Starting CV upload to Google Drive for job {job_id[:12]}...")

    # Get n8n webhook URL from environment
    n8n_webhook_url = os.getenv(
        "N8N_WEBHOOK_CV_UPLOAD",
        "https://n8n.srv1112039.hstgr.cloud/webhook/cv-upload",
    )
    pdf_service_url = os.getenv("PDF_SERVICE_URL", "http://pdf-service:8001")

    try:
        # Validate and fetch job
        repo = get_job_repository()
        job = repo.find_one({"_id": ObjectId(job_id)})
        if not job:
            return {"success": False, "error": f"Job not found: {job_id}"}

        company_name = job.get("company", "Unknown Company")
        role_name = job.get("title", "Unknown Role")
        webhook_job_id = str(job.get("jobId")) if job.get("jobId") is not None else job_id

        # Get editor state for PDF generation
        editor_state = job.get("cv_editor_state")

        # If no editor state, try to migrate from cv_text
        if not editor_state and job.get("cv_text"):
            # Import migration function
            from runner_service.app import migrate_cv_text_to_editor_state
            editor_state = migrate_cv_text_to_editor_state(job.get("cv_text"))

        if not editor_state:
            return {
                "success": False,
                "error": "No CV content available. Please generate or edit a CV first.",
            }

        _log(f"Generating PDF for {company_name} - {role_name}")

        # Build PDF request payload
        content = editor_state.get("content", [])
        if isinstance(content, list):
            tiptap_doc = {"type": "doc", "content": content}
        elif isinstance(content, dict) and content.get("type") == "doc":
            tiptap_doc = content
        else:
            tiptap_doc = {"type": "doc", "content": []}

        pdf_request = {
            "tiptap_json": tiptap_doc,
            "documentStyles": editor_state.get("documentStyles", {}),
            "header": editor_state.get("header", ""),
            "footer": editor_state.get("footer", ""),
            "company": company_name,
            "role": role_name,
        }

        async with httpx.AsyncClient(timeout=60.0) as http_client:
            # Step 1: Generate PDF
            pdf_response = await http_client.post(
                f"{pdf_service_url}/cv-to-pdf",
                json=pdf_request,
            )
            pdf_response.raise_for_status()
            pdf_content = pdf_response.content
            _log(f"PDF generated ({len(pdf_content)} bytes)")

            # Step 2: Upload to n8n webhook
            _log(f"Uploading to Google Drive...")

            files = {
                "data": (
                    "Taimoor Alam Resume.pdf",
                    BytesIO(pdf_content),
                    "application/pdf",
                ),
            }
            form_data = {
                "company_name": company_name,
                "role_name": role_name,
                "file_name": "Taimoor Alam Resume.pdf",
                "jobId": webhook_job_id,
            }

            upload_response = await http_client.post(
                n8n_webhook_url,
                files=files,
                data=form_data,
                timeout=30.0,
            )
            upload_response.raise_for_status()

            # Parse n8n response
            n8n_result = upload_response.json()
            _log(f"CV uploaded successfully to Google Drive")

            # Step 3: Update MongoDB with upload timestamp
            uploaded_at = datetime.utcnow()
            repo.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"gdrive_uploaded_at": uploaded_at}},
            )

            return {
                "success": True,
                "uploaded_at": uploaded_at.isoformat() + "Z",
                "message": "CV uploaded to Google Drive successfully",
                "gdrive_file_id": n8n_result.get("file_id"),
                "gdrive_folder_id": n8n_result.get("role_folder"),
            }

    except httpx.TimeoutException as e:
        error_msg = f"Upload timed out: {e}"
        logger.error(f"Timeout during CV Google Drive upload for job {job_id}: {e}")
        _log(f"Error: {error_msg}")
        return {"success": False, "error": error_msg}

    except httpx.HTTPStatusError as e:
        try:
            error_detail = e.response.json().get("detail", str(e))
        except Exception:
            error_detail = str(e)
        error_msg = f"HTTP {e.response.status_code}: {error_detail}"
        logger.error(f"HTTP error during CV upload for job {job_id}: {error_msg}")
        _log(f"Error: {error_msg}")
        return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Upload failed: {str(e)}"
        logger.error(f"CV Google Drive upload failed for job {job_id}: {e}")
        _log(f"Error: {error_msg}")
        return {"success": False, "error": error_msg}


async def upload_dossier_to_gdrive(
    job_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Upload dossier PDF to Google Drive via n8n webhook.

    This function:
    1. Fetches job from MongoDB (company, title, generated_dossier)
    2. Converts dossier text to HTML
    3. Generates PDF via pdf-service
    4. POSTs to n8n webhook with company_name, role_name, file_name, and PDF
    5. Updates MongoDB with dossier_gdrive_uploaded_at timestamp

    Args:
        job_id: MongoDB ObjectId of the job
        log_callback: Optional callback for logging (uses parent's run_id)

    Returns:
        Dict with: success, error, gdrive_file_id, gdrive_folder_id, uploaded_at
    """
    import httpx
    import sys

    def _log(message: str) -> None:
        """Emit log to callback if provided."""
        logger.info(message)
        if log_callback:
            try:
                log_callback(message)
            except Exception as e:
                logger.warning(f"Log callback error: {e}")

    _log(f"Starting dossier upload to Google Drive for job {job_id[:12]}...")

    # Import the filename generator from pdf_service
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from pdf_service.pdf_helpers import generate_dossier_filename

    n8n_webhook_url = os.getenv(
        "N8N_WEBHOOK_CV_UPLOAD",
        "https://n8n.srv1112039.hstgr.cloud/webhook/cv-upload",
    )
    pdf_service_url = os.getenv("PDF_SERVICE_URL", "http://pdf-service:8001")

    try:
        # Validate and fetch job
        repo = get_job_repository()
        job = repo.find_one({"_id": ObjectId(job_id)})
        if not job:
            return {"success": False, "error": f"Job not found: {job_id}"}

        company_name = job.get("company", "Unknown Company")
        role_name = job.get("title", "Unknown Role")
        webhook_job_id = str(job.get("jobId")) if job.get("jobId") is not None else job_id

        # Get generated dossier content OR generate best-effort from available data
        generated_dossier = job.get("generated_dossier")

        if not generated_dossier:
            # Import best-effort generator
            from runner_service.utils.best_effort_dossier import (
                generate_best_effort_dossier,
                has_minimum_dossier_data,
            )

            if not has_minimum_dossier_data(job):
                return {
                    "success": False,
                    "error": "Insufficient data for dossier. Need company, title, and job description or extracted JD.",
                }

            _log("Generating best-effort dossier from available data...")
            generated_dossier, sections_included = generate_best_effort_dossier(job)
            _log(f"Best-effort dossier generated with {len(sections_included)} sections")

        # Generate filename with timestamp
        file_name = generate_dossier_filename(company_name, role_name)
        _log(f"Generating dossier PDF: {file_name}")

        # Convert plain text dossier to simple HTML for PDF rendering
        escaped_dossier = html_module.escape(generated_dossier)

        dossier_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-size: 11pt;
            line-height: 1.5;
            margin: 40px;
            color: #333;
        }}
        pre {{
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: inherit;
        }}
    </style>
</head>
<body>
    <pre>{escaped_dossier}</pre>
</body>
</html>"""

        async with httpx.AsyncClient(timeout=60.0) as http_client:
            # Step 1: Generate PDF from dossier HTML
            pdf_response = await http_client.post(
                f"{pdf_service_url}/render-pdf",
                json={"html": dossier_html},
            )
            pdf_response.raise_for_status()
            pdf_content = pdf_response.content
            _log(f"Dossier PDF generated ({len(pdf_content)} bytes)")

            # Step 2: Upload to n8n webhook
            _log(f"Uploading dossier to Google Drive...")

            files = {
                "data": (
                    file_name,
                    BytesIO(pdf_content),
                    "application/pdf",
                ),
            }
            form_data = {
                "company_name": company_name,
                "role_name": role_name,
                "file_name": file_name,
                "jobId": webhook_job_id,
            }

            upload_response = await http_client.post(
                n8n_webhook_url,
                files=files,
                data=form_data,
                timeout=30.0,
            )
            upload_response.raise_for_status()

            # Parse n8n response
            n8n_result = upload_response.json()
            _log(f"Dossier uploaded successfully to Google Drive")

            # Step 3: Update MongoDB with upload timestamp
            uploaded_at = datetime.utcnow()
            repo.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"dossier_gdrive_uploaded_at": uploaded_at}},
            )

            return {
                "success": True,
                "uploaded_at": uploaded_at.isoformat() + "Z",
                "message": "Dossier uploaded to Google Drive successfully",
                "gdrive_file_id": n8n_result.get("file_id"),
                "gdrive_folder_id": n8n_result.get("role_folder"),
            }

    except httpx.TimeoutException as e:
        error_msg = f"Upload timed out: {e}"
        logger.error(f"Timeout during dossier Google Drive upload for job {job_id}: {e}")
        _log(f"Error: {error_msg}")
        return {"success": False, "error": error_msg}

    except httpx.HTTPStatusError as e:
        try:
            error_detail = e.response.json().get("detail", str(e))
        except Exception:
            error_detail = str(e)
        error_msg = f"HTTP {e.response.status_code}: {error_detail}"
        logger.error(f"HTTP error during dossier upload for job {job_id}: {error_msg}")
        _log(f"Error: {error_msg}")
        return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Upload failed: {str(e)}"
        logger.error(f"Dossier Google Drive upload failed for job {job_id}: {e}")
        _log(f"Error: {error_msg}")
        return {"success": False, "error": error_msg}
