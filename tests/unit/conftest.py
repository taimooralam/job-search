"""
Global fixtures for all unit tests.

This conftest provides autouse fixtures that prevent real external service calls:
- MongoDB connection attempts (would cause 5-30s timeout per test)
- Environment variable isolation (prevents credential leakage)

These fixtures apply automatically to ALL tests in tests/unit/.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

# Set test environment BEFORE any imports to prevent Config from loading real values
# Use "development" since runner_service validates against [development, staging, production]
os.environ["ENVIRONMENT"] = "development"
os.environ["USE_MASTER_CV_MONGODB"] = "false"
# Don't clear MONGODB_URI as it may break validation in runner_service


@pytest.fixture(autouse=True)
def mock_mongodb():
    """
    Prevent MongoDB connection attempts in all unit tests.

    Without this mock, CVGeneratorV2 initialization triggers:
    CVGeneratorV2 -> CVLoader -> MasterCVStore -> DatabaseClient -> MongoClient

    MongoClient("") defaults to localhost:27017, causing 5-30s timeout per test.
    """
    with patch("pymongo.MongoClient") as mock_client:
        mock_instance = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # Setup chain: client["db"]["collection"]
        mock_instance.__getitem__ = MagicMock(return_value=mock_db)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.find_one = MagicMock(return_value=None)
        mock_collection.find = MagicMock(return_value=[])

        mock_client.return_value = mock_instance
        yield mock_client


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch):
    """
    Isolate test environment from real credentials and configurations.

    This prevents:
    - Real API keys being used if tests accidentally call LLMs
    - MongoDB connections via USE_MASTER_CV_MONGODB
    - Other external service configurations
    """
    monkeypatch.setenv("USE_MASTER_CV_MONGODB", "false")
    monkeypatch.setenv("ENVIRONMENT", "development")
    # Use mock API keys to prevent accidental real API calls
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-mock-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-mock-key")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-mock-key")
