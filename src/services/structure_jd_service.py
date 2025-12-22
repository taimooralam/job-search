"""
Structure JD Service - Phase 4 Implementation

Service for structuring/parsing job descriptions into annotatable HTML sections.
Wraps the existing JD processing logic from layer1_4 with consistent
operation interface for button-triggered execution.

Usage:
    service = StructureJDService()
    result = await service.execute(job_id="...", tier=ModelTier.BALANCED, use_llm=True)
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from bson import ObjectId
from pymongo import MongoClient

from src.common.model_tiers import ModelTier, get_model_for_operation
from src.common.structured_logger import StructuredLogger
from src.common.token_tracker import TokenTracker, get_global_tracker
from src.layer1_4 import process_jd, process_jd_sync, processed_jd_to_dict, LLMMetadata
from src.services.operation_base import OperationResult, OperationService

logger = logging.getLogger(__name__)


class StructureJDService(OperationService):
    """
    Service for structuring job descriptions.

    Parses raw JD text into structured HTML sections for annotation.
    Supports both LLM-based (more accurate) and rule-based (faster) processing.
    """

    operation_name = "structure-jd"

    def __init__(self, db_client: Optional[MongoClient] = None):
        """
        Initialize the service.

        Args:
            db_client: Optional MongoDB client. If not provided, creates one.
        """
        self._db_client = db_client
        self._tracker: Optional[TokenTracker] = None

    def _get_db_client(self) -> MongoClient:
        """Get or create MongoDB client."""
        if self._db_client is not None:
            return self._db_client

        mongo_uri = (
            os.getenv("MONGODB_URI")
            or os.getenv("MONGO_URI")
            or "mongodb://localhost:27017"
        )
        return MongoClient(mongo_uri)

    def _get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch job from MongoDB by ID.

        Args:
            job_id: MongoDB ObjectId as string

        Returns:
            Job document or None if not found

        Raises:
            ValueError: If job_id is invalid
        """
        try:
            object_id = ObjectId(job_id)
        except Exception as e:
            raise ValueError(f"Invalid job ID format: {job_id}") from e

        client = self._get_db_client()
        try:
            db = client[os.getenv("MONGO_DB_NAME", "jobs")]
            return db["level-2"].find_one({"_id": object_id})
        finally:
            if self._db_client is None:
                client.close()

    def _get_jd_text(self, job: Dict[str, Any]) -> str:
        """
        Extract JD text from job document.

        Checks multiple possible field names for compatibility.

        Args:
            job: Job document from MongoDB

        Returns:
            JD text string

        Raises:
            ValueError: If no JD text found
        """
        jd_text = (
            job.get("job_description")
            or job.get("jobDescription")
            or job.get("description")
            or job.get("jd_text")
            or ""
        )

        if not jd_text.strip():
            raise ValueError("No job description text found in job document")

        return jd_text

    def _persist_result(
        self,
        job_id: str,
        processed_result: Dict[str, Any],
    ) -> bool:
        """
        Persist structured JD result to MongoDB.

        Updates jd_annotations field with processed HTML and increments version.

        Args:
            job_id: MongoDB ObjectId as string
            processed_result: Result from processed_jd_to_dict()

        Returns:
            True if update succeeded
        """
        try:
            object_id = ObjectId(job_id)
        except Exception:
            logger.error(f"Invalid job ID for persistence: {job_id}")
            return False

        client = self._get_db_client()
        try:
            db = client[os.getenv("MONGO_DB_NAME", "jobs")]
            collection = db["level-2"]

            # Get existing annotations to preserve them
            job = collection.find_one({"_id": object_id}, {"jd_annotations": 1})
            existing_annotations = job.get("jd_annotations", {}) if job else {}

            # Update with new processed JD
            existing_annotations["processed_jd_html"] = processed_result.get("html")
            existing_annotations["processed_jd_sections"] = processed_result.get(
                "sections"
            )
            existing_annotations["content_hash"] = processed_result.get("content_hash")
            existing_annotations["annotation_version"] = (
                existing_annotations.get("annotation_version", 0) + 1
            )

            result = collection.update_one(
                {"_id": object_id},
                {
                    "$set": {
                        "jd_annotations": existing_annotations,
                        "extracted_jd": processed_result,  # Also store full result
                        "updatedAt": datetime.utcnow(),
                    }
                },
            )

            return result.modified_count > 0 or result.matched_count > 0

        except Exception as e:
            logger.error(f"Failed to persist structured JD: {e}")
            return False
        finally:
            if self._db_client is None:
                client.close()

    async def execute(
        self,
        job_id: str,
        tier: ModelTier,
        use_llm: bool = True,
        progress_callback: Optional[Callable] = None,
        log_callback: Optional[Callable] = None,
        **kwargs,
    ) -> OperationResult:
        """
        Execute JD structuring operation.

        Args:
            job_id: MongoDB ObjectId of the job to process
            tier: Model tier for quality/cost selection
            use_llm: Whether to use LLM for intelligent structuring (default True)
            progress_callback: Optional callback for progress updates (layer_key, status, message)
            log_callback: Optional callback for log messages (JSON string)
            **kwargs: Additional arguments (ignored)

        Returns:
            OperationResult with structured JD data, cost, and status
        """
        run_id = self.create_run_id()
        logger.info(f"[{run_id[:16]}] Starting structure-jd for job {job_id}")

        # Progress callback helper for SSE streaming
        async def emit_progress(layer_key: str, status: str, message: str):
            if progress_callback:
                try:
                    progress_callback(layer_key, status, message)
                    await asyncio.sleep(0)  # Yield to event loop for SSE
                except Exception as e:
                    logger.warning(f"Progress callback failed: {e}")

        # Log callback helper for backend visibility
        def emit_log(message: str, **log_kwargs):
            if log_callback:
                try:
                    log_callback(json.dumps({"message": message, **log_kwargs}))
                except Exception:
                    pass

        # Create structured logger for frontend-visible LLM events
        struct_logger = StructuredLogger(job_id=job_id)

        with self.timed_execution() as timer:
            # Track per-layer status for detailed logging
            layer_status = {}

            try:
                # 1. Fetch job
                await emit_progress("fetch_job", "processing", "Loading job data")
                logger.info(f"[{run_id[:16]}] Fetching job from database")
                job = self._get_job(job_id)
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
                job_title = job.get('title', 'Unknown')
                layer_status["fetch_job"] = {
                    "status": "success",
                    "message": f"Found job: {job_title}"
                }
                await emit_progress("fetch_job", "success", f"Found job: {job_title}")

                # 2. Extract JD text
                await emit_progress("extract_text", "processing", "Extracting JD text")
                logger.info(f"[{run_id[:16]}] Extracting JD text")
                try:
                    jd_text = self._get_jd_text(job)
                    layer_status["extract_text"] = {
                        "status": "success",
                        "length": len(jd_text),
                        "message": f"Extracted {len(jd_text)} characters"
                    }
                    await emit_progress("extract_text", "success", f"JD text extracted: {len(jd_text)} chars")
                    emit_log(f"JD text extracted: {len(jd_text)} chars")
                except ValueError as e:
                    layer_status["extract_text"] = {
                        "status": "failed",
                        "message": str(e)
                    }
                    await emit_progress("extract_text", "failed", str(e))
                    return self.create_error_result(
                        run_id=run_id,
                        error=str(e),
                        duration_ms=timer.duration_ms,
                    )

                # 3. Get model for tier
                model = self.get_model(tier)
                logger.info(
                    f"[{run_id[:16]}] Using tier={tier.value}, model={model}, "
                    f"use_llm={use_llm}, jd_length={len(jd_text)}"
                )

                # 4. Process JD - now returns tuple (processed, llm_metadata)
                await emit_progress("jd_processor", "processing", f"Parsing JD with {'LLM' if use_llm else 'rules'}")
                emit_log(f"Processing JD with {'LLM' if use_llm else 'rule-based'}, model={model}")
                logger.info(f"[{run_id[:16]}] Processing JD with {'LLM' if use_llm else 'rules'}")
                llm_metadata: LLMMetadata
                if use_llm:
                    processed, llm_metadata = await process_jd(
                        jd_text,
                        use_llm=True,
                        model=model,
                        job_id=job_id,
                        struct_logger=struct_logger,
                    )
                else:
                    processed, llm_metadata = process_jd_sync(jd_text, use_llm=False)

                # 5. Emit structured LLM event for frontend visibility
                # Note: If struct_logger was passed to process_jd, events are already emitted
                # by UnifiedLLM. But if rule-based fallback happened, we emit manually here.
                if llm_metadata.backend == "rule_based":
                    # Rule-based fallback - emit event for visibility
                    struct_logger.emit(
                        event="llm_call_complete",
                        step_name="jd_structure_parsing",
                        backend=llm_metadata.backend,
                        model=llm_metadata.model,
                        tier=llm_metadata.tier,
                        duration_ms=llm_metadata.duration_ms,
                        cost_usd=llm_metadata.cost_usd,
                        status="complete",
                        metadata={
                            "fallback_reason": llm_metadata.fallback_reason,
                            "is_rule_based": True,
                        } if llm_metadata.fallback_reason else {"is_rule_based": True},
                    )

                # 6. Convert to dict
                result_data = processed_jd_to_dict(processed)
                section_count = len(result_data.get("sections", []))
                section_types = result_data.get("section_ids", [])
                layer_status["jd_processor"] = {
                    "status": "success",
                    "sections": section_count,
                    "section_types": section_types,
                    "backend": llm_metadata.backend,
                    "model": llm_metadata.model,
                    "message": f"Parsed {section_count} sections via {llm_metadata.backend}: {', '.join(section_types[:3])}{'...' if len(section_types) > 3 else ''}"
                }
                logger.info(
                    f"[{run_id[:16]}] JD Processor complete: {section_count} sections "
                    f"via backend={llm_metadata.backend}, model={llm_metadata.model}"
                )
                await emit_progress("jd_processor", "success", f"Parsed {section_count} sections via {llm_metadata.backend}")
                emit_log(
                    f"LLM responded via backend={llm_metadata.backend}, model={llm_metadata.model}",
                    backend=llm_metadata.backend,
                    model=llm_metadata.model,
                )

                # 7. Persist result
                await emit_progress("persist", "processing", "Saving to database")
                logger.info(f"[{run_id[:16]}] Persisting results to database")
                persisted = self._persist_result(job_id, result_data)
                if persisted:
                    layer_status["persist"] = {
                        "status": "success",
                        "message": "Saved to database"
                    }
                    await emit_progress("persist", "success", "Results saved")
                else:
                    layer_status["persist"] = {
                        "status": "warning",
                        "message": "Processing succeeded but persistence failed"
                    }
                    await emit_progress("persist", "warning", "Persistence failed but processing succeeded")
                    logger.warning(
                        f"[{run_id[:16]}] Failed to persist result, but processing succeeded"
                    )

                # 8. Use actual cost from LLM metadata if available
                input_tokens = 0
                output_tokens = 0
                cost_usd = llm_metadata.cost_usd or 0.0

                if use_llm and cost_usd == 0.0:
                    # Fallback to estimate if no actual cost available
                    input_tokens = len(jd_text) // 4 + 500  # Add system prompt overhead
                    output_tokens = len(str(result_data.get("sections", []))) // 4
                    cost_usd = self.estimate_cost(tier, input_tokens, output_tokens)

                # 9. Build response data with layer_status and LLM metadata
                response_data = {
                    "processed_jd": result_data,
                    "section_count": section_count,
                    "section_types": section_types,
                    "content_hash": result_data.get("content_hash"),
                    "used_llm": use_llm,
                    "persisted": persisted,
                    "layer_status": layer_status,
                    # Add LLM backend attribution for transparency
                    "llm_metadata": llm_metadata.to_dict(),
                }

                logger.info(
                    f"[{run_id[:16]}] Completed structure-jd: "
                    f"{response_data['section_count']} sections, "
                    f"backend={llm_metadata.backend}, cost=${cost_usd:.4f}"
                )

                # 10. Persist operation run for tracking
                result = self.create_success_result(
                    run_id=run_id,
                    data=response_data,
                    cost_usd=cost_usd,
                    duration_ms=timer.duration_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model_used=llm_metadata.model if use_llm else "rule-based",
                )

                # Persist run record
                self.persist_run(result, job_id, tier)

                return result

            except Exception as e:
                logger.exception(f"[{run_id[:16]}] structure-jd failed: {e}")
                error_result = self.create_error_result(
                    run_id=run_id,
                    error=str(e),
                    duration_ms=timer.duration_ms,
                )
                self.persist_run(error_result, job_id, tier)
                return error_result


# Convenience function for direct usage
async def structure_jd(
    job_id: str,
    tier: ModelTier = ModelTier.BALANCED,
    use_llm: bool = True,
    db_client: Optional[MongoClient] = None,
) -> OperationResult:
    """
    Convenience function to structure a JD.

    Args:
        job_id: MongoDB ObjectId of the job
        tier: Model tier (default: BALANCED)
        use_llm: Whether to use LLM (default: True)
        db_client: Optional MongoDB client

    Returns:
        OperationResult with structured JD
    """
    service = StructureJDService(db_client=db_client)
    return await service.execute(job_id=job_id, tier=tier, use_llm=use_llm)
