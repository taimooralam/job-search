from __future__ import annotations

import pytest
from bson import ObjectId

from src.preenrich.blueprint_models import (
    PainPointIntelligenceDoc,
    build_pain_point_intelligence_compact,
    normalize_pain_point_intelligence_payload,
    pain_input_hash,
)
from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
from src.preenrich.stages.pain_point_intelligence import PainPointIntelligenceStage
from src.preenrich.types import StageContext, StepConfig


class _FakeTracer:
    def __init__(self) -> None:
        self.trace = object()
        self.trace_id = "trace:pain-intel"
        self.trace_url = "https://langfuse.example/trace:pain-intel"
        self.started: list[dict] = []
        self.ended: list[dict] = []
        self.events: list[dict] = []

    def start_substage_span(self, stage_name, substage, metadata):
        span = {"stage_name": stage_name, "substage": substage, "metadata": metadata}
        self.started.append(span)
        return span

    def end_span(self, span, *, output=None):
        self.ended.append({"span": span, "output": output})

    def record_event(self, name, metadata):
        self.events.append({"name": name, "metadata": metadata})


def _ctx(*, research_status: str = "completed") -> StageContext:
    job_id = ObjectId()
    return StageContext(
        job_doc={
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "title": "Principal AI Architect",
            "company": "Acme",
            "description": "Lead production AI architecture, improve delivery reliability, and partner with stakeholders.",
            "pre_enrichment": {
                "outputs": {
                    "jd_facts": {
                        "merged_view": {
                            "title": "Principal AI Architect",
                            "seniority_level": "principal",
                            "responsibilities": [
                                "Lead production AI architecture across product and platform.",
                                "Improve delivery reliability for AI systems.",
                            ],
                            "qualifications": ["Distributed systems", "ML systems"],
                            "implied_pain_points": ["Delivery reliability is under pressure."],
                            "success_metrics": ["Reduce time to production for AI initiatives."],
                            "top_keywords": ["AI", "architecture", "reliability"],
                        }
                    },
                    "classification": {
                        "primary_role_category": "ai_architect",
                        "tone_family": "executive",
                        "ai_taxonomy": {"intensity": "significant"},
                    },
                    "research_enrichment": {
                        "status": research_status,
                        "research_input_hash": "sha256:research",
                        "company_profile": {
                            "identity_confidence": {"score": 0.9, "band": "high", "basis": "official"},
                            "role_relevant_signals": [{"description": "Scaling applied AI delivery."}],
                            "scale_signals": [{"description": "Engineering organization is growing."}],
                            "ai_data_platform_maturity": {"summary": "Platform maturity is increasing."},
                        },
                        "role_profile": {
                            "business_impact": ["Turn AI prototypes into reliable production systems."],
                            "risk_landscape": ["Production reliability risk if architecture ownership stays thin."],
                            "success_metrics": ["Production AI outcomes shipped with clear ownership."],
                            "evaluation_signals": ["Architecture judgment", "Production impact"],
                            "interview_themes": ["System design", "Execution rigor"],
                            "why_now": "AI delivery is scaling across teams.",
                        },
                        "application_profile": {
                            "friction_signals": ["Application flow is conventional but keyword-sensitive."],
                            "portal_family": "greenhouse",
                        },
                        "sources": [
                            {
                                "source_id": "source:role_profile",
                                "url": "https://acme.example.com/jobs/ai-architect",
                                "source_type": "official_job_page",
                                "trust_tier": "primary",
                            }
                        ],
                    },
                    "stakeholder_surface": {
                        "status": "completed",
                        "evaluator_coverage_target": ["recruiter", "hiring_manager", "peer_technical"],
                        "evaluator_coverage": [],
                    },
                    "job_inference": {"semantic_role_model": {"likely_screening_themes": ["platform scale"]}},
                    "cv_guidelines": {
                        "title_guidance": {"bullets": ["Principal AI Architect"]},
                        "identity_guidance": {"bullets": ["Architecture-heavy principal IC role."]},
                        "bullet_theme_guidance": {"bullets": ["Proof of production AI systems."]},
                        "ats_keyword_guidance": {"bullets": ["AI architecture", "reliability"]},
                        "cover_letter_expectations": {"bullets": ["Optional."]},
                    },
                    "application_surface": {"status": "resolved", "application_url": "https://acme.example.com/jobs/ai-architect"},
                }
            },
        },
        jd_checksum="sha256:jd",
        company_checksum="sha256:company",
        input_snapshot_id="sha256:snapshot",
        attempt_number=1,
        stage_name="pain_point_intelligence",
        tracer=_FakeTracer(),
        config=StepConfig(
            provider="codex",
            primary_model="gpt-5.4",
            fallback_provider="none",
            fallback_model="gpt-5.2",
            transport="none",
            fallback_transport="none",
            allow_repo_context=False,
        ),
    )


