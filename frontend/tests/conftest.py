"""
Shared fixtures for frontend tests.

Provides mock_db fixture that properly mocks the repository pattern
used by frontend/app.py after the repository migration.
"""

import pytest
from unittest.mock import MagicMock, patch
from src.common.repositories.base import WriteResult


@pytest.fixture
def client():
    """Create an authenticated test client for the Flask app."""
    # Import app here to avoid circular imports
    from frontend.app import app

    app.config['TESTING'] = True
    with app.test_client() as client:
        # Set up authenticated session
        with client.session_transaction() as sess:
            sess['authenticated'] = True
        yield client


@pytest.fixture
def mock_db():
    """Mock the repository pattern.

    After the repository migration, frontend/app.py uses _get_repo()
    instead of get_db(). This fixture mocks _get_repo() and provides
    a mock repository with all necessary methods.

    Returns a tuple of (mock_repo, mock_repo) for backwards compatibility
    with tests that unpack as (mock_database, mock_collection).
    """
    with patch('frontend.app._get_repo') as mock_get_repo:
        mock_repo = MagicMock()

        # Default return values for read operations
        mock_repo.find_one.return_value = None
        mock_repo.find.return_value = []
        mock_repo.count_documents.return_value = 0
        mock_repo.aggregate.return_value = []

        # Default return values for write operations
        mock_repo.update_one.return_value = WriteResult(matched_count=1, modified_count=1)
        mock_repo.update_many.return_value = WriteResult(matched_count=1, modified_count=1)
        mock_repo.delete_many.return_value = WriteResult(matched_count=0, modified_count=0)
        mock_repo.insert_one.return_value = WriteResult(matched_count=0, modified_count=0, upserted_id="test_id")

        mock_get_repo.return_value = mock_repo

        # Return tuple for compatibility with existing tests that unpack
        # as (mock_database, mock_collection) or (mock_repo, _)
        yield mock_repo, mock_repo
