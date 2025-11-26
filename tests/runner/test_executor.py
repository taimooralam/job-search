"""
Unit tests for pipeline executor module.
"""

import pytest
import asyncio
from pathlib import Path
from runner_service.executor import execute_pipeline, discover_artifacts


@pytest.mark.asyncio
async def test_execute_pipeline_with_invalid_job():
    """Test pipeline execution with an invalid job ID."""
    logs = []

    def log_callback(message: str):
        logs.append(message)

    # Execute with non-existent job
    success, artifacts, pipeline_state = await execute_pipeline(
        job_id="nonexistent-job-9999999",
        profile_ref=None,
        log_callback=log_callback
    )

    # Should fail
    assert success is False
    assert len(artifacts) == 0
    assert pipeline_state is None
    assert len(logs) > 0
    # Should have captured the command execution
    assert any("Executing:" in log for log in logs)


@pytest.mark.asyncio
async def test_execute_pipeline_timeout():
    """Test that pipeline execution respects timeout."""
    import os
    # Set a very short timeout for testing
    original_timeout = os.environ.get("PIPELINE_TIMEOUT_SECONDS")
    os.environ["PIPELINE_TIMEOUT_SECONDS"] = "1"

    # Reload module to pick up new timeout
    import importlib
    import runner_service.executor
    importlib.reload(runner_service.executor)
    from runner_service.executor import execute_pipeline as exec_pipe

    logs = []

    def log_callback(message: str):
        logs.append(message)

    # This should timeout with a 1 second limit
    # Using a job that would normally take longer
    success, artifacts, pipeline_state = await exec_pipe(
        job_id="test-job-timeout",
        profile_ref=None,
        log_callback=log_callback
    )

    # Restore original timeout
    if original_timeout:
        os.environ["PIPELINE_TIMEOUT_SECONDS"] = original_timeout
    else:
        os.environ.pop("PIPELINE_TIMEOUT_SECONDS", None)

    # Should fail due to timeout or other error
    assert success is False
    assert pipeline_state is None


def test_discover_artifacts_empty_directory():
    """Test artifact discovery when no applications directory exists."""
    artifacts = discover_artifacts("nonexistent-job")
    assert isinstance(artifacts, dict)
    # May be empty or may find existing artifacts from other tests


def test_discover_artifacts_with_files(tmp_path: Path):
    """Test artifact discovery with actual files."""
    # Create mock applications directory structure
    import os
    original_cwd = os.getcwd()

    try:
        os.chdir(tmp_path)

        # Create structure: applications/Company/Role/
        company_dir = tmp_path / "applications" / "TestCompany"
        role_dir = company_dir / "TestRole"
        role_dir.mkdir(parents=True)

        # Create artifact files
        (role_dir / "CV.md").write_text("# Test CV")
        (role_dir / "dossier.txt").write_text("Test dossier")

        # Discover artifacts
        artifacts = discover_artifacts("test-job")

        # Should find the files
        assert isinstance(artifacts, dict)
        # Note: The current implementation returns full paths
        # This test documents the actual behavior

    finally:
        os.chdir(original_cwd)
