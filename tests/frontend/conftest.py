"""
Pytest fixtures for frontend/Flask tests.
"""

import os
import sys
import pytest
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock
from pathlib import Path


@pytest.fixture(scope="session", autouse=True)
def setup_frontend_imports():
    """Add frontend directory to sys.path for imports."""
    frontend_path = Path(__file__).parent.parent.parent / "frontend"
    if str(frontend_path) not in sys.path:
        sys.path.insert(0, str(frontend_path))


@pytest.fixture(scope="session", autouse=True)
def set_test_env():
    """Set test environment variables."""
    os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
    os.environ["FLASK_ENV"] = "testing"
    os.environ["LOGIN_PASSWORD"] = "test-password"
    os.environ["MONGODB_URI"] = "mongodb://localhost:27017/jobs_test"


@pytest.fixture
def app():
    """Flask app fixture with test configuration."""
    from app import app
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def authenticated_client(client):
    """Flask test client with authenticated session."""
    with client.session_transaction() as sess:
        sess['authenticated'] = True
    return client


@pytest.fixture
def mock_db(mocker):
    """
    Mock MongoDB connection and collection for all Flask routes.

    This fixture mocks:
    1. MongoClient at the module level to prevent real DB connections
    2. get_db() to return a mocked database instance
    3. The collection chain (db['level-2']) to return a mock collection

    Tests using template rendering routes (e.g., /job/<id>) need this fixture
    to avoid "Connection refused" errors when Flask tries to query MongoDB.
    """
    # Create mock collection with common methods
    mock_collection = MagicMock()

    # Default return value for find_one (can be overridden in tests)
    mock_collection.find_one.return_value = None

    # Setup the mock database instance
    mock_db_instance = MagicMock()
    mock_db_instance.__getitem__.return_value = mock_collection

    # Mock MongoClient to prevent real connections
    mock_client = mocker.patch("app.MongoClient")
    mock_client.return_value.__getitem__.return_value = mock_db_instance

    # Mock get_db() to return the mocked database
    mocker.patch("app.get_db", return_value=mock_db_instance)

    return mock_collection


@pytest.fixture
def sample_job():
    """
    Sample job document without editor state.

    Includes all fields required by job_detail.html template to prevent
    Jinja2 UndefinedError exceptions during template rendering tests.
    """
    return {
        "_id": ObjectId(),
        "jobId": "test_job_001",
        "title": "Senior Python Developer",
        "company": "TechCorp",
        "location": "Remote",
        "url": "https://example.com/jobs/123",
        "status": "not processed",
        "score": 75,  # Required by template
        "fit_score": 80,  # Optional field used by template
        "createdAt": datetime(2025, 11, 26, 10, 0, 0),
        "updatedAt": datetime(2025, 11, 26, 10, 0, 0),
        "cv_text": "# John Doe\n\n## Experience\n\n- 5 years Python\n- 3 years FastAPI"
    }


@pytest.fixture
def sample_job_with_editor_state():
    """Sample job document with cv_editor_state."""
    return {
        "_id": ObjectId(),
        "jobId": "test_job_002",
        "title": "Staff Engineer",
        "company": "StartupCo",
        "location": "San Francisco, CA",
        "url": "https://example.com/jobs/456",
        "status": "marked for applying",
        "createdAt": datetime(2025, 11, 26, 11, 0, 0),
        "updatedAt": datetime(2025, 11, 26, 12, 0, 0),
        "cv_text": "# Jane Smith\n\n## Experience\n\n- 8 years engineering",
        "cv_editor_state": {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 1},
                        "content": [{"type": "text", "text": "Jane Smith"}]
                    },
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Senior software engineer with 8 years experience"}]
                    }
                ]
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.15,
                "margins": {
                    "top": 1.0,
                    "right": 1.0,
                    "bottom": 1.0,
                    "left": 1.0
                },
                "pageSize": "letter"
            },
            "lastSavedAt": datetime(2025, 11, 26, 12, 0, 0)
        }
    }


@pytest.fixture
def empty_tiptap_doc():
    """Empty TipTap document structure."""
    return {
        "type": "doc",
        "content": []
    }


