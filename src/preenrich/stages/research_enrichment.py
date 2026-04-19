"""Iteration-4.1 research_enrichment stage."""

from __future__ import annotations

from typing import List

from src.preenrich.blueprint_config import web_research_enabled
from src.preenrich.blueprint_models import CompanyProfile, ResearchEnrichmentDoc
from src.preenrich.types import ArtifactWrite, StageContext, StageResult

PROMPT_VERSION = "P-research:v1"


class ResearchEnrichmentStage:
    name: str = "research_enrichment"
    dependencies: List[str] = ["jd_facts"]

    def run(self, ctx: StageContext) -> StageResult:
        company = str(ctx.job_doc.get("company") or "").strip()
        url = ctx.job_doc.get("company_url") or (ctx.job_doc.get("company_research") or {}).get("url")
        status = "completed"
        notes: list[str] = []
        if not company:
            status = "unresolved"
            notes.append("Company identity unresolved; no research attempted.")
        elif not web_research_enabled():
            status = "no_research"
            notes.append("WEB_RESEARCH_ENABLED=false")

        existing = ctx.job_doc.get("company_research") or {}
        profile = CompanyProfile(
            company_name=company or None,
            company_type=existing.get("company_type"),
            summary=existing.get("summary") or (f"Public research not available for {company}." if company else None),
            url=url,
            signals=list(existing.get("signals") or []),
        )
        artifact = ResearchEnrichmentDoc(
            job_id=str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id")),
            level2_job_id=str(ctx.job_doc.get("_id")),
            jd_facts_id="__ref__:jd_facts.id",
            research_input_hash=f"{ctx.company_checksum}:{ctx.config.prompt_version}",
            prompt_version=PROMPT_VERSION,
            status=status,
            capability_flags={"web_research_enabled": web_research_enabled()},
            company_profile=profile,
            sources=[],
            notes=notes,
        )
        return StageResult(
            stage_output=artifact.model_dump(),
            artifact_writes=[
                ArtifactWrite(
                    collection="research_enrichment",
                    unique_filter={
                        "jd_facts_id": "__ref__:jd_facts.id",
                        "research_input_hash": artifact.research_input_hash,
                        "prompt_version": artifact.prompt_version,
                    },
                    document=artifact.model_dump(),
                    ref_name="research_enrichment",
                )
            ],
            provider_used=ctx.config.provider,
            model_used=ctx.config.primary_model,
            prompt_version=PROMPT_VERSION,
        )
