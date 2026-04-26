import pytest

from src.preenrich.blueprint_models import (
    APPLIES_TO_ENUM_VERSION,
    RULE_TYPE_ENUM_VERSION,
    TruthConstrainedEmphasisRulesDoc,
)
from tests.unit.preenrich._emphasis_rules_test_data import (
    emphasis_rules_payload,
)


def test_emphasis_rules_schema_accepts_canonical_payload():
    doc = TruthConstrainedEmphasisRulesDoc.model_validate(emphasis_rules_payload())

    assert doc.rule_type_enum_version == RULE_TYPE_ENUM_VERSION
    assert doc.applies_to_enum_version == APPLIES_TO_ENUM_VERSION
    assert len(doc.forbidden_claim_patterns) == 2
    assert len(doc.credibility_ladder_rules) == 1


def test_emphasis_rules_schema_forbids_extra_top_level_fields():
    payload = emphasis_rules_payload()
    payload["unexpected"] = True

    with pytest.raises(Exception):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("global_rules.0.rule_type", "authorize_anything"),
        ("global_rules.0.topic_family", "made_up_family"),
        ("section_rules.experience.0.applies_to", "not_a_section"),
    ],
)
def test_emphasis_rules_schema_rejects_invalid_enum_surfaces(path, value):
    payload = emphasis_rules_payload()
    target = payload
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if part.isdigit() else target[part]
    target[parts[-1]] = value

    with pytest.raises(Exception):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)


def test_emphasis_rules_schema_rejects_applies_to_kind_and_value_mismatch():
    payload = emphasis_rules_payload()
    payload["allowed_if_evidenced"][0]["applies_to_kind"] = "dimension"
    payload["allowed_if_evidenced"][0]["applies_to"] = "summary"

    with pytest.raises(Exception):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)


def test_emphasis_rules_schema_restricts_cap_dimension_weight_to_dimensions():
    payload = emphasis_rules_payload()
    payload["global_rules"][1]["applies_to_kind"] = "proof"
    payload["global_rules"][1]["applies_to"] = "leadership"

    with pytest.raises(Exception):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)


def test_emphasis_rules_schema_clamps_precedence_into_bounds():
    payload = emphasis_rules_payload()
    payload["global_rules"][0]["precedence"] = 999

    doc = TruthConstrainedEmphasisRulesDoc.model_validate(payload)

    assert doc.global_rules[0].precedence == 100


def test_emphasis_rules_schema_rejects_rule_confidence_above_document_confidence():
    payload = emphasis_rules_payload(confidence_band="medium", confidence_score=0.79)
    payload["global_rules"][0]["confidence"] = {"score": 0.85, "band": "high", "basis": "too_high"}

    with pytest.raises(Exception):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)


def test_emphasis_rules_schema_rejects_duplicate_rule_ids():
    payload = emphasis_rules_payload()
    payload["allowed_if_evidenced"][0]["rule_id"] = payload["allowed_if_evidenced"][1]["rule_id"]

    with pytest.raises(Exception):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)


def test_emphasis_rules_schema_rejects_invalid_regex_safe_patterns():
    payload = emphasis_rules_payload()
    payload["forbidden_claim_patterns"][1]["pattern"] = "(?=ai)visionary"

    with pytest.raises(Exception):
        TruthConstrainedEmphasisRulesDoc.model_validate(payload)
