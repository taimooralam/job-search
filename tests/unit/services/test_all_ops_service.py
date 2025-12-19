"""
Unit tests for AllOpsService.

Tests the composite service that runs JD extraction and company research in parallel.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.common.model_tiers import ModelTier
from src.services.all_ops_service import AllOpsService
from src.services.operation_base import OperationResult


class TestAllOpsServiceInit:
    """Tests for AllOpsService initialization."""

    def test_operation_name_is_set(self):
        """Operation name should be 'all-ops'."""
        service = AllOpsService()
        assert service.operation_name == "all-ops"

    def test_max_retries_is_one(self):
        """Max retries should be 1."""
        assert AllOpsService.MAX_RETRIES == 1

    def test_services_not_initialized_on_init(self):
        """Sub-services should be lazily initialized."""
        service = AllOpsService()
        assert service._extraction_service is None
        assert service._research_service is None


class TestAllOpsServiceSubServices:
    """Tests for lazy-loading of sub-services."""

    def test_extraction_service_lazy_init(self):
        """Extraction service should be initialized on first access."""
        service = AllOpsService()
        assert service._extraction_service is None
        _ = service.extraction_service
        assert service._extraction_service is not None

    def test_research_service_lazy_init(self):
        """Research service should be initialized on first access."""
        service = AllOpsService()
        assert service._research_service is None
        _ = service.research_service
        assert service._research_service is not None


class TestAllOpsServiceRunWithRetry:
    """Tests for the retry logic."""

    @pytest.mark.asyncio
    async def test_run_with_retry_success_first_attempt(self):
        """Successful operation on first attempt returns result."""
        service = AllOpsService()

        mock_result = OperationResult(
            success=True,
            run_id="test_run",
            operation="extraction",
            data={"key": "value"},
            cost_usd=0.01,
            duration_ms=100,
        )

        async def mock_operation():
            return mock_result

        result, error = await service._run_with_retry(
            "extraction", mock_operation, None, 1
        )

        assert result == mock_result
        assert error is None

    @pytest.mark.asyncio
    async def test_run_with_retry_failure_then_success(self):
        """Retry should succeed after initial failure."""
        service = AllOpsService()

        call_count = 0

        async def mock_operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return OperationResult(
                    success=False,
                    run_id="test_run",
                    operation="extraction",
                    data={},
                    cost_usd=0.0,
                    duration_ms=50,
                    error="First attempt failed",
                )
            return OperationResult(
                success=True,
                run_id="test_run",
                operation="extraction",
                data={"key": "value"},
                cost_usd=0.01,
                duration_ms=100,
            )

        result, error = await service._run_with_retry(
            "extraction", mock_operation, None, 1
        )

        assert result is not None
        assert result.success
        assert error is None
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_run_with_retry_all_attempts_fail(self):
        """All retries exhausted should return error."""
        service = AllOpsService()

        async def mock_operation():
            return OperationResult(
                success=False,
                run_id="test_run",
                operation="extraction",
                data={},
                cost_usd=0.0,
                duration_ms=50,
                error="Always fails",
            )

        result, error = await service._run_with_retry(
            "extraction", mock_operation, None, 1
        )

        assert result is None
        assert error == "Always fails"

    @pytest.mark.asyncio
    async def test_run_with_retry_exception_handling(self):
        """Exceptions should be caught and retried."""
        service = AllOpsService()

        call_count = 0

        async def mock_operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Test exception")
            return OperationResult(
                success=True,
                run_id="test_run",
                operation="extraction",
                data={},
                cost_usd=0.01,
                duration_ms=100,
            )

        result, error = await service._run_with_retry(
            "extraction", mock_operation, None, 1
        )

        assert result is not None
        assert result.success
        assert call_count == 2


class TestAllOpsServiceExecute:
    """Tests for the main execute method."""

    @pytest.mark.asyncio
    async def test_execute_both_success(self):
        """Both operations succeeding should return phase1_complete=True."""
        service = AllOpsService()

        extraction_result = OperationResult(
            success=True,
            run_id="extract_run",
            operation="full-extraction",
            data={
                "fit_score": 85,
                "fit_category": "strong",
                "pain_points_count": 3,
                "section_count": 5,
                "layer_status": {"jd_processor": {"status": "success"}},
            },
            cost_usd=0.02,
            duration_ms=2000,
            input_tokens=1000,
            output_tokens=500,
        )

        research_result = OperationResult(
            success=True,
            run_id="research_run",
            operation="research-company",
            data={
                "company_type": "startup",
                "signals_count": 5,
                "primary_contacts_count": 2,
                "secondary_contacts_count": 3,
                "layer_status": {"company_research": {"status": "success"}},
            },
            cost_usd=0.03,
            duration_ms=3000,
            input_tokens=1500,
            output_tokens=800,
        )

        # Create mock services
        mock_extraction = MagicMock()
        mock_extraction.execute = AsyncMock(return_value=extraction_result)
        mock_research = MagicMock()
        mock_research.execute = AsyncMock(return_value=research_result)

        # Patch the private attributes directly
        service._extraction_service = mock_extraction
        service._research_service = mock_research

        result = await service.execute(
            job_id="test_job_id",
            tier=ModelTier.BALANCED,
        )

        assert result.success
        assert result.data["phase1_complete"]
        assert result.data["extraction_completed"]
        assert result.data["research_completed"]
        assert result.data["fit_score"] == 85
        assert result.data["signals_count"] == 5
        assert result.cost_usd == 0.05  # 0.02 + 0.03
        assert result.input_tokens == 2500  # 1000 + 1500
        assert result.output_tokens == 1300  # 500 + 800

    @pytest.mark.asyncio
    async def test_execute_extraction_fails_research_succeeds(self):
        """Partial success when extraction fails but research succeeds."""
        service = AllOpsService()

        extraction_result = OperationResult(
            success=False,
            run_id="extract_run",
            operation="full-extraction",
            data={},
            cost_usd=0.01,
            duration_ms=1000,
            error="Extraction failed",
        )

        research_result = OperationResult(
            success=True,
            run_id="research_run",
            operation="research-company",
            data={
                "company_type": "enterprise",
                "signals_count": 3,
                "layer_status": {},
            },
            cost_usd=0.02,
            duration_ms=2000,
        )

        # Create mock services
        mock_extraction = MagicMock()
        mock_extraction.execute = AsyncMock(return_value=extraction_result)
        mock_research = MagicMock()
        mock_research.execute = AsyncMock(return_value=research_result)

        service._extraction_service = mock_extraction
        service._research_service = mock_research

        result = await service.execute(
            job_id="test_job_id",
            tier=ModelTier.BALANCED,
        )

        # Partial success - one operation succeeded
        assert result.success
        assert not result.data["phase1_complete"]
        assert not result.data["extraction_completed"]
        assert result.data["research_completed"]
        assert "extraction_error" in result.data
        assert result.error is not None  # Partial error included

    @pytest.mark.asyncio
    async def test_execute_both_fail(self):
        """Both operations failing should return success=False."""
        service = AllOpsService()

        extraction_result = OperationResult(
            success=False,
            run_id="extract_run",
            operation="full-extraction",
            data={},
            cost_usd=0.0,
            duration_ms=500,
            error="Extraction failed",
        )

        research_result = OperationResult(
            success=False,
            run_id="research_run",
            operation="research-company",
            data={},
            cost_usd=0.0,
            duration_ms=500,
            error="Research failed",
        )

        # Create mock services
        mock_extraction = MagicMock()
        mock_extraction.execute = AsyncMock(return_value=extraction_result)
        mock_research = MagicMock()
        mock_research.execute = AsyncMock(return_value=research_result)

        service._extraction_service = mock_extraction
        service._research_service = mock_research

        result = await service.execute(
            job_id="test_job_id",
            tier=ModelTier.BALANCED,
        )

        assert not result.success
        assert not result.data.get("phase1_complete", False)
        assert "Extraction" in result.error
        assert "Research" in result.error

    @pytest.mark.asyncio
    async def test_execute_passes_progress_callback(self):
        """Progress callback should be passed to sub-services."""
        service = AllOpsService()

        extraction_result = OperationResult(
            success=True,
            run_id="extract_run",
            operation="full-extraction",
            data={"layer_status": {}},
            cost_usd=0.01,
            duration_ms=1000,
        )

        research_result = OperationResult(
            success=True,
            run_id="research_run",
            operation="research-company",
            data={"layer_status": {}},
            cost_usd=0.01,
            duration_ms=1000,
        )

        progress_calls = []

        def mock_progress(layer_key, status, message):
            progress_calls.append((layer_key, status, message))

        # Create mock services
        mock_extraction = MagicMock()
        mock_extraction.execute = AsyncMock(return_value=extraction_result)
        mock_research = MagicMock()
        mock_research.execute = AsyncMock(return_value=research_result)

        service._extraction_service = mock_extraction
        service._research_service = mock_research

        result = await service.execute(
            job_id="test_job_id",
            tier=ModelTier.BALANCED,
            progress_callback=mock_progress,
        )

        # Should have progress calls for the all-ops operation
        assert any("all_ops" in call[0] or "parallel" in call[0] for call in progress_calls)


class TestAllOpsServiceClose:
    """Tests for resource cleanup."""

    def test_close_cleans_up_research_service(self):
        """Close should cleanup research service."""
        service = AllOpsService()

        # Initialize research service
        mock_research = MagicMock()
        service._research_service = mock_research

        service.close()

        mock_research.close.assert_called_once()
        assert service._research_service is None

    def test_close_handles_no_services(self):
        """Close should handle case when services not initialized."""
        service = AllOpsService()

        # Should not raise
        service.close()

        assert service._research_service is None
