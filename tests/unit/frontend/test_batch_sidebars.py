"""
Unit tests for batch page sidebar functionality.

Tests the sidebar endpoints and tri-state badge logic in frontend/app.py:
- GET /partials/batch-annotation/<job_id>: Annotation sidebar content
- GET /partials/batch-contacts/<job_id>: Contacts sidebar content
- GET /partials/batch-cv/<job_id>: CV editor sidebar content

Also tests tri-state badge logic in batch_job_single_row.html:
- JD Badge: gray → orange → green
- RS Badge: gray → orange → green
- CV Badge: gray → orange → green

Coverage:
- Authentication requirements for all endpoints
- 404 handling for invalid/missing jobs
- Template rendering with correct job data
- Badge state logic based on job fields
- Sidebar content display (annotations, contacts, CV)
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from bson import ObjectId
from flask import Flask
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


# ===== FIXTURES =====

@pytest.fixture
def app():
    """Create Flask app instance for testing."""
    from frontend.app import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-key"
    return flask_app


@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()


@pytest.fixture
def authenticated_client(client):
    """Create authenticated Flask test client."""
    with client.session_transaction() as sess:
        sess["authenticated"] = True
    return client


@pytest.fixture
def sample_job_minimal():
    """Minimal job document (gray badges)."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "title": "Software Engineer",
        "company": "Tech Corp",
        "status": "under processing",
        "batch_added_at": datetime.utcnow(),
    }


@pytest.fixture
def sample_job_with_extraction():
    """Job with extraction but no annotations (orange JD badge)."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439012"),
        "title": "Senior Backend Engineer",
        "company": "StartupXYZ",
        "status": "under processing",
        "batch_added_at": datetime.utcnow(),
        "extracted_jd": {
            "responsibilities": ["Build APIs", "Write tests"],
            "qualifications": ["5+ years Python", "MongoDB experience"],
            "nice_to_haves": ["AWS knowledge"],
        },
    }


@pytest.fixture
def sample_job_with_annotations():
    """Job with annotations (green JD badge)."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439013"),
        "title": "Staff Engineer",
        "company": "BigCorp",
        "status": "under processing",
        "batch_added_at": datetime.utcnow(),
        "extracted_jd": {
            "responsibilities": ["Lead architecture", "Mentor team"],
            "qualifications": ["10+ years experience"],
        },
        "jd_annotations": {
            "annotations": [
                {
                    "id": "ann1",
                    "text": "Lead architecture decisions",
                    "relevance": "critical",
                    "requirement_type": "must-have",
                    "strategic_note": "Highlight experience with system design",
                    "ats_keywords": ["architecture", "design", "leadership"],
                },
                {
                    "id": "ann2",
                    "text": "Mentor team members",
                    "relevance": "important",
                    "passion": True,
                },
            ],
            "processed_jd_html": "<p>Sample JD with <span class='annotation-highlight'>highlights</span></p>",
        },
    }


@pytest.fixture
def sample_job_with_research():
    """Job with research but no contacts (orange RS badge)."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439014"),
        "title": "Frontend Engineer",
        "company": "WebCo",
        "status": "under processing",
        "batch_added_at": datetime.utcnow(),
        "company_research": {
            "about": "Leading web development company",
            "tech_stack": ["React", "TypeScript"],
        },
        "role_skills": ["JavaScript", "CSS", "HTML"],
    }


@pytest.fixture
def sample_job_with_contacts():
    """Job with contacts (green RS badge)."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439015"),
        "title": "DevOps Engineer",
        "company": "CloudCo",
        "status": "under processing",
        "batch_added_at": datetime.utcnow(),
        "company_research": {"about": "Cloud infrastructure provider"},
        "primary_contacts": [
            {
                "name": "Jane Smith",
                "role": "Engineering Manager",
                "linkedin_url": "https://linkedin.com/in/janesmith",
                "email": "jane@cloudco.com",
                "linkedin_inmail": "Hi Jane, I'm interested in the DevOps role...",
                "linkedin_connection_message": "Let's connect!",
            }
        ],
        "secondary_contacts": [
            {
                "name": "Bob Wilson",
                "role": "Senior DevOps Engineer",
                "linkedin_url": "https://linkedin.com/in/bobwilson",
            }
        ],
    }


