"""Tests for CodexResearchTransport Langfuse instrumentation."""

from __future__ import annotations

from types import SimpleNamespace

from src.preenrich.research_transport import CodexResearchTransport
from src.preenrich.types import StepConfig


class _FakeSpan:
    def __init__(self):
        self.updated = None
        self.ended = False


class _FakeTracer:
    """Mimics the PreenrichTracingSession handle used by transports."""

    def __init__(self):
        self.trace = object()  # truthy sentinel — transport checks `getattr(tracer, "trace", None)`
        self.substage_calls = []
        self.ended_spans = []

    def start_substage_span(self, stage_name, substage, metadata):
        span = _FakeSpan()
        self.substage_calls.append(
            {"stage_name": stage_name, "substage": substage, "metadata": metadata, "span": span}
        )
        return span

    def end_span(self, span, *, output=None):
        self.ended_spans.append({"span": span, "output": output})


def _unsupported_config() -> StepConfig:
    # transport="none" forces `is_live_configured()` False, the easy
    # early-return path that must still emit an end-span.
    return StepConfig(provider="codex", primary_model="gpt-5.2", transport="none")


def test_invoke_json_emits_span_for_unsupported_transport():
    transport = CodexResearchTransport(_unsupported_config())
    tracer = _FakeTracer()

    result = transport.invoke_json(
        prompt="hello",
        job_id="job-1",
        tracer=tracer,
        stage_name="research_enrichment",
        substage="company",
        trace_metadata={"candidate_rank": 2},
    )

    assert result.success is False
    assert len(tracer.substage_calls) == 1
    call = tracer.substage_calls[0]
    assert call["stage_name"] == "research_enrichment"
    assert call["substage"] == "research.company"
    assert call["metadata"]["provider"] == "codex"
    assert call["metadata"]["transport"] == "none"
    assert call["metadata"]["prompt_length"] == 5
    assert call["metadata"]["prompt"] == "hello"
    assert call["metadata"]["candidate_rank"] == 2

    assert len(tracer.ended_spans) == 1
    ended = tracer.ended_spans[0]
    assert ended["output"]["outcome"] == "unsupported_transport"
    assert ended["output"]["success"] is False
    assert ended["output"]["schema_valid"] is None
    assert ended["output"]["error_class"] == "unsupported_transport"


def test_invoke_json_classifies_subprocess_timeout(monkeypatch):
    transport = CodexResearchTransport(
        StepConfig(provider="codex", primary_model="gpt-5.2", transport="codex_web_search")
    )
    tracer = _FakeTracer()

    fake_proc = SimpleNamespace(returncode=1, stdout="", stderr="", timed_out=True)

    def _fake_run(**kwargs):
        return fake_proc

    monkeypatch.setattr(
        "src.preenrich.research_transport._run_monitored_codex_subprocess",
        _fake_run,
    )

    result = transport.invoke_json(
        prompt="p",
        job_id="job-2",
        tracer=tracer,
        stage_name="research_enrichment",
        substage="role",
    )

    assert result.success is False
    assert tracer.ended_spans[0]["output"]["outcome"] == "error_timeout"
    assert tracer.ended_spans[0]["output"]["schema_valid"] is None


def test_invoke_json_classifies_missing_json(monkeypatch):
    transport = CodexResearchTransport(
        StepConfig(provider="codex", primary_model="gpt-5.2", transport="codex_web_search")
    )
    tracer = _FakeTracer()

    fake_proc = SimpleNamespace(returncode=0, stdout="no-json-here", stderr="", timed_out=False)
    monkeypatch.setattr(
        "src.preenrich.research_transport._run_monitored_codex_subprocess",
        lambda **kwargs: fake_proc,
    )
    monkeypatch.setattr(
        "src.preenrich.research_transport._extract_json_from_stdout",
        lambda _s: "",
    )

    result = transport.invoke_json(
        prompt="p",
        job_id="job-3",
        tracer=tracer,
        stage_name="research_enrichment",
        substage="company",
    )

    assert result.success is False
    assert tracer.ended_spans[0]["output"]["outcome"] == "error_no_json"


def test_invoke_json_classifies_success(monkeypatch):
    transport = CodexResearchTransport(
        StepConfig(provider="codex", primary_model="gpt-5.2", transport="codex_web_search")
    )
    tracer = _FakeTracer()

    fake_proc = SimpleNamespace(
        returncode=0, stdout='{"ok": true}', stderr="", timed_out=False
    )
    monkeypatch.setattr(
        "src.preenrich.research_transport._run_monitored_codex_subprocess",
        lambda **kwargs: fake_proc,
    )
    monkeypatch.setattr(
        "src.preenrich.research_transport._extract_json_from_stdout",
        lambda _s: '{"ok": true}',
    )
    monkeypatch.setattr(
        "src.preenrich.research_transport.parse_llm_json",
        lambda s: {"ok": True},
    )

    result = transport.invoke_json(
        prompt="p",
        job_id="job-4",
        tracer=tracer,
        stage_name="research_enrichment",
        substage="application_merge",
    )

    assert result.success is True
    assert tracer.ended_spans[0]["output"]["outcome"] == "success"
    assert tracer.ended_spans[0]["output"]["schema_valid"] is True


def test_invoke_json_tolerates_missing_tracer(monkeypatch):
    transport = CodexResearchTransport(_unsupported_config())

    # No tracer passed → no crash, no spans required.
    result = transport.invoke_json(prompt="p", job_id="job-5")
    assert result.success is False
