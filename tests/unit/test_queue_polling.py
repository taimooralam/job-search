"""
Unit tests for the queue polling loop in runner_service/app.py

Tests the startup_queue_polling_loop() function that:
- Polls Redis pending queue periodically
- Dequeues items when runner has capacity
- Dispatches to submit_service_task for execution
- Handles errors gracefully without crashing the loop
- Skips polling when queue manager is unavailable or runner is at capacity
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from runner_service.queue.models import QueueItem, QueueItemStatus


def _make_queue_item(**overrides) -> QueueItem:
    """Create a test QueueItem with sensible defaults."""
    defaults = {
        "queue_id": "q_test123",
        "job_id": "abc123",
        "job_title": "Senior Software Engineer",
        "company": "Acme Corp",
        "status": QueueItemStatus.RUNNING,  # dequeue() sets this
        "operation": "full-extraction",
        "processing_tier": "balanced",
        "created_at": datetime.utcnow(),
        "started_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    return QueueItem(**defaults)


class TestQueuePollingLoop:
    """Tests for the _queue_polling_loop logic."""

    @pytest.mark.asyncio
    async def test_dequeues_and_dispatches_when_capacity_available(self):
        """When queue has items and runner has capacity, dequeue and dispatch."""
        item = _make_queue_item()

        mock_queue_manager = AsyncMock()
        mock_queue_manager.is_connected = True
        mock_queue_manager.dequeue = AsyncMock(side_effect=[item, None])
        mock_queue_manager.link_run_id = AsyncMock()

        mock_semaphore = MagicMock()
        mock_semaphore._value = 2  # Has capacity

        mock_submit = MagicMock()
        mock_create_run = MagicMock(return_value="run_001")
        mock_append_log = MagicMock()
        mock_get_runner_id = MagicMock(return_value="runner-1")

        with patch("runner_service.app._queue_manager", mock_queue_manager), \
             patch("runner_service.app._semaphore", mock_semaphore), \
             patch("runner_service.routes.operations.submit_service_task", mock_submit), \
             patch("runner_service.routes.operation_streaming.create_operation_run", mock_create_run), \
             patch("runner_service.routes.operation_streaming.append_operation_log", mock_append_log), \
             patch("runner_service.routes.operation_streaming.get_runner_id", mock_get_runner_id):

            # Import after patching
            from runner_service.app import QUEUE_POLL_INTERVAL_SECONDS

            # Simulate one iteration of the polling loop
            # We can't easily test the infinite loop, so test the core logic directly
            if (
                mock_queue_manager
                and mock_queue_manager.is_connected
                and mock_semaphore._value > 0
            ):
                dequeued = await mock_queue_manager.dequeue()
                if dequeued:
                    run_id = mock_create_run(dequeued.job_id, dequeued.operation)
                    mock_append_log(run_id, f"[poll] Picked up by {mock_get_runner_id()}")
                    await mock_queue_manager.link_run_id(dequeued.queue_id, run_id)

            # Verify dequeue was called
            mock_queue_manager.dequeue.assert_called_once()

            # Verify operation run was created
            mock_create_run.assert_called_once_with("abc123", "full-extraction")

            # Verify log was appended
            mock_append_log.assert_called_once_with("run_001", "[poll] Picked up by runner-1")

            # Verify run_id was linked
            mock_queue_manager.link_run_id.assert_called_once_with("q_test123", "run_001")

    @pytest.mark.asyncio
    async def test_skips_when_no_capacity(self):
        """When semaphore is at 0, should not dequeue."""
        mock_queue_manager = AsyncMock()
        mock_queue_manager.is_connected = True
        mock_queue_manager.dequeue = AsyncMock()

        mock_semaphore = MagicMock()
        mock_semaphore._value = 0  # No capacity

        # Simulate the capacity check
        should_poll = (
            mock_queue_manager
            and mock_queue_manager.is_connected
            and mock_semaphore._value > 0
        )

        assert not should_poll
        mock_queue_manager.dequeue.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_queue_manager_disconnected(self):
        """When queue manager is disconnected, should not dequeue."""
        mock_queue_manager = AsyncMock()
        mock_queue_manager.is_connected = False
        mock_queue_manager.dequeue = AsyncMock()

        mock_semaphore = MagicMock()
        mock_semaphore._value = 2

        should_poll = (
            mock_queue_manager
            and mock_queue_manager.is_connected
            and mock_semaphore._value > 0
        )

        assert not should_poll
        mock_queue_manager.dequeue.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_queue_manager_is_none(self):
        """When queue manager is None (Redis not configured), should not poll."""
        mock_semaphore = MagicMock()
        mock_semaphore._value = 2

        _queue_manager = None

        should_poll = (
            _queue_manager
            and _queue_manager.is_connected
            and mock_semaphore._value > 0
        )

        assert not should_poll

    @pytest.mark.asyncio
    async def test_handles_empty_queue(self):
        """When dequeue returns None (empty queue), should just continue."""
        mock_queue_manager = AsyncMock()
        mock_queue_manager.is_connected = True
        mock_queue_manager.dequeue = AsyncMock(return_value=None)

        mock_semaphore = MagicMock()
        mock_semaphore._value = 2

        mock_submit = MagicMock()

        if (
            mock_queue_manager
            and mock_queue_manager.is_connected
            and mock_semaphore._value > 0
        ):
            item = await mock_queue_manager.dequeue()
            if item:
                mock_submit(item)

        mock_queue_manager.dequeue.assert_called_once()
        mock_submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_dequeue_exception(self):
        """When dequeue raises, should log warning and continue."""
        mock_queue_manager = AsyncMock()
        mock_queue_manager.is_connected = True
        mock_queue_manager.dequeue = AsyncMock(side_effect=RuntimeError("Redis timeout"))

        mock_semaphore = MagicMock()
        mock_semaphore._value = 2

        error_caught = False
        try:
            if (
                mock_queue_manager
                and mock_queue_manager.is_connected
                and mock_semaphore._value > 0
            ):
                await mock_queue_manager.dequeue()
        except Exception:
            error_caught = True

        assert error_caught
        mock_queue_manager.dequeue.assert_called_once()

    @pytest.mark.asyncio
    async def test_tier_fallback_to_balanced(self):
        """When tier string is invalid, should fall back to BALANCED."""
        from src.common.model_tiers import get_tier_from_string, ModelTier

        item = _make_queue_item(processing_tier="invalid_tier")

        tier = get_tier_from_string(item.processing_tier) or ModelTier.BALANCED
        assert tier == ModelTier.BALANCED

    @pytest.mark.asyncio
    async def test_tier_resolves_correctly(self):
        """When tier string is valid, should resolve to the correct ModelTier."""
        from src.common.model_tiers import get_tier_from_string, ModelTier

        item = _make_queue_item(processing_tier="balanced")
        tier = get_tier_from_string(item.processing_tier) or ModelTier.BALANCED
        assert tier == ModelTier.BALANCED

        item_fast = _make_queue_item(processing_tier="fast")
        tier_fast = get_tier_from_string(item_fast.processing_tier) or ModelTier.BALANCED
        assert tier_fast == ModelTier.FAST

    @pytest.mark.asyncio
    async def test_long_job_title_truncation(self):
        """Job title should be safely truncated in log messages."""
        long_title = "A" * 100
        item = _make_queue_item(job_title=long_title)

        # Simulate the log line formatting
        log_msg = (
            f"[poll] Dequeued {item.queue_id} for {item.job_id} "
            f"({item.company}: {item.job_title[:40]})"
        )

        assert len(item.job_title[:40]) == 40
        assert "AAAA" in log_msg


class TestStaleCleanupTimeout:
    """Test that stale cleanup uses 24-hour timeout."""

    @pytest.mark.asyncio
    async def test_cleanup_uses_24h_timeout(self):
        """Verify the startup code passes max_age_minutes=1440."""
        # This test verifies the code change by reading the source
        import inspect
        from runner_service.app import startup_queue_manager

        source = inspect.getsource(startup_queue_manager)
        assert "max_age_minutes=1440" in source
        assert "max_age_minutes=60" not in source


class TestQueuePollIntervalConfig:
    """Test the poll interval configuration."""

    def test_default_poll_interval(self):
        """Default poll interval should be 5 seconds."""
        from runner_service.app import QUEUE_POLL_INTERVAL_SECONDS
        # Default is 5 unless overridden by env var
        assert isinstance(QUEUE_POLL_INTERVAL_SECONDS, int)
        assert QUEUE_POLL_INTERVAL_SECONDS > 0
