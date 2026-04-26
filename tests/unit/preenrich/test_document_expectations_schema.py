from __future__ import annotations

import pytest

from src.preenrich.blueprint_models import DocumentExpectationsDoc


def _payload() -> dict:
    return {
        "status": "completed",
        "primary_document_goal": "architecture_first",
        "secondary_document_goals": ["delivery_first"],
        "audience_variants": {
            "recruiter": {
                "tilt": ["clarity_first"],
                "must_see": ["role_fit", "production_scope"],
                "risky_signals": ["tool_list_cv"],
                "rationale": "Recruiter lens needs fast role-fit clarity.",
            },
            "hiring_manager": {
                "tilt": ["evidence_first"],
                "must_see": ["architecture_judgment", "ownership_scope"],
                "risky_signals": ["hype_header"],
                "rationale": "Hiring manager wants proof-dense credibility.",
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
            "section_density_bias": [{"section_id": "summary", "bias": "medium"}],
        },
        "keyword_balance": {
            "target_keyword_pressure": "high",
            "ats_mirroring_bias": "balanced",
            "semantic_expansion_bias": "balanced",
        },
        "unresolved_markers": [],
        "rationale": "Proof-dense architecture-first thesis.",
        "debug_context": {
            "input_summary": {
                "role_family": "ai_architect",
                "seniority": "principal",
                "ai_intensity": "significant",
                "evaluator_roles_in_scope": ["recruiter", "hiring_manager"],
                "proof_category_frequencies": {"architecture": 2, "metric": 1},
                "top_keywords_top10": ["architecture", "ai"],
                "company_identity_band": "high",
                "research_status": "completed",
                "stakeholder_surface_status": "completed",
            },
            "defaults_applied": [],
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
        },
        "confidence": {"score": 0.82, "band": "high", "basis": "Upstream signals converge."},
        "evidence": [{"claim": "Architecture-first framing is supported by upstream artifacts.", "source_ids": ["classification.primary_role_category"]}],
    }


def test_document_expectations_doc_accepts_canonical_payload():
    doc = DocumentExpectationsDoc.model_validate(
        _payload(),
        context={"evaluator_coverage_target": ["recruiter", "hiring_manager"]},
    )
    assert doc.primary_document_goal == "architecture_first"
    assert doc.density_posture.header_density == "proof_dense"


def test_document_expectations_doc_forbids_unknown_top_level_keys():
    payload = _payload()
    payload["unexpected"] = "nope"
    with pytest.raises(ValueError):
        DocumentExpectationsDoc.model_validate(
            payload,
            context={"evaluator_coverage_target": ["recruiter", "hiring_manager"]},
        )


def test_document_expectations_doc_rejects_section_ids_in_audience_fields():
    payload = _payload()
    payload["audience_variants"]["recruiter"]["tilt"] = ["summary"]
    with pytest.raises(ValueError, match="abstract signal tags"):
        DocumentExpectationsDoc.model_validate(
            payload,
            context={"evaluator_coverage_target": ["recruiter", "hiring_manager"]},
        )


def test_document_expectations_doc_rejects_invalid_proof_category():
    payload = _payload()
    payload["proof_order"] = ["architecture", "delivery"]
    with pytest.raises(ValueError, match="non-canonical proof categories"):
        DocumentExpectationsDoc.model_validate(
            payload,
            context={"evaluator_coverage_target": ["recruiter", "hiring_manager"]},
        )


def test_document_expectations_doc_requires_audience_subset_of_coverage_target():
    payload = _payload()
    payload["audience_variants"]["executive_sponsor"] = {
        "tilt": ["clarity_first"],
        "must_see": ["role_fit"],
        "risky_signals": [],
        "rationale": "Invalid extra evaluator role for this context.",
    }
    with pytest.raises(ValueError, match="subset of evaluator_coverage_target"):
        DocumentExpectationsDoc.model_validate(
            payload,
            context={"evaluator_coverage_target": ["recruiter", "hiring_manager"]},
        )
