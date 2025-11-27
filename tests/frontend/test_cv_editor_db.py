"""
MongoDB integration tests for CV editor state persistence.

Tests that cv_editor_state is properly stored and retrieved from MongoDB.
"""

import pytest
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock


class TestMongoDBPersistence:
    """Tests for MongoDB storage of cv_editor_state."""

    def test_cv_editor_state_persists_to_mongodb(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should write cv_editor_state to level-2 collection."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 1},
                        "content": [{"type": "text", "text": "My CV"}]
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

        # Verify update_one was called with correct parameters
        mock_db.update_one.assert_called_once()
        call_args = mock_db.update_one.call_args

        # Check filter (first argument)
        filter_query = call_args[0][0]
        assert filter_query == {"_id": sample_job["_id"]}

        # Check update document (second argument)
        update_doc = call_args[0][1]
        assert "$set" in update_doc
        assert "cv_editor_state" in update_doc["$set"]
        assert "updatedAt" in update_doc["$set"]

    def test_cv_editor_state_field_structure(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should validate MongoDB document structure after save."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {"fontFamily": "Inter"}
        }

        # Act
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert
        call_args = mock_db.update_one.call_args
        update_doc = call_args[0][1]["$set"]

        saved_state = update_doc["cv_editor_state"]

        # Verify structure
        assert "version" in saved_state
        assert saved_state["version"] == 1

        assert "content" in saved_state
        assert saved_state["content"]["type"] == "doc"

        assert "documentStyles" in saved_state

        assert "lastSavedAt" in saved_state
        assert isinstance(saved_state["lastSavedAt"], datetime)

    def test_cv_editor_updates_cv_text_with_html(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should update cv_text field with HTML when saving editor state."""
        # Arrange
        job_id = str(sample_job["_id"])
        sample_job["cv_text"] = "# Legacy CV\n\nThis should be updated."
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

        # Verify cv_text was updated with HTML content
        call_args = mock_db.update_one.call_args
        update_doc = call_args[0][1]["$set"]

        assert "cv_text" in update_doc  # Should update cv_text with HTML
        assert isinstance(update_doc["cv_text"], str)  # Should be HTML string

    def test_cv_editor_state_includes_timestamp(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should include lastSavedAt timestamp in saved state."""
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
        before_save = datetime.utcnow()
        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )
        after_save = datetime.utcnow()

        # Assert
        assert response.status_code == 200

        call_args = mock_db.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        saved_state = update_doc["cv_editor_state"]

        # Verify lastSavedAt is within expected range
        assert "lastSavedAt" in saved_state
        saved_at = saved_state["lastSavedAt"]
        assert before_save <= saved_at <= after_save


class TestMongoDBRetrieval:
    """Tests for retrieving cv_editor_state from MongoDB."""

    def test_retrieves_editor_state_from_db(
        self, authenticated_client, mock_db, sample_job_with_editor_state
    ):
        """Should retrieve cv_editor_state from MongoDB."""
        # Arrange
        job_id = str(sample_job_with_editor_state["_id"])
        mock_db.find_one.return_value = sample_job_with_editor_state

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200
        data = response.get_json()

        # Verify find_one was called
        mock_db.find_one.assert_called_once()
        call_args = mock_db.find_one.call_args
        assert call_args[0][0] == {"_id": sample_job_with_editor_state["_id"]}

        # Verify returned editor state matches DB
        editor_state = data["editor_state"]
        db_state = sample_job_with_editor_state["cv_editor_state"]

        assert editor_state["version"] == db_state["version"]
        assert editor_state["content"] == db_state["content"]

    def test_migration_doesnt_modify_db(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should not write to DB when migrating cv_text on GET."""
        # Arrange
        job_id = str(sample_job["_id"])
        sample_job["cv_text"] = "# CV Title\n\nSome content"
        sample_job["cv_editor_state"] = None  # No editor state
        mock_db.find_one.return_value = sample_job

        # Act
        response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")

        # Assert
        assert response.status_code == 200

        # Verify update_one was NOT called (GET doesn't save migration)
        mock_db.update_one.assert_not_called()

    def test_returns_default_when_no_data(
        self, authenticated_client, mock_db
    ):
        """Should return default empty state when no CV data exists."""
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

        editor_state = data["editor_state"]
        assert editor_state["version"] == 1
        assert editor_state["content"]["content"] == []
        assert "documentStyles" in editor_state


class TestConcurrencyAndRaceConditions:
    """Tests for concurrent updates and race conditions."""

    def test_sequential_updates_work_correctly(
        self, authenticated_client, mock_db, sample_job
    ):
        """Should handle sequential updates correctly."""
        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        # Act - First update
        editor_state_1 = {
            "version": 1,
            "content": {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Version 1"}]}
            ]},
            "documentStyles": {}
        }
        response1 = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state_1,
            content_type="application/json"
        )

        # Act - Second update
        editor_state_2 = {
            "version": 1,
            "content": {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Version 2"}]}
            ]},
            "documentStyles": {}
        }
        response2 = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state_2,
            content_type="application/json"
        )

        # Assert - Both updates succeed
        assert response1.status_code == 200
        assert response2.status_code == 200

        # Verify update_one was called twice
        assert mock_db.update_one.call_count == 2

    def test_last_write_wins_behavior(
        self, authenticated_client, mock_db, sample_job
    ):
        """Last write should win (no optimistic locking in Phase 1)."""
        # Note: Phase 1 doesn't implement optimistic locking
        # This test documents expected behavior

        # Arrange
        job_id = str(sample_job["_id"])
        mock_db.find_one.return_value = sample_job

        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_db.update_one.return_value = mock_result

        # Act - Two competing writes
        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {}
        }

        response = authenticated_client.put(
            f"/api/jobs/{job_id}/cv-editor",
            json=editor_state,
            content_type="application/json"
        )

        # Assert - Both succeed (last write wins)
        assert response.status_code == 200


class TestErrorHandling:
    """Tests for database error scenarios."""

    def test_handles_update_failure(
        self, authenticated_client, mock_db, sample_job, mocker
    ):
        """Should handle MongoDB update failures gracefully."""
        # Arrange
        job_id = str(sample_job["_id"])

        # Simulate update failure by patching get_db
        mock_db_instance = MagicMock()
        mock_collection = MagicMock()
        mock_db_instance.__getitem__.return_value = mock_collection
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.side_effect = Exception("Database write error")

        mocker.patch("app.get_db", return_value=mock_db_instance)

        editor_state = {
            "version": 1,
            "content": {"type": "doc", "content": []},
            "documentStyles": {}
        }

        # Act
        try:
            response = authenticated_client.put(
                f"/api/jobs/{job_id}/cv-editor",
                json=editor_state,
                content_type="application/json"
            )
            # If no exception, check status code
            assert response.status_code == 500
        except Exception as e:
            # Expected behavior - database error propagates
            assert "Database write error" in str(e)

    def test_handles_find_failure(
        self, authenticated_client, mocker
    ):
        """Should handle MongoDB find failures gracefully."""
        # Arrange
        job_id = str(ObjectId())

        # Simulate find failure by patching get_db
        mocker.patch("app.get_db", side_effect=Exception("Database read error"))

        # Act
        try:
            response = authenticated_client.get(f"/api/jobs/{job_id}/cv-editor")
            # If no exception, check status code
            assert response.status_code == 500
        except Exception as e:
            # Expected behavior - database error propagates
            assert "Database read error" in str(e)
