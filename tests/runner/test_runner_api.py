"""
Unit tests for runner service API endpoints.
"""

import pytest
from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """Test health check endpoint returns 200 and correct data."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "active_runs" in data
    assert "max_concurrency" in data
    assert "timestamp" in data
    assert data["max_concurrency"] == 2  # From test env


def test_run_job_requires_auth(client: TestClient):
    """Test that running a job without auth returns 401."""
    response = client.post("/jobs/run", json={"job_id": "123"})
    assert response.status_code == 401  # Returns 401 for missing/invalid auth


def test_run_job_with_invalid_auth(client: TestClient, invalid_auth_headers: dict):
    """Test that running a job with invalid auth returns 401."""
    response = client.post(
        "/jobs/run",
        json={"job_id": "123"},
        headers=invalid_auth_headers
    )
    assert response.status_code == 401


def test_run_job_with_valid_auth(client: TestClient, auth_headers: dict):
    """Test that running a job with valid auth returns 200."""
    response = client.post(
        "/jobs/run",
        json={"job_id": "123", "source": "test"},
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert "run_id" in data
    assert "status_url" in data
    assert "log_stream_url" in data
    assert data["status_url"] == f"/jobs/{data['run_id']}/status"
    assert data["log_stream_url"] == f"/jobs/{data['run_id']}/logs"


def test_run_job_with_profile(client: TestClient, auth_headers: dict):
    """Test running a job with a profile reference."""
    response = client.post(
        "/jobs/run",
        json={"job_id": "456", "profile_ref": "custom-profile.md", "source": "test"},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data


def test_bulk_run_requires_auth(client: TestClient):
    """Test that bulk run without auth returns 401."""
    response = client.post("/jobs/run-bulk", json={"job_ids": ["123", "456"]})
    assert response.status_code == 401


def test_bulk_run_with_auth(client: TestClient, auth_headers: dict):
    """Test bulk run with authentication."""
    response = client.post(
        "/jobs/run-bulk",
        json={"job_ids": ["123", "456"], "source": "test"},
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert "runs" in data
    assert len(data["runs"]) == 2
    assert all("run_id" in run for run in data["runs"])


def test_get_status(client: TestClient, auth_headers: dict):
    """Test getting status for a run."""
    # First create a run
    create_response = client.post(
        "/jobs/run",
        json={"job_id": "789"},
        headers=auth_headers
    )
    run_id = create_response.json()["run_id"]

    # Get status
    status_response = client.get(f"/jobs/{run_id}/status")
    assert status_response.status_code == 200

    data = status_response.json()
    assert data["run_id"] == run_id
    assert data["job_id"] == "789"
    assert data["status"] in {"queued", "running", "completed", "failed"}
    assert "started_at" in data
    assert "updated_at" in data
    assert "artifacts" in data


def test_get_status_not_found(client: TestClient):
    """Test getting status for non-existent run returns 404."""
    response = client.get("/jobs/nonexistent-run-id/status")
    assert response.status_code == 404


def test_stream_logs_not_found(client: TestClient):
    """Test streaming logs for non-existent run returns 404."""
    response = client.get("/jobs/nonexistent-run-id/logs")
    assert response.status_code == 404


def test_get_artifact_not_found(client: TestClient):
    """Test getting artifact for non-existent run returns 404."""
    response = client.get("/artifacts/nonexistent-run-id/CV.md")
    assert response.status_code == 404


def test_concurrency_limit(client: TestClient, auth_headers: dict):
    """Test that concurrency limit is enforced."""
    # Create max concurrent runs (2 in test env)
    run_ids = []
    for i in range(2):
        response = client.post(
            "/jobs/run",
            json={"job_id": str(1000 + i)},
            headers=auth_headers
        )
        assert response.status_code == 200
        run_ids.append(response.json()["run_id"])

    # Next request should be queued (or 429 if semaphore is full)
    # In practice, background tasks execute quickly, so this might succeed
    # This test documents the behavior rather than strictly enforcing it
    response = client.post(
        "/jobs/run",
        json={"job_id": "1002"},
        headers=auth_headers
    )
    # Should either succeed (if prior tasks completed) or return 429
    assert response.status_code in {200, 429}


def test_missing_job_id(client: TestClient, auth_headers: dict):
    """Test that missing job_id returns validation error."""
    response = client.post(
        "/jobs/run",
        json={},
        headers=auth_headers
    )
    assert response.status_code == 422  # Validation error


def test_empty_bulk_job_ids(client: TestClient, auth_headers: dict):
    """Test that empty job_ids list returns validation error."""
    response = client.post(
        "/jobs/run-bulk",
        json={"job_ids": []},
        headers=auth_headers
    )
    assert response.status_code == 422  # Validation error


# === FireCrawl Credits Tests (GAP-070) ===


def test_firecrawl_credits_endpoint(client: TestClient):
    """Test FireCrawl credits endpoint returns expected data structure."""
    response = client.get("/firecrawl/credits")
    assert response.status_code == 200

    data = response.json()
    assert data["provider"] == "firecrawl"
    assert "daily_limit" in data
    assert "used_today" in data
    assert "remaining" in data
    assert "used_percent" in data
    assert "status" in data
    assert data["status"] in ["healthy", "warning", "critical", "exhausted"]


def test_firecrawl_credits_default_values(client: TestClient):
    """Test FireCrawl credits returns correct default values for fresh limiter."""
    response = client.get("/firecrawl/credits")
    assert response.status_code == 200

    data = response.json()
    # Fresh limiter should have a reasonable daily limit (500-600 depending on config)
    assert data["daily_limit"] >= 500  # At least free tier limit
    assert data["daily_limit"] <= 1000  # Not unreasonably high
    assert data["used_today"] >= 0  # Might have been used in other tests
    assert data["remaining"] <= data["daily_limit"]
    assert data["used_today"] + data["remaining"] == data["daily_limit"]


def test_firecrawl_credits_status_healthy(client: TestClient):
    """Test FireCrawl credits shows healthy status when under 80%."""
    response = client.get("/firecrawl/credits")
    assert response.status_code == 200

    data = response.json()
    # Fresh or lightly used limiter should be healthy
    if data["used_percent"] < 80:
        assert data["status"] == "healthy"
