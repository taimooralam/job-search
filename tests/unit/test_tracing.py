"""
Unit tests for src/common/tracing.py
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from src.common.tracing import (
    is_tracing_enabled,
    get_current_trace_context,
    set_trace_context,
    TraceMetadata,
    TracingContext,
    trace_span,
    traced,
    LayerTracer,
    get_trace_url_for_run,
    LANGSMITH_AVAILABLE,
)


class TestTracingEnabled:
    """Tests for is_tracing_enabled function."""

    def test_enabled_when_all_configured(self, monkeypatch):
        """Should return True when tracing is enabled and API key is set."""
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "test-key")

        # Result depends on whether langsmith is installed
        if LANGSMITH_AVAILABLE:
            assert is_tracing_enabled() is True
        else:
            assert is_tracing_enabled() is False

    def test_disabled_when_tracing_false(self, monkeypatch):
        """Should return False when LANGCHAIN_TRACING_V2 is false."""
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "test-key")

        assert is_tracing_enabled() is False

    def test_disabled_when_no_api_key(self, monkeypatch):
        """Should return False when API key is missing."""
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
        monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

        assert is_tracing_enabled() is False

    def test_uses_langsmith_api_key_fallback(self, monkeypatch):
        """Should check LANGSMITH_API_KEY as fallback."""
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
        monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

        # Result depends on whether langsmith is installed
        if LANGSMITH_AVAILABLE:
            assert is_tracing_enabled() is True
        else:
            assert is_tracing_enabled() is False


class TestTraceMetadata:
    """Tests for TraceMetadata dataclass."""

    def test_required_fields(self):
        """Should require run_id."""
        metadata = TraceMetadata(run_id="run_123")
        assert metadata.run_id == "run_123"
        assert metadata.job_id is None
        assert metadata.layer is None
        assert metadata.extra is None

    def test_all_fields(self):
        """Should store all fields."""
        metadata = TraceMetadata(
            run_id="run_123",
            job_id="job_456",
            layer="layer2",
            extra={"key": "value"},
        )
        assert metadata.run_id == "run_123"
        assert metadata.job_id == "job_456"
        assert metadata.layer == "layer2"
        assert metadata.extra == {"key": "value"}


class TestTraceContext:
    """Tests for trace context management."""

    def test_get_current_trace_context_returns_none_by_default(self):
        """Should return None when no context is set."""
        set_trace_context(None)  # Reset
        assert get_current_trace_context() is None

    def test_set_and_get_trace_context(self):
        """Should set and get trace context."""
        metadata = TraceMetadata(run_id="run_123", job_id="job_456")
        set_trace_context(metadata)

        result = get_current_trace_context()
        assert result is not None
        assert result.run_id == "run_123"
        assert result.job_id == "job_456"

        # Clean up
        set_trace_context(None)

    def test_clear_trace_context(self):
        """Should clear context when set to None."""
        metadata = TraceMetadata(run_id="run_123")
        set_trace_context(metadata)
        assert get_current_trace_context() is not None

        set_trace_context(None)
        assert get_current_trace_context() is None


class TestTracingContext:
    """Tests for TracingContext context manager."""

    def test_context_sets_and_clears_metadata(self):
        """Should set context on enter and clear on exit."""
        set_trace_context(None)  # Reset

        with TracingContext(run_id="run_123", job_id="job_456"):
            context = get_current_trace_context()
            assert context is not None
            assert context.run_id == "run_123"
            assert context.job_id == "job_456"

        # Context should be cleared after exit
        assert get_current_trace_context() is None

    def test_context_restores_previous_context(self):
        """Should restore previous context on exit."""
        outer_metadata = TraceMetadata(run_id="outer_run")
        set_trace_context(outer_metadata)

        with TracingContext(run_id="inner_run"):
            context = get_current_trace_context()
            assert context.run_id == "inner_run"

        # Should restore outer context
        restored = get_current_trace_context()
        assert restored is not None
        assert restored.run_id == "outer_run"

        # Clean up
        set_trace_context(None)

    def test_context_sets_project_env(self, monkeypatch):
        """Should set LANGCHAIN_PROJECT environment variable."""
        with TracingContext(run_id="run_123", project="test-project"):
            assert os.environ.get("LANGCHAIN_PROJECT") == "test-project"

    def test_context_handles_exception(self):
        """Should handle exceptions gracefully."""
        set_trace_context(None)

        with pytest.raises(ValueError):
            with TracingContext(run_id="run_123"):
                raise ValueError("Test error")

        # Context should still be cleared
        assert get_current_trace_context() is None

    def test_add_metadata(self):
        """Should add metadata during context."""
        with TracingContext(run_id="run_123") as ctx:
            ctx.add_metadata("custom_key", "custom_value")
            assert ctx.extra_metadata["custom_key"] == "custom_value"


class TestTraceSpan:
    """Tests for trace_span context manager."""

    def test_span_yields_dict(self):
        """Should yield a dict for collecting outputs."""
        with trace_span("test_operation") as span:
            assert isinstance(span, dict)
            span["result"] = "success"

    def test_span_collects_outputs(self):
        """Should collect outputs in the span dict."""
        with trace_span("test_operation", {"input": "value"}) as span:
            span["output1"] = "result1"
            span["output2"] = 42

        # After exit, span should have our values
        # (though they're local to the with block)

    def test_span_handles_exception(self):
        """Should handle exceptions gracefully."""
        with pytest.raises(RuntimeError):
            with trace_span("failing_operation"):
                raise RuntimeError("Operation failed")

    def test_span_with_no_context(self):
        """Should work without trace context."""
        set_trace_context(None)

        with trace_span("standalone_operation") as span:
            span["result"] = "works"

        # No exception should be raised


class TestTracedDecorator:
    """Tests for traced decorator."""

    def test_decorated_function_executes(self):
        """Should execute the decorated function."""
        @traced("test_func")
        def my_function(x: int) -> int:
            return x * 2

        result = my_function(5)
        assert result == 10

    def test_decorated_function_preserves_name(self):
        """Should preserve function name."""
        @traced("custom_name")
        def original_func():
            pass

        # The wrapper should have the original name (via functools.wraps)
        assert original_func.__name__ == "original_func"

    def test_decorated_function_handles_exception(self):
        """Should propagate exceptions."""
        @traced("failing_func")
        def failing_function():
            raise ValueError("Expected error")

        with pytest.raises(ValueError, match="Expected error"):
            failing_function()

    def test_decorator_with_no_name(self):
        """Should use function name when name not provided."""
        @traced()
        def auto_named_func():
            return "result"

        result = auto_named_func()
        assert result == "result"


class TestLayerTracer:
    """Tests for LayerTracer helper class."""

    def test_initialization(self):
        """Should initialize with layer name and operation."""
        tracer = LayerTracer("layer2", "pain_point_miner")
        assert tracer.layer_name == "layer2"
        assert tracer.operation == "pain_point_miner"

    def test_trace_layer_context(self):
        """Should provide trace context for layer."""
        tracer = LayerTracer("layer3", "company_researcher")
        state = {"job_id": "job_123", "run_id": "run_456"}

        with tracer.trace_layer(state) as trace:
            assert hasattr(trace, "outputs")
            assert isinstance(trace.outputs, dict)
            trace.add_output("companies_found", 5)

    def test_trace_layer_collects_outputs(self):
        """Should collect outputs added via add_output."""
        tracer = LayerTracer("layer4", "opportunity_mapper")
        state = {"job_id": "job_123", "run_id": "run_456"}

        with tracer.trace_layer(state) as trace:
            trace.add_output("fit_score", 85)
            trace.add_output("fit_category", "strong")

            assert trace.outputs["fit_score"] == 85
            assert trace.outputs["fit_category"] == "strong"

    def test_trace_layer_handles_exception(self):
        """Should handle exceptions and include error in outputs."""
        tracer = LayerTracer("layer5", "people_mapper")
        state = {"job_id": "job_123", "run_id": "run_456"}

        with pytest.raises(RuntimeError):
            with tracer.trace_layer(state) as trace:
                trace.add_output("contacts_found", 0)
                raise RuntimeError("API error")


class TestGetTraceUrl:
    """Tests for get_trace_url_for_run function."""

    def test_returns_none_when_tracing_disabled(self, monkeypatch):
        """Should return None when tracing is disabled."""
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
        assert get_trace_url_for_run("run_123") is None

    def test_returns_url_when_tracing_enabled(self, monkeypatch):
        """Should return URL when tracing is enabled."""
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "test-key")

        if LANGSMITH_AVAILABLE:
            url = get_trace_url_for_run("run_123", project="test-project")
            assert url is not None
            assert "run_123" in url
            assert "test-project" in url

    def test_encodes_project_name(self, monkeypatch):
        """Should URL-encode project name with spaces."""
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        monkeypatch.setenv("LANGCHAIN_API_KEY", "test-key")

        if LANGSMITH_AVAILABLE:
            url = get_trace_url_for_run("run_123", project="my project")
            assert url is not None
            assert "my%20project" in url


class TestTracingIntegration:
    """Integration tests for tracing components."""

    def test_nested_contexts_and_spans(self):
        """Should handle nested contexts and spans."""
        set_trace_context(None)

        with TracingContext(run_id="outer_run", job_id="job_A"):
            outer_context = get_current_trace_context()
            assert outer_context.run_id == "outer_run"

            with trace_span("outer_span") as outer_span:
                outer_span["step"] = 1

                with TracingContext(run_id="inner_run", job_id="job_B"):
                    inner_context = get_current_trace_context()
                    assert inner_context.run_id == "inner_run"

                    with trace_span("inner_span") as inner_span:
                        inner_span["step"] = 2

                # Should restore outer context
                restored = get_current_trace_context()
                assert restored.run_id == "outer_run"

        # Should be cleared
        assert get_current_trace_context() is None

    def test_layer_tracer_with_context(self):
        """Should work with layer tracer inside context."""
        tracer = LayerTracer("layer2", "test_op")
        state = {"job_id": "job_123", "run_id": "run_456"}

        with TracingContext(run_id="run_456", job_id="job_123"):
            with tracer.trace_layer(state) as trace:
                trace.add_output("result", "success")
                context = get_current_trace_context()
                assert context.layer == "layer2"
