"""
Unit tests for runner_service/queue/manager.py

Tests the Redis-backed queue manager including:
- Connection management (connect, disconnect)
- Queue operations (enqueue, dequeue, FIFO ordering)
- Item lifecycle (complete, fail, retry, cancel)
- State retrieval (get_item, get_item_by_job_id, get_state)
- Failed item management (dismiss_failed)
- Event publishing for WebSocket
- History trimming
- Edge cases (empty queue, item not found, invalid transitions)
- Interrupted run restoration
"""

import asyncio
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, call
from typing import Dict, Any, List

from runner_service.queue.manager import QueueManager
from runner_service.queue.models import QueueItem, QueueItemStatus, QueueState


class FakeRedis:
    """Fake Redis implementation for testing."""

    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.lists: Dict[str, List[str]] = {}
        self.sets: Dict[str, set] = {}
        self.sorted_sets: Dict[str, List[tuple]] = {}
        self.ttls: Dict[str, int] = {}

    async def ping(self):
        """Ping the fake Redis."""
        return True

    async def close(self):
        """Close the connection."""
        pass

    async def hset(self, key: str, mapping: dict):
        """Set hash values."""
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)

    async def hgetall(self, key: str):
        """Get all hash values."""
        return self.data.get(key, {})

    async def expire(self, key: str, seconds: int):
        """Set expiry on key."""
        self.ttls[key] = seconds

    async def ttl(self, key: str):
        """Get TTL of key."""
        return self.ttls.get(key, -1)

    async def lpush(self, key: str, *values):
        """Push values to left of list."""
        if key not in self.lists:
            self.lists[key] = []
        for value in reversed(values):
            self.lists[key].insert(0, value)

    async def rpush(self, key: str, *values):
        """Push values to right of list."""
        if key not in self.lists:
            self.lists[key] = []
        self.lists[key].extend(values)

    async def rpop(self, key: str):
        """Pop value from right of list."""
        if key not in self.lists or not self.lists[key]:
            return None
        return self.lists[key].pop()

    async def lrange(self, key: str, start: int, end: int):
        """Get range from list."""
        if key not in self.lists:
            return []
        lst = self.lists[key]
        if end == -1:
            return lst[start:]
        return lst[start:end + 1]

    async def llen(self, key: str):
        """Get length of list."""
        return len(self.lists.get(key, []))

    async def lrem(self, key: str, count: int, value: str):
        """Remove value from list."""
        if key not in self.lists:
            return 0
        try:
            self.lists[key].remove(value)
            return 1
        except ValueError:
            return 0

    async def ltrim(self, key: str, start: int, end: int):
        """Trim list to range."""
        if key in self.lists:
            self.lists[key] = self.lists[key][start:end + 1]

    async def sadd(self, key: str, *values):
        """Add values to set."""
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].update(values)

    async def srem(self, key: str, *values):
        """Remove values from set."""
        if key not in self.sets:
            return 0
        count = 0
        for value in values:
            if value in self.sets[key]:
                self.sets[key].remove(value)
                count += 1
        return count

    async def smembers(self, key: str):
        """Get all set members."""
        # Return as list to avoid "Set changed size during iteration" errors
        return list(self.sets.get(key, set()))

    async def zadd(self, key: str, mapping: dict):
        """Add to sorted set."""
        if key not in self.sorted_sets:
            self.sorted_sets[key] = []
        for member, score in mapping.items():
            # Remove if exists
            self.sorted_sets[key] = [(m, s) for m, s in self.sorted_sets[key] if m != member]
            # Add new
            self.sorted_sets[key].append((member, score))
            # Sort by score
            self.sorted_sets[key].sort(key=lambda x: x[1])

    async def zrange(self, key: str, start: int, end: int, desc: bool = False):
        """Get range from sorted set."""
        if key not in self.sorted_sets:
            return []
        members = [m for m, s in self.sorted_sets[key]]
        if desc:
            members = list(reversed(members))
        if end == -1:
            return members[start:]
        return members[start:end + 1]

    async def zrem(self, key: str, *members):
        """Remove from sorted set."""
        if key not in self.sorted_sets:
            return 0
        count = 0
        for member in members:
            self.sorted_sets[key] = [(m, s) for m, s in self.sorted_sets[key] if m != member]
            count += 1
        return count

    async def zcard(self, key: str):
        """Get cardinality of sorted set."""
        return len(self.sorted_sets.get(key, []))

    async def publish(self, channel: str, message: str):
        """Publish message to channel."""
        pass


