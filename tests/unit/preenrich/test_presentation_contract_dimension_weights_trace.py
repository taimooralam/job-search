from bson import ObjectId

from src.preenrich.stages.presentation_contract import PresentationContractStage
from src.preenrich.types import StageContext, StepConfig


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


def _ctx() -> StageContext:
    job_id = ObjectId()
    return StageContext(
        job_doc={
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "title": "Principal AI Architect",
            "company": "Acme",
            "description": "Lead architecture for production AI systems.",
            "pre_enrichment": {
                "outputs": {
                    "jd_facts": {"merged_view": {"title": "Principal AI Architect", "seniority_level": "principal", "top_keywords": ["architecture"], "responsibilities": ["Lead architecture"], "qualifications": ["Systems"], "ideal_candidate_profile": {"identity_statement": "Principal architect"}}},
                    "classification": {"primary_role_category": "ai_architect", "tone_family": "executive", "ai_taxonomy": {"intensity": "significant"}},
                    "research_enrichment": {"status": "completed", "company_profile": {"canonical_name": "Acme", "canonical_domain": "acme.example.com"}, "role_profile": {"status": "completed", "mandate": ["Lead architecture"]}, "application_profile": {"portal_family": "greenhouse"}},
                    "stakeholder_surface": {"status": "completed", "evaluator_coverage_target": ["recruiter", "hiring_manager"], "evaluator_coverage": [], "real_stakeholders": [], "inferred_stakeholder_personas": []},
                    "pain_point_intelligence": {"status": "completed", "proof_map": [{"pain_id": "p1", "preferred_proof_type": "architecture"}]},
                    "job_inference": {"semantic_role_model": {"role_mandate": "Own architecture."}},
                }
            },
        },
        jd_checksum="sha256:jd",
        company_checksum="sha256:company",
        input_snapshot_id="sha256:snapshot",
        attempt_number=1,
        stage_name="presentation_contract",
        config=StepConfig(
            provider="codex",
            primary_model="gpt-5.4",
            fallback_provider="none",
            transport="none",
            fallback_transport="none",
            allow_repo_context=False,
        ),
    )


def test_presentation_contract_dimension_weights_trace_is_metadata_first(monkeypatch):
    ctx = _ctx()
    ctx.tracer = _CapturingTracer()

    result = PresentationContractStage().run(ctx)

    assert result.stage_output["experience_dimension_weights"]["status"] in {
        "completed",
        "partial",
        "inferred_only",
    }
    assert any(item["substage"] == "dimension_weights" for item in ctx.tracer.started)
    dimension_end = next(item for item in ctx.tracer.ended if item["span"]["substage"] == "dimension_weights")
    output = dimension_end["output"]
    assert "overall_weights" not in output
    assert "rationale" not in output
    assert output["overall_weight_sum"] == 100


def test_presentation_contract_dimension_weights_emits_fail_open_event_when_flag_disabled(monkeypatch):
    monkeypatch.delenv("PREENRICH_PRESENTATION_CONTRACT_DIMENSION_WEIGHTS_ENABLED", raising=False)
    ctx = _ctx()
    ctx.tracer = _CapturingTracer()

    PresentationContractStage().run(ctx)

    assert any(name == "scout.preenrich.presentation_contract.dimension_weights.fail_open" for name, _ in ctx.tracer.events)
