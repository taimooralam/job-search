from src.preenrich.blueprint_models import normalize_experience_dimension_weights_payload


def test_dimension_weights_normalizer_coerces_aliases_and_float_looking_ints():
    payload = {
        "status": "completed",
        "scope": "jd_plus_research",
        "overall": {
            "architecture": "20.0",
            "ai": 12.0,
            "business_impact": 14,
            "hands_on_implementation": 18,
            "leadership": 6,
            "stakeholder": 8,
            "tools_stack": 6,
            "methodology": 4,
            "domain": 4,
            "quality_reliability": 4,
            "delivery": 2,
            "platform_scaling": 2,
            "made_up_dimension": 5,
        },
        "variants": {
            "recruiter": {"architecture": 30, "business_impact": 70},
            "unknown_role": {"architecture": 100},
        },
        "minimum_visible": ["architecture", "ai", "made_up_dimension"],
        "rationale": "I led this transformation personally.",
    }

    normalized = normalize_experience_dimension_weights_payload(
        payload,
        evaluator_coverage_target=["recruiter", "hiring_manager"],
        jd_excerpt="Architecture-heavy AI platform role.",
    )

    assert normalized["source_scope"] == "jd_plus_research"
    assert normalized["overall_weights"]["architecture_system_design"] == 20
    assert normalized["overall_weights"]["ai_ml_depth"] == 12
    assert "made_up_dimension" not in normalized["overall_weights"]
    assert normalized["stakeholder_variant_weights"]["recruiter"]["architecture_system_design"] == 30
    assert "unknown_role" not in normalized["stakeholder_variant_weights"]
    assert normalized["minimum_visible_dimensions"] == [
        "architecture_system_design",
        "ai_ml_depth",
    ]
    assert normalized["status"] == "partial"
    rejected = normalized["debug_context"]["rejected_output"]
    assert any(item["reason"] == "unknown_dimension" for item in rejected)
    assert any(item["reason"] == "invalid_evaluator_role" for item in rejected)


def test_dimension_weights_normalizer_rejects_half_float_weights():
    payload = {
        "overall_weights": {
            "architecture_system_design": "12.5",
            "hands_on_implementation": 20,
        }
    }

    normalized = normalize_experience_dimension_weights_payload(payload)

    assert "architecture_system_design" not in normalized["overall_weights"]
    assert any(
        item["path"] == "overall_weights.architecture_system_design"
        for item in normalized["debug_context"]["rejected_output"]
    )
