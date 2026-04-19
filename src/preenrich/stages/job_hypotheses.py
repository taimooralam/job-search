"""Iteration-4.1 job_hypotheses stage."""

from __future__ import annotations

from typing import List

from src.preenrich.blueprint_config import taxonomy_version
from src.preenrich.blueprint_models import JobHypothesesDoc, JobHypothesis
from src.preenrich.types import ArtifactWrite, StageContext, StageResult

PROMPT_VERSION = "P-hypotheses:v1"


class JobHypothesesStage:
    name: str = "job_hypotheses"
    dependencies: List[str] = ["jd_facts", "classification", "research_enrichment", "application_surface"]

    def run(self, ctx: StageContext) -> StageResult:
        title = str(ctx.job_doc.get("title") or "")
        hypotheses = []
        if "lead" in title.lower() or "manager" in title.lower():
            hypotheses.append(
                JobHypothesis(
                    field="screening_bias",
                    value="Likely to prioritize leadership examples early.",
                    reasoning="Leadership-oriented title often correlates with manager-led screening.",
                    source_hints=["title"],
                )
            )
        artifact = JobHypothesesDoc(
            job_id=str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id")),
            level2_job_id=str(ctx.job_doc.get("_id")),
            jd_facts_id="__ref__:jd_facts.id",
            research_enrichment_id="__ref__:research_enrichment.id",
            prompt_version=PROMPT_VERSION,
            taxonomy_version=taxonomy_version(),
            hypotheses=hypotheses,
        )
        return StageResult(
            stage_output={"status": "completed", "hypothesis_count": len(hypotheses)},
            artifact_writes=[
                ArtifactWrite(
                    collection="job_hypotheses",
                    unique_filter={
                        "jd_facts_id": "__ref__:jd_facts.id",
                        "research_enrichment_id": "__ref__:research_enrichment.id",
                        "prompt_version": artifact.prompt_version,
                        "taxonomy_version": artifact.taxonomy_version,
                    },
                    document=artifact.model_dump(),
                    ref_name="job_hypotheses",
                )
            ],
            provider_used=ctx.config.provider,
            model_used=ctx.config.primary_model,
            prompt_version=PROMPT_VERSION,
        )
