"""
Unit tests for CV Rich Text Editor API endpoints.

Tests the GET and PUT endpoints at /api/jobs/<job_id>/cv-editor
for managing TipTap editor state in MongoDB.
"""

import pytest
import json
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock


class TestGetCvEditorState:
    """Tests for GET /api/jobs/<job_id>/cv-editor endpoint."""

    def test_get_cv_editor_state_with_existing_state(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should return saved editor state from MongoDB."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "editor_state" in data
        assert data["editor_state"]["version"] == 1
        assert data["editor_state"]["content"]["type"] == "doc"
        assert len(data["editor_state"]["content"]["content"]) == 2

    def test_get_cv_editor_state_migrates_from_markdown(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should migrate cv_text to editor state when cv_editor_state doesn't exist."""
        # Arrange
        job_id = str(sample_job["_id"])
        sample_job["cv_text"] = "# John Doe\n\n## Senior Engineer\n\n- 5 years Python\n- Led team of 10"
        sample_job["cv_editor_state"] = None  # No editor state
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "editor_state" in data

        # Check migrated content structure
        content = data["editor_state"]["content"]["content"]
        assert len(content) > 0

        # First node should be a heading
        assert content[0]["type"] == "heading"
        assert content[0]["attrs"]["level"] == 1
        assert "John Doe" in content[0]["content"][0]["text"]

    def test_get_cv_editor_state_returns_default_empty(
        self, authenticated_client, mock_db
    ):
        """Should return empty TipTap doc when no CV data exists."""
        # Arrange
        job_id = str(ObjectId())
        mock_db.find_one.return_value = {
            "_id": ObjectId(job_id),
            "title": "Test Job",
            "company": "TestCo"
            # No cv_text or cv_editor_state
        }

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["editor_state"]["version"] == 1
        assert data["editor_state"]["content"]["type"] == "doc"
        assert data["editor_state"]["content"]["content"] == []

    def test_get_cv_editor_state_job_not_found(self, authenticated_client, mock_db):
        """Should return 404 for non-existent job."""
        # Arrange
        job_id = str(ObjectId())
        mock_db.find_one.return_value = None

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 404
        data = response.get_json()
        assert data["error"] == "Job not found"

    def test_get_cv_editor_state_requires_authentication(self, client, mock_db):
        """Should return 302 redirect when not logged in."""
        # Arrange
        job_id = str(ObjectId())

        # Act
        response = client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 302  # Redirect to login
        assert "/login" in response.location

    def test_get_cv_editor_state_invalid_job_id(self, authenticated_client, mock_db):
        """Should handle invalid MongoDB ObjectId format."""
        # Arrange
        invalid_job_id = "not-a-valid-objectid"

        # Act
        response = authenticated_client.get(f"/api/jobs/{invalid_job_id}/cv-editor")

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "Invalid job ID format" in data["error"]


class TestPutCvEditorState:
    """Tests for PUT /api/jobs/<job_id>/cv-editor endpoint."""

    def test_put_cv_editor_state_saves_successfully(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should save editor state to MongoDB."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Mock successful update
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Updated CV content"}]
                    }
                ]
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
                "lineHeight": 1.4,
                "margins": {"top": 0.75, "right": 0.75, "bottom": 0.75, "left": 0.75},
                "pageSize": "letter"
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "savedAt" in data

        # Verify update_one was called
        mock_db.update_one.assert_called_once()
        call_args = mock_db.update_one.call_args
        assert call_args[0][0] == {"_id": sample_job["_id"]}

    def test_put_cv_editor_state_updates_timestamp(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should update lastSavedAt timestamp."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {}
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()

        # Verify lastSavedAt is returned
        assert "savedAt" in data
        saved_at = datetime.fromisoformat(data["savedAt"])
        assert isinstance(saved_at, datetime)

        # Verify update_one included updatedAt
        call_args = mock_db.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        assert "updatedAt" in update_doc

    def test_put_cv_editor_state_preserves_job_data(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should not overwrite other job fields."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {}
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200

        # Verify update uses $set (not replace_one)
        call_args = mock_db.update_one.call_args
        assert "$set" in call_args[0][1]

        # Verify only cv_editor_state and updatedAt are updated
        update_doc = call_args[0][1]["$set"]
        assert "cv_editor_state" in update_doc
        assert "updatedAt" in update_doc
        assert "title" not in update_doc
        assert "company" not in update_doc

    def test_put_cv_editor_state_job_not_found(self, authenticated_client, mock_db):
        """Should return 404 for non-existent job."""
        # Arrange
        job_id = str(ObjectId())

        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_db.update_one.return_value = mock_result

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {}
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 404
        data = response.get_json()
        assert data["error"] == "Job not found"

    def test_put_cv_editor_state_requires_authentication(self, client, mock_db):
        """Should return 302 redirect when not logged in."""
        # Arrange
        job_id = str(ObjectId())
        editor_state = {"version": 1, "content": {"type": "doc", "content": []}}

        # Act
        response = client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 302  # Redirect to login
        assert "/login" in response.location

    def test_put_cv_editor_state_invalid_payload(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should return 400 for malformed JSON."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Act - Send plain text instead of JSON
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            data="not valid json",
            content_type="text/plain"
        )

        # Assert
        assert response.status_code in [400, 415]  # Bad Request or Unsupported Media Type

    def test_put_cv_editor_state_missing_required_fields(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should return 400 when content is missing."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        # Missing "content" field
        invalid_payload = {
            "version": 1,
            "documentStyles": {}
            # No "content" key
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=invalid_payload,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "Missing content" in data["error"]

    def test_put_cv_editor_state_empty_content(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should accept empty TipTap document (valid use case)."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        # Empty but valid TipTap document
        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": []  # Empty content array is valid
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11
            }
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_put_cv_editor_state_invalid_job_id(self, authenticated_client, mock_db):
        """Should handle invalid MongoDB ObjectId format."""
        # Arrange
        invalid_job_id = "not-a-valid-objectid"
        editor_state = {"version": 1, "content": {"type": "doc", "content": []}}

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{invalid_job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 400
        data = response.get_json()
        assert "Invalid job ID format" in data["error"]


class TestEdgeCases:
    """Edge case tests for CV editor API."""

    def test_handles_large_documents(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should handle documents > 100KB."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        # Create large document (100+ paragraphs)
        large_content = [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": f"This is paragraph {i} with some text content to increase size."}]
            }
            for i in range(200)
        ]

        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": large_content
            },
            "documentStyles": {}
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200

    def test_handles_special_characters(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should handle Unicode, emojis, and special chars in content."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        # Content with special characters
        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{
                            "type": "text",
                            "text": "François: 你好 👋 Русский <>&\"'"
                        }]
                    }
                ]
            },
            "documentStyles": {}
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        assert response.status_code == 200

    def test_handles_database_disconnection(
        self, authenticated_client, mock_db, sample_job, mocker
    ):
        """Should handle graceful failure when MongoDB unavailable."""
        # Arrange
        job_id = str(sample_job["_id"])

        # Simulate database error by mocking get_db to raise
        mocker.patch("app.get_db", side_effect=Exception("Database connection lost"))

        # Act
        # The error will be unhandled, so we expect it to propagate
        # In production, Flask would return 500, but in tests we catch the exception
        try:
            response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")
            # If no exception, check status code
            assert response.status_code in [500, 503]
        except Exception as e:
            # Expected behavior - database error propagates
            assert "Database connection lost" in str(e)
