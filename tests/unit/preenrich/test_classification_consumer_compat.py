from __future__ import annotations

from src.preenrich.blueprint_models import AITaxonomyDoc, ClassificationDoc, ClassificationEvidence, JdFactsAgreement


def test_root_ai_compat_projection_can_be_derived_from_ai_taxonomy():
    doc = ClassificationDoc(
        primary_role_category="engineering_manager",
        secondary_role_categories=[],
        search_profiles=["ai_leadership"],
        selector_profiles=["engineering-manager"],
        tone_family="executive",
        taxonomy_version="2026-04-20-v2",
        ambiguity_score=0.1,
        confidence="high",
        reason_codes=["deterministic_short_circuit"],
        evidence=ClassificationEvidence(),
        jd_facts_agreement=JdFactsAgreement(agrees=True, jd_facts_role_category="engineering_manager", reason="agree"),
        pre_score=[],
        decision_path="deterministic_short_circuit",
        ai_taxonomy=AITaxonomyDoc(
            is_ai_job=True,
            primary_specialization="ai_leadership",
            secondary_specializations=["genai_llm"],
            intensity="significant",
            scope_tags=["ai_leadership"],
            legacy_ai_categories=["ai_general"],
            rationale="Leadership + AI signals present",
        ),
        ai_relevance={"is_ai_job": True, "categories": ["ai_general"], "rationale": "Leadership + AI signals present"},
    )
    assert doc.ai_taxonomy.is_ai_job is True
    assert doc.ai_taxonomy.legacy_ai_categories == ["ai_general"]
    assert doc.ai_relevance["categories"] == ["ai_general"]
