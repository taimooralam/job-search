"""Iteration-4.1 classification stage."""

from __future__ import annotations

from typing import Any, List

from src.preenrich.blueprint_config import load_job_taxonomy, taxonomy_version
from src.preenrich.blueprint_models import ClassificationDoc
from src.preenrich.stages.base import StageBase
from src.preenrich.stages.blueprint_common import ai_relevance, search_profiles_for_primary, selector_profiles_for_primary, title_family, tone_for_primary
from src.preenrich.types import StageContext, StageResult

PROMPT_VERSION = "P-classify:v1"


class ClassificationStage:
    name: str = "classification"
    dependencies: List[str] = ["jd_facts"]

    def run(self, ctx: StageContext) -> StageResult:
        jd_facts = ((((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {}).get("jd_facts")) or {})
        merged = jd_facts.get("merged_view") or {}
        title = str(merged.get("title") or ctx.job_doc.get("title") or "")
        description = str(ctx.job_doc.get("description") or ctx.job_doc.get("job_description") or "")

        primary = title_family(title)
        classification = ClassificationDoc(
            primary_role_category=primary,
            secondary_role_categories=[],
            search_profiles=search_profiles_for_primary(primary),
            selector_profiles=selector_profiles_for_primary(primary),
            tone_family=tone_for_primary(primary),
            taxonomy_version=taxonomy_version(),
            ambiguity_score=0.1,
            ai_relevance=ai_relevance(description, title),
        )
        ai_meta = classification.ai_relevance
        ai_patch = {
            "is_ai_job": bool(ai_meta.get("is_ai_job")),
            "ai_categories": ai_meta.get("categories", []),
            "ai_category_count": len(ai_meta.get("categories", [])),
            "ai_rationale": ai_meta.get("rationale"),
            "ai_classification": {
                "is_ai_job": bool(ai_meta.get("is_ai_job")),
                "ai_categories": ai_meta.get("categories", []),
                "ai_category_count": len(ai_meta.get("categories", [])),
                "ai_rationale": ai_meta.get("rationale"),
                "taxonomy_version": classification.taxonomy_version,
            },
        }
        return StageResult(
            output=ai_patch,
            stage_output=classification.model_dump(),
            provider_used=ctx.config.provider,
            model_used=ctx.config.primary_model,
            prompt_version=PROMPT_VERSION,
        )


assert isinstance(ClassificationStage(), StageBase)
