"""
Pytest fixtures for runner service tests.
"""

import os

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
