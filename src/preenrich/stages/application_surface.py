"""Iteration-4.1 application_surface stage."""

from __future__ import annotations

from typing import List

from src.preenrich.stages.blueprint_common import detect_portal_family, normalize_url
from src.preenrich.types import StageContext, StageResult

PROMPT_VERSION = "P-application-url:v1"


class ApplicationSurfaceStage:
    name: str = "application_surface"
    dependencies: List[str] = ["jd_facts"]

    def run(self, ctx: StageContext) -> StageResult:
        candidates = [
            normalize_url(ctx.job_doc.get("application_url")),
            normalize_url(ctx.job_doc.get("jobUrl")),
            normalize_url(ctx.job_doc.get("job_url")),
            normalize_url(ctx.job_doc.get("url")),
        ]
        deduped = [value for value in dict.fromkeys([item for item in candidates if item])]
        application_url = deduped[0] if len(deduped) == 1 else None
        status = "resolved" if application_url else ("ambiguous" if len(deduped) > 1 else "unresolved")
        portal_family = detect_portal_family(application_url or (deduped[0] if deduped else None))
        friction_signals: list[str] = []
        if portal_family in {"workday", "greenhouse", "lever"}:
            friction_signals.append("multi_step_likely")
        if portal_family in {"workday", "bamboohr"}:
            friction_signals.append("account_creation_likely")
        stage_output = {
            "status": status,
            "job_url": deduped[0] if deduped else None,
            "application_url": application_url,
            "portal_family": portal_family,
            "is_direct_apply": bool(application_url and "linkedin.com" not in application_url.lower()),
            "friction_signals": friction_signals,
            "candidates": deduped,
        }
        output = {"application_url": application_url or ctx.job_doc.get("application_url")}
        return StageResult(
            output=output,
            stage_output=stage_output,
            provider_used="none" if status != "ambiguous" else ctx.config.provider,
            model_used=None if status != "ambiguous" else ctx.config.primary_model,
            prompt_version=PROMPT_VERSION,
        )

