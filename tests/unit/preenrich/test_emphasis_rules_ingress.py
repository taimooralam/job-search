from src.preenrich.blueprint_models import normalize_truth_constrained_emphasis_rules_payload
from tests.unit.preenrich._emphasis_rules_test_data import emphasis_rules_payload


def test_emphasis_rules_normalizer_handles_aliases_and_applies_to_prefixes():
    payload = {
        "status": "completed",
        "scope": "jd_plus_research_plus_stakeholder",
        "rules": [
            {
                "topic_family": "architecture_claims",
                "rule_type": "allowed_if_evidenced",
                "applies_to": "proof:architecture",
                "condition": "Architecture proof is direct.",
                "action": "Allow architecture claims when direct evidence is visible.",
                "rationale": "Architecture claims require direct proof.",
                "source_refs": ["pain_point_intelligence.proof_map"],
                "extra_field": "retain me",
            }
        ],
        "forbidden_patterns": [
            {
                "pattern": "chief ai officer",
                "reason": "inflation",
                "evidence_refs": ["ideal_candidate_presentation_model.acceptable_titles"],
            },
            {
                "pattern": "(?:llm|genai)\\s+visionary",
                "pattern_kind": "regex_safe",
                "reason": "inflation",
                "evidence_refs": ["classification.ai_taxonomy.intensity"],
            },
        ],
        "credibility_chain": [
            {
                "ladder_id": "main",
                "audience": "all",
                "proof_chain": ["architecture", "metric"],
                "fallback_rule_id": "tcer_architecture_claims_architecture_fake01",
                "source_refs": ["pain_point_intelligence.proof_map"],
            }
        ],
        "future_field": {"keep": "debug"},
    }

    normalized = normalize_truth_constrained_emphasis_rules_payload(
        payload,
        evaluator_coverage_target=["recruiter", "hiring_manager"],
        jd_excerpt="Architecture-heavy role.",
    )

    assert normalized["source_scope"] == "jd_plus_research_plus_stakeholder"
    assert normalized["allowed_if_evidenced"][0]["applies_to_kind"] == "proof"
    assert normalized["allowed_if_evidenced"][0]["applies_to"] == "architecture"
    assert normalized["forbidden_claim_patterns"][1]["pattern_kind"] == "regex_safe"
    assert normalized["credibility_ladder_rules"][0]["applies_to_audience"] == "all"
    retained = normalized["debug_context"]["richer_output_retained"]
    assert any(item["key"] == "global_rules.extra_field" for item in retained)
    assert any(item["key"] == "future_field" for item in retained)


def test_emphasis_rules_normalizer_rejects_bare_string_ambiguity():
    payload = {
        "rules": [
            {
                "topic_family": "architecture_claims",
                "rule_type": "allowed_if_evidenced",
                "applies_to": "architecture",
                "condition": "Architecture proof is direct.",
                "action": "Allow architecture claims when direct evidence is visible.",
                "basis": "Architecture claims require direct proof.",
                "evidence_refs": ["pain_point_intelligence.proof_map"],
            }
        ]
    }

    normalized = normalize_truth_constrained_emphasis_rules_payload(payload)

    assert normalized["allowed_if_evidenced"] == []
    assert any(
        item["reason"] == "applies_to_kind_value_mismatch"
        for item in normalized["debug_context"]["rejected_output"]
    )


def test_emphasis_rules_normalizer_collapses_duplicates_and_resolves_conflicts():
    payload = {
        "allowed_if_evidenced": [
            {
                "topic_family": "ai_claims",
                "rule_type": "allowed_if_evidenced",
                "applies_to_kind": "proof",
                "applies_to": "ai",
                "condition": "AI proof is direct.",
                "action": "Allow AI claims with proof.",
                "basis": "direct proof only",
                "evidence_refs": ["classification.ai_taxonomy.intensity"],
                "precedence": 20,
            },
            {
                "topic_family": "ai_claims",
                "rule_type": "allowed_if_evidenced",
                "applies_to_kind": "proof",
                "applies_to": "ai",
                "condition": "AI proof is direct.",
                "action": "Allow AI claims with proof.",
                "basis": "direct proof only",
                "evidence_refs": ["experience_dimension_weights.overall_weights.ai_ml_depth"],
                "precedence": 20,
            },
            {
                "rule_id": "ai_omit",
                "topic_family": "ai_claims",
                "rule_type": "omit_if_weak",
                "applies_to_kind": "proof",
                "applies_to": "ai",
                "condition": "AI proof is weak.",
                "action": "Omit AI claims when proof is weak.",
                "basis": "weak proof should not inflate AI depth",
                "evidence_refs": ["classification.ai_taxonomy.intensity"],
                "precedence": 80,
            },
            {
                "rule_id": "ai_allow_same_precedence",
                "topic_family": "ai_claims",
                "rule_type": "allowed_if_evidenced",
                "applies_to_kind": "proof",
                "applies_to": "ai",
                "condition": "AI proof is partial.",
                "action": "Allow AI claims when proof is partial.",
                "basis": "weaker rule should lose tie-break",
                "evidence_refs": ["classification.ai_taxonomy.intensity"],
                "precedence": 80,
            },
        ]
    }

    normalized = normalize_truth_constrained_emphasis_rules_payload(payload)

    assert normalized["allowed_if_evidenced"] == []
    assert len(normalized["omit_rules"]) == 1
    assert normalized["omit_rules"][0]["rule_id"] == "ai_omit"
    assert any(
        event["kind"] == "duplicate_collapsed"
        for event in normalized["normalization_events"]
    )
    assert any(
        event["kind"] == "conflict_suppressed"
        for event in normalized["normalization_events"]
    )


