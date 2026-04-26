from __future__ import annotations

import pytest

from src.preenrich.blueprint_models import (
    IdealCandidatePresentationModelDoc,
    normalize_ideal_candidate_payload,
)
from src.preenrich.stages.presentation_contract import _validate_ideal_candidate


def _payload() -> dict:
    return {
        "status": "completed",
        "visible_identity": "Principal AI architecture leader for production platforms",
        "acceptable_titles": ["Principal AI Architect", "Architect, AI Platforms"],
        "title_strategy": "closest_truthful",
        "must_signal": [
            {"tag": "architecture_judgment", "proof_category": "architecture", "rationale": "Architecture proof.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]},
            {"tag": "production_impact", "proof_category": "metric", "rationale": "Metrics proof.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p2"}]},
        ],
        "should_signal": [
            {"tag": "ai_depth", "proof_category": "ai", "rationale": "AI depth matters.", "evidence_refs": [{"source": "classification.ai_taxonomy.intensity"}]}
        ],
        "de_emphasize": [
            {"tag": "tool_listing", "proof_category": "process", "rationale": "Avoid tool lists.", "evidence_refs": [{"source": "document_expectations.anti_patterns"}]}
        ],
        "proof_ladder": [
            {"proof_category": "architecture", "signal_tag": "architecture_judgment", "rationale": "Architecture first.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]},
            {"proof_category": "metric", "signal_tag": "production_impact", "rationale": "Metrics second.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p2"}]},
        ],
        "tone_profile": {"primary_tone": "architect_first", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
        "credibility_markers": [
            {"marker": "named_systems", "proof_category": "architecture", "rationale": "Named systems.", "evidence_refs": [{"source": "pain_point_intelligence.proof_map:p1"}]}
        ],
        "risk_flags": [
            {"flag": "generic_ai_claim", "severity": "high", "rationale": "Avoid hype.", "evidence_refs": [{"source": "classification.ai_taxonomy.intensity"}]}
        ],
        "audience_variants": {
            "recruiter": {"tilt": ["clarity_first"], "must_land": ["role_fit", "recognizable_title"], "de_emphasize": ["tool_listing"], "rationale": "Recruiter lens."},
            "hiring_manager": {"tilt": ["evidence_first"], "must_land": ["architecture_judgment"], "de_emphasize": ["generic_leadership_claim"], "rationale": "Hiring manager lens."},
        },
        "confidence": {"score": 0.78, "band": "medium", "basis": "Grounded."},
        "defaults_applied": [],
        "unresolved_markers": [],
        "evidence_refs": [{"source": "jd_facts.merged_view.ideal_candidate_profile"}],
        "debug_context": {"input_summary": {}, "defaults_applied": [], "normalization_events": [], "richer_output_retained": [], "rejected_output": [], "retry_events": []},
    }


def test_ideal_candidate_schema_accepts_canonical_output():
    doc = IdealCandidatePresentationModelDoc.model_validate(
        _payload(),
        context={"evaluator_coverage_target": ["recruiter", "hiring_manager"], "expected_title_strategy": "closest_truthful"},
    )
    assert doc.title_strategy == "closest_truthful"
    assert len(doc.proof_ladder) == 2


def test_ideal_candidate_rejects_invalid_proof_category():
    payload = _payload()
    payload["proof_ladder"][0]["proof_category"] = "strategy"
    with pytest.raises(ValueError, match="proof_ladder.proof_category"):
        IdealCandidatePresentationModelDoc.model_validate(
            payload,
            context={"evaluator_coverage_target": ["recruiter", "hiring_manager"], "expected_title_strategy": "closest_truthful"},
        )


def test_ideal_candidate_rejects_invalid_audience_variant():
    payload = _payload()
    with pytest.raises(ValueError, match="subset of evaluator_coverage_target"):
        IdealCandidatePresentationModelDoc.model_validate(
            payload,
            context={"evaluator_coverage_target": ["recruiter"], "expected_title_strategy": "closest_truthful"},
        )


