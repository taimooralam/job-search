"""
CV Generation Service for Button-Triggered Pipeline Operations.

Wraps the Layer 6 V2 CV generation pipeline for on-demand execution
via the operations API. Handles:
- Job fetching from MongoDB
- Candidate profile loading
- Tier-based model selection
- CV generation with annotations
- Result persistence

Usage:
    service = CVGenerationService()
    result = await service.execute(job_id="123", tier=ModelTier.QUALITY)
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId
from pymongo import MongoClient

from src.common.model_tiers import ModelTier, get_model_for_operation
from src.services.operation_base import OperationResult, OperationService

logger = logging.getLogger(__name__)


class CVGenerationService(OperationService):
    """
    Service for generating tailored CVs via the operations API.

    Wraps the Layer 6 V2 orchestrator (CVGeneratorV2) for button-triggered
    CV generation with tier-based model selection and cost tracking.

    The service:
    1. Fetches job data from MongoDB (extracted_jd, annotations, etc.)
    2. Loads candidate profile from master-cv
    3. Builds JobState for the orchestrator
    4. Calls CVGeneratorV2 with tier-appropriate model
    5. Persists cv_text and cv_editor_state to MongoDB
    6. Returns OperationResult with generated CV

    Model tiers:
    - FAST: gpt-4o-mini (cheap, quick)
    - BALANCED: gpt-4o (good quality/cost)
    - QUALITY: claude-sonnet (best quality)
    """

    operation_name = "generate-cv"

    def __init__(self, db_client: Optional[MongoClient] = None):
        """
        Initialize the CV generation service.

        Args:
            db_client: Optional MongoDB client. If None, creates one from env.
        """
        self._db_client = db_client

    def _get_db(self) -> MongoClient:
        """Get or create MongoDB client."""
        if self._db_client is not None:
            return self._db_client

        mongo_uri = (
            os.getenv("MONGODB_URI")
            or os.getenv("MONGO_URI")
            or "mongodb://localhost:27017"
        )
        return MongoClient(mongo_uri)

    def _get_db_name(self) -> str:
        """Get database name from environment."""
        return os.getenv("MONGO_DB_NAME", "jobs")

    async def execute(
        self,
        job_id: str,
        tier: ModelTier,
        use_annotations: bool = True,
        progress_callback: callable = None,
        **kwargs,
    ) -> OperationResult:
        """
        Generate a tailored CV for a job.

        Args:
            job_id: MongoDB ObjectId of the job
            tier: Model tier (FAST, BALANCED, QUALITY)
            use_annotations: Whether to use JD annotations if available
            progress_callback: Optional callback for real-time progress updates.
                              Signature: callback(layer_key: str, status: str, message: str)
            **kwargs: Additional arguments (ignored)

        Returns:
            OperationResult with cv_text and cv_editor_state in data
        """
        run_id = self.create_run_id()
        model = self.get_model(tier)

        # Helper to call progress callback if provided (async to yield to event loop)
        async def emit_progress(layer_key: str, status: str, message: str):
            if progress_callback:
                try:
                    progress_callback(layer_key, status, message)
                    await asyncio.sleep(0)  # CRITICAL: Yield to event loop for SSE delivery
                except Exception as e:
                    logger.warning(f"Progress callback failed: {e}")

        logger.info(
            f"[{run_id[:16]}] Starting CV generation for job {job_id}, "
            f"tier={tier.value}, model={model}"
        )

        with self.timed_execution() as timer:
            # Track per-layer status for detailed logging
            layer_status = {}

            try:
                # Step 1: Fetch job from MongoDB
                await emit_progress("fetch_job", "processing", "Loading job data")
                logger.info(f"[{run_id[:16]}] Fetching job from database")
                job = self._fetch_job(job_id)
                if job is None:
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
                await emit_progress("fetch_job", "success", f"Found job: {job.get('title', 'Unknown')}")

                # Step 2: Validate job has required data
                await emit_progress("validate", "processing", "Validating job data")
                logger.info(f"[{run_id[:16]}] Validating job data")
                validation_error = self._validate_job_data(job)
                if validation_error:
                    layer_status["validate"] = {
                        "status": "failed",
                        "message": validation_error
                    }
                    await emit_progress("validate", "failed", validation_error)
                    return self.create_error_result(
                        run_id=run_id,
                        error=validation_error,
                        duration_ms=timer.duration_ms,
                    )
                layer_status["validate"] = {
                    "status": "success",
                    "message": "Job data validated"
                }
                await emit_progress("validate", "success", "Job data validated")

                # Step 3: Build state for CV generator
                await emit_progress("build_state", "processing", "Preparing CV generation context")
                logger.info(f"[{run_id[:16]}] Building CV generation state")
                state = self._build_state(job, use_annotations)
                state_msg = f"State built with {'annotations' if state.get('jd_annotations') else 'no annotations'}"
                layer_status["build_state"] = {
                    "status": "success",
                    "has_annotations": bool(state.get("jd_annotations")),
                    "has_stars": bool(state.get("all_stars")),
                    "message": state_msg
                }
                await emit_progress("build_state", "success", state_msg)

                # Step 4: Generate CV
                await emit_progress("cv_generator", "processing", f"Generating CV with {model}")
                logger.info(f"[{run_id[:16]}] Generating CV with model {model}")
                cv_result = self._generate_cv(state, model)

                if cv_result.get("errors"):
                    # Include traceback if available for debugging
                    traceback_info = cv_result.get("traceback", "")
                    if traceback_info:
                        logger.error(f"[{run_id[:16]}] CV generation traceback:\n{traceback_info}")
                    error_msg = f"Generation failed: {cv_result['errors'][0]}"
                    layer_status["cv_generator"] = {
                        "status": "failed",
                        "errors": cv_result["errors"],
                        "message": error_msg,
                        "traceback": traceback_info,
                    }
                    await emit_progress("cv_generator", "failed", error_msg)
                    return self.create_error_result(
                        run_id=run_id,
                        error="; ".join(cv_result["errors"]),
                        duration_ms=timer.duration_ms,
                    )

                # Step 5: Build cv_editor_state from generated CV
                cv_text = cv_result.get("cv_text", "")
                word_count = len(cv_text.split()) if cv_text else 0
                cv_editor_state = self._build_cv_editor_state(cv_text)
                cv_success_msg = f"Generated {word_count} word CV"
                layer_status["cv_generator"] = {
                    "status": "success",
                    "word_count": word_count,
                    "has_reasoning": bool(cv_result.get("cv_reasoning")),
                    "message": cv_success_msg
                }
                await emit_progress("cv_generator", "success", cv_success_msg)
                logger.info(f"[{run_id[:16]}] CV generated: {word_count} words")

                # Step 6: Persist to MongoDB
                await emit_progress("persist", "processing", "Saving CV to database")
                logger.info(f"[{run_id[:16]}] Persisting CV to database")
                persisted = self._persist_cv_result(job_id, cv_text, cv_editor_state, cv_result)
                persist_msg = "Saved to database" if persisted else "Persistence failed"
                layer_status["persist"] = {
                    "status": "success" if persisted else "warning",
                    "message": persist_msg
                }
                await emit_progress("persist", "success" if persisted else "warning", persist_msg)

                # Step 7: Calculate cost estimate
                # Estimate tokens based on typical CV generation
                input_tokens = 5000  # ~5K input (JD + master CV context)
                output_tokens = 2500  # ~2.5K output (CV text)
                cost = self.estimate_cost(tier, input_tokens, output_tokens)

                logger.info(
                    f"[{run_id[:16]}] CV generation complete. "
                    f"Duration: {timer.duration_ms}ms"
                )

                return self.create_success_result(
                    run_id=run_id,
                    data={
                        "cv_text": cv_text,
                        "cv_editor_state": cv_editor_state,
                        "cv_path": cv_result.get("cv_path"),
                        "cv_reasoning": cv_result.get("cv_reasoning"),
                        "grade_result": cv_result.get("cv_grade_result"),
                        "word_count": word_count,
                        "layer_status": layer_status,
                    },
                    cost_usd=cost,
                    duration_ms=timer.duration_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model_used=model,
                )

            except Exception as e:
                logger.exception(f"[{run_id[:16]}] CV generation failed: {e}")
                return self.create_error_result(
                    run_id=run_id,
                    error=str(e),
                    duration_ms=timer.duration_ms,
                )

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
        except Exception as e:
            logger.error(f"Invalid job ID format: {job_id} - {e}")
            return None

        client = self._get_db()
        try:
            db = client[self._get_db_name()]
            return db["level-2"].find_one({"_id": object_id})
        finally:
            if self._db_client is None:
                client.close()

    def _validate_job_data(self, job: Dict[str, Any]) -> Optional[str]:
        """
        Validate job has required data for CV generation.

        Args:
            job: Job document from MongoDB

        Returns:
            Error message if validation fails, None if OK
        """
        # Check for extracted JD (structured job description)
        extracted_jd = job.get("extracted_jd")
        if not extracted_jd:
            # Fall back to checking for raw JD text
            jd_text = job.get("jd_text") or job.get("description") or job.get("job_description")
            if not jd_text:
                return "Job missing job description (extracted_jd or jd_text required)"

        return None

    def _build_state(
        self,
        job: Dict[str, Any],
        use_annotations: bool,
    ) -> Dict[str, Any]:
        """
        Build JobState dictionary for the CV generator.

        Args:
            job: Job document from MongoDB
            use_annotations: Whether to include annotations

        Returns:
            JobState-compatible dictionary
        """
        # Get extracted_jd or build from raw text
        extracted_jd = job.get("extracted_jd", {})

        # If extracted_jd is minimal, populate basic fields from job
        if not extracted_jd.get("title"):
            extracted_jd["title"] = job.get("title", "")
        if not extracted_jd.get("company"):
            extracted_jd["company"] = job.get("company", "")

        state = {
            "job_id": str(job["_id"]),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "job_description": (
                job.get("jd_text")
                or job.get("description")
                or job.get("job_description", "")
            ),
            "extracted_jd": extracted_jd,
            "run_id": f"cv_gen_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "fit_score": job.get("fit_score"),
            "location": job.get("location", ""),
        }

        # Include annotations if requested and available
        if use_annotations and job.get("jd_annotations"):
            state["jd_annotations"] = job["jd_annotations"]
            logger.info("Including JD annotations in CV generation")

        # Include all_stars if available for achievement selection
        if job.get("all_stars"):
            state["all_stars"] = job["all_stars"]

        return state

    def _generate_cv(
        self,
        state: Dict[str, Any],
        model: str,
    ) -> Dict[str, Any]:
        """
        Run the CV generation pipeline.

        Args:
            state: JobState dictionary
            model: Model name to use

        Returns:
            Dictionary with cv_text, cv_path, cv_reasoning, etc.
        """
        from src.layer6_v2.orchestrator import CVGeneratorV2

        generator = CVGeneratorV2(model=model)
        return generator.generate(state)

    def _build_cv_editor_state(self, cv_text: str) -> Dict[str, Any]:
        """
        Build cv_editor_state from generated CV text.

        Converts markdown CV to TipTap-compatible editor state.

        Args:
            cv_text: Generated CV markdown text

        Returns:
            Dictionary with editor state (prosemirror format)
        """
        if not cv_text:
            return {"type": "doc", "content": []}

        # Import the converter if available
        try:
            from frontend.cv_editor.converters import markdown_to_prosemirror
            return markdown_to_prosemirror(cv_text)
        except ImportError:
            # Fallback: simple text-based state
            return {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": cv_text}],
                    }
                ],
            }

    def _persist_cv_result(
        self,
        job_id: str,
        cv_text: str,
        cv_editor_state: Dict[str, Any],
        cv_result: Dict[str, Any],
    ) -> bool:
        """
        Persist CV generation results to MongoDB.

        Args:
            job_id: Job ID
            cv_text: Generated CV markdown
            cv_editor_state: TipTap editor state
            cv_result: Full result from generator

        Returns:
            True if persisted successfully
        """
        try:
            object_id = ObjectId(job_id)
        except Exception:
            logger.error(f"Invalid job ID for persistence: {job_id}")
            return False

        client = self._get_db()
        try:
            db = client[self._get_db_name()]
            result = db["level-2"].update_one(
                {"_id": object_id},
                {
                    "$set": {
                        "cv_text": cv_text,
                        "cv_editor_state": cv_editor_state,
                        "cv_path": cv_result.get("cv_path"),
                        "cv_reasoning": cv_result.get("cv_reasoning"),
                        "cv_generated_at": datetime.utcnow(),
                        "updatedAt": datetime.utcnow(),
                    }
                },
            )
            if result.modified_count > 0:
                logger.info(f"Persisted CV result for job {job_id}")
                return True
            else:
                logger.warning(f"No document updated for job {job_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to persist CV result: {e}")
            return False
        finally:
            if self._db_client is None:
                client.close()
