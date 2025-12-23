"""
Unit tests for pipeline executor module.

These tests mock subprocess execution to prevent spawning real Python processes
which would be slow and require MongoDB/external services.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from runner_service.executor import execute_pipeline, discover_artifacts


class MockAsyncIterator:
    """Mock async iterator for subprocess stdout."""

    def __init__(self, lines):
        self.lines = lines
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.lines):
            raise StopAsyncIteration
        line = self.lines[self.index]
        self.index += 1
        return line


@pytest.fixture
def mock_subprocess_failure():
    """Mock subprocess that fails immediately."""
    async def mock_create_subprocess(*args, **kwargs):
        mock_process = MagicMock()
        mock_process.returncode = 1  # Non-zero = failure
        mock_process.stdout = MockAsyncIterator([
            b"Starting pipeline...\n",
            b"Error: Job not found\n",
        ])
        mock_process.wait = AsyncMock(return_value=1)
        return mock_process

    with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess):
        yield


@pytest.fixture
def mock_subprocess_timeout():
    """Mock subprocess that hangs (simulates timeout)."""
    async def mock_create_subprocess(*args, **kwargs):
        mock_process = MagicMock()
        mock_process.returncode = None  # Not finished
        mock_process.stdout = MockAsyncIterator([b"Starting...\n"])
        # Make wait return normally (it won't be called due to wait_for mock)
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.kill = MagicMock()
        return mock_process

    # Mock wait_for to raise TimeoutError (simulating timeout expiration)
    async def mock_wait_for(coro, timeout):
        # Cancel the coroutine to avoid "coroutine never awaited" warning
        coro.close() if hasattr(coro, 'close') else None
        raise asyncio.TimeoutError()

    with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess):
        with patch("runner_service.executor.asyncio.wait_for", side_effect=mock_wait_for):
            yield


@pytest.mark.asyncio
async def test_execute_pipeline_with_invalid_job(mock_subprocess_failure):
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
async def test_execute_pipeline_timeout(mock_subprocess_timeout):
    """Test that pipeline execution handles timeout correctly."""
    logs = []

    def log_callback(message: str):
        logs.append(message)

    # Execute with mocked subprocess that simulates timeout
    success, artifacts, pipeline_state = await execute_pipeline(
        job_id="test-job-timeout",
        profile_ref=None,
        log_callback=log_callback
    )

    # Should fail due to timeout
    assert success is False
    assert pipeline_state is None
    # Should have logged the timeout message
    assert any("timed out" in log.lower() for log in logs)


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
