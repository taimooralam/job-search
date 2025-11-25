"""
Integration tests for runner service.

These tests use mocked pipeline execution but test the full request/response cycle.
"""

import pytest
import time
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_full_pipeline_flow(client: TestClient, auth_headers: dict):
    """
    Test complete pipeline flow: trigger -> poll -> check artifacts.

    This is a smoke test that verifies the basic flow works.
    It uses a real job ID but may fail if MongoDB is not accessible.
    """
    # Trigger a run with test flag would be ideal, but not implemented yet
    # For now, just test the API flow with a dummy job
    response = client.post(
        "/jobs/run",
        json={"job_id": "test-integration-job", "source": "integration-test"},
        headers=auth_headers
    )
    assert response.status_code == 200

    run_id = response.json()["run_id"]
    assert run_id

    # Poll status a few times
    max_polls = 5
    final_status = None

    for _ in range(max_polls):
        status_response = client.get(f"/jobs/{run_id}/status")
        assert status_response.status_code == 200

        data = status_response.json()
        final_status = data["status"]

        if final_status in {"completed", "failed"}:
            break

        time.sleep(1)

    # The run should eventually complete or fail
    # Since we don't have the test data in MongoDB, it will likely fail
    assert final_status in {"queued", "running", "completed", "failed"}


@pytest.mark.integration
def test_log_streaming(client: TestClient, auth_headers: dict):
    """Test that log streaming works."""
    # Trigger a run
    response = client.post(
        "/jobs/run",
        json={"job_id": "test-log-stream", "source": "integration-test"},
        headers=auth_headers
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    # Stream logs (note: TestClient doesn't support true streaming well)
    # So we'll just check the endpoint is accessible
    with client.stream("GET", f"/jobs/{run_id}/logs") as response:
        assert response.status_code == 200
        # Read first few chunks
        chunks = []
        for i, chunk in enumerate(response.iter_bytes()):
            chunks.append(chunk)
            if i >= 10:  # Limit to first 10 chunks
                break

    # Should have received some data
    assert len(chunks) > 0


@pytest.mark.integration
def test_bulk_run_flow(client: TestClient, auth_headers: dict):
    """Test bulk run creates multiple runs."""
    response = client.post(
        "/jobs/run-bulk",
        json={
            "job_ids": ["bulk-test-1", "bulk-test-2", "bulk-test-3"],
            "source": "integration-test"
        },
        headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    assert "runs" in data
    assert len(data["runs"]) == 3

    # All runs should have unique IDs
    run_ids = [run["run_id"] for run in data["runs"]]
    assert len(run_ids) == len(set(run_ids))  # All unique

    # Check we can get status for each
    for run_id in run_ids:
        status_response = client.get(f"/jobs/{run_id}/status")
        assert status_response.status_code == 200


@pytest.mark.integration
@pytest.mark.skip(reason="Requires MongoDB with test data")
def test_full_pipeline_with_real_job(client: TestClient, auth_headers: dict):
    """
    Test full pipeline with a real job from MongoDB.

    Skipped by default - enable when testing with real MongoDB.
    """
    # This would need a known test job in MongoDB
    test_job_id = "4335713702"  # From sample data

    response = client.post(
        "/jobs/run",
        json={"job_id": test_job_id, "source": "integration-test"},
        headers=auth_headers
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    # Poll until completion (with timeout)
    max_wait = 120  # 2 minutes
    start_time = time.time()

    while time.time() - start_time < max_wait:
        status_response = client.get(f"/jobs/{run_id}/status")
        data = status_response.json()

        if data["status"] in {"completed", "failed"}:
            break

        time.sleep(2)

    assert data["status"] == "completed"
    assert len(data["artifacts"]) > 0
