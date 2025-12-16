"""
Tests for runner_service/persistence.py

Tests the MongoDB persistence logic, specifically verifying that boolean
progress flags (processed_jd, has_research, generated_cv) are set based
on data presence, not just pipeline completion status.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


class TestPersistRunToMongo:
    """Tests for persist_run_to_mongo function."""

    @pytest.fixture
    def mock_mongo_client(self):
        """Create a mock MongoDB client."""
        with patch("runner_service.persistence.MongoClient") as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.update_one.return_value = MagicMock(matched_count=1)
            mock_db.__getitem__.return_value = mock_collection
            mock_client.return_value.__getitem__.return_value = mock_db
            yield mock_client, mock_collection

    @pytest.fixture
    def base_args(self):
        """Base arguments for persist_run_to_mongo."""
        return {
            "job_id": "507f1f77bcf86cd799439011",
            "run_id": "test-run-123",
            "status": "running",
            "started_at": datetime(2024, 1, 1, 12, 0, 0),
            "updated_at": datetime(2024, 1, 1, 12, 5, 0),
            "artifacts": {},
        }

    def test_boolean_flags_set_when_data_present_and_running(
        self, mock_mongo_client, base_args
    ):
        """Boolean flags should be set when data is present, even if status is 'running'."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            # Pipeline state with JD data (pain_points) - status is "running"
            pipeline_state = {
                "pain_points": ["Need to improve deployment speed"],
                "strategic_needs": None,
            }

            persist_run_to_mongo(
                **base_args,
                pipeline_state=pipeline_state,
            )

            # Verify update_one was called
            mock_collection.update_one.assert_called_once()
            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            # processed_jd should be True because pain_points exists
            assert update_doc["$set"]["processed_jd"] is True

            # has_research and generated_cv should NOT be in $set (no data)
            assert "has_research" not in update_doc["$set"]
            assert "generated_cv" not in update_doc["$set"]

    def test_cv_flag_set_when_cv_text_present(self, mock_mongo_client, base_args):
        """generated_cv flag should be set when cv_text is present."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            pipeline_state = {
                "cv_text": "# John Doe\nSenior Engineer...",
            }

            persist_run_to_mongo(
                **base_args,
                pipeline_state=pipeline_state,
            )

            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            assert update_doc["$set"]["generated_cv"] is True

    def test_cv_flag_set_when_cv_editor_state_present(self, mock_mongo_client, base_args):
        """generated_cv flag should be set when cv_editor_state is present."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            pipeline_state = {
                "cv_editor_state": {"content": {"type": "doc", "content": []}},
            }

            persist_run_to_mongo(
                **base_args,
                pipeline_state=pipeline_state,
            )

            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            assert update_doc["$set"]["generated_cv"] is True

    def test_research_flag_set_when_company_research_present(
        self, mock_mongo_client, base_args
    ):
        """has_research flag should be set when company_research is present."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            pipeline_state = {
                "company_research": {"summary": "Acme Corp is a tech company..."},
            }

            persist_run_to_mongo(
                **base_args,
                pipeline_state=pipeline_state,
            )

            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            assert update_doc["$set"]["has_research"] is True

    def test_research_flag_set_when_role_research_present(
        self, mock_mongo_client, base_args
    ):
        """has_research flag should be set when role_research is present."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            pipeline_state = {
                "role_research": {"key_skills": ["Python", "AWS"]},
            }

            persist_run_to_mongo(
                **base_args,
                pipeline_state=pipeline_state,
            )

            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            assert update_doc["$set"]["has_research"] is True

    def test_all_flags_set_when_all_data_present(self, mock_mongo_client, base_args):
        """All boolean flags should be set when all corresponding data is present."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            pipeline_state = {
                "pain_points": ["Need better DevOps"],
                "company_research": {"summary": "Tech company"},
                "cv_text": "# Resume content",
            }

            persist_run_to_mongo(
                **base_args,
                pipeline_state=pipeline_state,
            )

            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            assert update_doc["$set"]["processed_jd"] is True
            assert update_doc["$set"]["has_research"] is True
            assert update_doc["$set"]["generated_cv"] is True

    def test_no_flags_set_when_pipeline_state_is_none(self, mock_mongo_client, base_args):
        """No boolean flags should be set when pipeline_state is None."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            persist_run_to_mongo(
                **base_args,
                pipeline_state=None,
            )

            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            assert "processed_jd" not in update_doc["$set"]
            assert "has_research" not in update_doc["$set"]
            assert "generated_cv" not in update_doc["$set"]

    def test_no_flags_set_when_pipeline_state_is_empty(
        self, mock_mongo_client, base_args
    ):
        """No boolean flags should be set when pipeline_state is empty dict."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            persist_run_to_mongo(
                **base_args,
                pipeline_state={},
            )

            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            # Flags should not be in $set since no data is present
            assert "processed_jd" not in update_doc["$set"]
            assert "has_research" not in update_doc["$set"]
            assert "generated_cv" not in update_doc["$set"]

    def test_state_fields_only_persisted_on_completion(self, mock_mongo_client, base_args):
        """State fields (pain_points, cv_text, etc.) should only be persisted when status is 'completed'."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            pipeline_state = {
                "pain_points": ["Need better DevOps"],
                "cv_text": "# Resume",
            }

            # Status is "running" - state fields should NOT be persisted
            persist_run_to_mongo(
                **base_args,  # status is "running"
                pipeline_state=pipeline_state,
            )

            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            # State fields should NOT be in $set (status is not "completed")
            assert "pain_points" not in update_doc["$set"]
            assert "cv_text" not in update_doc["$set"]

            # But boolean flags SHOULD be set based on data presence
            assert update_doc["$set"]["processed_jd"] is True
            assert update_doc["$set"]["generated_cv"] is True

    def test_state_fields_persisted_on_completion(self, mock_mongo_client, base_args):
        """State fields should be persisted when status is 'completed'."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            base_args["status"] = "completed"
            pipeline_state = {
                "pain_points": ["Need better DevOps"],
                "cv_text": "# Resume",
            }

            persist_run_to_mongo(
                **base_args,
                pipeline_state=pipeline_state,
            )

            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            # State fields SHOULD be in $set (status is "completed")
            assert update_doc["$set"]["pain_points"] == ["Need better DevOps"]
            assert update_doc["$set"]["cv_text"] == "# Resume"

            # Boolean flags should also be set
            assert update_doc["$set"]["processed_jd"] is True
            assert update_doc["$set"]["generated_cv"] is True

    def test_job_status_updated_on_completion(self, mock_mongo_client, base_args):
        """Job status should be set to 'ready for applying' when pipeline completes."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            base_args["status"] = "completed"

            persist_run_to_mongo(
                **base_args,
                pipeline_state={},
            )

            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            assert update_doc["$set"]["status"] == "ready for applying"

    def test_skips_persistence_when_mongodb_uri_not_set(self, base_args):
        """Should skip persistence when MONGODB_URI is not set."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove MONGODB_URI from environment
            import os
            if "MONGODB_URI" in os.environ:
                del os.environ["MONGODB_URI"]

            from runner_service.persistence import persist_run_to_mongo

            # Should not raise any errors
            persist_run_to_mongo(
                **base_args,
                pipeline_state={"cv_text": "test"},
            )

    def test_handles_invalid_job_id_gracefully(self, mock_mongo_client, base_args):
        """Should handle invalid ObjectId format gracefully."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import persist_run_to_mongo

            base_args["job_id"] = "not-a-valid-object-id"

            # Should not raise, should use string fallback
            persist_run_to_mongo(
                **base_args,
                pipeline_state={},
            )

            # Should still call update_one (with string job_id as fallback)
            mock_collection.update_one.assert_called_once()