def test_normalize_pain_point_intelligence_payload_handles_aliases():
    normalized = normalize_pain_point_intelligence_payload(
        {
            "status": "completed",
            "source_scope": "jd_plus_research",
            "pains": [{"id": "p_custom", "category": "technical", "pain": "Production AI architecture is under strain.", "source_ids": ["jd:responsibilities:0"]}],
            "needs": [{"need": "Architect reliable AI delivery.", "source_ids": ["jd:responsibilities:0"]}],
            "risks": [{"risk": "Reliability risk grows.", "source_ids": ["jd:responsibilities:0"]}],
            "success_metrics": [{"metric": "Shipped production AI outcomes.", "source_ids": ["jd:success_metrics:0"]}],
            "proof_map": [{"pain_ref": "p_custom", "proof_type": "architecture", "shape": "Named system ownership.", "sections": ["summary"], "rationale": "Architecture proof is needed."}],
            "search_terms": ["production AI architecture"],
            "unknown_field": {"kept": True},
        }
    )
    assert normalized["pain_points"][0]["pain_id"] == "p_custom"
    assert normalized["strategic_needs"][0]["statement"] == "Architect reliable AI delivery."
    assert normalized["proof_map"][0]["preferred_proof_type"] == "architecture"
    retained = normalized["debug_context"]["richer_output_retained"]
    assert any(item["key"] == "unknown_field" for item in retained)


def test_normalize_pain_point_intelligence_payload_keeps_jd_grounded_product_proper_nouns():
    normalized = normalize_pain_point_intelligence_payload(
        {
            "status": "completed",
            "source_scope": "jd_only",
            "pain_points": [
                {
                    "pain_id": "p_technical_microsoft_stack",
                    "category": "technical",
                    "statement": "The role needs production AI agents across Microsoft 365 and Copilot Studio.",
                    "evidence_refs": ["artifact:jd_excerpt"],
                    "likely_proof_targets": ["architecture"],
                }
            ],
            "strategic_needs": [
                {
                    "category": "technical",
                    "statement": "Build a Microsoft-centered AI automation capability using Copilot Studio and Power Platform.",
                    "evidence_refs": ["artifact:jd_excerpt"],
                }
            ],
            "risks_if_unfilled": [
                {
                    "category": "business",
                    "statement": "Copilot and Power Platform solutions may stay disconnected from the tax workflow.",
                    "evidence_refs": ["artifact:jd_excerpt"],
                }
            ],
            "success_metrics": [
                {
                    "statement": "Copilot and Power Platform solutions are running in production.",
                    "metric_kind": "outcome",
                    "evidence_refs": ["artifact:jd_excerpt"],
                }
            ],
            "proof_map": [
                {
                    "pain_id": "p_technical_microsoft_stack",
                    "preferred_proof_type": "architecture",
                    "preferred_evidence_shape": "Named system ownership on Microsoft 365.",
                    "affected_document_sections": ["summary"],
                    "rationale": "The JD is explicit about the Microsoft stack.",
                }
            ],
            "search_terms": [
                {"term": "Copilot Studio Microsoft 365 production workflow", "intent": "retrieval", "source_basis": "artifact:jd_excerpt"}
            ],
            "evidence": [
                {"claim": "The role builds Copilot and Power Platform solutions across business areas.", "source_ids": ["artifact:jd_excerpt"]}
            ],
            "confidence": {"score": 0.7, "band": "medium", "basis": "jd"},
        },
        jd_excerpt="Build Copilot and Power Platform solutions on Microsoft 365 for the tax landscape.",
    )
    assert normalized["strategic_needs"][0]["statement"].startswith("Build a Microsoft-centered")
    assert normalized["risks_if_unfilled"][0]["statement"].startswith("Copilot and Power Platform")
    assert normalized["success_metrics"][0]["statement"].startswith("Copilot and Power Platform")
    assert normalized["search_terms"][0]["term"].startswith("Copilot Studio Microsoft 365")
    assert normalized["evidence"][0]["claim"].startswith("The role builds Copilot")


