from __future__ import annotations

from src.preenrich.stages.blueprint_common import score_categories_from_taxonomy


def test_score_categories_from_taxonomy_prefers_management_role_for_people_signals():
    rows = score_categories_from_taxonomy(
        {
            "title": "AI Engineering Leader",
            "jd_facts_role_category": "engineering_manager",
            "seniority_level": "director",
            "responsibilities": [
                "Manage engineers",
                "Hire engineers",
                "Lead AI engineering delivery",
            ],
            "qualifications": ["People management experience"],
            "top_keywords": ["people management", "AI", "hiring"],
            "competency_weights": {"delivery": 25, "process": 20, "architecture": 15, "leadership": 40},
            "ideal_candidate_archetype": "people_leader",
        }
    )
    assert rows[0]["category"] == "engineering_manager"
    assert rows[0]["score"] > rows[1]["score"]


def test_score_categories_from_taxonomy_prefers_staff_principal_for_architect_signals():
    rows = score_categories_from_taxonomy(
        {
            "title": "Principal AI Architect",
            "jd_facts_role_category": "staff_principal_engineer",
            "seniority_level": "principal",
            "responsibilities": ["Architect AI platform standards", "Define technical strategy"],
            "qualifications": ["Principal level engineering experience"],
            "top_keywords": ["architecture", "principal", "platform strategy"],
            "competency_weights": {"delivery": 20, "process": 15, "architecture": 45, "leadership": 20},
            "ideal_candidate_archetype": "technical_architect",
        }
    )
    assert rows[0]["category"] == "staff_principal_engineer"
