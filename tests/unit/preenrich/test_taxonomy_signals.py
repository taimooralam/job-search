from __future__ import annotations

from src.preenrich.blueprint_config import load_job_taxonomy
from src.preenrich.stages.blueprint_common import (
    apply_disambiguation_rules,
    detect_ai_taxonomy,
    score_categories_from_taxonomy,
)


def test_taxonomy_has_signal_blocks_for_each_category():
    taxonomy = load_job_taxonomy()
    for category, node in (taxonomy.get("primary_role_categories") or {}).items():
        assert node.get("title_signals"), category
        assert "responsibility_signals" in node
        assert "qualification_signals" in node
        assert "keyword_signals" in node
        assert "competency_anchors" in node
        assert "archetype_signals" in node


def test_detect_ai_taxonomy_uses_taxonomy_blocks():
    ai_taxonomy = detect_ai_taxonomy(
        {
            "title": "AI Platform Engineer",
            "responsibilities": ["Build model serving and inference platform"],
            "qualifications": ["Experience with MLOps"],
            "top_keywords": ["mlops", "model serving", "inference platform"],
        }
    )
    assert ai_taxonomy.is_ai_job is True
    assert ai_taxonomy.primary_specialization == "mlops_llmops"
    assert "mlops_llmops" in ai_taxonomy.scope_tags


def test_disambiguation_rule_prefers_engineering_manager_over_tech_lead():
    inputs = {
        "title": "AI Engineering Leader",
        "responsibilities": ["Manage engineers", "Conduct performance reviews", "Lead AI engineering delivery"],
        "qualifications": ["People management experience"],
        "top_keywords": ["AI", "team leadership"],
        "seniority_level": "director",
        "jd_facts_role_category": "engineering_manager",
        "competency_weights": {"delivery": 25, "process": 20, "architecture": 15, "leadership": 40},
        "ideal_candidate_archetype": "people_leader",
    }
    taxonomy = load_job_taxonomy()
    pre_score = score_categories_from_taxonomy(inputs, taxonomy)
    primary, reasons = apply_disambiguation_rules(pre_score, inputs, taxonomy)
    assert primary == "engineering_manager"
    assert reasons == [] or any(reason.startswith("disambiguation:") for reason in reasons)