def test_emphasis_rules_normalizer_derives_stable_rule_ids_across_run_order():
    first = normalize_truth_constrained_emphasis_rules_payload(
        {
            "allowed_if_evidenced": [
                {
                    "topic_family": "architecture_claims",
                    "rule_type": "allowed_if_evidenced",
                    "applies_to_kind": "proof",
                    "applies_to": "architecture",
                    "condition": "Architecture proof is direct.",
                    "action": "Allow architecture claims with direct proof.",
                    "basis": "proof-gated",
                    "evidence_refs": ["pain_point_intelligence.proof_map"],
                }
            ]
        }
    )
    second = normalize_truth_constrained_emphasis_rules_payload(
        {
            "allowed_if_evidenced": list(
                reversed(
                    [
                        {
                            "topic_family": "architecture_claims",
                            "rule_type": "allowed_if_evidenced",
                            "applies_to_kind": "proof",
                            "applies_to": "architecture",
                            "condition": "Architecture proof is direct.",
                            "action": "Allow architecture claims with direct proof.",
                            "basis": "proof-gated",
                            "evidence_refs": ["pain_point_intelligence.proof_map"],
                        }
                    ]
                )
            )
        }
    )

    assert first["allowed_if_evidenced"][0]["rule_id"] == second["allowed_if_evidenced"][0]["rule_id"]


def test_emphasis_rules_normalizer_rejects_candidate_leakage_and_preserves_debug():
    payload = {
        "rules": [
            {
                "topic_family": "title_inflation",
                "rule_type": "forbid_without_direct_proof",
                "applies_to_kind": "global",
                "applies_to": "global",
                "condition": "I led Acme's platform transformation.",
                "action": "Do not claim I doubled revenue.",
                "basis": "I delivered the program.",
                "evidence_refs": ["jd_facts.merged_view.title"],
            }
        ],
        "unknown_top_level": "retained",
    }

    normalized = normalize_truth_constrained_emphasis_rules_payload(
        payload,
        allowed_company_names=["Acme"],
        jd_excerpt="Lead architecture for platform systems.",
    )

    assert normalized["global_rules"] == []
    assert normalized["status"] == "partial"
    assert any(
        "candidate_leakage" in item["reason"]
        for item in normalized["debug_context"]["rejected_output"]
    )


def test_emphasis_rules_normalizer_tolerates_freeform_normalization_event_strings():
    payload = emphasis_rules_payload()
    payload["normalization_events"] = [
        "restricted_rule_types_to_canonical_enums_v1",
        {"kind": "duplicate_collapsed", "reason": "duplicate_rule", "path": "allowed_if_evidenced"},
    ]

    normalized = normalize_truth_constrained_emphasis_rules_payload(payload)

    assert any(
        entry["key"] == "normalization_events[]"
        and entry["value"] == "restricted_rule_types_to_canonical_enums_v1"
        for entry in normalized["debug_context"]["richer_output_retained"]
    )
    assert any(
        event["kind"] == "duplicate_collapsed"
        for event in normalized["normalization_events"]
    )


def test_emphasis_rules_normalizer_rejects_unsafe_regex_patterns():
    payload = emphasis_rules_payload()
    payload["forbidden_claim_patterns"][1]["pattern"] = "(?=ai)visionary"

    normalized = normalize_truth_constrained_emphasis_rules_payload(payload)

    assert len(normalized["forbidden_claim_patterns"]) == 1
    assert any(
        item["reason"] == "regex_outside_whitelist"
        for item in normalized["debug_context"]["rejected_output"]
    )
