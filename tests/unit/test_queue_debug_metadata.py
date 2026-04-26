"""
Unit tests for debug metadata fields in queue models and manager.

Covers:
- QueueItem new fields: retry_count, last_error_at, failure_context, attempt_history
- to_redis_hash() serialization of debug fields
- from_dict() deserialization including backward compat with missing fields
- QueueManager.complete(success=False) sets last_error_at and failure_context
- Multiple failures accumulate in attempt_history
- QueueManager.retry() increments retry_count and preserves error history
"""

import json
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from runner_service.queue.manager import QueueManager
from runner_service.queue.models import QueueItem, QueueItemStatus

# ---------------------------------------------------------------------------
# FakeRedis — copied from test_queue_manager.py and extended with get/incr
# ---------------------------------------------------------------------------

class FakeRedis:
    """Fake Redis implementation for testing (with get/incr/delete support)."""

    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.lists: Dict[str, List[str]] = {}
        self.sets: Dict[str, set] = {}
        self.sorted_sets: Dict[str, List[tuple]] = {}
        self.ttls: Dict[str, int] = {}
        self.strings: Dict[str, str] = {}  # For get/set/incr

    async def ping(self):
        return True

    async def close(self):
        pass

    async def hset(self, key: str, mapping: dict):
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)

    async def hgetall(self, key: str):
        return self.data.get(key, {})

    async def expire(self, key: str, seconds: int):
        self.ttls[key] = seconds

    async def get(self, key: str):
        return self.strings.get(key)

    async def incr(self, key: str):
        current = int(self.strings.get(key, 0))
        new_val = current + 1
        self.strings[key] = str(new_val)
        return new_val

    async def delete(self, *keys):
        count = 0
        for key in keys:
            for store in (self.data, self.lists, self.sets, self.sorted_sets, self.strings):
                if key in store:
                    del store[key]
                    count += 1
        return count

    async def lpush(self, key: str, *values):
        if key not in self.lists:
            self.lists[key] = []
        for value in reversed(values):
            self.lists[key].insert(0, value)

    async def rpush(self, key: str, *values):
        if key not in self.lists:
            self.lists[key] = []
        self.lists[key].extend(values)

    async def lpop(self, key: str):
        if key not in self.lists or not self.lists[key]:
            return None
        return self.lists[key].pop(0)

    async def rpop(self, key: str):
        if key not in self.lists or not self.lists[key]:
            return None
        return self.lists[key].pop()

    async def lrange(self, key: str, start: int, end: int):
        if key not in self.lists:
            return []
        lst = self.lists[key]
        if end == -1:
            return lst[start:]
        return lst[start:end + 1]

    async def llen(self, key: str):
        return len(self.lists.get(key, []))

    async def lrem(self, key: str, count: int, value: str):
        if key not in self.lists:
            return 0
        try:
            self.lists[key].remove(value)
            return 1
        except ValueError:
            return 0

    async def ltrim(self, key: str, start: int, end: int):
        if key in self.lists:
            self.lists[key] = self.lists[key][start:end + 1]

    async def sadd(self, key: str, *values):
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].update(values)

    async def srem(self, key: str, *values):
        if key not in self.sets:
            return 0
        count = 0
        for value in values:
            if value in self.sets[key]:
                self.sets[key].remove(value)
                count += 1
        return count

    async def smembers(self, key: str):
        return list(self.sets.get(key, set()))

    async def zadd(self, key: str, mapping: dict):
        if key not in self.sorted_sets:
            self.sorted_sets[key] = []
        for member, score in mapping.items():
            self.sorted_sets[key] = [
                (m, s) for m, s in self.sorted_sets[key] if m != member
            ]
            self.sorted_sets[key].append((member, score))
            self.sorted_sets[key].sort(key=lambda x: x[1])

    async def zrange(self, key: str, start: int, end: int, desc: bool = False):
        if key not in self.sorted_sets:
            return []
        members = [m for m, s in self.sorted_sets[key]]
        if desc:
            members = list(reversed(members))
        if end == -1:
            return members[start:]
        return members[start:end + 1]

    async def zrem(self, key: str, *members):
        if key not in self.sorted_sets:
            return 0
        count = 0
        for member in members:
            self.sorted_sets[key] = [
                (m, s) for m, s in self.sorted_sets[key] if m != member
            ]
            count += 1
        return count

    async def zcard(self, key: str):
        return len(self.sorted_sets.get(key, []))

    async def publish(self, channel: str, message: str):
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(**kwargs) -> QueueItem:
    """Build a minimal QueueItem with sane defaults."""
    defaults = dict(
        queue_id="q_test001",
        job_id="job_abc123",
        job_title="AI Engineer",
        company="Acme Corp",
        status=QueueItemStatus.PENDING,
        created_at=datetime.utcnow(),
    )
    defaults.update(kwargs)
    return QueueItem(**defaults)


def _make_manager() -> QueueManager:
    """Return a QueueManager wired to a fresh FakeRedis."""
    mgr = QueueManager(redis_url="redis://localhost:6379/0")
    mgr._redis = FakeRedis()
    mgr._connected = True
    return mgr


