"""Tests for iteration-4.1 blueprint stages and snapshot isolation."""

from __future__ import annotations

from bson import ObjectId
import pytest

from src.preenrich.blueprint_models import GuidelineBlock
from src.preenrich.blueprint_prompts import build_p_cv_guidelines
from src.preenrich.stages.application_surface import ApplicationSurfaceStage
from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
from src.preenrich.stages.classification import ClassificationStage
from src.preenrich.stages.cv_guidelines import CVGuidelinesStage
from src.preenrich.stages.jd_facts import JDFactsStage
from src.preenrich.stages.job_hypotheses import JobHypothesesStage
from src.preenrich.stages.job_inference import JobInferenceStage
from src.preenrich.stages.research_enrichment import ResearchEnrichmentStage
from src.preenrich.types import StageContext, StepConfig


def _context(*, title: str = "Head of Engineering", company: str = "Acme", description: str = "") -> StageContext:
    if not description:
        description = (
            "Remote role. Requirements:\n"
            "- Python\n"
            "- Kubernetes\n"
            "- Leadership\n"
            "Preferred:\n"
            "- ML\n"
            "Apply here: https://boards.greenhouse.io/acme/jobs/12345"
        )
    job_id = ObjectId()
    return StageContext(
        job_doc={
            "_id": job_id,
            "job_id": f"job-{job_id}",
            "title": title,
            "company": company,
            "location": "Remote - Europe",
            "description": description,
            "jobUrl": "https://boards.greenhouse.io/acme/jobs/12345",
            "pre_enrichment": {"outputs": {}},
        },
        jd_checksum="sha256:jd",
        company_checksum="sha256:company",
        input_snapshot_id="sha256:snapshot",
        attempt_number=1,
        config=StepConfig(
            provider="codex",
            primary_model="gpt-5.4-mini",
            fallback_provider="claude",
            fallback_model="claude-haiku-4-5",
        ),
    )


def test_jd_facts_does_not_silently_overwrite_deterministic_fields(monkeypatch):
    ctx = _context()

    def _fake_llm(**_: object):
        return {
            "additions": [
                {
                    "field": "title",
                    "value": "Changed title",
                    "confidence": "high",
                    "evidence_span": {"quote": "Head of Engineering"},
                },
                {
                    "field": "employment_type",
                    "value": "full_time",
                    "confidence": "high",
                    "evidence_span": {"quote": "Remote role"},
                },
            ],
            "flags": [],
            "confirmations": {"title": True},
        }, [{"provider": "codex", "model": "gpt-5.4-mini", "outcome": "success"}]

    monkeypatch.setattr("src.preenrich.stages.jd_facts._call_llm_with_fallback", _fake_llm)

    result = JDFactsStage().run(ctx)
    merged = result.stage_output["merged_view"]
    assert merged["title"] == "Head of Engineering"
    assert merged["employment_type"] == "full_time"
    assert result.stage_output["provenance"]["title"] == "deterministic"
    assert result.stage_output["provenance"]["employment_type"] == "llm_addition"
    assert result.stage_output["llm_flags"]


def test_classification_uses_taxonomy_mappings():
    ctx = _context()
    ctx.job_doc["pre_enrichment"]["outputs"]["jd_facts"] = {"merged_view": {"title": "Head of Engineering"}}
    result = ClassificationStage().run(ctx)
    assert result.stage_output["primary_role_category"] == "head_of_engineering"
    assert result.stage_output["search_profiles"] == ["ai_leadership"]
    assert result.stage_output["selector_profiles"] == ["head-director"]
    assert result.stage_output["tone_family"] == "executive"


def test_research_enrichment_respects_no_research_gate(monkeypatch):
    monkeypatch.setenv("WEB_RESEARCH_ENABLED", "false")
    ctx = _context(company="Acme")
    result = ResearchEnrichmentStage().run(ctx)
    assert result.stage_output["status"] == "no_research"
    assert result.stage_output["capability_flags"]["web_research_enabled"] is False


def test_application_surface_is_deterministic_first():
    ctx = _context()
    ctx.job_doc["jobUrl"] = "boards.greenhouse.io/acme/jobs/12345"
    result = ApplicationSurfaceStage().run(ctx)
    assert result.stage_output["application_url"] == "https://boards.greenhouse.io/acme/jobs/12345"
    assert result.stage_output["portal_family"] == "greenhouse"
    assert "multi_step_likely" in result.stage_output["friction_signals"]


def test_job_inference_builds_evidence_backed_semantic_model():
    ctx = _context()
    ctx.job_doc["pre_enrichment"]["outputs"] = {
        "jd_facts": {
            "merged_view": {
                "title": "Head of Engineering",
                "must_haves": ["Scale platform", "Lead delivery"],
                "top_keywords": ["python", "kubernetes", "ai"],
                "nice_to_haves": ["ml"],
            }
        },
        "classification": {
            "primary_role_category": "head_of_engineering",
            "tone_family": "executive",
        },
        "research_enrichment": {"company_profile": {"summary": "Growth-stage AI company", "company_type": "employer"}},
        "application_surface": {
            "status": "resolved",
            "application_url": "https://boards.greenhouse.io/acme/jobs/12345",
            "portal_family": "greenhouse",
            "is_direct_apply": True,
        },
    }
    result = JobInferenceStage().run(ctx)
    assert "semantic_role_model" in result.stage_output
    assert result.stage_output["application_surface"]["portal_family"] == "greenhouse"
    assert result.stage_output["inferences"][0]["evidence_spans"]


