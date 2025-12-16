"""
Unit tests for cross-runner WebSocket event propagation.

Tests cover:
1. Event listener receives events from other runner instances
2. Event listener ignores events from same instance (no double-delivery)
3. Listener cleanup on disconnect
4. Instance ID uniqueness across QueueManager instances

These tests ensure that when scaling to multiple runner instances,
WebSocket clients connected to any runner receive real-time updates
for jobs running on any other runner instance.
"""

import asyncio
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from runner_service.queue.manager import QueueManager
from runner_service.queue.models import QueueItem, QueueItemStatus


class TestCrossRunnerEventListener:
    """Tests for the Redis Pub/Sub event listener."""

    @pytest.fixture
    def redis_url(self):
        """Redis URL for testing."""
        return "redis://localhost:6379/0"

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.ping = AsyncMock(return_value=True)
        mock.pubsub = MagicMock(return_value=AsyncMock())
        mock.close = AsyncMock()
        return mock

    @pytest.fixture
    def queue_manager(self, redis_url):
        """Create a QueueManager instance."""
        return QueueManager(redis_url)

    def test_instance_id_is_unique(self, redis_url):
        """Each QueueManager should have a unique instance ID."""
        manager1 = QueueManager(redis_url)
        manager2 = QueueManager(redis_url)

        assert manager1._instance_id != manager2._instance_id
        assert len(manager1._instance_id) == 8  # uuid hex[:8]
        assert len(manager2._instance_id) == 8

    def test_instance_id_is_8_char_hex(self, queue_manager):
        """Instance ID should be 8-character hex string."""
        instance_id = queue_manager._instance_id
        assert len(instance_id) == 8
        # Should be valid hex
        int(instance_id, 16)

    @pytest.mark.asyncio
    async def test_start_event_listener_requires_redis_connection(self, queue_manager):
        """start_event_listener should do nothing if not connected."""
        # Not connected - _redis is None
        await queue_manager.start_event_listener()

        assert queue_manager._listener_task is None
        assert queue_manager._pubsub is None

    @pytest.mark.asyncio
    async def test_start_event_listener_creates_pubsub_and_task(self, queue_manager, mock_redis):
        """start_event_listener should create pubsub subscription and listener task."""
        queue_manager._redis = mock_redis
        queue_manager._connected = True

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = AsyncMock(return_value=iter([]))
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        await queue_manager.start_event_listener()

        # Should have created pubsub and subscribed
        assert queue_manager._pubsub == mock_pubsub
        mock_pubsub.subscribe.assert_called_once_with(QueueManager.EVENTS_CHANNEL)

        # Should have created listener task
        assert queue_manager._listener_task is not None

        # Cleanup
        queue_manager._listener_task.cancel()
        try:
            await queue_manager._listener_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_event_listener_ignores_own_events(self, queue_manager, mock_redis):
        """Event listener should ignore events from this instance."""
        queue_manager._redis = mock_redis
        queue_manager._connected = True

        # Track callback invocations
        callback_events = []

        async def callback(event):
            callback_events.append(event)

        await queue_manager.subscribe(callback)

        # Create mock pubsub that yields one event from THIS instance
        own_event = {
            "action": "completed",
            "item": {"queue_id": "test_123"},
            "timestamp": datetime.utcnow().isoformat(),
            "source_instance": queue_manager._instance_id,  # Same instance!
        }

        async def mock_listen():
            yield {"type": "message", "data": json.dumps(own_event)}

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = mock_listen
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        await queue_manager.start_event_listener()

        # Give the listener loop time to process
        await asyncio.sleep(0.1)

        # Callback should NOT have been called (event was from self)
        assert len(callback_events) == 0

        # Cleanup
        queue_manager._listener_task.cancel()
        try:
            await queue_manager._listener_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_event_listener_forwards_external_events(self, queue_manager, mock_redis):
        """Event listener should forward events from other instances."""
        queue_manager._redis = mock_redis
        queue_manager._connected = True

        # Track callback invocations
        callback_events = []

        async def callback(event):
            callback_events.append(event)

        await queue_manager.subscribe(callback)

        # Create mock pubsub that yields one event from ANOTHER instance
        external_event = {
            "action": "completed",
            "item": {"queue_id": "test_456"},
            "timestamp": datetime.utcnow().isoformat(),
            "source_instance": "other123",  # Different instance!
        }

        async def mock_listen():
            yield {"type": "message", "data": json.dumps(external_event)}

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = mock_listen
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        await queue_manager.start_event_listener()

        # Give the listener loop time to process
        await asyncio.sleep(0.1)

        # Callback SHOULD have been called
        assert len(callback_events) == 1
        assert callback_events[0]["action"] == "completed"
        assert callback_events[0]["source_instance"] == "other123"

        # Cleanup
        queue_manager._listener_task.cancel()
        try:
            await queue_manager._listener_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_event_listener_handles_invalid_json(self, queue_manager, mock_redis):
        """Event listener should handle invalid JSON gracefully."""
        queue_manager._redis = mock_redis
        queue_manager._connected = True

        callback_events = []

        async def callback(event):
            callback_events.append(event)

        await queue_manager.subscribe(callback)

        # Create mock pubsub that yields invalid JSON
        async def mock_listen():
            yield {"type": "message", "data": "not valid json {{{"}

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = mock_listen
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        # Should not raise exception
        await queue_manager.start_event_listener()
        await asyncio.sleep(0.1)

        # No events should have been forwarded
        assert len(callback_events) == 0

        # Cleanup
        queue_manager._listener_task.cancel()
        try:
            await queue_manager._listener_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_disconnect_cancels_listener_task(self, queue_manager, mock_redis):
        """disconnect() should cancel the listener task."""
        queue_manager._redis = mock_redis
        queue_manager._connected = True

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()

        async def mock_listen():
            while True:
                await asyncio.sleep(0.1)
                yield {"type": "ping", "data": None}

        mock_pubsub.listen = mock_listen
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        await queue_manager.start_event_listener()

        assert queue_manager._listener_task is not None
        assert not queue_manager._listener_task.done()

        # Disconnect should cleanup
        await queue_manager.disconnect()

        assert queue_manager._listener_task is None
        assert queue_manager._pubsub is None
        assert queue_manager._redis is None


