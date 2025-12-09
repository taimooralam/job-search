"""
Unit tests for job detail page fixes.

Tests the following fixes:
1. serialize_job() description field normalization (Issue 1)
2. CV editor disk fallback when cv_text missing but cv_path exists (Issue 3)
3. openAnnotationPanel() jobId parameter handling (Issue 4)
"""

import pytest
from datetime import datetime
from bson import ObjectId
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import os


class TestSerializeJobDescriptionNormalization:
    """Tests for serialize_job() description field normalization (Issue 1)."""

    def test_description_field_used_directly_when_present(self, app):
        """Should use 'description' field directly when it exists."""
        # Arrange
        from app import serialize_job

        job = {
            "_id": ObjectId(),
            "title": "Software Engineer",
            "description": "This is the main description",
            "job_description": "This should be ignored",
            "jobDescription": "This should also be ignored",
            "createdAt": datetime(2025, 12, 9, 10, 0, 0),
        }

        # Act
        result = serialize_job(job)

        # Assert
        assert result["description"] == "This is the main description"

    def test_job_description_normalized_to_description(self, app):
        """Should normalize 'job_description' to 'description' when description is missing."""
        # Arrange
        from app import serialize_job

        job = {
            "_id": ObjectId(),
            "title": "Senior Engineer",
            "job_description": "This is the job_description variant",
            "createdAt": datetime(2025, 12, 9, 10, 0, 0),
        }

        # Act
        result = serialize_job(job)

        # Assert
        assert result["description"] == "This is the job_description variant"
        assert "job_description" in result  # Original field preserved

    def test_camel_case_job_description_normalized(self, app):
        """Should normalize 'jobDescription' (camelCase) to 'description'."""
        # Arrange
        from app import serialize_job

        job = {
            "_id": ObjectId(),
            "title": "Staff Engineer",
            "jobDescription": "This is the camelCase variant",
            "createdAt": datetime(2025, 12, 9, 10, 0, 0),
        }

        # Act
        result = serialize_job(job)

        # Assert
        assert result["description"] == "This is the camelCase variant"
        assert "jobDescription" in result  # Original field preserved

    def test_priority_description_over_job_description(self, app):
        """Should prioritize 'description' over 'job_description'."""
        # Arrange
        from app import serialize_job

        job = {
            "_id": ObjectId(),
            "title": "Principal Engineer",
            "description": "Priority description",
            "job_description": "Should be ignored",
            "createdAt": datetime(2025, 12, 9, 10, 0, 0),
        }

        # Act
        result = serialize_job(job)

        # Assert
        assert result["description"] == "Priority description"

    def test_priority_job_description_over_camel_case(self, app):
        """Should prioritize 'job_description' over 'jobDescription'."""
        # Arrange
        from app import serialize_job

        job = {
            "_id": ObjectId(),
            "title": "Lead Engineer",
            "job_description": "Snake case wins",
            "jobDescription": "CamelCase loses",
            "createdAt": datetime(2025, 12, 9, 10, 0, 0),
        }

        # Act
        result = serialize_job(job)

        # Assert
        assert result["description"] == "Snake case wins"

    def test_empty_string_when_no_description_variants(self, app):
        """Should set description to empty string when no variants exist."""
        # Arrange
        from app import serialize_job

        job = {
            "_id": ObjectId(),
            "title": "Backend Engineer",
            "createdAt": datetime(2025, 12, 9, 10, 0, 0),
        }

        # Act
        result = serialize_job(job)

        # Assert
        assert result["description"] == ""

    def test_handles_none_values_in_description_variants(self, app):
        """Should handle None values gracefully in description fields."""
        # Arrange
        from app import serialize_job

        job = {
            "_id": ObjectId(),
            "title": "DevOps Engineer",
            "description": None,
            "job_description": None,
            "jobDescription": "Only this has value",
            "createdAt": datetime(2025, 12, 9, 10, 0, 0),
        }

        # Act
        result = serialize_job(job)

        # Assert
        assert result["description"] == "Only this has value"

    def test_object_id_and_datetime_serialization(self, app):
        """Should properly serialize ObjectId and datetime fields."""
        # Arrange
        from app import serialize_job

        obj_id = ObjectId()
        created_at = datetime(2025, 12, 9, 10, 30, 0)

        job = {
            "_id": obj_id,
            "title": "Full Stack Engineer",
            "description": "Great job",
            "createdAt": created_at,
            "nested_id": ObjectId(),
        }

        # Act
        result = serialize_job(job)

        # Assert
        assert result["_id"] == str(obj_id)
        assert result["createdAt"] == created_at.isoformat()
        assert isinstance(result["nested_id"], str)  # ObjectId converted to string


