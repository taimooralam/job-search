from src.preenrich.stages.presentation_contract import (
    PresentationContractStage,
    _mark_emphasis_defaults_applied,
    _validate_truth_constrained_emphasis_rules,
)
from tests.unit.preenrich._emphasis_rules_test_data import (
    build_stage_context,
    cv_shape_expectations_payload,
    dimension_weights_payload,
    document_expectations_payload,
    emphasis_rules_payload,
    ideal_candidate_payload,
)


def _priors() -> dict:
    payload = emphasis_rules_payload()
    return {
        "rules_by_topic": {},
        "forbidden_claim_patterns": payload["forbidden_claim_patterns"],
        "credibility_ladder_rules": payload["credibility_ladder_rules"],
        "role_family_emphasis_rule_priors": {"role_family": "architecture_first"},
        "title_safety_envelope": payload["debug_context"]["title_safety_envelope"],
        "ai_claim_envelope": payload["debug_context"]["ai_claim_envelope"],
        "leadership_claim_envelope": payload["debug_context"]["leadership_claim_envelope"],
        "architecture_claim_envelope": payload["debug_context"]["architecture_claim_envelope"],
    }


def test_emphasis_rules_fail_open_on_thin_stakeholder_surface():
    payload = emphasis_rules_payload()
    payload["downgrade_rules"].append(
        {
            "rule_id": "peer_variant_soften",
            "rule_type": "suppress_audience_variant_signal",
            "topic_family": "audience_variant_specific_softening",
            "applies_to_kind": "audience_variant",
            "applies_to": "peer_technical",
            "condition": "Peer-technical preferences are thin.",
            "action": "Suppress audience-specific peer-technical softening when stakeholder evidence is thin.",
            "basis": "Thin stakeholder evidence should not overfit audience policy.",
            "evidence_refs": ["stakeholder_surface.evaluator_coverage_target"],
            "precedence": 75,
            "confidence": {"score": 0.68, "band": "medium", "basis": "test"},
        }
    )

    doc = _validate_truth_constrained_emphasis_rules(
        payload,
        evaluator_coverage_target=["recruiter", "hiring_manager", "peer_technical"],
        stakeholder_status="inferred_only",
        ai_intensity="significant",
        priors=_priors(),
        document_expectations=document_expectations_payload(),
        cv_shape_expectations=cv_shape_expectations_payload(),
        ideal_candidate=ideal_candidate_payload(),
        experience_dimension_weights=dimension_weights_payload(),
    )

    assert doc.status == "inferred_only"
    assert doc.fail_open_reason == "thin_stakeholder"
    assert "thin_stakeholder_surface" in doc.unresolved_markers
    assert "thin_stakeholder_emphasis_defaults" in doc.defaults_applied
    assert all(rule.applies_to_kind != "audience_variant" for rule in doc.downgrade_rules)


def test_emphasis_rules_default_marking_caps_confidence():
    doc = _validate_truth_constrained_emphasis_rules(
        emphasis_rules_payload(),
        evaluator_coverage_target=["recruiter"],
        stakeholder_status="completed",
        ai_intensity="significant",
        priors=_priors(),
        document_expectations=document_expectations_payload(),
        cv_shape_expectations=cv_shape_expectations_payload(),
        ideal_candidate=ideal_candidate_payload(),
        experience_dimension_weights=dimension_weights_payload(),
    )

    defaulted = _mark_emphasis_defaults_applied(
        doc,
        default_id="role_family_emphasis_rules_default",
        unresolved_marker="schema_defaulted_emphasis_rules",
        fail_open_reason="schema_repair_exhausted",
    )

    assert defaulted.status == "partial"
    assert defaulted.confidence.band == "medium"
    assert defaulted.confidence.score <= 0.79
    assert defaulted.fail_open_reason == "schema_repair_exhausted"


def test_presentation_contract_emphasis_rules_fail_open_with_partial_research():
    result = PresentationContractStage().run(build_stage_context(role_profile_status="partial"))
    emphasis = result.stage_output["truth_constrained_emphasis_rules"]
    coverage = {
        entry["topic_family"]: entry["rule_count"]
        for entry in emphasis["topic_coverage"]
    }

    assert result.stage_output["status"] in {"completed", "partial"}
    assert emphasis["status"] in {"completed", "partial", "inferred_only"}
    assert coverage["title_inflation"] >= 1
