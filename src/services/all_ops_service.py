"""
All Operations Service - Phase 1 Parallel Execution

Service for running JD extraction and company research in parallel.
This is the "All Ops" button on the job detail page that combines:
- Full Extraction: Layer 1.4 (JD parsing) + Layer 2 (pain points) + Layer 4 (fit scoring)
- Company Research: Layer 3 (company) + Layer 3.5 (role) + Layer 5 (people contacts)

Design:
- Reuses existing FullExtractionService and CompanyResearchService
- Parallel execution via asyncio.gather
- Retry failed operations once, then continue with partial results
- Progress callbacks for SSE streaming
- Aggregates results from both services

Usage:
    service = AllOpsService()
    result = await service.execute(job_id="...", tier=ModelTier.BALANCED)
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.common.model_tiers import ModelTier
from src.services.company_research_service import CompanyResearchService
from src.services.full_extraction_service import FullExtractionService
from src.services.operation_base import OperationResult, OperationService

logger = logging.getLogger(__name__)


class AllOpsService(OperationService):
    """
    Service for running all Phase 1 operations (JD extraction + company research) in parallel.

    This combines:
    - FullExtractionService: JD parsing, pain points, fit scoring
    - CompanyResearchService: Company research, role research, people contacts

    Both services run in parallel for faster execution.
    If one fails, the other's results are still returned (partial success).
    """

    operation_name = "all-ops"

    # Maximum retries for each sub-operation
    MAX_RETRIES = 1

    def __init__(self):
        """Initialize the service with lazy-loaded sub-services."""
        self._extraction_service: Optional[FullExtractionService] = None
        self._research_service: Optional[CompanyResearchService] = None

    @property
    def extraction_service(self) -> FullExtractionService:
        """Lazy-initialize Full Extraction Service."""
        if self._extraction_service is None:
            self._extraction_service = FullExtractionService()
        return self._extraction_service

    @property
    def research_service(self) -> CompanyResearchService:
        """Lazy-initialize Company Research Service."""
        if self._research_service is None:
            self._research_service = CompanyResearchService()
        return self._research_service

    async def _run_with_retry(
        self,
        operation_name: str,
        operation_fn: Callable,
        progress_callback: Optional[Callable] = None,
        max_retries: int = 1,
    ) -> Tuple[Optional[OperationResult], Optional[str]]:
        """
        Run an operation with retry logic.

        Args:
            operation_name: Name for logging/progress (e.g., "extraction", "research")
            operation_fn: Async function that returns OperationResult
            progress_callback: Optional callback(layer_key, status, message)
            max_retries: Maximum number of retry attempts

        Returns:
            Tuple of (result, error):
            - On success: (OperationResult, None)
            - On failure after retries: (None, error_message)
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"Retrying {operation_name} (attempt {attempt + 1})")
                    if progress_callback:
                        progress_callback(
                            operation_name,
                            "retrying",
                            f"Retry attempt {attempt + 1}",
                        )

                result = await operation_fn()

                if result.success:
                    return result, None
                else:
                    # Operation returned but failed
                    last_error = result.error or f"{operation_name} failed"
                    logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}): {last_error}"
                    )

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"{operation_name} exception (attempt {attempt + 1}): {e}"
                )

        # All retries exhausted
        return None, last_error

    async def execute(
        self,
        job_id: str,
        tier: ModelTier,
        force_refresh: bool = False,
        use_llm: bool = True,
        progress_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
        **kwargs,
    ) -> OperationResult:
        """
        Execute all Phase 1 operations in parallel.

        Runs JD extraction and company research concurrently.
        If one fails, continues with partial results from the other.

        Args:
            job_id: MongoDB ObjectId of the job to process
            tier: Model tier for quality/cost selection
            force_refresh: Force refresh for company research (ignore cache)
            use_llm: Whether to use LLM for extraction (default True)
            progress_callback: Optional callback(layer_key, status, message) for structured updates
            log_callback: Optional callback(message: str) for log streaming to SSE frontend
            **kwargs: Additional arguments (ignored)

        Returns:
            OperationResult with combined data from both services
        """
        run_id = self.create_run_id()
        logger.info(f"[{run_id[:16]}] Starting all-ops for job {job_id}")

        # Helper to emit progress with event loop yield
        async def emit_progress(layer_key: str, status: str, message: str):
            if progress_callback:
                try:
                    progress_callback(layer_key, status, message)
                    await asyncio.sleep(0)  # Yield to event loop for SSE delivery
                except Exception as e:
                    logger.warning(f"Progress callback failed: {e}")

        with self.timed_execution() as timer:
            try:
                model = self.get_model(tier)
                logger.info(
                    f"[{run_id[:16]}] Using tier={tier.value}, model={model}, "
                    f"force_refresh={force_refresh}, use_llm={use_llm}"
                )

                await emit_progress("all_ops", "processing", "Starting parallel operations")

                # Create wrapped operations with their own progress tracking
                async def run_extraction():
                    """Run full extraction with progress prefix."""

                    def extraction_progress(layer_key: str, status: str, message: str):
                        # Prefix layer keys to distinguish from research
                        if progress_callback:
                            progress_callback(f"extraction_{layer_key}", status, message)

                    return await self.extraction_service.execute(
                        job_id=job_id,
                        tier=tier,
                        use_llm=use_llm,
                        progress_callback=extraction_progress,
                        log_callback=log_callback,
                    )

                async def run_research():
                    """Run company research with progress prefix."""

                    def research_progress(layer_key: str, status: str, message: str):
                        # Prefix layer keys to distinguish from extraction
                        if progress_callback:
                            progress_callback(f"research_{layer_key}", status, message)

                    return await self.research_service.execute(
                        job_id=job_id,
                        tier=tier,
                        force_refresh=force_refresh,
                        progress_callback=research_progress,
                        log_callback=log_callback,
                    )

                # Run both operations in parallel with retry logic
                await emit_progress("parallel_exec", "processing", "Running extraction and research in parallel")

                extraction_task = asyncio.create_task(
                    self._run_with_retry(
                        "extraction",
                        run_extraction,
                        progress_callback,
                        self.MAX_RETRIES,
                    )
                )
                research_task = asyncio.create_task(
                    self._run_with_retry(
                        "research",
                        run_research,
                        progress_callback,
                        self.MAX_RETRIES,
                    )
                )

                # Wait for both to complete (return_exceptions=False since we handle errors in _run_with_retry)
                results = await asyncio.gather(extraction_task, research_task)

                extraction_result, extraction_error = results[0]
                research_result, research_error = results[1]

                # Aggregate results
                combined_data: Dict[str, Any] = {
                    "extraction_completed": extraction_result is not None and extraction_result.success,
                    "research_completed": research_result is not None and research_result.success,
                    "phase1_complete": False,  # Will set to True if both succeeded
                }

                # Aggregate layer status from both operations
                combined_layer_status: Dict[str, Any] = {}

                # Process extraction results
                if extraction_result and extraction_result.success:
                    combined_data["extraction"] = extraction_result.data
                    combined_data["fit_score"] = extraction_result.data.get("fit_score")
                    combined_data["fit_category"] = extraction_result.data.get("fit_category")
                    combined_data["pain_points_count"] = extraction_result.data.get("pain_points_count", 0)
                    combined_data["section_count"] = extraction_result.data.get("section_count", 0)
                    # Copy layer status with extraction prefix
                    for key, value in extraction_result.data.get("layer_status", {}).items():
                        combined_layer_status[f"extraction_{key}"] = value
                else:
                    combined_data["extraction_error"] = extraction_error

                # Process research results
                if research_result and research_result.success:
                    combined_data["research"] = research_result.data
                    combined_data["company_type"] = research_result.data.get("company_type")
                    combined_data["signals_count"] = research_result.data.get("signals_count", 0)
                    combined_data["primary_contacts_count"] = research_result.data.get("primary_contacts_count", 0)
                    combined_data["secondary_contacts_count"] = research_result.data.get("secondary_contacts_count", 0)
                    # Copy layer status with research prefix
                    for key, value in research_result.data.get("layer_status", {}).items():
                        combined_layer_status[f"research_{key}"] = value
                else:
                    combined_data["research_error"] = research_error

                combined_data["layer_status"] = combined_layer_status

                # Calculate combined cost
                total_cost = 0.0
                total_input_tokens = 0
                total_output_tokens = 0

                if extraction_result:
                    total_cost += extraction_result.cost_usd
                    total_input_tokens += extraction_result.input_tokens
                    total_output_tokens += extraction_result.output_tokens

                if research_result:
                    total_cost += research_result.cost_usd
                    total_input_tokens += research_result.input_tokens
                    total_output_tokens += research_result.output_tokens

                # Determine overall success
                # Success if at least one operation succeeded
                # Full success (phase1_complete) if both succeeded
                any_success = (
                    (extraction_result and extraction_result.success) or
                    (research_result and research_result.success)
                )

                both_success = (
                    (extraction_result and extraction_result.success) and
                    (research_result and research_result.success)
                )

                combined_data["phase1_complete"] = both_success

                # Build error message if partial failure
                errors: List[str] = []
                if extraction_error:
                    errors.append(f"Extraction: {extraction_error}")
                if research_error:
                    errors.append(f"Research: {research_error}")

                combined_error = "; ".join(errors) if errors else None

                # Log completion status
                if both_success:
                    await emit_progress("all_ops", "success", "All operations completed successfully")
                    logger.info(
                        f"[{run_id[:16]}] All-ops complete: "
                        f"fit={combined_data.get('fit_score')}, "
                        f"signals={combined_data.get('signals_count', 0)}, "
                        f"contacts={combined_data.get('primary_contacts_count', 0)}"
                    )
                elif any_success:
                    await emit_progress("all_ops", "warning", "Partial success - some operations failed")
                    logger.warning(
                        f"[{run_id[:16]}] All-ops partial success: "
                        f"extraction={combined_data['extraction_completed']}, "
                        f"research={combined_data['research_completed']}"
                    )
                else:
                    await emit_progress("all_ops", "failed", "All operations failed")
                    logger.error(f"[{run_id[:16]}] All-ops failed: {combined_error}")

                # Create result
                if any_success:
                    result = self.create_success_result(
                        run_id=run_id,
                        data=combined_data,
                        cost_usd=total_cost,
                        duration_ms=timer.duration_ms,
                        input_tokens=total_input_tokens,
                        output_tokens=total_output_tokens,
                        model_used=model,
                    )
                    # Add partial error if applicable
                    if combined_error:
                        result.error = combined_error
                else:
                    result = self.create_error_result(
                        run_id=run_id,
                        error=combined_error or "All operations failed",
                        duration_ms=timer.duration_ms,
                        cost_usd=total_cost,
                        input_tokens=total_input_tokens,
                        output_tokens=total_output_tokens,
                    )

                # Persist operation run
                self.persist_run(result, job_id, tier)

                return result

            except Exception as e:
                logger.exception(f"[{run_id[:16]}] all-ops failed with exception: {e}")
                error_result = self.create_error_result(
                    run_id=run_id,
                    error=str(e),
                    duration_ms=timer.duration_ms,
                )
                self.persist_run(error_result, job_id, tier)
                return error_result

    def close(self):
        """Clean up resources from sub-services."""
        if self._research_service:
            self._research_service.close()
            self._research_service = None


# Convenience function
async def all_ops(
    job_id: str,
    tier: ModelTier = ModelTier.BALANCED,
    force_refresh: bool = False,
    use_llm: bool = True,
) -> OperationResult:
    """
    Convenience function for running all Phase 1 operations.

    Args:
        job_id: MongoDB ObjectId of the job
        tier: Model tier (default: BALANCED)
        force_refresh: Force refresh for company research
        use_llm: Whether to use LLM (default: True)

    Returns:
        OperationResult with combined extraction and research data
    """
    service = AllOpsService()
    try:
        return await service.execute(
            job_id=job_id,
            tier=tier,
            force_refresh=force_refresh,
            use_llm=use_llm,
        )
    finally:
        service.close()
