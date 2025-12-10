"""
Full Extraction Service - Phase 4 Implementation

Service for running the complete JD extraction pipeline:
- Layer 1.4: JD Structuring (parse into sections)
- Layer 2: Pain Point Mining (extract pain points, strategic needs, etc.)
- Layer 4: Fit Scoring (opportunity mapping)

Combines all results into a single badge showing extraction status.

Usage:
    service = FullExtractionService()
    result = await service.execute(job_id="...", tier=ModelTier.BALANCED)
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId
from pymongo import MongoClient

from src.common.model_tiers import ModelTier, get_model_for_operation
from src.common.state import JobState
from src.layer1_4 import process_jd, process_jd_sync, processed_jd_to_dict
from src.services.operation_base import OperationResult, OperationService

logger = logging.getLogger(__name__)


class FullExtractionService(OperationService):
    """
    Service for full JD extraction including structuring, pain points, and fit scoring.

    Runs Layer 1.4 + Layer 2 + Layer 4 and persists combined results.
    """

    operation_name = "full-extraction"

    def __init__(self, db_client: Optional[MongoClient] = None):
        """
        Initialize the service.

        Args:
            db_client: Optional MongoDB client. If not provided, creates one.
        """
        self._db_client = db_client

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
        """Fetch job from MongoDB by ID."""
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
        """Extract JD text from job document."""
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

    def _run_layer_1_4(self, jd_text: str, model: str, use_llm: bool) -> Dict[str, Any]:
        """
        Run Layer 1.4: JD Structuring.

        Returns processed JD dict with sections.
        """
        import asyncio

        if use_llm:
            # Run async process_jd synchronously
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, use run_coroutine_threadsafe
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, process_jd(jd_text, use_llm=True, model=model)
                    )
                    processed = future.result()
            else:
                processed = loop.run_until_complete(
                    process_jd(jd_text, use_llm=True, model=model)
                )
        else:
            processed = process_jd_sync(jd_text, use_llm=False)

        return processed_jd_to_dict(processed)

    def _run_layer_2(self, job: Dict[str, Any], jd_text: str) -> Dict[str, Any]:
        """
        Run Layer 2: Pain Point Mining.

        Returns dict with pain_points, strategic_needs, risks_if_unfilled, success_metrics.
        """
        from src.layer2.pain_point_miner import PainPointMiner

        state: JobState = {
            "job_id": str(job.get("_id", "")),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "job_description": jd_text,
        }

        miner = PainPointMiner(use_enhanced_format=False)
        return miner.extract_pain_points(state)

    def _run_layer_4(
        self, job: Dict[str, Any], jd_text: str, pain_points_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run Layer 4: Opportunity Mapping / Fit Scoring.

        Returns dict with fit_score, fit_rationale, fit_category.
        """
        from src.layer4.opportunity_mapper import OpportunityMapper

        state: JobState = {
            "job_id": str(job.get("_id", "")),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "job_description": jd_text,
            # Include pain points from Layer 2
            "pain_points": pain_points_data.get("pain_points", []),
            "strategic_needs": pain_points_data.get("strategic_needs", []),
            "risks_if_unfilled": pain_points_data.get("risks_if_unfilled", []),
            "success_metrics": pain_points_data.get("success_metrics", []),
            # Include any existing research
            "company_research": job.get("company_research"),
            "role_research": job.get("role_research"),
            # Include candidate profile if available
            "candidate_profile": job.get("candidate_profile", ""),
            "selected_stars": job.get("selected_stars", []),
            "all_stars": job.get("all_stars", []),
        }

        mapper = OpportunityMapper()
        return mapper.map_opportunity(state)

    def _persist_results(
        self,
        job_id: str,
        processed_jd: Dict[str, Any],
        pain_points_data: Dict[str, Any],
        fit_data: Dict[str, Any],
    ) -> bool:
        """
        Persist all extraction results to MongoDB.

        Args:
            job_id: MongoDB ObjectId as string
            processed_jd: Layer 1.4 results
            pain_points_data: Layer 2 results
            fit_data: Layer 4 results

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

            # Update with processed JD
            existing_annotations["processed_jd_html"] = processed_jd.get("html")
            existing_annotations["processed_jd_sections"] = processed_jd.get("sections")
            existing_annotations["content_hash"] = processed_jd.get("content_hash")
            existing_annotations["annotation_version"] = (
                existing_annotations.get("annotation_version", 0) + 1
            )

            # Build update document
            update_doc = {
                "jd_annotations": existing_annotations,
                "extracted_jd": processed_jd,
                # Layer 2 results
                "pain_points": pain_points_data.get("pain_points", []),
                "strategic_needs": pain_points_data.get("strategic_needs", []),
                "risks_if_unfilled": pain_points_data.get("risks_if_unfilled", []),
                "success_metrics": pain_points_data.get("success_metrics", []),
                # Layer 4 results
                "fit_score": fit_data.get("fit_score"),
                "fit_rationale": fit_data.get("fit_rationale"),
                "fit_category": fit_data.get("fit_category"),
                # Metadata
                "full_extraction_completed_at": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }

            result = collection.update_one(
                {"_id": object_id},
                {"$set": update_doc},
            )

            return result.modified_count > 0 or result.matched_count > 0

        except Exception as e:
            logger.error(f"Failed to persist extraction results: {e}")
            return False
        finally:
            if self._db_client is None:
                client.close()

    async def execute(
        self,
        job_id: str,
        tier: ModelTier,
        use_llm: bool = True,
        **kwargs,
    ) -> OperationResult:
        """
        Execute full extraction operation (Layer 1.4 + Layer 2 + Layer 4).

        Args:
            job_id: MongoDB ObjectId of the job to process
            tier: Model tier for quality/cost selection
            use_llm: Whether to use LLM for processing (default True)
            **kwargs: Additional arguments (ignored)

        Returns:
            OperationResult with combined extraction data
        """
        run_id = self.create_run_id()
        logger.info(f"[{run_id[:16]}] Starting full-extraction for job {job_id}")

        with self.timed_execution() as timer:
            try:
                # 1. Fetch job
                job = self._get_job(job_id)
                if not job:
                    return self.create_error_result(
                        run_id=run_id,
                        error=f"Job not found: {job_id}",
                        duration_ms=timer.duration_ms,
                    )

                # 2. Extract JD text
                try:
                    jd_text = self._get_jd_text(job)
                except ValueError as e:
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

                # 4. Run Layer 1.4: JD Structuring
                logger.info(f"[{run_id[:16]}] Running Layer 1.4: JD Structuring")
                processed_jd = self._run_layer_1_4(jd_text, model, use_llm)
                section_count = len(processed_jd.get("sections", []))
                logger.info(f"[{run_id[:16]}] Layer 1.4 complete: {section_count} sections")

                # 5. Run Layer 2: Pain Point Mining
                logger.info(f"[{run_id[:16]}] Running Layer 2: Pain Point Mining")
                pain_points_data = self._run_layer_2(job, jd_text)
                pain_count = len(pain_points_data.get("pain_points", []))
                logger.info(f"[{run_id[:16]}] Layer 2 complete: {pain_count} pain points")

                # 6. Run Layer 4: Fit Scoring
                logger.info(f"[{run_id[:16]}] Running Layer 4: Fit Scoring")
                fit_data = self._run_layer_4(job, jd_text, pain_points_data)
                fit_score = fit_data.get("fit_score")
                fit_category = fit_data.get("fit_category")
                logger.info(f"[{run_id[:16]}] Layer 4 complete: score={fit_score}, category={fit_category}")

                # 7. Persist results
                persisted = self._persist_results(job_id, processed_jd, pain_points_data, fit_data)
                if not persisted:
                    logger.warning(f"[{run_id[:16]}] Failed to persist results")

                # 8. Estimate cost (rough - 3 LLM calls)
                input_tokens = len(jd_text) // 4 * 3 + 1500  # 3x JD + prompts
                output_tokens = 2000  # Approximate
                cost_usd = self.estimate_cost(tier, input_tokens, output_tokens)

                # 9. Build combined response
                response_data = {
                    "processed_jd": processed_jd,
                    "section_count": section_count,
                    "pain_points_count": pain_count,
                    "strategic_needs_count": len(pain_points_data.get("strategic_needs", [])),
                    "fit_score": fit_score,
                    "fit_category": fit_category,
                    "fit_rationale": fit_data.get("fit_rationale"),
                    "layers_completed": ["1.4", "2", "4"],
                    "persisted": persisted,
                }

                logger.info(
                    f"[{run_id[:16]}] Full extraction complete: "
                    f"{section_count} sections, {pain_count} pain points, "
                    f"fit={fit_score}/{fit_category}"
                )

                result = self.create_success_result(
                    run_id=run_id,
                    data=response_data,
                    cost_usd=cost_usd,
                    duration_ms=timer.duration_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model_used=model if use_llm else "rule-based",
                )

                self.persist_run(result, job_id, tier)
                return result

            except Exception as e:
                logger.exception(f"[{run_id[:16]}] full-extraction failed: {e}")
                error_result = self.create_error_result(
                    run_id=run_id,
                    error=str(e),
                    duration_ms=timer.duration_ms,
                )
                self.persist_run(error_result, job_id, tier)
                return error_result


# Convenience function
async def full_extraction(
    job_id: str,
    tier: ModelTier = ModelTier.BALANCED,
    use_llm: bool = True,
    db_client: Optional[MongoClient] = None,
) -> OperationResult:
    """
    Convenience function for full JD extraction.

    Args:
        job_id: MongoDB ObjectId of the job
        tier: Model tier (default: BALANCED)
        use_llm: Whether to use LLM (default: True)
        db_client: Optional MongoDB client

    Returns:
        OperationResult with extraction data
    """
    service = FullExtractionService(db_client=db_client)
    return await service.execute(job_id=job_id, tier=tier, use_llm=use_llm)
