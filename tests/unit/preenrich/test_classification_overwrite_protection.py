from __future__ import annotations

from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
from src.preenrich.stages.classification import ClassificationStage
from src.preenrich.types import StageContext, StepConfig


def test_classification_never_writes_extracted_jd(monkeypatch):
    monkeypatch.setenv("PREENRICH_CLASSIFICATION_V2_ENABLED", "true")
    ctx = StageContext(
        job_doc={
            "_id": "job-1",
            "job_id": "job-1",
            "title": "Engineering Manager",
            "description": "Manage engineers and lead delivery.",
            "pre_enrichment": {
                "outputs": {
                    "jd_facts": {
                        "extraction": {
                            "title": "Engineering Manager",
                            "role_category": "engineering_manager",
                            "seniority_level": "director",
                            "responsibilities": ["Manage engineers"],
                            "qualifications": ["People management experience"],
                            "top_keywords": ["people management"],
                            "competency_weights": {"delivery": 25, "process": 20, "architecture": 15, "leadership": 40},
                            "ideal_candidate_profile": {"archetype": "people_leader"},
                        }
                    }
                }
            },
        },
        jd_checksum="sha256:jd",
        company_checksum="sha256:company",
        input_snapshot_id="sha256:snapshot",
        attempt_number=1,
        config=StepConfig(provider="codex", primary_model="gpt-5.4-mini"),
    )
    result = ClassificationStage().run(ctx)
    assert all(not key.startswith("extracted_jd") for key in result.output)


def test_blueprint_assembly_mirrors_classification_without_extracted_jd_writes(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_COMPAT_PROJECTIONS_ENABLED", "true")
    ctx = StageContext(
        job_doc={
            "_id": "job-1",
            "job_id": "job-1",
            "application_url": "https://example.com/apply",
            "pre_enrichment": {
                "outputs": {
                    "classification": {
                        "primary_role_category": "engineering_manager",
                        "secondary_role_categories": ["tech_lead"],
                        "search_profiles": ["ai_leadership"],
                        "selector_profiles": ["engineering-manager"],
                        "tone_family": "executive",
                        "taxonomy_version": "2026-04-20-v2",
                        "confidence": "high",
                        "ambiguity_score": 0.12,
                        "reason_codes": ["deterministic_short_circuit"],
                        "ai_taxonomy": {"is_ai_job": True, "primary_specialization": "ai_leadership", "secondary_specializations": [], "intensity": "significant", "scope_tags": [], "legacy_ai_categories": ["ai_general"], "rationale": "AI signals present"},
                    },
                    "application_surface": {"status": "resolved", "application_url": "https://example.com/apply", "portal_family": "custom_unknown", "is_direct_apply": True},
                    "research_enrichment": {"company_profile": {"summary": "Summary", "company_type": "employer", "url": None, "signals": []}},
                    "job_inference": {"semantic_role_model": {"role_mandate": "Lead the team", "expected_success_metrics": ["Ship roadmap"], "likely_screening_themes": ["leadership"]}, "qualifications": {"must_have": ["people management"]}},
                    "cv_guidelines": {
                        "title_guidance": {"bullets": ["Lead with scope"]},
                        "identity_guidance": {"bullets": ["Show delivery"]},
                        "bullet_theme_guidance": {"bullets": ["Execution"]},
                        "ats_keyword_guidance": {"bullets": ["AI", "leadership"]},
                        "cover_letter_expectations": {"bullets": ["Tie to team context"]},
                    },
                    "annotations": {"annotations": []},
                    "persona_compat": {"status": "skipped"},
                }
            },
        },
        jd_checksum="sha256:jd",
        company_checksum="sha256:company",
        input_snapshot_id="sha256:snapshot",
        attempt_number=1,
        config=StepConfig(provider="none"),
    )
    result = BlueprintAssemblyStage().run(ctx)
    assert all(not key.startswith("extracted_jd") for key in result.output)
    snapshot = result.output["pre_enrichment.job_blueprint_snapshot"]["classification"]
    assert snapshot["confidence"] == "high"
    assert snapshot["ai_taxonomy"]["primary_specialization"] == "ai_leadership"