def test_job_hypotheses_stays_isolated_from_stage_output():
    ctx = _context(title="Engineering Manager")
    result = JobHypothesesStage().run(ctx)
    assert result.output == {}
    assert result.stage_output["status"] == "completed"
    artifact = result.artifact_writes[0].document
    assert artifact["hypotheses"]
    assert "job_hypotheses" not in result.stage_output


def test_cv_guidelines_blocks_require_evidence_refs():
    with pytest.raises(ValueError, match="evidence references"):
        GuidelineBlock(title="bad", bullets=["x"], evidence_refs=[])


def test_cv_guidelines_prompt_rejects_hypothesis_leakage():
    with pytest.raises(ValueError, match="must not reference job_hypotheses"):
        build_p_cv_guidelines(
            jd_facts={"merged_view": {"title": "Head of Engineering"}},
            job_inference={"semantic_role_model": {"role_mandate": "Lead engineering"}},
            research_enrichment={"job_hypotheses": {"should_not": "leak"}},
        )


def test_cv_guidelines_stage_emits_evidence_backed_blocks():
    ctx = _context()
    ctx.job_doc["pre_enrichment"]["outputs"] = {
        "jd_facts": {"merged_view": {"title": "Head of Engineering", "must_haves": ["Scale platform"], "top_keywords": ["python", "kubernetes"]}},
        "job_inference": {"primary_role_category": "head_of_engineering"},
        "research_enrichment": {"company_profile": {"summary": "Growth-stage AI company"}},
    }
    result = CVGuidelinesStage().run(ctx)
    assert result.stage_output["title_guidance"]["evidence_refs"]
    assert result.stage_output["cover_letter_expectations"]["evidence_refs"]


def test_blueprint_assembly_excludes_hypotheses_from_snapshot_and_preserves_compat(monkeypatch):
    monkeypatch.setenv("PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED", "true")
    monkeypatch.setenv("PREENRICH_BLUEPRINT_COMPAT_PROJECTIONS_ENABLED", "true")
    ctx = _context()
    ctx.job_doc["pre_enrichment"]["outputs"] = {
        "jd_facts": {"merged_view": {"title": "Head of Engineering"}},
        "classification": {
            "primary_role_category": "head_of_engineering",
            "secondary_role_categories": [],
            "search_profiles": ["ai_leadership"],
            "selector_profiles": ["head-director"],
            "tone_family": "executive",
            "taxonomy_version": "2026-04-19-v1",
        },
        "research_enrichment": {
            "company_profile": {
                "summary": "Growth-stage AI company",
                "company_type": "employer",
                "url": "https://acme.example.com",
                "signals": [{"type": "growth", "description": "Hiring leadership"}],
            }
        },
        "application_surface": {
            "status": "resolved",
            "application_url": "https://boards.greenhouse.io/acme/jobs/12345",
            "portal_family": "greenhouse",
            "is_direct_apply": True,
            "friction_signals": ["multi_step_likely"],
        },
        "job_inference": {
            "semantic_role_model": {
                "role_mandate": "Lead engineering execution.",
                "expected_success_metrics": ["Ship roadmap"],
                "likely_screening_themes": ["leadership", "delivery"],
                "ideal_candidate_archetypes": ["strategic_visionary"],
            },
            "qualifications": {"must_have": ["Scale teams"]},
        },
        "cv_guidelines": {
            "title_guidance": {"title": "Title guidance", "bullets": ["Mirror the mandate"], "evidence_refs": [{"source": "jd_facts"}]},
            "identity_guidance": {"title": "Identity guidance", "bullets": ["Lead with scope"], "evidence_refs": [{"source": "jd_facts"}]},
            "bullet_theme_guidance": {"title": "Bullet guidance", "bullets": ["Show execution"], "evidence_refs": [{"source": "jd_facts"}]},
            "ats_keyword_guidance": {"title": "ATS", "bullets": ["python", "leadership"], "evidence_refs": [{"source": "jd_facts"}]},
            "cover_letter_expectations": {"title": "Cover letter", "bullets": ["Tie to company context"], "evidence_refs": [{"source": "jd_facts"}]},
        },
        "job_hypotheses": {"status": "completed", "hypothesis_count": 1},
        "annotations": {"annotations": []},
        "persona_compat": {"status": "skipped"},
    }

    result = BlueprintAssemblyStage().run(ctx)
    snapshot = result.output["pre_enrichment.job_blueprint_snapshot"]
    assert "job_hypotheses" not in snapshot
    assert snapshot["company_research"]["summary"] == "Growth-stage AI company"
    assert result.output["application_url"] == "https://boards.greenhouse.io/acme/jobs/12345"
    artifact = result.artifact_writes[0].document
    assert "job_hypotheses_id" in artifact
    assert "job_hypotheses" not in artifact["snapshot"]
