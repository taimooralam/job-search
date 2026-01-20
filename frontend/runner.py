"""
Runner API Proxy Blueprint.

Proxies requests from the frontend to the VPS runner service.
This approach centralizes authentication and avoids CORS complexity.
"""

import os
from typing import Generator

import requests
from dotenv import load_dotenv
from flask import Blueprint, Response, jsonify, request, stream_with_context

# Load environment variables
load_dotenv()

# Create blueprint
runner_bp = Blueprint("runner", __name__, url_prefix="/api/runner")

# Configuration
RUNNER_URL = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
RUNNER_API_SECRET = os.getenv("RUNNER_API_SECRET", "")
REQUEST_TIMEOUT = 30  # seconds for quick operations
STREAMING_KICKOFF_TIMEOUT = 60  # seconds for starting streaming operations (job validation + init)


def get_headers():
    """Get headers for runner API requests including Bearer token."""
    return {
        "Authorization": f"Bearer {RUNNER_API_SECRET}",
        "Content-Type": "application/json",
    }


@runner_bp.route("/jobs/run", methods=["POST"])
def run_single_job():
    """
    Trigger pipeline for a single job.

    Request Body:
        job_id: MongoDB job ID
        level: Processing level (1 or 2)
        debug: Optional boolean - enable verbose debug logging

    Returns:
        JSON with run_id and status
    """
    try:
        data = request.get_json()
        if not data or "job_id" not in data:
            return jsonify({"error": "job_id is required"}), 400

        # Ensure debug flag is included in request (defaults to False)
        if "debug" not in data:
            data["debug"] = False

        # Proxy request to runner service
        response = requests.post(
            f"{RUNNER_URL}/jobs/run",
            json=data,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        # Return runner's response
        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/run-bulk", methods=["POST"])
def run_bulk_jobs():
    """
    Trigger pipeline for multiple jobs.

    Request Body:
        job_ids: List of MongoDB job IDs
        level: Processing level (1 or 2)
        debug: Optional boolean - enable verbose debug logging

    Returns:
        JSON with run_ids array
    """
    try:
        data = request.get_json()
        if not data or "job_ids" not in data:
            return jsonify({"error": "job_ids array is required"}), 400

        # Ensure debug flag is included in request (defaults to False)
        if "debug" not in data:
            data["debug"] = False

        # Proxy request to runner service
        response = requests.post(
            f"{RUNNER_URL}/jobs/run-bulk",
            json=data,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        # Return runner's response
        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/<run_id>/status", methods=["GET"])
def get_run_status(run_id: str):
    """
    Get status of a pipeline run.

    Returns:
        JSON with run status, progress, and artifacts
    """
    try:
        # Proxy request to runner service
        response = requests.get(
            f"{RUNNER_URL}/jobs/{run_id}/status",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        # Return runner's response
        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/<run_id>/cancel", methods=["POST"])
def cancel_run(run_id: str):
    """
    Cancel a running pipeline.

    Sends SIGKILL to the subprocess and discards all partial results.

    Returns:
        JSON with cancellation result
    """
    try:
        response = requests.post(
            f"{RUNNER_URL}/jobs/{run_id}/cancel",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/<run_id>/progress", methods=["GET"])
def get_run_progress(run_id: str):
    """
    Get detailed layer-by-layer progress of a pipeline run.

    Returns:
        JSON with run progress, layer status, and completion percentage
    """
    try:
        # Proxy request to runner service
        response = requests.get(
            f"{RUNNER_URL}/jobs/{run_id}/progress",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        # Return runner's response
        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/<run_id>/logs", methods=["GET"])
def stream_logs(run_id: str):
    """
    Stream real-time logs from a pipeline run via Server-Sent Events.

    Returns:
        SSE stream of log lines
    """
    def generate() -> Generator[str, None, None]:
        """Generate SSE stream from runner service."""
        try:
            # Stream logs from runner service
            response = requests.get(
                f"{RUNNER_URL}/jobs/{run_id}/logs",
                headers=get_headers(),
                stream=True,
                timeout=300,  # Longer timeout for streaming
            )

            # Stream response to client using iter_content for real-time delivery
            # iter_content(chunk_size=None) yields data as it arrives without buffering
            buffer = ""
            for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                if chunk:
                    buffer += chunk
                    # Process complete SSE events (ending with double newline)
                    while "\n\n" in buffer:
                        event, buffer = buffer.split("\n\n", 1)
                        yield event + "\n\n"

        except requests.exceptions.Timeout:
            yield f"event: error\ndata: Runner service timeout\n\n"
        except requests.exceptions.ConnectionError:
            yield f"event: error\ndata: Cannot connect to runner service\n\n"
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable proxy buffering
        },
    )


@runner_bp.route("/jobs/<run_id>/artifacts/<artifact_name>", methods=["GET"])
def download_artifact(run_id: str, artifact_name: str):
    """
    Download an artifact from a completed pipeline run.

    Returns:
        File download or error
    """
    try:
        # Proxy request to runner service
        response = requests.get(
            f"{RUNNER_URL}/artifacts/{run_id}/{artifact_name}",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
            stream=True,
        )

        # Check if successful
        if response.status_code != 200:
            return jsonify({"error": "Artifact not found"}), response.status_code

        # Stream file to client
        return Response(
            response.iter_content(chunk_size=8192),
            content_type=response.headers.get("Content-Type", "application/octet-stream"),
            headers={
                "Content-Disposition": response.headers.get(
                    "Content-Disposition", f'attachment; filename="{artifact_name}"'
                )
            },
        )

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/health", methods=["GET"])
def health_check():
    """
    Check if runner service is healthy.

    Returns:
        JSON with runner service health status
    """
    try:
        # Check runner service health
        response = requests.get(
            f"{RUNNER_URL}/health",
            timeout=5,
        )

        return jsonify({
            "status": "healthy" if response.status_code == 200 else "unhealthy",
            "runner_url": RUNNER_URL,
            "runner_response": response.json() if response.status_code == 200 else None,
        }), 200

    except requests.exceptions.Timeout:
        return jsonify({
            "status": "unhealthy",
            "error": "Runner service timeout",
            "runner_url": RUNNER_URL,
        }), 503
    except requests.exceptions.ConnectionError:
        return jsonify({
            "status": "unhealthy",
            "error": "Cannot connect to runner service",
            "runner_url": RUNNER_URL,
        }), 503
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "runner_url": RUNNER_URL,
        }), 503


# =============================================================================
# Operation Start Proxy Routes (New Canonical Names)
# =============================================================================
# NOTE: The /stream endpoints are deprecated in favor of /start.
# These endpoints initiate background operations and return a run_id for
# HTTP polling (NOT Server-Sent Events streaming).


@runner_bp.route("/operations/<job_id>/research-company/start", methods=["POST"])
@runner_bp.route("/operations/<job_id>/research-company/stream", methods=["POST"])  # Deprecated alias
def research_company_start(job_id: str):
    """
    Start company research operation.

    Returns run_id immediately; client should poll /api/runner/logs/{run_id} for progress.
    NOTE: /stream is deprecated, use /start instead.
    """
    try:
        data = request.get_json() or {}

        # Use /start endpoint on backend (handles both /start and /stream)
        response = requests.post(
            f"{RUNNER_URL}/api/jobs/{job_id}/research-company/start",
            json=data,
            headers=get_headers(),
            timeout=STREAMING_KICKOFF_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout starting research"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/operations/<job_id>/generate-cv/start", methods=["POST"])
@runner_bp.route("/operations/<job_id>/generate-cv/stream", methods=["POST"])  # Deprecated alias
def generate_cv_start(job_id: str):
    """
    Start CV generation operation.

    Returns run_id immediately; client should poll /api/runner/logs/{run_id} for progress.
    NOTE: /stream is deprecated, use /start instead.
    """
    try:
        data = request.get_json() or {}

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/{job_id}/generate-cv/start",
            json=data,
            headers=get_headers(),
            timeout=STREAMING_KICKOFF_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout starting CV generation"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/operations/<job_id>/full-extraction/start", methods=["POST"])
