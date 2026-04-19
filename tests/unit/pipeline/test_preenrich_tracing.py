"""Tests for iteration-4 preenrich Langfuse tracing helpers."""

from __future__ import annotations

from src.pipeline import tracing


class _FakeObservation:
    def __init__(self):
        self.updated = []
        self.ended = False
        self.trace_updates = []

    def start_observation(self, **kwargs):
        return _FakeObservation()

    def update(self, **kwargs):
        self.updated.append(kwargs)

    def update_trace(self, **kwargs):
        self.trace_updates.append(kwargs)

    def end(self):
        self.ended = True


class _FakeLangfuse:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.events = []

    def create_trace_id(self, seed: str):
        return f"trace:{seed}"

    def start_observation(self, **kwargs):
        self.last_observation = _FakeObservation()
        self.last_observation_kwargs = kwargs
        return self.last_observation

    def create_event(self, **kwargs):
        self.events.append(kwargs)

    def get_trace_url(self, trace_id: str):
        return f"https://langfuse.example/{trace_id}"

    def flush(self):
        return None


def test_sanitize_langfuse_payload_redacts_prompts_by_default(monkeypatch):
    monkeypatch.delenv("LANGFUSE_CAPTURE_FULL_PROMPTS", raising=False)

    payload = tracing._sanitize_langfuse_payload(
        {
            "job_id": "job-1",
            "prompt": "x" * 200,
            "nested": {"system_prompt": "hello world"},
        }
    )

    assert payload["job_id"] == "job-1"
    assert payload["prompt"]["captured"] is False
    assert payload["prompt"]["length"] == 200
    assert payload["nested"]["system_prompt"]["captured"] is False


def test_sanitize_langfuse_payload_keeps_prompts_when_enabled(monkeypatch):
    monkeypatch.setenv("LANGFUSE_CAPTURE_FULL_PROMPTS", "true")

    payload = tracing._sanitize_langfuse_payload({"prompt": "full prompt"})

    assert payload == {"prompt": "full prompt"}


def test_preenrich_tracing_session_exposes_trace_refs(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "secret")
    monkeypatch.setattr(tracing, "Langfuse", _FakeLangfuse)

    session = tracing.PreenrichTracingSession(
        run_id="preenrich:jd_structure:123",
        session_id="job:abc",
        metadata={"job_id": "job-1", "prompt": "sensitive prompt"},
    )

    assert session.enabled is True
    assert session.trace_id == "trace:preenrich:jd_structure:123"
    assert session.trace_url == "https://langfuse.example/trace:preenrich:jd_structure:123"

    span = session.start_stage_span("jd_structure", {"attempt_token": "tok"})
    session.end_span(span, output={"status": "completed"})
    session.record_event("scout.preenrich.retry", {"reason": "snapshot_changed"})
    session.complete(output={"status": "completed"})


def test_emit_standalone_event_returns_trace_refs(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "secret")
    monkeypatch.setattr(tracing, "Langfuse", _FakeLangfuse)

    result = tracing.emit_standalone_event(
        name="scout.preenrich.enqueue_root",
        session_id="job:abc",
        metadata={"prompt": "secret", "job_id": "job-1"},
    )

    assert result["trace_id"] is not None
    assert result["trace_url"] == f"https://langfuse.example/{result['trace_id']}"
