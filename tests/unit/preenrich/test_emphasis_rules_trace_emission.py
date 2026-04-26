import pytest

from src.preenrich.blueprint_models import TruthConstrainedEmphasisRulesDoc
from src.preenrich.stages.presentation_contract import (
    PresentationContractStage,
    _emit_emphasis_consistency_events,
)
from tests.unit.preenrich._emphasis_rules_test_data import (
    build_stage_context,
    clone,
    cv_shape_expectations_payload,
    dimension_weights_payload,
    document_expectations_payload,
    emphasis_rules_payload,
    ideal_candidate_payload,
)


class _CapturingTracer:
    def __init__(self) -> None:
        self.trace_id = "trace:presentation"
        self.trace_url = "https://langfuse.example/trace:presentation"
        self.trace = object()
        self.enabled = True
        self.started: list[dict] = []
        self.ended: list[dict] = []
        self.events: list[tuple[str, dict]] = []

    def start_substage_span(self, stage_name: str, substage: str, metadata: dict):
        span = {"stage_name": stage_name, "substage": substage, "metadata": metadata}
        self.started.append(span)
        return span

    def end_span(self, span, *, output=None) -> None:
        self.ended.append({"span": span, "output": output})

    def record_event(self, name: str, metadata: dict) -> None:
        self.events.append((name, metadata))

    def complete(self, *, output=None) -> None:
        return None


def _install_stage_llm_mock(
    monkeypatch,
    *,
    ideal_payload: dict | None = None,
    dimension_payload: dict | None = None,
    emphasis_payloads: list[dict] | None = None,
) -> None:
    remaining_emphasis = list(emphasis_payloads or [{"truth_constrained_emphasis_rules": emphasis_rules_payload()}])

    def _fake_invoke(*, prompt: str, model: str, job_id: str, substage: str | None = None, **kwargs):
        tracer = kwargs.get("tracer")
        stage_name = kwargs.get("stage_name") or "presentation_contract"
        repair_span = None
        if tracer is not None and isinstance(substage, str) and substage.endswith(".schema_repair"):
            repair_span = tracer.start_substage_span(stage_name, substage, {"job_id": job_id})
        if substage == "document_expectations":
            payload = {"document_expectations": document_expectations_payload()}
        elif substage == "cv_shape_expectations":
            payload = {"cv_shape_expectations": cv_shape_expectations_payload()}
        elif substage == "ideal_candidate":
            payload = {
                "ideal_candidate_presentation_model": ideal_payload or ideal_candidate_payload()
            }
        elif substage == "dimension_weights":
            payload = {
                "experience_dimension_weights": dimension_payload or dimension_weights_payload()
            }
        elif substage in {"emphasis_rules", "emphasis_rules.schema_repair"}:
            payload = remaining_emphasis.pop(0)
        else:
            pytest.fail(f"Unexpected prompt: {substage} {prompt[:120]}")
        if repair_span is not None:
            tracer.end_span(repair_span, output={"status": "completed"})
        return payload, {"provider": "codex", "model": model}

    monkeypatch.setattr("src.preenrich.stages.presentation_contract._invoke_codex_json_traced", _fake_invoke)


def test_presentation_contract_emphasis_rules_trace_is_metadata_first():
    ctx = build_stage_context()
    ctx.tracer = _CapturingTracer()

    result = PresentationContractStage().run(ctx)

    assert result.stage_output["truth_constrained_emphasis_rules"]["status"] in {
        "completed",
        "partial",
        "inferred_only",
    }
    emphasis_end = next(item for item in ctx.tracer.ended if item["span"]["substage"] == "emphasis_rules")
    output = emphasis_end["output"]
    assert "global_rules" not in output
    assert "forbidden_claim_patterns" not in output
    assert "forbidden_claim_pattern_examples" not in output
    assert output["forbidden_claim_patterns_count"] >= 2


def test_presentation_contract_emphasis_rules_emits_fail_open_event_when_flag_disabled(monkeypatch):
    monkeypatch.delenv("PREENRICH_PRESENTATION_CONTRACT_EMPHASIS_RULES_ENABLED", raising=False)
    ctx = build_stage_context()
    ctx.tracer = _CapturingTracer()

    PresentationContractStage().run(ctx)

    assert any(
        name == "scout.preenrich.presentation_contract.emphasis_rules.fail_open"
        for name, _ in ctx.tracer.events
    )


def test_presentation_contract_emphasis_rules_schema_repair_span_only_when_triggered(monkeypatch):
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_DIMENSION_WEIGHTS_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_EMPHASIS_RULES_ENABLED", "true")
    invalid_payload = emphasis_rules_payload()
    invalid_payload["credibility_ladder_rules"][0]["fallback_rule_id"] = "missing_rule"
    invalid = {"truth_constrained_emphasis_rules": invalid_payload}
    valid = {"truth_constrained_emphasis_rules": emphasis_rules_payload()}
    _install_stage_llm_mock(monkeypatch, emphasis_payloads=[invalid, valid])
    ctx = build_stage_context()
    ctx.tracer = _CapturingTracer()

    PresentationContractStage().run(ctx)

    started = [item["substage"] for item in ctx.tracer.started]
    assert "emphasis_rules.schema_repair" in started


def test_presentation_contract_emphasis_rules_rule_conflict_span_only_when_triggered(monkeypatch):
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_DIMENSION_WEIGHTS_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_EMPHASIS_RULES_ENABLED", "true")
    payload = emphasis_rules_payload()
    payload["allowed_if_evidenced"].append(clone(payload["allowed_if_evidenced"][0]))
    _install_stage_llm_mock(monkeypatch, emphasis_payloads=[{"truth_constrained_emphasis_rules": payload}])
    ctx = build_stage_context()
    ctx.tracer = _CapturingTracer()

    PresentationContractStage().run(ctx)

    started = [item["substage"] for item in ctx.tracer.started]
    assert "emphasis_rules.rule_conflict_resolution" in started


def test_emit_emphasis_consistency_events_records_suppressed_downgraded_and_retained():
    ctx = build_stage_context()
    ctx.tracer = _CapturingTracer()
    payload = emphasis_rules_payload()
    payload["debug_context"]["conflict_resolution_log"] = [
        {
            "rule_id": "title_rule",
            "topic_family": "title_inflation",
            "applies_to_kind": "global",
            "applies_to": "global",
            "conflict_source": "title_strategy",
            "resolution": "retained",
            "note": "retained by title envelope",
        },
        {
            "rule_id": "dimension_rule",
            "topic_family": "leadership_scope",
            "applies_to_kind": "dimension",
            "applies_to": "leadership_enablement",
            "conflict_source": "dimension_weights",
            "resolution": "downgraded",
            "note": "dimension clamped",
        },
        {
            "rule_id": "ai_rule",
            "topic_family": "ai_claims",
            "applies_to_kind": "proof",
            "applies_to": "ai",
            "conflict_source": "ai_section_policy",
            "resolution": "suppressed",
            "note": "suppressed by AI policy",
        },
    ]
    doc = TruthConstrainedEmphasisRulesDoc.model_validate(payload)

    _emit_emphasis_consistency_events(ctx, doc)

    emitted = [
        metadata["resolution"]
        for name, metadata in ctx.tracer.events
        if name == "scout.preenrich.presentation_contract.consistency.emphasis_rules"
    ]
    assert emitted == ["retained", "downgraded", "suppressed"]
