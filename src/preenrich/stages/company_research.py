"""
company_research stage — wraps CompanyResearcher (company branch only).

Default provider: Claude Sonnet + WebSearch (per plan §4).
Codex path raises NotImplementedError (Codex CLI web access is not a production contract).

Dependencies: [] (company name-driven, no upstream stage required)
Output patch: {"company_research": {...}, "company_summary": str|None, "company_url": str|None}

Cache-hit logic (plan S9):
- Before running, check company_cache collection (7d TTL per existing contract).
- If hit: materialize cached data into job.company_research via the patch,
  return StageResult with status via skip_reason="company_cache_hit" and
  cache_source_job_id set.
- If miss: run research via CompanyResearcher, write company_cache entry
  (reuse existing upsert_cache path), return COMPLETED.

Behaviour change from CompanyResearchService (plan §3.4):
- company_research and role_research are now independent stages.
- Cache-hit no longer skips role_research. The role_research stage still runs
  because the dependency graph requires it; it consumes company_research data
  whether it came from cache or a fresh run.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.common.repositories import get_company_cache_repository
from src.layer3.company_researcher import CompanyResearcher
from src.preenrich.stages.base import StageBase
from src.preenrich.types import StageContext, StageResult

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
COMPANY_CACHE_TTL_DAYS = 7


class CompanyResearchStage:
    """
    Adapter over layer3.company_researcher.CompanyResearcher (company branch only).

    The stage is responsible for:
    1. Cache lookup via company_cache collection (7d TTL).
    2. On cache miss: run CompanyResearcher, save result to company_cache.
    3. Return a patch with company_research, company_summary, company_url.

    Role research is NOT run here — that is a separate stage (role_research.py).
    This is an explicit behaviour change from CompanyResearchService which previously
    skipped role_research on cache hit (plan §3.4).
    """

    name: str = "company_research"
    dependencies: List[str] = []

    def run(self, ctx: StageContext) -> StageResult:
        """
        Perform company research or return cached result.

        Args:
            ctx: Stage context. config.provider must be "claude" or "codex".

        Returns:
            StageResult with output patch. When cache hit, skip_reason is set to
            "company_cache_hit" and cache_source_job_id contains the canonical
            company_cache document's company_key (not a job _id — the cache is
            keyed by company name, not job).

        Raises:
            NotImplementedError: If config.provider == "codex"
            ValueError: If unsupported provider or company name is missing
        """
        provider = ctx.config.provider if ctx.config else "claude"

        if provider == "codex":
            raise NotImplementedError(
                "codex provider: Codex CLI web access is not a production contract. "
                "Use provider='claude' for company_research."
            )

        if provider != "claude":
            raise ValueError(
                f"Unsupported provider '{provider}' for company_research. "
                "Valid values: 'claude'."
            )

        return self._run_claude(ctx)

    def _run_claude(self, ctx: StageContext) -> StageResult:
        """Run company research (cache-aware) via CompanyResearcher."""
        from src.common.state import JobState

        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))

        company_name = job_doc.get("company", "") or job_doc.get("firm", "")
        if not company_name:
            raise ValueError(
                f"No company name in job_doc for job {job_id} — cannot run company_research"
            )

        company_key = company_name.lower().strip()

        # ── Cache lookup ─────────────────────────────────────────────────────
        t0 = time.monotonic()
        cache_repo = get_company_cache_repository()

        try:
            cached = cache_repo.find_by_company_key(company_key)
        except Exception as cache_err:
            logger.warning(
                "company_research: cache lookup failed for %s: %s — running fresh research",
                company_name,
                cache_err,
            )
            cached = None

        if cached:
            cached_at: Optional[datetime] = cached.get("cached_at")
            if cached_at:
                expiry = cached_at + timedelta(days=COMPANY_CACHE_TTL_DAYS)
                if datetime.utcnow() < expiry:
                    # Cache HIT — materialize per-job patch from canonical cache entry
                    company_research = cached.get("company_research") or {}
                    duration_ms = int((time.monotonic() - t0) * 1000)

                    patch = _build_company_patch(company_research)

                    logger.info(
                        "company_research: cache HIT for '%s' (job %s, cached_at=%s)",
                        company_name,
                        job_id,
                        cached_at.isoformat() if hasattr(cached_at, "isoformat") else str(cached_at),
                    )

                    return StageResult(
                        output=patch,
                        provider_used="cache",
                        model_used=None,
                        prompt_version=PROMPT_VERSION,
                        duration_ms=duration_ms,
                        skip_reason="company_cache_hit",
                        cache_source_job_id=company_key,  # canonical cache key
                    )
                else:
                    logger.info("company_research: cache EXPIRED for '%s'", company_name)
            else:
                logger.info(
                    "company_research: cache entry has no cached_at for '%s' — running fresh",
                    company_name,
                )

        # ── Cache MISS — run fresh research ──────────────────────────────────
        logger.info(
            "company_research: cache MISS for '%s' (job %s) — running CompanyResearcher",
            company_name,
            job_id,
        )

        # Build minimal JobState for company researcher
        jd_text: str = (
            job_doc.get("job_description")
            or job_doc.get("description")
            or job_doc.get("jd_text")
            or ""
        )
        state: JobState = {
            "job_id": job_id,
            "title": job_doc.get("title", ""),
            "company": company_name,
            "job_description": jd_text,
            "job_url": job_doc.get("job_url") or job_doc.get("url", ""),
            "source": job_doc.get("source", ""),
            "candidate_profile": "",
            "extracted_jd": job_doc.get("extracted_jd"),
            "selected_stars": job_doc.get("selected_stars"),
            "company_research": job_doc.get("company_research"),
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

        researcher = CompanyResearcher()
        try:
            company_result: Dict[str, Any] = researcher.research_company(state)
        except Exception as exc:
            raise ValueError(
                f"CompanyResearcher failed for job {job_id} (company='{company_name}'): {exc}"
            ) from exc

        duration_ms = int((time.monotonic() - t0) * 1000)

        company_research = company_result.get("company_research")
        if not company_research:
            errors = company_result.get("errors", [])
            error_detail = errors[-1] if errors else "No company_research in result"
            raise ValueError(
                f"company_research stage failed for job {job_id}: {error_detail}"
            )

        # ── Write to company_cache (reuse existing upsert_cache path) ─────────
        try:
            cache_entry: Dict[str, Any] = {
                "company_key": company_key,
                "company_name": company_name,
                "company_research": company_research,
                "cached_at": datetime.utcnow(),
                "source_job_id": job_id,
            }
            cache_repo.upsert_cache(company_key, cache_entry)
            logger.info("company_research: wrote cache entry for '%s'", company_name)
        except Exception as cache_write_err:
            # Non-fatal — research succeeded, only caching failed
            logger.warning(
                "company_research: failed to write cache entry for '%s': %s",
                company_name,
                cache_write_err,
            )

        patch = _build_company_patch(company_research)

        logger.debug(
            "company_research: fresh research completed for '%s' (job %s, duration=%dms)",
            company_name,
            job_id,
            duration_ms,
        )

        return StageResult(
            output=patch,
            provider_used="claude",
            model_used=None,
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
        )


def _build_company_patch(company_research: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the Mongo patch from company_research data.

    Matches the field shape written by CompanyResearchService._persist_research().
    """
    return {
        "company_research": company_research,
        # Legacy fields for backward compatibility
        "company_summary": company_research.get("summary"),
        "company_url": company_research.get("url"),
    }


# Verify protocol compliance at import time
assert isinstance(CompanyResearchStage(), StageBase), (
    "CompanyResearchStage does not satisfy StageBase protocol"
)
