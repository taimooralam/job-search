from __future__ import annotations

from src.preenrich.blueprint_models import ClassificationDoc, ClassificationEvidence, JdFactsAgreement


def test_classification_doc_preserves_rich_fields_without_compat_leakage():
    doc = ClassificationDoc(
        primary_role_category="tech_lead",
        secondary_role_categories=["engineering_manager"],
        search_profiles=["ai_core"],
        selector_profiles=["tech-lead"],
        tone_family="player_coach",
        taxonomy_version="2026-04-20-v2",
        ambiguity_score=0.3,
        confidence="medium",
        reason_codes=["llm_disambiguation"],
        evidence=ClassificationEvidence(title_matches=["ai engineering leader"]),
        jd_facts_agreement=JdFactsAgreement(agrees=False, jd_facts_role_category="engineering_manager", reason="title suggests lead"),
        pre_score=[],
        decision_path="llm_disagreement_resolution",
        model_used="gpt-5.4-mini",
        provider_used="codex",
        prompt_version="P-classify:v2",
        ai_taxonomy={"is_ai_job": True, "primary_specialization": "ai_leadership", "secondary_specializations": [], "intensity": "significant", "scope_tags": ["ai_leadership"], "legacy_ai_categories": ["ai_general"], "rationale": "AI leadership signals present"},
        ai_relevance={"is_ai_job": True, "categories": ["ai_general"], "rationale": "AI leadership signals present"},
    )
    payload = doc.model_dump()
    assert "primary_role_category" in payload
    assert "ai_taxonomy" in payload
    assert "evidence" in payload
    assert "extracted_jd" not in payload
