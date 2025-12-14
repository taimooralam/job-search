"""
Redis Queue Manager

Provides persistent FIFO queue operations backed by Redis.
Handles job lifecycle: enqueue, dequeue, complete, retry, cancel.
Publishes events for real-time WebSocket broadcasting.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, date
from typing import Any, Callable, Coroutine, Dict, List, Optional

import redis.asyncio as aioredis
from redis.asyncio import Redis

from .models import QueueItem, QueueItemStatus, QueueState

logger = logging.getLogger(__name__)


class QueueManager:
    """
    Manages the persistent job queue in Redis.

    Uses Redis data structures:
    - LIST for FIFO queue (pending jobs)
    - SET for running jobs
    - ZSET for failed jobs (sorted by timestamp)
    - LIST for history (recent completed, capped)
    - HASH for individual item data
    - Pub/Sub for real-time event broadcasting
    """

    # Redis key prefixes
    PENDING_KEY = "queue:pending"
    RUNNING_KEY = "queue:running"
    FAILED_KEY = "queue:failed"
    HISTORY_KEY = "queue:history"
    ITEM_PREFIX = "queue:item:"
    EVENTS_CHANNEL = "queue:events"

    # Limits
    HISTORY_LIMIT = 100
    ITEM_TTL_SECONDS = 86400 * 7  # 7 days

    def __init__(self, redis_url: str):
        """
        Initialize queue manager.

        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self._redis: Optional[Redis] = None
        self._pubsub = None
        self._subscribers: List[Callable[[Dict], Coroutine[Any, Any, None]]] = []
        self._connected = False

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            await self._redis.ping()
            self._connected = True
            logger.info("Queue manager connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._connected = False
            logger.info("Queue manager disconnected from Redis")

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._connected and self._redis is not None

    async def enqueue(
        self,
        job_id: str,
        job_title: str,
        company: str,
        operation: str = "full_pipeline",
        processing_tier: str = "auto",
    ) -> QueueItem:
        """
        Add a job to the queue (FIFO).

        Args:
            job_id: MongoDB job _id
            job_title: Job title for display
            company: Company name for display
            operation: Operation type
            processing_tier: Processing tier

        Returns:
            Created QueueItem
        """
        if not self._redis:
            raise RuntimeError("Queue manager not connected")

        queue_id = f"q_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        item = QueueItem(
            queue_id=queue_id,
            job_id=job_id,
            job_title=job_title,
            company=company,
            status=QueueItemStatus.PENDING,
            operation=operation,
            processing_tier=processing_tier,
            created_at=now,
        )

        # Store item data as hash
        await self._redis.hset(
            f"{self.ITEM_PREFIX}{queue_id}",
            mapping=item.to_redis_hash()
        )
        await self._redis.expire(
            f"{self.ITEM_PREFIX}{queue_id}",
            self.ITEM_TTL_SECONDS
        )

        # Add to pending queue (LPUSH = add to head, RPOP = remove from tail = FIFO)
        await self._redis.lpush(self.PENDING_KEY, queue_id)

        # Calculate position
        item.position = await self._redis.llen(self.PENDING_KEY)

        # Publish event
        await self._publish_event("added", item)

        logger.info(f"Enqueued job {job_id} as {queue_id} (position {item.position})")
        return item

    async def dequeue(self) -> Optional[QueueItem]:
        """
        Get next job from queue (FIFO).

        Moves item from pending to running.

        Returns:
            QueueItem or None if queue is empty
        """
        if not self._redis:
            raise RuntimeError("Queue manager not connected")

        # RPOP = remove from tail (oldest item)
        queue_id = await self._redis.rpop(self.PENDING_KEY)
        if not queue_id:
            return None

        item = await self.get_item(queue_id)
        if not item:
            logger.warning(f"Queue item {queue_id} not found after dequeue")
            return None

        # Move to running set
        await self._redis.sadd(self.RUNNING_KEY, queue_id)

        # Update item status
        item.status = QueueItemStatus.RUNNING
        item.started_at = datetime.utcnow()
        item.position = 0  # No longer in queue
        await self._update_item(item)

        # Publish event
        await self._publish_event("started", item)

        logger.info(f"Dequeued {queue_id} for job {item.job_id}")
        return item

    async def complete(
        self,
        queue_id: str,
        success: bool,
        error: Optional[str] = None
    ) -> Optional[QueueItem]:
        """
        Mark a job as completed or failed.

        Args:
            queue_id: Queue item ID
            success: Whether the job succeeded
            error: Error message if failed

        Returns:
            Updated QueueItem or None if not found
        """
        if not self._redis:
            raise RuntimeError("Queue manager not connected")

        item = await self.get_item(queue_id)
        if not item:
            logger.warning(f"Cannot complete: queue item {queue_id} not found")
            return None

        # Remove from running set
        await self._redis.srem(self.RUNNING_KEY, queue_id)

        item.completed_at = datetime.utcnow()

        if success:
            item.status = QueueItemStatus.COMPLETED
            # Add to history (LPUSH + LTRIM for capped list)
            await self._redis.lpush(self.HISTORY_KEY, queue_id)
            await self._redis.ltrim(self.HISTORY_KEY, 0, self.HISTORY_LIMIT - 1)
            await self._publish_event("completed", item)
            logger.info(f"Completed {queue_id} for job {item.job_id}")
        else:
            item.status = QueueItemStatus.FAILED
            item.error = error
            # Add to failed set (ZADD with timestamp for sorting)
            await self._redis.zadd(
                self.FAILED_KEY,
                {queue_id: item.completed_at.timestamp()}
            )
            await self._publish_event("failed", item)
            logger.warning(f"Failed {queue_id} for job {item.job_id}: {error}")

        await self._update_item(item)
        return item

    async def fail(
        self,
        queue_id: str,
        error: str
    ) -> Optional[QueueItem]:
        """
        Mark a job as failed (convenience wrapper for complete with success=False).

        Args:
            queue_id: Queue item ID
            error: Error message

        Returns:
            Updated QueueItem or None if not found
        """
        return await self.complete(queue_id, success=False, error=error)

    async def retry(self, queue_id: str) -> Optional[QueueItem]:
        """
        Retry a failed job (move back to pending).

        Args:
            queue_id: Queue item ID

        Returns:
            Updated QueueItem or None if not found/not failed
        """
        if not self._redis:
            raise RuntimeError("Queue manager not connected")

        item = await self.get_item(queue_id)
        if not item:
            logger.warning(f"Cannot retry: queue item {queue_id} not found")
            return None

        if item.status != QueueItemStatus.FAILED:
            logger.warning(f"Cannot retry: queue item {queue_id} is not failed")
            return None

        # Remove from failed set
        await self._redis.zrem(self.FAILED_KEY, queue_id)

        # Reset status
        item.status = QueueItemStatus.PENDING
        item.started_at = None
        item.completed_at = None
        item.error = None
        item.run_id = None

        await self._update_item(item)

        # Re-add to pending queue (at the front for immediate retry)
        await self._redis.rpush(self.PENDING_KEY, queue_id)

        # Calculate new position
        item.position = 1  # First in queue (at tail = next to be processed)

        await self._publish_event("retried", item)

        logger.info(f"Retried {queue_id} for job {item.job_id}")
        return item

    async def cancel(self, queue_id: str) -> bool:
        """
        Cancel a pending job.

        Args:
            queue_id: Queue item ID

        Returns:
            True if cancelled, False if not found or not pending
        """
        if not self._redis:
            raise RuntimeError("Queue manager not connected")

        item = await self.get_item(queue_id)
        if not item:
            logger.warning(f"Cannot cancel: queue item {queue_id} not found")
            return False

        if item.status != QueueItemStatus.PENDING:
            logger.warning(f"Cannot cancel: queue item {queue_id} is not pending")
            return False

        # Remove from pending queue
        await self._redis.lrem(self.PENDING_KEY, 1, queue_id)

        # Update status
        item.status = QueueItemStatus.CANCELLED
        item.completed_at = datetime.utcnow()
        item.position = 0
        await self._update_item(item)

        await self._publish_event("cancelled", item)

        logger.info(f"Cancelled {queue_id} for job {item.job_id}")
        return True

    async def dismiss_failed(self, queue_id: str) -> bool:
        """
        Dismiss a failed job (remove from failed list without retry).

        Args:
            queue_id: Queue item ID

        Returns:
            True if dismissed, False if not found or not failed
        """
        if not self._redis:
            raise RuntimeError("Queue manager not connected")

        item = await self.get_item(queue_id)
        if not item:
            return False

        if item.status != QueueItemStatus.FAILED:
            return False

        # Remove from failed set
        await self._redis.zrem(self.FAILED_KEY, queue_id)

        # Move to history as failed
        await self._redis.lpush(self.HISTORY_KEY, queue_id)
        await self._redis.ltrim(self.HISTORY_KEY, 0, self.HISTORY_LIMIT - 1)

        await self._publish_event("dismissed", item)

        logger.info(f"Dismissed failed {queue_id}")
        return True

    async def link_run_id(self, queue_id: str, run_id: str) -> None:
        """
        Link a run_id to a queue item (when execution starts).

        Args:
            queue_id: Queue item ID
            run_id: Pipeline run ID
        """
        if not self._redis:
            return

        item = await self.get_item(queue_id)
        if item:
            item.run_id = run_id
            await self._update_item(item)
            await self._publish_event("updated", item)

    async def get_item(self, queue_id: str) -> Optional[QueueItem]:
        """
        Get queue item by ID.

        Args:
            queue_id: Queue item ID

        Returns:
            QueueItem or None if not found
        """
        if not self._redis:
            return None

        data = await self._redis.hgetall(f"{self.ITEM_PREFIX}{queue_id}")
        if not data:
            return None

        return QueueItem.from_dict(queue_id, data)

    async def get_item_by_job_id(self, job_id: str) -> Optional[QueueItem]:
        """
        Find queue item by job_id.

        Searches pending, running, and failed sets.

        Args:
            job_id: MongoDB job _id

        Returns:
            QueueItem or None if not found
        """
        if not self._redis:
            return None

        # Check running first (most likely to be queried)
        running_ids = await self._redis.smembers(self.RUNNING_KEY)
        for queue_id in running_ids:
            item = await self.get_item(queue_id)
            if item and item.job_id == job_id:
                return item

        # Check pending
        pending_ids = await self._redis.lrange(self.PENDING_KEY, 0, -1)
        for i, queue_id in enumerate(reversed(pending_ids)):
            item = await self.get_item(queue_id)
            if item and item.job_id == job_id:
                item.position = i + 1
                return item

        # Check failed
        failed_ids = await self._redis.zrange(self.FAILED_KEY, 0, -1)
        for queue_id in failed_ids:
            item = await self.get_item(queue_id)
            if item and item.job_id == job_id:
                return item

        return None

    async def get_state(self, pending_limit: int = 10) -> QueueState:
        """
        Get full queue state for WebSocket clients.

        Args:
            pending_limit: Max pending items to return (default 10)

        Returns:
            QueueState with all queue information
        """
        if not self._redis:
            return QueueState(stats={
                "total_pending": 0,
                "total_running": 0,
                "total_failed": 0,
                "total_completed_today": 0,
            })

        # Get pending (first N items, ordered by position)
        # LRANGE returns newest first (LPUSH order), we want oldest first
        pending_ids = await self._redis.lrange(self.PENDING_KEY, -pending_limit, -1)
        pending_ids.reverse()  # Now oldest first
        total_pending = await self._redis.llen(self.PENDING_KEY)

        pending = []
        for i, queue_id in enumerate(pending_ids):
            item = await self.get_item(queue_id)
            if item:
                # Position is 1-indexed from the front of the queue
                item.position = total_pending - len(pending_ids) + i + 1
                pending.append(item)

        # Get running
        running_ids = await self._redis.smembers(self.RUNNING_KEY)
        running = []
        for queue_id in running_ids:
            item = await self.get_item(queue_id)
            if item:
                running.append(item)

        # Get failed (most recent 20)
        failed_ids = await self._redis.zrange(self.FAILED_KEY, 0, 19, desc=True)
        failed = []
        for queue_id in failed_ids:
            item = await self.get_item(queue_id)
            if item:
                failed.append(item)

        # Get history (last 20 completed)
        history_ids = await self._redis.lrange(self.HISTORY_KEY, 0, 19)
        history = []
        for queue_id in history_ids:
            item = await self.get_item(queue_id)
            if item:
                history.append(item)

        # Calculate stats
        total_failed = await self._redis.zcard(self.FAILED_KEY)
        completed_today = await self._count_completed_today()

        return QueueState(
            pending=pending,
            running=running,
            failed=failed,
            history=history,
            stats={
                "total_pending": total_pending,
                "total_running": len(running),
                "total_failed": total_failed,
                "total_completed_today": completed_today,
            }
        )

    async def subscribe(
        self,
        callback: Callable[[Dict], Coroutine[Any, Any, None]]
    ) -> None:
        """
        Subscribe to queue events.

        Args:
            callback: Async function to call on events
        """
        self._subscribers.append(callback)

    def unsubscribe(
        self,
        callback: Callable[[Dict], Coroutine[Any, Any, None]]
    ) -> None:
        """
        Unsubscribe from queue events.

        Args:
            callback: Previously registered callback
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def _publish_event(self, action: str, item: QueueItem) -> None:
        """
        Publish queue event to all subscribers.

        Args:
            action: Event action (added, started, completed, failed, etc.)
            item: Queue item involved
        """
        event = {
            "action": action,
            "item": item.to_dict(),
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Publish to Redis pub/sub for multi-instance support
        if self._redis:
            try:
                await self._redis.publish(
                    self.EVENTS_CHANNEL,
                    json.dumps(event)
                )
            except Exception as e:
                logger.warning(f"Failed to publish to Redis pub/sub: {e}")

        # Call local subscribers
        for callback in self._subscribers:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Subscriber callback error: {e}")

    async def _update_item(self, item: QueueItem) -> None:
        """
        Update item in Redis.

        Args:
            item: QueueItem to update
        """
        if self._redis:
            await self._redis.hset(
                f"{self.ITEM_PREFIX}{item.queue_id}",
                mapping=item.to_redis_hash()
            )

    async def _count_completed_today(self) -> int:
        """
        Count jobs completed today.

        Returns:
            Number of jobs completed since midnight UTC
        """
        if not self._redis:
            return 0

        today = date.today()
        count = 0

        # Check history list
        history_ids = await self._redis.lrange(self.HISTORY_KEY, 0, -1)
        for queue_id in history_ids:
            item = await self.get_item(queue_id)
            if item and item.completed_at:
                if item.completed_at.date() == today:
                    count += 1
                else:
                    # History is ordered, so once we hit older items, stop
                    break

        return count

    async def restore_interrupted_runs(self) -> List[QueueItem]:
        """
        Restore any runs that were interrupted (in running state after restart).

        Moves interrupted runs back to pending queue.

        Returns:
            List of restored items
        """
        if not self._redis:
            return []

        restored = []
        running_ids = await self._redis.smembers(self.RUNNING_KEY)

        for queue_id in running_ids:
            item = await self.get_item(queue_id)
            if item:
                # Move back to pending
                await self._redis.srem(self.RUNNING_KEY, queue_id)
                item.status = QueueItemStatus.PENDING
                item.started_at = None
                item.run_id = None
                await self._update_item(item)
                await self._redis.rpush(self.PENDING_KEY, queue_id)
                restored.append(item)
                logger.info(f"Restored interrupted run {queue_id} for job {item.job_id}")

        return restored

    async def cleanup_stale_items(self, max_age_minutes: int = 60) -> Dict[str, int]:
        """
        Clean up stale/orphaned queue items.

        Removes:
        1. Pending items older than max_age_minutes that haven't started
        2. Queue IDs in pending list that have no corresponding item data
        3. Queue IDs in running set that have no corresponding item data

        Args:
            max_age_minutes: Maximum age for pending items before cleanup

        Returns:
            Dict with cleanup statistics
        """
        if not self._redis:
            return {"error": "Not connected to Redis"}

        stats = {
            "stale_pending_removed": 0,
            "orphan_pending_removed": 0,
            "orphan_running_removed": 0,
            "total_cleaned": 0,
        }

        from datetime import timedelta
        cutoff_time = datetime.utcnow() - timedelta(minutes=max_age_minutes)

        # Clean up pending queue
        pending_ids = await self._redis.lrange(self.PENDING_KEY, 0, -1)
        for queue_id in pending_ids:
            item = await self.get_item(queue_id)

            if not item:
                # Orphan: queue_id in list but no item data
                await self._redis.lrem(self.PENDING_KEY, 1, queue_id)
                stats["orphan_pending_removed"] += 1
                logger.info(f"Removed orphan pending queue_id: {queue_id}")
            elif item.status == QueueItemStatus.PENDING and item.created_at < cutoff_time:
                # Stale: pending for too long without being picked up
                await self._redis.lrem(self.PENDING_KEY, 1, queue_id)
                # Mark as failed with timeout reason
                item.status = QueueItemStatus.FAILED
                item.error = f"Stale: pending for over {max_age_minutes} minutes"
                item.completed_at = datetime.utcnow()
                await self._update_item(item)
                # Add to failed set for visibility
                await self._redis.zadd(
                    self.FAILED_KEY,
                    {queue_id: item.completed_at.timestamp()}
                )
                await self._publish_event("failed", item)
                stats["stale_pending_removed"] += 1
                logger.info(f"Removed stale pending {queue_id} for job {item.job_id} (created: {item.created_at})")
            elif item.status != QueueItemStatus.PENDING:
                # Item in pending list but status is not pending (completed/failed/etc)
                await self._redis.lrem(self.PENDING_KEY, 1, queue_id)
                stats["orphan_pending_removed"] += 1
                logger.info(f"Removed completed item from pending list: {queue_id} (status: {item.status})")

        # Clean up running set
        running_ids = await self._redis.smembers(self.RUNNING_KEY)
        for queue_id in running_ids:
            item = await self.get_item(queue_id)
            if not item:
                # Orphan: queue_id in set but no item data
                await self._redis.srem(self.RUNNING_KEY, queue_id)
                stats["orphan_running_removed"] += 1
                logger.info(f"Removed orphan running queue_id: {queue_id}")

        stats["total_cleaned"] = (
            stats["stale_pending_removed"] +
            stats["orphan_pending_removed"] +
            stats["orphan_running_removed"]
        )

        if stats["total_cleaned"] > 0:
            logger.info(f"Queue cleanup completed: {stats}")

        return stats

    async def clear_all(self) -> Dict[str, int]:
        """
        Clear all queue data (for admin/maintenance use).

        Removes all items from pending, running, failed, and history.

        Returns:
            Dict with counts of items removed from each queue
        """
        if not self._redis:
            return {"error": "Not connected to Redis"}

        stats = {
            "pending_cleared": 0,
            "running_cleared": 0,
            "failed_cleared": 0,
            "history_cleared": 0,
            "items_deleted": 0,
        }

        # Get all queue_ids before clearing
        pending_ids = await self._redis.lrange(self.PENDING_KEY, 0, -1)
        running_ids = await self._redis.smembers(self.RUNNING_KEY)
        failed_ids = await self._redis.zrange(self.FAILED_KEY, 0, -1)
        history_ids = await self._redis.lrange(self.HISTORY_KEY, 0, -1)

        # Clear lists/sets
        if pending_ids:
            await self._redis.delete(self.PENDING_KEY)
            stats["pending_cleared"] = len(pending_ids)

        if running_ids:
            await self._redis.delete(self.RUNNING_KEY)
            stats["running_cleared"] = len(running_ids)

        if failed_ids:
            await self._redis.delete(self.FAILED_KEY)
            stats["failed_cleared"] = len(failed_ids)

        if history_ids:
            await self._redis.delete(self.HISTORY_KEY)
            stats["history_cleared"] = len(history_ids)

        # Delete all item hashes
        all_queue_ids = set(pending_ids) | running_ids | set(failed_ids) | set(history_ids)
        for queue_id in all_queue_ids:
            key = f"{self.ITEM_PREFIX}{queue_id}"
            deleted = await self._redis.delete(key)
            if deleted:
                stats["items_deleted"] += 1

        logger.warning(f"Queue cleared by admin: {stats}")

        return stats