# ---------------------------------------------------------------------------
# TestDebugMetadata — model-level tests (no Redis needed)
# ---------------------------------------------------------------------------

class TestDebugMetadata:
    """Tests for the four new debug fields on QueueItem."""

    def test_new_fields_have_defaults(self):
        """QueueItem created without debug fields should default gracefully (backward compat)."""
        item = _make_item()

        assert item.retry_count == 0
        assert item.last_error_at is None
        assert item.failure_context is None
        assert item.attempt_history is None

    def test_to_redis_hash_includes_debug_fields(self):
        """to_redis_hash() must serialise all four debug fields as strings."""
        now = datetime(2026, 3, 6, 12, 0, 0)
        ctx = json.dumps({"error": "timeout", "failed_at": now.isoformat()})
        hist = json.dumps([{"attempt": 1, "error": "timeout"}])

        item = _make_item(
            status=QueueItemStatus.FAILED,
            retry_count=2,
            last_error_at=now,
            failure_context=ctx,
            attempt_history=hist,
        )
        redis_hash = item.to_redis_hash()

        assert redis_hash["retry_count"] == "2"
        assert redis_hash["last_error_at"] == now.isoformat()
        assert redis_hash["failure_context"] == ctx
        assert redis_hash["attempt_history"] == hist

    def test_to_redis_hash_uses_empty_string_for_none_fields(self):
        """None debug fields must serialise to empty strings, not 'None'."""
        item = _make_item()
        redis_hash = item.to_redis_hash()

        assert redis_hash["last_error_at"] == ""
        assert redis_hash["failure_context"] == ""
        assert redis_hash["attempt_history"] == ""

    def test_from_dict_deserializes_debug_fields(self):
        """from_dict() must correctly round-trip all four debug fields."""
        now = datetime(2026, 3, 6, 12, 0, 0)
        ctx = json.dumps({"error": "OOM", "failed_at": now.isoformat()})
        hist = json.dumps([{"attempt": 1, "error": "OOM"}])

        data = {
            "job_id": "job_abc",
            "job_title": "Engineer",
            "company": "Corp",
            "status": "failed",
            "created_at": now.isoformat(),
            "retry_count": "3",
            "last_error_at": now.isoformat(),
            "failure_context": ctx,
            "attempt_history": hist,
        }
        item = QueueItem.from_dict("q_test", data)

        assert item.retry_count == 3
        assert item.last_error_at == now
        assert item.failure_context == ctx
        assert item.attempt_history == hist

    def test_from_dict_handles_missing_fields(self):
        """Existing Redis items without debug fields must deserialize with defaults (backward compat)."""
        now = datetime(2026, 3, 6, 12, 0, 0)
        # Simulate an old Redis hash that never had the new keys
        data = {
            "job_id": "job_legacy",
            "job_title": "Old Role",
            "company": "Legacy Corp",
            "status": "failed",
            "created_at": now.isoformat(),
            # retry_count, last_error_at, failure_context, attempt_history are absent
        }
        item = QueueItem.from_dict("q_legacy", data)

        assert item.retry_count == 0
        assert item.last_error_at is None
        assert item.failure_context is None
        assert item.attempt_history is None


# ---------------------------------------------------------------------------
# TestFailureRecordsContext — manager-level failure tests
# ---------------------------------------------------------------------------