def test_pain_point_doc_rejects_orphaned_proof_map():
    with pytest.raises(ValueError, match="proof_map pain_id does not resolve"):
        PainPointIntelligenceDoc.model_validate(
            {
                "job_id": "job-1",
                "level2_job_id": "level2-1",
                "pain_input_hash": "sha256:test",
                "prompt_version": "pain_point_intelligence@v4.2.3",
                "status": "completed",
                "source_scope": "jd_plus_research",
                "pain_points": [],
                "strategic_needs": [],
                "risks_if_unfilled": [],
                "success_metrics": [],
                "proof_map": [
                    {
                        "pain_id": "missing",
                        "preferred_proof_type": "architecture",
                        "preferred_evidence_shape": "Named systems.",
                        "bad_proof_patterns": [],
                        "affected_document_sections": ["summary"],
                        "rationale": "Missing pain reference.",
                        "confidence": {"score": 0.6, "band": "medium", "basis": "test"},
                    }
                ],
                "search_terms": [],
                "unresolved_questions": [],
                "sources": [],
                "evidence": [],
                "confidence": {"score": 0.4, "band": "low", "basis": "test"},
            }
        )


def test_pain_point_stage_happy_path(monkeypatch):
    def _fake_invoke(*, prompt: str, model: str, job_id: str, **_kwargs):
        return (
            {
                "pain_point_intelligence": {
                    "status": "completed",
                    "source_scope": "jd_plus_research",
                    "pain_points": [
                        {
                            "pain_id": "p_technical_12345678",
                            "category": "technical",
                            "statement": "Production AI architecture needs explicit ownership.",
                            "why_now": "AI delivery is scaling across teams.",
                            "source_scope": "jd_plus_research",
                            "evidence_refs": [
                                "artifact:pre_enrichment.outputs.jd_facts.merged_view.responsibilities[0]",
                                "artifact:pre_enrichment.outputs.research_enrichment.role_profile.business_impact[0]",
                            ],
                            "urgency": "medium",
                            "related_stakeholders": ["hiring_manager", "peer_technical"],
                            "likely_proof_targets": ["architecture", "ai"],
                            "confidence": {"score": 0.78, "band": "medium", "basis": "good"},
                        }
                    ],
                    "strategic_needs": [
                        {
                            "category": "business",
                            "statement": "Make AI delivery reliable and repeatable.",
                            "evidence_refs": ["artifact:pre_enrichment.outputs.research_enrichment.role_profile.business_impact[0]"],
                            "confidence": {"score": 0.7, "band": "medium", "basis": "good"},
                        }
                    ],
                    "risks_if_unfilled": [
                        {
                            "category": "delivery",
                            "statement": "Reliability issues will continue without stronger architecture ownership.",
                            "evidence_refs": ["artifact:pre_enrichment.outputs.research_enrichment.role_profile.risk_landscape[0]"],
                            "confidence": {"score": 0.68, "band": "medium", "basis": "good"},
                        }
                    ],
                    "success_metrics": [
                        {
                            "statement": "Production AI outcomes shipped with clear ownership.",
                            "metric_kind": "outcome",
                            "horizon": "90_day",
                            "evidence_refs": ["artifact:pre_enrichment.outputs.research_enrichment.role_profile.success_metrics[0]"],
                            "confidence": {"score": 0.67, "band": "medium", "basis": "good"},
                        }
                    ],
                    "proof_map": [
                        {
                            "pain_id": "p_technical_12345678",
                            "preferred_proof_type": "architecture",
                            "preferred_evidence_shape": "Named systems plus measurable production impact.",
                            "bad_proof_patterns": ["tool list without ownership"],
                            "affected_document_sections": ["summary", "experience"],
                            "rationale": "Architecture ownership is the reassurance signal.",
                            "confidence": {"score": 0.74, "band": "medium", "basis": "good"},
                        }
                    ],
                    "search_terms": [{"term": "production AI architecture reliability", "intent": "retrieval", "source_basis": "role and JD"}],
                    "unresolved_questions": [],
                    "sources": [],
                    "evidence": [],
                    "confidence": {"score": 0.74, "band": "medium", "basis": "good"},
                }
            },
            {"provider": "codex", "model": model, "outcome": "success"},
        )

    monkeypatch.setattr("src.preenrich.stages.pain_point_intelligence._invoke_codex_json_traced", _fake_invoke)
    result = PainPointIntelligenceStage().run(_ctx())
    assert result.stage_output["status"] == "completed"
    assert result.stage_output["proof_map"][0]["pain_id"] == result.stage_output["pain_points"][0]["pain_id"]
    assert result.stage_output["compact"]["proof_map_size"] == 1
    assert result.stage_output["trace_ref"]["trace_url"] == "https://langfuse.example/trace:pain-intel"
    assert result.output["pain_points"] == ["Production AI architecture needs explicit ownership."]


