"""
Queue Data Models

Defines the data structures for queue items and their statuses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class QueueItemStatus(str, Enum):
    """Status values for queue items."""

    PENDING = "pending"      # Waiting in queue
    RUNNING = "running"      # Currently executing
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"        # Failed (needs manual retry)
    CANCELLED = "cancelled"  # User cancelled


@dataclass
class QueueItem:
    """
    Represents a job in the queue.

    Links a queue entry to a MongoDB job and tracks its execution status.
    """

    queue_id: str               # Unique queue entry ID (e.g., "q_abc123def456")
    job_id: str                 # MongoDB job _id
    job_title: str              # For display without DB lookup
    company: str                # For display
    status: QueueItemStatus     # Current status
    created_at: datetime        # When queued
    operation: str = "full_pipeline"  # Operation type
    processing_tier: str = "auto"     # Tier: auto, gold, silver, bronze
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    run_id: Optional[str] = None      # Links to RunState when running
    position: int = 0                  # Queue position (1-indexed, 0 = not in queue)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "queue_id": self.queue_id,
            "job_id": self.job_id,
            "job_title": self.job_title,
            "company": self.company,
            "status": self.status.value,
            "operation": self.operation,
            "processing_tier": self.processing_tier,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "run_id": self.run_id,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, queue_id: str, data: Dict[str, str]) -> "QueueItem":
        """
        Create QueueItem from Redis hash data.

        Args:
            queue_id: The queue item ID
            data: Dictionary from Redis HGETALL

        Returns:
            QueueItem instance
        """
        def parse_datetime(value: str) -> Optional[datetime]:
            """Parse ISO datetime string, return None if empty."""
            if not value:
                return None
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None

        return cls(
            queue_id=queue_id,
            job_id=data.get("job_id", ""),
            job_title=data.get("job_title", "Unknown"),
            company=data.get("company", "Unknown"),
            status=QueueItemStatus(data.get("status", "pending")),
            operation=data.get("operation", "full_pipeline"),
            processing_tier=data.get("processing_tier", "auto"),
            created_at=parse_datetime(data.get("created_at", "")) or datetime.utcnow(),
            started_at=parse_datetime(data.get("started_at", "")),
            completed_at=parse_datetime(data.get("completed_at", "")),
            error=data.get("error") or None,
            run_id=data.get("run_id") or None,
            position=int(data.get("position", 0)),
        )

    def to_redis_hash(self) -> Dict[str, str]:
        """
        Convert to Redis hash format.

        All values are strings for Redis HSET.
        """
        return {
            "job_id": self.job_id,
            "job_title": self.job_title,
            "company": self.company,
            "status": self.status.value,
            "operation": self.operation,
            "processing_tier": self.processing_tier,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "started_at": self.started_at.isoformat() if self.started_at else "",
            "completed_at": self.completed_at.isoformat() if self.completed_at else "",
            "error": self.error or "",
            "run_id": self.run_id or "",
            "position": str(self.position),
        }


@dataclass
class QueueState:
    """
    Complete queue state for WebSocket broadcast.

    Contains all information needed to render the queue UI.
    """

    pending: list = field(default_factory=list)     # QueueItems waiting
    running: list = field(default_factory=list)     # QueueItems executing
    failed: list = field(default_factory=list)      # QueueItems that failed
    history: list = field(default_factory=list)     # Recent completed
    stats: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pending": [
                item.to_dict() if isinstance(item, QueueItem) else item
                for item in self.pending
            ],
            "running": [
                item.to_dict() if isinstance(item, QueueItem) else item
                for item in self.running
            ],
            "failed": [
                item.to_dict() if isinstance(item, QueueItem) else item
                for item in self.failed
            ],
            "history": [
                item.to_dict() if isinstance(item, QueueItem) else item
                for item in self.history
            ],
            "stats": self.stats,
        }