@pytest.fixture
def default_editor_state():
    """Default editor state with empty document."""
    return {
        "version": 1,
        "content": {
            "type": "doc",
            "content": []
        },
        "documentStyles": {
            "fontFamily": "Inter",
            "fontSize": 11,
            "lineHeight": 1.15,  # Phase 3: Standard resume spacing
            "margins": {
                "top": 1.0,  # Phase 3: Standard 1-inch margins
                "right": 1.0,
                "bottom": 1.0,
                "left": 1.0
            },
            "pageSize": "letter"
        }
    }


@pytest.fixture
def sample_job_with_phase2_formatting():
    """Sample job with Phase 2 formatting (fonts, alignment, indentation, highlight)."""
    return {
        "_id": ObjectId(),
        "jobId": "test_job_003",
        "title": "Principal Engineer",
        "company": "BigTech Inc",
        "location": "New York, NY",
        "url": "https://example.com/jobs/789",
        "status": "ready for applying",
        "createdAt": datetime(2025, 11, 26, 14, 0, 0),
        "updatedAt": datetime(2025, 11, 26, 15, 0, 0),
        "cv_text": "# Alex Johnson\n\n## Experience\n\n- Led engineering teams",
        "cv_editor_state": {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 1, "textAlign": "center"},
                        "content": [
                            {
                                "type": "text",
                                "text": "Alex Johnson",
                                "marks": [
                                    {
                                        "type": "textStyle",
                                        "attrs": {
                                            "fontFamily": "Playfair Display",
                                            "fontSize": "24pt"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "paragraph",
                        "attrs": {
                            "textAlign": "justify",
                            "style": "margin-left: 0.5in"
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "Principal Engineer with 15 years of experience building scalable systems. ",
                                "marks": [
                                    {"type": "textStyle", "attrs": {"fontSize": "11pt"}}
                                ]
                            },
                            {
                                "type": "text",
                                "text": "Expert in distributed architecture.",
                                "marks": [
                                    {"type": "textStyle", "attrs": {"fontSize": "11pt"}},
                                    {"type": "highlight", "attrs": {"color": "#ffff00"}}
                                ]
                            }
                        ]
                    },
                    {
                        "type": "heading",
                        "attrs": {"level": 2, "textAlign": "left"},
                        "content": [
                            {
                                "type": "text",
                                "text": "TECHNICAL EXPERIENCE",
                                "marks": [
                                    {"type": "textStyle", "attrs": {"fontFamily": "Roboto", "fontSize": "14pt"}},
                                    {"type": "bold"}
                                ]
                            }
                        ]
                    },
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "attrs": {"style": "margin-left: 1in"},
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "Architected microservices platform serving 10M+ users",
                                                "marks": [
                                                    {"type": "textStyle", "attrs": {"fontSize": "11pt"}}
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "Reduced latency by 60% through optimization",
                                                "marks": [
                                                    {"type": "textStyle", "attrs": {"fontSize": "11pt"}},
                                                    {"type": "highlight", "attrs": {"color": "#00ff00"}}
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.15,
                "margins": {
                    "top": 1.0,
                    "right": 1.0,
                    "bottom": 1.0,
                    "left": 1.0
                },
                "pageSize": "letter"
            },
            "lastSavedAt": datetime(2025, 11, 26, 15, 0, 0)
        }
    }


@pytest.fixture
def phase2_formatted_content():
    """TipTap JSON content with Phase 2 formatting (for testing)."""
    return {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1, "textAlign": "center"},
                "content": [
                    {
                        "type": "text",
                        "text": "Professional CV",
                        "marks": [
                            {"type": "textStyle", "attrs": {"fontFamily": "Merriweather", "fontSize": "22pt"}},
                            {"type": "bold"}
                        ]
                    }
                ]
            },
            {
                "type": "paragraph",
                "attrs": {"textAlign": "justify", "style": "margin-left: 0.5in"},
                "content": [
                    {
                        "type": "text",
                        "text": "Highlighted achievement",
                        "marks": [
                            {"type": "textStyle", "attrs": {"fontSize": "11pt"}},
                            {"type": "highlight", "attrs": {"color": "#ffff00"}}
                        ]
                    }
                ]
            },
            {
                "type": "paragraph",
                "attrs": {"textAlign": "right"},
                "content": [
                    {
                        "type": "text",
                        "text": "Right-aligned signature",
                        "marks": [
                            {"type": "textStyle", "attrs": {"fontFamily": "Pacifico", "fontSize": "14pt"}},
                            {"type": "italic"}
                        ]
                    }
                ]
            }
        ]
    }
