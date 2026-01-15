"""
Company Research Service (Phase 4).

Provides button-triggered company and role research as an independent operation.
Wraps the existing Layer 3 (Company Researcher) and Layer 3.5 (Role Researcher)
logic with OperationService patterns.

Usage:
    service = CompanyResearchService()
    result = await service.execute(job_id, tier, force_refresh=False)
"""

import asyncio
import json
import logging
import os
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from bson import ObjectId

from src.common.model_tiers import (
    ModelTier,
    get_model_for_operation,
    get_tier_cost_estimate,
)
from src.common.repositories import (
    get_job_repository,
    JobRepositoryInterface,
    get_company_cache_repository,
    CompanyCacheRepositoryInterface,
)
from src.common.state import JobState, CompanyResearch, RoleResearch
from src.layer3.company_researcher import CompanyResearcher
from src.layer3.role_researcher import RoleResearcher
from src.layer5.people_mapper import PeopleMapper
from src.services.operation_base import OperationResult, OperationService

logger = logging.getLogger(__name__)

# Cache TTL in days
COMPANY_CACHE_TTL_DAYS = 7


class CompanyResearchService(OperationService):
    """
    Service for company and role research operations.

    Wraps Layer 3 (Company Researcher) and Layer 3.5 (Role Researcher)
    as a button-triggered operation with cost tracking and caching.
    """

    operation_name: str = "research-company"

    def __init__(
        self,
        repository: Optional[JobRepositoryInterface] = None,
        cache_repository: Optional[CompanyCacheRepositoryInterface] = None,
    ):
        """Initialize the service with optional repositories."""
        self._repository = repository
        self._cache_repository = cache_repository
        self._company_researcher: Optional[CompanyResearcher] = None
        self._role_researcher: Optional[RoleResearcher] = None
        self._people_mapper: Optional[PeopleMapper] = None

    def _get_repository(self) -> JobRepositoryInterface:
        """Get the job repository instance."""
        if self._repository is not None:
            return self._repository
        return get_job_repository()

    def _get_cache_repository(self) -> CompanyCacheRepositoryInterface:
        """Get the company cache repository instance."""
        if self._cache_repository is not None:
            return self._cache_repository
        return get_company_cache_repository()

    @property
    def company_researcher(self) -> CompanyResearcher:
        """Lazy-initialize Company Researcher."""
        if self._company_researcher is None:
            self._company_researcher = CompanyResearcher()
        return self._company_researcher

    @property
    def role_researcher(self) -> RoleResearcher:
        """Lazy-initialize Role Researcher."""
        if self._role_researcher is None:
            self._role_researcher = RoleResearcher()
        return self._role_researcher

    @property
    def people_mapper(self) -> PeopleMapper:
        """Lazy-initialize People Mapper."""
        if self._people_mapper is None:
            self._people_mapper = PeopleMapper()
        return self._people_mapper

    def _fetch_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch job document from MongoDB.

        Args:
            job_id: MongoDB ObjectId as string

        Returns:
            Job document or None if not found
        """
        try:
            object_id = ObjectId(job_id)
            repo = self._get_repository()
            return repo.find_one({"_id": object_id})
        except Exception as e:
            logger.error(f"Failed to fetch job {job_id}: {e}")
            return None

    def _check_cache(
        self, company_name: str, force_refresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Check company cache for existing research.

        Args:
            company_name: Company name to look up
            force_refresh: If True, skip cache lookup

        Returns:
            Cached research data or None if not found/expired
        """
        if force_refresh:
            logger.info(f"Force refresh requested, skipping cache for {company_name}")
            return None

        cache_key = company_name.lower().strip()
        cache_repo = self._get_cache_repository()

        cached = cache_repo.find_by_company_key(cache_key)

        if cached:
            # Check if cache is still valid (within TTL)
            cached_at = cached.get("cached_at")
            if cached_at:
                expiry = cached_at + timedelta(days=COMPANY_CACHE_TTL_DAYS)
                if datetime.utcnow() < expiry:
                    logger.info(f"Cache HIT for {company_name}")
                    return cached
                else:
                    logger.info(f"Cache EXPIRED for {company_name}")
                    return None

        logger.info(f"Cache MISS for {company_name}")
        return None

    def _build_job_state(self, job: Dict[str, Any]) -> JobState:
        """
        Build JobState from MongoDB job document.

        Args:
            job: Job document from MongoDB

        Returns:
            JobState TypedDict for research processing
        """
        # Extract job description from various possible fields
        jd_text = (
            job.get("jd_text")
            or job.get("description")
            or job.get("job_description")
            or ""
        )

        # Build minimal JobState for research
        state: JobState = {
            "job_id": str(job["_id"]),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "job_description": jd_text,
            "job_url": job.get("url") or job.get("job_url", ""),
            "source": job.get("source", ""),
            "candidate_profile": "",  # Not needed for research
            # Optional fields from existing state
            "extracted_jd": job.get("extracted_jd"),
            "selected_stars": job.get("selected_stars"),
            "company_research": job.get("company_research"),
            "role_research": job.get("role_research"),
            "errors": job.get("errors", []),
            # Initialize remaining fields - include jd_annotations if available
            "scraped_job_posting": None,
            # Phase 4: Pass jd_annotations for annotation-guided research
            "jd_annotations": job.get("jd_annotations"),
            "improvement_suggestions": None,
            "interview_prep": None,
            "pain_points": job.get("pain_points"),
            "strategic_needs": job.get("strategic_needs"),
            "risks_if_unfilled": job.get("risks_if_unfilled"),
            "success_metrics": job.get("success_metrics"),
            "star_to_pain_mapping": job.get("star_to_pain_mapping"),
            "all_stars": None,
            "company_summary": job.get("company_summary"),
            "company_url": job.get("company_url"),
            "application_form_fields": None,
            "fit_score": job.get("fit_score"),
            "fit_rationale": job.get("fit_rationale"),
            "fit_category": job.get("fit_category"),
            "tier": job.get("tier"),
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

        return state

    def _persist_research(
        self,
        job_id: str,
        company_research: Optional[CompanyResearch],
        role_research: Optional[RoleResearch],
        scraped_job_posting: Optional[str] = None,
        primary_contacts: Optional[list] = None,
        secondary_contacts: Optional[list] = None,
    ) -> bool:
        """
        Persist research results back to MongoDB.

        Args:
            job_id: MongoDB ObjectId as string
            company_research: Company research result
            role_research: Role research result
            scraped_job_posting: Optional scraped job posting markdown
            primary_contacts: Optional list of primary contacts from people research
            secondary_contacts: Optional list of secondary contacts from people research

        Returns:
            True if persisted successfully
        """
        try:
            object_id = ObjectId(job_id)
            update_doc: Dict[str, Any] = {
                "updatedAt": datetime.utcnow(),
            }

            if company_research:
                update_doc["company_research"] = company_research
                # Also set legacy fields for backward compatibility
                update_doc["company_summary"] = company_research.get("summary")
                update_doc["company_url"] = company_research.get("url")

            if role_research:
                update_doc["role_research"] = role_research

            if scraped_job_posting:
                update_doc["scraped_job_posting"] = scraped_job_posting

            # Persist people research contacts
            if primary_contacts is not None:
                update_doc["primary_contacts"] = primary_contacts
            if secondary_contacts is not None:
                update_doc["secondary_contacts"] = secondary_contacts

            repo = self._get_repository()
            result = repo.update_one(
                {"_id": object_id},
                {"$set": update_doc}
            )

            if result.modified_count > 0:
                logger.info(f"Persisted research for job {job_id}")
                return True
            else:
                logger.warning(f"No changes persisted for job {job_id}")
                return True  # Document found but no changes needed

        except Exception as e:
            logger.error(f"Failed to persist research for job {job_id}: {e}")
            return False

    async def execute(
        self,
        job_id: str,
        tier: ModelTier,
        force_refresh: bool = False,
        progress_callback: callable = None,
        log_callback: callable = None,
        parent_run_id: Optional[str] = None,
        **kwargs,
    ) -> OperationResult:
        """
        Execute company and role research for a job.

        Args:
            job_id: MongoDB ObjectId of the job
            tier: Model tier for quality/cost selection
            force_refresh: If True, skip cache and re-research
            progress_callback: Optional callback(layer_key, status, message) for real-time updates
            log_callback: Optional callback(message: str) for log streaming to frontend
            parent_run_id: Optional run_id from parent pipeline (e.g., BatchPipelineService).
                          If provided, logs to parent's run_id for unified CLI visibility.
            **kwargs: Additional parameters (unused)

        Returns:
            OperationResult with research data and cost info
        """
        # Helper to call progress callback if provided (async to yield to event loop)
        async def emit_progress(layer_key: str, status: str, message: str):
            if progress_callback:
                try:
                    progress_callback(layer_key, status, message)
                    await asyncio.sleep(0)  # CRITICAL: Yield to event loop for SSE delivery
                except Exception as e:
                    logger.warning(f"Progress callback failed: {e}")

        run_id = self.create_run_id(parent_run_id)
        model = self.get_model(tier)

        logger.info(
            f"[{run_id[:16]}] Starting company research for job {job_id} "
            f"(tier={tier.value}, model={model}, force_refresh={force_refresh})"
        )

        with self.timed_execution() as timer:
            # Track per-layer status for detailed logging
            layer_status = {}

            try:
                # Fetch job from MongoDB
                await emit_progress("fetch_job", "processing", "Loading job data")
                logger.info(f"[{run_id[:16]}] Fetching job from database")
                job = self._fetch_job(job_id)
                if not job:
                    layer_status["fetch_job"] = {
                        "status": "failed",
                        "message": f"Job not found: {job_id}"
                    }
                    await emit_progress("fetch_job", "failed", f"Job not found: {job_id}")
                    return self.create_error_result(
                        run_id=run_id,
                        error=f"Job not found: {job_id}",
                        duration_ms=timer.duration_ms,
                    )
                layer_status["fetch_job"] = {
                    "status": "success",
                    "message": f"Found job: {job.get('title', 'Unknown')}"
                }
                await emit_progress("fetch_job", "success", "Job loaded")

                company_name = job.get("company", "")
                if not company_name:
                    layer_status["validate"] = {
                        "status": "failed",
                        "message": "Job has no company name"
                    }
                    return self.create_error_result(
                        run_id=run_id,
                        error="Job has no company name",
                        duration_ms=timer.duration_ms,
                    )

                # Check cache (unless force_refresh)
                await emit_progress("cache_check", "processing", "Checking cache")
                cached = self._check_cache(company_name, force_refresh)

                # Track if we need to run contact discovery even with cached company research
                use_cached_company_research = False
                cached_research = None

                if cached and not force_refresh:
                    cached_research = cached.get("company_research", {})

                    # Cache hit for company research only
                    # NOTE: Contacts are ROLE-SPECIFIC and should NEVER be cached.
                    # Each job application targets different roles, so contact discovery
                    # must always run fresh to find relevant hiring managers/team leads.
                    logger.info(f"[{run_id[:16]}] Cache hit - using cached company research, running fresh contact discovery for {company_name}")
                    layer_status["cache_check"] = {
                        "status": "success",
                        "message": f"Cache hit for {company_name} (running fresh contact discovery)"
                    }
                    await emit_progress("cache_check", "success", f"Cache hit for {company_name} (contacts always fresh)")
                    use_cached_company_research = True
                    # Continue to contact discovery below

                if not use_cached_company_research:
                    layer_status["cache_check"] = {
                        "status": "success",
                        "message": "Cache miss - running fresh research"
                    }
                    await emit_progress("cache_check", "success", "Cache miss - running fresh research")

                # Build JobState for research
                state = self._build_job_state(job)

                # Initialize variables for company/role research
                company_research = None
                company_result = {}  # Empty dict for cached case
                scraped_job_posting = None
                role_research = None

                # Skip company research if using cached data
                if use_cached_company_research:
                    # Use cached company research, skip fresh research
                    company_research = cached_research
                    state["company_research"] = company_research
                    layer_status["company_research"] = {
                        "status": "success",
                        "message": "Using cached company research",
                        "from_cache": True,
                    }
                    await emit_progress("company_research", "success", "Using cached research")
                    layer_status["role_research"] = {
                        "status": "skipped",
                        "message": "Skipped (using cached data)"
                    }
                    await emit_progress("role_research", "skipped", "Skipped (using cached data)")
                    logger.info(f"[{run_id[:16]}] Using cached company research, skipping role research")
                else:
                    # Run Company Research (Layer 3)
                    await emit_progress("company_research", "processing", f"Researching {company_name}")
                    logger.info(f"[{run_id[:16]}] Running company research for {company_name}")

                    # Create CompanyResearcher with log_callback for this invocation
                    researcher = CompanyResearcher(log_callback=log_callback)
                    company_result = researcher.research_company(state)

                    company_research = company_result.get("company_research")
                    scraped_job_posting = company_result.get("scraped_job_posting")

                    if company_research:
                        signals_count = len(company_research.get("signals", []))
                        company_type = company_research.get("company_type", "unknown")
                        layer_status["company_research"] = {
                            "status": "success",
                            "signals": signals_count,
                            "company_type": company_type,
                            "message": f"Found {signals_count} signals, type: {company_type}"
                        }
                        await emit_progress("company_research", "success", f"Found {signals_count} signals")
                        state["company_research"] = company_research
                    else:
                        # Extract error details from the result
                        errors = company_result.get("errors", [])
                        error_detail = errors[-1] if errors else "No details available"
                        layer_status["company_research"] = {
                            "status": "failed",
                            "message": f"Company research failed: {error_detail}",
                            "errors": errors,
                        }
                        await emit_progress("company_research", "failed", f"Failed after all fallbacks: {error_detail}")
                    logger.info(f"[{run_id[:16]}] Company research complete: {layer_status['company_research']['message']}")

                    # Run Role Research (Layer 3.5) if company research succeeded
                    if company_research:
                        # Skip role research for recruitment agencies
                        company_type = company_research.get("company_type", "employer")
                        if company_type != "recruitment_agency":
                            await emit_progress("role_research", "processing", "Researching role context")
                            logger.info(f"[{run_id[:16]}] Running role research")
                            role_result = self.role_researcher.research_role(state)
                            role_research = role_result.get("role_research")
                            if role_research:
                                business_impact_count = len(role_research.get("business_impact", []))
                                layer_status["role_research"] = {
                                    "status": "success",
                                    "business_impacts": business_impact_count,
                                    "message": f"Found {business_impact_count} business impacts"
                                }
                                await emit_progress("role_research", "success", f"Found {business_impact_count} impacts")
                                # Update state with role research for people mapper
                                state["role_research"] = role_research
                            else:
                                # Extract detailed error information from the result
                                role_errors = role_result.get("errors", [])
                                role_traceback = role_result.get("role_research_traceback", "")
                                error_detail = role_errors[-1] if role_errors else "Unknown error"

                                layer_status["role_research"] = {
                                    "status": "failed",
                                    "message": f"Role research failed: {error_detail}",
                                    "errors": role_errors,
                                    "traceback": role_traceback,
                                }
                                await emit_progress("role_research", "failed", f"Role research failed: {error_detail}")
                        else:
                            layer_status["role_research"] = {
                                "status": "skipped",
                                "message": "Skipped for recruitment agency"
                            }
                            await emit_progress("role_research", "skipped", "Skipped (recruitment agency)")
                            logger.info(f"[{run_id[:16]}] Skipping role research (recruitment agency)")
                    else:
                        layer_status["role_research"] = {
                            "status": "skipped",
                            "message": "Skipped - company research failed"
                        }
                        await emit_progress("role_research", "skipped", "Skipped (company research failed)")

                # Run People Research (Layer 5) with skip_outreach=True
                # Contact discovery happens here; outreach generation is triggered separately
                primary_contacts = None
                secondary_contacts = None
                if company_research:
                    await emit_progress("people_research", "processing", "Discovering contacts")
                    logger.info(f"[{run_id[:16]}] Running people research (contact discovery only)")
                    try:
                        people_result = self.people_mapper.map_people(state, skip_outreach=True)
                        primary_contacts = people_result.get("primary_contacts", [])
                        secondary_contacts = people_result.get("secondary_contacts", [])

                        total_contacts = len(primary_contacts) + len(secondary_contacts)
                        if total_contacts > 0:
                            layer_status["people_research"] = {
                                "status": "success",
                                "primary_contacts": len(primary_contacts),
                                "secondary_contacts": len(secondary_contacts),
                                "message": f"Found {len(primary_contacts)} primary + {len(secondary_contacts)} secondary contacts"
                            }
                            await emit_progress("people_research", "success", f"Found {total_contacts} contacts")
                        else:
                            layer_status["people_research"] = {
                                "status": "warning",
                                "primary_contacts": 0,
                                "secondary_contacts": 0,
                                "message": "No contacts discovered"
                            }
                            await emit_progress("people_research", "warning", "No contacts found")
                        logger.info(f"[{run_id[:16]}] People research complete: {layer_status['people_research']['message']}")

                    except Exception as e:
                        logger.warning(f"[{run_id[:16]}] People research failed (non-fatal): {e}")
                        layer_status["people_research"] = {
                            "status": "failed",
                            "message": f"People research failed: {str(e)}"
                        }
                        await emit_progress("people_research", "failed", "Contact discovery failed")
                else:
                    layer_status["people_research"] = {
                        "status": "skipped",
                        "message": "Skipped - company research failed"
                    }
                    await emit_progress("people_research", "skipped", "Skipped (company research failed)")

                # Persist results to MongoDB
                await emit_progress("save_results", "processing", "Saving to database")
                logger.info(f"[{run_id[:16]}] Persisting results to database")
                persisted = self._persist_research(
                    job_id=job_id,
                    company_research=company_research,
                    role_research=role_research,
                    scraped_job_posting=scraped_job_posting,
                    primary_contacts=primary_contacts,
                    secondary_contacts=secondary_contacts,
                )
                layer_status["persist"] = {
                    "status": "success" if persisted else "warning",
                    "message": "Saved to database" if persisted else "Persistence failed"
                }
                await emit_progress("save_results", "success" if persisted else "failed",
                             "Results saved" if persisted else "Persistence failed")

                # Estimate cost (rough estimate based on typical token usage)
                # Company research: ~3000 input, ~2000 output
                # Role research: ~2000 input, ~1000 output
                # People research (contact discovery only, no outreach): ~2000 input, ~1500 output
                estimated_input_tokens = 7000
                estimated_output_tokens = 4500
                cost_usd = self.estimate_cost(tier, estimated_input_tokens, estimated_output_tokens)

                # Collect any errors from the research process
                errors = company_result.get("errors", [])
                if role_research is None and company_research:
                    # Role research might have failed
                    pass  # Errors would be in role_result if we had it

                # Build response data with layer_status
                response_data = {
                    "company_research": company_research,
                    "role_research": role_research,
                    "primary_contacts": primary_contacts,
                    "secondary_contacts": secondary_contacts,
                    "from_cache": False,
                    "company": company_name,
                    "layer_status": layer_status,
                }

                # Add summary stats
                if company_research:
                    response_data["signals_count"] = len(company_research.get("signals", []))
                    response_data["company_type"] = company_research.get("company_type", "unknown")

                if role_research:
                    response_data["business_impact_count"] = len(role_research.get("business_impact", []))

                # Add contacts count
                if primary_contacts or secondary_contacts:
                    response_data["primary_contacts_count"] = len(primary_contacts) if primary_contacts else 0
                    response_data["secondary_contacts_count"] = len(secondary_contacts) if secondary_contacts else 0

                logger.info(
                    f"[{run_id[:16]}] Completed research: "
                    f"signals={response_data.get('signals_count', 0)}, "
                    f"company_type={response_data.get('company_type', 'unknown')}, "
                    f"contacts={response_data.get('primary_contacts_count', 0)}+{response_data.get('secondary_contacts_count', 0)}"
                )

                # Persist operation run for tracking
                result = self.create_success_result(
                    run_id=run_id,
                    data=response_data,
                    cost_usd=cost_usd,
                    duration_ms=timer.duration_ms,
                    input_tokens=estimated_input_tokens,
                    output_tokens=estimated_output_tokens,
                    model_used=model,
                )

                self.persist_run(result, job_id, tier)

                return result

            except Exception as e:
                # Capture full traceback for frontend display
                tb_str = traceback.format_exc()
                error_msg = f"{type(e).__name__}: {str(e)}"

                logger.exception(f"[{run_id[:16]}] Company research failed: {e}")

                # Emit structured error log with traceback for frontend CLI panel
                if log_callback:
                    error_log = json.dumps({
                        "event": "layer_error",
                        "layer_name": "company_research",
                        "error": error_msg,
                        "metadata": {
                            "error_type": type(e).__name__,
                            "traceback": tb_str,
                            "context": "CompanyResearchService.execute",
                            "run_id": run_id,
                        }
                    })
                    log_callback(error_log)

                # Also emit progress callback with error details
                if progress_callback:
                    try:
                        # Include traceback in metadata if layer_callback supports it
                        progress_callback(
                            "company_research",
                            "error",
                            error_msg,
                            {"traceback": tb_str, "error_type": type(e).__name__},
                        )
                    except TypeError:
                        # Fallback if callback doesn't accept metadata
                        progress_callback("company_research", "error", error_msg)

                error_result = self.create_error_result(
                    run_id=run_id,
                    error=str(e),
                    duration_ms=timer.duration_ms,
                )
                self.persist_run(error_result, job_id, tier)
                return error_result
