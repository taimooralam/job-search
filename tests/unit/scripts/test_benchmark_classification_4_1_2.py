from __future__ import annotations

from scripts.benchmark_classification_4_1_2 import compare_classifications, run_benchmark


def _gold() -> dict:
    return {
        "primary_role_category": "engineering_manager",
        "jd_facts_agreement": {"agrees": True},
        "ambiguous": False,
        "ai_taxonomy": {
            "primary_specialization": "ai_leadership",
            "intensity": "significant",
        },
    }


def _candidate() -> dict:
    return {
        "primary_role_category": "engineering_manager",
        "secondary_role_categories": [],
        "search_profiles": ["ai_leadership"],
        "selector_profiles": ["engineering-manager"],
        "tone_family": "executive",
        "taxonomy_version": "2026-04-20-v2",
        "ambiguity_score": 0.1,
        "confidence": "high",
        "reason_codes": ["deterministic_short_circuit"],
        "evidence": {"title_matches": ["engineering manager"]},
        "jd_facts_agreement": {"agrees": True, "jd_facts_role_category": "engineering_manager", "reason": "agree"},
        "pre_score": [],
        "decision_path": "deterministic_short_circuit",
        "provider_used": "none",
        "model_used": None,
        "prompt_version": "P-classify:v2",
        "ai_taxonomy": {
            "is_ai_job": True,
            "primary_specialization": "ai_leadership",
            "secondary_specializations": [],
            "intensity": "significant",
            "scope_tags": ["ai_leadership"],
            "legacy_ai_categories": ["ai_general"],
            "rationale": "AI leadership signals present",
        },
        "ai_relevance": {"is_ai_job": True, "categories": ["ai_general"], "rationale": "AI leadership signals present"},
    }


def test_compare_classifications_reports_schema_failure():
    comparison = compare_classifications(_gold(), {"primary_role_category": "engineering_manager"})
    assert comparison["schema_valid"] is False


def test_run_benchmark_passes_with_fixture_candidate():
    rows, summary = run_benchmark(
        [
            {
                "job_id": "job-1",
                "gold_classification": _gold(),
                "candidate_classification": _candidate(),
            }
        ],
        use_fixture_candidate=True,
    )
    assert len(rows) == 1
    assert summary["schema_validity_pass_rate"] == 1.0
    assert summary["passes_thresholds"] is True
