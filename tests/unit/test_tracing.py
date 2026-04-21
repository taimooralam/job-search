"""Unit tests for the local tracing helpers."""

import pytest

from src.common.tracing import (
    LayerTracer,
    TraceMetadata,
    TracingContext,
    get_current_trace_context,
    get_trace_url_for_run,
    is_tracing_enabled,
    set_trace_context,
    trace_span,
    traced,
)


def test_tracing_disabled():
    assert is_tracing_enabled() is False


def test_trace_metadata_fields():
    metadata = TraceMetadata(run_id="run_123", job_id="job_456", layer="layer2", extra={"k": "v"})
    assert metadata.run_id == "run_123"
    assert metadata.job_id == "job_456"
    assert metadata.layer == "layer2"
    assert metadata.extra == {"k": "v"}


def test_set_and_clear_trace_context():
    metadata = TraceMetadata(run_id="run_123", job_id="job_456")
    set_trace_context(metadata)
    assert get_current_trace_context() == metadata
    set_trace_context(None)
    assert get_current_trace_context() is None


def test_tracing_context_sets_and_restores_context():
    set_trace_context(TraceMetadata(run_id="outer"))
    with TracingContext(run_id="inner", job_id="job_123") as ctx:
        current = get_current_trace_context()
        assert current is not None
        assert current.run_id == "inner"
        assert current.job_id == "job_123"
        ctx.add_metadata("custom", "value")
        assert ctx.extra_metadata["custom"] == "value"
        assert ctx.trace_url is None
    restored = get_current_trace_context()
    assert restored is not None
    assert restored.run_id == "outer"
    set_trace_context(None)


def test_trace_span_collects_outputs():
    with trace_span("test") as span:
        span["value"] = 42
        assert span["value"] == 42


def test_trace_span_propagates_exceptions():
    with pytest.raises(RuntimeError):
        with trace_span("boom"):
            raise RuntimeError("expected")


def test_traced_decorator_preserves_name_and_behavior():
    @traced("test_func")
    def my_function(x: int) -> int:
        return x * 2

    assert my_function.__name__ == "my_function"
    assert my_function(5) == 10


def test_layer_tracer_updates_context_and_outputs():
    tracer = LayerTracer("layer3", "company_researcher")
    state = {"job_id": "job_123", "run_id": "run_456"}

    with TracingContext(run_id="run_456", job_id="job_123"):
        with tracer.trace_layer(state) as trace:
            trace.add_output("companies_found", 3)
            current = get_current_trace_context()
            assert current is not None
            assert current.layer == "layer3"
            assert trace.outputs["companies_found"] == 3


def test_layer_tracer_records_error_before_reraising():
    tracer = LayerTracer("layer5", "people_mapper")
    state = {"job_id": "job_123", "run_id": "run_456"}

    with pytest.raises(RuntimeError):
        with tracer.trace_layer(state) as trace:
            trace.add_output("contacts_found", 0)
            raise RuntimeError("API error")


def test_trace_url_lookup_returns_none():
    assert get_trace_url_for_run("run_123") is None
