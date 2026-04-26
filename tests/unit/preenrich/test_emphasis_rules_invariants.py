import pytest

from src.preenrich.blueprint_models import PresentationContractDoc, TruthConstrainedEmphasisRulesDoc
from tests.unit.preenrich._emphasis_rules_test_data import (
    clone,
    emphasis_rules_payload,
    presentation_contract_payload,
)


def _contract() -> dict:
    return presentation_contract_payload()


def _validate_contract(payload: dict) -> PresentationContractDoc:
    return PresentationContractDoc.model_validate(
        payload,
        context={
            "ai_intensity": "significant",
            "document_header_density": "proof_dense",
            "evaluator_coverage_target": ["recruiter", "hiring_manager", "peer_technical"],
            "expected_title_strategy": "closest_truthful",
        },
    )


def test_emphasis_rules_invariants_accept_canonical_contract():
    doc = _validate_contract(_contract())

    assert doc.truth_constrained_emphasis_rules.status == "completed"
    assert doc.cv_shape_expectations.title_strategy == "closest_truthful"


def test_emphasis_rules_invariant_ier1_rejects_invalid_applies_to_surface():
    payload = emphasis_rules_payload()
    payload["allowed_if_evidenced"][0]["applies_to_kind"] = "proof"
    payload["allowed_if_evidenced"][0]["applies_to"] = "header"

    with pytest.raises(Exception):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)


def test_emphasis_rules_invariant_ier2_rejects_title_envelope_mismatch():
    payload = _contract()
    payload["truth_constrained_emphasis_rules"]["debug_context"]["title_safety_envelope"]["title_strategy"] = "exact_match"

    with pytest.raises(Exception, match="title envelope"):
        _validate_contract(payload)


def test_emphasis_rules_invariant_ier3_rejects_ai_authorization_above_intensity():
    payload = _contract()
    payload["truth_constrained_emphasis_rules"]["debug_context"]["ai_claim_envelope"]["ai_intensity"] = "adjacent"

    with pytest.raises(Exception, match="AI claims"):
        _validate_contract(payload)


def test_emphasis_rules_invariant_ier4_rejects_caps_below_current_weight_without_overuse():
    payload = _contract()
    payload["truth_constrained_emphasis_rules"]["global_rules"][1]["cap_value"] = 5

    with pytest.raises(Exception, match="overuse risk"):
        _validate_contract(payload)


def test_emphasis_rules_invariant_ier5_rejects_forbidden_patterns_that_suppress_top_proofs():
    payload = _contract()
    payload["truth_constrained_emphasis_rules"]["forbidden_claim_patterns"][0]["pattern"] = "architecture authority"

    with pytest.raises(Exception, match="top two proof categories"):
        _validate_contract(payload)


def test_emphasis_rules_invariant_ier6_rejects_must_signal_contradictions_without_unresolved_marker():
    payload = _contract()
    payload["truth_constrained_emphasis_rules"]["omit_rules"].append(
        {
            "rule_id": "omit_architecture_must_signal",
            "rule_type": "omit_if_weak",
            "topic_family": "architecture_claims",
            "applies_to_kind": "proof",
            "applies_to": "architecture",
            "condition": "Architecture evidence is weak.",
            "action": "Omit architecture claims when evidence is weak.",
            "basis": "test",
            "evidence_refs": ["pain_point_intelligence.proof_map"],
            "precedence": 65,
            "confidence": {"score": 0.7, "band": "medium", "basis": "test"},
        }
    )

    with pytest.raises(Exception, match="must_signal"):
        _validate_contract(payload)


