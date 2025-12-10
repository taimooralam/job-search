"""
Base class for button-triggered pipeline operation services.

Each operation (Structure JD, Research, Generate CV, etc.) extends this
to provide consistent execution, cost tracking, and persistence.
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Generator, Optional
import logging
import time
import uuid

from src.common.model_tiers import (
    ModelTier,
    get_model_for_operation,
    get_tier_cost_estimate,
)

logger = logging.getLogger(__name__)


@dataclass
class OperationResult:
    """Result from an operation execution."""

    success: bool
    run_id: str
    operation: str
    data: Dict[str, Any]
    cost_usd: float
    duration_ms: int
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    model_used: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "run_id": self.run_id,
            "operation": self.operation,
            "data": self.data,
            "cost_usd": self.cost_usd,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model_used": self.model_used,
            "timestamp": self.timestamp.isoformat(),
        }


class OperationService(ABC):
    """Base class for button-triggered operations."""

    operation_name: str  # Override in subclass

    @abstractmethod
    async def execute(
        self,
        job_id: str,
        tier: ModelTier,
        **kwargs,
    ) -> OperationResult:
        """
        Execute the operation. Override in subclass.

        Args:
            job_id: The job ID to process
            tier: Model tier for quality/cost selection
            **kwargs: Operation-specific arguments

        Returns:
            OperationResult with success status, data, and cost info
        """
        pass

    def get_model(self, tier: ModelTier) -> str:
        """
        Get appropriate model for this operation based on tier.

        Args:
            tier: The model tier

        Returns:
            Model name string
        """
        return get_model_for_operation(tier, self.operation_name)

    def create_run_id(self) -> str:
        """
        Generate unique run ID for tracking.

        Returns:
            Unique run ID string in format "op_{operation}_{random_hex}"
        """
        return f"op_{self.operation_name}_{uuid.uuid4().hex[:12]}"

    def estimate_cost(
        self, tier: ModelTier, input_tokens: int, output_tokens: int
    ) -> float:
        """
        Estimate cost for the operation.

        Args:
            tier: The model tier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD
        """
        return get_tier_cost_estimate(tier, input_tokens, output_tokens)

    def create_success_result(
        self,
        run_id: str,
        data: Dict[str, Any],
        cost_usd: float,
        duration_ms: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model_used: Optional[str] = None,
    ) -> OperationResult:
        """
        Create a successful operation result.

        Args:
            run_id: The operation run ID
            data: Result data dictionary
            cost_usd: Cost in USD
            duration_ms: Duration in milliseconds
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens used
            model_used: Model name that was used

        Returns:
            OperationResult with success=True
        """
        return OperationResult(
            success=True,
            run_id=run_id,
            operation=self.operation_name,
            data=data,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            error=None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_used=model_used,
        )

    def create_error_result(
        self,
        run_id: str,
        error: str,
        duration_ms: int,
        cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> OperationResult:
        """
        Create a failed operation result.

        Args:
            run_id: The operation run ID
            error: Error message
            duration_ms: Duration in milliseconds
            cost_usd: Cost in USD (may be non-zero if error occurred after LLM call)
            input_tokens: Number of input tokens used before failure
            output_tokens: Number of output tokens used before failure

        Returns:
            OperationResult with success=False
        """
        return OperationResult(
            success=False,
            run_id=run_id,
            operation=self.operation_name,
            data={},
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            error=error,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def persist_run(
        self,
        result: OperationResult,
        job_id: str,
        tier: ModelTier,
        db_client: Optional[Any] = None,
    ) -> bool:
        """
        Persist operation run details to MongoDB for tracking.

        Creates a record in the operation_runs collection with full
        execution metadata for cost tracking and auditing.

        Args:
            result: The OperationResult from execution
            job_id: The job ID that was processed
            tier: The model tier that was used
            db_client: Optional database client. If not provided,
                       uses the global DatabaseClient singleton.

        Returns:
            True if persisted successfully, False otherwise
        """
        try:
            # Import here to avoid circular dependency
            from src.common.database import DatabaseClient

            client = db_client if db_client else DatabaseClient()
            collection = client.db["operation_runs"]

            doc = {
                "run_id": result.run_id,
                "operation": result.operation,
                "job_id": job_id,
                "tier": tier.value,
                "success": result.success,
                "cost_usd": result.cost_usd,
                "duration_ms": result.duration_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "model_used": result.model_used,
                "error": result.error,
                "timestamp": result.timestamp,
                "created_at": datetime.utcnow(),
            }

            collection.insert_one(doc)
            logger.info(
                f"Persisted operation run: {result.run_id} "
                f"({result.operation}, success={result.success})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to persist operation run: {e}")
            return False

    @contextmanager
    def timed_execution(self) -> Generator["OperationTimer", None, None]:
        """
        Context manager for timing operation execution.

        Yields an OperationTimer that tracks start time and
        provides duration_ms when exiting the context.

        Usage:
            with self.timed_execution() as timer:
                # do work
                pass
            duration_ms = timer.duration_ms

        Yields:
            OperationTimer instance for accessing duration
        """
        timer = OperationTimer()
        try:
            yield timer
        finally:
            timer.stop()


@dataclass
class OperationTimer:
    """Timer utility for tracking operation duration."""

    start_time: float = field(default_factory=time.perf_counter)
    end_time: Optional[float] = None

    @property
    def duration_ms(self) -> int:
        """
        Get duration in milliseconds.

        Returns:
            Duration in milliseconds, or 0 if not stopped yet
        """
        if self.end_time is None:
            return int((time.perf_counter() - self.start_time) * 1000)
        return int((self.end_time - self.start_time) * 1000)

    @property
    def duration_seconds(self) -> float:
        """
        Get duration in seconds.

        Returns:
            Duration in seconds, or 0 if not stopped yet
        """
        return self.duration_ms / 1000.0

    def stop(self) -> int:
        """
        Stop the timer and return duration in milliseconds.

        Returns:
            Duration in milliseconds
        """
        self.end_time = time.perf_counter()
        return self.duration_ms
