"""
Job Ingest Service

Shared logic for job ingestion from external sources (Himalaya, Indeed, etc.).
Handles deduplication, scoring, state management for incremental fetching,
and insertion into MongoDB level-2 collection.

Used by both:
- Runner endpoint (on-demand ingestion)
- Cron script (scheduled ingestion)

Usage:
    from src.services.job_ingest_service import IngestService, IngestResult

    db = get_mongodb()
    service = IngestService(db, use_claude_scorer=True)

    # Fetch and ingest
    jobs = himalayas_source.fetch_jobs(config)
    result = await service.ingest_jobs(
        jobs=jobs,
        source_name="himalayas_auto",
        incremental=True,
    )
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from pymongo.database import Database

from src.common.repositories import (
    get_job_repository,
    JobRepositoryInterface,
    get_system_state_repository,
    SystemStateRepositoryInterface,
)
from src.services.job_sources import JobData

logger = logging.getLogger(__name__)

# Type alias for log callback
LogCallback = Callable[[str], None]


@dataclass
class IngestResult:
    """Result of a job ingestion run."""

    success: bool
    source: str
    fetched: int = 0
    ingested: int = 0
    duplicates_skipped: int = 0
    below_threshold: int = 0
    errors: int = 0
    duration_ms: int = 0
    incremental: bool = False
    last_fetch_at: Optional[datetime] = None
    ingested_jobs: List[Dict[str, Any]] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "success": self.success,
            "source": self.source,
            "incremental": self.incremental,
            "stats": {
                "fetched": self.fetched,
                "ingested": self.ingested,
                "duplicates_skipped": self.duplicates_skipped,
                "below_threshold": self.below_threshold,
                "errors": self.errors,
                "duration_ms": self.duration_ms,
            },
            "last_fetch_at": self.last_fetch_at.isoformat() if self.last_fetch_at else None,
            "jobs": self.ingested_jobs,
            "error": self.error_message,
        }


class IngestService:
    """
    Shared job ingestion logic for cron and on-demand.

    Features:
    - Deduplication via dedupeKey
    - Quick scoring (Claude CLI or OpenRouter)
    - Incremental fetching via last_fetch_at state
    - Tier derivation and auto_discovered flag
    - Optional verbose logging via log_callback
    """

    def __init__(
        self,
        db: Database,
        use_claude_scorer: bool = True,
        log_callback: Optional[LogCallback] = None,
        repository: Optional[JobRepositoryInterface] = None,
        system_state_repository: Optional[SystemStateRepositoryInterface] = None,
    ):
        """
        Initialize the ingest service.

        Args:
            db: MongoDB database instance
            use_claude_scorer: If True, use Claude CLI for scoring (free).
                               If False, use OpenRouter (paid per token).
            log_callback: Optional callback for verbose logging (e.g., to Redis/SSE)
            repository: Optional job repository. If provided, uses repository for level-2 ops.
            system_state_repository: Optional system state repository for ingestion state.
        """
        self.db = db
        self._repository = repository
        self._system_state_repository = system_state_repository
        self.use_claude_scorer = use_claude_scorer
        self._log_callback = log_callback
        self._scorer = None  # Lazy init

    def _get_repository(self) -> JobRepositoryInterface:
        """Get the job repository instance."""
        if self._repository is not None:
            return self._repository
        return get_job_repository()

    def _get_system_state_repository(self) -> SystemStateRepositoryInterface:
        """Get the system state repository instance."""
        if self._system_state_repository is not None:
            return self._system_state_repository
        return get_system_state_repository()

    def _log(self, message: str) -> None:
        """Emit a log message via callback if available."""
        if self._log_callback:
            self._log_callback(message)

    def _get_scorer(self):
        """Get the appropriate scorer (lazy initialization)."""
        if self._scorer is None:
            if self.use_claude_scorer:
                try:
                    from src.services.claude_quick_scorer import ClaudeQuickScorer
                    self._scorer = ClaudeQuickScorer(log_callback=self._log_callback)
                    logger.info("Using ClaudeQuickScorer (Claude CLI)")
                except Exception as e:
                    logger.warning(f"Claude scorer unavailable, falling back to OpenRouter: {e}")
                    self._scorer = "openrouter"
            else:
                self._scorer = "openrouter"
        return self._scorer

    def get_last_fetch_timestamp(self, source: str) -> Optional[datetime]:
        """
        Get last successful fetch time for incremental fetching.

        Args:
            source: Source identifier (e.g., "himalayas_auto")

        Returns:
            Datetime of last fetch, or None if never fetched
        """
        state_repo = self._get_system_state_repository()
        state = state_repo.get_state(f"ingest_{source}")
        if state:
            return state.get("last_fetch_at")
        return None

    def update_last_fetch_timestamp(
        self,
        source: str,
        timestamp: datetime,
        stats: Optional[Dict[str, int]] = None,
    ):
        """
        Update last fetch time after successful ingestion.

        Args:
            source: Source identifier
            timestamp: Timestamp to record
            stats: Optional stats to store
        """
        state_repo = self._get_system_state_repository()
        state_id = f"ingest_{source}"

        update_doc = {
            "last_fetch_at": timestamp,
            "updated_at": datetime.utcnow(),
        }
        if stats:
            update_doc["last_run_stats"] = stats

        state_repo.set_state(state_id, update_doc, upsert=True)
        logger.info(f"Updated ingest state for {source}: last_fetch_at={timestamp}")

        # Store run in history (keep last 50 runs)
        if stats:
            run_record = {
                "timestamp": timestamp,
                "stats": stats,
                "source": source,
            }
            state_repo.push_to_array(state_id, "run_history", run_record, max_size=50)
            logger.info(f"Added run to history for {source}")

    def generate_dedupe_key(self, job: JobData, source_name: str) -> str:
        """
        Generate a deduplication key for a job.

        Format: company|title|location|source (lowercase, normalized)
        """
        company = (job.company or "").lower().strip()
        title = (job.title or "").lower().strip()
        location = (job.location or "").lower().strip()

        return f"{company}|{title}|{location}|{source_name}"

    def create_job_document(
        self,
        job: JobData,
        source_name: str,
        score: Optional[int],
        rationale: Optional[str],
    ) -> Dict[str, Any]:
        """
        Create a MongoDB document for a job.

        Follows the level-2 schema expected by Layer 1.4.
        """
        from src.services.claude_quick_scorer import derive_tier_from_score

        return {
            "company": job.company,
            "title": job.title,
            "location": job.location,
            "jobUrl": job.url,
            "description": job.description,
            "dedupeKey": self.generate_dedupe_key(job, source_name),
            "createdAt": datetime.utcnow(),
            "status": "not processed",
            "source": source_name,
            "auto_discovered": True,
            "score": score,  # Normalized field for templates
            "quick_score": score,
            "quick_score_rationale": rationale,
            "tier": derive_tier_from_score(score),
            # Optional fields
            "salary": job.salary,
            "jobType": job.job_type,
            "postedDate": job.posted_date,
            "sourceId": job.source_id,
        }

    async def _score_job(
        self,
        job: JobData,
        candidate_profile: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Score a job using the appropriate scorer.

        Returns:
            Tuple of (score, rationale)
        """
        scorer = self._get_scorer()

        if scorer == "openrouter":
            # Use existing quick_scorer (sync)
            from src.services.quick_scorer import quick_score_job
            return quick_score_job(
                title=job.title,
                company=job.company,
                location=job.location,
                description=job.description or "",
                candidate_profile=candidate_profile,
            )
        else:
            # Use ClaudeQuickScorer (async)
            return await scorer.score_job(
                title=job.title,
                company=job.company,
                location=job.location,
                description=job.description or "",
                candidate_profile=candidate_profile,
            )

    async def ingest_jobs(
        self,
        jobs: List[JobData],
        source_name: str,
        score_threshold: int = 70,
        skip_scoring: bool = False,
        incremental: bool = True,
        candidate_profile: Optional[str] = None,
    ) -> IngestResult:
        """
        Ingest jobs with deduplication, scoring, and state tracking.

        Args:
            jobs: List of JobData from source
            source_name: Source identifier (e.g., "himalayas_auto")
            score_threshold: Minimum score for ingestion (default 70 = Tier B+)
            skip_scoring: Skip LLM scoring (for testing)
            incremental: If True, filter by last_fetch_at timestamp
            candidate_profile: Optional profile override for scoring

        Returns:
            IngestResult with stats
        """
        start_time = datetime.utcnow()
        result = IngestResult(
            success=True,
            source=source_name,
            incremental=incremental,
        )

        try:
            # Get last fetch for incremental filtering
            last_fetch = None
            if incremental:
                last_fetch = self.get_last_fetch_timestamp(source_name)
                result.last_fetch_at = last_fetch
                if last_fetch:
                    logger.info(f"Incremental mode: filtering jobs newer than {last_fetch}")
                    self._log(f"[filter_incremental] Filtering jobs newer than {last_fetch.isoformat()}")

            # Filter by timestamp if incremental
            filtered_jobs = jobs
            original_count = len(jobs)
            if last_fetch:
                filtered_jobs = [
                    j for j in jobs
                    if j.posted_date and j.posted_date > last_fetch
                ]
                logger.info(f"Filtered {len(jobs)} jobs to {len(filtered_jobs)} new jobs")
                self._log(f"[filter_result] {original_count} -> {len(filtered_jobs)} after incremental filter")

            result.fetched = len(filtered_jobs)
            self._log(f"[process_start] Processing {len(filtered_jobs)} jobs...")

            # Process each job
            job_index = 0
            for job in filtered_jobs:
                job_index += 1
                try:
                    # Check for duplicates using repository
                    repo = self._get_repository()
                    dedupe_key = self.generate_dedupe_key(job, source_name)
                    if repo.find_one({"dedupeKey": dedupe_key}):
                        result.duplicates_skipped += 1
                        self._log(f"[dedupe_skip] ({job_index}/{len(filtered_jobs)}) {job.company} | {job.title} - duplicate")
                        continue

                    # Score the job
                    if skip_scoring:
                        score, rationale = 75, "Scoring skipped (test mode)"
                        self._log(f"[score_skip] ({job_index}/{len(filtered_jobs)}) {job.company} | {job.title} - scoring skipped")
                    else:
                        self._log(f"[score_start] ({job_index}/{len(filtered_jobs)}) Scoring {job.company} | {job.title}...")
                        score, rationale = await self._score_job(job, candidate_profile)

                    # Check threshold
                    if score is None or score < score_threshold:
                        result.below_threshold += 1
                        tier = self._derive_tier_label(score)
                        logger.debug(
                            f"Below threshold: {job.company} - {job.title} "
                            f"(score: {score}, threshold: {score_threshold})"
                        )
                        self._log(f"[score_reject] ({job_index}/{len(filtered_jobs)}) {job.company} | {job.title} | Score: {score} ({tier}) - below threshold")
                        continue

                    # Create and insert document using repository
                    doc = self.create_job_document(job, source_name, score, rationale or "")
                    insert_result = repo.insert_one(doc)

                    logger.info(
                        f"Ingested: {job.company} - {job.title} "
                        f"(score: {score}, tier: {doc['tier']})"
                    )
                    self._log(f"[score_accept] ({job_index}/{len(filtered_jobs)}) {job.company} | {job.title} | Score: {score} ({doc['tier']}) - ingested")

                    result.ingested += 1
                    result.ingested_jobs.append({
                        "job_id": str(insert_result.upserted_id),
                        "title": job.title,
                        "company": job.company,
                        "score": score,
                        "tier": doc["tier"],
                    })

                except Exception as e:
                    logger.error(f"Error processing job {job.company} - {job.title}: {e}")
                    self._log(f"[score_error] ({job_index}/{len(filtered_jobs)}) {job.company} | {job.title} - error: {str(e)}")
                    result.errors += 1

            # Update state after successful run
            if result.ingested > 0 or result.duplicates_skipped > 0:
                self.update_last_fetch_timestamp(
                    source=source_name,
                    timestamp=datetime.utcnow(),
                    stats={
                        "fetched": result.fetched,
                        "ingested": result.ingested,
                        "duplicates_skipped": result.duplicates_skipped,
                        "below_threshold": result.below_threshold,
                    },
                )

        except Exception as e:
            logger.exception(f"Ingestion failed for {source_name}: {e}")
            result.success = False
            result.error_message = str(e)
            self._log(f"[ingest_error] Ingestion failed: {str(e)}")

        # Calculate duration
        end_time = datetime.utcnow()
        result.duration_ms = int((end_time - start_time).total_seconds() * 1000)

        logger.info(
            f"Ingestion complete for {source_name}: "
            f"fetched={result.fetched}, ingested={result.ingested}, "
            f"duplicates={result.duplicates_skipped}, below_threshold={result.below_threshold}, "
            f"errors={result.errors}, duration={result.duration_ms}ms"
        )
        self._log(
            f"[ingest_summary] Fetched={result.fetched}, Ingested={result.ingested}, "
            f"Dupes={result.duplicates_skipped}, BelowThreshold={result.below_threshold}, "
            f"Errors={result.errors}"
        )

        return result

    def _derive_tier_label(self, score: Optional[int]) -> str:
        """Helper to derive tier label for logging."""
        if score is None:
            return "N/A"
        if score >= 80:
            return "A"
        elif score >= 60:
            return "B"
        elif score >= 40:
            return "C"
        else:
            return "D"
