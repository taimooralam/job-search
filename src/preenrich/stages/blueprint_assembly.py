"""Iteration-4.1 blueprint_assembly stage."""

from __future__ import annotations

from typing import Any, List

from src.preenrich.blueprint_config import (
    BLUEPRINT_SNAPSHOT_VERSION,
    blueprint_compat_projections_enabled,
    blueprint_snapshot_write_enabled,
    research_enrichment_v2_enabled,
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


def _build_legacy_role_research(inference: dict[str, Any], guidelines: dict[str, Any]) -> dict[str, Any]:
    semantic = inference.get("semantic_role_model") or {}
    return {
        "summary": semantic.get("role_mandate"),
        "business_impact": list(semantic.get("expected_success_metrics") or []),
        "why_now": "; ".join((guidelines.get("bullet_theme_guidance") or {}).get("bullets", [])[:2]) or None,
    }


def _build_role_research(research: dict[str, Any], inference: dict[str, Any], guidelines: dict[str, Any]) -> dict[str, Any]:
    role_profile = research.get("role_profile") or {}
    if research_enrichment_v2_enabled() and role_profile:
        return {
            "summary": role_profile.get("summary") or role_profile.get("role_summary"),
            "business_impact": list(role_profile.get("business_impact") or []),
            "why_now": role_profile.get("why_now"),
        }
    return _build_legacy_role_research(inference, guidelines)


def _build_compact_research_snapshot(research: dict[str, Any]) -> dict[str, Any]:
    company_profile = research.get("company_profile") or {}
    role_profile = research.get("role_profile") or {}
    application_profile = research.get("application_profile") or {}
    stakeholders = list(research.get("stakeholder_intelligence") or [])
    top_names = []
    counts_by_type: dict[str, int] = {}
    for item in stakeholders:
        if not isinstance(item, dict):
            continue
        stakeholder_type = str(item.get("stakeholder_type") or "unknown")
        counts_by_type[stakeholder_type] = counts_by_type.get(stakeholder_type, 0) + 1
        confidence_band = ((item.get("identity_confidence") or {}).get("band") if isinstance(item.get("identity_confidence"), dict) else None)
        if confidence_band in {"high", "medium"} and len(top_names) < 5:
            top_names.append(
                {
                    "name": item.get("name"),
                    "title": item.get("current_title"),
                    "stakeholder_type": stakeholder_type,
                }
            )
    return {
        "company_profile": {
            "summary": company_profile.get("summary"),
            "signals": company_profile.get("signals", []),
        },
        "role_profile": {
            "summary": role_profile.get("summary") or role_profile.get("role_summary"),
            "why_now": role_profile.get("why_now"),
            "success_metrics": role_profile.get("success_metrics", []),
        },
        "application_profile": {
            "portal_family": application_profile.get("portal_family"),
            "canonical_application_url": application_profile.get("canonical_application_url"),
            "stale_signal": application_profile.get("stale_signal"),
            "closed_signal": application_profile.get("closed_signal"),
            "ui_actionability": application_profile.get("ui_actionability"),
        },
        "stakeholder_summary": {
            "count": len(stakeholders),
            "counts_by_type": counts_by_type,
            "top_candidates": top_names,
            "artifact_ref": "__ref__:research_enrichment.id",
        },
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
        v2_enabled = research_enrichment_v2_enabled()

        company_research = _build_company_research(research) if v2_enabled else (ctx.job_doc.get("company_research") or _build_company_research(research))
        role_research = _build_role_research(research, inference, guidelines) if v2_enabled else (ctx.job_doc.get("role_research") or _build_legacy_role_research(inference, guidelines))
        bullet_guidance = list((guidelines.get("bullet_theme_guidance") or {}).get("bullets", []))
        cover_letter_expectations = list((guidelines.get("cover_letter_expectations") or {}).get("bullets", []))
        ats_keywords = list((guidelines.get("ats_keyword_guidance") or {}).get("bullets", []))
        semantic = inference.get("semantic_role_model") or {}
        application_profile = (research.get("application_profile") or {}) if v2_enabled else {}
        application_surface_snapshot = dict(application_surface or {})
        if v2_enabled and application_profile:
            application_surface_snapshot.setdefault("application_url", application_profile.get("canonical_application_url"))
            application_surface_snapshot.setdefault("portal_family", application_profile.get("portal_family"))
            application_surface_snapshot.setdefault("status", application_profile.get("resolution_status") or application_profile.get("status"))
            application_surface_snapshot.setdefault("is_direct_apply", application_profile.get("is_direct_apply"))
            application_surface_snapshot.setdefault("stale_signal", application_profile.get("stale_signal"))
            application_surface_snapshot.setdefault("closed_signal", application_profile.get("closed_signal"))

        snapshot = JobBlueprintSnapshot(
            classification={
                "primary_role_category": classification.get("primary_role_category"),
                "secondary_role_categories": classification.get("secondary_role_categories", []),
                "search_profiles": classification.get("search_profiles", []),
                "selector_profiles": classification.get("selector_profiles", []),
                "tone_family": classification.get("tone_family"),
                "taxonomy_version": classification.get("taxonomy_version"),
                "confidence": classification.get("confidence"),
                "ambiguity_score": classification.get("ambiguity_score"),
                "reason_codes": classification.get("reason_codes", []),
                "ai_taxonomy": classification.get("ai_taxonomy", {}),
            },
            application_surface=application_surface_snapshot,
            company_research=company_research,
            role_research=role_research,
            research=_build_compact_research_snapshot(research) if v2_enabled else {},
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
            "application_url": (
                (application_profile or {}).get("canonical_application_url")
                if v2_enabled
                else (application_surface or {}).get("application_url")
            ) or ctx.job_doc.get("application_url"),
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
            application_surface=ApplicationSurfaceDoc.model_validate(application_surface_snapshot or {"status": "unresolved"}),
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
