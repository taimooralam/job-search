from __future__ import annotations

from src.preenrich.blueprint_models import (
    normalize_cv_shape_expectations_payload,
    normalize_document_expectations_payload,
)


def test_document_expectations_normalizer_maps_aliases_and_retains_unknown_fields():
    payload = {
        "goal": "Architecture-First",
        "audiences": {
            "hiring_manager": {
                "communication_style_tag": "evidence_first",
                "must_see": ["architecture_judgment"],
                "risky_signals": ["hype_header"],
                "rationale": "Hiring manager wants rigor.",
                "extra_note": "keep me",
            }
        },
        "proof_categories": ["architecture", "metric"],
        "anti_patterns": ["tool_list_cv"],
        "tone_posture": {"primary_tone": "architect_first", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
        "density_posture": {"overall_density": "high", "header_density": "proof_dense", "section_density_bias": []},
        "keyword_balance": {"target_keyword_pressure": "high", "ats_mirroring_bias": "balanced", "semantic_expansion_bias": "balanced"},
        "rationale": "Candidate-agnostic thesis.",
        "confidence": {"score": 0.8, "band": "high", "basis": "signals"},
        "evidence": [],
        "unexpected_wrapper": {"foo": "bar"},
    }

    normalized = normalize_document_expectations_payload(
        payload,
        evaluator_coverage_target=["hiring_manager"],
        allowed_company_names=["Acme"],
        allowed_company_domain="acme.example.com",
        jd_excerpt="Architecture-heavy role.",
    )

    assert normalized["primary_document_goal"] == "architecture_first"
    assert normalized["proof_order"] == ["architecture", "metric"]
    assert normalized["audience_variants"]["hiring_manager"]["tilt"] == ["evidence_first"]
    retained_keys = [item["key"] for item in normalized["debug_context"]["richer_output_retained"]]
    assert "audience_variants.hiring_manager.extra_note" in retained_keys
    assert "unexpected_wrapper" in retained_keys


def test_cv_shape_normalizer_coerces_shape_and_section_emphasis_map():
    payload = {
        "shape": {"sections": ["header", "summary", "experience"]},
        "section_emphasis": {
            "summary": {
                "emphasis": "highlight",
                "categories": ["architecture"],
                "length_bias": "short",
                "ordering_bias": "outcome_first",
                "rationale": "Fast thesis.",
            }
        },
        "ai_policy": "embedded_only",
        "header_shape": {"density": "balanced", "include_elements": ["name"], "proof_line_policy": "optional", "differentiator_line_policy": "omit"},
        "counts": {
            "key_achievements_min": 2,
            "key_achievements_max": 4,
            "core_competencies_min": 5,
            "core_competencies_max": 8,
            "summary_sentences_min": 2,
            "summary_sentences_max": 3,
        },
        "ats_envelope": {"pressure": "standard", "format_rules": ["single_column"], "keyword_placement_bias": "balanced"},
        "evidence_density": "medium",
        "seniority_signal_strength": "medium",
        "compression_rules": ["compress_core_competencies_first"],
        "omission_rules": ["omit_publications_if_unused_in_role_family"],
        "rationale": "Conservative shape.",
        "confidence": {"score": 0.6, "band": "medium", "basis": "defaults"},
        "evidence": [],
    }

    normalized = normalize_cv_shape_expectations_payload(
        payload,
        allowed_company_names=["Acme"],
        allowed_company_domain="acme.example.com",
        jd_excerpt="General role.",
    )

    assert normalized["section_order"] == ["header", "summary", "experience"]
    assert normalized["section_emphasis"][0]["section_id"] == "summary"
    assert normalized["section_emphasis"][0]["focus_categories"] == ["architecture"]
    assert normalized["ai_section_policy"] == "embedded_only"
    assert "alias:shape.sections->section_order" in normalized["debug_context"]["normalization_events"]
    assert "coerced:section_emphasis_map->list" in normalized["debug_context"]["normalization_events"]


def test_document_expectations_normalizer_flags_candidate_leakage():
    payload = {
        "primary_document_goal": "balanced",
        "audience_variants": {
            "hiring_manager": {
                "tilt": ["clarity_first"],
                "must_see": ["ownership_scope"],
                "risky_signals": [],
                "rationale": "I led a 40% YoY transformation at Contoso.",
            }
        },
        "proof_order": ["metric"],
        "anti_patterns": ["tool_list_cv"],
        "tone_posture": {"primary_tone": "balanced", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
        "density_posture": {"overall_density": "medium", "header_density": "balanced", "section_density_bias": []},
        "keyword_balance": {"target_keyword_pressure": "medium", "ats_mirroring_bias": "balanced", "semantic_expansion_bias": "balanced"},
        "rationale": "I built this.",
        "confidence": {"score": 0.7, "band": "high", "basis": "bad"},
        "evidence": [],
    }

    normalized = normalize_document_expectations_payload(
        payload,
        evaluator_coverage_target=["hiring_manager"],
        allowed_company_names=["Acme"],
        allowed_company_domain="acme.example.com",
        jd_excerpt="No achievement numbers in JD.",
    )

    assert normalized["status"] == "partial"
    rejected = normalized["debug_context"]["rejected_output"]
    assert any("candidate_leakage" in item["reason"] for item in rejected)


def test_normalizer_rejects_invalid_proof_category_and_section_id():
    doc_normalized = normalize_document_expectations_payload(
        {
            "primary_document_goal": "balanced",
            "audience_variants": {},
            "proof_order": ["architecture", "delivery"],
            "anti_patterns": ["tool_list_cv"],
            "tone_posture": {"primary_tone": "balanced", "hype_tolerance": "low", "narrative_tolerance": "medium", "formality": "neutral"},
            "density_posture": {"overall_density": "medium", "header_density": "balanced", "section_density_bias": []},
            "keyword_balance": {"target_keyword_pressure": "medium", "ats_mirroring_bias": "balanced", "semantic_expansion_bias": "balanced"},
            "confidence": {"score": 0.5, "band": "medium", "basis": "defaults"},
            "evidence": [],
        },
        evaluator_coverage_target=[],
        allowed_company_names=["Acme"],
        allowed_company_domain="acme.example.com",
        jd_excerpt="",
    )
    assert any(item["reason"] == "invalid_proof_category:delivery" for item in doc_normalized["debug_context"]["rejected_output"])

    shape_normalized = normalize_cv_shape_expectations_payload(
        {
            "header_shape": {"density": "balanced", "include_elements": ["name"], "proof_line_policy": "optional", "differentiator_line_policy": "omit"},
            "section_order": ["header", "overview", "experience"],
            "section_emphasis": [],
            "ai_section_policy": "embedded_only",
            "counts": {"key_achievements_min": 1, "key_achievements_max": 2, "core_competencies_min": 4, "core_competencies_max": 6, "summary_sentences_min": 2, "summary_sentences_max": 3},
            "ats_envelope": {"pressure": "standard", "format_rules": ["single_column"], "keyword_placement_bias": "balanced"},
            "evidence_density": "medium",
            "seniority_signal_strength": "medium",
            "compression_rules": [],
            "omission_rules": [],
            "confidence": {"score": 0.5, "band": "medium", "basis": "defaults"},
            "evidence": [],
        },
        allowed_company_names=["Acme"],
        allowed_company_domain="acme.example.com",
        jd_excerpt="",
    )
    assert any(item["reason"] == "invalid_section_id:overview" for item in shape_normalized["debug_context"]["rejected_output"])