def test_ideal_candidate_rejects_title_strategy_mismatch():
    payload = _payload()
    payload["title_strategy"] = "exact_match"
    with pytest.raises(ValueError, match="title_strategy must match"):
        IdealCandidatePresentationModelDoc.model_validate(
            payload,
            context={"evaluator_coverage_target": ["recruiter", "hiring_manager"], "expected_title_strategy": "closest_truthful"},
        )


def test_ideal_candidate_normalizer_maps_aliases_and_drops_candidate_leakage():
    normalized = normalize_ideal_candidate_payload(
        {
            "status": "completed",
            "identity": "I built the platform identity.",
            "titles": ["Principal AI Architect", "VP AI"],
            "title_strategy": "closest_truthful",
            "must_have_signals": [{"signal": "architecture_judgment", "proof_category": "architecture", "rationale": "I built Acme Cloud."}],
            "secondary_signals": [{"tag": "ai_depth", "proof_category": "ai", "rationale": "AI depth."}],
            "downplay": [{"tag": "tool_listing", "proof_category": "process", "rationale": "Avoid tools."}],
            "proof_order_with_signals": [{"category": "architecture", "tag": "architecture_judgment", "rationale": "Architecture first."}],
            "tone": {"primary_tone": "architect_first"},
            "guardrails": [{"risk_id": "generic_ai_claim", "severity": "high", "rationale": "Avoid hype."}],
            "audiences": {"recruiter": {"must_see": ["role_fit"], "downplay": ["tool_listing"], "rationale": "Recruiter."}},
            "confidence": {"score": 0.7, "band": "high", "basis": "raw"},
            "evidence_refs": [{"source": "jd_facts.merged_view.ideal_candidate_profile"}],
        },
        evaluator_coverage_target=["recruiter"],
        expected_title_strategy="closest_truthful",
        allowed_company_names=["Acme"],
        allowed_company_domain="acme.example.com",
        jd_excerpt="Principal AI Architect role for Acme.",
    )
    assert normalized["visible_identity"] is None
    assert normalized["acceptable_titles"] == ["Principal AI Architect", "VP AI"]
    assert normalized["must_signal"][0]["tag"] == "architecture_judgment"
    rejected = normalized["debug_context"]["rejected_output"]
    assert any("candidate_leakage" in item["reason"] for item in rejected)


def test_validate_ideal_candidate_caps_confidence_when_defaults_are_applied():
    payload = _payload()
    payload["defaults_applied"] = ["role_family_ideal_candidate_default"]
    payload["confidence"] = {"score": 0.95, "band": "high", "basis": "too high"}
    doc = _validate_ideal_candidate(
        payload,
        evaluator_coverage_target=["recruiter", "hiring_manager"],
        expected_title_strategy="closest_truthful",
        stakeholder_status="completed",
    )
    assert doc.status == "partial"
    assert doc.confidence.band == "medium"
    assert doc.confidence.score == pytest.approx(0.79)