class TestQueueManagerInit:
    """Tests for QueueManager initialization."""

    def test_init_with_redis_url(self):
        """Should initialize with redis URL."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        assert manager.redis_url == "redis://localhost:6379/0"
        assert manager._redis is None
        assert manager._connected is False
        assert manager._subscribers == []

    def test_init_sets_correct_key_prefixes(self):
        """Should have correct Redis key prefixes."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        assert manager.PENDING_KEY == "queue:pending"
        assert manager.RUNNING_KEY == "queue:running"
        assert manager.FAILED_KEY == "queue:failed"
        assert manager.HISTORY_KEY == "queue:history"
        assert manager.ITEM_PREFIX == "queue:item:"
        assert manager.EVENTS_CHANNEL == "queue:events"

    def test_init_sets_correct_limits(self):
        """Should have correct default limits."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        assert manager.HISTORY_LIMIT == 100
        assert manager.ITEM_TTL_SECONDS == 86400 * 7  # 7 days


class TestQueueManagerConnection:
    """Tests for connection management."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_connect_establishes_connection(self):
        """Should establish Redis connection."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        # Mock the from_url to use FakeRedis
        async def fake_from_url(*args, **kwargs):
            return FakeRedis()

        with patch("redis.asyncio.from_url", side_effect=fake_from_url) as mock_from_url:
            await manager.connect()

            assert manager._connected is True
            assert manager._redis is not None
            mock_from_url.assert_called_once_with(
                "redis://localhost:6379/0",
                encoding="utf-8",
                decode_responses=True
            )

    @pytest.mark.asyncio
    async def test_connect_raises_on_connection_failure(self):
        """Should raise exception if connection fails."""
        manager = QueueManager(redis_url="redis://invalid:9999/0")

        # Create a mock Redis that raises on ping
        class FailingRedis:
            async def ping(self):
                raise ConnectionError("Connection failed")

        async def fake_from_url(*args, **kwargs):
            return FailingRedis()

        with patch("redis.asyncio.from_url", side_effect=fake_from_url):
            with pytest.raises(ConnectionError):
                await manager.connect()

            assert manager._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_closes_connection(self, manager):
        """Should close Redis connection."""
        assert manager.is_connected is True

        await manager.disconnect()

        assert manager._redis is None
        assert manager._connected is False

    @pytest.mark.asyncio
    async def test_is_connected_property(self, manager):
        """Should return connection status."""
        assert manager.is_connected is True

        await manager.disconnect()

        assert manager.is_connected is False


class TestQueueManagerEnqueue:
    """Tests for enqueue() method."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_enqueue_creates_queue_item(self, manager):
        """Should create and return QueueItem."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock) as mock_publish:
            item = await manager.enqueue(
                job_id="job_12345",
                job_title="Software Engineer",
                company="Test Corp",
                operation="full_pipeline",
                processing_tier="gold"
            )

            assert item.job_id == "job_12345"
            assert item.job_title == "Software Engineer"
            assert item.company == "Test Corp"
            assert item.operation == "full_pipeline"
            assert item.processing_tier == "gold"
            assert item.status == QueueItemStatus.PENDING
            assert item.queue_id.startswith("q_")
            assert item.position == 1
            assert item.created_at is not None

    @pytest.mark.asyncio
    async def test_enqueue_stores_in_redis(self, manager):
        """Should store item data in Redis hash."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_12345",
                job_title="Backend Engineer",
                company="Tech Inc"
            )

            # Verify hash exists
            key = f"{manager.ITEM_PREFIX}{item.queue_id}"
            data = await manager._redis.hgetall(key)

            assert data["job_id"] == "job_12345"
            assert data["job_title"] == "Backend Engineer"
            assert data["company"] == "Tech Inc"
            assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_enqueue_adds_to_pending_queue(self, manager):
        """Should add queue_id to pending list (FIFO)."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_12345",
                job_title="Test Job",
                company="Test Co"
            )

            # Verify in pending list
            pending = await manager._redis.lrange(manager.PENDING_KEY, 0, -1)
            assert item.queue_id in pending

    @pytest.mark.asyncio
    async def test_enqueue_sets_correct_position(self, manager):
        """Should calculate correct queue position."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item1 = await manager.enqueue("job1", "Title 1", "Company 1")
            item2 = await manager.enqueue("job2", "Title 2", "Company 2")
            item3 = await manager.enqueue("job3", "Title 3", "Company 3")

            assert item1.position == 1
            assert item2.position == 2
            assert item3.position == 3

    @pytest.mark.asyncio
    async def test_enqueue_sets_ttl_on_item(self, manager):
        """Should set TTL on item hash."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")

            # Check TTL is set
            key = f"{manager.ITEM_PREFIX}{item.queue_id}"
            ttl = await manager._redis.ttl(key)

            # Should be around 7 days (allow some margin)
            assert 604700 < ttl <= 604800

    @pytest.mark.asyncio
    async def test_enqueue_publishes_event(self, manager):
        """Should publish 'added' event."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock) as mock_publish:
            item = await manager.enqueue("job_12345", "Test", "Company")

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args[0]
            assert call_args[0] == "added"
            assert call_args[1].queue_id == item.queue_id

    @pytest.mark.asyncio
    async def test_enqueue_raises_when_not_connected(self):
        """Should raise RuntimeError when not connected."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        with pytest.raises(RuntimeError, match="not connected"):
            await manager.enqueue("job_12345", "Test", "Company")

    @pytest.mark.asyncio
    async def test_enqueue_uses_default_values(self, manager):
        """Should use default values for operation and tier."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")

            assert item.operation == "full_pipeline"
            assert item.processing_tier == "auto"


