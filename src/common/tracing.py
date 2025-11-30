"""
Distributed Tracing Module (Gap OB-3).

Provides LangSmith integration for distributed tracing of the job intelligence pipeline.
Enables trace visualization, debugging, and performance analysis across all layers.

Features:
- Automatic LangChain tracing via LANGCHAIN_TRACING_V2
- Custom run metadata (job_id, run_id, layer)
- Manual span creation for non-LLM operations
- Trace context propagation across layers
- Graceful degradation when LangSmith unavailable

Usage:
    # In workflow.py
    with TracingContext(run_id="run_123", job_id="job_456") as trace:
        # All LangChain calls within this block are traced
        result = app.invoke(initial_state)

    # In layer code (manual span)
    with trace_span("scrape_company_page", {"url": url}):
        data = scraper.fetch(url)

Environment Variables:
    LANGCHAIN_TRACING_V2: "true" to enable tracing (default: true)
    LANGCHAIN_API_KEY or LANGSMITH_API_KEY: LangSmith API key
    LANGCHAIN_PROJECT: Project name in LangSmith (default: job-intelligence-pipeline)
"""

import os
import functools
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Generator, Optional, TypeVar
from threading import local

# Type variable for decorated functions
F = TypeVar('F', bound=Callable[..., Any])

# Thread-local storage for trace context
_trace_context = local()

# Try to import LangSmith
try:
    from langsmith import Client as LangSmithClient
    from langsmith.run_trees import RunTree
    from langsmith import traceable
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    LangSmithClient = None
    RunTree = None
    traceable = None


@dataclass
class TraceMetadata:
    """Metadata for a trace run."""
    run_id: str
    job_id: Optional[str] = None
    layer: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


def is_tracing_enabled() -> bool:
    """
    Check if tracing is enabled.

    Returns:
        True if LANGCHAIN_TRACING_V2 is true and API key is configured
    """
    tracing_v2 = os.getenv("LANGCHAIN_TRACING_V2", "true").lower() == "true"
    api_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
    return bool(tracing_v2 and api_key and LANGSMITH_AVAILABLE)


def get_langsmith_client() -> Optional["LangSmithClient"]:
    """
    Get LangSmith client if available and configured.

    Returns:
        LangSmithClient instance or None if not available
    """
    if not is_tracing_enabled():
        return None

    try:
        api_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
        return LangSmithClient(api_key=api_key)
    except Exception:
        return None


def get_current_trace_context() -> Optional[TraceMetadata]:
    """
    Get the current trace context from thread-local storage.

    Returns:
        TraceMetadata if in a trace context, None otherwise
    """
    return getattr(_trace_context, 'metadata', None)


def set_trace_context(metadata: Optional[TraceMetadata]) -> None:
    """
    Set the trace context in thread-local storage.

    Args:
        metadata: TraceMetadata to set, or None to clear
    """
    _trace_context.metadata = metadata


