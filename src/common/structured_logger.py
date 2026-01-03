"""
Structured JSON logger for pipeline events.

Emits JSON-formatted log events for:
- Layer start/complete/error tracking
- Pipeline status updates
- Real-time frontend updates via SSE

Usage:
    logger = StructuredLogger(job_id="abc123")
    logger.layer_start(2, "pain_point_miner")
    # ... do work ...
    logger.layer_complete(2, "pain_point_miner", duration_ms=4500, metadata={"points": 5})
"""

import json
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class EventType(str, Enum):
    """Standard pipeline event types."""
    LAYER_START = "layer_start"
    LAYER_COMPLETE = "layer_complete"
    LAYER_ERROR = "layer_error"
    LAYER_SKIP = "layer_skip"
    PIPELINE_START = "pipeline_start"
    PIPELINE_COMPLETE = "pipeline_complete"
    LLM_CALL_START = "llm_call_start"
    LLM_CALL_COMPLETE = "llm_call_complete"
    LLM_CALL_ERROR = "llm_call_error"
    LLM_CALL_FALLBACK = "llm_call_fallback"
    # Phase 0 Extension: CV generation granular logging
    SUBPHASE_START = "subphase_start"
    SUBPHASE_COMPLETE = "subphase_complete"
    DECISION_POINT = "decision_point"
    VALIDATION_RESULT = "validation_result"


class LayerStatus(str, Enum):
    """Layer execution status."""
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"
    PARTIAL = "partial"


@dataclass
class LogEvent:
    """Structured log event with all optional fields."""
    timestamp: str
    event: str
    job_id: str
    layer: Optional[int] = None
    layer_name: Optional[str] = None
    status: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    # LLM-specific fields for backend attribution
    backend: Optional[str] = None       # "claude_cli" or "langchain"
    model: Optional[str] = None         # Model ID used (e.g., "claude-sonnet-4-5-20250929")
    tier: Optional[str] = None          # Tier level: "low", "middle", "high"
    cost_usd: Optional[float] = None    # Estimated cost in USD
    step_name: Optional[str] = None     # Pipeline step name (e.g., "grader")

    def to_json(self) -> str:
        """Convert to JSON string, excluding None values."""
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(data)