class TestQueueManagerDequeue:
    """Tests for dequeue() method."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_dequeue_returns_oldest_item_fifo(self, manager):
        """Should return oldest item (FIFO order)."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item1 = await manager.enqueue("job1", "First", "Company")
            item2 = await manager.enqueue("job2", "Second", "Company")
            item3 = await manager.enqueue("job3", "Third", "Company")

            # Dequeue should return item1 (oldest)
            dequeued = await manager.dequeue()

            assert dequeued.queue_id == item1.queue_id
            assert dequeued.job_id == "job1"

    @pytest.mark.asyncio
    async def test_dequeue_moves_to_running(self, manager):
        """Should move item from pending to running set."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")

            dequeued = await manager.dequeue()

            # Should be in running set
            running = await manager._redis.smembers(manager.RUNNING_KEY)
            assert dequeued.queue_id in running

            # Should not be in pending list
            pending = await manager._redis.lrange(manager.PENDING_KEY, 0, -1)
            assert dequeued.queue_id not in pending

    @pytest.mark.asyncio
    async def test_dequeue_updates_status_to_running(self, manager):
        """Should update item status to RUNNING."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            await manager.enqueue("job_12345", "Test", "Company")

            dequeued = await manager.dequeue()

            assert dequeued.status == QueueItemStatus.RUNNING
            assert dequeued.started_at is not None
            assert dequeued.position == 0

    @pytest.mark.asyncio
    async def test_dequeue_returns_none_when_empty(self, manager):
        """Should return None when queue is empty."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            result = await manager.dequeue()

            assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_publishes_started_event(self, manager):
        """Should publish 'started' event."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock) as mock_publish:
            await manager.enqueue("job_12345", "Test", "Company")
            mock_publish.reset_mock()

            dequeued = await manager.dequeue()

            # Should have been called with 'started'
            assert any(
                call_args[0][0] == "started" and call_args[0][1].queue_id == dequeued.queue_id
                for call_args in mock_publish.call_args_list
            )

    @pytest.mark.asyncio
    async def test_dequeue_raises_when_not_connected(self):
        """Should raise RuntimeError when not connected."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        with pytest.raises(RuntimeError, match="not connected"):
            await manager.dequeue()

    @pytest.mark.asyncio
    async def test_dequeue_handles_missing_item_gracefully(self, manager):
        """Should handle case where item data is missing."""
        # Manually add queue_id to pending without creating item hash
        await manager._redis.lpush(manager.PENDING_KEY, "q_missing123")

        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            result = await manager.dequeue()

            assert result is None


class TestQueueManagerComplete:
    """Tests for complete() method."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_complete_success_marks_as_completed(self, manager):
        """Should mark item as completed when success=True."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            completed = await manager.complete(dequeued.queue_id, success=True)

            assert completed.status == QueueItemStatus.COMPLETED
            assert completed.completed_at is not None
            assert completed.error is None

    @pytest.mark.asyncio
    async def test_complete_success_adds_to_history(self, manager):
        """Should add completed item to history list."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            await manager.complete(dequeued.queue_id, success=True)

            # Check history
            history = await manager._redis.lrange(manager.HISTORY_KEY, 0, -1)
            assert dequeued.queue_id in history

    @pytest.mark.asyncio
    async def test_complete_success_removes_from_running(self, manager):
        """Should remove item from running set."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            await manager.complete(dequeued.queue_id, success=True)

            # Should not be in running set
            running = await manager._redis.smembers(manager.RUNNING_KEY)
            assert dequeued.queue_id not in running

    @pytest.mark.asyncio
    async def test_complete_failure_marks_as_failed(self, manager):
        """Should mark item as failed when success=False."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            completed = await manager.complete(
                dequeued.queue_id,
                success=False,
                error="Pipeline execution failed"
            )

            assert completed.status == QueueItemStatus.FAILED
            assert completed.completed_at is not None
            assert completed.error == "Pipeline execution failed"

    @pytest.mark.asyncio
    async def test_complete_failure_adds_to_failed_zset(self, manager):
        """Should add failed item to failed sorted set."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            completed = await manager.complete(
                dequeued.queue_id,
                success=False,
                error="Test error"
            )

            # Check failed zset
            failed = await manager._redis.zrange(manager.FAILED_KEY, 0, -1)
            assert dequeued.queue_id in failed

    @pytest.mark.asyncio
    async def test_complete_publishes_completed_event(self, manager):
        """Should publish 'completed' event for success."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock) as mock_publish:
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()
            mock_publish.reset_mock()

            await manager.complete(dequeued.queue_id, success=True)

            # Check for 'completed' event
            assert any(
                call_args[0][0] == "completed"
                for call_args in mock_publish.call_args_list
            )

    @pytest.mark.asyncio
    async def test_complete_publishes_failed_event(self, manager):
        """Should publish 'failed' event for failure."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock) as mock_publish:
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()
            mock_publish.reset_mock()

            await manager.complete(dequeued.queue_id, success=False, error="Error")

            # Check for 'failed' event
            assert any(
                call_args[0][0] == "failed"
                for call_args in mock_publish.call_args_list
            )

    @pytest.mark.asyncio
    async def test_complete_returns_none_for_missing_item(self, manager):
        """Should return None if item not found."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            result = await manager.complete("q_nonexistent", success=True)

            assert result is None

    @pytest.mark.asyncio
    async def test_complete_raises_when_not_connected(self):
        """Should raise RuntimeError when not connected."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        with pytest.raises(RuntimeError, match="not connected"):
            await manager.complete("q_12345", success=True)


class TestQueueManagerRetry:
    """Tests for retry() method."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_retry_moves_failed_back_to_pending(self, manager):
        """Should move failed item back to pending queue."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()
            failed = await manager.complete(dequeued.queue_id, success=False, error="Error")

            retried = await manager.retry(failed.queue_id)

            assert retried.status == QueueItemStatus.PENDING
            assert retried.started_at is None
            assert retried.completed_at is None
            assert retried.error is None
            assert retried.run_id is None

    @pytest.mark.asyncio
    async def test_retry_removes_from_failed_set(self, manager):
        """Should remove item from failed zset."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()
            failed = await manager.complete(dequeued.queue_id, success=False, error="Error")

            await manager.retry(failed.queue_id)

            # Check not in failed set
            failed_items = await manager._redis.zrange(manager.FAILED_KEY, 0, -1)
            assert failed.queue_id not in failed_items

    @pytest.mark.asyncio
    async def test_retry_adds_to_pending_queue(self, manager):
        """Should add item back to pending queue."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()
            failed = await manager.complete(dequeued.queue_id, success=False, error="Error")

            retried = await manager.retry(failed.queue_id)

            # Check in pending queue
            pending = await manager._redis.lrange(manager.PENDING_KEY, 0, -1)
            assert retried.queue_id in pending

    @pytest.mark.asyncio
    async def test_retry_sets_position_to_one(self, manager):
        """Should set position to 1 (next to be processed)."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()
            failed = await manager.complete(dequeued.queue_id, success=False, error="Error")

            retried = await manager.retry(failed.queue_id)

            assert retried.position == 1

    @pytest.mark.asyncio
    async def test_retry_returns_none_for_missing_item(self, manager):
        """Should return None if item not found."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            result = await manager.retry("q_nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_retry_returns_none_for_non_failed_item(self, manager):
        """Should return None if item is not in failed state."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")

            # Try to retry a pending item
            result = await manager.retry(item.queue_id)

            assert result is None

    @pytest.mark.asyncio
    async def test_retry_publishes_retried_event(self, manager):
        """Should publish 'retried' event."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock) as mock_publish:
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()
            failed = await manager.complete(dequeued.queue_id, success=False, error="Error")
            mock_publish.reset_mock()

            await manager.retry(failed.queue_id)

            # Check for 'retried' event
            assert any(
                call_args[0][0] == "retried"
                for call_args in mock_publish.call_args_list
            )

    @pytest.mark.asyncio
    async def test_retry_raises_when_not_connected(self):
        """Should raise RuntimeError when not connected."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        with pytest.raises(RuntimeError, match="not connected"):
            await manager.retry("q_12345")