class TestCvEditorDiskFallback:
    """Tests for CV editor disk fallback when cv_text missing (Issue 3)."""

    def test_cv_editor_loads_from_disk_when_cv_path_exists(
        self, authenticated_client, mock_db, tmp_path
    ):
        """Should load CV from disk when cv_text is missing but cv_path exists."""
        # Arrange
        job_id = str(ObjectId())

        # Create temporary CV file
        cv_file = tmp_path / "test_cv.md"
        cv_content = "# Jane Doe\n\n## Senior Engineer\n\n- 10 years experience\n- Led teams"
        cv_file.write_text(cv_content, encoding="utf-8")

        mock_db.find_one.return_value = {
            "_id": ObjectId(job_id),
            "title": "Senior Engineer",
            "company": "TechCorp",
            "cv_path": str(cv_file),  # Path exists
            # cv_text is missing
            # cv_editor_state is missing
        }

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "editor_state" in data

        # Check migrated content from disk
        content = data["editor_state"]["content"]["content"]
        assert len(content) > 0

        # Should have heading with "Jane Doe"
        heading_found = False
        for node in content:
            if node["type"] == "heading" and node.get("attrs", {}).get("level") == 1:
                if any("Jane Doe" in c.get("text", "") for c in node.get("content", [])):
                    heading_found = True

        assert heading_found, "Migrated content should include heading with 'Jane Doe'"

    def test_cv_editor_handles_missing_cv_path_file(
        self, authenticated_client, mock_db
    ):
        """Should handle gracefully when cv_path points to non-existent file."""
        # Arrange
        job_id = str(ObjectId())

        mock_db.find_one.return_value = {
            "_id": ObjectId(job_id),
            "title": "Data Scientist",
            "company": "DataCo",
            "cv_path": "/non/existent/path/cv.md",  # Path doesn't exist
            # cv_text is missing
        }

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        # Should return default empty state (fallback)
        assert data["editor_state"]["version"] == 1
        assert data["editor_state"]["content"]["type"] == "doc"
        assert data["editor_state"]["content"]["content"] == []

    def test_cv_editor_prioritizes_cv_text_over_cv_path(
        self, authenticated_client, mock_db, tmp_path
    ):
        """Should prioritize cv_text over cv_path when both exist."""
        # Arrange
        job_id = str(ObjectId())

        # Create disk file
        cv_file = tmp_path / "disk_cv.md"
        cv_file.write_text("# Disk CV\n\nThis should be ignored", encoding="utf-8")

        mock_db.find_one.return_value = {
            "_id": ObjectId(job_id),
            "title": "ML Engineer",
            "company": "AI Corp",
            "cv_text": "# Memory CV\n\nThis should be used",
            "cv_path": str(cv_file),
        }

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()

        # Check content came from cv_text, not cv_path
        content = data["editor_state"]["content"]["content"]
        memory_cv_found = False
        disk_cv_found = False

        for node in content:
            if node["type"] == "heading":
                for c in node.get("content", []):
                    text = c.get("text", "")
                    if "Memory CV" in text:
                        memory_cv_found = True
                    if "Disk CV" in text:
                        disk_cv_found = True

        assert memory_cv_found, "Should use cv_text (Memory CV)"
        assert not disk_cv_found, "Should NOT use cv_path (Disk CV)"

    def test_cv_editor_handles_disk_read_errors(
        self, authenticated_client, mock_db, tmp_path, mocker
    ):
        """Should handle file read errors gracefully and return default state."""
        # Arrange
        job_id = str(ObjectId())

        cv_file = tmp_path / "error_cv.md"
        cv_file.write_text("# Test CV", encoding="utf-8")

        mock_db.find_one.return_value = {
            "_id": ObjectId(job_id),
            "title": "Architect",
            "company": "DesignCo",
            "cv_path": str(cv_file),
        }

        # Mock Path.read_text to raise exception
        with patch("pathlib.Path.read_text", side_effect=IOError("Permission denied")):
            # Act
            response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

            # Assert
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True

            # Should return default empty state
            assert data["editor_state"]["content"]["content"] == []

    def test_cv_editor_uses_existing_editor_state_over_all(
        self, authenticated_client, mock_db, tmp_path
    ):
        """Should prioritize existing cv_editor_state over cv_text and cv_path."""
        # Arrange
        job_id = str(ObjectId())

        cv_file = tmp_path / "disk_cv.md"
        cv_file.write_text("# Disk CV", encoding="utf-8")

        existing_editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 1},
                        "content": [{"type": "text", "text": "Editor State CV"}]
                    }
                ]
            },
            "documentStyles": {
                "fontFamily": "Inter",
                "fontSize": 11,
            }
        }

        mock_db.find_one.return_value = {
            "_id": ObjectId(job_id),
            "title": "CTO",
            "company": "Startup",
            "cv_text": "# Memory CV",
            "cv_path": str(cv_file),
            "cv_editor_state": existing_editor_state,
        }

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()

        # Should use existing editor state
        content = data["editor_state"]["content"]["content"]
        assert len(content) == 1
        assert content[0]["content"][0]["text"] == "Editor State CV"