def test_pain_point_stage_stabilizes_jd_excerpt_refs_and_high_urgency(monkeypatch):
    def _fake_invoke(*, prompt: str, model: str, job_id: str, **_kwargs):
        return (
            {
                "pain_point_intelligence": {
                    "status": "completed",
                    "source_scope": "jd_only",
                    "pain_points": [
                        {
                            "pain_id": "p_microsoft_stack",
                            "category": "technical",
                            "statement": "The team needs someone to ship Microsoft 365 and Copilot Studio workflows.",
                            "source_scope": "jd_only",
                            "evidence_refs": ["artifact:jd_excerpt"],
                            "urgency": "high",
                            "related_stakeholders": ["hiring_manager"],
                            "likely_proof_targets": ["architecture", "process"],
                            "confidence": {"score": 0.8, "band": "high", "basis": "jd"},
                        }
                    ],
                    "strategic_needs": [
                        {
                            "category": "technical",
                            "statement": "Build a Microsoft-centered AI automation capability.",
                            "evidence_refs": ["artifact:jd_excerpt"],
                            "confidence": {"score": 0.7, "band": "medium", "basis": "jd"},
                        }
                    ],
                    "risks_if_unfilled": [
                        {
                            "category": "delivery",
                            "statement": "Operating concepts may remain weak.",
                            "evidence_refs": ["artifact:jd_excerpt"],
                            "confidence": {"score": 0.7, "band": "medium", "basis": "jd"},
                        }
                    ],
                    "success_metrics": [
                        {
                            "statement": "Copilot workflows are running in production.",
                            "metric_kind": "outcome",
                            "horizon": "90_day",
                            "evidence_refs": ["artifact:jd_excerpt"],
                            "confidence": {"score": 0.7, "band": "medium", "basis": "jd"},
                        }
                    ],
                    "proof_map": [
                        {
                            "pain_id": "p_microsoft_stack",
                            "preferred_proof_type": "architecture",
                            "preferred_evidence_shape": "Named systems on Microsoft 365.",
                            "bad_proof_patterns": [],
                            "affected_document_sections": ["summary", "experience"],
                            "rationale": "JD signal only.",
                            "confidence": {"score": 0.7, "band": "medium", "basis": "jd"},
                        }
                    ],
                    "search_terms": [{"term": "Microsoft 365 Copilot Studio workflow", "intent": "retrieval", "source_basis": "artifact:jd_excerpt"}],
                    "unresolved_questions": [],
                    "sources": [],
                    "evidence": [{"claim": "The JD explicitly mentions Microsoft 365 and Copilot Studio workflow ownership.", "source_ids": ["artifact:jd_excerpt"]}],
                    "confidence": {"score": 0.76, "band": "medium", "basis": "jd"},
                }
            },
            {"provider": "codex", "model": model, "outcome": "success"},
        )

    monkeypatch.setattr("src.preenrich.stages.pain_point_intelligence._invoke_codex_json_traced", _fake_invoke)
    result = PainPointIntelligenceStage().run(_ctx(research_status="partial"))
    assert result.stage_output["status"] == "partial"
    assert result.stage_output["fail_open_reason"] == "thin_research"
    assert result.stage_output["pain_points"][0]["urgency"] == "medium"
    assert result.stage_output["proof_map"][0]["pain_id"] == "p_microsoft_stack"
    diffs = result.stage_output["debug_context"]["deterministic_validator_diffs"]
    assert any("clamped urgency=high -> medium" in item for item in diffs)


