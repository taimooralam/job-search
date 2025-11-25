"""
Pytest fixtures for runner service tests.
"""

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def set_test_env():
    """Set test environment variables."""
    os.environ["ENVIRONMENT"] = "development"
    os.environ["RUNNER_API_SECRET"] = "test-secret-key"
    os.environ["MAX_CONCURRENCY"] = "2"
    os.environ["LOG_BUFFER_LIMIT"] = "100"
    os.environ["PIPELINE_TIMEOUT_SECONDS"] = "30"


@pytest.fixture
def client():
    """FastAPI test client fixture."""
    from runner_service.app import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Authentication headers for test requests."""
    return {"Authorization": "Bearer test-secret-key"}


@pytest.fixture
def invalid_auth_headers():
    """Invalid authentication headers for testing auth failures."""
    return {"Authorization": "Bearer wrong-secret"}