class TestQueueManagerCancel:
    """Tests for cancel() method."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_cancel_removes_pending_item(self, manager):
        """Should cancel pending item."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")

            result = await manager.cancel(item.queue_id)

            assert result is True

            # Should not be in pending queue
            pending = await manager._redis.lrange(manager.PENDING_KEY, 0, -1)
            assert item.queue_id not in pending

    @pytest.mark.asyncio
    async def test_cancel_updates_status_to_cancelled(self, manager):
        """Should update status to CANCELLED."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")

            await manager.cancel(item.queue_id)

            # Retrieve and check status
            cancelled = await manager.get_item(item.queue_id)
            assert cancelled.status == QueueItemStatus.CANCELLED
            assert cancelled.completed_at is not None
            assert cancelled.position == 0

    @pytest.mark.asyncio
    async def test_cancel_returns_false_for_missing_item(self, manager):
        """Should return False if item not found."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            result = await manager.cancel("q_nonexistent")

            assert result is False

    @pytest.mark.asyncio
    async def test_cancel_returns_false_for_non_pending_item(self, manager):
        """Should return False if item is not pending."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            # Try to cancel a running item
            result = await manager.cancel(dequeued.queue_id)

            assert result is False

    @pytest.mark.asyncio
    async def test_cancel_publishes_cancelled_event(self, manager):
        """Should publish 'cancelled' event."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock) as mock_publish:
            item = await manager.enqueue("job_12345", "Test", "Company")
            mock_publish.reset_mock()

            await manager.cancel(item.queue_id)

            # Check for 'cancelled' event
            assert any(
                call_args[0][0] == "cancelled"
                for call_args in mock_publish.call_args_list
            )

    @pytest.mark.asyncio
    async def test_cancel_raises_when_not_connected(self):
        """Should raise RuntimeError when not connected."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        with pytest.raises(RuntimeError, match="not connected"):
            await manager.cancel("q_12345")


class TestQueueManagerDismissFailed:
    """Tests for dismiss_failed() method."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_dismiss_failed_removes_from_failed_set(self, manager):
        """Should remove item from failed zset."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()
            failed = await manager.complete(dequeued.queue_id, success=False, error="Error")

            result = await manager.dismiss_failed(failed.queue_id)

            assert result is True

            # Check not in failed set
            failed_items = await manager._redis.zrange(manager.FAILED_KEY, 0, -1)
            assert failed.queue_id not in failed_items

    @pytest.mark.asyncio
    async def test_dismiss_failed_moves_to_history(self, manager):
        """Should move failed item to history."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()
            failed = await manager.complete(dequeued.queue_id, success=False, error="Error")

            await manager.dismiss_failed(failed.queue_id)

            # Check in history
            history = await manager._redis.lrange(manager.HISTORY_KEY, 0, -1)
            assert failed.queue_id in history

    @pytest.mark.asyncio
    async def test_dismiss_failed_returns_false_for_missing_item(self, manager):
        """Should return False if item not found."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            result = await manager.dismiss_failed("q_nonexistent")

            assert result is False

    @pytest.mark.asyncio
    async def test_dismiss_failed_returns_false_for_non_failed_item(self, manager):
        """Should return False if item is not failed."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")

            result = await manager.dismiss_failed(item.queue_id)

            assert result is False

    @pytest.mark.asyncio
    async def test_dismiss_failed_publishes_dismissed_event(self, manager):
        """Should publish 'dismissed' event."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock) as mock_publish:
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()
            failed = await manager.complete(dequeued.queue_id, success=False, error="Error")
            mock_publish.reset_mock()

            await manager.dismiss_failed(failed.queue_id)

            # Check for 'dismissed' event
            assert any(
                call_args[0][0] == "dismissed"
                for call_args in mock_publish.call_args_list
            )

    @pytest.mark.asyncio
    async def test_dismiss_failed_raises_when_not_connected(self):
        """Should raise RuntimeError when not connected."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        with pytest.raises(RuntimeError, match="not connected"):
            await manager.dismiss_failed("q_12345")