class TestAnnotationPanelJobId:
    """Tests for annotation panel jobId parameter handling (Issue 4)."""

    def test_open_annotation_panel_with_explicit_job_id(
        self, authenticated_client, mock_db
    ):
        """Should use explicit jobId parameter when provided."""
        # This is a JavaScript function test - testing the Flask template rendering
        # that sets up the data attribute correctly

        # Arrange
        job_id = str(ObjectId())
        mock_db.find_one.return_value = {
            "_id": ObjectId(job_id),
            "title": "Test Job",
            "company": "TestCo",
            "description": "Test description",
            "status": "not processed",
            "score": 75,
        }

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Verify the panel has data-job-id attribute set
        # Template uses: data-job-id="{{ job._id }}"
        assert f'data-job-id="{job_id}"' in html, f"Expected to find data-job-id=\"{job_id}\" in HTML"

    def test_job_detail_page_sets_annotation_panel_data_attribute(
        self, authenticated_client, mock_db
    ):
        """Should set data-job-id on annotation panel element in job detail page."""
        # Arrange
        job_id = str(ObjectId())
        mock_db.find_one.return_value = {
            "_id": ObjectId(job_id),
            "title": "Senior Developer",
            "company": "DevCorp",
            "description": "Great opportunity",
            "status": "not processed",
            "score": 85,
        }

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Check for annotation panel with data attribute
        assert 'id="jd-annotation-panel"' in html
        assert f'data-job-id="{job_id}"' in html, f"Expected to find data-job-id=\"{job_id}\" in HTML"

    def test_annotation_panel_has_job_id_in_config(
        self, authenticated_client, mock_db
    ):
        """Should pass job ID via JOB_DETAIL_CONFIG for JavaScript access."""
        # Arrange
        job_id = str(ObjectId())
        mock_db.find_one.return_value = {
            "_id": ObjectId(job_id),
            "title": "Lead Engineer",
            "company": "LeadCo",
            "description": "Leadership role",
            "status": "not processed",
            "score": 90,
        }

        # Act
        response = authenticated_client.get(f"/job/{job_id}")

        # Assert
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Check for JOB_DETAIL_CONFIG with jobId
        # This is used by external JS files
        assert "window.JOB_DETAIL_CONFIG" in html
        assert f'jobId: "{job_id}"' in html


class TestSerializeJobEdgeCases:
    """Additional edge case tests for serialize_job()."""

    def test_preserves_all_original_fields(self, app):
        """Should preserve all original job fields including description variants."""
        # Arrange
        from app import serialize_job

        job = {
            "_id": ObjectId(),
            "title": "DevOps Lead",
            "description": "Main description",
            "job_description": "Alternative description",
            "jobDescription": "CamelCase description",
            "status": "not processed",
            "score": 88,
            "custom_field": "custom_value",
            "createdAt": datetime(2025, 12, 9, 10, 0, 0),
        }

        # Act
        result = serialize_job(job)

        # Assert
        assert result["description"] == "Main description"
        assert result["job_description"] == "Alternative description"
        assert result["jobDescription"] == "CamelCase description"
        assert result["custom_field"] == "custom_value"
        assert result["status"] == "not processed"

    def test_handles_empty_string_in_description(self, app):
        """Should handle empty string in description field correctly."""
        # Arrange
        from app import serialize_job

        job = {
            "_id": ObjectId(),
            "title": "QA Engineer",
            "description": "",  # Empty but present
            "job_description": "This should be used as fallback",
        }

        # Act
        result = serialize_job(job)

        # Assert
        # Empty string is falsy, so fallback should kick in
        assert result["description"] == "This should be used as fallback"

    def test_handles_whitespace_only_description(self, app):
        """Should handle whitespace-only description."""
        # Arrange
        from app import serialize_job

        job = {
            "_id": ObjectId(),
            "title": "Security Engineer",
            "description": "   ",  # Whitespace only
            "job_description": "Real description",
        }

        # Act
        result = serialize_job(job)

        # Assert
        # Whitespace is truthy in Python, so it should be preserved
        assert result["description"] == "   "


class TestCvEditorIntegration:
    """Integration tests for CV editor with description normalization."""

    def test_cv_editor_works_with_normalized_description(
        self, authenticated_client, mock_db
    ):
        """Should work correctly with normalized description field."""
        # Arrange
        job_id = str(ObjectId())

        mock_db.find_one.return_value = {
            "_id": ObjectId(job_id),
            "title": "Platform Engineer",
            "company": "Platform Co",
            "job_description": "Build scalable platforms",  # Using snake_case variant
            "cv_text": "# My CV\n\n## Experience",
        }

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "editor_state" in data