def test_ideal_candidate_rationale_allows_job_side_proper_nouns_without_forcing_partial():
    normalized = normalize_ideal_candidate_payload(
        {
            "status": "completed",
            "visible_identity": "AI engineer-architect for production workflow platforms",
            "acceptable_titles": ["AI Engineer & Architect"],
            "title_strategy": "closest_truthful",
            "must_signal": [
                {
                    "tag": "architecture_judgment",
                    "proof_category": "architecture",
                    "rationale": "Microsoft Copilot Studio architecture should be visible.",
                    "evidence_refs": [{"source": "jd_excerpt"}],
                }
            ],
            "proof_ladder": [
                {
                    "proof_category": "architecture",
                    "signal_tag": "architecture_judgment",
                    "rationale": "Lead with Microsoft Copilot Studio delivery proof.",
                    "evidence_refs": [{"source": "jd_excerpt"}],
                }
            ],
            "risk_flags": [
                {
                    "flag": "tool_listing_without_proof",
                    "severity": "high",
                    "rationale": "Do not reduce Microsoft Copilot Studio to a keyword list.",
                    "evidence_refs": [{"source": "jd_excerpt"}],
                }
            ],
            "audience_variants": {
                "recruiter": {
                    "tilt": ["clarity_first"],
                    "must_land": ["architecture_judgment"],
                    "de_emphasize": ["tool_listing"],
                    "rationale": "Recruiter should still see Microsoft platform fit without hype.",
                }
            },
            "confidence": {"score": 0.8, "band": "high", "basis": "Grounded."},
            "evidence_refs": [{"source": "jd_excerpt"}],
        },
        evaluator_coverage_target=["recruiter"],
        expected_title_strategy="closest_truthful",
        allowed_company_names=["Grant Thornton Austria"],
        allowed_company_domain="grantthorntonaustria.at",
        jd_excerpt="Role mentions Microsoft Copilot Studio and Power Platform.",
    )
    assert normalized["status"] == "completed"
    assert normalized["debug_context"]["rejected_output"] == []


def test_ideal_candidate_raw_debug_rejections_do_not_force_partial_without_new_normalizer_rejections():
    normalized = normalize_ideal_candidate_payload(
        {
            "status": "completed",
            "visible_identity": "AI engineer-architect for production workflow platforms",
            "acceptable_titles": ["AI Engineer & Architect"],
            "title_strategy": "closest_truthful",
            "must_signal": [
                {
                    "tag": "architecture_judgment",
                    "proof_category": "architecture",
                    "rationale": "Lead with architecture proof.",
                    "evidence_refs": [{"source": "jd_excerpt"}],
                }
            ],
            "proof_ladder": [
                {
                    "proof_category": "architecture",
                    "signal_tag": "architecture_judgment",
                    "rationale": "Architecture first.",
                    "evidence_refs": [{"source": "jd_excerpt"}],
                }
            ],
            "confidence": {"score": 0.8, "band": "high", "basis": "Grounded."},
            "evidence_refs": [{"source": "jd_excerpt"}],
            "debug_context": {
                "rejected_output": [
                    {
                        "path": "acceptable_titles",
                        "reason": "Rejected inflated variants and kept truthful ones.",
                    }
                ]
            },
        },
        evaluator_coverage_target=["recruiter"],
        expected_title_strategy="closest_truthful",
        allowed_company_names=["Grant Thornton Austria"],
        allowed_company_domain="grantthorntonaustria.at",
        jd_excerpt="Role mentions Microsoft Copilot Studio and Power Platform.",
    )
    assert normalized["status"] == "completed"
    assert normalized["debug_context"]["rejected_output"] == [
        {
            "path": "acceptable_titles",
            "reason": "Rejected inflated variants and kept truthful ones.",
        }
    ]


def test_ideal_candidate_debug_rejected_field_alias_is_coerced_to_path():
    normalized = normalize_ideal_candidate_payload(
        {
            "status": "completed",
            "visible_identity": "AI engineer-architect for production workflow platforms",
            "acceptable_titles": ["AI Engineer & Architect"],
            "title_strategy": "closest_truthful",
            "must_signal": [
                {
                    "tag": "architecture_judgment",
                    "proof_category": "architecture",
                    "rationale": "Lead with architecture proof.",
                    "evidence_refs": [{"source": "jd_excerpt"}],
                }
            ],
            "proof_ladder": [
                {
                    "proof_category": "architecture",
                    "signal_tag": "architecture_judgment",
                    "rationale": "Architecture first.",
                    "evidence_refs": [{"source": "jd_excerpt"}],
                }
            ],
            "confidence": {"score": 0.8, "band": "high", "basis": "Grounded."},
            "evidence_refs": [{"source": "jd_excerpt"}],
            "debug_context": {
                "rejected_output": [
                    {
                        "field": "acceptable_titles",
                        "value": "Principal AI Architect",
                        "reason": "Rejected inflated variants and kept truthful ones.",
                    }
                ]
            },
        },
        evaluator_coverage_target=["recruiter"],
        expected_title_strategy="closest_truthful",
        allowed_company_names=["Grant Thornton Austria"],
        allowed_company_domain="grantthorntonaustria.at",
        jd_excerpt="Role mentions Microsoft Copilot Studio and Power Platform.",
    )

    assert normalized["status"] == "completed"
    assert normalized["debug_context"]["rejected_output"] == [
        {
            "path": "acceptable_titles",
            "reason": "Rejected inflated variants and kept truthful ones.",
        }
    ]