@pytest.fixture
def sample_job_with_cv_generated():
    """Job with generated CV but not edited (orange CV badge)."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439016"),
        "title": "Backend Developer",
        "company": "DataCorp",
        "status": "under processing",
        "batch_added_at": datetime.utcnow(),
        "generated_cv": "<html><body>Generated CV content</body></html>",
        "cv_text": "Plain text CV fallback",
    }


@pytest.fixture
def sample_job_with_cv_edited():
    """Job with edited CV (green CV badge)."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439017"),
        "title": "Full Stack Engineer",
        "company": "TechStart",
        "status": "under processing",
        "batch_added_at": datetime.utcnow(),
        "generated_cv": "<html><body>Generated CV</body></html>",
        "cv_editor_state": '{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"Edited CV"}]}]}',
        "cv_reasoning": "Tailored to emphasize full-stack experience and modern frameworks",
    }


# ===== TESTS: GET /partials/batch-annotation/<job_id> =====

class TestBatchAnnotationPartial:
    """Tests for GET /partials/batch-annotation/<job_id> endpoint."""

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_returns_annotation_sidebar_for_valid_job(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_annotations
    ):
        """Should render annotation sidebar template with job data."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_annotations
        mock_render_template.return_value = "<div>Annotation sidebar</div>"

        job_id = str(sample_job_with_annotations["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-annotation/{job_id}")

        # Assert
        assert response.status_code == 200
        mock_repo.find_one.assert_called_once_with({"_id": ObjectId(job_id)})
        mock_render_template.assert_called_once()

        # Verify correct template
        call_args = mock_render_template.call_args
        template_name = call_args[0][0]
        assert template_name == "partials/batch/_annotation_sidebar_content.html"

        # Verify job data passed to template
        context = call_args[1]
        assert "job" in context
        assert context["job"]["_id"] == sample_job_with_annotations["_id"]

    @patch("frontend.app._get_repo")
    def test_returns_404_for_invalid_objectid(
        self, mock_get_repo, authenticated_client
    ):
        """Should return 404 for invalid ObjectId format."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        # Act
        response = authenticated_client.get("/partials/batch-annotation/invalid-id")

        # Assert
        assert response.status_code == 404

    @patch("frontend.app._get_repo")
    def test_returns_404_when_job_not_found(
        self, mock_get_repo, authenticated_client
    ):
        """Should return 404 when job doesn't exist."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = None

        # Act
        response = authenticated_client.get("/partials/batch-annotation/507f1f77bcf86cd799439011")

        # Assert
        assert response.status_code == 404

    def test_requires_authentication(self, client):
        """Should require authentication (redirect or 401)."""
        # Act
        response = client.get("/partials/batch-annotation/507f1f77bcf86cd799439011")

        # Assert
        assert response.status_code in [302, 401]

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_displays_annotations_list(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_annotations
    ):
        """Should pass annotations data to template for rendering."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_annotations
        mock_render_template.return_value = "<div>Annotations</div>"

        job_id = str(sample_job_with_annotations["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-annotation/{job_id}")

        # Assert
        assert response.status_code == 200

        # Verify annotations are accessible in template
        call_args = mock_render_template.call_args
        context = call_args[1]
        assert "job" in context
        assert "jd_annotations" in context["job"]
        assert len(context["job"]["jd_annotations"]["annotations"]) == 2

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_handles_job_with_no_annotations(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_minimal
    ):
        """Should handle job with no annotations gracefully."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_minimal
        mock_render_template.return_value = "<div>Empty state</div>"

        job_id = str(sample_job_minimal["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-annotation/{job_id}")

        # Assert
        assert response.status_code == 200

        # Verify job is passed (template will show empty state)
        call_args = mock_render_template.call_args
        context = call_args[1]
        assert "job" in context
        assert "jd_annotations" not in context["job"]


# ===== TESTS: GET /partials/batch-contacts/<job_id> =====

class TestBatchContactsPartial:
    """Tests for GET /partials/batch-contacts/<job_id> endpoint."""

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_returns_contacts_sidebar_for_valid_job(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_contacts
    ):
        """Should render contacts sidebar template with job data."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_contacts
        mock_render_template.return_value = "<div>Contacts sidebar</div>"

        job_id = str(sample_job_with_contacts["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-contacts/{job_id}")

        # Assert
        assert response.status_code == 200
        mock_repo.find_one.assert_called_once_with({"_id": ObjectId(job_id)})
        mock_render_template.assert_called_once()

        # Verify correct template
        call_args = mock_render_template.call_args
        template_name = call_args[0][0]
        assert template_name == "partials/batch/_contacts_sidebar_content.html"

        # Verify job data passed
        context = call_args[1]
        assert "job" in context
        assert context["job"]["_id"] == sample_job_with_contacts["_id"]

    @patch("frontend.app._get_repo")
    def test_returns_404_for_invalid_objectid(
        self, mock_get_repo, authenticated_client
    ):
        """Should return 404 for invalid ObjectId format."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        # Act
        response = authenticated_client.get("/partials/batch-contacts/not-an-objectid")

        # Assert
        assert response.status_code == 404

    @patch("frontend.app._get_repo")
    def test_returns_404_when_job_not_found(
        self, mock_get_repo, authenticated_client
    ):
        """Should return 404 when job doesn't exist."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = None

        # Act
        response = authenticated_client.get("/partials/batch-contacts/507f1f77bcf86cd799439011")

        # Assert
        assert response.status_code == 404

    def test_requires_authentication(self, client):
        """Should require authentication."""
        # Act
        response = client.get("/partials/batch-contacts/507f1f77bcf86cd799439011")

        # Assert
        assert response.status_code in [302, 401]

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_displays_primary_contacts(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_contacts
    ):
        """Should pass primary contacts to template."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_contacts
        mock_render_template.return_value = "<div>Primary contacts</div>"

        job_id = str(sample_job_with_contacts["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-contacts/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        assert "job" in context
        assert "primary_contacts" in context["job"]
        assert len(context["job"]["primary_contacts"]) == 1
        assert context["job"]["primary_contacts"][0]["name"] == "Jane Smith"

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_displays_secondary_contacts(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_contacts
    ):
        """Should pass secondary contacts to template."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_contacts
        mock_render_template.return_value = "<div>Secondary contacts</div>"

        job_id = str(sample_job_with_contacts["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-contacts/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        assert "job" in context
        assert "secondary_contacts" in context["job"]
        assert len(context["job"]["secondary_contacts"]) == 1

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_contact_cards_have_correct_structure(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_contacts
    ):
        """Should pass contact with name, role, LinkedIn, and email."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_contacts
        mock_render_template.return_value = "<div>Contact card</div>"

        job_id = str(sample_job_with_contacts["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-contacts/{job_id}")

        # Assert
        call_args = mock_render_template.call_args
        context = call_args[1]
        primary_contact = context["job"]["primary_contacts"][0]

        assert primary_contact["name"] == "Jane Smith"
        assert primary_contact["role"] == "Engineering Manager"
        assert primary_contact["linkedin_url"] == "https://linkedin.com/in/janesmith"
        assert primary_contact["email"] == "jane@cloudco.com"

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_handles_job_with_no_contacts(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_minimal
    ):
        """Should show empty state when no contacts exist."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_minimal
        mock_render_template.return_value = "<div>No contacts</div>"

        job_id = str(sample_job_minimal["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-contacts/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        assert "job" in context
        # Template will check for primary_contacts/secondary_contacts and show empty state
        assert "primary_contacts" not in context["job"]


# ===== TESTS: GET /partials/batch-cv/<job_id> =====

class TestBatchCVPartial:
    """Tests for GET /partials/batch-cv/<job_id> endpoint."""

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_returns_cv_sidebar_for_valid_job(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_cv_edited
    ):
        """Should render CV sidebar template with job data."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_cv_edited
        mock_render_template.return_value = "<div>CV editor</div>"

        job_id = str(sample_job_with_cv_edited["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-cv/{job_id}")

        # Assert
        assert response.status_code == 200
        mock_repo.find_one.assert_called_once_with({"_id": ObjectId(job_id)})
        mock_render_template.assert_called_once()

        # Verify correct template
        call_args = mock_render_template.call_args
        template_name = call_args[0][0]
        assert template_name == "partials/batch/_cv_sidebar_content.html"

        # Verify job data passed
        context = call_args[1]
        assert "job" in context
        assert context["job"]["_id"] == sample_job_with_cv_edited["_id"]

    @patch("frontend.app._get_repo")
    def test_returns_404_for_invalid_objectid(
        self, mock_get_repo, authenticated_client
    ):
        """Should return 404 for invalid ObjectId format."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        # Act
        response = authenticated_client.get("/partials/batch-cv/bad-id-format")

        # Assert
        assert response.status_code == 404

    @patch("frontend.app._get_repo")
    def test_returns_404_when_job_not_found(
        self, mock_get_repo, authenticated_client
    ):
        """Should return 404 when job doesn't exist."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = None

        # Act
        response = authenticated_client.get("/partials/batch-cv/507f1f77bcf86cd799439011")

        # Assert
        assert response.status_code == 404

    def test_requires_authentication(self, client):
        """Should require authentication."""
        # Act
        response = client.get("/partials/batch-cv/507f1f77bcf86cd799439011")

        # Assert
        assert response.status_code in [302, 401]

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_displays_cv_editor_state(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_cv_edited
    ):
        """Should pass cv_editor_state to template for TipTap rendering."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_cv_edited
        mock_render_template.return_value = "<div>CV with editor state</div>"

        job_id = str(sample_job_with_cv_edited["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-cv/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        assert "job" in context
        assert "cv_editor_state" in context["job"]
        assert "cv_reasoning" in context["job"]

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_displays_cv_text_fallback(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_cv_generated
    ):
        """Should use cv_text as fallback when cv_editor_state doesn't exist."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_cv_generated
        mock_render_template.return_value = "<div>CV text</div>"

        job_id = str(sample_job_with_cv_generated["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-cv/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        assert "job" in context
        # Has generated_cv and cv_text but no cv_editor_state
        assert "generated_cv" in context["job"]
        assert "cv_text" in context["job"]
        assert "cv_editor_state" not in context["job"]

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_shows_empty_state_when_no_cv(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_minimal
    ):
        """Should show empty state when no CV exists."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_minimal
        mock_render_template.return_value = "<div>No CV</div>"

        job_id = str(sample_job_minimal["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-cv/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        assert "job" in context
        # Template will check for cv_editor_state, cv_text, generated_cv and show empty state
        assert "cv_editor_state" not in context["job"]
        assert "generated_cv" not in context["job"]


# ===== TESTS: Tri-State Badge Logic =====

class TestTriStateBadgeLogic:
    """
    Tests for tri-state badge logic in batch_job_single_row.html.

    Badge states are determined by Jinja2 template logic based on job fields:
    - JD: gray (no extraction) → orange (extracted, no annotations) → green (has annotations)
    - RS: gray (no research) → orange (has research, no contacts) → green (has contacts)
    - CV: gray (no CV) → orange (generated, not edited) → green (has cv_editor_state)

    These tests verify that the template receives the correct job data
    to render the appropriate badge states.
    """

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_jd_badge_gray_when_no_extraction(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_minimal
    ):
        """JD badge should be gray when no extracted_jd exists."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_minimal
        mock_render_template.return_value = "<tbody>...</tbody>"

        job_id = str(sample_job_minimal["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-job-row/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        job = context["job"]

        # Verify job has no extraction data (gray badge)
        assert "extracted_jd" not in job
        assert "processed_jd" not in job
        assert "jd_annotations" not in job

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_jd_badge_orange_when_extracted_no_annotations(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_extraction
    ):
        """JD badge should be orange when extracted_jd exists but no annotations."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_extraction
        mock_render_template.return_value = "<tbody>...</tbody>"

        job_id = str(sample_job_with_extraction["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-job-row/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        job = context["job"]

        # Verify job has extraction but no annotations (orange badge)
        assert "extracted_jd" in job
        assert job["extracted_jd"] is not None
        assert "jd_annotations" not in job or not job.get("jd_annotations", {}).get("annotations")

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_jd_badge_green_when_has_annotations(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_annotations
    ):
        """JD badge should be green when jd_annotations.annotations has items."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_annotations
        mock_render_template.return_value = "<tbody>...</tbody>"

        job_id = str(sample_job_with_annotations["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-job-row/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        job = context["job"]

        # Verify job has annotations (green badge)
        assert "jd_annotations" in job
        assert "annotations" in job["jd_annotations"]
        assert len(job["jd_annotations"]["annotations"]) > 0

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_rs_badge_gray_when_no_research(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_minimal
    ):
        """RS badge should be gray when no company_research exists."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_minimal
        mock_render_template.return_value = "<tbody>...</tbody>"

        job_id = str(sample_job_minimal["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-job-row/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        job = context["job"]

        # Verify job has no research (gray badge)
        assert "company_research" not in job
        assert "role_skills" not in job
        assert "primary_contacts" not in job
        assert "secondary_contacts" not in job

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_rs_badge_orange_when_research_no_contacts(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_research
    ):
        """RS badge should be orange when has research but no contacts."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_research
        mock_render_template.return_value = "<tbody>...</tbody>"

        job_id = str(sample_job_with_research["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-job-row/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        job = context["job"]

        # Verify job has research but no contacts (orange badge)
        assert "company_research" in job or "role_skills" in job
        assert "primary_contacts" not in job or len(job.get("primary_contacts", [])) == 0
        assert "secondary_contacts" not in job or len(job.get("secondary_contacts", [])) == 0

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_rs_badge_green_when_has_contacts(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_contacts
    ):
        """RS badge should be green when has primary or secondary contacts."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_contacts
        mock_render_template.return_value = "<tbody>...</tbody>"

        job_id = str(sample_job_with_contacts["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-job-row/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        job = context["job"]

        # Verify job has contacts (green badge)
        has_primary = "primary_contacts" in job and len(job["primary_contacts"]) > 0
        has_secondary = "secondary_contacts" in job and len(job["secondary_contacts"]) > 0
        assert has_primary or has_secondary

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_cv_badge_gray_when_no_cv(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_minimal
    ):
        """CV badge should be gray when no CV exists."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_minimal
        mock_render_template.return_value = "<tbody>...</tbody>"

        job_id = str(sample_job_minimal["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-job-row/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        job = context["job"]

        # Verify job has no CV (gray badge)
        assert "generated_cv" not in job
        assert "cv_output" not in job
        assert "cv_text" not in job
        assert "cv_editor_state" not in job

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_cv_badge_orange_when_generated_not_edited(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_cv_generated
    ):
        """CV badge should be orange when CV generated but not edited."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_cv_generated
        mock_render_template.return_value = "<tbody>...</tbody>"

        job_id = str(sample_job_with_cv_generated["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-job-row/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        job = context["job"]

        # Verify job has generated CV but no editor state (orange badge)
        has_cv = "generated_cv" in job or "cv_output" in job or "cv_text" in job
        assert has_cv
        assert "cv_editor_state" not in job or not job.get("cv_editor_state")

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_cv_badge_green_when_edited(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_with_cv_edited
    ):
        """CV badge should be green when cv_editor_state exists."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_with_cv_edited
        mock_render_template.return_value = "<tbody>...</tbody>"

        job_id = str(sample_job_with_cv_edited["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-job-row/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        job = context["job"]

        # Verify job has editor state (green badge)
        assert "cv_editor_state" in job
        assert job["cv_editor_state"] is not None
        assert len(job["cv_editor_state"]) > 0


# ===== TESTS: Application URL Quick Entry =====

class TestApplicationURLQuickEntry:
    """Tests for inline application URL popover in batch_job_single_row.html."""

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_row_template_includes_application_url(
        self, mock_render_template, mock_get_repo, authenticated_client
    ):
        """Should pass application_url to template for quick entry popover."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        job_with_url = {
            "_id": ObjectId("507f1f77bcf86cd799439018"),
            "title": "ML Engineer",
            "company": "AI Corp",
            "status": "under processing",
            "batch_added_at": datetime.utcnow(),
            "url": "https://example.com/job",
            "application_url": "https://example.com/apply",
        }

        mock_repo.find_one.return_value = job_with_url
        mock_render_template.return_value = "<tbody>...</tbody>"

        job_id = str(job_with_url["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-job-row/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        job = context["job"]

        # Verify both URLs are present for template
        assert "url" in job
        assert "application_url" in job
        assert job["application_url"] == "https://example.com/apply"

    @patch("frontend.app._get_repo")
    @patch("frontend.app.render_template")
    def test_row_template_handles_missing_application_url(
        self, mock_render_template, mock_get_repo, authenticated_client, sample_job_minimal
    ):
        """Should handle job without application_url (popover shows as not set)."""
        # Arrange
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        mock_repo.find_one.return_value = sample_job_minimal
        mock_render_template.return_value = "<tbody>...</tbody>"

        job_id = str(sample_job_minimal["_id"])

        # Act
        response = authenticated_client.get(f"/partials/batch-job-row/{job_id}")

        # Assert
        assert response.status_code == 200

        call_args = mock_render_template.call_args
        context = call_args[1]
        job = context["job"]

        # Verify application_url is not present (template will show empty state)
        assert "application_url" not in job
