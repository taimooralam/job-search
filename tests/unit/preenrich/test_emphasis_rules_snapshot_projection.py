from bson import ObjectId

from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
from src.preenrich.types import StageContext, StepConfig
from tests.unit.preenrich._emphasis_rules_test_data import (
    cv_shape_expectations_payload,
    dimension_weights_payload,
    document_expectations_payload,
    emphasis_rules_payload,
    ideal_candidate_payload,
)


def _ctx() -> StageContext:
    job_id = ObjectId()
    return StageContext(
        job_doc={
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "title": "Principal AI Architect",
            "company": "Acme",
            "pre_enrichment": {
                "outputs": {
                    "jd_facts": {"merged_view": {"title": "Principal AI Architect"}},
                    "classification": {
                        "primary_role_category": "ai_architect",
                        "secondary_role_categories": [],
                        "search_profiles": [],
                        "selector_profiles": [],
                        "tone_family": "executive",
                        "taxonomy_version": "2026-04-19-v1",
                    },
                    "research_enrichment": {
                        "company_profile": {
                            "summary": "AI company",
                            "company_type": "employer",
                            "url": "https://acme.example.com",
                            "signals": [],
                        }
                    },
                    "application_surface": {},
                    "job_inference": {
                        "semantic_role_model": {"role_mandate": "Lead AI architecture."},
                        "qualifications": {"must_have": []},
                    },
                    "cv_guidelines": {
                        "title_guidance": {
                            "title": "Title",
                            "bullets": ["Lead with architecture"],
                            "evidence_refs": [{"source": "jd_facts"}],
                        },
                        "identity_guidance": {
                            "title": "Identity",
                            "bullets": ["Keep truthful"],
                            "evidence_refs": [{"source": "jd_facts"}],
                        },
                        "bullet_theme_guidance": {
                            "title": "Bullets",
                            "bullets": ["Show impact"],
                            "evidence_refs": [{"source": "jd_facts"}],
                        },
                        "ats_keyword_guidance": {
                            "title": "ATS",
                            "bullets": ["ai", "architecture"],
                            "evidence_refs": [{"source": "jd_facts"}],
                        },
                        "cover_letter_expectations": {
                            "title": "Cover",
                            "bullets": ["Align to mandate"],
                            "evidence_refs": [{"source": "jd_facts"}],
                        },
                    },
                    "presentation_contract": {
                        "status": "completed",
                        "trace_ref": {
                            "trace_id": "trace:pc",
                            "trace_url": "https://langfuse.example/trace:pc",
                        },
                        "document_expectations": document_expectations_payload(),
                        "cv_shape_expectations": cv_shape_expectations_payload(),
                        "ideal_candidate_presentation_model": ideal_candidate_payload(),
                        "experience_dimension_weights": dimension_weights_payload(),
                        "truth_constrained_emphasis_rules": emphasis_rules_payload(),
                    },
                    "pain_point_intelligence": {
                        "status": "completed",
                        "pain_points": [],
                        "strategic_needs": [],
                        "risks_if_unfilled": [],
                        "success_metrics": [],
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
        stage_name="blueprint_assembly",
        config=StepConfig(
            provider="none",
            primary_model=None,
            fallback_provider="none",
            transport="none",
            fallback_transport="none",
        ),
    )


def test_blueprint_assembly_projects_emphasis_rules_compact_snapshot():
    result = BlueprintAssemblyStage().run(_ctx())

    compact = result.stage_output["snapshot"]["presentation_contract"]["emphasis_rules"]
    compact_v2 = result.stage_output["snapshot"]["presentation_contract_compact"]["emphasis_rules"]

    assert compact["rule_type_enum_version"] == "v1"
    assert compact["forbidden_claim_patterns_count"] == 2
    assert compact["credibility_ladder_rules_count"] == 1
    assert compact["topic_coverage"]["title_inflation"] == 1
    assert compact["trace_ref"]["trace_id"] == "trace:pc"
    assert "global_rules" not in compact
    assert compact_v2 == compact
