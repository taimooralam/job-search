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

import asyncio
import json
import logging
import os
import traceback
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from bson import ObjectId

from src.common.model_tiers import ModelTier, get_model_for_operation
from src.common.repositories import get_job_repository, JobRepositoryInterface
from src.common.state import JobState
from src.layer1_4 import process_jd, process_jd_sync, processed_jd_to_dict, LLMMetadata
from src.layer1_4.claude_jd_extractor import JDExtractor
from src.services.operation_base import OperationResult, OperationService

logger = logging.getLogger(__name__)


class FullExtractionService(OperationService):
    """
    Service for full JD extraction including structuring, pain points, and fit scoring.

    Runs Layer 1.4 + Layer 2 + Layer 4 and persists combined results.
    """

    operation_name = "full-extraction"

    def __init__(self, repository: Optional[JobRepositoryInterface] = None):
        """
        Initialize the service.

        Args:
            repository: Optional job repository. If not provided, uses default factory.
        """
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

    def _load_candidate_profile(self) -> Optional[str]:
        """
        Load candidate profile for fit scoring.

        Priority order:
        1. MongoDB via MasterCVStore (when USE_MASTER_CV_MONGODB=true)
        2. Config.CANDIDATE_PROFILE_PATH file
        3. data/master-cv/master-cv.md fallback

        This ensures fit analysis has candidate context from the CV Editor
        data stored in MongoDB, with file fallback for backward compatibility.

        Returns:
            Candidate profile text, or None if not available
        """
        from pathlib import Path
        from src.common.config import Config

        # Priority 1: Try MongoDB first (when enabled)
        if Config.USE_MASTER_CV_MONGODB:
            try:
                from src.common.master_cv_store import get_candidate_profile_text
                profile_text = get_candidate_profile_text()
                if profile_text:
                    logger.info(
                        f"Loaded candidate profile from MongoDB ({len(profile_text)} chars)"
                    )
                    return profile_text
                else:
                    logger.debug("No candidate profile in MongoDB, falling back to files")
            except Exception as e:
                logger.warning(f"MongoDB candidate profile load failed: {e}")

        # Priority 2: Try the configured file path
        profile_path = Path(Config.CANDIDATE_PROFILE_PATH)
        if profile_path.exists():
            try:
                profile_text = profile_path.read_text(encoding="utf-8")
                logger.info(
                    f"Loaded candidate profile from file: {profile_path} ({len(profile_text)} chars)"
                )
                return profile_text
            except Exception as e:
                logger.warning(f"Error reading candidate profile from {profile_path}: {e}")

        # Priority 3: Try data/master-cv/master-cv.md as final fallback
        fallback_path = Path("data/master-cv/master-cv.md")
        if fallback_path.exists():
            try:
                profile_text = fallback_path.read_text(encoding="utf-8")
                logger.info(
                    f"Loaded candidate profile from fallback: {fallback_path} ({len(profile_text)} chars)"
                )
                return profile_text
            except Exception as e:
                logger.warning(f"Error reading candidate profile from {fallback_path}: {e}")

        logger.warning("No candidate profile found - fit analysis may lack grounding")
        return None

    def _run_jd_processor(self, jd_text: str, model: str, use_llm: bool) -> Tuple[Dict[str, Any], LLMMetadata]:
        """
        Run JD Processor: Parse JD into HTML sections for annotation.

        Returns:
            Tuple of (processed JD dict with html, sections, section_ids, LLMMetadata for backend attribution)
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
                    processed, llm_metadata = future.result()
            else:
                processed, llm_metadata = loop.run_until_complete(
                    process_jd(jd_text, use_llm=True, model=model)
                )
        else:
            processed, llm_metadata = process_jd_sync(jd_text, use_llm=False)

        return processed_jd_to_dict(processed), llm_metadata

    def _run_jd_extractor(
        self, job: Dict[str, Any], jd_text: str, log_callback: callable = None
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Run JD Extractor: Extract structured intelligence from JD.

        Uses Claude Code CLI for high-quality extraction.

        Args:
            job: Job document from MongoDB
            jd_text: Job description text
            log_callback: Optional callback for log streaming with backend visibility

        Returns:
            Tuple of (extracted_jd, error_message):
            - On success: (extracted_jd_dict, None)
            - On failure: (None, error_message_string)
        """
        job_id = str(job.get("_id", ""))
        title = job.get("title", "")
        company = job.get("firm") or job.get("company", "")

        extractor = JDExtractor(log_callback=log_callback)
        result = extractor.extract(
            job_id=job_id,
            title=title,
            company=company,
            job_description=jd_text,
        )

        if result.success and result.extracted_jd:
            return result.extracted_jd, None
        else:
            error_message = result.error
            # Truncate if too long for SSE display
            if error_message and len(error_message) > 200:
                error_message = error_message[:197] + "..."
            return None, error_message

    def _run_layer_2(
        self, job: Dict[str, Any], jd_text: str, log_callback: callable = None
    ) -> Dict[str, Any]:
        """
        Run Layer 2: Pain Point Mining.

        Args:
            job: Job document from MongoDB
            jd_text: Job description text
            log_callback: Optional callback for log streaming with backend visibility

        Returns dict with pain_points, strategic_needs, risks_if_unfilled, success_metrics.
        """
        from src.layer2.pain_point_miner import PainPointMiner

        state: JobState = {
            "job_id": str(job.get("_id", "")),
            "title": job.get("title", ""),
            "company": job.get("firm") or job.get("company", ""),
            "job_description": jd_text,
        }

        miner = PainPointMiner(use_enhanced_format=False, log_callback=log_callback)
        return miner.extract_pain_points(state)

    def _aggregate_annotations(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggregate annotation signals into a fit summary.

        Returns dict with:
            - annotation_score: weighted score 0-100 based on annotations
            - good_match_count: annotations marked as core_strength or extremely_relevant
            - partial_match_count: annotations marked as relevant or tangential
            - gap_count: annotations marked as gap
            - strategic_notes: list of strategic notes from annotations
            - must_have_gaps: list of gaps on must-have requirements
        """
        jd_annotations = job.get("jd_annotations", {})
        annotations = jd_annotations.get("annotations", [])

        if not annotations:
            return {
                "annotation_score": None,
                "good_match_count": 0,
                "partial_match_count": 0,
                "gap_count": 0,
                "strategic_notes": [],
                "must_have_gaps": [],
                "annotation_summary": "No annotations available"
            }

        # Multipliers aligned with jd-annotation.js
        RELEVANCE_MULTIPLIERS = {
            "core_strength": 3.0,
            "extremely_relevant": 2.0,
            "relevant": 1.0,
            "tangential": 0.7,
            "gap": 0.3
        }

        good_match_count = 0
        partial_match_count = 0
        gap_count = 0
        strategic_notes = []
        must_have_gaps = []
        total_weight = 0
        weighted_sum = 0

        for ann in annotations:
            relevance = ann.get("relevance", "relevant")
            requirement = ann.get("requirement_type", "neutral")
            multiplier = RELEVANCE_MULTIPLIERS.get(relevance, 1.0)

            # Count by category
            if relevance in ("core_strength", "extremely_relevant"):
                good_match_count += 1
            elif relevance in ("relevant", "tangential"):
                partial_match_count += 1
            elif relevance == "gap":
                gap_count += 1
                if requirement == "must_have":
                    must_have_gaps.append({
                        "text": ann.get("target", {}).get("text", ""),
                        "reframe_note": ann.get("reframe_note", "")
                    })

            # Collect strategic notes
            if ann.get("strategic_note"):
                strategic_notes.append(ann["strategic_note"])

            # Weight calculation - must-haves count more
            weight = 2.0 if requirement == "must_have" else 1.0
            total_weight += weight
            weighted_sum += multiplier * weight * 33.33  # Scale to 0-100

        # Calculate annotation-based fit score
        annotation_score = int(weighted_sum / total_weight) if total_weight > 0 else None

        # Build summary
        total = good_match_count + partial_match_count + gap_count
        summary_parts = []
        if good_match_count > 0:
            summary_parts.append(f"{good_match_count} strong matches")
        if partial_match_count > 0:
            summary_parts.append(f"{partial_match_count} partial matches")
        if gap_count > 0:
            summary_parts.append(f"{gap_count} gaps")

        return {
            "annotation_score": annotation_score,
            "good_match_count": good_match_count,
            "partial_match_count": partial_match_count,
            "gap_count": gap_count,
            "strategic_notes": strategic_notes,
            "must_have_gaps": must_have_gaps,
            "annotation_summary": ", ".join(summary_parts) if summary_parts else "No annotations"
        }

    def _run_layer_4(
        self,
        job: Dict[str, Any],
        jd_text: str,
        pain_points_data: Dict[str, Any],
        log_callback: callable = None,
    ) -> Dict[str, Any]:
        """
        Run Layer 4: Opportunity Mapping / Fit Scoring.

        Args:
            job: Job document from MongoDB
            jd_text: Job description text
            pain_points_data: Output from Layer 2 pain point mining
            log_callback: Optional callback for log streaming to frontend

        Returns:
            Dict with fit_score, fit_rationale, fit_category.
        """
        from src.layer4.opportunity_mapper import OpportunityMapper

        # Aggregate annotation signals for fit scoring
        annotation_signals = self._aggregate_annotations(job)

        state: JobState = {
            "job_id": str(job.get("_id", "")),
            "title": job.get("title", ""),
            "company": job.get("firm") or job.get("company", ""),
            "job_description": jd_text,
            # Include pain points from Layer 2
            "pain_points": pain_points_data.get("pain_points", []),
            "strategic_needs": pain_points_data.get("strategic_needs", []),
            "risks_if_unfilled": pain_points_data.get("risks_if_unfilled", []),
            "success_metrics": pain_points_data.get("success_metrics", []),
            # Include any existing research
            "company_research": job.get("company_research"),
            "role_research": job.get("role_research"),
            # Include candidate profile - check MongoDB first, then file fallback
            # CRITICAL: Ensures fit analysis has candidate context for accurate scoring
            "candidate_profile": job.get("candidate_profile") or self._load_candidate_profile() or "",
            "selected_stars": job.get("selected_stars", []),
            "all_stars": job.get("all_stars", []),
            # Include annotation signals for fit scoring
            "annotation_signals": annotation_signals,
        }

        mapper = OpportunityMapper()
        result = mapper.map_opportunity(state, log_callback=log_callback)

        # Add annotation summary to result
        result["annotation_signals"] = annotation_signals

        return result

    def _persist_results(
        self,
        job_id: str,
        processed_jd: Dict[str, Any],
        extracted_jd: Optional[Dict[str, Any]],
        pain_points_data: Dict[str, Any],
        fit_data: Dict[str, Any],
    ) -> bool:
        """
        Persist all extraction results to MongoDB.

        Args:
            job_id: MongoDB ObjectId as string
            processed_jd: JD Processor results (html, sections for annotation UI)
            extracted_jd: JD Extractor results (role_category, responsibilities, etc.)
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

        repo = self._get_repository()
        try:
            # Get existing annotations and URL fields to preserve/normalize them
            job = repo.find_one({"_id": object_id})
            existing_annotations = job.get("jd_annotations", {}) if job else {}

            # Update with processed JD (for annotation UI)
            existing_annotations["processed_jd_html"] = processed_jd.get("html")
            existing_annotations["processed_jd_sections"] = processed_jd.get("sections")
            existing_annotations["content_hash"] = processed_jd.get("content_hash")
            existing_annotations["annotation_version"] = (
                existing_annotations.get("annotation_version", 0) + 1
            )

            # Normalize LinkedIn URL if present
            normalized_url = None
            if job:
                current_url = job.get("job_url") or job.get("jobUrl")
                if current_url:
                    from src.services.linkedin_scraper import normalize_linkedin_url

                    normalized_url = normalize_linkedin_url(current_url)
                    if normalized_url and normalized_url != current_url:
                        logger.info(
                            f"Normalized LinkedIn URL: {current_url} -> {normalized_url}"
                        )

            # Build update document
            update_doc = {
                "jd_annotations": existing_annotations,
                # Store extracted_jd (role_category, responsibilities, etc.) for template
                "extracted_jd": extracted_jd,
                # Store processed_jd separately for annotation system
                "processed_jd": processed_jd,
                # Layer 2 results
                "pain_points": pain_points_data.get("pain_points", []),
                "strategic_needs": pain_points_data.get("strategic_needs", []),
                "risks_if_unfilled": pain_points_data.get("risks_if_unfilled", []),
                "success_metrics": pain_points_data.get("success_metrics", []),
                # Layer 4 results
                "fit_score": fit_data.get("fit_score"),
                "fit_rationale": fit_data.get("fit_rationale"),
                "fit_category": fit_data.get("fit_category"),
                # Annotation signals (for UI heatmap)
                "annotation_signals": fit_data.get("annotation_signals"),
                # Metadata
                "full_extraction_completed_at": datetime.utcnow(),
                "updatedAt": datetime.utcnow(),
            }

            # Add normalized LinkedIn URL if changed
            if normalized_url:
                update_doc["job_url"] = normalized_url
                update_doc["jobUrl"] = normalized_url

            result = repo.update_one(
                {"_id": object_id},
                {"$set": update_doc},
            )

            return result.modified_count > 0 or result.matched_count > 0

        except Exception as e:
            logger.error(f"Failed to persist extraction results: {e}")
            return False

    async def execute(
        self,
        job_id: str,
        tier: ModelTier,
        use_llm: bool = True,
        progress_callback: callable = None,
        log_callback: callable = None,
        **kwargs,
    ) -> OperationResult:
        """
        Execute full extraction operation (Layer 1.4 + Layer 2 + Layer 4).

        Args:
            job_id: MongoDB ObjectId of the job to process
            tier: Model tier for quality/cost selection
            use_llm: Whether to use LLM for processing (default True)
            progress_callback: Optional callback(layer_key, status, message) for real-time updates
            log_callback: Optional callback(message: str) for log streaming to frontend
            **kwargs: Additional arguments (ignored)

        Returns:
            OperationResult with combined extraction data
        """
        # Helper to call progress callback if provided (async to yield to event loop)
        async def emit_progress(layer_key: str, status: str, message: str):
            if progress_callback:
                try:
                    progress_callback(layer_key, status, message)
                    await asyncio.sleep(0)  # CRITICAL: Yield to event loop for SSE delivery
                except Exception as e:
                    logger.warning(f"Progress callback failed: {e}")

        # Create JSON log callback wrapper for JDExtractor
        # This converts JDExtractor's dict logs to JSON strings for Redis streaming
        # The frontend parses these JSON logs to display backend/LLM provider badges
        import json as _json
        def jd_log_callback(job_id: str, level: str, data: Dict[str, Any]) -> None:
            if log_callback:
                # Emit JSON log with backend field for frontend visibility
                log_callback(_json.dumps(data))

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
                    if log_callback:
                        log_callback(_json.dumps({"message": f"JD text extracted: {len(jd_text)} chars"}))
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

                # Track per-layer status for detailed logging
                layer_status = {}

                # 4a. Run JD Processor: Parse into HTML sections
                await emit_progress("jd_processor", "processing", "Parsing job description")
                logger.info(f"[{run_id[:16]}] Running JD Processor: Parsing into sections")
                processed_jd, jd_processor_llm_metadata = self._run_jd_processor(jd_text, model, use_llm)
                section_count = len(processed_jd.get("sections", []))
                layer_status["jd_processor"] = {
                    "status": "success",
                    "sections": section_count,
                    "backend": jd_processor_llm_metadata.backend,
                    "model": jd_processor_llm_metadata.model,
                    "message": f"Parsed {section_count} sections via {jd_processor_llm_metadata.backend}"
                }
                await emit_progress("jd_processor", "success", f"Parsed {section_count} sections via {jd_processor_llm_metadata.backend}")
                logger.info(f"[{run_id[:16]}] JD Processor complete: {section_count} sections via backend={jd_processor_llm_metadata.backend}")

                # 4b. Run JD Extractor: Extract structured intelligence
                await emit_progress("jd_extractor", "processing", "Extracting role intelligence")
                logger.info(f"[{run_id[:16]}] Running JD Extractor: Extracting role info")
                extracted_jd, extractor_error = self._run_jd_extractor(job, jd_text, jd_log_callback)
                if extracted_jd:
                    role_category = extracted_jd.get("role_category", "unknown")
                    keywords_count = len(extracted_jd.get("top_keywords", []))
                    layer_status["jd_extractor"] = {
                        "status": "success",
                        "role_category": role_category,
                        "keywords": keywords_count,
                        "message": f"Extracted role: {role_category}, {keywords_count} keywords"
                    }
                    await emit_progress("jd_extractor", "success", f"Role: {role_category}, {keywords_count} keywords")
                    logger.info(f"[{run_id[:16]}] JD Extractor complete: role={role_category}, {keywords_count} keywords")
                else:
                    # Include actual error message in status and SSE stream
                    error_display = f"Failed: {extractor_error}" if extractor_error else "Using fallback"
                    layer_status["jd_extractor"] = {
                        "status": "failed",
                        "error": extractor_error,
                        "message": f"JD extraction failed - {error_display}"
                    }
                    await emit_progress("jd_extractor", "failed", error_display)
                    logger.warning(f"[{run_id[:16]}] JD Extractor failed: {extractor_error}")

                # 5. Run Layer 2: Pain Point Mining
                await emit_progress("pain_points", "processing", "Mining pain points")
                logger.info(f"[{run_id[:16]}] Running Layer 2: Pain Point Mining")
                pain_points_data = self._run_layer_2(job, jd_text, log_callback=log_callback)
                pain_count = len(pain_points_data.get("pain_points", []))
                layer_status["layer_2"] = {
                    "status": "success",
                    "pain_points": pain_count,
                    "strategic_needs": len(pain_points_data.get("strategic_needs", [])),
                    "message": f"Found {pain_count} pain points"
                }
                await emit_progress("pain_points", "success", f"Found {pain_count} pain points")
                logger.info(f"[{run_id[:16]}] Layer 2 complete: {pain_count} pain points")

                # 6. Run Layer 4: Fit Scoring (with annotation signals)
                await emit_progress("fit_scoring", "processing", "Calculating fit score")
                logger.info(f"[{run_id[:16]}] Running Layer 4: Fit Scoring")

                # Log annotation aggregation before fit scoring
                existing_annotations = job.get("jd_annotations", {}).get("annotations", [])
                if existing_annotations:
                    match_count = sum(1 for a in existing_annotations if a.get("relevance") in ("core_strength", "extremely_relevant", "relevant", "tangential"))
                    gap_count = sum(1 for a in existing_annotations if a.get("relevance") == "gap")
                    if log_callback:
                        log_callback(_json.dumps({"message": f"Aggregating annotations: {match_count} matches, {gap_count} gaps"}))

                fit_data = self._run_layer_4(job, jd_text, pain_points_data, log_callback=log_callback)
                fit_score = fit_data.get("fit_score")
                fit_category = fit_data.get("fit_category")
                annotation_signals = fit_data.get("annotation_signals", {})
                layer_status["layer_4"] = {
                    "status": "success",
                    "fit_score": fit_score,
                    "fit_category": fit_category,
                    "annotation_score": annotation_signals.get("annotation_score"),
                    "annotation_summary": annotation_signals.get("annotation_summary"),
                    "message": f"Fit score: {fit_score} ({fit_category})"
                }
                await emit_progress("fit_scoring", "success", f"Score: {fit_score} ({fit_category})")
                logger.info(f"[{run_id[:16]}] Layer 4 complete: score={fit_score}, category={fit_category}")
                if annotation_signals.get("annotation_score"):
                    logger.info(f"[{run_id[:16]}] Annotation score: {annotation_signals['annotation_score']}, "
                               f"summary: {annotation_signals['annotation_summary']}")

                # 7. Persist results (pass both processed_jd and extracted_jd)
                await emit_progress("save_results", "processing", "Saving to database")
                if log_callback:
                    log_callback(_json.dumps({"message": "Persisting extraction results to database..."}))
                persisted = self._persist_results(
                    job_id, processed_jd, extracted_jd, pain_points_data, fit_data
                )
                if persisted:
                    if log_callback:
                        log_callback(_json.dumps({"message": "Results saved successfully"}))
                    await emit_progress("save_results", "success", "Results saved")
                else:
                    await emit_progress("save_results", "failed", "Persistence failed")
                    logger.warning(f"[{run_id[:16]}] Failed to persist results")

                # 8. Estimate cost (rough - 4 LLM calls now)
                input_tokens = len(jd_text) // 4 * 4 + 2000  # 4x JD + prompts
                output_tokens = 3000  # Approximate
                cost_usd = self.estimate_cost(tier, input_tokens, output_tokens)
                if log_callback:
                    log_callback(_json.dumps({"message": f"Estimated cost: ${cost_usd:.4f} ({tier.value} tier)"}))

                # 9. Build combined response with layer status
                response_data = {
                    "processed_jd": processed_jd,
                    "extracted_jd": extracted_jd,
                    "section_count": section_count,
                    "pain_points_count": pain_count,
                    "strategic_needs_count": len(pain_points_data.get("strategic_needs", [])),
                    "fit_score": fit_score,
                    "fit_category": fit_category,
                    "fit_rationale": fit_data.get("fit_rationale"),
                    # Include annotation-based signals
                    "annotation_signals": annotation_signals,
                    "annotation_score": annotation_signals.get("annotation_score"),
                    "good_match_count": annotation_signals.get("good_match_count", 0),
                    "gap_count": annotation_signals.get("gap_count", 0),
                    "layers_completed": ["1.4-processor", "1.4-extractor", "2", "4"],
                    "layer_status": layer_status,
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
                # Capture full traceback for frontend display
                tb_str = traceback.format_exc()
                error_msg = f"{type(e).__name__}: {str(e)}"

                logger.exception(f"[{run_id[:16]}] full-extraction failed: {e}")

                # Emit structured error log with traceback for frontend CLI panel
                if log_callback:
                    error_log = json.dumps({
                        "event": "layer_error",
                        "layer_name": "full_extraction",
                        "error": error_msg,
                        "metadata": {
                            "error_type": type(e).__name__,
                            "traceback": tb_str,
                            "context": "FullExtractionService.execute",
                            "run_id": run_id,
                        }
                    })
                    log_callback(error_log)

                # Also emit progress callback with error details
                if progress_callback:
                    try:
                        # Include traceback in metadata if layer_callback supports it
                        progress_callback(
                            "full_extraction",
                            "error",
                            error_msg,
                            {"traceback": tb_str, "error_type": type(e).__name__},
                        )
                    except TypeError:
                        # Fallback if callback doesn't accept metadata
                        progress_callback("full_extraction", "error", error_msg)

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
    repository: Optional[JobRepositoryInterface] = None,
) -> OperationResult:
    """
    Convenience function for full JD extraction.

    Args:
        job_id: MongoDB ObjectId of the job
        tier: Model tier (default: BALANCED)
        use_llm: Whether to use LLM (default: True)
        repository: Optional job repository for MongoDB operations

    Returns:
        OperationResult with extraction data
    """
    service = FullExtractionService(repository=repository)
    return await service.execute(job_id=job_id, tier=tier, use_llm=use_llm)
