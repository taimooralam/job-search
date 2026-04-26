import pytest
from bson import ObjectId

from src.preenrich.stages.presentation_contract import PresentationContractStage
from src.preenrich.types import StageContext, StepConfig


class _FakeTracer:
    def __init__(self) -> None:
        self.trace_id = "trace:presentation"
        self.trace_url = "https://langfuse.example/trace:presentation"
        self.trace = object()
        self.enabled = True
        self.started: list[str] = []
        self.events: list[tuple[str, dict]] = []

    def start_substage_span(self, stage_name: str, substage: str, metadata: dict):
        self.started.append(f"{stage_name}.{substage}")
        return {"stage_name": stage_name, "substage": substage, "metadata": metadata}

    def end_span(self, span, *, output=None) -> None:
        return None

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
            "description": "Lead architecture for production AI systems across product and platform.",
            "pre_enrichment": {
                "outputs": {
                    "jd_facts": {
                        "merged_view": {
                            "title": "Principal AI Architect",
                            "normalized_title": "Principal AI Architect",
                            "seniority_level": "principal",
                            "top_keywords": ["architecture", "ai", "platform"],
                            "responsibilities": ["Lead architecture", "Drive technical direction"],
                            "qualifications": ["Distributed systems", "ML systems"],
                            "ideal_candidate_profile": {
                                "identity_statement": "Principal AI architecture lead",
                                "archetype": "technical_architect",
                            },
                        }
                    },
                    "classification": {
                        "primary_role_category": "ai_architect",
                        "tone_family": "executive",
                        "ai_taxonomy": {"intensity": "significant"},
                    },
                    "research_enrichment": {
                        "status": "completed",
                        "company_profile": {
                            "canonical_name": "Acme",
                            "canonical_domain": "acme.example.com",
                            "identity_confidence": {"score": 0.9, "band": "high", "basis": "official"},
                            "scale_signals": ["platform_scale"],
                        },
                        "role_profile": {
                            "status": "completed",
                            "mandate": ["Lead architecture", "Set platform direction"],
                            "business_impact": ["Increase platform reliability"],
                        },
                        "application_profile": {"portal_family": "greenhouse", "ats_vendor": "greenhouse"},
                    },
                    "stakeholder_surface": {
                        "status": "completed",
                        "evaluator_coverage_target": ["recruiter", "hiring_manager", "peer_technical"],
                        "evaluator_coverage": [],
                        "real_stakeholders": [
                            {
                                "stakeholder_type": "hiring_manager",
                                "cv_preference_surface": {
                                    "preferred_evidence_types": ["named_systems", "metrics"],
                                    "preferred_signal_order": ["metrics"],
                                    "ai_section_preference": "dedicated_if_core",
                                },
                            }
                        ],
                        "inferred_stakeholder_personas": [],
                    },
                    "pain_point_intelligence": {
                        "status": "completed",
                        "proof_map": [
                            {"pain_id": "p1", "preferred_proof_type": "architecture"},
                            {"pain_id": "p2", "preferred_proof_type": "metric"},
                            {"pain_id": "p3", "preferred_proof_type": "ai"},
                        ],
                    },
                    "job_inference": {"semantic_role_model": {"role_mandate": "Own AI platform architecture."}},
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


def _dimension_payload() -> dict:
    return {
        "experience_dimension_weights": {
            "status": "completed",
            "source_scope": "jd_plus_research_plus_stakeholder",
            "dimension_enum_version": "v1",
            "overall_weights": {
                "hands_on_implementation": 12,
                "architecture_system_design": 20,
                "leadership_enablement": 8,
                "tools_technology_stack": 6,
                "methodology_operating_model": 6,
                "business_impact": 12,
                "stakeholder_communication": 8,
                "ai_ml_depth": 12,
                "domain_context": 4,
                "quality_risk_reliability": 5,
                "delivery_execution_pace": 4,
                "platform_scaling_change": 3,
            },
            "stakeholder_variant_weights": {
                "recruiter": {
                    "hands_on_implementation": 10,
                    "architecture_system_design": 18,
                    "leadership_enablement": 6,
                    "tools_technology_stack": 8,
                    "methodology_operating_model": 6,
                    "business_impact": 14,
                    "stakeholder_communication": 10,
                    "ai_ml_depth": 10,
                    "domain_context": 4,
                    "quality_risk_reliability": 5,
                    "delivery_execution_pace": 5,
                    "platform_scaling_change": 4,
                }
            },
            "minimum_visible_dimensions": ["architecture_system_design", "business_impact", "ai_ml_depth"],
            "overuse_risks": [],
            "rationale": "test",
            "unresolved_markers": [],
            "defaults_applied": [],
            "normalization_events": [],
            "confidence": {"score": 0.78, "band": "medium", "basis": "test"},
            "evidence": [],
            "notes": [],
        }
    }


def _mock_llm(monkeypatch):
    calls: list[str] = []

    def _fake_invoke(*, prompt: str, model: str, job_id: str, **kwargs):
        if "P-document-expectations@v1" in prompt:
            calls.append("document_expectations")
            return {
                "document_expectations": {
                    "status": "completed",
                    "primary_document_goal": "architecture_first",
                    "secondary_document_goals": [],
                    "audience_variants": {
                        "recruiter": {"tilt": ["clarity_first"], "must_see": ["role_fit"], "risky_signals": [], "rationale": "r"},
                        "hiring_manager": {"tilt": ["evidence_first"], "must_see": ["architecture_judgment"], "risky_signals": [], "rationale": "hm"},
                    },
                    "proof_order": ["architecture", "metric", "ai"],
                    "anti_patterns": ["tool_list_cv"],
                    "tone_posture": {"primary_tone": "architect_first", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
                    "density_posture": {"overall_density": "high", "header_density": "proof_dense", "section_density_bias": []},
                    "keyword_balance": {"target_keyword_pressure": "high", "ats_mirroring_bias": "balanced", "semantic_expansion_bias": "balanced"},
                    "unresolved_markers": [],
                    "rationale": "r",
                    "confidence": {"score": 0.8, "band": "high", "basis": "test"},
                    "evidence": [],
                }
            }, {"provider": "codex", "model": model, "outcome": "success"}
        if "P-cv-shape-expectations@v1" in prompt:
            calls.append("cv_shape_expectations")
            return {
                "cv_shape_expectations": {
                    "status": "completed",
                    "title_strategy": "closest_truthful",
                    "header_shape": {"density": "proof_dense", "include_elements": ["name"], "proof_line_policy": "required", "differentiator_line_policy": "optional"},
                    "section_order": ["header", "summary", "experience"],
                    "section_emphasis": [
                        {"section_id": "summary", "emphasis": "highlight", "focus_categories": ["architecture"], "length_bias": "short", "ordering_bias": "outcome_first", "rationale": "s"},
                        {"section_id": "experience", "emphasis": "highlight", "focus_categories": ["metric"], "length_bias": "long", "ordering_bias": "outcome_first", "rationale": "e"},
                    ],
                    "ai_section_policy": "required",
                    "counts": {"key_achievements_min": 3, "key_achievements_max": 5, "core_competencies_min": 6, "core_competencies_max": 10, "summary_sentences_min": 2, "summary_sentences_max": 4},
                    "ats_envelope": {"pressure": "standard", "format_rules": ["single_column"], "keyword_placement_bias": "top_heavy"},
                    "evidence_density": "high",
                    "seniority_signal_strength": "high",
                    "compression_rules": ["compress_core_competencies_first"],
                    "omission_rules": ["omit_publications_if_unused_in_role_family"],
                    "unresolved_markers": [],
                    "rationale": "shape",
                    "confidence": {"score": 0.8, "band": "high", "basis": "test"},
                    "evidence": [],
                }
            }, {"provider": "codex", "model": model, "outcome": "success"}
        if "P-ideal-candidate@v1" in prompt:
            calls.append("ideal_candidate")
            return {
                "ideal_candidate_presentation_model": {
                    "status": "completed",
                    "visible_identity": "Principal AI architecture leader",
                    "acceptable_titles": ["Principal AI Architect"],
                    "title_strategy": "closest_truthful",
                    "must_signal": [{"tag": "architecture_judgment", "proof_category": "architecture", "rationale": "a", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                    "should_signal": [{"tag": "ai_depth", "proof_category": "ai", "rationale": "a", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p3"}]}],
                    "de_emphasize": [{"tag": "tool_listing", "proof_category": "process", "rationale": "d", "evidence_refs": [{"source": "stakeholder_surface.evaluator_coverage_target"}]}],
                    "proof_ladder": [{"proof_category": "architecture", "signal_tag": "architecture_judgment", "rationale": "p", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                    "tone_profile": {"primary_tone": "architect_first", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
                    "credibility_markers": [],
                    "risk_flags": [],
                    "audience_variants": {"recruiter": {"tilt": ["clarity_first"], "must_land": ["role_fit"], "de_emphasize": ["tool_listing"], "rationale": "r"}},
                    "confidence": {"score": 0.75, "band": "medium", "basis": "test"},
                    "defaults_applied": [],
                    "unresolved_markers": [],
                    "evidence_refs": [{"source": "jd_facts.merged_view.ideal_candidate_profile"}],
                    "debug_context": {"input_summary": {"role_family": "architecture_first"}, "defaults_applied": [], "normalization_events": [], "richer_output_retained": [], "rejected_output": [], "retry_events": []},
                }
            }, {"provider": "codex", "model": model, "outcome": "success"}
        if "P-experience-dimension-weights@v1" in prompt:
            calls.append("experience_dimension_weights")
            return _dimension_payload(), {"provider": "codex", "model": model, "outcome": "success"}
        if "P-document-and-cv-shape@v1" in prompt:
            calls.append("document_and_cv_shape")
            merged = {
                "document_expectations": _fake_invoke(prompt="P-document-expectations@v1", model=model, job_id=job_id)[0]["document_expectations"],
                "cv_shape_expectations": _fake_invoke(prompt="P-cv-shape-expectations@v1", model=model, job_id=job_id)[0]["cv_shape_expectations"],
                "experience_dimension_weights": _dimension_payload()["experience_dimension_weights"],
            }
            return merged, {"provider": "codex", "model": model, "outcome": "success"}
        pytest.fail(f"Unexpected prompt: {prompt[:120]}")

    monkeypatch.setattr("src.preenrich.stages.presentation_contract._invoke_codex_json_traced", _fake_invoke)
    return calls


def test_presentation_contract_split_mode_includes_dimension_weights(monkeypatch):
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_DIMENSION_WEIGHTS_ENABLED", "true")
    calls = _mock_llm(monkeypatch)
    ctx = _ctx()
    ctx.tracer = _FakeTracer()

    result = PresentationContractStage().run(ctx)

    assert result.stage_output["experience_dimension_weights"]["status"] == "completed"
    assert sum(result.stage_output["experience_dimension_weights"]["overall_weights"].values()) == 100
    assert result.stage_output["prompt_versions"]["experience_dimension_weights"] == "P-experience-dimension-weights@v1"
    assert calls == [
        "document_expectations",
        "cv_shape_expectations",
        "ideal_candidate",
        "experience_dimension_weights",
    ]


def test_presentation_contract_merged_mode_parses_dimension_weights_from_merged_response(monkeypatch):
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_MERGED_PROMPT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_DIMENSION_WEIGHTS_ENABLED", "true")
    calls = _mock_llm(monkeypatch)
    ctx = _ctx()
    ctx.tracer = _FakeTracer()

    result = PresentationContractStage().run(ctx)

    assert result.stage_output["experience_dimension_weights"]["dimension_enum_version"] == "v1"
    assert calls == ["document_and_cv_shape", "document_expectations", "cv_shape_expectations", "ideal_candidate"]