class TestPublishEventWithSourceInstance:
    """Tests for _publish_event including source_instance."""

    @pytest.fixture
    def redis_url(self):
        return "redis://localhost:6379/0"

    @pytest.fixture
    def queue_manager(self, redis_url):
        return QueueManager(redis_url)

    @pytest.fixture
    def mock_queue_item(self):
        """Create a mock QueueItem."""
        return QueueItem(
            queue_id="q_test123",
            job_id="job_abc",
            job_title="Test Job",
            company="Test Company",
            status=QueueItemStatus.COMPLETED,
            operation="full_pipeline",
            processing_tier="auto",
            created_at=datetime.utcnow(),
        )

    @pytest.mark.asyncio
    async def test_publish_event_includes_source_instance(self, queue_manager, mock_queue_item):
        """Published events should include source_instance field."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        queue_manager._redis = mock_redis

        # Track local subscriber calls
        received_events = []

        async def subscriber(event):
            received_events.append(event)

        await queue_manager.subscribe(subscriber)

        # Publish an event
        await queue_manager._publish_event("completed", mock_queue_item)

        # Check Redis publish was called with source_instance
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        channel = call_args[0][0]
        data = json.loads(call_args[0][1])

        assert channel == QueueManager.EVENTS_CHANNEL
        assert data["action"] == "completed"
        assert data["source_instance"] == queue_manager._instance_id
        assert "timestamp" in data

        # Local subscriber should also receive it
        assert len(received_events) == 1
        assert received_events[0]["source_instance"] == queue_manager._instance_id
