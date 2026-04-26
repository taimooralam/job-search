import pytest

from src.preenrich.blueprint_models import DIMENSION_ENUM_VERSION, ExperienceDimensionWeightsDoc


def _payload() -> dict:
    return {
        "status": "completed",
        "source_scope": "jd_plus_research_plus_stakeholder",
        "dimension_enum_version": DIMENSION_ENUM_VERSION,
        "prompt_version": "P-experience-dimension-weights@v1",
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
        "minimum_visible_dimensions": [
            "architecture_system_design",
            "business_impact",
            "ai_ml_depth",
        ],
        "overuse_risks": [
            {
                "dimension": "leadership_enablement",
                "reason": "seniority_mismatch",
                "threshold": 18,
                "mitigation": "proof_first",
            }
        ],
        "rationale": "Lead with architecture, business impact, and AI depth.",
        "unresolved_markers": [],
        "defaults_applied": [],
        "normalization_events": [],
        "confidence": {"score": 0.75, "band": "medium", "basis": "test"},
        "evidence": [],
        "notes": [],
        "debug_context": {
            "input_summary": {"role_family": "architecture_first"},
            "role_family_weight_priors": {},
            "evaluator_dimension_pressure": {},
            "ai_intensity_cap": 28,
            "architecture_evidence_band": "strong",
            "leadership_evidence_band": "partial",
            "defaults_applied": [],
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
        },
    }


def test_experience_dimension_weights_schema_accepts_canonical_payload():
    doc = ExperienceDimensionWeightsDoc.model_validate(
        _payload(),
        context={"evaluator_coverage_target": ["recruiter", "hiring_manager"]},
    )

    assert doc.dimension_enum_version == DIMENSION_ENUM_VERSION
    assert sum(doc.overall_weights.values()) == 100
    assert doc.minimum_visible_dimensions == [
        "architecture_system_design",
        "business_impact",
        "ai_ml_depth",
    ]


def test_experience_dimension_weights_schema_forbids_extra_top_level_fields():
    payload = _payload()
    payload["unexpected"] = True

    with pytest.raises(Exception):
        ExperienceDimensionWeightsDoc.model_validate(
            payload,
            context={"evaluator_coverage_target": ["recruiter"]},
        )
