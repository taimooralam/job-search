from __future__ import annotations

import pytest

from src.preenrich.blueprint_prompts import build_p_classify


def test_build_p_classify_contains_required_contract_fields():
    prompt = build_p_classify(
        jd_facts={
            "title": "AI Engineering Leader",
            "jd_facts_role_category": "engineering_manager",
            "responsibilities": ["Lead AI engineering delivery"],
            "qualifications": ["People management experience"],
            "top_keywords": ["AI", "engineering leadership"],
        },
        taxonomy={"version": "test-v1", "primary_role_categories": {}, "disambiguation_rules": [], "ai_taxonomy": {}},
        pre_score=[{"category": "engineering_manager", "score": 4.2}],
        section_context={"used_processed_jd_sections": True},
    )
    assert "primary_role_category" in prompt
    assert "secondary_role_categories" in prompt
    assert "reason_codes" in prompt
    assert "ai_taxonomy" in prompt
    assert "taxonomy_version=test-v1" in prompt
    assert "Forbidden inputs: job_hypotheses and research_enrichment" in prompt


def test_build_p_classify_includes_taxonomy_and_prescore():
    prompt = build_p_classify(
        jd_facts={"title": "Head of Engineering"},
        taxonomy={
            "version": "test-v2",
            "primary_role_categories": {"head_of_engineering": {"summary": "leader"}},
            "disambiguation_rules": [{"id": "r1"}],
            "ai_taxonomy": {"specializations": {"ai_core": {"description": "core"}}},
        },
        pre_score=[{"category": "head_of_engineering", "score": 10.0}],
        section_context={"sections": [{"header": "Responsibilities"}]},
    )
    assert '"pre_score"' in prompt
    assert '"head_of_engineering"' in prompt
    assert '"ai_taxonomy"' in prompt
    assert '"section_context"' in prompt


def test_build_p_classify_rejects_hypothesis_leakage():
    with pytest.raises(ValueError, match="must not reference job_hypotheses"):
        build_p_classify(
            jd_facts={"title": "Head of Engineering"},
            taxonomy={"version": "test-v1", "primary_role_categories": {}},
            section_context={"job_hypotheses": {"leak": True}},
        )
