from __future__ import annotations

import pytest
from bson import ObjectId

from src.preenrich.stages.presentation_contract import PresentationContractStage
from src.preenrich.types import StageContext, StepConfig
from tests.unit.preenrich._emphasis_rules_test_data import (
    dimension_weights_payload,
    emphasis_rules_payload,
)


class _FakeTracer:
    def __init__(self) -> None:
        self.trace_id = "trace:presentation"
        self.trace_url = "https://langfuse.example/trace:presentation"
        self.trace = object()
        self.enabled = True
        self.started: list[str] = []
        self.ended: list[dict] = []
        self.events: list[tuple[str, dict]] = []

    def start_substage_span(self, stage_name: str, substage: str, metadata: dict):
        self.started.append(f"{stage_name}.{substage}")
        return {"stage_name": stage_name, "substage": substage}

    def end_span(self, span, *, output=None) -> None:
        self.ended.append({"span": span, "output": output})

    def record_event(self, name: str, metadata: dict) -> None:
        self.events.append((name, metadata))

    def complete(self, *, output=None) -> None:
        return None


def _ctx(
    *,
    stakeholder_status: str = "completed",
    include_pain_map: bool = True,
    role_profile_status: str = "completed",
    ai_intensity: str = "significant",
) -> StageContext:
    job_id = ObjectId()
    pain_map = (
        [
            {"pain_id": "p1", "preferred_proof_type": "architecture"},
            {"pain_id": "p2", "preferred_proof_type": "metric"},
            {"pain_id": "p3", "preferred_proof_type": "ai"},
        ]
        if include_pain_map
        else []
    )
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
                            "responsibilities": ["Lead architecture", "Ship production AI systems"],
                            "qualifications": ["Distributed systems", "ML systems"],
                            "ideal_candidate_profile": {
                                "identity_statement": "Principal AI architecture lead for production systems.",
                                "archetype": "technical_architect",
                                "key_traits": ["architecture depth", "delivery rigor"],
                                "culture_signals": ["enterprise", "platform"],
                            },
                        }
                    },
                    "classification": {
                        "primary_role_category": "ai_architect",
                        "tone_family": "executive",
                        "ai_taxonomy": {"intensity": ai_intensity},
                    },
                    "research_enrichment": {
                        "status": "completed",
                        "company_profile": {
                            "canonical_name": "Acme",
                            "canonical_domain": "acme.example.com",
                            "identity_confidence": {"score": 0.9, "band": "high", "basis": "official"},
                        },
                        "role_profile": {
                            "status": role_profile_status,
                            "summary": "Architecture-heavy principal IC role.",
                            "mandate": ["Lead architecture", "Drive AI platform standards"],
                            "business_impact": ["Improve platform reliability"],
                            "why_now": "Platform scale is increasing.",
                            "org_placement": {"function_area": "engineering"},
                        },
                        "application_profile": {
                            "portal_family": "greenhouse",
                            "ats_vendor": "greenhouse",
                        },
                    },
                    "stakeholder_surface": {
                        "status": stakeholder_status,
                        "evaluator_coverage_target": ["recruiter", "hiring_manager", "peer_technical"],
                        "evaluator_coverage": [
                            {"role": "recruiter", "required": True, "status": "real", "stakeholder_refs": ["candidate_rank:1"], "persona_refs": [], "coverage_confidence": {"score": 0.8, "band": "high", "basis": "real"}},
                            {"role": "hiring_manager", "required": True, "status": "real", "stakeholder_refs": ["candidate_rank:2"], "persona_refs": [], "coverage_confidence": {"score": 0.8, "band": "high", "basis": "real"}},
                            {"role": "peer_technical", "required": True, "status": "inferred", "stakeholder_refs": [], "persona_refs": ["persona_peer_technical_1"], "coverage_confidence": {"score": 0.6, "band": "medium", "basis": "inferred"}},
                        ],
                        "real_stakeholders": [
                            {
                                "stakeholder_type": "hiring_manager",
                                "stakeholder_ref": "candidate_rank:2",
                                "stakeholder_record_snapshot": {
                                    "stakeholder_type": "hiring_manager",
                                    "identity_status": "resolved",
                                    "identity_confidence": {"score": 0.85, "band": "high", "basis": "official"},
                                    "matched_signal_classes": ["official_team_page_named_person", "public_profile_company_role_match"],
                                },
                                "cv_preference_surface": {
                                    "review_objectives": ["Verify architecture judgment", "Verify shipped systems"],
                                    "preferred_evidence_types": ["named_systems", "metrics"],
                                    "ai_section_preference": "dedicated_if_core",
                                },
                                "likely_reject_signals": [{"bullet": "Hype without evidence.", "reason": "rigor"}],
                                "confidence": {"score": 0.75, "band": "medium", "basis": "signals"},
                                "status": "completed",
                            }
                        ],
                        "inferred_stakeholder_personas": [
                            {
                                "persona_id": "persona_peer_technical_1",
                                "persona_type": "peer_technical",
                                "coverage_gap": "peer_technical",
                                "evidence_basis": "This is inferred from role class and coverage gap.",
                                "confidence": {"score": 0.6, "band": "medium", "basis": "inferred"},
                            }
                        ],
                    },
                    "pain_point_intelligence": {
                        "status": "completed" if include_pain_map else "partial",
                        "proof_map": pain_map,
                    },
                    "job_inference": {
                        "semantic_role_model": {
                            "role_mandate": "Own AI platform architecture and technical direction.",
                        }
                    },
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


