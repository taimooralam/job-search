from __future__ import annotations

from bson import ObjectId
import pytest

from src.preenrich.blueprint_config import validate_blueprint_feature_flags
from src.preenrich.blueprint_models import (
    ApplicationSurfaceDoc,
    ConfidenceDoc,
    InitialOutreachGuidance,
    GuidanceActionBullet,
    GuidanceAvoidBullet,
    GuidanceBullet,
    RoleProfile,
    StakeholderRecord,
)
from src.preenrich.research_transport import ResearchTransportResult
from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
from src.preenrich.stages.research_enrichment import ResearchEnrichmentStage
from src.preenrich.types import StageContext, StepConfig


def _context() -> StageContext:
    job_id = ObjectId()
    return StageContext(
        job_doc={
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "title": "Staff Platform Engineer",
            "company": "Acme",
            "location": "Berlin, Germany",
            "application_url": "https://boards.greenhouse.io/acme/jobs/123",
            "company_research": {
                "summary": "Acme builds AI workflow software.",
                "url": "https://acme.example.com",
                "company_type": "employer",
                "signals": [{"type": "growth", "description": "Hiring across platform."}],
            },
            "role_research": {
                "summary": "Staff platform role focused on reliability.",
                "business_impact": ["Scale platform delivery"],
                "why_now": "Growth in enterprise demand.",
            },
            "primary_contacts": [
                {
                    "name": "Jordan Smith",
                    "role": "Engineering Manager",
                    "company": "Acme",
                    "why_relevant": "Likely hiring manager for platform scope.",
                    "linkedin_url": "https://linkedin.com/in/jordan-smith",
                }
            ],
            "pre_enrichment": {
                "outputs": {
                    "jd_facts": {
                        "merged_view": {
                            "title": "Staff Platform Engineer",
                            "responsibilities": ["Improve platform reliability", "Lead delivery"],
                            "success_metrics": ["Reduce incidents", "Improve deploy velocity"],
                            "top_keywords": ["platform", "reliability", "python"],
                        }
                    },
                    "classification": {
                        "primary_role_category": "staff_principal_engineer",
                        "tone_family": "hands_on",
                    },
                    "application_surface": {
                        "status": "resolved",
                        "application_url": "https://boards.greenhouse.io/acme/jobs/123",
                        "canonical_application_url": "https://boards.greenhouse.io/acme/jobs/123",
                        "portal_family": "greenhouse",
                        "resolution_status": "resolved",
                        "is_direct_apply": True,
                        "confidence": {"score": 0.9, "band": "high", "basis": "direct"},
                    },
                    "job_inference": {
                        "semantic_role_model": {
                            "role_mandate": "Lead platform reliability.",
                            "expected_success_metrics": ["Reduce incidents"],
                            "likely_screening_themes": ["platform", "reliability"],
                        },
                        "qualifications": {"must_have": ["Platform leadership"]},
                    },
                    "cv_guidelines": {
                        "title_guidance": {"title": "Title", "bullets": ["Lead with platform scope"], "evidence_refs": [{"source": "jd_facts"}]},
                        "identity_guidance": {"title": "Identity", "bullets": ["Show reliability wins"], "evidence_refs": [{"source": "jd_facts"}]},
                        "bullet_theme_guidance": {"title": "Bullets", "bullets": ["Reliability", "Delivery"], "evidence_refs": [{"source": "jd_facts"}]},
                        "ats_keyword_guidance": {"title": "ATS", "bullets": ["python", "platform"], "evidence_refs": [{"source": "jd_facts"}]},
                        "cover_letter_expectations": {"title": "CL", "bullets": ["Tie story to company context"], "evidence_refs": [{"source": "jd_facts"}]},
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
        config=StepConfig(
            provider="codex",
            primary_model="gpt-5.4-mini",
            fallback_provider="none",
            fallback_model=None,
            transport="codex_web_search",
            fallback_transport="none",
        ),
    )


def _mock_live_research_transport(monkeypatch):
    def _fake_invoke(self, *, prompt: str, job_id: str, validator=None):
        if "P-research-company@" in prompt:
            payload = {
                "summary": "Acme builds AI workflow software for enterprise operations teams.",
                "url": "https://acme.example.com",
                "signals": [{"type": "growth", "description": "Hiring across platform engineering.", "source_ids": ["s_company"]}],
                "canonical_name": "Acme",
                "canonical_domain": "acme.example.com",
                "canonical_url": "https://acme.example.com",
                "identity_confidence": {"score": 0.9, "band": "high", "basis": "Official company website"},
                "identity_basis": "Official site and verified posting",
                "company_type": "employer",
                "mission_summary": "Enterprise workflow automation.",
                "product_summary": "AI workflow software.",
                "business_model": "b2b_software",
                "customers_and_market": {"segment": "enterprise"},
                "scale_signals": {},
                "funding_signals": [],
                "ai_data_platform_maturity": {},
                "team_org_signals": {},
                "recent_signals": [],
                "role_relevant_signals": [],
                "sources": [{
                    "source_id": "s_company",
                    "url": "https://acme.example.com",
                    "source_type": "official_company_site",
                    "fetched_at": "2026-04-20T00:00:00+00:00",
                    "trust_tier": "primary",
                    "domain": "acme.example.com",
                }],
                "evidence": [{
                    "claim": "Company identity was verified on the official site.",
                    "source_ids": ["s_company"],
                    "basis": "official_site",
                }],
                "confidence": {"score": 0.9, "band": "high", "basis": "Official company site"},
                "status": "completed",
            }
        elif "P-research-role@" in prompt:
            payload = {
                "summary": "Staff platform role focused on reliability and delivery.",
                "role_summary": "Staff platform role focused on reliability and delivery.",
                "mandate": ["Improve platform reliability", "Lead delivery"],
                "business_impact": ["Scale platform delivery"],
                "why_now": "Growth in enterprise demand.",
                "success_metrics": ["Reduce incidents", "Improve deploy velocity"],
                "collaboration_map": [],
                "reporting_line": {"manager_title": "Head of Platform", "source_ids": ["s_role"]},
                "org_placement": {"function_area": "staff_principal_engineer"},
                "interview_themes": ["platform", "reliability"],
                "evaluation_signals": ["systems thinking"],
                "risk_landscape": [],
                "company_context_alignment": "Growth-stage AI platform.",
                "sources": [{
                    "source_id": "s_role",
                    "url": "https://acme.example.com/careers/123",
                    "source_type": "official_job_posting",
                    "fetched_at": "2026-04-20T00:00:00+00:00",
                    "trust_tier": "primary",
                    "domain": "acme.example.com",
                }],
                "evidence": [{
                    "claim": "Role profile came from the verified job posting and company context.",
                    "source_ids": ["s_role"],
                    "basis": "official_job_posting",
                }],
                "confidence": {"score": 0.84, "band": "high", "basis": "Verified job posting"},
                "status": "completed",
            }
        elif "P-stakeholder-discovery@" in prompt:
            payload = {
                "stakeholder_intelligence": [{
                    "stakeholder_type": "hiring_manager",
                    "identity_status": "resolved",
                    "identity_confidence": {"score": 0.82, "band": "high", "basis": "Official team page + public profile"},
                    "identity_basis": "Engineering leadership page and public profile.",
                    "matched_signal_classes": ["official_team_page_named_person", "public_profile_function_match"],
                    "candidate_rank": 1,
                    "name": "Jordan Smith",
                    "current_title": "Engineering Manager",
                    "current_company": "Acme",
                    "profile_url": "https://www.linkedin.com/in/jordan-smith",
                    "source_trail": ["s_person"],
                    "function": "engineering",
                    "seniority": "manager",
                    "relationship_to_role": "likely_hiring_manager",
                    "likely_influence": "strong_input",
                    "public_professional_background": {"career_arc": "Platform leadership", "source_ids": ["s_person"]},
                    "public_communication_signals": {"topics_they_post_about": [], "tone": "direct", "cadence": "low", "source_ids": ["s_person"]},
                    "working_style_signals": [],
                    "likely_priorities": [],
                    "avoid_points": [],
                    "evidence_basis": "Official team page plus public profile.",
                    "confidence": {"score": 0.82, "band": "high", "basis": "Official team page + public profile"},
                    "unresolved_markers": [],
                    "sources": [{
                        "source_id": "s_person",
                        "url": "https://www.linkedin.com/in/jordan-smith",
                        "source_type": "public_professional_profile",
                        "fetched_at": "2026-04-20T00:00:00+00:00",
                        "trust_tier": "secondary",
                    }],
                    "evidence": [{
                        "claim": "Jordan Smith is a plausible hiring manager for the role.",
                        "source_ids": ["s_person"],
                        "basis": "public_profile",
                    }],
                }]
            }
        elif "P-stakeholder-profile@" in prompt:
            payload = {
                "public_professional_background": {"career_arc": "Platform leadership and reliability focus.", "source_ids": ["s_person"]},
                "public_communication_signals": {"topics_they_post_about": ["platform reliability"], "tone": "direct", "cadence": "low", "source_ids": ["s_person"]},
                "working_style_signals": ["execution_focus"],
                "likely_priorities": [{"bullet": "Platform reliability and operational discipline.", "basis": "public_posts", "source_ids": ["s_person"]}],
                "relationship_to_role": "likely_hiring_manager",
                "evidence_basis": "Public professional signals about platform reliability.",
                "unresolved_markers": [],
                "sources": [],
                "evidence": [],
                "confidence": {"score": 0.8, "band": "high", "basis": "Public professional signals"},
            }
        elif "P-stakeholder-outreach-guidance@" in prompt:
            payload = {
                "stakeholder_ref": 1,
                "stakeholder_type": "hiring_manager",
                "likely_priorities": [{"bullet": "Operational reliability and delivery quality.", "basis": "role", "source_ids": ["s_person"]}],
                "initial_outreach_guidance": {
                    "what_they_likely_care_about": [{"bullet": "Operational reliability and delivery quality.", "basis": "role", "source_ids": ["s_person"]}],
                    "initial_cold_interaction_guidance": [{"bullet": "Lead with one concrete reliability win.", "dimension": "value_signal", "source_ids": ["s_person"]}],
                    "avoid_in_initial_contact": [{"bullet": "Do not guess internal roadmap priorities.", "reason": "anti_speculation", "source_ids": ["s_person"]}],
                    "confidence_and_basis": {"score": 0.8, "band": "high", "basis": "Public professional signals"},
                },
                "avoid_points": [{"bullet": "Do not guess internal roadmap priorities.", "reason": "anti_speculation", "source_ids": ["s_person"]}],
                "evidence_basis": "Public professional signals",
                "confidence": {"score": 0.8, "band": "high", "basis": "Public professional signals"},
                "status": "completed",
            }
        else:
            payload = {
                "application_profile": {
                    "status": "resolved",
                    "job_url": "https://boards.greenhouse.io/acme/jobs/123",
                    "application_url": "https://boards.greenhouse.io/acme/jobs/123",
                    "canonical_application_url": "https://boards.greenhouse.io/acme/jobs/123",
                    "redirect_chain": ["https://boards.greenhouse.io/acme/jobs/123"],
                    "last_verified_at": "2026-04-20T00:00:00+00:00",
                    "final_http_status": 200,
                    "resolution_method": "codex_verified",
                    "resolution_confidence": {"score": 0.9, "band": "high", "basis": "Verified"},
                    "resolution_status": "resolved",
                    "resolution_note": "Verified official ATS URL.",
                    "ui_actionability": "ready",
                    "portal_family": "greenhouse",
                    "ats_vendor": "greenhouse",
                    "is_direct_apply": True,
                    "account_creation_likely": False,
                    "multi_step_likely": True,
                    "form_fetch_status": "not_attempted",
                    "stale_signal": "active",
                    "closed_signal": "open",
                    "duplicate_signal": {},
                    "geo_normalization": {},
                    "apply_instructions": "Use the canonical application URL.",
                    "apply_caveats": [],
                    "sources": [{
                        "source_id": "s_app",
                        "url": "https://boards.greenhouse.io/acme/jobs/123",
                        "source_type": "official_job_posting",
                        "fetched_at": "2026-04-20T00:00:00+00:00",
                        "trust_tier": "primary",
                    }],
                    "evidence": [{
                        "claim": "Application URL was verified on the ATS.",
                        "source_ids": ["s_app"],
                        "basis": "official_job_posting",
                    }],
                    "confidence": {"score": 0.9, "band": "high", "basis": "Verified"},
                    "candidates": ["https://boards.greenhouse.io/acme/jobs/123"],
                    "friction_signals": ["multi_step_likely"],
                    "notes": [],
                }
            }
        return ResearchTransportResult(
            success=True,
            payload=validator(payload) if validator else payload,
            attempts=[{"provider": "codex", "outcome": "success"}],
            provider_used="codex",
            model_used="gpt-5.4-mini",
            transport_used="codex_web_search",
        )

    monkeypatch.setattr("src.preenrich.research_transport.CodexResearchTransport.invoke_json", _fake_invoke)


def test_role_profile_alias_syncs_summary():
    profile = RoleProfile(role_summary="Canonical role summary")
    assert profile.summary == "Canonical role summary"


def test_application_surface_alias_syncs_application_url():
    doc = ApplicationSurfaceDoc(canonical_application_url="https://boards.greenhouse.io/acme/jobs/123")
    assert doc.application_url == "https://boards.greenhouse.io/acme/jobs/123"


def test_stakeholder_medium_confidence_requires_multiple_signal_classes():
    with pytest.raises(ValueError, match="medium/high stakeholder identity requires"):
        StakeholderRecord(
            stakeholder_type="hiring_manager",
            identity_status="resolved",
            identity_confidence=ConfidenceDoc(score=0.7, band="medium", basis="insufficient"),
            matched_signal_classes=["public_profile_company_match"],
        )


def test_outreach_guidance_blocked_for_low_confidence_stakeholder():
    with pytest.raises(ValueError, match="outreach guidance requires medium or high stakeholder identity confidence"):
        StakeholderRecord(
            stakeholder_type="recruiter",
            identity_status="ambiguous",
            identity_confidence=ConfidenceDoc(score=0.2, band="low", basis="weak"),
            matched_signal_classes=["public_profile_company_match"],
            initial_outreach_guidance=InitialOutreachGuidance(
                what_they_likely_care_about=[GuidanceBullet(bullet="Care about fit", source_ids=["s1"])],
                initial_cold_interaction_guidance=[GuidanceActionBullet(bullet="Keep it brief", source_ids=["s1"])],
                avoid_in_initial_contact=[GuidanceAvoidBullet(bullet="Do not guess priorities", source_ids=["s1"])],
                confidence_and_basis=ConfidenceDoc(score=0.2, band="low", basis="weak"),
            ),
        )


def test_research_stage_v2_off_preserves_legacy_authority(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "false")
    result = ResearchEnrichmentStage().run(_context())
    assert result.stage_output["status"] in {"completed", "no_research"}
    assert "legacy 4.1 projections remain authoritative" in " ".join(result.stage_output["notes"]).lower()


def test_research_stage_writes_cache_refs_and_stakeholders(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "true")
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_RESEARCH_ENABLE_STAKEHOLDERS", "true")
    monkeypatch.setenv("PREENRICH_RESEARCH_ENABLE_OUTREACH_GUIDANCE", "true")
    _mock_live_research_transport(monkeypatch)
    result = ResearchEnrichmentStage().run(_context())
    stage_output = result.stage_output
    assert stage_output["application_profile"]["canonical_application_url"] == "https://boards.greenhouse.io/acme/jobs/123"
    assert stage_output["cache_refs"]["company_cache_key"]
    assert any(write.collection == "research_company_cache" for write in result.artifact_writes)
    assert stage_output["stakeholder_intelligence"]
    stakeholder = stage_output["stakeholder_intelligence"][0]
    assert stakeholder["identity_confidence"]["band"] in {"medium", "high"}
    assert stakeholder["initial_outreach_guidance"]["what_they_likely_care_about"]
    assert stage_output["company_profile"]["status"] == "completed"
    assert stage_output["role_profile"]["status"] == "completed"


def test_research_stage_accepts_richer_live_shapes_after_normalization(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "true")
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_RESEARCH_ENABLE_STAKEHOLDERS", "true")

    def _fake_invoke(self, *, prompt: str, job_id: str, validator=None):
        if "P-research-company@" in prompt:
            payload = {
                "summary": {"text": "Acme builds AI workflow software for enterprise teams."},
                "canonical_name": {"text": "Acme"},
                "canonical_domain": {"value": "acme.example.com"},
                "canonical_url": {"value": "https://acme.example.com"},
                "identity_basis": {"text": "Official site and verified posting"},
                "signals": [{
                    "name": "growth",
                    "value": "Hiring across platform engineering.",
                    "confidence": {"score": 0.7, "band": "medium", "basis": "observed"},
                    "evidence": [{"source_ids": ["s_company"]}],
                }],
                "sources": [{
                    "source_id": "s_company",
                    "url": "https://acme.example.com",
                    "source_type": "official_company_site",
                    "fetched_at": "2026-04-20T00:00:00+00:00",
                    "trust_tier": "primary",
                    "domain": "acme.example.com",
                }],
                "confidence": {"score": 0.9, "band": "high", "basis": "Official company site"},
                "status": "completed",
            }
        elif "P-research-role@" in prompt:
            payload = {
                "summary": {"text": "Staff platform role focused on reliability and delivery."},
                "role_summary": {"text": "Senior platform leadership role with execution depth."},
                "why_now": {"text": "Growth in enterprise demand."},
                "company_context_alignment": {"text": "The role supports platform scale and reliability."},
                "mandate": ["Improve platform reliability", "Lead delivery"],
                "success_metrics": ["Reduce incidents", "Improve deploy velocity"],
                "confidence": {"score": 0.84, "band": "high", "basis": "Verified job posting"},
                "status": "completed",
            }
        elif "P-stakeholder-discovery@" in prompt:
            payload = {
                "stakeholder_intelligence": [{
                    "stakeholder_type": "hiring_manager",
                    "identity_status": "resolved",
                    "identity_confidence": {"score": 0.82, "band": "high", "basis": "Official team page + public profile"},
                    "identity_basis": "Engineering leadership page and public profile.",
                    "matched_signal_classes": ["official_team_page_named_person", "public_profile_function_match"],
                    "candidate_rank": 1,
                    "name": "Jordan Smith",
                    "title": "Engineering Manager",
                    "company": "Acme",
                    "relationship": "likely_hiring_manager",
                }]
            }
        else:
                payload = {
                    "application_profile": {
                        "canonical_application_url": "https://boards.greenhouse.io/acme/jobs/123",
                        "status": "partial",
                        "resolution_status": "partial",
                        "portal_family": "greenhouse",
                        "ui_actionability": "applyable",
                        "form_fetch_status": "unavailable",
                        "apply_instructions": ["Use the official ATS entrypoint."],
                    },
                "application_surface_artifact": {"status": "resolved"},
                "job_document_hints": {"company": "Acme"},
            }
        return ResearchTransportResult(
            success=True,
            payload=validator(payload) if validator else payload,
            attempts=[{"provider": "codex", "outcome": "success"}],
            provider_used="codex",
            model_used="gpt-5.4-mini",
            transport_used="codex_web_search",
        )

    monkeypatch.setattr("src.preenrich.research_transport.CodexResearchTransport.invoke_json", _fake_invoke)
    result = ResearchEnrichmentStage().run(_context())
    stage_output = result.stage_output
    assert stage_output["company_profile"]["canonical_name"] == "Acme"
    assert stage_output["company_profile"]["signals_rich"][0]["name"] == "growth"
    assert stage_output["role_profile"]["summary_detail"]["text"] == "Staff platform role focused on reliability and delivery."
    assert stage_output["application_profile"]["canonical_application_url"] == "https://boards.greenhouse.io/acme/jobs/123"
    assert stage_output["application_profile"]["debug_context"]["application_surface_artifact"]["status"] == "resolved"
    assert stage_output["stakeholder_intelligence"][0]["current_title"] == "Engineering Manager"
    assert stage_output["stakeholder_intelligence"][0]["relationship_to_role"] == "likely_hiring_manager"


def test_snapshot_compactness_allow_list(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_COMPAT_PROJECTIONS_ENABLED", "true")
    ctx = _context()
    research = ResearchEnrichmentStage().run(ctx).stage_output
    ctx.job_doc["pre_enrichment"]["outputs"]["research_enrichment"] = research
    snapshot = BlueprintAssemblyStage().run(ctx).output["pre_enrichment.job_blueprint_snapshot"]
    compact = snapshot["research"]
    assert compact["company_profile"]["summary"]
    assert "sources" not in compact["company_profile"]
    assert "evidence" not in compact["role_profile"]
    assert "initial_outreach_guidance" not in json_dump(snapshot)


def test_research_flag_validation_rules(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_RESEARCH_LIVE_COMPAT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_RESEARCH_REQUIRE_SOURCE_ATTRIBUTION", "false")
    with pytest.raises(RuntimeError, match="live compat write requires"):
        validate_blueprint_feature_flags()


def json_dump(payload: object) -> str:
    import json

    return json.dumps(payload, sort_keys=True)
