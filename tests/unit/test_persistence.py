"""
Tests for runner_service/persistence.py

Tests the MongoDB persistence logic using the repository pattern.
Verifies that boolean progress flags (processed_jd, has_research, generated_cv)
are set based on data presence, not just pipeline completion status.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.common.repositories import WriteResult, reset_repository


class TestPersistRunToMongo:
    """Tests for persist_run_to_mongo function."""

    @pytest.fixture(autouse=True)
    def reset_repo_singleton(self):
        """Reset repository singleton before each test."""
        reset_repository()
        yield
        reset_repository()

    @pytest.fixture
    def mock_repository(self):
        """Create a mock job repository."""
        mock_repo = MagicMock()
        mock_repo.update_one.return_value = WriteResult(matched_count=1, modified_count=1)

        # Patch at the source module since persist_run_to_mongo imports inside the function
        with patch("src.common.repositories.get_job_repository", return_value=mock_repo):
            yield mock_repo

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
        self, mock_repository, base_args
    ):
        """Boolean flags should be set when data is present, even if status is 'running'."""
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
        mock_repository.update_one.assert_called_once()
        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        # processed_jd should be True because pain_points exists
        assert update_doc["$set"]["processed_jd"] is True

        # has_research and generated_cv should NOT be in $set (no data)
        assert "has_research" not in update_doc["$set"]
        assert "generated_cv" not in update_doc["$set"]

    def test_cv_flag_set_when_cv_text_present(self, mock_repository, base_args):
        """generated_cv flag should be set when cv_text is present."""
        from runner_service.persistence import persist_run_to_mongo

        pipeline_state = {
            "cv_text": "# John Doe\nSenior Engineer...",
        }

        persist_run_to_mongo(
            **base_args,
            pipeline_state=pipeline_state,
        )

        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        assert update_doc["$set"]["generated_cv"] is True

    def test_cv_flag_set_when_cv_editor_state_present(self, mock_repository, base_args):
        """generated_cv flag should be set when cv_editor_state is present."""
        from runner_service.persistence import persist_run_to_mongo

        pipeline_state = {
            "cv_editor_state": {"content": {"type": "doc", "content": []}},
        }

        persist_run_to_mongo(
            **base_args,
            pipeline_state=pipeline_state,
        )

        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        assert update_doc["$set"]["generated_cv"] is True

    def test_research_flag_set_when_company_research_present(
        self, mock_repository, base_args
    ):
        """has_research flag should be set when company_research is present."""
        from runner_service.persistence import persist_run_to_mongo

        pipeline_state = {
            "company_research": {"summary": "Acme Corp is a tech company..."},
        }

        persist_run_to_mongo(
            **base_args,
            pipeline_state=pipeline_state,
        )

        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        assert update_doc["$set"]["has_research"] is True

    def test_research_flag_set_when_role_research_present(
        self, mock_repository, base_args
    ):
        """has_research flag should be set when role_research is present."""
        from runner_service.persistence import persist_run_to_mongo

        pipeline_state = {
            "role_research": {"key_skills": ["Python", "AWS"]},
        }

        persist_run_to_mongo(
            **base_args,
            pipeline_state=pipeline_state,
        )

        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        assert update_doc["$set"]["has_research"] is True

    def test_all_flags_set_when_all_data_present(self, mock_repository, base_args):
        """All boolean flags should be set when all corresponding data is present."""
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

        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        assert update_doc["$set"]["processed_jd"] is True
        assert update_doc["$set"]["has_research"] is True
        assert update_doc["$set"]["generated_cv"] is True

    def test_no_flags_set_when_pipeline_state_is_none(self, mock_repository, base_args):
        """No boolean flags should be set when pipeline_state is None."""
        from runner_service.persistence import persist_run_to_mongo

        persist_run_to_mongo(
            **base_args,
            pipeline_state=None,
        )

        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        assert "processed_jd" not in update_doc["$set"]
        assert "has_research" not in update_doc["$set"]
        assert "generated_cv" not in update_doc["$set"]

    def test_no_flags_set_when_pipeline_state_is_empty(
        self, mock_repository, base_args
    ):
        """No boolean flags should be set when pipeline_state is empty dict."""
        from runner_service.persistence import persist_run_to_mongo

        persist_run_to_mongo(
            **base_args,
            pipeline_state={},
        )

        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        # Flags should not be in $set since no data is present
        assert "processed_jd" not in update_doc["$set"]
        assert "has_research" not in update_doc["$set"]
        assert "generated_cv" not in update_doc["$set"]

    def test_state_fields_only_persisted_on_completion(self, mock_repository, base_args):
        """State fields (pain_points, cv_text, etc.) should only be persisted when status is 'completed'."""
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

        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        # State fields should NOT be in $set (status is not "completed")
        assert "pain_points" not in update_doc["$set"]
        assert "cv_text" not in update_doc["$set"]

        # But boolean flags SHOULD be set based on data presence
        assert update_doc["$set"]["processed_jd"] is True
        assert update_doc["$set"]["generated_cv"] is True

    def test_state_fields_persisted_on_completion(self, mock_repository, base_args):
        """State fields should be persisted when status is 'completed'."""
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

        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        # State fields SHOULD be in $set (status is "completed")
        assert update_doc["$set"]["pain_points"] == ["Need better DevOps"]
        assert update_doc["$set"]["cv_text"] == "# Resume"

        # Boolean flags should also be set
        assert update_doc["$set"]["processed_jd"] is True
        assert update_doc["$set"]["generated_cv"] is True

    def test_job_status_updated_on_completion(self, mock_repository, base_args):
        """Job status should be set to 'ready for applying' when pipeline completes."""
        from runner_service.persistence import persist_run_to_mongo

        base_args["status"] = "completed"

        persist_run_to_mongo(
            **base_args,
            pipeline_state={},
        )

        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        assert update_doc["$set"]["status"] == "ready for applying"

    def test_skips_persistence_when_mongodb_uri_not_set(self, base_args):
        """Should skip persistence when MONGODB_URI is not set."""
        with patch.dict("os.environ", {}, clear=True):
            from runner_service.persistence import persist_run_to_mongo

            # Should not raise any errors (logs debug message)
            persist_run_to_mongo(
                **base_args,
                pipeline_state={"cv_text": "test"},
            )

    def test_handles_invalid_job_id_gracefully(self, mock_repository, base_args):
        """Should handle invalid ObjectId format gracefully."""
        from runner_service.persistence import persist_run_to_mongo

        base_args["job_id"] = "not-a-valid-object-id"

        # Should not raise, should use string fallback
        persist_run_to_mongo(
            **base_args,
            pipeline_state={},
        )

        # Should still call update_one (with string job_id as fallback)
        mock_repository.update_one.assert_called_once()

    def test_returns_false_when_job_not_found(self, mock_repository, base_args):
        """Should return False when job not found in MongoDB."""
        mock_repository.update_one.return_value = WriteResult(
            matched_count=0, modified_count=0
        )

        from runner_service.persistence import persist_run_to_mongo

        result = persist_run_to_mongo(
            **base_args,
            pipeline_state={},
        )

        assert result is False
        mock_repository.update_one.assert_called_once()

    def test_returns_true_on_successful_update(self, mock_repository, base_args):
        """Should return True when update succeeds."""
        mock_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1
        )

        from runner_service.persistence import persist_run_to_mongo

        result = persist_run_to_mongo(
            **base_args,
            pipeline_state={},
        )

        assert result is True

    def test_verification_readback_for_completed_cv(self, mock_repository, base_args):
        """Should verify CV was saved by reading back for completed pipelines."""
        base_args["status"] = "completed"
        pipeline_state = {"cv_text": "# My CV content"}

        # Mock find_one to return the saved document
        mock_repository.find_one.return_value = {
            "cv_text": "# My CV content",
            "generated_cv": True,
            "pipeline_status": "completed"
        }

        from runner_service.persistence import persist_run_to_mongo

        result = persist_run_to_mongo(
            **base_args,
            pipeline_state=pipeline_state,
        )

        assert result is True
        # Verify find_one was called for verification
        mock_repository.find_one.assert_called_once()

    def test_verification_fails_when_cv_not_saved(self, mock_repository, base_args):
        """Should return False when verification shows CV was not saved."""
        base_args["status"] = "completed"
        pipeline_state = {"cv_text": "# My CV content"}

        # Mock find_one to return document WITHOUT cv_text (simulating save failure)
        mock_repository.find_one.return_value = {
            "cv_text": None,
            "generated_cv": None,
            "pipeline_status": "completed"
        }

        from runner_service.persistence import persist_run_to_mongo

        result = persist_run_to_mongo(
            **base_args,
            pipeline_state=pipeline_state,
        )

        assert result is False
        mock_repository.find_one.assert_called_once()

    def test_no_verification_for_running_status(self, mock_repository, base_args):
        """Should not do verification read-back for running status (only completed)."""
        base_args["status"] = "running"
        pipeline_state = {"cv_text": "# My CV content"}

        from runner_service.persistence import persist_run_to_mongo

        result = persist_run_to_mongo(
            **base_args,
            pipeline_state=pipeline_state,
        )

        assert result is True
        # find_one should NOT be called for running status
        mock_repository.find_one.assert_not_called()

    def test_returns_true_when_mongodb_not_configured(self, base_args):
        """Should return True when MongoDB is not configured (dev environment)."""
        with patch.dict("os.environ", {}, clear=True):
            from runner_service.persistence import persist_run_to_mongo

            result = persist_run_to_mongo(
                **base_args,
                pipeline_state={"cv_text": "test"},
            )

            # Returns True since this is expected in dev environments
            assert result is True

    def test_returns_false_on_exception(self, mock_repository, base_args):
        """Should return False when an exception occurs during persistence."""
        mock_repository.update_one.side_effect = Exception("Connection error")

        from runner_service.persistence import persist_run_to_mongo

        result = persist_run_to_mongo(
            **base_args,
            pipeline_state={},
        )

        assert result is False


class TestUpdateJobPipelineFailed:
    """Tests for update_job_pipeline_failed function."""

    @pytest.fixture(autouse=True)
    def reset_repo_singleton(self):
        """Reset repository singleton before each test."""
        reset_repository()
        yield
        reset_repository()

    @pytest.fixture
    def mock_repository(self):
        """Create a mock job repository."""
        mock_repo = MagicMock()
        mock_repo.update_one.return_value = WriteResult(matched_count=1, modified_count=1)

        # Patch at the source module since update_job_pipeline_failed imports inside the function
        with patch("src.common.repositories.get_job_repository", return_value=mock_repo):
            yield mock_repo

    def test_updates_pipeline_failed_status(self, mock_repository):
        """Should update job with pipeline_failed status and error message."""
        from runner_service.persistence import update_job_pipeline_failed

        update_job_pipeline_failed(
            job_id="507f1f77bcf86cd799439011",
            error="Layer 3 failed: API timeout",
        )

        mock_repository.update_one.assert_called_once()
        call_args = mock_repository.update_one.call_args
        update_doc = call_args[0][1]

        assert update_doc["$set"]["pipeline_status"] == "pipeline_failed"
        assert update_doc["$set"]["pipeline_error"] == "Layer 3 failed: API timeout"
        assert "pipeline_failed_at" in update_doc["$set"]

    def test_skips_when_mongodb_uri_not_set(self):
        """Should skip update when MONGODB_URI is not set."""
        with patch.dict("os.environ", {}, clear=True):
            from runner_service.persistence import update_job_pipeline_failed

            # Should not raise (logs debug message)
            update_job_pipeline_failed(
                job_id="507f1f77bcf86cd799439011",
                error="Test error",
            )

    def test_handles_no_match(self, mock_repository):
        """Should log warning when job not found."""
        mock_repository.update_one.return_value = WriteResult(
            matched_count=0, modified_count=0
        )

        from runner_service.persistence import update_job_pipeline_failed

        # Should not raise
        update_job_pipeline_failed(
            job_id="nonexistent",
            error="Test error",
        )
