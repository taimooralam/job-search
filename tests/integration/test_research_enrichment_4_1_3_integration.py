from __future__ import annotations

from bson import ObjectId

from src.preenrich.dag import invalidate
from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
from src.preenrich.stages.research_enrichment import ResearchEnrichmentStage
from src.preenrich.types import StageContext, StepConfig


def _context() -> StageContext:
    job_id = ObjectId()
    return StageContext(
        job_doc={
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "title": "Engineering Manager",
            "company": "Acme",
            "location": "Remote",
            "application_url": "https://boards.greenhouse.io/acme/jobs/123",
            "company_research": {
                "summary": "Acme is growing quickly.",
                "url": "https://acme.example.com",
                "company_type": "employer",
                "signals": [{"type": "growth", "description": "Hiring managers in platform."}],
            },
            "role_research": {
                "summary": "Leadership role for platform reliability.",
                "business_impact": ["Scale delivery"],
                "why_now": "Growth requires stronger engineering management.",
            },
            "pre_enrichment": {
                "outputs": {
                    "jd_facts": {
                        "merged_view": {
                            "title": "Engineering Manager",
                            "responsibilities": ["Lead platform team"],
                            "success_metrics": ["Scale delivery"],
                            "top_keywords": ["leadership", "platform"],
                        }
                    },
                    "classification": {
                        "primary_role_category": "engineering_manager",
                        "tone_family": "executive",
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
                            "expected_success_metrics": ["Scale delivery"],
                            "likely_screening_themes": ["leadership", "platform"],
                        },
                        "qualifications": {"must_have": ["Engineering leadership"]},
                    },
                    "cv_guidelines": {
                        "title_guidance": {"title": "Title", "bullets": ["Lead with scope"], "evidence_refs": [{"source": "jd_facts"}]},
                        "identity_guidance": {"title": "Identity", "bullets": ["Show leadership"], "evidence_refs": [{"source": "jd_facts"}]},
                        "bullet_theme_guidance": {"title": "Bullets", "bullets": ["Delivery"], "evidence_refs": [{"source": "jd_facts"}]},
                        "ats_keyword_guidance": {"title": "ATS", "bullets": ["platform"], "evidence_refs": [{"source": "jd_facts"}]},
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


def test_dag_change_propagates_through_application_surface_and_research(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_ENABLED", "true")
    stale = invalidate({"jd"})
    assert "application_surface" in stale
    assert "research_enrichment" in stale
    assert "job_inference" in stale


def test_cv_ready_path_tolerates_unresolved_stakeholder_subdocs(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_RESEARCH_ENABLE_STAKEHOLDERS", "true")
    ctx = _context()
    result = ResearchEnrichmentStage().run(ctx)
    assert result.stage_output["status"] in {"completed", "partial", "no_research", "unresolved"}
    # Stakeholders are optional; unresolved stakeholders must not remove the canonical artifact.
    assert "company_profile" in result.stage_output
    assert "role_profile" in result.stage_output
    assert "application_profile" in result.stage_output


def test_compat_projection_uses_canonical_application_url_when_v2_live(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_COMPAT_PROJECTIONS_ENABLED", "true")
    ctx = _context()
    ctx.job_doc["pre_enrichment"]["outputs"]["research_enrichment"] = ResearchEnrichmentStage().run(ctx).stage_output
    result = BlueprintAssemblyStage().run(ctx)
    assert result.output["application_url"] == "https://boards.greenhouse.io/acme/jobs/123"


def test_transport_unavailable_degrades_honestly(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "true")
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "false")
    ctx = _context()
    result = ResearchEnrichmentStage().run(ctx)
    assert any("transport unavailable" in item.lower() for item in result.stage_output["unresolved_questions"])


def test_shadow_mode_and_live_compat_flags_persist_in_capability_flags(monkeypatch):
    monkeypatch.setenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_RESEARCH_SHADOW_MODE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_RESEARCH_LIVE_COMPAT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_RESEARCH_REQUIRE_SOURCE_ATTRIBUTION", "true")
    ctx = _context()
    result = ResearchEnrichmentStage().run(ctx)
    assert result.stage_output["capability_flags"]["research_shadow_mode_enabled"] is True
    assert result.stage_output["capability_flags"]["research_live_compat_write_enabled"] is True