class TracingContext:
    """
    Context manager for distributed tracing of pipeline runs.

    Wraps a pipeline execution with LangSmith tracing and metadata.
    All LangChain operations within the context are automatically traced.

    Usage:
        with TracingContext(run_id="run_123", job_id="job_456") as trace:
            result = pipeline.run(...)

        # Access trace URL after completion
        print(f"Trace: {trace.trace_url}")
    """

    def __init__(
        self,
        run_id: str,
        job_id: Optional[str] = None,
        project: Optional[str] = None,
        tags: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize tracing context.

        Args:
            run_id: Unique identifier for this pipeline run
            job_id: Optional job identifier
            project: LangSmith project name (defaults to LANGCHAIN_PROJECT env var)
            tags: Optional list of tags for the trace
            metadata: Optional extra metadata to attach to the trace
        """
        self.run_id = run_id
        self.job_id = job_id
        self.project = project or os.getenv("LANGCHAIN_PROJECT", "job-intelligence-pipeline")
        self.tags = tags or []
        self.extra_metadata = metadata or {}

        self._run_tree: Optional["RunTree"] = None
        self._start_time: Optional[datetime] = None
        self._trace_url: Optional[str] = None
        self._previous_context: Optional[TraceMetadata] = None

    def __enter__(self) -> "TracingContext":
        """Start tracing context."""
        self._start_time = datetime.utcnow()

        # Save previous context and set new one
        self._previous_context = get_current_trace_context()
        set_trace_context(TraceMetadata(
            run_id=self.run_id,
            job_id=self.job_id,
            extra=self.extra_metadata,
        ))

        # Configure LangChain environment for this run
        os.environ["LANGCHAIN_PROJECT"] = self.project

        # Set run metadata in environment for LangChain to pick up
        if self.run_id:
            os.environ["LANGCHAIN_RUN_ID"] = self.run_id

        if is_tracing_enabled() and RunTree is not None:
            try:
                # Create a run tree for this pipeline execution
                self._run_tree = RunTree(
                    name=f"pipeline_run_{self.job_id or self.run_id}",
                    run_type="chain",
                    project_name=self.project,
                    tags=self.tags + [f"job:{self.job_id}"] if self.job_id else self.tags,
                    extra={
                        "metadata": {
                            "run_id": self.run_id,
                            "job_id": self.job_id,
                            **self.extra_metadata,
                        }
                    },
                )
            except Exception:
                # Silently fail if RunTree creation fails
                self._run_tree = None

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """End tracing context."""
        # Restore previous context
        set_trace_context(self._previous_context)

        # Clean up environment
        if "LANGCHAIN_RUN_ID" in os.environ:
            del os.environ["LANGCHAIN_RUN_ID"]

        if self._run_tree is not None:
            try:
                if exc_type is not None:
                    # Mark as error if exception occurred
                    self._run_tree.end(error=str(exc_val))
                else:
                    self._run_tree.end()

                # Post the trace
                self._run_tree.post()

                # Get trace URL
                self._trace_url = self._get_trace_url()
            except Exception:
                # Silently fail if trace posting fails
                pass

    def _get_trace_url(self) -> Optional[str]:
        """Get the LangSmith trace URL."""
        if self._run_tree is None:
            return None

        try:
            # Construct trace URL from project and run ID
            project_encoded = self.project.replace(" ", "%20")
            return f"https://smith.langchain.com/o/default/projects/p/{project_encoded}?selectedRunId={self._run_tree.id}"
        except Exception:
            return None

    @property
    def trace_url(self) -> Optional[str]:
        """Get the LangSmith trace URL (available after context exit)."""
        return self._trace_url

    def add_metadata(self, key: str, value: Any) -> None:
        """
        Add metadata to the current trace.

        Args:
            key: Metadata key
            value: Metadata value
        """
        self.extra_metadata[key] = value
        if self._run_tree is not None:
            try:
                self._run_tree.extra["metadata"][key] = value
            except Exception:
                pass


@contextmanager
def trace_span(
    name: str,
    metadata: Optional[Dict[str, Any]] = None,
    run_type: str = "tool",
) -> Generator[Dict[str, Any], None, None]:
    """
    Create a manual trace span for non-LLM operations.

    Use this to trace custom operations like web scraping, file I/O, etc.

    Usage:
        with trace_span("scrape_company_page", {"url": url}) as span:
            data = scraper.fetch(url)
            span["result_size"] = len(data)

    Args:
        name: Name of the span
        metadata: Optional metadata to attach
        run_type: Type of run (tool, retriever, chain, etc.)

    Yields:
        Dict to collect span outputs
    """
    span_data: Dict[str, Any] = {}
    start_time = datetime.utcnow()

    # Get current trace context
    context = get_current_trace_context()

    if is_tracing_enabled() and RunTree is not None and context is not None:
        try:
            # Create child run
            run_tree = RunTree(
                name=name,
                run_type=run_type,
                project_name=os.getenv("LANGCHAIN_PROJECT", "job-intelligence-pipeline"),
                extra={
                    "metadata": {
                        "run_id": context.run_id,
                        "job_id": context.job_id,
                        "layer": context.layer,
                        **(metadata or {}),
                    }
                },
            )

            try:
                yield span_data
                run_tree.end(outputs=span_data)
            except Exception as e:
                run_tree.end(error=str(e))
                raise
            finally:
                try:
                    run_tree.post()
                except Exception:
                    pass
        except Exception:
            # Fall back to no-op if tracing fails
            yield span_data
    else:
        # No tracing available, just yield
        yield span_data


def traced(
    name: Optional[str] = None,
    run_type: str = "chain",
    metadata: Optional[Dict[str, Any]] = None,
) -> Callable[[F], F]:
    """
    Decorator to trace a function.

    Usage:
        @traced("process_job_description")
        def process_job(description: str) -> dict:
            # ... processing logic
            return result

    Args:
        name: Name for the span (defaults to function name)
        run_type: Type of run
        metadata: Optional metadata to attach

    Returns:
        Decorated function
    """
    def decorator(func: F) -> F:
        # If LangSmith traceable is available, use it
        if LANGSMITH_AVAILABLE and traceable is not None:
            traced_func = traceable(
                name=name or func.__name__,
                run_type=run_type,
                metadata=metadata,
            )(func)
            return traced_func

        # Otherwise, use our manual tracing
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            span_name = name or func.__name__
            with trace_span(span_name, metadata, run_type):
                return func(*args, **kwargs)
        return wrapper  # type: ignore

    return decorator


class LayerTracer:
    """
    Helper class for tracing pipeline layers.

    Provides consistent tracing for layer entry, exit, and operations.

    Usage:
        tracer = LayerTracer("layer2", "pain_point_miner")

        with tracer.trace_layer(state) as trace:
            result = miner.extract(state)
            trace.add_output("pain_points_count", len(result.get("pain_points", [])))
    """

    def __init__(self, layer_name: str, operation: str):
        """
        Initialize layer tracer.

        Args:
            layer_name: Name of the layer (e.g., "layer2")
            operation: Name of the operation (e.g., "pain_point_miner")
        """
        self.layer_name = layer_name
        self.operation = operation

    @contextmanager
    def trace_layer(
        self,
        state: Dict[str, Any],
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Generator["LayerTrace", None, None]:
        """
        Trace layer execution.

        Args:
            state: Pipeline state
            extra_metadata: Optional extra metadata

        Yields:
            LayerTrace object for adding outputs
        """
        metadata = {
            "layer": self.layer_name,
            "operation": self.operation,
            "job_id": state.get("job_id"),
            "run_id": state.get("run_id"),
            **(extra_metadata or {}),
        }

        # Update current context with layer info
        context = get_current_trace_context()
        if context is not None:
            context.layer = self.layer_name

        layer_trace = LayerTrace()

        with trace_span(
            f"{self.layer_name}:{self.operation}",
            metadata=metadata,
            run_type="chain",
        ) as span:
            try:
                yield layer_trace
                # Add outputs to span
                span.update(layer_trace.outputs)
            except Exception as e:
                layer_trace.add_output("error", str(e))
                span.update(layer_trace.outputs)
                raise


class LayerTrace:
    """Trace object for collecting layer outputs."""

    def __init__(self):
        """Initialize layer trace."""
        self.outputs: Dict[str, Any] = {}

    def add_output(self, key: str, value: Any) -> None:
        """
        Add an output value to the trace.

        Args:
            key: Output key
            value: Output value
        """
        self.outputs[key] = value


# =============================================================================
# Convenience Functions
# =============================================================================

def get_trace_url_for_run(run_id: str, project: Optional[str] = None) -> Optional[str]:
    """
    Get the LangSmith trace URL for a run ID.

    Args:
        run_id: Run identifier
        project: Project name (defaults to LANGCHAIN_PROJECT env var)

    Returns:
        Trace URL or None if not available
    """
    if not is_tracing_enabled():
        return None

    project = project or os.getenv("LANGCHAIN_PROJECT", "job-intelligence-pipeline")
    project_encoded = project.replace(" ", "%20")
    return f"https://smith.langchain.com/o/default/projects/p/{project_encoded}?search={run_id}"


def log_trace_info(run_id: str, job_id: Optional[str] = None) -> None:
    """
    Log trace information for debugging.

    Args:
        run_id: Run identifier
        job_id: Optional job identifier
    """
    if is_tracing_enabled():
        trace_url = get_trace_url_for_run(run_id)
        print(f"[Tracing] Run: {run_id}")
        print(f"[Tracing] Job: {job_id or 'N/A'}")
        print(f"[Tracing] URL: {trace_url}")
    else:
        print(f"[Tracing] Disabled (Run: {run_id})")