def _mock_llm(
    monkeypatch,
    *,
    document_payload=None,
    shape_payload=None,
    ideal_payload=None,
    dimension_payload=None,
    emphasis_payload=None,
):
    calls: list[tuple[str, str]] = []

    def _fake_invoke(*, prompt: str, model: str, job_id: str, **kwargs):
        if "P-document-expectations@v1" in prompt:
            calls.append(("document_expectations", job_id))
            return document_payload, {"provider": "codex", "model": model, "outcome": "success"}
        if "P-cv-shape-expectations@v1" in prompt:
            calls.append(("cv_shape_expectations", job_id))
            return shape_payload, {"provider": "codex", "model": model, "outcome": "success"}
        if "P-document-and-cv-shape@v1" in prompt:
            calls.append(("document_and_cv_shape", job_id))
            merged = {
                "document_expectations": (document_payload or {}).get("document_expectations", {}),
                "cv_shape_expectations": (shape_payload or {}).get("cv_shape_expectations", {}),
            }
            if dimension_payload:
                merged["experience_dimension_weights"] = dimension_payload.get("experience_dimension_weights", {})
            if emphasis_payload:
                merged["truth_constrained_emphasis_rules"] = emphasis_payload.get(
                    "truth_constrained_emphasis_rules",
                    {},
                )
            return merged, {"provider": "codex", "model": model, "outcome": "success"}
        if "P-ideal-candidate@v1" in prompt:
            calls.append(("ideal_candidate", job_id))
            return ideal_payload, {"provider": "codex", "model": model, "outcome": "success"}
        if "P-experience-dimension-weights@v1" in prompt:
            calls.append(("experience_dimension_weights", job_id))
            return dimension_payload, {"provider": "codex", "model": model, "outcome": "success"}
        if "P-emphasis-rules@v1" in prompt:
            calls.append(("emphasis_rules", job_id))
            return emphasis_payload, {"provider": "codex", "model": model, "outcome": "success"}
        pytest.fail(f"Unexpected prompt: {prompt[:120]}")

    monkeypatch.setattr("src.preenrich.stages.presentation_contract._invoke_codex_json_traced", _fake_invoke)
    return calls


