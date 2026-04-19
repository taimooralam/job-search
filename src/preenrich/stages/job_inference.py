"""Iteration-4.1 job_inference stage."""

from __future__ import annotations

from typing import List

from src.preenrich.blueprint_config import taxonomy_version
from src.preenrich.blueprint_models import ApplicationSurfaceDoc, EvidenceRef, InferenceField, JobInferenceDoc
from src.preenrich.stages.blueprint_common import ideal_archetypes_for_primary
from src.preenrich.types import ArtifactWrite, StageContext, StageResult

PROMPT_VERSION = "P-role-model:v1"


class JobInferenceStage:
    name: str = "job_inference"
    dependencies: List[str] = ["jd_facts", "classification", "research_enrichment", "application_surface"]

    def run(self, ctx: StageContext) -> StageResult:
        outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
        jd_facts = outputs.get("jd_facts") or {}
        classification = outputs.get("classification") or {}
        research = outputs.get("research_enrichment") or {}
        app_surface = outputs.get("application_surface") or {}
        merged = jd_facts.get("merged_view") or {}
        primary = classification.get("primary_role_category") or "senior_engineer"

        semantic_role_model = {
            "role_mandate": f"Lead delivery for {merged.get('title') or ctx.job_doc.get('title')}.",
            "expected_success_metrics": list(merged.get("must_haves") or [])[:3],
            "likely_screening_themes": list(merged.get("top_keywords") or [])[:5],
            "ideal_candidate_archetypes": ideal_archetypes_for_primary(primary),
        }
        qualifications = {
            "must_have": list(merged.get("must_haves") or []),
            "nice_to_have": list(merged.get("nice_to_haves") or []),
            "keywords": list(merged.get("top_keywords") or []),
        }
        inferences = [
            InferenceField(
                field="role_mandate",
                value=semantic_role_model["role_mandate"],
                confidence="high",
                evidence_spans=[EvidenceRef(source="jd_facts", locator="merged_view.title", quote=str(merged.get("title") or ctx.job_doc.get("title") or ""))],
            )
        ]
        artifact = JobInferenceDoc(
            job_id=str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id")),
            level2_job_id=str(ctx.job_doc.get("_id")),
            jd_facts_id="__ref__:jd_facts.id",
            research_enrichment_id="__ref__:research_enrichment.id",
            prompt_version=PROMPT_VERSION,
            taxonomy_version=taxonomy_version(),
            primary_role_category=primary,
            tone_family=classification.get("tone_family") or "hands_on",
            semantic_role_model=semantic_role_model,
            company_model={
                "company_summary": ((research.get("company_profile") or {}).get("summary")),
                "company_type": ((research.get("company_profile") or {}).get("company_type")),
            },
            qualifications=qualifications,
            application_surface=ApplicationSurfaceDoc.model_validate(app_surface or {"status": "unresolved"}),
            inferences=inferences,
        )
        return StageResult(
            stage_output=artifact.model_dump(),
            artifact_writes=[
                ArtifactWrite(
                    collection="job_inference",
                    unique_filter={
                        "jd_facts_id": "__ref__:jd_facts.id",
                        "research_enrichment_id": "__ref__:research_enrichment.id",
                        "prompt_version": artifact.prompt_version,
                        "taxonomy_version": artifact.taxonomy_version,
                    },
                    document=artifact.model_dump(),
                    ref_name="job_inference",
                )
            ],
            provider_used=ctx.config.provider,
            model_used=ctx.config.primary_model,
            prompt_version=PROMPT_VERSION,
        )
