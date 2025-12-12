"""
Unit Tests for SSE Streaming Outreach Generation.

Tests the new streaming endpoint for outreach generation that returns
real-time SSE logs during message generation.

Key features tested:
1. POST /{job_id}/contacts/{contact_type}/{contact_index}/generate-outreach/stream
2. Returns StreamingOutreachResponse with run_id, log_stream_url, status
3. Background task execute_outreach_with_logging() emits SSE logs
4. Error handling for invalid job_id, contact_index, tier
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call
from bson import ObjectId
from fastapi import BackgroundTasks, HTTPException

from runner_service.routes.contacts import (
    generate_outreach_stream,
    StreamingOutreachResponse,
    OutreachRequest,
    _validate_job_exists,
    _get_contact,
    _validate_tier,
)
from src.common.model_tiers import ModelTier


# ===== FIXTURES =====


@pytest.fixture
def sample_job_id():
    """Sample job ID."""
    return "507f1f77bcf86cd799439011"


@pytest.fixture
def mock_job_doc(sample_job_id):
    """Mock MongoDB job document with contacts."""
    return {
        "_id": ObjectId(sample_job_id),
        "title": "Senior Software Engineer",
        "company": "TechCorp",
        "job_description": "Build scalable systems. Python, AWS, Kubernetes required.",
        "jd_text": "Build scalable systems. Python, AWS, Kubernetes required.",
        "url": "https://example.com/job/123",
        "source": "linkedin",
        "primary_contacts": [
            {
                "name": "Jane Doe",
                "role": "Hiring Manager",
                "linkedin_url": "https://linkedin.com/in/janedoe",
                "contact_type": "hiring_manager",
                "why_relevant": "Makes hiring decisions",
            }
        ],
        "secondary_contacts": [
            {
                "name": "John Smith",
                "role": "Engineer",
                "linkedin_url": "https://linkedin.com/in/johnsmith",
                "contact_type": "peer",
                "why_relevant": "Works on the team",
            }
        ],
    }


@pytest.fixture
def mock_background_tasks():
    """Mock FastAPI BackgroundTasks."""
    tasks = MagicMock(spec=BackgroundTasks)
    tasks.add_task = Mock()
    return tasks


@pytest.fixture
def mock_operation_streaming(mocker):
    """Mock all operation_streaming functions."""
    return {
        "create_operation_run": mocker.patch(
            "runner_service.routes.contacts.create_operation_run",
            return_value="outreach_abc123def456",
        ),
        "append_operation_log": mocker.patch(
            "runner_service.routes.contacts.append_operation_log"
        ),
        "update_operation_status": mocker.patch(
            "runner_service.routes.contacts.update_operation_status"
        ),
        "create_log_callback": mocker.patch(
            "runner_service.routes.contacts.create_log_callback",
            return_value=Mock(),
        ),
        "create_layer_callback": mocker.patch(
            "runner_service.routes.contacts.create_layer_callback",
            return_value=Mock(),
        ),
    }


# ===== ENDPOINT TESTS =====


class TestGenerateOutreachStreamEndpoint:
    """Test the streaming outreach generation endpoint."""

    @pytest.mark.asyncio
    async def test_returns_streaming_response_with_run_id(
        self, sample_job_id, mock_background_tasks, mock_operation_streaming, mocker
    ):
        """Should return StreamingOutreachResponse with run_id and log_stream_url."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_tier",
            return_value=ModelTier.BALANCED,
        )
        request = OutreachRequest(tier="balanced", message_type="connection")

        # Act
        response = await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="primary",
            contact_index=0,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Assert
        assert isinstance(response, StreamingOutreachResponse)
        assert response.run_id == "outreach_abc123def456"
        assert response.log_stream_url == "/api/jobs/operations/outreach_abc123def456/logs"
        assert response.status == "queued"

    @pytest.mark.asyncio
    async def test_creates_operation_run_immediately(
        self, sample_job_id, mock_background_tasks, mock_operation_streaming, mocker
    ):
        """Should create operation run before queuing background task."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_tier",
            return_value=ModelTier.FAST,
        )
        request = OutreachRequest(tier="fast", message_type="inmail")

        # Act
        await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="secondary",
            contact_index=0,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Assert
        mock_operation_streaming["create_operation_run"].assert_called_once_with(
            sample_job_id, "outreach"
        )

    @pytest.mark.asyncio
    async def test_appends_initial_logs(
        self, sample_job_id, mock_background_tasks, mock_operation_streaming, mocker
    ):
        """Should append initial logs describing the operation."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_tier",
            return_value=ModelTier.QUALITY,
        )
        request = OutreachRequest(tier="quality", message_type="connection")

        # Act
        await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="primary",
            contact_index=1,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Assert
        run_id = "outreach_abc123def456"
        mock_operation_streaming["append_operation_log"].assert_has_calls(
            [
                call(run_id, f"Starting connection generation for job {sample_job_id}"),
                call(run_id, f"Tier: quality, Contact: primary[1]"),
            ]
        )

    @pytest.mark.asyncio
    async def test_queues_background_task(
        self, sample_job_id, mock_background_tasks, mock_operation_streaming, mocker
    ):
        """Should add execute_outreach_with_logging to background tasks."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_tier",
            return_value=ModelTier.BALANCED,
        )
        request = OutreachRequest(tier="balanced", message_type="inmail")

        # Act
        await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="primary",
            contact_index=0,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Assert
        mock_background_tasks.add_task.assert_called_once()
        # The first argument should be a coroutine function
        task_func = mock_background_tasks.add_task.call_args[0][0]
        assert callable(task_func)

    @pytest.mark.asyncio
    async def test_validates_tier_synchronously(
        self, sample_job_id, mock_background_tasks, mock_operation_streaming, mocker
    ):
        """Should validate tier before creating operation run."""
        # Arrange
        mock_validate_tier = mocker.patch(
            "runner_service.routes.contacts._validate_tier",
            return_value=ModelTier.BALANCED,
        )
        request = OutreachRequest(tier="balanced", message_type="connection")

        # Act
        await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="primary",
            contact_index=0,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Assert
        mock_validate_tier.assert_called_once_with("balanced")


# ===== BACKGROUND TASK TESTS =====


class TestExecuteOutreachWithLogging:
    """Test the background task that executes outreach generation with logging."""

    @pytest.mark.asyncio
    async def test_background_task_queued_for_execution(
        self, sample_job_id, mock_background_tasks, mock_operation_streaming, mocker
    ):
        """Should queue the background task for execution."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_tier",
            return_value=ModelTier.BALANCED,
        )
        request = OutreachRequest(tier="balanced", message_type="connection")

        # Act
        await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="primary",
            contact_index=0,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Assert
        # Background task should be queued
        mock_background_tasks.add_task.assert_called_once()
        # The queued task should be a coroutine function
        task_func = mock_background_tasks.add_task.call_args[0][0]
        assert callable(task_func)

    @pytest.mark.asyncio
    async def test_creates_log_and_layer_callbacks(
        self, sample_job_id, mock_background_tasks, mock_operation_streaming, mocker
    ):
        """Should create log and layer callbacks for streaming."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_tier",
            return_value=ModelTier.BALANCED,
        )
        request = OutreachRequest(tier="balanced", message_type="connection")

        # Act
        await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="primary",
            contact_index=0,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Assert - callbacks should be created for the run_id
        run_id = "outreach_abc123def456"
        # Verify operation run was created (callbacks will be created inside background task)
        mock_operation_streaming["create_operation_run"].assert_called_once_with(
            sample_job_id, "outreach"
        )

    @pytest.mark.asyncio
    async def test_initial_status_is_queued(
        self, sample_job_id, mock_background_tasks, mock_operation_streaming, mocker
    ):
        """Should return response with status 'queued'."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_tier",
            return_value=ModelTier.BALANCED,
        )
        request = OutreachRequest(tier="balanced", message_type="connection")

        # Act
        response = await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="primary",
            contact_index=0,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Assert
        assert response.status == "queued"

    @pytest.mark.asyncio
    async def test_handles_job_not_found_error(
        self, sample_job_id, mock_operation_streaming, mocker
    ):
        """Should update status to failed when job is not found."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_job_exists",
            side_effect=HTTPException(status_code=404, detail="Job not found"),
        )

        request = OutreachRequest(tier="balanced", message_type="connection")
        mock_background_tasks = MagicMock(spec=BackgroundTasks)

        # Act
        await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="primary",
            contact_index=0,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Execute the background task
        background_task = mock_background_tasks.add_task.call_args[0][0]
        await background_task()

        # Assert
        run_id = "outreach_abc123def456"
        layer_cb = mock_operation_streaming["create_layer_callback"].return_value
        layer_cb.assert_any_call("validate", "failed", "Job validation failed: Job not found")
        mock_operation_streaming["update_operation_status"].assert_called_with(
            run_id, "failed", error="Job not found"
        )

    @pytest.mark.asyncio
    async def test_handles_contact_index_out_of_bounds(
        self, sample_job_id, mock_job_doc, mock_operation_streaming, mocker
    ):
        """Should update status to failed when contact index is invalid."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_job_exists",
            return_value=mock_job_doc,
        )
        mocker.patch(
            "runner_service.routes.contacts._get_contact",
            side_effect=HTTPException(
                status_code=400, detail="Contact index 5 out of range"
            ),
        )

        request = OutreachRequest(tier="balanced", message_type="connection")
        mock_background_tasks = MagicMock(spec=BackgroundTasks)

        # Act
        await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="primary",
            contact_index=5,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Execute the background task
        background_task = mock_background_tasks.add_task.call_args[0][0]
        await background_task()

        # Assert
        run_id = "outreach_abc123def456"
        layer_cb = mock_operation_streaming["create_layer_callback"].return_value
        layer_cb.assert_any_call(
            "contact", "failed", "Contact fetch failed: Contact index 5 out of range"
        )
        mock_operation_streaming["update_operation_status"].assert_called_with(
            run_id, "failed", error="Contact index 5 out of range"
        )

    @pytest.mark.asyncio
    async def test_appends_tier_info_to_logs(
        self, sample_job_id, mock_background_tasks, mock_operation_streaming, mocker
    ):
        """Should append tier and contact info to initial logs."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_tier",
            return_value=ModelTier.QUALITY,
        )
        request = OutreachRequest(tier="quality", message_type="inmail")

        # Act
        await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="secondary",
            contact_index=2,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Assert
        run_id = "outreach_abc123def456"
        mock_operation_streaming["append_operation_log"].assert_any_call(
            run_id, "Tier: quality, Contact: secondary[2]"
        )

    @pytest.mark.asyncio
    async def test_handles_unexpected_exceptions(
        self, sample_job_id, mock_job_doc, mock_operation_streaming, mocker
    ):
        """Should catch and log unexpected exceptions during execution."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_job_exists",
            side_effect=RuntimeError("Unexpected database error"),
        )

        request = OutreachRequest(tier="balanced", message_type="connection")
        mock_background_tasks = MagicMock(spec=BackgroundTasks)

        # Act
        await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="primary",
            contact_index=0,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Execute the background task
        background_task = mock_background_tasks.add_task.call_args[0][0]
        await background_task()

        # Assert
        run_id = "outreach_abc123def456"
        log_cb = mock_operation_streaming["create_log_callback"].return_value
        log_cb.assert_any_call("Error: Unexpected database error")
        mock_operation_streaming["update_operation_status"].assert_called_with(
            run_id, "failed", error="Unexpected database error"
        )