def test_emphasis_rules_invariant_ier7_requires_allowed_companion_for_should_signal_omission():
    payload = _contract()
    payload["truth_constrained_emphasis_rules"]["allowed_if_evidenced"] = [
        rule
        for rule in payload["truth_constrained_emphasis_rules"]["allowed_if_evidenced"]
        if rule["applies_to"] != "ai"
    ]
    payload["truth_constrained_emphasis_rules"]["omit_rules"].append(
        {
            "rule_id": "omit_ai_without_companion",
            "rule_type": "omit_if_weak",
            "topic_family": "ai_claims",
            "applies_to_kind": "proof",
            "applies_to": "ai",
            "condition": "AI proof is weak.",
            "action": "Omit AI claims when proof is weak.",
            "basis": "test",
            "evidence_refs": ["classification.ai_taxonomy.intensity"],
            "precedence": 65,
            "confidence": {"score": 0.7, "band": "medium", "basis": "test"},
        }
    )
    payload["truth_constrained_emphasis_rules"]["topic_coverage"] = [
        entry
        for entry in payload["truth_constrained_emphasis_rules"]["topic_coverage"]
        if entry["topic_family"] != "ai_claims"
    ] + [{"topic_family": "ai_claims", "rule_count": 1, "source": "llm"}]

    with pytest.raises(Exception, match="should_signal"):
        _validate_contract(payload)


def test_emphasis_rules_invariant_ier8_requires_de_emphasize_reflection():
    payload = _contract()
    payload["truth_constrained_emphasis_rules"]["downgrade_rules"] = [
        rule
        for rule in payload["truth_constrained_emphasis_rules"]["downgrade_rules"]
        if rule["applies_to"] != "process"
    ]

    with pytest.raises(Exception, match="de_emphasize"):
        _validate_contract(payload)


def test_emphasis_rules_invariant_ier9_requires_mandatory_topic_coverage():
    payload = emphasis_rules_payload()
    payload["topic_coverage"] = [
        entry
        for entry in payload["topic_coverage"]
        if entry["topic_family"] != "ai_claims"
    ]

    with pytest.raises(Exception, match="mandatory topic coverage"):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)


def test_emphasis_rules_invariant_ier10_requires_unique_rule_ids():
    payload = emphasis_rules_payload()
    payload["global_rules"][0]["rule_id"] = payload["global_rules"][1]["rule_id"]

    with pytest.raises(Exception, match="rule_id"):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)


def test_emphasis_rules_invariant_ier11_requires_section_rules_to_target_section_order():
    payload = _contract()
    payload["truth_constrained_emphasis_rules"]["section_rules"]["projects"] = clone(
        payload["truth_constrained_emphasis_rules"]["section_rules"]["experience"]
    )
    payload["truth_constrained_emphasis_rules"]["section_rules"]["projects"][0]["applies_to"] = "projects"
    payload["truth_constrained_emphasis_rules"]["section_rules"]["projects"][0]["rule_id"] = "credibility_marker_projects"
    payload["truth_constrained_emphasis_rules"]["topic_coverage"] = clone(
        payload["truth_constrained_emphasis_rules"]["topic_coverage"]
    )

    with pytest.raises(Exception, match="section rules"):
        _validate_contract(payload)


def test_emphasis_rules_invariant_ier12_rejects_rule_confidence_above_subdocument_confidence():
    payload = emphasis_rules_payload(confidence_band="medium", confidence_score=0.79)
    payload["global_rules"][0]["confidence"] = {"score": 0.85, "band": "high", "basis": "too_high"}

    with pytest.raises(Exception, match="rule confidence"):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)


def test_emphasis_rules_invariant_ier13_requires_credibility_ladder_fallback_resolution():
    payload = emphasis_rules_payload()
    payload["credibility_ladder_rules"][0]["fallback_rule_id"] = "missing_rule"

    with pytest.raises(Exception, match="fallback_rule_id"):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)


def test_emphasis_rules_invariant_ier14_rejects_regex_patterns_outside_safe_subset():
    payload = emphasis_rules_payload()
    payload["forbidden_claim_patterns"][1]["pattern"] = "(?=ai)visionary"

    with pytest.raises(Exception, match="bounded regex"):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)