@runner_bp.route("/operations/<job_id>/full-extraction/stream", methods=["POST"])  # Deprecated alias
def full_extraction_start(job_id: str):
    """
    Start full JD extraction operation.

    Returns run_id immediately; client should poll /api/runner/logs/{run_id} for progress.
    NOTE: /stream is deprecated, use /start instead.
    """
    try:
        data = request.get_json() or {}

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/{job_id}/full-extraction/start",
            json=data,
            headers=get_headers(),
            timeout=STREAMING_KICKOFF_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout starting full-extraction"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/operations/<job_id>/scrape-form-answers/start", methods=["POST"])
@runner_bp.route("/operations/<job_id>/scrape-form-answers/stream", methods=["POST"])  # Deprecated alias
def scrape_form_answers_start(job_id: str):
    """
    Start form scraping and answer generation operation.

    Returns run_id immediately; client should poll /api/runner/logs/{run_id} for progress.
    NOTE: /stream is deprecated, use /start instead.
    """
    try:
        data = request.get_json() or {}

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/{job_id}/scrape-form-answers/start",
            json=data,
            headers=get_headers(),
            timeout=STREAMING_KICKOFF_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout starting scrape-form-answers"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route(
    "/contacts/<job_id>/<contact_type>/<int:contact_index>/generate-outreach/stream",
    methods=["POST"],
)
def generate_outreach_stream(job_id: str, contact_type: str, contact_index: int):
    """
    Start outreach generation with SSE streaming.

    Returns run_id immediately; client should connect to log_stream_url for SSE.
    """
    try:
        data = request.get_json() or {}

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/{job_id}/contacts/{contact_type}/{contact_index}/generate-outreach/stream",
            json=data,
            headers=get_headers(),
            timeout=STREAMING_KICKOFF_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout starting outreach generation"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/operations/<run_id>/logs", methods=["GET"])