class TestUpdateJobPipelineFailed:
    """Tests for update_job_pipeline_failed function."""

    @pytest.fixture
    def mock_mongo_client(self):
        """Create a mock MongoDB client."""
        with patch("runner_service.persistence.MongoClient") as mock_client:
            mock_db = MagicMock()
            mock_collection = MagicMock()
            mock_collection.update_one.return_value = MagicMock(matched_count=1)
            mock_db.__getitem__.return_value = mock_collection
            mock_client.return_value.__getitem__.return_value = mock_db
            yield mock_client, mock_collection

    def test_updates_pipeline_failed_status(self, mock_mongo_client):
        """Should update job with pipeline_failed status and error message."""
        _, mock_collection = mock_mongo_client

        with patch.dict("os.environ", {"MONGODB_URI": "mongodb://test"}):
            from runner_service.persistence import update_job_pipeline_failed

            update_job_pipeline_failed(
                job_id="507f1f77bcf86cd799439011",
                error="Layer 3 failed: API timeout",
            )

            mock_collection.update_one.assert_called_once()
            call_args = mock_collection.update_one.call_args
            update_doc = call_args[0][1]

            assert update_doc["$set"]["pipeline_status"] == "pipeline_failed"
            assert update_doc["$set"]["pipeline_error"] == "Layer 3 failed: API timeout"
            assert "pipeline_failed_at" in update_doc["$set"]
