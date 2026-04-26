from src.preenrich.blueprint_models import ExperienceDimensionWeightsDoc
from src.preenrich.stages.presentation_contract import (
    _apply_emphasis_dimension_caps,
    _validate_truth_constrained_emphasis_rules,
)
from tests.unit.preenrich._emphasis_rules_test_data import (
    clone,
    cv_shape_expectations_payload,
    dimension_weights_payload,
    document_expectations_payload,
    emphasis_rules_payload,
    ideal_candidate_payload,
)


def _priors(*, ai_intensity: str = "significant", seniority: str = "principal", direct_reports: int = 0) -> dict:
    payload = emphasis_rules_payload(ai_intensity=ai_intensity)
    return {
        "rules_by_topic": {},
        "forbidden_claim_patterns": clone(payload["forbidden_claim_patterns"]),
        "credibility_ladder_rules": clone(payload["credibility_ladder_rules"]),
        "role_family_emphasis_rule_priors": {"role_family": "architecture_first"},
        "title_safety_envelope": clone(payload["debug_context"]["title_safety_envelope"]),
        "ai_claim_envelope": {"ai_intensity": ai_intensity, "ai_intensity_cap": 20},
        "leadership_claim_envelope": {"seniority": seniority, "direct_reports": direct_reports},
        "architecture_claim_envelope": {"architecture_evidence_band": "strong"},
    }


def test_apply_emphasis_dimension_caps_clamps_dimension_weights_and_records_conflicts():
    dimension_doc = ExperienceDimensionWeightsDoc.model_validate(
        dimension_weights_payload(
            leadership_weight=12,
            overuse_risks=[
                {
                    "dimension": "leadership_enablement",
                    "reason": "seniority_mismatch",
                    "threshold": 12,
                    "mitigation": "proof_first",
                }
            ],
        ),
        context={"evaluator_coverage_target": ["recruiter"]},
    )
    emphasis_doc = _validate_truth_constrained_emphasis_rules(
        emphasis_rules_payload(leadership_cap=5),
        evaluator_coverage_target=["recruiter"],
        stakeholder_status="completed",
        ai_intensity="significant",
        priors=_priors(),
        document_expectations=document_expectations_payload(),
        cv_shape_expectations=cv_shape_expectations_payload(),
        ideal_candidate=ideal_candidate_payload(),
        experience_dimension_weights=dimension_doc.model_dump(),
    )

    updated_dimension, updated_emphasis = _apply_emphasis_dimension_caps(
        dimension_doc,
        emphasis_doc,
        evaluator_coverage_target=["recruiter"],
    )

    assert updated_dimension.overall_weights["leadership_enablement"] == 5
    assert any(event.kind == "cap_clamp" for event in updated_dimension.normalization_events)
    assert any(
        entry.conflict_source == "dimension_weights" and entry.resolution == "downgraded"
        for entry in updated_emphasis.debug_context.conflict_resolution_log
    )


def test_apply_emphasis_dimension_caps_is_noop_when_dimension_weights_already_match_leadership_envelope():
    dimension_doc = ExperienceDimensionWeightsDoc.model_validate(
        dimension_weights_payload(leadership_weight=5),
        context={"evaluator_coverage_target": ["recruiter"]},
    )
    emphasis_doc = _validate_truth_constrained_emphasis_rules(
        emphasis_rules_payload(leadership_cap=5),
        evaluator_coverage_target=["recruiter"],
        stakeholder_status="completed",
        ai_intensity="significant",
        priors=_priors(seniority="senior", direct_reports=0),
        document_expectations=document_expectations_payload(),
        cv_shape_expectations=cv_shape_expectations_payload(),
        ideal_candidate=ideal_candidate_payload(),
        experience_dimension_weights=dimension_doc.model_dump(),
    )

    updated_dimension, updated_emphasis = _apply_emphasis_dimension_caps(
        dimension_doc,
        emphasis_doc,
        evaluator_coverage_target=["recruiter"],
    )

    assert updated_dimension.overall_weights["leadership_enablement"] == 5
    assert [
        entry
        for entry in updated_emphasis.debug_context.conflict_resolution_log
        if entry.conflict_source == "dimension_weights"
    ] == []


def test_validate_emphasis_rules_suppresses_ai_authorization_above_adjacent_intensity():
    payload = emphasis_rules_payload(ai_intensity="adjacent")
    payload["global_rules"].append(
        {
            "rule_id": "ai_forbid_adjacent",
            "rule_type": "forbid_without_direct_proof",
            "topic_family": "ai_claims",
            "applies_to_kind": "section",
            "applies_to": "ai_highlights",
            "condition": "AI depth is adjacent or absent.",
            "action": "Do not surface a dedicated AI highlights section without direct proof.",
            "basis": "Low-AI roles fail closed on dedicated AI depth framing.",
            "evidence_refs": ["classification.ai_taxonomy.intensity"],
            "precedence": 80,
            "confidence": {"score": 0.74, "band": "medium", "basis": "test"},
        }
    )
    payload["topic_coverage"] = [
        entry if entry["topic_family"] != "ai_claims" else {**entry, "rule_count": 2}
        for entry in payload["topic_coverage"]
    ]

    doc = _validate_truth_constrained_emphasis_rules(
        payload,
        evaluator_coverage_target=["recruiter", "hiring_manager"],
        stakeholder_status="completed",
        ai_intensity="adjacent",
        priors=_priors(ai_intensity="adjacent"),
        document_expectations=document_expectations_payload(),
        cv_shape_expectations=cv_shape_expectations_payload(ai_section_policy="embedded_only"),
        ideal_candidate=ideal_candidate_payload(),
        experience_dimension_weights=dimension_weights_payload(),
    )

    assert doc.status == "partial"
    assert doc.fail_open_reason == "ai_authorization_above_intensity"
    assert all(
        not (rule.topic_family == "ai_claims" and rule.rule_type == "allowed_if_evidenced")
        for rule in list(doc.global_rules) + list(doc.allowed_if_evidenced) + list(doc.omit_rules)
    )


def test_validate_emphasis_rules_suppresses_leadership_authorization_above_envelope():
    payload = emphasis_rules_payload()
    payload["allowed_if_evidenced"].append(
        {
            "rule_id": "leadership_allow_bad",
            "rule_type": "allowed_if_evidenced",
            "topic_family": "leadership_scope",
            "applies_to_kind": "proof",
            "applies_to": "leadership",
            "condition": "Leadership evidence is partial.",
            "action": "Allow leadership claims whenever leadership language appears in the JD.",
            "basis": "bad test rule",
            "evidence_refs": ["jd_facts.merged_view.responsibilities"],
            "precedence": 20,
            "confidence": {"score": 0.7, "band": "medium", "basis": "test"},
        }
    )
    payload["topic_coverage"] = [
        entry if entry["topic_family"] != "leadership_scope" else {**entry, "rule_count": 2}
        for entry in payload["topic_coverage"]
    ]

    doc = _validate_truth_constrained_emphasis_rules(
        payload,
        evaluator_coverage_target=["recruiter"],
        stakeholder_status="completed",
        ai_intensity="significant",
        priors=_priors(seniority="senior", direct_reports=0),
        document_expectations=document_expectations_payload(),
        cv_shape_expectations=cv_shape_expectations_payload(),
        ideal_candidate=ideal_candidate_payload(),
        experience_dimension_weights=dimension_weights_payload(),
    )

    assert doc.status == "partial"
    assert doc.fail_open_reason == "leadership_authorization_above_envelope"
    assert all(rule.rule_id != "leadership_allow_bad" for rule in doc.allowed_if_evidenced)
