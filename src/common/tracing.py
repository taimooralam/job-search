"""
Local tracing helpers.

This module intentionally keeps a lightweight local trace context only.
External tracing integration has been removed.
"""

from __future__ import annotations

import functools
from contextlib import contextmanager
from dataclasses import dataclass
from threading import local
from typing import Any, Callable, Dict, Generator, Optional, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

_trace_context = local()


@dataclass
class TraceMetadata:
    """Metadata for a local trace context."""

    run_id: str
    job_id: Optional[str] = None
    layer: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


def is_tracing_enabled() -> bool:
    """External tracing is disabled."""
    return False


def get_current_trace_context() -> Optional[TraceMetadata]:
    """Get the current trace context from thread-local storage."""
    return getattr(_trace_context, "metadata", None)


def set_trace_context(metadata: Optional[TraceMetadata]) -> None:
    """Set the current trace context."""
    _trace_context.metadata = metadata


class TracingContext:
    """Context manager for local trace metadata propagation."""

    def __init__(
        self,
        run_id: str,
        job_id: Optional[str] = None,
        project: Optional[str] = None,
        tags: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.run_id = run_id
        self.job_id = job_id
        self.project = project
        self.tags = tags or []
        self.extra_metadata = metadata or {}
        self._trace_url: Optional[str] = None
        self._previous_context: Optional[TraceMetadata] = None

    def __enter__(self) -> "TracingContext":
        self._previous_context = get_current_trace_context()
        set_trace_context(
            TraceMetadata(
                run_id=self.run_id,
                job_id=self.job_id,
                extra=self.extra_metadata,
            )
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        set_trace_context(self._previous_context)

    @property
    def trace_url(self) -> Optional[str]:
        """External trace URLs are no longer generated."""
        return self._trace_url

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the local context."""
        self.extra_metadata[key] = value


@contextmanager
def trace_span(
    name: str,
    metadata: Optional[Dict[str, Any]] = None,
    run_type: str = "tool",
) -> Generator[Dict[str, Any], None, None]:
    """No-op span helper that still collects local outputs."""
    del name, metadata, run_type
    span_data: Dict[str, Any] = {}
    yield span_data


def traced(
    name: Optional[str] = None,
    run_type: str = "chain",
    metadata: Optional[Dict[str, Any]] = None,
) -> Callable[[F], F]:
    """Decorator that wraps a function in a local no-op span."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with trace_span(name or func.__name__, metadata, run_type):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


class LayerTrace:
    """Container for layer outputs."""

    def __init__(self):
        self.outputs: Dict[str, Any] = {}

    def add_output(self, key: str, value: Any) -> None:
        self.outputs[key] = value


class LayerTracer:
    """Helper class for layer-scoped local trace metadata."""

    def __init__(self, layer_name: str, operation: str):
        self.layer_name = layer_name
        self.operation = operation

    @contextmanager
    def trace_layer(
        self,
        state: Dict[str, Any],
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Generator["LayerTrace", None, None]:
        del extra_metadata
        context = get_current_trace_context()
        if context is not None:
            context.layer = self.layer_name

        layer_trace = LayerTrace()
        with trace_span(
            f"{self.layer_name}:{self.operation}",
            metadata={
                "layer": self.layer_name,
                "operation": self.operation,
                "job_id": state.get("job_id"),
                "run_id": state.get("run_id"),
            },
            run_type="chain",
        ) as span:
            try:
                yield layer_trace
                span.update(layer_trace.outputs)
            except Exception as exc:
                layer_trace.add_output("error", str(exc))
                span.update(layer_trace.outputs)
                raise


def get_trace_url_for_run(run_id: str, project: Optional[str] = None) -> Optional[str]:
    """External trace URLs are no longer available."""
    del run_id, project
    return None


def log_trace_info(run_id: str, job_id: Optional[str] = None) -> None:
    """No-op retained for compatibility."""
    del run_id, job_id
