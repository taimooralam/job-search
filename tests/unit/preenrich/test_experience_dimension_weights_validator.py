import pytest

from src.preenrich.stages.presentation_contract import _validate_experience_dimension_weights


def _payload() -> dict:
    return {
        "status": "completed",
        "source_scope": "jd_plus_research_plus_stakeholder",
        "dimension_enum_version": "v1",
        "overall_weights": {
            "hands_on_implementation": 8,
            "architecture_system_design": 8,
            "leadership_enablement": 24,
            "tools_technology_stack": 6,
            "methodology_operating_model": 6,
            "business_impact": 10,
            "stakeholder_communication": 6,
            "ai_ml_depth": 30,
            "domain_context": 2,
            "quality_risk_reliability": 2,
            "delivery_execution_pace": 1,
            "platform_scaling_change": 1,
        },
        "stakeholder_variant_weights": {
            "recruiter": {
                "hands_on_implementation": 10,
                "architecture_system_design": 14,
                "leadership_enablement": 10,
                "tools_technology_stack": 10,
                "methodology_operating_model": 8,
                "business_impact": 14,
                "stakeholder_communication": 10,
                "ai_ml_depth": 10,
                "domain_context": 4,
                "quality_risk_reliability": 4,
                "delivery_execution_pace": 4,
                "platform_scaling_change": 2,
            }
        },
        "minimum_visible_dimensions": ["architecture_system_design", "ai_ml_depth"],
        "overuse_risks": [
            {
                "dimension": "leadership_enablement",
                "reason": "seniority_mismatch",
                "threshold": 18,
                "mitigation": "proof_first",
            }
        ],
        "rationale": "test",
        "unresolved_markers": [],
        "defaults_applied": [],
        "normalization_events": [],
        "confidence": {"score": 0.88, "band": "high", "basis": "test"},
        "evidence": [],
        "notes": [],
        "debug_context": {
            "input_summary": {"role_family": "architecture_first"},
            "role_family_weight_priors": {},
            "evaluator_dimension_pressure": {},
            "ai_intensity_cap": 15,
            "architecture_evidence_band": "partial",
            "leadership_evidence_band": "none",
            "defaults_applied": [],
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
        },
    }


def test_dimension_weights_validator_enforces_caps_and_must_signal_floor():
    doc = _validate_experience_dimension_weights(
        _payload(),
        evaluator_coverage_target=["recruiter", "hiring_manager"],
        ai_intensity="adjacent",
        priors={
            "ai_intensity_cap": 15,
            "architecture_evidence_band": "partial",
            "leadership_evidence_band": "none",
            "seniority_band": "senior",
            "role_family": "architecture_first",
            "proof_category_dimension_pressure": {"business_impact": 2},
            "evaluator_dimension_pressure": {"recruiter": {"business_impact": 2}},
            "must_signal_dimensions": ["architecture_system_design"],
            "ideal_de_emphasize_dimensions": ["leadership_enablement"],
        },
        document_expectations={"primary_document_goal": "architecture_first"},
        cv_shape_expectations={
            "section_emphasis": [
                {"section_id": "summary", "focus_categories": ["architecture"]},
                {"section_id": "experience", "focus_categories": ["metric"]},
            ]
        },
        ideal_candidate={
            "must_signal": [{"tag": "architecture_judgment"}],
            "de_emphasize": [{"tag": "leadership_scope"}],
            "proof_ladder": [{"proof_category": "architecture"}],
        },
    )

    assert doc.overall_weights["ai_ml_depth"] <= 15
    assert doc.overall_weights["architecture_system_design"] >= 10
    assert doc.overall_weights["leadership_enablement"] <= 5
    assert sum(doc.overall_weights.values()) == 100
    assert any(event.kind == "cap_clamp" for event in doc.normalization_events)


