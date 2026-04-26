"""
role_research stage — thin adapter over src/layer3/role_researcher.RoleResearcher.

Default provider: Claude Sonnet (per plan §4).
Codex path raises NotImplementedError (Phase 6).

Dependencies: ["jd_extraction", "company_research"]

NOTE: This stage runs even when company_research was a cache hit. The cache hit
materializes company_research data into the patch (and the job_doc for the next tick),
so role_research has the company context it needs. This is an explicit behaviour
change from CompanyResearchService which previously skipped role_research on cache hit
(plan §3.4).

Output patch: {"role_research": {...}}
"""

import logging
import time
from typing import Any, Dict, List

from src.layer3.role_researcher import RoleResearcher
from src.preenrich.stages.base import StageBase
from src.preenrich.types import StageContext, StageResult

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"


class RoleResearchStage:
    """
    Thin adapter over layer3.role_researcher.RoleResearcher.

    Reads company_research from job_doc (populated by the company_research stage).
    Runs unconditionally — cache hit or fresh company_research both provide
    the required context.
    """

    name: str = "role_research"
    dependencies: List[str] = ["jd_extraction", "company_research"]

    def run(self, ctx: StageContext) -> StageResult:
        """
        Perform role research.

        Args:
            ctx: Stage context. config.provider must be "claude" or "codex".

        Returns:
            StageResult with output patch {"role_research": {...}}.

        Raises:
            NotImplementedError: If config.provider == "codex"
            ValueError: If unsupported provider, missing JD text, or research fails
        """
        provider = ctx.config.provider if ctx.config else "claude"

        if provider == "codex":
            raise NotImplementedError(
                "codex provider pending Phase 6 cutover — use provider='claude'"
            )

        if provider != "claude":
            raise ValueError(
                f"Unsupported provider '{provider}' for role_research. "
                "Valid values: 'claude', 'codex' (pending)."
            )

        return self._run_claude(ctx)

    def _run_claude(self, ctx: StageContext) -> StageResult:
        """Run role research via RoleResearcher."""
        from src.common.state import JobState

        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))

        jd_text: str = (
            job_doc.get("job_description")
            or job_doc.get("description")
            or job_doc.get("jd_text")
            or ""
        )
        if not jd_text.strip():
            raise ValueError(
                f"No JD text available for role_research on job {job_id}"
            )

        # company_research should be populated by the upstream stage
        # (either from cache-hit materialization or fresh research)
        company_research = job_doc.get("company_research")
        if not company_research:
            raise ValueError(
                f"No company_research available for role_research on job {job_id}. "
                "company_research stage must complete (or be skipped with cache data) first."
            )

        # Check if company is a recruitment agency — skip role research in that case
        # (matches the existing behaviour in CompanyResearchService)
        company_type = company_research.get("company_type", "employer")
        if company_type == "recruitment_agency":
            logger.info(
                "role_research: skipping for job %s (recruitment_agency)", job_id
            )
            return StageResult(
                output={},
                provider_used="claude",
                model_used=None,
                prompt_version=PROMPT_VERSION,
                skip_reason="recruitment_agency",
            )

        # Build JobState for RoleResearcher
        state: JobState = {
            "job_id": job_id,
            "title": job_doc.get("title", ""),
            "company": job_doc.get("company", "") or job_doc.get("firm", ""),
            "job_description": jd_text,
            "job_url": job_doc.get("job_url") or job_doc.get("url", ""),
            "source": job_doc.get("source", ""),
            "candidate_profile": "",
            "extracted_jd": job_doc.get("extracted_jd"),
            "selected_stars": job_doc.get("selected_stars"),
            "company_research": company_research,
            "role_research": job_doc.get("role_research"),
            "errors": job_doc.get("errors", []),
            "scraped_job_posting": None,
            "jd_annotations": job_doc.get("jd_annotations"),
            "improvement_suggestions": None,
            "interview_prep": None,
            "pain_points": job_doc.get("pain_points"),
            "strategic_needs": job_doc.get("strategic_needs"),
            "risks_if_unfilled": job_doc.get("risks_if_unfilled"),
            "success_metrics": job_doc.get("success_metrics"),
            "star_to_pain_mapping": job_doc.get("star_to_pain_mapping"),
            "all_stars": None,
            "company_summary": job_doc.get("company_summary"),
            "company_url": job_doc.get("company_url"),
            "application_form_fields": None,
            "fit_score": job_doc.get("fit_score"),
            "fit_rationale": job_doc.get("fit_rationale"),
            "fit_category": job_doc.get("fit_category"),
            "tier": job_doc.get("tier"),
            "primary_contacts": None,
            "secondary_contacts": None,
            "people": None,
            "outreach_packages": None,
            "fallback_cover_letters": None,
            "cover_letter": None,
            "cv_path": None,
            "cv_text": None,
            "cv_reasoning": None,
            "dossier_path": None,
            "drive_folder_url": None,
            "sheet_row_id": None,
            "run_id": None,
            "created_at": None,
            "status": "processing",
            "trace_url": None,
            "token_usage": None,
            "total_tokens": None,
            "total_cost_usd": None,
            "processing_tier": None,
            "tier_config": None,
            "pipeline_runs": None,
            "debug_mode": None,
        }

        researcher = RoleResearcher()

        t0 = time.monotonic()
        try:
            role_result: Dict[str, Any] = researcher.research_role(state)
        except Exception as exc:
            raise ValueError(
                f"RoleResearcher failed for job {job_id}: {exc}"
            ) from exc
        duration_ms = int((time.monotonic() - t0) * 1000)

        role_research = role_result.get("role_research")
        if not role_research:
            errors = role_result.get("errors", [])
            error_detail = errors[-1] if errors else "No role_research in result"
            raise ValueError(
                f"role_research stage failed for job {job_id}: {error_detail}"
            )

        impact_count = len(role_research.get("business_impact", []))
        logger.debug(
            "role_research: completed for job %s (%d business impacts, duration=%dms)",
            job_id,
            impact_count,
            duration_ms,
        )

        return StageResult(
            output={"role_research": role_research},
            provider_used="claude",
            model_used=None,
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
        )


# Verify protocol compliance at import time
assert isinstance(RoleResearchStage(), StageBase), (
    "RoleResearchStage does not satisfy StageBase protocol"
)