class StructuredLogger:
    """
    Structured JSON logger for pipeline events.

    Emits JSON lines to stdout for parsing by the runner service,
    which forwards events to the frontend via SSE.
    """

    # Layer name mapping for consistent naming
    LAYER_NAMES = {
        1: "jd_extractor",
        2: "pain_point_miner",
        2.5: "star_selector",
        3: "company_researcher",
        3.5: "role_researcher",
        4: "opportunity_mapper",
        5: "people_mapper",
        6: "cv_generator",
        7: "publisher",
    }

    def __init__(self, job_id: str, enabled: bool = True):
        """
        Initialize structured logger.

        Args:
            job_id: Job ID for correlation
            enabled: Whether to emit events (can disable for testing)
        """
        self.job_id = job_id
        self.enabled = enabled
        self._layer_start_times: Dict[int, float] = {}

    def _emit(self, event: LogEvent) -> None:
        """Emit a log event as JSON line."""
        if self.enabled:
            print(event.to_json(), file=sys.stdout, flush=True)

    def _now(self) -> str:
        """Get current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _get_layer_name(self, layer: int) -> str:
        """Get standard layer name from number."""
        return self.LAYER_NAMES.get(layer, f"layer_{layer}")

    def emit(
        self,
        event: str,
        layer: Optional[int] = None,
        layer_name: Optional[str] = None,
        status: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        backend: Optional[str] = None,
        model: Optional[str] = None,
        tier: Optional[str] = None,
        cost_usd: Optional[float] = None,
        step_name: Optional[str] = None,
    ) -> None:
        """
        Emit a custom log event.

        Args:
            event: Event type name
            layer: Layer number
            layer_name: Layer name (auto-derived if not provided)
            status: Execution status
            duration_ms: Duration in milliseconds
            metadata: Additional event metadata
            error: Error message if applicable
            backend: LLM backend used ("claude_cli" or "langchain")
            model: Model ID used
            tier: Tier level ("low", "middle", "high")
            cost_usd: Estimated cost in USD
            step_name: Pipeline step name
        """
        if layer is not None and layer_name is None:
            layer_name = self._get_layer_name(layer)

        log_event = LogEvent(
            timestamp=self._now(),
            event=event,
            job_id=self.job_id,
            layer=layer,
            layer_name=layer_name,
            status=status,
            duration_ms=duration_ms,
            metadata=metadata,
            error=error,
            backend=backend,
            model=model,
            tier=tier,
            cost_usd=cost_usd,
            step_name=step_name,
        )
        self._emit(log_event)

    # ===== Convenience Methods =====

    def layer_start(self, layer: int, layer_name: Optional[str] = None) -> None:
        """
        Log layer execution start.

        Args:
            layer: Layer number
            layer_name: Optional override for layer name
        """
        self._layer_start_times[layer] = time.time()
        self.emit(
            event=EventType.LAYER_START.value,
            layer=layer,
            layer_name=layer_name,
        )

    def layer_complete(
        self,
        layer: int,
        layer_name: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log layer execution complete.

        Args:
            layer: Layer number
            layer_name: Optional override for layer name
            duration_ms: Duration (auto-calculated if layer_start was called)
            metadata: Additional metadata (e.g., fit_score, tokens_used)
        """
        if duration_ms is None and layer in self._layer_start_times:
            duration_ms = int((time.time() - self._layer_start_times[layer]) * 1000)
            del self._layer_start_times[layer]

        self.emit(
            event=EventType.LAYER_COMPLETE.value,
            layer=layer,
            layer_name=layer_name,
            status=LayerStatus.SUCCESS.value,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    def layer_error(
        self,
        layer: int,
        error: str,
        layer_name: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log layer execution error.

        Args:
            layer: Layer number
            error: Error message
            layer_name: Optional override for layer name
            duration_ms: Duration (auto-calculated if layer_start was called)
            metadata: Additional context
        """
        if duration_ms is None and layer in self._layer_start_times:
            duration_ms = int((time.time() - self._layer_start_times[layer]) * 1000)
            del self._layer_start_times[layer]

        self.emit(
            event=EventType.LAYER_ERROR.value,
            layer=layer,
            layer_name=layer_name,
            status=LayerStatus.ERROR.value,
            duration_ms=duration_ms,
            error=error,
            metadata=metadata,
        )

    def layer_skip(
        self,
        layer: int,
        reason: str,
        layer_name: Optional[str] = None,
    ) -> None:
        """
        Log layer skipped.

        Args:
            layer: Layer number
            reason: Reason for skipping
            layer_name: Optional override for layer name
        """
        self.emit(
            event=EventType.LAYER_SKIP.value,
            layer=layer,
            layer_name=layer_name,
            status=LayerStatus.SKIPPED.value,
            metadata={"reason": reason},
        )

    def pipeline_start(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log pipeline execution start."""
        self.emit(
            event=EventType.PIPELINE_START.value,
            metadata=metadata,
        )

    def pipeline_complete(
        self,
        status: str = "success",
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log pipeline execution complete.

        Args:
            status: Final status (success, partial, error)
            duration_ms: Total duration
            metadata: Summary metadata
        """
        self.emit(
            event=EventType.PIPELINE_COMPLETE.value,
            status=status,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    # ===== LLM Call Tracking Methods =====

    def emit_llm_call(
        self,
        step_name: str,
        backend: str,
        model: str,
        tier: str,
        status: str,
        duration_ms: Optional[int] = None,
        cost_usd: Optional[float] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emit standardized LLM call event for console display and tracking.

        This method provides a consistent interface for logging all LLM
        invocations across the pipeline, enabling backend attribution
        and cost tracking.

        Args:
            step_name: The pipeline step name (e.g., "grader", "header_generator")
            backend: LLM backend used ("claude_cli" or "langchain")
            model: Model ID used (e.g., "claude-sonnet-4-5-20250929")
            tier: Tier level ("low", "middle", "high")
            status: Call status ("start", "complete", "error", "fallback")
            duration_ms: Duration in milliseconds (for complete/error status)
            cost_usd: Estimated cost in USD (if available)
            error: Error message (for error status)
            metadata: Additional context metadata

        Example:
            >>> logger.emit_llm_call(
            ...     step_name="grader",
            ...     backend="claude_cli",
            ...     model="claude-sonnet-4-5-20250929",
            ...     tier="middle",
            ...     status="complete",
            ...     duration_ms=1500,
            ...     cost_usd=0.05,
            ... )
        """
        # Map status to event type
        event_map = {
            "start": EventType.LLM_CALL_START.value,
            "complete": EventType.LLM_CALL_COMPLETE.value,
            "error": EventType.LLM_CALL_ERROR.value,
            "fallback": EventType.LLM_CALL_FALLBACK.value,
        }
        event = event_map.get(status, EventType.LLM_CALL_COMPLETE.value)

        self.emit(
            event=event,
            status=status,
            duration_ms=duration_ms,
            metadata=metadata,
            error=error,
            backend=backend,
            model=model,
            tier=tier,
            cost_usd=cost_usd,
            step_name=step_name,
        )

    def llm_call_start(
        self,
        step_name: str,
        backend: str,
        model: str,
        tier: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log LLM call start.

        Args:
            step_name: Pipeline step name
            backend: Backend being used ("claude_cli" or "langchain")
            model: Model ID
            tier: Tier level
            metadata: Additional context
        """
        self.emit_llm_call(
            step_name=step_name,
            backend=backend,
            model=model,
            tier=tier,
            status="start",
            metadata=metadata,
        )

    def llm_call_complete(
        self,
        step_name: str,
        backend: str,
        model: str,
        tier: str,
        duration_ms: int,
        cost_usd: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log LLM call completion.

        Args:
            step_name: Pipeline step name
            backend: Backend used
            model: Model ID
            tier: Tier level
            duration_ms: Call duration
            cost_usd: Estimated cost
            metadata: Additional context
        """
        self.emit_llm_call(
            step_name=step_name,
            backend=backend,
            model=model,
            tier=tier,
            status="complete",
            duration_ms=duration_ms,
            cost_usd=cost_usd,
            metadata=metadata,
        )

    def llm_call_error(
        self,
        step_name: str,
        backend: str,
        model: str,
        tier: str,
        error: str,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log LLM call error.

        Args:
            step_name: Pipeline step name
            backend: Backend that failed
            model: Model ID
            tier: Tier level
            error: Error message
            duration_ms: Call duration before failure
            metadata: Additional context
        """
        self.emit_llm_call(
            step_name=step_name,
            backend=backend,
            model=model,
            tier=tier,
            status="error",
            error=error,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    def llm_call_fallback(
        self,
        step_name: str,
        from_backend: str,
        to_backend: str,
        model: str,
        tier: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log LLM backend fallback.

        Args:
            step_name: Pipeline step name
            from_backend: Original backend that failed
            to_backend: Fallback backend being used
            model: Model ID for fallback
            tier: Tier level
            reason: Reason for fallback
            metadata: Additional context
        """
        fallback_metadata = {
            "from_backend": from_backend,
            "to_backend": to_backend,
            "reason": reason,
        }
        if metadata:
            fallback_metadata.update(metadata)

        self.emit_llm_call(
            step_name=step_name,
            backend=to_backend,
            model=model,
            tier=tier,
            status="fallback",
            metadata=fallback_metadata,
        )

    # ===== Error with Traceback =====

    def emit_error_with_traceback(
        self,
        error: Exception,
        context: str,
        layer: Optional[int] = None,
        layer_name: Optional[str] = None,
        include_locals: bool = False,
    ) -> None:
        """
        Emit an error event with the full stack trace for frontend debugging.

        This method captures the complete traceback from an exception and
        formats it for display in the frontend CLI panel.

        Args:
            error: The exception that was raised
            context: Human-readable context (e.g., "during CV generation")
            layer: Optional layer number
            layer_name: Optional layer name
            include_locals: Whether to include local variables (can be verbose)

        Example:
            >>> try:
            ...     risky_operation()
            ... except Exception as e:
            ...     logger.emit_error_with_traceback(e, "during CV generation", layer=6)
        """
        # Format the traceback
        tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
        tb_str = "".join(tb_lines)

        # Build metadata with error details
        metadata = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": tb_str,
            "context": context,
        }

        # Optionally include local variables from the frame
        if include_locals and error.__traceback__:
            try:
                tb = error.__traceback__
                while tb.tb_next:
                    tb = tb.tb_next
                frame_locals = {
                    k: repr(v)[:200]  # Truncate large values
                    for k, v in tb.tb_frame.f_locals.items()
                    if not k.startswith("_") and not callable(v)
                }
                metadata["frame_locals"] = frame_locals
            except Exception:
                pass  # Don't fail if we can't get locals

        # Emit as a layer_error or generic error event
        if layer is not None:
            self.layer_error(
                layer=layer,
                error=f"{type(error).__name__}: {str(error)}",
                layer_name=layer_name,
                metadata=metadata,
            )
        else:
            self.emit(
                event="error",
                error=f"{type(error).__name__}: {str(error)}",
                metadata=metadata,
            )

    def emit_plain_error(
        self,
        message: str,
        traceback_str: Optional[str] = None,
        context: Optional[str] = None,
        layer: Optional[int] = None,
        layer_name: Optional[str] = None,
    ) -> None:
        """
        Emit an error event with optional traceback string.

        Use this when you have a plain error message and traceback string
        (e.g., captured from subprocess stderr).

        Args:
            message: Error message
            traceback_str: Optional formatted traceback string
            context: Human-readable context
            layer: Optional layer number
            layer_name: Optional layer name
        """
        metadata = {}
        if traceback_str:
            metadata["traceback"] = traceback_str
        if context:
            metadata["context"] = context

        if layer is not None:
            self.layer_error(
                layer=layer,
                error=message,
                layer_name=layer_name,
                metadata=metadata if metadata else None,
            )
        else:
            self.emit(
                event="error",
                error=message,
                metadata=metadata if metadata else None,
            )


# ===== Context Manager for Layer Timing =====

class LayerContext:
    """
    Context manager for automatic layer timing.

    Usage:
        with LayerContext(logger, 4, "opportunity_mapper") as ctx:
            # ... do work ...
            ctx.add_metadata("fit_score", 85)
    """

    def __init__(
        self,
        logger: StructuredLogger,
        layer: int,
        layer_name: Optional[str] = None,
    ):
        self.logger = logger
        self.layer = layer
        self.layer_name = layer_name
        self.metadata: Dict[str, Any] = {}
        self._start_time: float = 0

    def __enter__(self) -> "LayerContext":
        self._start_time = time.time()
        self.logger.layer_start(self.layer, self.layer_name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        duration_ms = int((time.time() - self._start_time) * 1000)

        if exc_type is not None:
            # Capture full traceback for frontend display
            tb_lines = traceback.format_exception(exc_type, exc_val, exc_tb)
            tb_str = "".join(tb_lines)

            # Include traceback in metadata
            error_metadata = dict(self.metadata) if self.metadata else {}
            error_metadata["traceback"] = tb_str
            error_metadata["error_type"] = exc_type.__name__ if exc_type else "Unknown"

            self.logger.layer_error(
                self.layer,
                f"{exc_type.__name__}: {str(exc_val)}" if exc_type else str(exc_val),
                self.layer_name,
                duration_ms,
                error_metadata,
            )
            return False  # Re-raise exception

        self.logger.layer_complete(
            self.layer,
            self.layer_name,
            duration_ms,
            self.metadata if self.metadata else None,
        )
        return False

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to be included in completion event."""
        self.metadata[key] = value


# ===== Factory Function =====

def get_structured_logger(job_id: str, enabled: bool = True) -> StructuredLogger:
    """
    Get a structured logger instance.

    Args:
        job_id: Job ID for event correlation
        enabled: Whether to emit events

    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(job_id, enabled)