def test_ideal_candidate_debug_retained_field_alias_is_coerced_to_canonical_shape():
    normalized = normalize_ideal_candidate_payload(
        {
            "status": "completed",
            "visible_identity": "AI engineer-architect for production workflow platforms",
            "acceptable_titles": ["AI Engineer & Architect"],
            "title_strategy": "closest_truthful",
            "must_signal": [
                {
                    "tag": "architecture_judgment",
                    "proof_category": "architecture",
                    "rationale": "Lead with architecture proof.",
                    "evidence_refs": [{"source": "jd_excerpt"}],
                }
            ],
            "proof_ladder": [
                {
                    "proof_category": "architecture",
                    "signal_tag": "architecture_judgment",
                    "rationale": "Architecture first.",
                    "evidence_refs": [{"source": "jd_excerpt"}],
                }
            ],
            "confidence": {"score": 0.8, "band": "high", "basis": "Grounded."},
            "evidence_refs": [{"source": "jd_excerpt"}],
            "debug_context": {
                "richer_output_retained": [
                    {
                        "field": "proof_ladder",
                        "reason": "Retained extra proof ordering notes for debugging.",
                    }
                ]
            },
        },
        evaluator_coverage_target=["recruiter"],
        expected_title_strategy="closest_truthful",
        allowed_company_names=["Grant Thornton Austria"],
        allowed_company_domain="grantthorntonaustria.at",
        jd_excerpt="Role mentions Microsoft Copilot Studio and Power Platform.",
    )

    assert normalized["status"] == "completed"
    assert normalized["debug_context"]["richer_output_retained"] == [
        {
            "key": "proof_ladder",
            "value": None,
            "note": "Retained extra proof ordering notes for debugging.",
        }
    ]


def test_ideal_candidate_debug_retained_string_is_coerced_to_canonical_shape():
    normalized = normalize_ideal_candidate_payload(
        {
            "status": "completed",
            "visible_identity": "AI engineer-architect for production workflow platforms",
            "acceptable_titles": ["AI Engineer & Architect"],
            "title_strategy": "closest_truthful",
            "must_signal": [
                {
                    "tag": "architecture_judgment",
                    "proof_category": "architecture",
                    "rationale": "Lead with architecture proof.",
                    "evidence_refs": [{"source": "jd_excerpt"}],
                }
            ],
            "proof_ladder": [
                {
                    "proof_category": "architecture",
                    "signal_tag": "architecture_judgment",
                    "rationale": "Architecture first.",
                    "evidence_refs": [{"source": "jd_excerpt"}],
                }
            ],
            "confidence": {"score": 0.8, "band": "high", "basis": "Grounded."},
            "evidence_refs": [{"source": "jd_excerpt"}],
            "debug_context": {"richer_output_retained": ["cross_functional_partner_variant"]},
        },
        evaluator_coverage_target=["recruiter"],
        expected_title_strategy="closest_truthful",
        allowed_company_names=["Grant Thornton Austria"],
        allowed_company_domain="grantthorntonaustria.at",
        jd_excerpt="Role mentions Microsoft Copilot Studio and Power Platform.",
    )

    assert normalized["status"] == "completed"
    assert normalized["debug_context"]["richer_output_retained"] == [
        {
            "key": "cross_functional_partner_variant",
            "value": None,
            "note": None,
        }
    ]
