"""Iteration-4.1 cv_guidelines stage."""

from __future__ import annotations

from typing import List

from src.preenrich.blueprint_models import CVGuidelinesDoc, EvidenceRef, GuidelineBlock
from src.preenrich.types import ArtifactWrite, StageContext, StageResult

PROMPT_VERSION = "P-cv-guidelines:v1"


class CVGuidelinesStage:
    name: str = "cv_guidelines"
    dependencies: List[str] = ["jd_facts", "job_inference", "research_enrichment"]

    def run(self, ctx: StageContext) -> StageResult:
        outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
        jd_facts = outputs.get("jd_facts") or {}
        inference = outputs.get("job_inference") or {}
        merged = jd_facts.get("merged_view") or {}
        evidence = [EvidenceRef(source="jd_facts", locator="merged_view.top_keywords", quote=", ".join((merged.get("top_keywords") or [])[:5]))]
        artifact = CVGuidelinesDoc(
            job_id=str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id")),
            level2_job_id=str(ctx.job_doc.get("_id")),
            jd_facts_id="__ref__:jd_facts.id",
            job_inference_id="__ref__:job_inference.id",
            research_enrichment_id="__ref__:research_enrichment.id",
            prompt_version=PROMPT_VERSION,
            title_guidance=GuidelineBlock(
                title="Title guidance",
                bullets=[f"Mirror the role family '{inference.get('primary_role_category') or merged.get('title') or ctx.job_doc.get('title')}'."],
                evidence_refs=evidence,
            ),
            identity_guidance=GuidelineBlock(
                title="Identity guidance",
                bullets=["Lead with the operating scope, domain, and systems context signaled by the JD."],
                evidence_refs=evidence,
            ),
            bullet_theme_guidance=GuidelineBlock(
                title="Bullet themes",
                bullets=list((merged.get("must_haves") or [])[:4]) or ["Show delivery outcomes tied to the role mandate."],
                evidence_refs=evidence,
            ),
            ats_keyword_guidance=GuidelineBlock(
                title="ATS keywords",
                bullets=list((merged.get("top_keywords") or [])[:8]),
                evidence_refs=evidence,
            ),
            cover_letter_expectations=GuidelineBlock(
                title="Cover letter expectations",
                bullets=["Keep any cover letter tightly tied to the company context and role mandate."],
                evidence_refs=evidence,
            ),
        )
        return StageResult(
            stage_output=artifact.model_dump(),
            artifact_writes=[
                ArtifactWrite(
                    collection="cv_guidelines",
                    unique_filter={
                        "jd_facts_id": "__ref__:jd_facts.id",
                        "job_inference_id": "__ref__:job_inference.id",
                        "research_enrichment_id": "__ref__:research_enrichment.id",
                        "prompt_version": artifact.prompt_version,
                    },
                    document=artifact.model_dump(),
                    ref_name="cv_guidelines",
                )
            ],
            provider_used=ctx.config.provider,
            model_used=ctx.config.primary_model,
            prompt_version=PROMPT_VERSION,
        )
