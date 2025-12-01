"""
Unit tests for Contact Management API endpoints.

Tests the DELETE, POST, and GET endpoints for managing contacts:
- DELETE /api/jobs/<job_id>/contacts/<type>/<index>
- POST /api/jobs/<job_id>/contacts
- GET /api/jobs/<job_id>/contacts/prompt
"""

import pytest
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock


class TestDeleteContact:
    """Tests for DELETE /api/jobs/<job_id>/contacts/<type>/<index> endpoint."""

    def test_delete_primary_contact_success(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should delete a primary contact by index."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["primary_contacts"] = [
            {"name": "Jane Doe", "role": "Hiring Manager", "linkedin_url": "https://linkedin.com/in/janedoe"},
            {"name": "John Smith", "role": "Recruiter", "linkedin_url": "https://linkedin.com/in/johnsmith"}
        ]
        mock_db.find_one.return_value = sample_job_with_editor_state

        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_db.update_one.return_value = mock_result

        # Act
        response = authenticated_client.delete(f"/api/jobs/{job_id}/contacts/primary/0")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "Jane Doe" in data["message"]

    def test_delete_secondary_contact_success(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should delete a secondary contact by index."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["secondary_contacts"] = [
            {"name": "Bob Wilson", "role": "Tech Lead", "linkedin_url": "https://linkedin.com/in/bobwilson"}
        ]
        mock_db.find_one.return_value = sample_job_with_editor_state

        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_db.update_one.return_value = mock_result

        # Act
        response = authenticated_client.delete(f"/api/jobs/{job_id}/contacts/secondary/0")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_delete_contact_invalid_type(self, authenticated_client, mock_db):
        """Should return 400 for invalid contact type."""
        # Arrange
        job_id = str(ObjectId())

        # Act
        response = authenticated_client.delete(f"/api/jobs/{job_id}/contacts/invalid/0")

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "Invalid contact type" in data["error"]

    def test_delete_contact_index_out_of_range(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should return 400 when contact index is out of range."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["primary_contacts"] = [
            {"name": "Jane Doe", "role": "Hiring Manager", "linkedin_url": "https://linkedin.com/in/janedoe"}
        ]
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.delete(f"/api/jobs/{job_id}/contacts/primary/5")

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "out of range" in data["error"]

    def test_delete_contact_job_not_found(self, authenticated_client, mock_db):
        """Should return 404 when job doesn't exist."""
        # Arrange
        job_id = str(ObjectId())
        mock_db.find_one.return_value = None

        # Act
        response = authenticated_client.delete(f"/api/jobs/{job_id}/contacts/primary/0")

        # Assert
        assert response.status_code == 404
        data = response.get_json()
        assert data["error"] == "Job not found"

    def test_delete_contact_requires_authentication(self, client, mock_db):
        """Should return 401/302 when not authenticated."""
        # Arrange
        job_id = str(ObjectId())

        # Act
        response = client.delete(f"/api/jobs/{job_id}/contacts/primary/0")

        # Assert
        assert response.status_code in [401, 302]