def test_pain_point_stage_fail_open_on_llm_terminal_failure(monkeypatch):
    calls = {"count": 0}

    def _fake_invoke(*, prompt: str, model: str, job_id: str, **_kwargs):
        calls["count"] += 1
        return None, {"provider": "codex", "model": model, "outcome": "error_subprocess"}

    monkeypatch.setattr("src.preenrich.stages.pain_point_intelligence._invoke_codex_json_traced", _fake_invoke)
    result = PainPointIntelligenceStage().run(_ctx())
    assert calls["count"] == 2
    assert result.stage_output["status"] == "unresolved"
    assert result.stage_output["fail_open_reason"] == "llm_terminal_failure"
    assert result.stage_output["pain_points"] == []


def test_pain_point_stage_emits_cache_miss_and_fail_open_events(monkeypatch):
    def _fake_invoke(*, prompt: str, model: str, job_id: str, **_kwargs):
        return None, {"provider": "codex", "model": model, "outcome": "error_subprocess"}

    ctx = _ctx()
    monkeypatch.setattr("src.preenrich.stages.pain_point_intelligence._invoke_codex_json_traced", _fake_invoke)
    PainPointIntelligenceStage().run(ctx)
    event_names = [item["name"] for item in ctx.tracer.events]
    assert "scout.preenrich.pain_point_intelligence.cache.miss" in event_names
    assert "scout.preenrich.pain_point_intelligence.fail_open" in event_names


def test_pain_point_stage_cache_hit_accepts_persisted_compact_and_artifact_refs(monkeypatch):
    monkeypatch.setenv("PREENRICH_STAKEHOLDER_SURFACE_ENABLED", "true")
    ctx = _ctx()
    payload = {
        "job_id": str(ctx.job_doc["_id"]),
        "level2_job_id": str(ctx.job_doc["_id"]),
        "input_snapshot_id": ctx.input_snapshot_id,
        "pain_input_hash": "sha256:cache-hit",
        "prompt_version": "pain_point_intelligence@v4.2.3",
        "provider_used": "codex",
        "model_used": "gpt-5.4",
        "transport_used": "none",
        "status": "completed",
        "source_scope": "jd_plus_research",
        "pain_points": [
            {
                "pain_id": "p_cache_hit",
                "category": "technical",
                "statement": "Cached pain survives reread.",
                "evidence_refs": ["artifact:pre_enrichment.outputs.jd_facts.merged_view.responsibilities[0]"],
                "urgency": "medium",
                "likely_proof_targets": ["architecture"],
                "confidence": {"score": 0.7, "band": "medium", "basis": "cached"},
            }
        ],
        "strategic_needs": [
            {
                "category": "technical",
                "statement": "Cached strategic need survives reread.",
                "evidence_refs": ["artifact:pre_enrichment.outputs.jd_facts.merged_view.responsibilities[0]"],
                "confidence": {"score": 0.6, "band": "medium", "basis": "cached"},
            }
        ],
        "risks_if_unfilled": [
            {
                "category": "delivery",
                "statement": "Cached risk survives reread.",
                "evidence_refs": ["artifact:pre_enrichment.outputs.jd_facts.merged_view.responsibilities[0]"],
                "confidence": {"score": 0.6, "band": "medium", "basis": "cached"},
            }
        ],
        "success_metrics": [
            {
                "statement": "Cached metric survives reread.",
                "metric_kind": "outcome",
                "horizon": "90_day",
                "evidence_refs": ["artifact:pre_enrichment.outputs.jd_facts.merged_view.success_metrics[0]"],
                "confidence": {"score": 0.6, "band": "medium", "basis": "cached"},
            }
        ],
        "proof_map": [
            {
                "pain_id": "p_cache_hit",
                "preferred_proof_type": "architecture",
                "preferred_evidence_shape": "Cached proof shape.",
                "bad_proof_patterns": [],
                "affected_document_sections": ["summary"],
                "rationale": "Cached rationale.",
                "confidence": {"score": 0.6, "band": "medium", "basis": "cached"},
            }
        ],
        "search_terms": [{"term": "cached pain proof", "intent": "retrieval", "source_basis": "cache"}],
        "unresolved_questions": [],
        "sources": [],
        "evidence": [{"claim": "Cached evidence survives reread.", "source_ids": ["artifact:pre_enrichment.outputs.jd_facts.merged_view.responsibilities[0]"]}],
        "confidence": {"score": 0.65, "band": "medium", "basis": "cached"},
        "compact": {"pains_count": 1},
        "artifact_refs": {"pain_point_intelligence": {"collection": "pain_point_intelligence", "id": "artifact-1"}},
    }
    ctx.job_doc["pre_enrichment"]["outputs"]["pain_point_intelligence"] = payload

    computed = pain_input_hash(
        {
            "jd_facts": ctx.job_doc["pre_enrichment"]["outputs"]["jd_facts"]["merged_view"],
            "classification": {
                "primary_role_category": "ai_architect",
                "tone_family": "executive",
                "ai_taxonomy": {"intensity": "significant"},
            },
            "research_input_hash": ctx.job_doc["pre_enrichment"]["outputs"]["research_enrichment"]["research_input_hash"],
            "research_status": ctx.job_doc["pre_enrichment"]["outputs"]["research_enrichment"]["status"],
            "stakeholder_coverage_digest": {
                "status": ctx.job_doc["pre_enrichment"]["outputs"]["stakeholder_surface"]["status"],
                "evaluator_coverage_target": ctx.job_doc["pre_enrichment"]["outputs"]["stakeholder_surface"]["evaluator_coverage_target"],
            },
            "prompt_version": "pain_point_intelligence@v4.2.3",
        }
    )
    ctx.job_doc["pre_enrichment"]["outputs"]["pain_point_intelligence"]["pain_input_hash"] = computed

    result = PainPointIntelligenceStage().run(ctx)
    assert result.stage_output["compact"]["pains_count"] == 1
    assert result.stage_output["artifact_refs"]["pain_point_intelligence"]["id"] == "artifact-1"
    assert result.stage_output["pain_points"][0]["pain_id"] == "p_cache_hit"