def test_presentation_contract_happy_path(monkeypatch):
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_DIMENSION_WEIGHTS_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_EMPHASIS_RULES_ENABLED", "true")
    calls = _mock_llm(
        monkeypatch,
        document_payload={
            "document_expectations": {
                "status": "completed",
                "primary_document_goal": "architecture_first",
                "secondary_document_goals": ["delivery_first"],
                "audience_variants": {
                    "recruiter": {"tilt": ["clarity_first"], "must_see": ["role_fit"], "risky_signals": ["tool_list_cv"], "rationale": "Recruiter lens."},
                    "hiring_manager": {"tilt": ["evidence_first"], "must_see": ["architecture_judgment"], "risky_signals": ["hype_header"], "rationale": "Hiring manager lens."},
                    "peer_technical": {"tilt": ["evidence_first"], "must_see": ["hands_on_implementation"], "risky_signals": ["tool_list_cv"], "rationale": "Peer lens."},
                },
                "proof_order": ["architecture", "metric", "ai"],
                "anti_patterns": ["tool_list_cv", "hype_header"],
                "tone_posture": {"primary_tone": "architect_first", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
                "density_posture": {"overall_density": "high", "header_density": "proof_dense", "section_density_bias": []},
                "keyword_balance": {"target_keyword_pressure": "high", "ats_mirroring_bias": "balanced", "semantic_expansion_bias": "balanced"},
                "unresolved_markers": [],
                "rationale": "Architecture thesis.",
                "confidence": {"score": 0.84, "band": "high", "basis": "strong"},
                "evidence": [],
            }
        },
        shape_payload={
            "cv_shape_expectations": {
                "status": "completed",
                "title_strategy": "closest_truthful",
                "header_shape": {"density": "proof_dense", "include_elements": ["name", "links"], "proof_line_policy": "required", "differentiator_line_policy": "optional"},
                "section_order": ["header", "summary", "key_achievements", "core_competencies", "ai_highlights", "experience", "education"],
                "section_emphasis": [
                    {"section_id": "summary", "emphasis": "highlight", "focus_categories": ["architecture"], "length_bias": "short", "ordering_bias": "outcome_first", "rationale": "fast proof"},
                    {"section_id": "experience", "emphasis": "highlight", "focus_categories": ["architecture", "metric"], "length_bias": "long", "ordering_bias": "outcome_first", "rationale": "main proof"},
                ],
                "ai_section_policy": "required",
                "counts": {"key_achievements_min": 3, "key_achievements_max": 5, "core_competencies_min": 6, "core_competencies_max": 10, "summary_sentences_min": 2, "summary_sentences_max": 4},
                "ats_envelope": {"pressure": "standard", "format_rules": ["single_column"], "keyword_placement_bias": "top_heavy"},
                "evidence_density": "high",
                "seniority_signal_strength": "high",
                "compression_rules": ["compress_core_competencies_first"],
                "omission_rules": ["omit_publications_if_unused_in_role_family"],
                "unresolved_markers": [],
                "rationale": "proof dense shape",
                "confidence": {"score": 0.8, "band": "high", "basis": "strong"},
                "evidence": [],
            }
        },
        ideal_payload={
            "ideal_candidate_presentation_model": {
                "status": "completed",
                "visible_identity": "Principal AI architecture leader for production platforms",
                "acceptable_titles": ["Principal AI Architect", "Architect, AI Platforms"],
                "title_strategy": "closest_truthful",
                "must_signal": [
                    {"tag": "architecture_judgment", "proof_category": "architecture", "rationale": "Lead with architecture proof.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]},
                ],
                "should_signal": [
                    {"tag": "ai_depth", "proof_category": "ai", "rationale": "AI credibility should be explicit.", "evidence_refs": [{"source": "classification.ai_taxonomy.intensity"}]}
                ],
                "de_emphasize": [
                    {"tag": "tool_listing", "proof_category": "process", "rationale": "Do not lead with tools.", "evidence_refs": [{"source": "stakeholder_surface.real_stakeholders[0].likely_reject_signals"}]}
                ],
                "proof_ladder": [
                    {"proof_category": "architecture", "signal_tag": "architecture_judgment", "rationale": "Architecture first.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]},
                ],
                "tone_profile": {"primary_tone": "architect_first", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
                "credibility_markers": [
                    {"marker": "named_systems", "proof_category": "architecture", "rationale": "Named systems matter.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}
                ],
                "risk_flags": [
                    {"flag": "generic_ai_claim", "severity": "high", "rationale": "Do not claim AI without proof.", "evidence_refs": [{"source": "classification.ai_taxonomy.intensity"}]}
                ],
                "audience_variants": {
                    "recruiter": {"tilt": ["clarity_first", "keyword_visible"], "must_land": ["role_fit", "recognizable_title"], "de_emphasize": ["tool_listing"], "rationale": "Recruiter lens."},
                    "hiring_manager": {"tilt": ["evidence_first", "architect_first"], "must_land": ["architecture_judgment", "production_impact"], "de_emphasize": ["generic_leadership_claim"], "rationale": "Hiring manager lens."},
                    "peer_technical": {"tilt": ["evidence_first"], "must_land": ["hands_on_implementation", "architecture_judgment"], "de_emphasize": ["tool_listing"], "rationale": "Peer lens."},
                },
                "confidence": {"score": 0.82, "band": "high", "basis": "strong"},
                "defaults_applied": [],
                "unresolved_markers": [],
                "evidence_refs": [{"source": "jd_facts.merged_view.ideal_candidate_profile"}],
                "debug_context": {"input_summary": {}, "defaults_applied": [], "normalization_events": [], "richer_output_retained": [], "rejected_output": [], "retry_events": []},
            }
        },
        dimension_payload={"experience_dimension_weights": dimension_weights_payload()},
        emphasis_payload={"truth_constrained_emphasis_rules": emphasis_rules_payload()},
    )

    result = PresentationContractStage().run(_ctx())
    assert result.stage_output["status"] == "completed"
    assert result.stage_output["document_expectations"]["primary_document_goal"] == "architecture_first"
    assert result.stage_output["cv_shape_expectations"]["ai_section_policy"] == "required"
    assert result.stage_output["cv_shape_expectations"]["header_shape"]["density"] == "proof_dense"
    assert result.stage_output["ideal_candidate_presentation_model"]["title_strategy"] == "closest_truthful"
    assert result.stage_output["ideal_candidate_presentation_model"]["acceptable_titles"][0] == "Principal AI Architect"
    assert result.stage_output["experience_dimension_weights"]["status"] == "completed"
    assert result.stage_output["truth_constrained_emphasis_rules"]["status"] == "completed"
    assert result.stage_output["trace_ref"]["trace_id"] is None
    assert [call[0] for call in calls] == [
        "document_expectations",
        "cv_shape_expectations",
        "ideal_candidate",
        "experience_dimension_weights",
        "emphasis_rules",
    ]


def test_presentation_contract_fail_open_on_inferred_only_stakeholders(monkeypatch):
    _mock_llm(monkeypatch, document_payload=None, shape_payload=None)
    result = PresentationContractStage().run(_ctx(stakeholder_status="inferred_only"))
    assert result.stage_output["status"] == "partial"
    assert result.stage_output["document_expectations"]["status"] == "inferred_only"
    assert set(result.stage_output["document_expectations"]["audience_variants"].keys()) <= {"recruiter", "hiring_manager", "peer_technical"}
    assert result.stage_output["document_expectations"]["confidence"]["band"] != "high"
    assert result.stage_output["ideal_candidate_presentation_model"]["confidence"]["band"] != "high"


def test_presentation_contract_fail_open_when_pain_map_missing(monkeypatch):
    _mock_llm(monkeypatch, document_payload=None, shape_payload=None)
    result = PresentationContractStage().run(_ctx(include_pain_map=False))
    assert result.stage_output["status"] == "partial"
    assert result.stage_output["document_expectations"]["proof_order"]
    assert "role_family_document_expectations_default" in result.stage_output["document_expectations"]["debug_context"]["defaults_applied"]
    assert result.stage_output["ideal_candidate_presentation_model"]["proof_ladder"]


def test_presentation_contract_fail_open_when_role_profile_partial(monkeypatch):
    _mock_llm(monkeypatch, document_payload=None, shape_payload=None)
    result = PresentationContractStage().run(_ctx(role_profile_status="partial"))
    assert result.stage_output["document_expectations"]["primary_document_goal"] == "architecture_first"
    assert result.stage_output["document_expectations"]["status"] in {"completed", "partial", "inferred_only"}
    assert result.stage_output["ideal_candidate_presentation_model"]["acceptable_titles"]


def test_presentation_contract_retries_and_falls_back_on_invalid_ai_policy(monkeypatch):
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED", "true")
    _mock_llm(
        monkeypatch,
        document_payload={
            "document_expectations": {
                "status": "completed",
                "primary_document_goal": "balanced",
                "secondary_document_goals": [],
                "audience_variants": {"recruiter": {"tilt": ["clarity_first"], "must_see": ["role_fit"], "risky_signals": [], "rationale": "Recruiter."}},
                "proof_order": ["metric"],
                "anti_patterns": ["tool_list_cv"],
                "tone_posture": {"primary_tone": "balanced", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
                "density_posture": {"overall_density": "medium", "header_density": "balanced", "section_density_bias": []},
                "keyword_balance": {"target_keyword_pressure": "medium", "ats_mirroring_bias": "balanced", "semantic_expansion_bias": "balanced"},
                "unresolved_markers": [],
                "rationale": "balanced",
                "confidence": {"score": 0.6, "band": "medium", "basis": "ok"},
                "evidence": [],
            }
        },
        shape_payload={
            "cv_shape_expectations": {
                "status": "completed",
                "title_strategy": "exact_match",
                "header_shape": {"density": "balanced", "include_elements": ["name"], "proof_line_policy": "optional", "differentiator_line_policy": "optional"},
                "section_order": ["header", "summary", "experience"],
                "section_emphasis": [{"section_id": "experience", "emphasis": "highlight", "focus_categories": ["metric"], "length_bias": "long", "ordering_bias": "outcome_first", "rationale": "main"}],
                "ai_section_policy": "required",
                "counts": {"key_achievements_min": 2, "key_achievements_max": 4, "core_competencies_min": 4, "core_competencies_max": 8, "summary_sentences_min": 2, "summary_sentences_max": 3},
                "ats_envelope": {"pressure": "standard", "format_rules": ["single_column"], "keyword_placement_bias": "balanced"},
                "evidence_density": "medium",
                "seniority_signal_strength": "medium",
                "compression_rules": ["compress_core_competencies_first"],
                "omission_rules": ["omit_publications_if_unused_in_role_family"],
                "unresolved_markers": [],
                "rationale": "invalid",
                "confidence": {"score": 0.6, "band": "medium", "basis": "invalid"},
                "evidence": [],
            }
        },
        ideal_payload={
            "ideal_candidate_presentation_model": {
                "status": "completed",
                "visible_identity": "Principal AI Architect",
                "acceptable_titles": ["Principal AI Architect"],
                "title_strategy": "exact_match",
                "must_signal": [{"tag": "architecture_judgment", "proof_category": "architecture", "rationale": "Proof.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "should_signal": [],
                "de_emphasize": [{"tag": "tool_listing", "proof_category": "process", "rationale": "Avoid tools.", "evidence_refs": [{"source": "document_expectations.anti_patterns"}]}],
                "proof_ladder": [{"proof_category": "architecture", "signal_tag": "architecture_judgment", "rationale": "Architecture first.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "tone_profile": {"primary_tone": "balanced", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
                "credibility_markers": [{"marker": "named_systems", "proof_category": "architecture", "rationale": "Named systems.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "risk_flags": [{"flag": "generic_ai_claim", "severity": "medium", "rationale": "Avoid AI hype.", "evidence_refs": [{"source": "classification.ai_taxonomy.intensity"}]}],
                "audience_variants": {"recruiter": {"tilt": ["clarity_first"], "must_land": ["role_fit"], "de_emphasize": ["tool_listing"], "rationale": "Recruiter."}},
                "confidence": {"score": 0.6, "band": "medium", "basis": "ok"},
                "defaults_applied": [],
                "unresolved_markers": [],
                "evidence_refs": [{"source": "jd_facts.merged_view.ideal_candidate_profile"}],
                "debug_context": {"input_summary": {}, "defaults_applied": [], "normalization_events": [], "richer_output_retained": [], "rejected_output": [], "retry_events": []},
            }
        },
    )

    result = PresentationContractStage().run(_ctx(ai_intensity="none"))
    assert result.stage_output["status"] == "partial"
    assert result.stage_output["cv_shape_expectations"]["ai_section_policy"] in {"embedded_only", "discouraged"}
    assert result.stage_output["cv_shape_expectations"]["debug_context"]["defaults_applied"]
    assert (
        result.stage_output["ideal_candidate_presentation_model"]["title_strategy"]
        == result.stage_output["cv_shape_expectations"]["title_strategy"]
    )


def test_presentation_contract_candidate_leakage_drops_offending_fields(monkeypatch):
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED", "true")
    _mock_llm(
        monkeypatch,
        document_payload={
            "document_expectations": {
                "status": "completed",
                "primary_document_goal": "balanced",
                "secondary_document_goals": [],
                "audience_variants": {
                    "hiring_manager": {
                        "tilt": ["clarity_first"],
                        "must_see": ["ownership_scope"],
                        "risky_signals": [],
                        "rationale": "I led a 40% YoY platform migration.",
                    }
                },
                "proof_order": ["metric"],
                "anti_patterns": ["tool_list_cv"],
                "tone_posture": {"primary_tone": "balanced", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
                "density_posture": {"overall_density": "medium", "header_density": "balanced", "section_density_bias": []},
                "keyword_balance": {"target_keyword_pressure": "medium", "ats_mirroring_bias": "balanced", "semantic_expansion_bias": "balanced"},
                "unresolved_markers": [],
                "rationale": "I did this.",
                "confidence": {"score": 0.7, "band": "high", "basis": "bad"},
                "evidence": [],
            }
        },
        shape_payload=None,
        ideal_payload={
            "ideal_candidate_presentation_model": {
                "status": "completed",
                "visible_identity": "I built the platform leader identity.",
                "acceptable_titles": ["Principal AI Architect", "VP AI"],
                "title_strategy": "closest_truthful",
                "must_signal": [{"tag": "architecture_judgment", "proof_category": "architecture", "rationale": "I built Acme Cloud.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "should_signal": [],
                "de_emphasize": [{"tag": "tool_listing", "proof_category": "process", "rationale": "Avoid tools.", "evidence_refs": [{"source": "document_expectations.anti_patterns"}]}],
                "proof_ladder": [{"proof_category": "architecture", "signal_tag": "architecture_judgment", "rationale": "I delivered 40% growth.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "tone_profile": {"primary_tone": "architect_first", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
                "credibility_markers": [{"marker": "named_systems", "proof_category": "architecture", "rationale": "Named systems.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "risk_flags": [{"flag": "generic_ai_claim", "severity": "medium", "rationale": "Avoid hype.", "evidence_refs": [{"source": "classification.ai_taxonomy.intensity"}]}],
                "audience_variants": {"hiring_manager": {"tilt": ["clarity_first"], "must_land": ["ownership_scope"], "de_emphasize": ["tool_listing"], "rationale": "I did this."}},
                "confidence": {"score": 0.7, "band": "high", "basis": "bad"},
                "defaults_applied": [],
                "unresolved_markers": [],
                "evidence_refs": [{"source": "jd_facts.merged_view.ideal_candidate_profile"}],
                "debug_context": {"input_summary": {}, "defaults_applied": [], "normalization_events": [], "richer_output_retained": [], "rejected_output": [], "retry_events": []},
            }
        },
    )
    result = PresentationContractStage().run(_ctx())
    assert result.stage_output["status"] == "partial"
    rejected = result.stage_output["document_expectations"]["debug_context"]["rejected_output"]
    assert any("candidate_leakage" in item["reason"] for item in rejected)
    ideal_rejected = result.stage_output["ideal_candidate_presentation_model"]["debug_context"]["rejected_output"]
    assert any("candidate_leakage" in item["reason"] for item in ideal_rejected)


def test_presentation_contract_merged_mode_still_calls_ideal_candidate(monkeypatch):
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_MERGED_PROMPT_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED", "true")
    calls = _mock_llm(
        monkeypatch,
        document_payload={
            "document_expectations": {
                "status": "completed",
                "primary_document_goal": "architecture_first",
                "secondary_document_goals": [],
                "audience_variants": {"recruiter": {"tilt": ["clarity_first"], "must_see": ["role_fit"], "risky_signals": [], "rationale": "Recruiter."}},
                "proof_order": ["architecture", "metric"],
                "anti_patterns": ["tool_list_cv"],
                "tone_posture": {"primary_tone": "architect_first", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
                "density_posture": {"overall_density": "high", "header_density": "proof_dense", "section_density_bias": []},
                "keyword_balance": {"target_keyword_pressure": "medium", "ats_mirroring_bias": "balanced", "semantic_expansion_bias": "balanced"},
                "unresolved_markers": [],
                "rationale": "Architecture thesis.",
                "confidence": {"score": 0.84, "band": "high", "basis": "strong"},
                "evidence": [],
            }
        },
        shape_payload={
            "cv_shape_expectations": {
                "status": "completed",
                "title_strategy": "closest_truthful",
                "header_shape": {"density": "proof_dense", "include_elements": ["name"], "proof_line_policy": "required", "differentiator_line_policy": "optional"},
                "section_order": ["header", "summary", "experience"],
                "section_emphasis": [{"section_id": "experience", "emphasis": "highlight", "focus_categories": ["architecture"], "length_bias": "long", "ordering_bias": "outcome_first", "rationale": "main"}],
                "ai_section_policy": "required",
                "counts": {"key_achievements_min": 2, "key_achievements_max": 4, "core_competencies_min": 4, "core_competencies_max": 8, "summary_sentences_min": 2, "summary_sentences_max": 3},
                "ats_envelope": {"pressure": "standard", "format_rules": ["single_column"], "keyword_placement_bias": "balanced"},
                "evidence_density": "high",
                "seniority_signal_strength": "high",
                "compression_rules": ["compress_core_competencies_first"],
                "omission_rules": ["omit_publications_if_unused_in_role_family"],
                "unresolved_markers": [],
                "rationale": "proof dense shape",
                "confidence": {"score": 0.8, "band": "high", "basis": "strong"},
                "evidence": [],
            }
        },
        ideal_payload={
            "ideal_candidate_presentation_model": {
                "status": "completed",
                "visible_identity": "Principal AI architecture leader",
                "acceptable_titles": ["Principal AI Architect"],
                "title_strategy": "closest_truthful",
                "must_signal": [{"tag": "architecture_judgment", "proof_category": "architecture", "rationale": "Proof.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "should_signal": [],
                "de_emphasize": [{"tag": "tool_listing", "proof_category": "process", "rationale": "Avoid tools.", "evidence_refs": [{"source": "document_expectations.anti_patterns"}]}],
                "proof_ladder": [{"proof_category": "architecture", "signal_tag": "architecture_judgment", "rationale": "Architecture first.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "tone_profile": {"primary_tone": "architect_first", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
                "credibility_markers": [{"marker": "named_systems", "proof_category": "architecture", "rationale": "Named systems.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "risk_flags": [{"flag": "generic_ai_claim", "severity": "medium", "rationale": "Avoid hype.", "evidence_refs": [{"source": "classification.ai_taxonomy.intensity"}]}],
                "audience_variants": {"recruiter": {"tilt": ["clarity_first"], "must_land": ["role_fit"], "de_emphasize": ["tool_listing"], "rationale": "Recruiter."}},
                "confidence": {"score": 0.7, "band": "medium", "basis": "ok"},
                "defaults_applied": [],
                "unresolved_markers": [],
                "evidence_refs": [{"source": "jd_facts.merged_view.ideal_candidate_profile"}],
                "debug_context": {"input_summary": {}, "defaults_applied": [], "normalization_events": [], "richer_output_retained": [], "rejected_output": [], "retry_events": []},
            }
        },
    )
    result = PresentationContractStage().run(_ctx())
    assert result.stage_output["ideal_candidate_presentation_model"]["acceptable_titles"] == ["Principal AI Architect"]
    assert [call[0] for call in calls] == ["document_and_cv_shape", "ideal_candidate"]


def test_presentation_contract_emits_ideal_candidate_trace_ref(monkeypatch):
    monkeypatch.setenv("PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED", "true")
    _mock_llm(
        monkeypatch,
        document_payload=None,
        shape_payload=None,
        ideal_payload={
            "ideal_candidate_presentation_model": {
                "status": "completed",
                "visible_identity": "Principal AI architecture leader",
                "acceptable_titles": ["Principal AI Architect"],
                "title_strategy": "closest_truthful",
                "must_signal": [{"tag": "architecture_judgment", "proof_category": "architecture", "rationale": "Proof.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "should_signal": [],
                "de_emphasize": [{"tag": "tool_listing", "proof_category": "process", "rationale": "Avoid tools.", "evidence_refs": [{"source": "document_expectations.anti_patterns"}]}],
                "proof_ladder": [{"proof_category": "architecture", "signal_tag": "architecture_judgment", "rationale": "Architecture first.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "tone_profile": {"primary_tone": "architect_first", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
                "credibility_markers": [{"marker": "named_systems", "proof_category": "architecture", "rationale": "Named systems.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}],
                "risk_flags": [{"flag": "generic_ai_claim", "severity": "medium", "rationale": "Avoid hype.", "evidence_refs": [{"source": "classification.ai_taxonomy.intensity"}]}],
                "audience_variants": {"recruiter": {"tilt": ["clarity_first"], "must_land": ["role_fit"], "de_emphasize": ["tool_listing"], "rationale": "Recruiter."}},
                "confidence": {"score": 0.7, "band": "medium", "basis": "ok"},
                "defaults_applied": [],
                "unresolved_markers": [],
                "evidence_refs": [{"source": "jd_facts.merged_view.ideal_candidate_profile"}],
                "debug_context": {"input_summary": {}, "defaults_applied": [], "normalization_events": [], "richer_output_retained": [], "rejected_output": [], "retry_events": []},
            }
        },
    )
    ctx = _ctx()
    ctx.tracer = _FakeTracer()
    result = PresentationContractStage().run(ctx)
    assert "presentation_contract.ideal_candidate" in ctx.tracer.started
    assert result.stage_output["trace_ref"]["trace_id"] == "trace:presentation"
