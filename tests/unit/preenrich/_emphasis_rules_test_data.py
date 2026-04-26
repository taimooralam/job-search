from __future__ import annotations

from copy import deepcopy

from bson import ObjectId

from src.preenrich.blueprint_models import (
    APPLIES_TO_ENUM_VERSION,
    DIMENSION_ENUM_VERSION,
    RULE_TYPE_ENUM_VERSION,
)
from src.preenrich.types import StageContext, StepConfig


def clone(payload: dict) -> dict:
    return deepcopy(payload)


def document_expectations_payload() -> dict:
    return {
        "status": "completed",
        "primary_document_goal": "architecture_first",
        "secondary_document_goals": ["delivery_first"],
        "audience_variants": {
            "recruiter": {
                "tilt": ["clarity_first"],
                "must_see": ["role_fit"],
                "risky_signals": ["tool_list_cv"],
                "rationale": "Recruiter lens.",
            },
            "hiring_manager": {
                "tilt": ["evidence_first"],
                "must_see": ["architecture_judgment"],
                "risky_signals": ["hype_header"],
                "rationale": "Hiring manager lens.",
            },
            "peer_technical": {
                "tilt": ["evidence_first"],
                "must_see": ["hands_on_implementation"],
                "risky_signals": ["tool_list_cv"],
                "rationale": "Peer lens.",
            },
        },
        "proof_order": ["architecture", "metric", "ai"],
        "anti_patterns": ["tool_list_cv", "hype_header"],
        "tone_posture": {
            "primary_tone": "architect_first",
            "hype_tolerance": "low",
            "narrative_tolerance": "medium",
            "formality": "neutral",
        },
        "density_posture": {
            "overall_density": "high",
            "header_density": "proof_dense",
            "section_density_bias": [],
        },
        "keyword_balance": {
            "target_keyword_pressure": "high",
            "ats_mirroring_bias": "balanced",
            "semantic_expansion_bias": "balanced",
        },
        "unresolved_markers": [],
        "rationale": "Architecture-first, proof-dense presentation.",
        "confidence": {"score": 0.84, "band": "high", "basis": "test"},
        "evidence": [],
    }


def cv_shape_expectations_payload(
    *,
    title_strategy: str = "closest_truthful",
    ai_section_policy: str = "required",
    section_order: list[str] | None = None,
) -> dict:
    order = section_order or [
        "header",
        "summary",
        "key_achievements",
        "ai_highlights",
        "experience",
        "education",
    ]
    return {
        "status": "completed",
        "title_strategy": title_strategy,
        "header_shape": {
            "density": "proof_dense",
            "include_elements": ["name", "links"],
            "proof_line_policy": "required",
            "differentiator_line_policy": "optional",
        },
        "section_order": order,
        "section_emphasis": [
            {
                "section_id": "summary",
                "emphasis": "highlight",
                "focus_categories": ["architecture"],
                "length_bias": "short",
                "ordering_bias": "outcome_first",
                "rationale": "Lead with architecture proof.",
            },
            {
                "section_id": "experience",
                "emphasis": "highlight",
                "focus_categories": ["metric", "architecture"],
                "length_bias": "long",
                "ordering_bias": "outcome_first",
                "rationale": "Primary proof section.",
            },
        ],
        "ai_section_policy": ai_section_policy,
        "counts": {
            "key_achievements_min": 3,
            "key_achievements_max": 5,
            "core_competencies_min": 6,
            "core_competencies_max": 10,
            "summary_sentences_min": 2,
            "summary_sentences_max": 4,
        },
        "ats_envelope": {
            "pressure": "standard",
            "format_rules": ["single_column"],
            "keyword_placement_bias": "top_heavy",
        },
        "evidence_density": "high",
        "seniority_signal_strength": "high",
        "compression_rules": ["compress_core_competencies_first"],
        "omission_rules": ["omit_publications_if_unused_in_role_family"],
        "unresolved_markers": [],
        "rationale": "Proof-dense CV shape.",
        "confidence": {"score": 0.8, "band": "high", "basis": "test"},
        "evidence": [],
    }


