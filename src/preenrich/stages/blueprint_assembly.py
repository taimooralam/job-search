"""Iteration-4.1 blueprint_assembly stage."""

from __future__ import annotations

from typing import Any, List

from src.preenrich.blueprint_config import (
    BLUEPRINT_SNAPSHOT_VERSION,
    blueprint_compat_projections_enabled,
    blueprint_snapshot_write_enabled,
    taxonomy_version,
)
from src.preenrich.blueprint_models import ApplicationSurfaceDoc, JobBlueprintDoc, JobBlueprintSnapshot
from src.preenrich.types import ArtifactWrite, StageContext, StageResult

PROMPT_VERSION = "blueprint_assembly:v1"


def _build_company_research(research: dict[str, Any]) -> dict[str, Any]:
    company_profile = research.get("company_profile") or {}
    return {
        "summary": company_profile.get("summary"),
        "url": company_profile.get("url"),
        "company_type": company_profile.get("company_type"),
        "signals": company_profile.get("signals", []),
    }


def _build_role_research(inference: dict[str, Any], guidelines: dict[str, Any]) -> dict[str, Any]:
    semantic = inference.get("semantic_role_model") or {}
    return {
        "summary": semantic.get("role_mandate"),
        "business_impact": list(semantic.get("expected_success_metrics") or []),
        "why_now": "; ".join((guidelines.get("bullet_theme_guidance") or {}).get("bullets", [])[:2]) or None,
    }


class BlueprintAssemblyStage:
    name: str = "blueprint_assembly"
    dependencies: List[str] = ["jd_facts", "job_inference", "cv_guidelines", "application_surface", "annotations", "persona_compat"]

    def run(self, ctx: StageContext) -> StageResult:
        outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
        jd_facts = outputs.get("jd_facts") or {}
        inference = outputs.get("job_inference") or {}
        guidelines = outputs.get("cv_guidelines") or {}
        research = outputs.get("research_enrichment") or {}
        classification = outputs.get("classification") or {}
        application_surface = outputs.get("application_surface") or {}

        company_research = _build_company_research(research)
        role_research = _build_role_research(inference, guidelines)
        bullet_guidance = list((guidelines.get("bullet_theme_guidance") or {}).get("bullets", []))
        cover_letter_expectations = list((guidelines.get("cover_letter_expectations") or {}).get("bullets", []))
        ats_keywords = list((guidelines.get("ats_keyword_guidance") or {}).get("bullets", []))
        semantic = inference.get("semantic_role_model") or {}

        snapshot = JobBlueprintSnapshot(
            classification={
                "primary_role_category": classification.get("primary_role_category"),
                "secondary_role_categories": classification.get("secondary_role_categories", []),
                "search_profiles": classification.get("search_profiles", []),
                "selector_profiles": classification.get("selector_profiles", []),
                "tone_family": classification.get("tone_family"),
                "taxonomy_version": classification.get("taxonomy_version"),
            },
            application_surface=application_surface,
            company_research=company_research,
            role_research=role_research,
            cv_guidelines={
                "title_guidance": guidelines.get("title_guidance"),
                "identity_guidance": guidelines.get("identity_guidance"),
                "bullet_theme_guidance": guidelines.get("bullet_theme_guidance"),
                "ats_keyword_guidance": guidelines.get("ats_keyword_guidance"),
                "cover_letter_expectations": guidelines.get("cover_letter_expectations"),
            },
            pain_points=list(semantic.get("likely_screening_themes") or []),
            strategic_needs=list((inference.get("qualifications") or {}).get("must_have", [])),
            risks_if_unfilled=["Loss of role-specific delivery capacity."],
            success_metrics=list(semantic.get("expected_success_metrics") or []),
            ats_keywords=ats_keywords,
            title_guidance=" ".join((guidelines.get("title_guidance") or {}).get("bullets", [])[:1]) or None,
            identity_guidance=" ".join((guidelines.get("identity_guidance") or {}).get("bullets", [])[:1]) or None,
            bullet_guidance=bullet_guidance,
            cover_letter_expectations=cover_letter_expectations,
        )
        compat_projection = {
            "application_url": (application_surface or {}).get("application_url") or ctx.job_doc.get("application_url"),
            "pain_points": snapshot.pain_points,
            "strategic_needs": snapshot.strategic_needs,
            "risks_if_unfilled": snapshot.risks_if_unfilled,
            "success_metrics": snapshot.success_metrics,
            "company_research": company_research,
            "role_research": role_research,
        }
        blueprint = JobBlueprintDoc(
            job_id=str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id")),
            level2_job_id=str(ctx.job_doc.get("_id")),
            blueprint_version=BLUEPRINT_SNAPSHOT_VERSION,
            taxonomy_version=taxonomy_version(),
            jd_facts_id="__ref__:jd_facts.id",
            job_inference_id="__ref__:job_inference.id",
            research_enrichment_id="__ref__:research_enrichment.id",
            application_surface=ApplicationSurfaceDoc.model_validate(application_surface or {"status": "unresolved"}),
            cv_guidelines_id="__ref__:cv_guidelines.id",
            job_hypotheses_id="__ref__:job_hypotheses.id",
            snapshot=snapshot,
            compatibility_projection=compat_projection,
        )

        output: dict[str, Any] = {}
        if blueprint_snapshot_write_enabled():
            output.update(
                {
                    "pre_enrichment.job_blueprint_refs": {
                        "job_blueprint_id": "__artifact__:job_blueprint",
                        "jd_facts_id": "__ref__:jd_facts.id",
                        "job_inference_id": "__ref__:job_inference.id",
                        "research_enrichment_id": "__ref__:research_enrichment.id",
                        "cv_guidelines_id": "__ref__:cv_guidelines.id",
                        "job_hypotheses_id": "__ref__:job_hypotheses.id",
                    },
                    "pre_enrichment.job_blueprint_snapshot": snapshot.model_dump(),
                    "pre_enrichment.job_blueprint_version": BLUEPRINT_SNAPSHOT_VERSION,
                    "pre_enrichment.job_blueprint_status": "ready",
                    "pre_enrichment.job_blueprint_updated_at": "__now__",
                }
            )
        if blueprint_compat_projections_enabled():
            output.update(compat_projection)

        return StageResult(
            output=output,
            stage_output={
                "job_blueprint_version": BLUEPRINT_SNAPSHOT_VERSION,
                "snapshot": snapshot.model_dump(),
                "compatibility_projection": compat_projection,
            },
            artifact_writes=[
                ArtifactWrite(
                    collection="job_blueprint",
                    unique_filter={
                        "job_id": blueprint.job_id,
                        "blueprint_version": blueprint.blueprint_version,
                    },
                    document=blueprint.model_dump(),
                    ref_name="job_blueprint",
                )
            ],
            provider_used="none",
            model_used=None,
            prompt_version=PROMPT_VERSION,
        )
