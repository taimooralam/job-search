from __future__ import annotations

import pytest

from src.preenrich.blueprint_models import CvShapeExpectationsDoc


def _payload() -> dict:
    return {
        "status": "completed",
        "title_strategy": "closest_truthful",
        "header_shape": {
            "density": "proof_dense",
            "include_elements": ["name", "current_or_target_title", "links", "proof_line"],
            "proof_line_policy": "required",
            "differentiator_line_policy": "optional",
        },
        "section_order": ["header", "summary", "key_achievements", "core_competencies", "ai_highlights", "experience", "education"],
        "section_emphasis": [
            {
                "section_id": "summary",
                "emphasis": "highlight",
                "focus_categories": ["architecture", "metric"],
                "length_bias": "short",
                "ordering_bias": "outcome_first",
                "rationale": "Fast proof summary.",
            },
            {
                "section_id": "experience",
                "emphasis": "highlight",
                "focus_categories": ["architecture", "leadership"],
                "length_bias": "long",
                "ordering_bias": "outcome_first",
                "rationale": "Main proof surface.",
            },
        ],
        "ai_section_policy": "required",
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
            "format_rules": ["single_column", "no_tables_in_experience", "plain_bullets"],
            "keyword_placement_bias": "top_heavy",
        },
        "evidence_density": "high",
        "seniority_signal_strength": "high",
        "compression_rules": ["compress_core_competencies_first", "compress_certifications_second"],
        "omission_rules": ["omit_publications_if_unused_in_role_family"],
        "unresolved_markers": [],
        "rationale": "Proof-dense structure.",
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
        "confidence": {"score": 0.8, "band": "high", "basis": "Consistent with thesis and AI intensity."},
        "evidence": [{"claim": "Shape is supported by thesis and AI intensity.", "source_ids": ["document_expectations.primary_document_goal"]}],
    }


def test_cv_shape_expectations_doc_accepts_canonical_payload():
    doc = CvShapeExpectationsDoc.model_validate(
        _payload(),
        context={"ai_intensity": "significant", "document_header_density": "proof_dense"},
    )
    assert doc.header_shape.density == "proof_dense"
    assert doc.section_order[0] == "header"


def test_cv_shape_expectations_doc_rejects_invalid_section_id():
    payload = _payload()
    payload["section_order"] = ["header", "summary", "overview", "experience"]
    with pytest.raises(ValueError, match="non-canonical section ids"):
        CvShapeExpectationsDoc.model_validate(
            payload,
            context={"ai_intensity": "significant", "document_header_density": "proof_dense"},
        )


def test_cv_shape_expectations_doc_requires_section_emphasis_subset_of_section_order():
    payload = _payload()
    payload["section_emphasis"][1]["section_id"] = "projects"
    with pytest.raises(ValueError, match="subset of section_order"):
        CvShapeExpectationsDoc.model_validate(
            payload,
            context={"ai_intensity": "significant", "document_header_density": "proof_dense"},
        )


def test_cv_shape_expectations_doc_rejects_invalid_ai_policy_for_intensity():
    payload = _payload()
    payload["ai_section_policy"] = "required"
    with pytest.raises(ValueError, match="incompatible with ai_intensity=none"):
        CvShapeExpectationsDoc.model_validate(
            payload,
            context={"ai_intensity": "none", "document_header_density": "proof_dense"},
        )


def test_cv_shape_expectations_doc_rejects_invalid_count_ranges():
    payload = _payload()
    payload["counts"]["summary_sentences_min"] = 5
    payload["counts"]["summary_sentences_max"] = 4
    with pytest.raises(ValueError, match="summary_sentences_min must be <= summary_sentences_max"):
        CvShapeExpectationsDoc.model_validate(
            payload,
            context={"ai_intensity": "significant", "document_header_density": "proof_dense"},
        )


def test_cv_shape_expectations_doc_requires_header_density_alignment():
    payload = _payload()
    with pytest.raises(ValueError, match="header_shape.density must match"):
        CvShapeExpectationsDoc.model_validate(
            payload,
            context={"ai_intensity": "significant", "document_header_density": "balanced"},
        )