def ideal_candidate_payload(*, title_strategy: str = "closest_truthful") -> dict:
    return {
        "status": "completed",
        "visible_identity": "Principal AI architecture leader for production platforms",
        "acceptable_titles": ["Principal AI Architect", "Architect, AI Platforms"],
        "title_strategy": title_strategy,
        "must_signal": [
            {
                "tag": "architecture_judgment",
                "proof_category": "architecture",
                "rationale": "Lead with architecture proof.",
                "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}],
            }
        ],
        "should_signal": [
            {
                "tag": "ai_depth",
                "proof_category": "ai",
                "rationale": "AI credibility remains conditional.",
                "evidence_refs": [{"source": "classification.ai_taxonomy.intensity"}],
            }
        ],
        "de_emphasize": [
            {
                "tag": "tool_listing",
                "proof_category": "process",
                "rationale": "Do not lead with tools.",
                "evidence_refs": [{"source": "document_expectations.anti_patterns"}],
            }
        ],
        "proof_ladder": [
            {
                "proof_category": "architecture",
                "signal_tag": "architecture_judgment",
                "rationale": "Architecture first.",
                "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}],
            },
            {
                "proof_category": "metric",
                "signal_tag": "production_impact",
                "rationale": "Metrics second.",
                "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p2"}],
            },
        ],
        "tone_profile": {
            "primary_tone": "architect_first",
            "hype_tolerance": "low",
            "narrative_tolerance": "medium",
            "formality": "neutral",
        },
        "credibility_markers": [
            {
                "marker": "named_systems",
                "proof_category": "architecture",
                "rationale": "Named systems matter.",
                "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}],
            }
        ],
        "risk_flags": [
            {
                "flag": "generic_ai_claim",
                "severity": "medium",
                "rationale": "Avoid AI hype without direct proof.",
                "evidence_refs": [{"source": "classification.ai_taxonomy.intensity"}],
            }
        ],
        "audience_variants": {
            "recruiter": {
                "tilt": ["clarity_first", "keyword_visible"],
                "must_land": ["role_fit", "recognizable_title"],
                "de_emphasize": ["tool_listing"],
                "rationale": "Recruiter lens.",
            },
            "hiring_manager": {
                "tilt": ["evidence_first", "architect_first"],
                "must_land": ["architecture_judgment"],
                "de_emphasize": ["tool_listing"],
                "rationale": "Hiring manager lens.",
            },
        },
        "confidence": {"score": 0.82, "band": "high", "basis": "test"},
        "defaults_applied": [],
        "unresolved_markers": [],
        "evidence_refs": [{"source": "jd_facts.merged_view.ideal_candidate_profile"}],
        "debug_context": {
            "input_summary": {"role_family": "architecture_first"},
            "defaults_applied": [],
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
        },
    }


def dimension_weights_payload(
    *,
    leadership_weight: int = 8,
    overuse_risks: list[dict] | None = None,
) -> dict:
    leadership_delta = leadership_weight - 8
    return {
        "status": "completed",
        "source_scope": "jd_plus_research_plus_stakeholder",
        "dimension_enum_version": DIMENSION_ENUM_VERSION,
        "overall_weights": {
            "hands_on_implementation": 12 - leadership_delta,
            "architecture_system_design": 20,
            "leadership_enablement": leadership_weight,
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
                "hands_on_implementation": 10 - leadership_delta,
                "architecture_system_design": 18,
                "leadership_enablement": leadership_weight,
                "tools_technology_stack": 8,
                "methodology_operating_model": 6,
                "business_impact": 14,
                "stakeholder_communication": 10,
                "ai_ml_depth": 10,
                "domain_context": 4,
                "quality_risk_reliability": 5,
                "delivery_execution_pace": 5,
                "platform_scaling_change": 2,
            }
        },
        "minimum_visible_dimensions": [
            "architecture_system_design",
            "business_impact",
            "ai_ml_depth",
        ],
        "overuse_risks": overuse_risks or [],
        "rationale": "Lead with architecture, impact, and AI depth.",
        "unresolved_markers": [],
        "defaults_applied": [],
        "normalization_events": [],
        "confidence": {"score": 0.78, "band": "medium", "basis": "test"},
        "evidence": [],
        "notes": [],
        "debug_context": {
            "input_summary": {"role_family": "architecture_first"},
            "role_family_weight_priors": {},
            "evaluator_dimension_pressure": {},
            "ai_intensity_cap": 20,
            "architecture_evidence_band": "strong",
            "leadership_evidence_band": "partial",
            "defaults_applied": [],
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
        },
    }


