"""
Pytest fixtures for runner service tests.
"""

import os
from unittest.mock import patch, AsyncMock

# IMPORTANT: Set environment variables BEFORE any imports from runner_service
# to ensure RunnerSettings is configured correctly when first loaded.
# RunnerSettings validation requires:
# - runner_api_secret: min 16 characters
# - pipeline_timeout_seconds: min 60 seconds
os.environ["ENVIRONMENT"] = "development"
os.environ["RUNNER_API_SECRET"] = "test-secret-key-1234"  # Min 16 chars
os.environ["MAX_CONCURRENCY"] = "2"
os.environ["LOG_BUFFER_LIMIT"] = "100"
os.environ["PIPELINE_TIMEOUT_SECONDS"] = "60"  # Min 60 seconds

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_execute_pipeline():
    """
    Mock execute_pipeline to prevent actual subprocess execution.

    This dramatically speeds up tests by avoiding:
    1. Subprocess spawning overhead
    2. Heavy module imports in subprocess
    3. MongoDB connection attempts
    4. 60-second timeout waits

    The mock returns success with empty artifacts immediately.
    """
    async def mock_pipeline(*args, **kwargs):
        # Simulate immediate success
        return (True, {"CV.md": "/fake/path/CV.md"}, {"status": "completed"})

    with patch("runner_service.app.execute_pipeline", new=mock_pipeline):
        yield


@pytest.fixture
def client():
    """FastAPI test client fixture."""
    from runner_service.app import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Authentication headers for test requests."""
    return {"Authorization": "Bearer test-secret-key-1234"}


@pytest.fixture
def invalid_auth_headers():
    """Invalid authentication headers for testing auth failures."""
    return {"Authorization": "Bearer wrong-secret"}