def stream_operation_logs(run_id: str):
    """
    Stream real-time logs from an operation run via Server-Sent Events.

    This is the SSE endpoint for streaming operation progress.
    """
    def generate() -> Generator[str, None, None]:
        """Generate SSE stream from runner service."""
        try:
            response = requests.get(
                f"{RUNNER_URL}/api/jobs/operations/{run_id}/logs",
                headers=get_headers(),
                stream=True,
                timeout=300,  # Longer timeout for streaming
            )

            # Stream response to client using iter_content for real-time delivery
            # iter_content(chunk_size=None) yields data as it arrives without buffering
            buffer = ""
            for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                if chunk:
                    buffer += chunk
                    # Process complete SSE events (ending with double newline)
                    while "\n\n" in buffer:
                        event, buffer = buffer.split("\n\n", 1)
                        yield event + "\n\n"

        except requests.exceptions.Timeout:
            yield f"event: error\ndata: Runner service timeout\n\n"
        except requests.exceptions.ConnectionError:
            yield f"event: error\ndata: Cannot connect to runner service\n\n"
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@runner_bp.route("/operations/<run_id>/status", methods=["GET"])
def get_operation_status(run_id: str):
    """
    Get current status of an operation run.

    Fallback for polling-based status checks.
    """
    try:
        response = requests.get(
            f"{RUNNER_URL}/api/jobs/operations/{run_id}/status",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/operations/<run_id>/logs/redis", methods=["GET"])
def get_operation_redis_logs(run_id: str):
    """
    Get operation logs from Redis persistence.

    Fetches logs from Redis cache (24h TTL) for completed runs.
    Useful when in-memory logs are unavailable after service restart.
    """
    try:
        response = requests.get(
            f"{RUNNER_URL}/api/jobs/operations/{run_id}/logs/redis",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Queue Management Routes (Redis-backed real-time queue)
# =============================================================================


@runner_bp.route("/queue/state", methods=["GET"])
def get_queue_state():
    """
    Get current queue state from runner service.

    Returns queue state with pending, running, failed, and history items.
    This is a REST fallback for WebSocket-based updates.
    """
    try:
        response = requests.get(
            f"{RUNNER_URL}/queue/state",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/logs/<run_id>", methods=["GET"])
def poll_logs(run_id: str):
    """
    Poll logs for a pipeline operation.

    Proxies to runner service's /api/logs/{run_id} endpoint.
    Supports ?since=N&limit=M query parameters for pagination.
    """
    try:
        # Forward query parameters
        params = {
            "since": request.args.get("since", 0),
            "limit": request.args.get("limit", 100),
        }
        response = requests.get(
            f"{RUNNER_URL}/api/logs/{run_id}",
            headers=get_headers(),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/logs/<run_id>/status", methods=["GET"])
def get_log_status(run_id: str):
    """
    Get status for a pipeline operation (without logs).

    Proxies to runner service's /api/logs/{run_id}/status endpoint.
    """
    try:
        response = requests.get(
            f"{RUNNER_URL}/api/logs/{run_id}/status",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/queue/<queue_id>/retry", methods=["POST"])
def retry_queue_item(queue_id: str):
    """
    Retry a failed queue item.

    Moves the item back to the pending queue for re-execution.
    """
    try:
        response = requests.post(
            f"{RUNNER_URL}/queue/{queue_id}/retry",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/queue/<queue_id>/cancel", methods=["POST"])
def cancel_queue_item(queue_id: str):
    """
    Cancel a pending queue item.

    Removes the item from the queue without execution.
    """
    try:
        response = requests.post(
            f"{RUNNER_URL}/queue/{queue_id}/cancel",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/queue/<queue_id>/dismiss", methods=["POST"])
def dismiss_queue_item(queue_id: str):
    """
    Dismiss a failed queue item.

    Removes from failed list without retry, moves to history.
    """
    try:
        response = requests.post(
            f"{RUNNER_URL}/queue/{queue_id}/dismiss",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/queue/item/<job_id>", methods=["GET"])
def get_queue_item_by_job(job_id: str):
    """
    Get queue item by job ID.

    Useful for checking if a job is currently queued or running.
    """
    try:
        response = requests.get(
            f"{RUNNER_URL}/queue/item/{job_id}",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Batch Operation Proxy Routes (New Canonical Names)
# =============================================================================
# NOTE: The /bulk endpoints are deprecated in favor of /batch.


@runner_bp.route("/jobs/full-extraction/batch", methods=["POST"])
@runner_bp.route("/jobs/full-extraction/bulk", methods=["POST"])  # Deprecated alias
def full_extraction_batch():
    """
    Start full extraction for multiple jobs.

    Request Body:
        job_ids: List of MongoDB job IDs
        tier: Processing tier (fast, balanced, quality)
        use_llm: Whether to use LLM (default True)

    Returns:
        JSON with runs array containing run_ids for each job

    NOTE: /bulk is deprecated, use /batch instead.
    """
    try:
        data = request.get_json()
        if not data or "job_ids" not in data:
            return jsonify({"error": "job_ids array is required"}), 400

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/full-extraction/batch",
            json=data,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/research-company/batch", methods=["POST"])
@runner_bp.route("/jobs/research-company/bulk", methods=["POST"])  # Deprecated alias
def research_company_batch():
    """
    Start company research for multiple jobs.

    Request Body:
        job_ids: List of MongoDB job IDs
        tier: Processing tier (fast, balanced, quality)
        force_refresh: Whether to force refresh (default False)

    Returns:
        JSON with runs array containing run_ids for each job

    NOTE: /bulk is deprecated, use /batch instead.
    """
    try:
        data = request.get_json()
        if not data or "job_ids" not in data:
            return jsonify({"error": "job_ids array is required"}), 400

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/research-company/batch",
            json=data,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/generate-cv/batch", methods=["POST"])
@runner_bp.route("/jobs/generate-cv/bulk", methods=["POST"])  # Deprecated alias
def generate_cv_batch():
    """
    Start CV generation for multiple jobs.

    Request Body:
        job_ids: List of MongoDB job IDs
        tier: Processing tier (fast, balanced, quality)

    Returns:
        JSON with runs array containing run_ids for each job

    NOTE: /bulk is deprecated, use /batch instead.
    """
    try:
        data = request.get_json()
        if not data or "job_ids" not in data:
            return jsonify({"error": "job_ids array is required"}), 400

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/generate-cv/batch",
            json=data,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Queue-Based Operation Endpoints (Job Detail Page)
# =============================================================================


@runner_bp.route("/jobs/<job_id>/operations/<operation>/queue", methods=["POST"])
def queue_operation(job_id: str, operation: str):
    """
    Queue a pipeline operation for background execution.

    This is the queue-first approach for the job detail page:
    - Adds operation to Redis queue
    - Status updates via WebSocket
    - User can view logs on-demand

    Request Body:
        tier: Processing tier (fast, balanced, quality)
        force_refresh: Whether to force refresh (for company research)
        use_llm: Whether to use LLM (for extraction)
        use_annotations: Whether to use annotations (for CV generation)

    Returns:
        JSON with queue_id, position, and estimated wait time
    """
    try:
        data = request.get_json() or {}

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/{job_id}/operations/{operation}/queue",
            json=data,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/<job_id>/queue-status", methods=["GET"])
def get_job_queue_status(job_id: str):
    """
    Get queue status for all operations on a specific job.

    Used by the frontend pipelines panel to show current status
    of each operation type (full-extraction, research-company, generate-cv).

    Returns:
        JSON with status for each operation type
    """
    try:
        response = requests.get(
            f"{RUNNER_URL}/api/jobs/{job_id}/queue-status",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# All Ops Endpoints (Full Pipeline: Extract + Research + Generate CV)
# =============================================================================


@runner_bp.route("/jobs/<job_id>/all-ops/start", methods=["POST"])
@runner_bp.route("/jobs/<job_id>/all-ops/stream", methods=["POST"])  # Deprecated alias
def all_ops_start(job_id: str):
    """
    Start all operations for a single job.

    Runs the complete pipeline:
    - Full extraction (Layer 1.4 + Layer 2 + Layer 4)
    - Company research
    - CV generation

    Request Body:
        tier: Processing tier (fast, balanced, quality)

    Returns:
        JSON with run_id for tracking the operation

    NOTE: /stream is deprecated, use /start instead.
    """
    try:
        data = request.get_json() or {}

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/{job_id}/all-ops/start",
            json=data,
            headers=get_headers(),
            timeout=STREAMING_KICKOFF_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/all-ops/batch", methods=["POST"])
@runner_bp.route("/jobs/all-ops/bulk", methods=["POST"])  # Deprecated alias
def all_ops_batch():
    """
    Start all operations for multiple jobs.

    Runs the complete pipeline for each job:
    - Full extraction (Layer 1.4 + Layer 2 + Layer 4)
    - Company research
    - CV generation

    Request Body:
        job_ids: List of MongoDB job IDs
        tier: Processing tier (fast, balanced, quality)

    Returns:
        JSON with runs array containing run_ids for each job

    NOTE: /bulk is deprecated, use /batch instead.
    """
    try:
        data = request.get_json()
        if not data or "job_ids" not in data:
            return jsonify({"error": "job_ids array is required"}), 400

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/all-ops/batch",
            json=data,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Job Ingestion Routes
# =============================================================================


@runner_bp.route("/jobs/ingest/himalaya", methods=["POST"])
def ingest_himalaya_jobs():
    """
    Trigger Himalaya job ingestion on-demand.

    Query Parameters:
        keywords: List of keywords to filter jobs
        max_results: Maximum jobs to fetch (default 50, max 100)
        worldwide_only: Only fetch worldwide remote jobs (default true)
        skip_scoring: Skip LLM scoring for faster testing
        incremental: Only fetch jobs newer than last run (default true)
        score_threshold: Minimum score for ingestion (default 70)

    Returns:
        JSON with ingestion stats and list of ingested jobs
    """
    try:
        # Build query params from request args
        params = {}
        if request.args.get("keywords"):
            params["keywords"] = request.args.getlist("keywords")
        if request.args.get("max_results"):
            params["max_results"] = request.args.get("max_results")
        if request.args.get("worldwide_only"):
            params["worldwide_only"] = request.args.get("worldwide_only")
        if request.args.get("skip_scoring"):
            params["skip_scoring"] = request.args.get("skip_scoring")
        if request.args.get("incremental"):
            params["incremental"] = request.args.get("incremental")
        if request.args.get("score_threshold"):
            params["score_threshold"] = request.args.get("score_threshold")

        response = requests.post(
            f"{RUNNER_URL}/jobs/ingest/himalaya",
            headers=get_headers(),
            params=params,
            timeout=120,  # Longer timeout for ingestion
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Ingestion timeout - operation may still be running"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/ingest/indeed", methods=["POST"])
def ingest_indeed_jobs():
    """
    Trigger Indeed job ingestion on-demand.

    Query Parameters:
        search_term: Job search query
        location: Location to search in
        country: Country code (e.g., 'us', 'uk')
        max_results: Maximum jobs to fetch (default 50, max 100)
        hours_old: Only fetch jobs posted within this many hours
        skip_scoring: Skip LLM scoring for faster testing
        incremental: Only fetch jobs newer than last run (default true)
        score_threshold: Minimum score for ingestion (default 70)

    Returns:
        JSON with ingestion stats and list of ingested jobs
    """
    try:
        # Build query params from request args
        params = {}
        if request.args.get("search_term"):
            params["search_term"] = request.args.get("search_term")
        if request.args.get("location"):
            params["location"] = request.args.get("location")
        if request.args.get("country"):
            params["country"] = request.args.get("country")
        if request.args.get("max_results"):
            params["max_results"] = request.args.get("max_results")
        if request.args.get("hours_old"):
            params["hours_old"] = request.args.get("hours_old")
        if request.args.get("skip_scoring"):
            params["skip_scoring"] = request.args.get("skip_scoring")
        if request.args.get("incremental"):
            params["incremental"] = request.args.get("incremental")
        if request.args.get("score_threshold"):
            params["score_threshold"] = request.args.get("score_threshold")

        response = requests.post(
            f"{RUNNER_URL}/jobs/ingest/indeed",
            headers=get_headers(),
            params=params,
            timeout=120,  # Longer timeout for ingestion
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Ingestion timeout - operation may still be running"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/ingest/bayt", methods=["POST"])
def ingest_bayt_jobs():
    """
    Trigger Bayt job ingestion on-demand.

    Query Parameters:
        search_term: Job search query
        max_results: Maximum jobs to fetch (default 50, max 100)
        skip_scoring: Skip LLM scoring for faster testing
        incremental: Only fetch jobs newer than last run (default true)
        score_threshold: Minimum score for ingestion (default 70)

    Returns:
        JSON with ingestion stats and list of ingested jobs
    """
    try:
        # Build query params from request args
        params = {}
        if request.args.get("search_term"):
            params["search_term"] = request.args.get("search_term")
        if request.args.get("max_results"):
            params["max_results"] = request.args.get("max_results")
        if request.args.get("skip_scoring"):
            params["skip_scoring"] = request.args.get("skip_scoring")
        if request.args.get("incremental"):
            params["incremental"] = request.args.get("incremental")
        if request.args.get("score_threshold"):
            params["score_threshold"] = request.args.get("score_threshold")

        response = requests.post(
            f"{RUNNER_URL}/jobs/ingest/bayt",
            headers=get_headers(),
            params=params,
            timeout=120,  # Longer timeout for ingestion
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Ingestion timeout - operation may still be running"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/ingest/<run_id>/result", methods=["GET"])
def get_ingest_result(run_id: str):
    """
    Get the result of an ingestion operation.

    Used by the frontend to fetch final results after log polling completes.

    Returns:
        JSON with ingestion result (stats, ingested jobs, etc.)
    """
    try:
        response = requests.get(
            f"{RUNNER_URL}/jobs/ingest/{run_id}/result",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/ingest/state/<source>", methods=["GET"])
def get_ingest_state(source: str):
    """
    Get the current ingestion state for a source.

    Returns last fetch timestamp and stats from previous run.
    """
    try:
        response = requests.get(
            f"{RUNNER_URL}/jobs/ingest/state/{source}",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/ingest/state/<source>", methods=["DELETE"])
def reset_ingest_state(source: str):
    """
    Reset the ingestion state for a source.

    Use this to force a full (non-incremental) fetch on next run.
    """
    try:
        response = requests.delete(
            f"{RUNNER_URL}/jobs/ingest/state/{source}",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/jobs/ingest/history/<source>", methods=["GET"])
def get_ingest_history(source: str):
    """
    Get the ingestion run history for a source.

    Query Parameters:
        limit: Number of runs to return (default 20, max 50)

    Returns the last N runs with timestamps and stats.
    """
    try:
        params = {}
        if request.args.get("limit"):
            params["limit"] = request.args.get("limit")

        response = requests.get(
            f"{RUNNER_URL}/jobs/ingest/history/{source}",
            headers=get_headers(),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Annotation Suggestion System Routes
# =============================================================================


@runner_bp.route("/jobs/<job_id>/generate-annotations", methods=["POST"])
def generate_annotations(job_id: str):
    """
    Generate annotation suggestions for a job's structured JD.

    Uses sentence embeddings and skill priors to match JD items against
    historical annotation patterns. Only generates annotations for items
    that match the user's profile (skills, responsibilities, identity, passion).

    Returns:
        JSON with created/skipped counts and generated annotations
    """
    try:
        response = requests.post(
            f"{RUNNER_URL}/jobs/{job_id}/generate-annotations",
            headers=get_headers(),
            timeout=180,  # 3 min timeout for embedding loading + similarity computation
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Annotation generation timeout - embedding computation took too long"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/user/annotation-priors", methods=["GET"])
def get_annotation_priors():
    """
    Get statistics about annotation priors.

    Returns accuracy, coverage, and health metrics for the
    annotation suggestion system.
    """
    try:
        response = requests.get(
            f"{RUNNER_URL}/user/annotation-priors",
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/user/annotation-priors/rebuild", methods=["POST"])
def rebuild_annotation_priors():
    """
    Rebuild annotation priors from all historical annotations.

    Re-computes sentence embeddings and skill priors. Takes ~15-30 seconds
    for 3000 annotations.

    Returns:
        JSON with rebuild status and metrics
    """
    try:
        response = requests.post(
            f"{RUNNER_URL}/user/annotation-priors/rebuild",
            headers=get_headers(),
            timeout=120,  # Longer timeout for full rebuild
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Priors rebuild timeout - may still be running"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/user/annotation-feedback", methods=["POST"])
def capture_annotation_feedback():
    """
    Capture feedback from user editing or deleting an auto-generated annotation.

    This updates skill priors based on whether the user accepted,
    edited, or deleted the suggestion.

    Request Body:
        annotation_id: ID of the annotation
        action: "save" or "delete"
        original_values: Original suggested values
        final_values: Final values after user edit (only for "save")

    Returns:
        JSON with updated prior info
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        response = requests.post(
            f"{RUNNER_URL}/user/annotation-feedback",
            json=data,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500