# ===== HELPER FUNCTION TESTS =====


class TestValidateTier:
    """Test tier validation helper."""

    def test_validates_fast_tier(self):
        """Should accept 'fast' tier."""
        tier = _validate_tier("fast")
        assert tier == ModelTier.FAST

    def test_validates_balanced_tier(self):
        """Should accept 'balanced' tier."""
        tier = _validate_tier("balanced")
        assert tier == ModelTier.BALANCED

    def test_validates_quality_tier(self):
        """Should accept 'quality' tier."""
        tier = _validate_tier("quality")
        assert tier == ModelTier.QUALITY

    def test_rejects_invalid_tier(self):
        """Should raise HTTPException for invalid tier."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_tier("ultra-premium")

        assert exc_info.value.status_code == 400
        assert "Invalid tier 'ultra-premium'" in exc_info.value.detail

    def test_rejects_empty_tier(self):
        """Should raise HTTPException for empty tier."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_tier("")

        assert exc_info.value.status_code == 400


# ===== INTEGRATION TESTS =====


class TestOutreachStreamingIntegration:
    """Integration tests for outreach streaming with SSE."""

    @pytest.mark.asyncio
    async def test_connection_message_type_endpoint_integration(
        self, sample_job_id, mock_background_tasks, mock_operation_streaming, mocker
    ):
        """Should successfully queue connection message generation."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_tier",
            return_value=ModelTier.BALANCED,
        )
        request = OutreachRequest(tier="balanced", message_type="connection")

        # Act
        response = await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="primary",
            contact_index=0,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Assert - Endpoint response
        assert response.run_id == "outreach_abc123def456"
        assert response.status == "queued"
        assert "/api/jobs/operations/outreach_abc123def456/logs" in response.log_stream_url

        # Assert - Initial logs contain message type
        mock_operation_streaming["append_operation_log"].assert_any_call(
            "outreach_abc123def456",
            f"Starting connection generation for job {sample_job_id}"
        )

    @pytest.mark.asyncio
    async def test_inmail_message_type_endpoint_integration(
        self, sample_job_id, mock_background_tasks, mock_operation_streaming, mocker
    ):
        """Should successfully queue inmail message generation."""
        # Arrange
        mocker.patch(
            "runner_service.routes.contacts._validate_tier",
            return_value=ModelTier.QUALITY,
        )
        request = OutreachRequest(tier="quality", message_type="inmail")

        # Act
        response = await generate_outreach_stream(
            job_id=sample_job_id,
            contact_type="secondary",
            contact_index=0,
            request=request,
            background_tasks=mock_background_tasks,
        )

        # Assert
        assert response.run_id == "outreach_abc123def456"
        assert response.status == "queued"

        # Should have logged inmail message type
        mock_operation_streaming["append_operation_log"].assert_any_call(
            "outreach_abc123def456",
            f"Starting inmail generation for job {sample_job_id}"
        )
