from __future__ import annotations

from src.preenrich.blueprint_prompts import build_p_classify


def test_classification_prompt_snapshot_is_stable_enough():
    prompt = build_p_classify(
        jd_facts={
            "title": "Engineering Manager",
            "jd_facts_role_category": "engineering_manager",
            "responsibilities": ["Manage engineers"],
            "qualifications": ["People management"],
            "top_keywords": ["people management"],
            "competency_weights": {"delivery": 25, "process": 20, "architecture": 15, "leadership": 40},
        },
        taxonomy={
            "version": "snapshot-v1",
            "primary_role_categories": {"engineering_manager": {"summary": "manager"}},
            "disambiguation_rules": [{"id": "mgr_vs_lead"}],
            "ai_taxonomy": {"specializations": {"none": {"description": "none"}}},
        },
        pre_score=[{"category": "engineering_manager", "score": 7.0}],
        section_context={"used_processed_jd_sections": True},
    )
    assert prompt.startswith("You are P-classify")
    assert "taxonomy_version=snapshot-v1" in prompt
    assert "primary_role_category" in prompt
    assert "ai_taxonomy must include" in prompt