def test_dimension_weights_validator_caps_confidence_when_defaults_applied():
    payload = _payload()
    payload["defaults_applied"] = ["role_family_dimension_weights_default"]

    doc = _validate_experience_dimension_weights(
        payload,
        evaluator_coverage_target=["recruiter"],
        ai_intensity="significant",
        priors={
            "ai_intensity_cap": 28,
            "architecture_evidence_band": "strong",
            "leadership_evidence_band": "partial",
            "seniority_band": "senior",
            "role_family": "architecture_first",
            "proof_category_dimension_pressure": {},
            "evaluator_dimension_pressure": {},
            "must_signal_dimensions": [],
            "ideal_de_emphasize_dimensions": [],
        },
        document_expectations={},
        cv_shape_expectations={"section_emphasis": []},
        ideal_candidate={"must_signal": [], "de_emphasize": [], "proof_ladder": []},
    )

    assert doc.confidence.band == "medium"
    assert doc.confidence.score <= 0.79


def test_dimension_weights_validator_rebalances_focus_categories_in_fail_open_mode():
    payload = _payload()
    payload["overall_weights"] = {
        "hands_on_implementation": 10,
        "architecture_system_design": 10,
        "leadership_enablement": 5,
        "tools_technology_stack": 10,
        "methodology_operating_model": 10,
        "business_impact": 5,
        "stakeholder_communication": 10,
        "ai_ml_depth": 15,
        "domain_context": 5,
        "quality_risk_reliability": 5,
        "delivery_execution_pace": 7,
        "platform_scaling_change": 8,
    }

    kwargs = {
        "evaluator_coverage_target": ["recruiter", "hiring_manager"],
        "ai_intensity": "adjacent",
        "priors": {
            "ai_intensity_cap": 15,
            "architecture_evidence_band": "partial",
            "leadership_evidence_band": "none",
            "seniority_band": "senior",
            "role_family": "architecture_first",
            "proof_category_dimension_pressure": {},
            "evaluator_dimension_pressure": {},
            "must_signal_dimensions": ["architecture_system_design"],
            "ideal_de_emphasize_dimensions": ["leadership_enablement"],
        },
        "document_expectations": {"primary_document_goal": "architecture_first"},
        "cv_shape_expectations": {
            "section_emphasis": [
                {"section_id": "experience", "focus_categories": ["metric"]},
            ]
        },
        "ideal_candidate": {
            "must_signal": [{"tag": "architecture_judgment"}],
            "de_emphasize": [{"tag": "leadership_scope"}],
            "proof_ladder": [{"proof_category": "architecture"}],
        },
    }

    with pytest.raises(ValueError, match="business_impact"):
        _validate_experience_dimension_weights(payload, **kwargs)

    doc = _validate_experience_dimension_weights(
        payload,
        allow_fail_open_rebalance=True,
        **kwargs,
    )

    assert doc.overall_weights["business_impact"] >= 6
    assert any(
        event.kind == "floor_boost" and event.reason == "section_focus_floor"
        for event in doc.normalization_events
    )


def test_dimension_weights_validator_caps_leadership_for_zero_report_senior_ic():
    payload = _payload()
    payload["overall_weights"]["leadership_enablement"] = 9

    doc = _validate_experience_dimension_weights(
        payload,
        evaluator_coverage_target=["recruiter", "hiring_manager"],
        ai_intensity="adjacent",
        priors={
            "ai_intensity_cap": 15,
            "architecture_evidence_band": "partial",
            "leadership_evidence_band": "none",
            "seniority_band": "senior",
            "direct_reports": 0,
            "role_family": "architecture_first",
            "proof_category_dimension_pressure": {},
            "evaluator_dimension_pressure": {},
            "must_signal_dimensions": ["architecture_system_design"],
            "ideal_de_emphasize_dimensions": [],
        },
        document_expectations={"primary_document_goal": "architecture_first"},
        cv_shape_expectations={"section_emphasis": []},
        ideal_candidate={"must_signal": [], "de_emphasize": [], "proof_ladder": []},
    )

    assert doc.overall_weights["leadership_enablement"] <= 5
    assert any(
        event.kind == "cap_clamp"
        and event.path == "leadership_enablement"
        for event in doc.normalization_events
    )