def emphasis_rules_payload(
    *,
    ai_intensity: str = "significant",
    leadership_cap: int = 10,
    defaults_applied: list[str] | None = None,
    unresolved_markers: list[str] | None = None,
    confidence_band: str = "high",
    confidence_score: float = 0.84,
) -> dict:
    defaults_applied = defaults_applied or []
    unresolved_markers = unresolved_markers or []
    global_rules = [
        {
            "rule_id": "title_guard_global",
            "rule_type": "forbid_without_direct_proof",
            "topic_family": "title_inflation",
            "applies_to_kind": "global",
            "applies_to": "global",
            "condition": "Requested title exceeds the acceptable title envelope.",
            "action": "Do not authorize titles outside acceptable_titles; use closest truthful framing.",
            "basis": "Title claims must stay inside the peer title envelope.",
            "evidence_refs": [
                "cv_shape_expectations.title_strategy",
                "ideal_candidate_presentation_model.acceptable_titles",
            ],
            "precedence": 80,
            "confidence": {"score": 0.8, "band": "high", "basis": "test"},
        },
        {
            "rule_id": "leadership_cap_rule",
            "rule_type": "cap_dimension_weight",
            "topic_family": "leadership_scope",
            "applies_to_kind": "dimension",
            "applies_to": "leadership_enablement",
            "condition": "Leadership scope evidence is bounded by the leadership envelope.",
            "action": "Cap leadership framing to the supported envelope and require proof for stronger claims.",
            "basis": "Leadership claims must not outrun seniority or reporting evidence.",
            "evidence_refs": [
                "jd_facts.merged_view.team_context",
                "experience_dimension_weights.debug_context.leadership_evidence_band",
            ],
            "precedence": 80,
            "cap_value": leadership_cap,
            "confidence": {"score": 0.76, "band": "medium", "basis": "test"},
        },
    ]
    section_rules = {
        "experience": [
            {
                "rule_id": "credibility_marker_experience",
                "rule_type": "require_credibility_marker",
                "topic_family": "credibility_ladder_degradation",
                "applies_to_kind": "section",
                "applies_to": "experience",
                "condition": "Every high-emphasis claim needs a credibility marker.",
                "action": "Require named systems, scoped metrics, or ownership markers before emphasis increases.",
                "basis": "Thin proof must degrade emphasis gracefully.",
                "evidence_refs": [
                    "ideal_candidate_presentation_model.credibility_markers",
                    "pain_point_intelligence.proof_map",
                ],
                "precedence": 70,
                "confidence": {"score": 0.72, "band": "medium", "basis": "test"},
            }
        ]
    }
    allowed_if_evidenced = [
        {
            "rule_id": "ai_claims_ai",
            "rule_type": "allowed_if_evidenced",
            "topic_family": "ai_claims",
            "applies_to_kind": "proof",
            "applies_to": "ai",
            "condition": "AI depth claims remain conditional on direct proof.",
            "action": "Allow AI claims only when direct evidence is visible and truthful.",
            "basis": "AI claim policy must track classification intensity and evidence depth.",
            "evidence_refs": [
                "classification.ai_taxonomy.intensity",
                "experience_dimension_weights.overall_weights.ai_ml_depth",
            ],
            "precedence": 20,
            "confidence": {"score": 0.72, "band": "medium", "basis": "test"},
        },
        {
            "rule_id": "architecture_claims_architecture",
            "rule_type": "allowed_if_evidenced",
            "topic_family": "architecture_claims",
            "applies_to_kind": "proof",
            "applies_to": "architecture",
            "condition": "Architecture framing is grounded in mandate and direct proof.",
            "action": "Allow architecture claims when anchored to direct evidence.",
            "basis": "Architecture claims track role mandate and proof map support.",
            "evidence_refs": [
                "research_enrichment.role_profile.mandate",
                "pain_point_intelligence.proof_map",
            ],
            "precedence": 20,
            "confidence": {"score": 0.74, "band": "medium", "basis": "test"},
        },
    ]
    downgrade_rules = [
        {
            "rule_id": "stakeholder_soften_stakeholder",
            "rule_type": "prefer_softened_form",
            "topic_family": "stakeholder_management_claims",
            "applies_to_kind": "proof",
            "applies_to": "stakeholder",
            "condition": "Stakeholder evidence is indirect or inferred.",
            "action": "Use conservative stakeholder language unless direct cross-functional proof is visible.",
            "basis": "Stakeholder claims should not outrun the evaluator surface.",
            "evidence_refs": [
                "stakeholder_surface.evaluator_coverage_target",
                "pain_point_intelligence.proof_map",
            ],
            "precedence": 50,
            "confidence": {"score": 0.7, "band": "medium", "basis": "test"},
        },
        {
            "rule_id": "tooling_soften_process",
            "rule_type": "prefer_softened_form",
            "topic_family": "tooling_inflation",
            "applies_to_kind": "proof",
            "applies_to": "process",
            "condition": "Tool and process lists are weak as primary evidence.",
            "action": "Soften tooling-first language and keep proof ahead of tool names.",
            "basis": "Process-heavy language should not dominate the CV narrative.",
            "evidence_refs": [
                "document_expectations.anti_patterns",
                "ideal_candidate_presentation_model.de_emphasize",
            ],
            "precedence": 50,
            "confidence": {"score": 0.68, "band": "medium", "basis": "test"},
        },
    ]
    omit_rules = [
        {
            "rule_id": "domain_guard_domain",
            "rule_type": "never_infer_from_job_only",
            "topic_family": "domain_expertise",
            "applies_to_kind": "proof",
            "applies_to": "domain",
            "condition": "Domain expertise is not directly evidenced beyond job context.",
            "action": "Do not infer deep domain expertise from job fit alone.",
            "basis": "Domain claims require more than JD-only inference.",
            "evidence_refs": [
                "jd_facts.merged_view.qualifications",
                "research_enrichment.role_profile.summary",
            ],
            "precedence": 85,
            "confidence": {"score": 0.7, "band": "medium", "basis": "test"},
        },
        {
            "rule_id": "metric_guard_metric",
            "rule_type": "omit_if_weak",
            "topic_family": "metrics_scale_claims",
            "applies_to_kind": "proof",
            "applies_to": "metric",
            "condition": "Metric or scale proof is weak, generic, or lacks scope.",
            "action": "Omit metric-led claims until direct scope and scale proof exists.",
            "basis": "Fabricated metrics and scale are not permitted.",
            "evidence_refs": [
                "pain_point_intelligence.proof_map",
                "document_expectations.anti_patterns",
            ],
            "precedence": 65,
            "confidence": {"score": 0.74, "band": "medium", "basis": "test"},
        },
    ]
    return {
        "status": "partial" if defaults_applied or unresolved_markers else "completed",
        "source_scope": "jd_plus_research_plus_stakeholder",
        "rule_type_enum_version": RULE_TYPE_ENUM_VERSION,
        "applies_to_enum_version": APPLIES_TO_ENUM_VERSION,
        "prompt_version": "P-emphasis-rules@v1",
        "global_rules": global_rules,
        "section_rules": section_rules,
        "allowed_if_evidenced": allowed_if_evidenced,
        "downgrade_rules": downgrade_rules,
        "omit_rules": omit_rules,
        "forbidden_claim_patterns": [
            {
                "pattern_id": "chief_ai_officer",
                "pattern": "chief ai officer",
                "pattern_kind": "substring",
                "reason": "Do not authorize inflated AI-executive titles.",
                "example": "Chief AI Officer",
                "evidence_refs": ["ideal_candidate_presentation_model.acceptable_titles"],
                "confidence": {"score": 0.78, "band": "medium", "basis": "test"},
            },
            {
                "pattern_id": "genai_visionary",
                "pattern": "(?:llm|genai)\\s+visionary",
                "pattern_kind": "regex_safe",
                "reason": "Do not authorize unsupported AI-visionary branding.",
                "example": "GenAI visionary",
                "evidence_refs": ["classification.ai_taxonomy.intensity"],
                "confidence": {"score": 0.72, "band": "medium", "basis": "test"},
            },
        ],
        "credibility_ladder_rules": [
            {
                "ladder_id": "main_credibility_ladder",
                "applies_to_audience": "all",
                "ladder": ["architecture", "metric", "stakeholder"],
                "fallback_rule_id": "credibility_marker_experience",
                "rationale": "Fall back to explicit credibility markers when proof is thin.",
                "evidence_refs": [
                    "ideal_candidate_presentation_model.proof_ladder",
                    "pain_point_intelligence.proof_map",
                ],
                "confidence": {"score": 0.74, "band": "medium", "basis": "test"},
            }
        ],
        "topic_coverage": [
            {"topic_family": "title_inflation", "rule_count": 1, "source": "llm"},
            {"topic_family": "ai_claims", "rule_count": 1, "source": "llm"},
            {"topic_family": "leadership_scope", "rule_count": 1, "source": "llm"},
            {"topic_family": "architecture_claims", "rule_count": 1, "source": "llm"},
            {"topic_family": "domain_expertise", "rule_count": 1, "source": "llm"},
            {"topic_family": "stakeholder_management_claims", "rule_count": 1, "source": "llm"},
            {"topic_family": "metrics_scale_claims", "rule_count": 1, "source": "llm"},
            {"topic_family": "credibility_ladder_degradation", "rule_count": 1, "source": "llm"},
            {"topic_family": "tooling_inflation", "rule_count": 1, "source": "llm"},
        ],
        "rationale": "Truth-constrained emphasis rules bound downstream claim policy.",
        "unresolved_markers": unresolved_markers,
        "defaults_applied": defaults_applied,
        "normalization_events": [],
        "confidence": {
            "score": confidence_score,
            "band": confidence_band,
            "basis": "test",
        },
        "evidence": [
            {
                "claim": "Emphasis rules are bounded by title, AI, leadership, architecture, and proof envelopes.",
                "source_ids": [
                    "document_expectations.proof_order",
                    "cv_shape_expectations.ai_section_policy",
                    "ideal_candidate_presentation_model.acceptable_titles",
                    "experience_dimension_weights.overall_weights",
                ],
            }
        ],
        "notes": ["Rules describe claim policy only, never candidate truth or CV prose."],
        "debug_context": {
            "input_summary": {
                "role_family": "architecture_first",
                "seniority": "principal",
                "ai_intensity": ai_intensity,
                "evaluator_roles_in_scope": ["recruiter", "hiring_manager", "peer_technical"],
            },
            "role_family_emphasis_rule_priors": {"role_family": "architecture_first"},
            "title_safety_envelope": {
                "title_strategy": "closest_truthful",
                "acceptable_titles": ["Principal AI Architect", "Architect, AI Platforms"],
            },
            "ai_claim_envelope": {"ai_intensity": ai_intensity, "ai_intensity_cap": 20},
            "leadership_claim_envelope": {"seniority": "principal", "direct_reports": 0},
            "architecture_claim_envelope": {"architecture_evidence_band": "strong"},
            "forbidden_claim_pattern_examples": ["Chief AI Officer", "GenAI visionary"],
            "defaults_applied": defaults_applied,
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
            "conflict_resolution_log": [],
        },
        "fail_open_reason": None,
    }