class TestImportContacts:
    """Tests for POST /api/jobs/<job_id>/contacts endpoint."""

    def test_import_contacts_success(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should import valid contacts."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_db.update_one.return_value = mock_result

        contacts_data = {
            "contacts": [
                {
                    "name": "Jane Doe",
                    "title": "Hiring Manager",
                    "linkedin_url": "https://linkedin.com/in/janedoe",
                    "email": "jane@company.com"
                },
                {
                    "name": "John Smith",
                    "role": "Recruiter",  # Using 'role' instead of 'title'
                    "linkedin_url": "https://linkedin.com/in/johnsmith"
                }
            ],
            "contact_type": "primary"
        }

        # Act
        response = authenticated_client.post(
            f"/api/jobs/{job_id}/contacts",
            json=contacts_data,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["importedCount"] == 2

    def test_import_contacts_secondary_type(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should import contacts as secondary by default."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_db.update_one.return_value = mock_result

        contacts_data = {
            "contacts": [
                {
                    "name": "Bob Wilson",
                    "title": "Tech Lead",
                    "linkedin_url": "https://linkedin.com/in/bobwilson"
                }
            ]
            # No contact_type specified - should default to secondary
        }

        # Act
        response = authenticated_client.post(
            f"/api/jobs/{job_id}/contacts",
            json=contacts_data,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["contactType"] == "secondary"

    def test_import_contacts_filters_invalid(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should filter out invalid contacts and import valid ones."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_db.update_one.return_value = mock_result

        contacts_data = {
            "contacts": [
                {
                    "name": "Valid Contact",
                    "title": "Manager",
                    "linkedin_url": "https://linkedin.com/in/valid"
                },
                {
                    "name": "Missing LinkedIn",
                    "title": "Manager"
                    # No linkedin_url - invalid
                },
                {
                    "title": "Manager",
                    "linkedin_url": "https://linkedin.com/in/noname"
                    # No name - invalid
                }
            ]
        }

        # Act
        response = authenticated_client.post(
            f"/api/jobs/{job_id}/contacts",
            json=contacts_data,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["importedCount"] == 1

    def test_import_contacts_no_valid_contacts(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should return 400 when no valid contacts provided."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        contacts_data = {
            "contacts": [
                {"name": "Invalid", "title": "Manager"}  # Missing linkedin_url
            ]
        }

        # Act
        response = authenticated_client.post(
            f"/api/jobs/{job_id}/contacts",
            json=contacts_data,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "No valid contacts" in data["error"]

    def test_import_contacts_empty_array(self, authenticated_client, mock_db, sample_job):
        """Should return 400 when contacts array is empty."""
        # Arrange
        job_id = str(sample_job["_id"])

        contacts_data = {"contacts": []}

        # Act
        response = authenticated_client.post(
            f"/api/jobs/{job_id}/contacts",
            json=contacts_data,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "No contacts provided" in data["error"]

    def test_import_contacts_job_not_found(self, authenticated_client, mock_db):
        """Should return 404 when job doesn't exist."""
        # Arrange
        job_id = str(ObjectId())
        mock_db.find_one.return_value = None

        contacts_data = {
            "contacts": [
                {"name": "Test", "title": "Manager", "linkedin_url": "https://linkedin.com/in/test"}
            ]
        }

        # Act
        response = authenticated_client.post(
            f"/api/jobs/{job_id}/contacts",
            json=contacts_data,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 404

    def test_import_contacts_requires_authentication(self, client, mock_db):
        """Should return 401/302 when not authenticated."""
        # Arrange
        job_id = str(ObjectId())
        contacts_data = {"contacts": []}

        # Act
        response = client.post(
            f"/api/jobs/{job_id}/contacts",
            json=contacts_data,
            content_type="application/json"
        )

        # Assert
        assert response.status_code in [401, 302]


class TestGetFirecrawlPrompt:
    """Tests for GET /api/jobs/<job_id>/contacts/prompt endpoint."""

    def test_get_prompt_success(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should return FireCrawl prompt with job details."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/contacts/prompt")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "prompt" in data
        assert sample_job["company"] in data["prompt"]
        assert sample_job["title"] in data["prompt"]
        assert "mcp__firecrawl__firecrawl_search" in data["prompt"]

    def test_get_prompt_includes_schema(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should include contact schema in prompt."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/contacts/prompt")

        # Assert
        data = response.get_json()
        assert "linkedin_url" in data["prompt"]
        assert "email" in data["prompt"]
        assert "title" in data["prompt"]

    def test_get_prompt_job_not_found(self, authenticated_client, mock_db):
        """Should return 404 when job doesn't exist."""
        # Arrange
        job_id = str(ObjectId())
        mock_db.find_one.return_value = None

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/contacts/prompt")

        # Assert
        assert response.status_code == 404

    def test_get_prompt_requires_authentication(self, client, mock_db):
        """Should return 401/302 when not authenticated."""
        # Arrange
        job_id = str(ObjectId())

        # Act
        response = client.get(f"/api/jobs/{job_id}/contacts/prompt")

        # Assert
        assert response.status_code in [401, 302]

    def test_get_prompt_invalid_job_id(self, authenticated_client, mock_db):
        """Should return 400 for invalid job ID format."""
        # Arrange
        invalid_job_id = "not-a-valid-objectid"

        # Act
        response = authenticated_client.get(f"/api/jobs/{invalid_job_id}/contacts/prompt")

        # Assert
        assert response.status_code == 400


class TestContactManagementUI:
    """Tests for Contact Management UI elements in job_detail.html."""

    def test_contact_section_has_management_buttons(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should show Copy Prompt and Add Contacts buttons when contacts exist."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["primary_contacts"] = [
            {"name": "Jane Doe", "role": "Hiring Manager", "linkedin_url": "https://linkedin.com/in/janedoe"}
        ]
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert 'copyFirecrawlPrompt()' in html
        assert 'openAddContactsModal()' in html

    def test_contact_cards_have_delete_button(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should show delete button on each contact card."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        sample_job_with_editor_state["primary_contacts"] = [
            {"name": "Jane Doe", "role": "Hiring Manager", "linkedin_url": "https://linkedin.com/in/janedoe"}
        ]
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert 'deleteContact(' in html

    def test_import_modal_exists(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should include the import contacts modal in the page."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert 'add-contacts-modal' in html
        assert 'contacts-json' in html

    def test_empty_contacts_shows_add_button(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should show Add Contacts button even when no contacts exist."""
        # Arrange
        job_id = str(sample_job["_id"])
        sample_job["primary_contacts"] = None
        sample_job["secondary_contacts"] = None
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        # Should still show the contacts section with add functionality
        assert 'openAddContactsModal()' in html or 'Add Contacts' in html