def test_blueprint_assembly_prefers_pain_point_artifact_projection():
    ctx = _ctx()
    ctx.stage_name = "blueprint_assembly"
    ctx.job_doc["pre_enrichment"]["outputs"]["pain_point_intelligence"] = {
        "status": "completed",
        "source_scope": "jd_plus_research",
        "pain_points": [{"statement": "Real pain from artifact."}],
        "strategic_needs": [{"statement": "Real need from artifact."}],
        "risks_if_unfilled": [{"statement": "Real risk from artifact."}],
        "success_metrics": [{"statement": "Real metric from artifact."}],
        "proof_map": [],
        "unresolved_questions": [],
        "confidence": {"score": 0.7, "band": "medium", "basis": "artifact"},
        "pain_input_hash": "sha256:test",
        "prompt_version": "pain_point_intelligence@v4.2.3",
    }
    result = BlueprintAssemblyStage().run(ctx)
    assert result.stage_output["snapshot"]["pain_points"] == ["Real pain from artifact."]
    assert result.stage_output["snapshot"]["pain_point_intelligence_compact"]["pains_count"] == 1


def test_build_pain_point_intelligence_compact_counts_high_urgency():
    compact = build_pain_point_intelligence_compact(
        {
            "status": "partial",
            "source_scope": "jd_only",
            "pain_points": [{"urgency": "high"}, {"urgency": "medium"}],
            "strategic_needs": [{}],
            "risks_if_unfilled": [{}],
            "success_metrics": [{}],
            "proof_map": [{}, {}],
            "unresolved_questions": ["a", "b"],
            "confidence": {"score": 0.4, "band": "low"},
            "prompt_version": "pain_point_intelligence@v4.2.3",
            "pain_input_hash": "sha256:test",
            "trace_ref": {"trace_id": "trace:1"},
        }
    )
    assert compact["high_urgency_pains_count"] == 1
    assert compact["proof_map_size"] == 2
