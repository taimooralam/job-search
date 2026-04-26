from bson import ObjectId

from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
from src.preenrich.types import StageContext, StepConfig


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
                    "research_enrichment": {"company_profile": {"summary": "AI company", "company_type": "employer", "url": "https://acme.example.com", "signals": []}},
                    "application_surface": {},
                    "job_inference": {"semantic_role_model": {"role_mandate": "Lead AI architecture."}, "qualifications": {"must_have": []}},
                    "cv_guidelines": {
                        "title_guidance": {"title": "Title", "bullets": ["Lead with architecture"], "evidence_refs": [{"source": "jd_facts"}]},
                        "identity_guidance": {"title": "Identity", "bullets": ["Keep truthful"], "evidence_refs": [{"source": "jd_facts"}]},
                        "bullet_theme_guidance": {"title": "Bullets", "bullets": ["Show impact"], "evidence_refs": [{"source": "jd_facts"}]},
                        "ats_keyword_guidance": {"title": "ATS", "bullets": ["ai", "architecture"], "evidence_refs": [{"source": "jd_facts"}]},
                        "cover_letter_expectations": {"title": "Cover", "bullets": ["Align to mandate"], "evidence_refs": [{"source": "jd_facts"}]},
                    },
                    "presentation_contract": {
                        "status": "completed",
                        "trace_ref": {"trace_id": "trace:pc", "trace_url": "https://langfuse.example/trace:pc"},
                        "document_expectations": {
                            "status": "completed",
                            "primary_document_goal": "architecture_first",
                            "confidence": {"score": 0.8, "band": "high"},
                        },
                        "cv_shape_expectations": {
                            "status": "completed",
                            "section_order": ["header", "summary", "experience"],
                            "ai_section_policy": "required",
                            "confidence": {"score": 0.77, "band": "medium"},
                        },
                        "ideal_candidate_presentation_model": {
                            "status": "completed",
                            "acceptable_titles": ["Principal AI Architect"],
                            "must_signal": [{"tag": "architecture_judgment"}],
                            "should_signal": [{"tag": "ai_depth"}],
                            "de_emphasize": [{"tag": "tool_listing"}],
                            "proof_ladder": [{"proof_category": "architecture", "signal_tag": "architecture_judgment"}],
                            "audience_variants": {"recruiter": {}},
                            "credibility_markers": [{"marker": "named_systems"}],
                            "risk_flags": [{"flag": "generic_ai_claim"}],
                            "defaults_applied": [],
                            "unresolved_markers": [],
                            "title_strategy": "closest_truthful",
                            "confidence": {"score": 0.74, "band": "medium"},
                        },
                        "experience_dimension_weights": {
                            "status": "completed",
                            "dimension_enum_version": "v1",
                            "overall_weights": {
                                "hands_on_implementation": 12,
                                "architecture_system_design": 20,
                                "leadership_enablement": 8,
                                "tools_technology_stack": 6,
                                "methodology_operating_model": 6,
                                "business_impact": 12,
                                "stakeholder_communication": 8,
                                "ai_ml_depth": 12,
                                "domain_context": 4,
                                "quality_risk_reliability": 5,
                                "delivery_execution_pace": 4,
                                "platform_scaling_change": 3,
                            },
                            "stakeholder_variant_weights": {"recruiter": {"hands_on_implementation": 100}},
                            "minimum_visible_dimensions": ["architecture_system_design", "business_impact", "ai_ml_depth"],
                            "overuse_risks": [],
                            "defaults_applied": [],
                            "normalization_events": [],
                            "confidence": {"score": 0.74, "band": "medium"},
                        },
                    },
                    "pain_point_intelligence": {"status": "completed", "pain_points": [], "strategic_needs": [], "risks_if_unfilled": [], "success_metrics": []},
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
        config=StepConfig(provider="none", primary_model=None, fallback_provider="none", transport="none", fallback_transport="none"),
    )


def test_blueprint_assembly_projects_dimension_weights_compact_snapshot():
    result = BlueprintAssemblyStage().run(_ctx())

    compact = result.stage_output["snapshot"]["presentation_contract"]["dimension_weights"]
    compact_v2 = result.stage_output["snapshot"]["presentation_contract_compact"]["dimension_weights"]
    assert compact["dimension_enum_version"] == "v1"
    assert compact["overall_weight_sum"] == 100
    assert compact["overall_top3"][0]["dimension"] == "architecture_system_design"
    assert compact["trace_ref"]["trace_id"] == "trace:pc"
    assert "overall_weights" not in compact
    assert compact_v2 == compact