def presentation_contract_payload() -> dict:
    return {
        "job_id": "job-test",
        "level2_job_id": str(ObjectId()),
        "input_snapshot_id": "sha256:snapshot",
        "status": "completed",
        "prompt_versions": {
            "document_expectations": "P-document-expectations@v1",
            "cv_shape_expectations": "P-cv-shape-expectations@v1",
            "ideal_candidate": "P-ideal-candidate@v1",
            "experience_dimension_weights": "P-experience-dimension-weights@v1",
            "emphasis_rules": "P-emphasis-rules@v1",
        },
        "prompt_metadata": {},
        "document_expectations": document_expectations_payload(),
        "cv_shape_expectations": cv_shape_expectations_payload(),
        "ideal_candidate_presentation_model": ideal_candidate_payload(),
        "experience_dimension_weights": dimension_weights_payload(),
        "truth_constrained_emphasis_rules": emphasis_rules_payload(),
        "debug": {"raw_outputs": {}},
        "unresolved_questions": [],
        "notes": [],
        "timing": {"generated_at": "2026-04-25T00:00:00+00:00"},
        "usage": {"provider": "codex", "model": "gpt-5.4"},
        "cache_refs": {},
    }


def build_stage_context(
    *,
    stakeholder_status: str = "completed",
    role_profile_status: str = "completed",
    ai_intensity: str = "significant",
    direct_reports: int = 0,
) -> StageContext:
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
                            "team_context": {"direct_reports": direct_reports},
                            "ideal_candidate_profile": {
                                "identity_statement": "Principal AI architecture lead",
                                "archetype": "technical_architect",
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
                            "identity_confidence": {
                                "score": 0.9,
                                "band": "high",
                                "basis": "official",
                            },
                            "scale_signals": ["platform_scale"],
                        },
                        "role_profile": {
                            "status": role_profile_status,
                            "summary": "Architecture-heavy principal role.",
                            "mandate": ["Lead architecture", "Set platform direction"],
                            "business_impact": ["Increase platform reliability"],
                        },
                        "application_profile": {
                            "portal_family": "greenhouse",
                            "ats_vendor": "greenhouse",
                        },
                    },
                    "stakeholder_surface": {
                        "status": stakeholder_status,
                        "evaluator_coverage_target": [
                            "recruiter",
                            "hiring_manager",
                            "peer_technical",
                        ],
                        "evaluator_coverage": [],
                        "real_stakeholders": [
                            {
                                "stakeholder_type": "hiring_manager",
                                "cv_preference_surface": {
                                    "preferred_evidence_types": ["named_systems", "metrics"],
                                    "preferred_signal_order": ["architecture", "metric"],
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
                    "job_inference": {
                        "semantic_role_model": {"role_mandate": "Own AI platform architecture."}
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
