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

            # Stream response to client
            for line in response.iter_lines():
                if line:
                    # Forward SSE data to client
                    yield line.decode("utf-8") + "\n\n"

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
# Streaming Operation Proxy Routes (SSE Support for Small Actions)
# =============================================================================


@runner_bp.route("/operations/<job_id>/research-company/stream", methods=["POST"])
def research_company_stream(job_id: str):
    """
    Start company research with SSE streaming.

    Returns run_id immediately; client should connect to log_stream_url for SSE.
    """
    try:
        data = request.get_json() or {}

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/{job_id}/research-company/stream",
            json=data,
            headers=get_headers(),
            timeout=STREAMING_KICKOFF_TIMEOUT,  # Longer timeout for streaming init
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout starting research"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/operations/<job_id>/generate-cv/stream", methods=["POST"])
def generate_cv_stream(job_id: str):
    """
    Start CV generation with SSE streaming.

    Returns run_id immediately; client should connect to log_stream_url for SSE.
    """
    try:
        data = request.get_json() or {}

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/{job_id}/generate-cv/stream",
            json=data,
            headers=get_headers(),
            timeout=STREAMING_KICKOFF_TIMEOUT,  # Longer timeout for streaming init
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout starting CV generation"}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot connect to runner service"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@runner_bp.route("/operations/<job_id>/full-extraction/stream", methods=["POST"])
def full_extraction_stream(job_id: str):
    """
    Start full JD extraction with SSE streaming.

    Returns run_id immediately; client should connect to log_stream_url for SSE.
    """
    try:
        data = request.get_json() or {}

        response = requests.post(
            f"{RUNNER_URL}/api/jobs/{job_id}/full-extraction/stream",
            json=data,
            headers=get_headers(),
            timeout=STREAMING_KICKOFF_TIMEOUT,  # Longer timeout for streaming init
        )

        return jsonify(response.json()), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"error": "Runner service timeout starting full-extraction"}), 504
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

            for line in response.iter_lines():
                if line:
                    yield line.decode("utf-8") + "\n\n"

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
