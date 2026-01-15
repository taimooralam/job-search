"""
Batch Pipeline Service - Complete Move-to-Batch Orchestrator

Orchestrates the complete batch processing pipeline when a job is moved to batch:
1. Full Extraction (JD processing, pain points, fit scoring) + Annotations + Persona
2. Company Research (Layer 3) + Role Research (Layer 3.5) + People Mapping (Layer 5)
3. CV Generation (6-phase orchestrator)
4. Upload CV to Google Drive
5. Upload Dossier to Google Drive

Each step emits progress to Redis for frontend polling (Redis transparency).
On failure, continues to next step (except extraction which is required foundation).

Usage:
    service = BatchPipelineService()
    result = await service.execute(job_id="...", tier=ModelTier.QUALITY)
"""

import asyncio
import logging
import traceback
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from bson import ObjectId

from src.common.model_tiers import ModelTier
from src.common.repositories import get_job_repository, JobRepositoryInterface
from src.services.operation_base import OperationResult, OperationService

logger = logging.getLogger(__name__)


class BatchPipelineService(OperationService):
    """
    Orchestrates complete batch processing pipeline.

    Steps:
    1-3. Full Extraction + Annotations + Persona (FullExtractionService)
    4.   Company Research + Role Research + People Mapping (CompanyResearchService)
    5.   CV Generation (CVGenerationService)
    6.   Upload CV to Google Drive
    7.   Upload Dossier to Google Drive
    """

    operation_name = "batch-pipeline"

    def __init__(self, repository: Optional[JobRepositoryInterface] = None):
        """Initialize the service with optional repository."""
        self._repository = repository

    def _get_repository(self) -> JobRepositoryInterface:
        """Get the job repository instance."""
        if self._repository is not None:
            return self._repository
        return get_job_repository()

    def _get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Fetch job from MongoDB by ID."""
        try:
            object_id = ObjectId(job_id)
        except Exception as e:
            raise ValueError(f"Invalid job ID format: {job_id}") from e

        repo = self._get_repository()
        return repo.find_one({"_id": object_id})

    async def _call_upload_endpoint(
        self,
        job_id: str,
        endpoint_path: str,
        step_name: str,
    ) -> Dict[str, Any]:
        """
        Call an existing upload endpoint via HTTP.

        Reuses the existing upload endpoints in runner_service/routes/operations.py
        without duplicating code.

        Args:
            job_id: MongoDB ObjectId of the job
            endpoint_path: Path after /api/jobs/{job_id}/ (e.g., "cv/upload-drive")
            step_name: Step name for logging

        Returns:
            Dict with: success, error, gdrive_file_id, etc.
        """
        import os
        import httpx

        # Get runner service URL (use localhost since we're in the same service)
        runner_url = os.getenv("RUNNER_URL", "http://localhost:8000")
        runner_secret = os.getenv("RUNNER_API_SECRET", "")

        url = f"{runner_url}/api/jobs/{job_id}/{endpoint_path}"
        headers = {"Authorization": f"Bearer {runner_secret}"}

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(url, headers=headers)

                if response.status_code in (200, 201):
                    result = response.json()
                    return {
                        "success": result.get("success", True),
                        "error": result.get("error"),
                        "gdrive_file_id": result.get("gdrive_file_id"),
                        "gdrive_folder_id": result.get("gdrive_folder_id"),
                        "uploaded_at": result.get("uploaded_at"),
                    }
                else:
                    try:
                        error_detail = response.json().get("detail", response.text)
                    except Exception:
                        error_detail = response.text
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {error_detail}",
                    }

        except httpx.TimeoutException:
            return {"success": False, "error": f"{step_name} timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def execute(
        self,
        job_id: str,
        tier: ModelTier = ModelTier.QUALITY,
        progress_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
        stop_on_failure: bool = False,
        **kwargs,
    ) -> OperationResult:
        """
        Execute complete batch pipeline for a job.

        Args:
            job_id: MongoDB ObjectId of the job
            tier: Model tier (default QUALITY for batch processing)
            progress_callback: Optional callback(layer_key, status, message) for Redis updates
            log_callback: Optional callback for JSON log streaming
            stop_on_failure: If True, stop pipeline on any failure (default: continue)

        Returns:
            OperationResult with success status and step_results dict
        """
        start_time = datetime.utcnow()
        run_id = f"op_{self.operation_name}_{job_id[:8]}_{start_time.strftime('%H%M%S')}"

        step_results: Dict[str, Dict[str, Any]] = {}
        total_cost = 0.0
        total_input_tokens = 0
        total_output_tokens = 0

        def _emit_progress(layer: str, status: str, message: str):
            """Emit progress to callback if provided."""
            logger.info(f"[{layer}] {status}: {message}")
            if progress_callback:
                try:
                    progress_callback(layer, status, message)
                except Exception as e:
                    logger.warning(f"Progress callback error: {e}")

        def _emit_log(log_entry: Dict[str, Any]):
            """Emit log entry to callback if provided."""
            if log_callback:
                try:
                    log_callback(log_entry)
                except Exception as e:
                    logger.warning(f"Log callback error: {e}")

        _emit_log({
            "level": "info",
            "message": f"Starting batch pipeline for job {job_id}",
            "step": "init",
            "tier": tier.value,
        })

        # =====================================================================
        # STEP 1-3: Full Extraction + Annotations + Persona
        # =====================================================================
        _emit_progress("extraction", "running", "Starting JD extraction with annotations and persona...")

        try:
            from src.services.full_extraction_service import FullExtractionService

            extraction_service = FullExtractionService(repository=self._repository)
            extraction_result = await extraction_service.execute(
                job_id=job_id,
                tier=tier,
                use_llm=True,
                progress_callback=progress_callback,
                log_callback=log_callback,
                auto_annotate=True,
                auto_persona=True,
                parent_run_id=run_id,  # Pass parent's run_id for unified logging
            )

            step_results["extraction"] = {
                "success": extraction_result.success,
                "error": extraction_result.error,
                "duration_ms": extraction_result.duration_ms,
            }
            total_cost += extraction_result.cost_usd
            total_input_tokens += extraction_result.input_tokens
            total_output_tokens += extraction_result.output_tokens

            if extraction_result.success:
                _emit_progress("extraction", "completed", "Extraction, annotations, and persona completed")
            else:
                _emit_progress("extraction", "failed", f"Extraction failed: {extraction_result.error}")
                # Extraction is required - if it fails, stop the pipeline
                return OperationResult(
                    success=False,
                    run_id=run_id,
                    operation=self.operation_name,
                    data={"step_results": step_results, "stopped_at": "extraction"},
                    cost_usd=total_cost,
                    duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    error="Extraction failed - cannot continue pipeline",
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    model_used=tier.value,
                )

        except Exception as e:
            error_msg = f"Extraction exception: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            step_results["extraction"] = {"success": False, "error": error_msg}
            _emit_progress("extraction", "failed", error_msg)
            return OperationResult(
                success=False,
                run_id=run_id,
                operation=self.operation_name,
                data={"step_results": step_results, "stopped_at": "extraction"},
                cost_usd=total_cost,
                duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                error=error_msg,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                model_used=tier.value,
            )

        # =====================================================================
        # STEP 4: Company Research + Role Research + People Mapping
        # =====================================================================
        _emit_progress("company_research", "running", "Starting company and role research...")

        try:
            from src.services.company_research_service import CompanyResearchService

            research_service = CompanyResearchService(repository=self._repository)
            research_result = await research_service.execute(
                job_id=job_id,
                tier=tier,
                force_refresh=False,
                progress_callback=progress_callback,
                log_callback=log_callback,
                parent_run_id=run_id,  # Pass parent's run_id for unified logging
            )

            step_results["company_research"] = {
                "success": research_result.success,
                "error": research_result.error,
                "duration_ms": research_result.duration_ms,
            }
            total_cost += research_result.cost_usd
            total_input_tokens += research_result.input_tokens
            total_output_tokens += research_result.output_tokens

            if research_result.success:
                _emit_progress("company_research", "completed", "Company and role research completed")
            else:
                _emit_progress("company_research", "failed", f"Research failed: {research_result.error}")
                if stop_on_failure:
                    return self._build_partial_result(
                        run_id, start_time, step_results, total_cost,
                        total_input_tokens, total_output_tokens, tier,
                        stopped_at="company_research"
                    )

        except Exception as e:
            error_msg = f"Company research exception: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            step_results["company_research"] = {"success": False, "error": error_msg}
            _emit_progress("company_research", "failed", error_msg)
            if stop_on_failure:
                return self._build_partial_result(
                    run_id, start_time, step_results, total_cost,
                    total_input_tokens, total_output_tokens, tier,
                    stopped_at="company_research"
                )

        # =====================================================================
        # STEP 5: CV Generation
        # =====================================================================
        _emit_progress("cv_generation", "running", "Starting CV generation...")

        try:
            from src.services.cv_generation_service import CVGenerationService

            cv_service = CVGenerationService(repository=self._repository)
            cv_result = await cv_service.execute(
                job_id=job_id,
                tier=tier,
                use_annotations=True,
                progress_callback=progress_callback,
                parent_run_id=run_id,  # Pass parent's run_id for unified logging
            )

            step_results["cv_generation"] = {
                "success": cv_result.success,
                "error": cv_result.error,
                "duration_ms": cv_result.duration_ms,
            }
            total_cost += cv_result.cost_usd
            total_input_tokens += cv_result.input_tokens
            total_output_tokens += cv_result.output_tokens

            if cv_result.success:
                _emit_progress("cv_generation", "completed", "CV generated successfully")
            else:
                _emit_progress("cv_generation", "failed", f"CV generation failed: {cv_result.error}")
                if stop_on_failure:
                    return self._build_partial_result(
                        run_id, start_time, step_results, total_cost,
                        total_input_tokens, total_output_tokens, tier,
                        stopped_at="cv_generation"
                    )

        except Exception as e:
            error_msg = f"CV generation exception: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            step_results["cv_generation"] = {"success": False, "error": error_msg}
            _emit_progress("cv_generation", "failed", error_msg)
            if stop_on_failure:
                return self._build_partial_result(
                    run_id, start_time, step_results, total_cost,
                    total_input_tokens, total_output_tokens, tier,
                    stopped_at="cv_generation"
                )

        # =====================================================================
        # STEP 6: Upload CV to Google Drive
        # Uses direct function call for unified logging (no HTTP overhead)
        # =====================================================================
        _emit_progress("cv_upload", "running", "Uploading CV to Google Drive...")

        try:
            from src.services.gdrive_upload_service import upload_cv_to_gdrive

            # Create string log callback wrapper for upload service
            def cv_upload_log(message: str) -> None:
                if log_callback:
                    log_callback(message)

            cv_upload_result = await upload_cv_to_gdrive(
                job_id=job_id,
                log_callback=cv_upload_log,
            )

            step_results["cv_upload"] = cv_upload_result

            if cv_upload_result["success"]:
                _emit_progress("cv_upload", "completed", "CV uploaded to Google Drive")
            else:
                _emit_progress("cv_upload", "failed", f"CV upload failed: {cv_upload_result.get('error')}")
                if stop_on_failure:
                    return self._build_partial_result(
                        run_id, start_time, step_results, total_cost,
                        total_input_tokens, total_output_tokens, tier,
                        stopped_at="cv_upload"
                    )

        except Exception as e:
            error_msg = f"CV upload exception: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            step_results["cv_upload"] = {"success": False, "error": error_msg}
            _emit_progress("cv_upload", "failed", error_msg)
            if stop_on_failure:
                return self._build_partial_result(
                    run_id, start_time, step_results, total_cost,
                    total_input_tokens, total_output_tokens, tier,
                    stopped_at="cv_upload"
                )

        # =====================================================================
        # STEP 7: Upload Dossier to Google Drive
        # Uses direct function call for unified logging (no HTTP overhead)
        # =====================================================================
        _emit_progress("dossier_upload", "running", "Uploading dossier to Google Drive...")

        try:
            from src.services.gdrive_upload_service import upload_dossier_to_gdrive

            # Create string log callback wrapper for upload service
            def dossier_upload_log(message: str) -> None:
                if log_callback:
                    log_callback(message)

            dossier_upload_result = await upload_dossier_to_gdrive(
                job_id=job_id,
                log_callback=dossier_upload_log,
            )

            step_results["dossier_upload"] = dossier_upload_result

            if dossier_upload_result["success"]:
                _emit_progress("dossier_upload", "completed", "Dossier uploaded to Google Drive")
            else:
                _emit_progress("dossier_upload", "failed", f"Dossier upload failed: {dossier_upload_result.get('error')}")

        except Exception as e:
            error_msg = f"Dossier upload exception: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            step_results["dossier_upload"] = {"success": False, "error": error_msg}
            _emit_progress("dossier_upload", "failed", error_msg)

        # =====================================================================
        # BUILD FINAL RESULT
        # =====================================================================
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Count successes and failures
        steps_completed = sum(1 for r in step_results.values() if r.get("success", False))
        steps_failed = sum(1 for r in step_results.values() if not r.get("success", True))
        all_success = all(r.get("success", False) for r in step_results.values())

        _emit_log({
            "level": "info" if all_success else "warning",
            "message": f"Batch pipeline completed: {steps_completed}/7 steps succeeded",
            "step": "complete",
            "steps_completed": steps_completed,
            "steps_failed": steps_failed,
        })

        return OperationResult(
            success=all_success,
            run_id=run_id,
            operation=self.operation_name,
            data={
                "step_results": step_results,
                "steps_completed": steps_completed,
                "steps_failed": steps_failed,
                "completed_at": end_time.isoformat() + "Z",
            },
            cost_usd=total_cost,
            duration_ms=duration_ms,
            error=None if all_success else f"{steps_failed} step(s) failed",
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            model_used=tier.value,
        )

    def _build_partial_result(
        self,
        run_id: str,
        start_time: datetime,
        step_results: Dict[str, Dict[str, Any]],
        total_cost: float,
        total_input_tokens: int,
        total_output_tokens: int,
        tier: ModelTier,
        stopped_at: str,
    ) -> OperationResult:
        """Build a partial result when pipeline is stopped due to failure."""
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        steps_completed = sum(1 for r in step_results.values() if r.get("success", False))
        steps_failed = sum(1 for r in step_results.values() if not r.get("success", True))

        return OperationResult(
            success=False,
            run_id=run_id,
            operation=self.operation_name,
            data={
                "step_results": step_results,
                "stopped_at": stopped_at,
                "steps_completed": steps_completed,
                "steps_failed": steps_failed,
            },
            cost_usd=total_cost,
            duration_ms=duration_ms,
            error=f"Pipeline stopped at {stopped_at}",
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            model_used=tier.value,
        )