class TestQueueManagerGetItem:
    """Tests for get_item() and get_item_by_job_id() methods."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_get_item_retrieves_by_queue_id(self, manager):
        """Should retrieve item by queue_id."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test Job", "Test Co")

            retrieved = await manager.get_item(item.queue_id)

            assert retrieved is not None
            assert retrieved.queue_id == item.queue_id
            assert retrieved.job_id == "job_12345"
            assert retrieved.job_title == "Test Job"
            assert retrieved.company == "Test Co"

    @pytest.mark.asyncio
    async def test_get_item_returns_none_for_missing_item(self, manager):
        """Should return None if item not found."""
        result = await manager.get_item("q_nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_item_returns_none_when_not_connected(self):
        """Should return None when not connected."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        result = await manager.get_item("q_12345")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_item_by_job_id_finds_in_running(self, manager):
        """Should find item by job_id in running set."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            found = await manager.get_item_by_job_id("job_12345")

            assert found is not None
            assert found.job_id == "job_12345"
            assert found.status == QueueItemStatus.RUNNING

    @pytest.mark.asyncio
    async def test_get_item_by_job_id_finds_in_pending(self, manager):
        """Should find item by job_id in pending queue."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")

            found = await manager.get_item_by_job_id("job_12345")

            assert found is not None
            assert found.job_id == "job_12345"
            assert found.status == QueueItemStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_item_by_job_id_finds_in_failed(self, manager):
        """Should find item by job_id in failed set."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()
            failed = await manager.complete(dequeued.queue_id, success=False, error="Error")

            found = await manager.get_item_by_job_id("job_12345")

            assert found is not None
            assert found.job_id == "job_12345"
            assert found.status == QueueItemStatus.FAILED

    @pytest.mark.asyncio
    async def test_get_item_by_job_id_returns_none_when_not_found(self, manager):
        """Should return None if job_id not found."""
        result = await manager.get_item_by_job_id("job_nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_item_by_job_id_sets_position_for_pending(self, manager):
        """Should calculate position for pending items."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item1 = await manager.enqueue("job1", "First", "Company")
            item2 = await manager.enqueue("job2", "Second", "Company")
            item3 = await manager.enqueue("job3", "Third", "Company")

            found = await manager.get_item_by_job_id("job2")

            assert found.position == 2


class TestQueueManagerGetState:
    """Tests for get_state() method."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_get_state_returns_queue_state(self, manager):
        """Should return QueueState with all lists."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            # Create items in different states
            item1 = await manager.enqueue("job1", "Pending 1", "Company")
            item2 = await manager.enqueue("job2", "Pending 2", "Company")
            item3 = await manager.enqueue("job3", "Pending 3", "Company")
            dequeued = await manager.dequeue()  # item1 is now running (FIFO)

            state = await manager.get_state()

            assert isinstance(state, QueueState)
            assert len(state.pending) >= 1
            assert len(state.running) == 1
            assert state.running[0].job_id == "job1"

    @pytest.mark.asyncio
    async def test_get_state_limits_pending_items(self, manager):
        """Should limit pending items to pending_limit."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            # Create 15 pending items
            for i in range(15):
                await manager.enqueue(f"job{i}", f"Job {i}", "Company")

            state = await manager.get_state(pending_limit=5)

            # Should return only 5 oldest pending items
            assert len(state.pending) == 5

    @pytest.mark.asyncio
    async def test_get_state_includes_stats(self, manager):
        """Should include queue statistics."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item1 = await manager.enqueue("job1", "Test 1", "Company")
            item2 = await manager.enqueue("job2", "Test 2", "Company")
            dequeued = await manager.dequeue()
            await manager.complete(dequeued.queue_id, success=False, error="Error")

            state = await manager.get_state()

            assert state.stats["total_pending"] == 1
            assert state.stats["total_running"] == 0
            assert state.stats["total_failed"] == 1

    @pytest.mark.asyncio
    async def test_get_state_returns_default_when_not_connected(self):
        """Should return empty state when not connected."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        state = await manager.get_state()

        assert isinstance(state, QueueState)
        assert state.stats["total_pending"] == 0
        assert state.stats["total_running"] == 0
        assert state.stats["total_failed"] == 0

    @pytest.mark.asyncio
    async def test_get_state_sets_correct_positions(self, manager):
        """Should set correct positions for pending items."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            # Create multiple pending items
            for i in range(5):
                await manager.enqueue(f"job{i}", f"Job {i}", "Company")

            state = await manager.get_state(pending_limit=10)

            # Positions should be 1-indexed
            for i, item in enumerate(state.pending, start=1):
                assert item.position == i


class TestQueueManagerLinkRunId:
    """Tests for link_run_id() method."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_link_run_id_updates_item(self, manager):
        """Should link run_id to queue item."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")

            await manager.link_run_id(item.queue_id, "run_abc123")

            updated = await manager.get_item(item.queue_id)
            assert updated.run_id == "run_abc123"

    @pytest.mark.asyncio
    async def test_link_run_id_publishes_updated_event(self, manager):
        """Should publish 'updated' event."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock) as mock_publish:
            item = await manager.enqueue("job_12345", "Test", "Company")
            mock_publish.reset_mock()

            await manager.link_run_id(item.queue_id, "run_abc123")

            # Check for 'updated' event
            assert any(
                call_args[0][0] == "updated"
                for call_args in mock_publish.call_args_list
            )

    @pytest.mark.asyncio
    async def test_link_run_id_handles_missing_item(self, manager):
        """Should handle missing item gracefully."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            # Should not raise
            await manager.link_run_id("q_nonexistent", "run_abc123")


class TestQueueManagerRestoreInterruptedRuns:
    """Tests for restore_interrupted_runs() method."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_restore_interrupted_runs_moves_running_to_pending(self, manager):
        """Should move interrupted runs back to pending."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            # Simulate service restart
            restored = await manager.restore_interrupted_runs()

            assert len(restored) == 1
            assert restored[0].queue_id == dequeued.queue_id
            assert restored[0].status == QueueItemStatus.PENDING
            assert restored[0].started_at is None
            assert restored[0].run_id is None

    @pytest.mark.asyncio
    async def test_restore_interrupted_runs_removes_from_running_set(self, manager):
        """Should remove items from running set."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            await manager.restore_interrupted_runs()

            # Check not in running set
            running = await manager._redis.smembers(manager.RUNNING_KEY)
            assert len(running) == 0

    @pytest.mark.asyncio
    async def test_restore_interrupted_runs_adds_to_pending_queue(self, manager):
        """Should add items back to pending queue."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            await manager.restore_interrupted_runs()

            # Check in pending queue
            pending = await manager._redis.lrange(manager.PENDING_KEY, 0, -1)
            assert dequeued.queue_id in pending

    @pytest.mark.asyncio
    async def test_restore_interrupted_runs_returns_empty_when_none(self, manager):
        """Should return empty list when no interrupted runs."""
        restored = await manager.restore_interrupted_runs()

        assert restored == []

    @pytest.mark.asyncio
    async def test_restore_interrupted_runs_returns_empty_when_not_connected(self):
        """Should return empty list when not connected."""
        manager = QueueManager(redis_url="redis://localhost:6379/0")

        restored = await manager.restore_interrupted_runs()

        assert restored == []


class TestQueueManagerHistoryTrimming:
    """Tests for history list trimming."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_history_trimmed_to_limit(self, manager):
        """Should trim history to HISTORY_LIMIT."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            # Complete more items than the history limit (100)
            for i in range(105):
                item = await manager.enqueue(f"job{i}", f"Job {i}", "Company")
                dequeued = await manager.dequeue()
                await manager.complete(dequeued.queue_id, success=True)

            # Check history length
            history_len = await manager._redis.llen(manager.HISTORY_KEY)
            assert history_len == manager.HISTORY_LIMIT


class TestQueueManagerEventPublishing:
    """Tests for event publishing mechanism."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_subscribe_adds_callback(self, manager):
        """Should add callback to subscribers list."""
        async def callback(event):
            pass

        await manager.subscribe(callback)

        assert callback in manager._subscribers

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_callback(self, manager):
        """Should remove callback from subscribers list."""
        async def callback(event):
            pass

        await manager.subscribe(callback)
        manager.unsubscribe(callback)

        assert callback not in manager._subscribers

    @pytest.mark.asyncio
    async def test_publish_event_calls_subscribers(self, manager):
        """Should call all registered subscribers."""
        events_received = []

        async def callback(event):
            events_received.append(event)

        await manager.subscribe(callback)

        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")

        # Manually trigger event to test subscribers
        await manager._publish_event("test", item)

        assert len(events_received) == 1
        assert events_received[0]["action"] == "test"

    @pytest.mark.asyncio
    async def test_publish_event_handles_callback_exceptions(self, manager):
        """Should handle subscriber callback exceptions gracefully."""
        async def failing_callback(event):
            raise RuntimeError("Callback error")

        async def working_callback(event):
            pass

        await manager.subscribe(failing_callback)
        await manager.subscribe(working_callback)

        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")

        # Should not raise despite callback failing
        await manager._publish_event("test", item)


class TestQueueManagerEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def manager(self):
        """Create manager with fake Redis."""
        mgr = QueueManager(redis_url="redis://localhost:6379/0")
        mgr._redis = FakeRedis()
        mgr._connected = True
        return mgr

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue_returns_none(self, manager):
        """Should return None when dequeueing empty queue."""
        result = await manager.dequeue()

        assert result is None

    @pytest.mark.asyncio
    async def test_complete_same_item_twice_handles_gracefully(self, manager):
        """Should handle completing same item twice."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            await manager.complete(dequeued.queue_id, success=True)
            # Try to complete again - should handle gracefully
            result = await manager.complete(dequeued.queue_id, success=True)

            # Item is no longer in running set, so this should work but be idempotent
            assert result is not None

    @pytest.mark.asyncio
    async def test_fifo_ordering_maintained(self, manager):
        """Should maintain FIFO ordering."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item1 = await manager.enqueue("job1", "First", "Company")
            item2 = await manager.enqueue("job2", "Second", "Company")
            item3 = await manager.enqueue("job3", "Third", "Company")

            dequeued1 = await manager.dequeue()
            dequeued2 = await manager.dequeue()
            dequeued3 = await manager.dequeue()

            assert dequeued1.job_id == "job1"
            assert dequeued2.job_id == "job2"
            assert dequeued3.job_id == "job3"

    @pytest.mark.asyncio
    async def test_special_characters_in_job_data(self, manager):
        """Should handle special characters in job data."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_12345",
                job_title="Software Engineer (Backend/Frontend)",
                company="O'Reilly & Sons, Inc."
            )

            retrieved = await manager.get_item(item.queue_id)

            assert retrieved.job_title == "Software Engineer (Backend/Frontend)"
            assert retrieved.company == "O'Reilly & Sons, Inc."

    @pytest.mark.asyncio
    async def test_long_error_messages_stored(self, manager):
        """Should handle long error messages."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue("job_12345", "Test", "Company")
            dequeued = await manager.dequeue()

            long_error = "Error: " + "x" * 5000
            completed = await manager.complete(
                dequeued.queue_id,
                success=False,
                error=long_error
            )

            assert completed.error == long_error

    @pytest.mark.asyncio
    async def test_count_completed_today_filters_correctly(self, manager):
        """Should count only items completed today."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            # Complete some items
            for i in range(3):
                item = await manager.enqueue(f"job{i}", f"Job {i}", "Company")
                dequeued = await manager.dequeue()
                await manager.complete(dequeued.queue_id, success=True)

            count = await manager._count_completed_today()

            assert count == 3

    @pytest.mark.asyncio
    async def test_empty_job_title_and_company_handled(self, manager):
        """Should handle empty job title and company."""
        with patch.object(manager, '_publish_event', new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_12345",
                job_title="",
                company=""
            )

            assert item.job_title == ""
            assert item.company == ""