class TestFailureRecordsContext:
    """Tests that complete(success=False) correctly writes debug metadata to Redis."""

    @pytest.mark.asyncio
    async def test_complete_failure_sets_error_metadata(self):
        """complete(success=False) must populate last_error_at and failure_context."""
        manager = _make_manager()

        # Arrange: enqueue and dequeue so the item exists and is RUNNING
        with patch.object(manager, "_publish_event", new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_001",
                job_title="AI Engineer",
                company="Acme",
            )
            await manager.dequeue()

            # Act
            result = await manager.complete(
                item.queue_id,
                success=False,
                error="Layer 4 timed out",
            )

        # Assert
        assert result is not None
        assert result.status == QueueItemStatus.FAILED
        assert result.error == "Layer 4 timed out"
        assert result.last_error_at is not None
        assert isinstance(result.last_error_at, datetime)

        ctx = json.loads(result.failure_context)
        assert ctx["error"] == "Layer 4 timed out"
        assert "failed_at" in ctx

    @pytest.mark.asyncio
    async def test_complete_failure_initializes_attempt_history(self):
        """First failure must create attempt_history with exactly one entry."""
        manager = _make_manager()

        with patch.object(manager, "_publish_event", new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_002",
                job_title="Data Scientist",
                company="Beta",
            )
            await manager.dequeue()
            result = await manager.complete(
                item.queue_id,
                success=False,
                error="connection reset",
            )

        history = json.loads(result.attempt_history)
        assert len(history) == 1
        assert history[0]["attempt"] == 1
        assert history[0]["error"] == "connection reset"
        assert "failed_at" in history[0]

    @pytest.mark.asyncio
    async def test_attempt_history_accumulates(self):
        """Multiple failures must accumulate distinct entries in attempt_history."""
        manager = _make_manager()

        with patch.object(manager, "_publish_event", new_callable=AsyncMock):
            # First cycle: enqueue → dequeue → fail
            item = await manager.enqueue(
                job_id="job_003",
                job_title="ML Infra",
                company="Gamma",
            )
            await manager.dequeue()
            failed_item = await manager.complete(
                item.queue_id,
                success=False,
                error="timeout on layer 3",
            )
            assert failed_item is not None

            # Retry (moves back to pending, increments retry_count)
            await manager.retry(failed_item.queue_id)

            # Second cycle: dequeue → fail again
            await manager.dequeue()
            failed_again = await manager.complete(
                failed_item.queue_id,
                success=False,
                error="OOM on layer 5",
            )

        assert failed_again is not None
        history = json.loads(failed_again.attempt_history)
        assert len(history) == 2, f"Expected 2 attempt entries, got {len(history)}: {history}"
        errors = [h["error"] for h in history]
        assert "timeout on layer 3" in errors
        assert "OOM on layer 5" in errors

    @pytest.mark.asyncio
    async def test_complete_success_does_not_set_error_metadata(self):
        """complete(success=True) must leave debug fields unpopulated."""
        manager = _make_manager()

        with patch.object(manager, "_publish_event", new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_004",
                job_title="Engineer",
                company="Delta",
            )
            await manager.dequeue()
            result = await manager.complete(item.queue_id, success=True)

        assert result is not None
        assert result.status == QueueItemStatus.COMPLETED
        assert result.last_error_at is None
        assert result.failure_context is None
        assert result.attempt_history is None


# ---------------------------------------------------------------------------
# TestRetryIncrementsCount — retry() behaviour tests
# ---------------------------------------------------------------------------

class TestRetryIncrementsCount:
    """Tests that retry() increments retry_count and preserves error history."""

    @pytest.mark.asyncio
    async def test_retry_increments_count(self):
        """retry() must increment retry_count from 0 to 1."""
        manager = _make_manager()

        with patch.object(manager, "_publish_event", new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_005",
                job_title="Platform Engineer",
                company="Epsilon",
            )
            await manager.dequeue()
            await manager.complete(item.queue_id, success=False, error="first error")

            retried = await manager.retry(item.queue_id)

        assert retried is not None
        assert retried.retry_count == 1

    @pytest.mark.asyncio
    async def test_retry_increments_count_multiple_times(self):
        """retry_count must reflect the total number of retries across the lifecycle."""
        manager = _make_manager()

        with patch.object(manager, "_publish_event", new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_006",
                job_title="Backend Engineer",
                company="Zeta",
            )

            # Fail + retry three times
            for i in range(3):
                await manager.dequeue()
                await manager.complete(item.queue_id, success=False, error=f"error {i + 1}")
                retried = await manager.retry(item.queue_id)
                assert retried.retry_count == i + 1

    @pytest.mark.asyncio
    async def test_retry_preserves_error_history(self):
        """retry() must NOT clear failure_context or attempt_history."""
        manager = _make_manager()

        with patch.object(manager, "_publish_event", new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_007",
                job_title="SRE",
                company="Eta",
            )
            await manager.dequeue()
            await manager.complete(
                item.queue_id,
                success=False,
                error="disk full",
            )

            retried = await manager.retry(item.queue_id)

        # failure_context and attempt_history should survive the retry transition
        assert retried is not None
        assert retried.failure_context is not None
        ctx = json.loads(retried.failure_context)
        assert ctx["error"] == "disk full"

        assert retried.attempt_history is not None
        history = json.loads(retried.attempt_history)
        assert len(history) == 1
        assert history[0]["error"] == "disk full"

    @pytest.mark.asyncio
    async def test_retry_resets_transient_status_fields(self):
        """retry() must reset status to PENDING and clear started_at/completed_at/error."""
        manager = _make_manager()

        with patch.object(manager, "_publish_event", new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_008",
                job_title="DevOps",
                company="Theta",
            )
            await manager.dequeue()
            await manager.complete(item.queue_id, success=False, error="pod crash")
            retried = await manager.retry(item.queue_id)

        assert retried.status == QueueItemStatus.PENDING
        assert retried.started_at is None
        assert retried.completed_at is None
        assert retried.error is None

    @pytest.mark.asyncio
    async def test_retry_only_works_on_failed_items(self):
        """retry() on a PENDING item must return None without modifying the item."""
        manager = _make_manager()

        with patch.object(manager, "_publish_event", new_callable=AsyncMock):
            item = await manager.enqueue(
                job_id="job_009",
                job_title="Analyst",
                company="Iota",
            )
            # Do not dequeue/complete — item stays PENDING
            result = await manager.retry(item.queue_id)

        assert result is None
        # Original item should be unmodified
        original = await manager.get_item(item.queue_id)
        assert original.retry_count == 0
