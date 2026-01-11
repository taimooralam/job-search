"""
Application Outcome Tracker (Phase 7).

Tracks application outcomes and enables annotation effectiveness analysis.

Key Features:
- Per-job outcome tracking with timestamps
- Conversion metrics calculation
- Annotation profile correlation

Usage:
    from src.analytics.outcome_tracker import OutcomeTracker

    tracker = OutcomeTracker()

    # Update outcome for a job
    outcome = tracker.update_outcome(job_id, status="applied", applied_via="linkedin")

    # Get effectiveness report
    report = tracker.get_effectiveness_report(date_range_days=90)
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import MongoClient
from pymongo.database import Database

from src.common.annotation_types import ApplicationOutcome
from src.common.config import Config
from src.common.repositories import get_job_repository, JobRepositoryInterface

logger = logging.getLogger(__name__)


# Valid outcome status values
VALID_STATUSES = {
    "not_applied",
    "applied",
    "response_received",
    "screening_scheduled",
    "interview_scheduled",
    "interviewing",
    "offer_received",
    "offer_accepted",
    "rejected",
    "withdrawn",
}

# Status to timestamp field mapping
STATUS_TIMESTAMP_MAP = {
    "applied": "applied_at",
    "response_received": "response_at",
    "screening_scheduled": "screening_at",
    "interview_scheduled": "interview_at",
    "interviewing": "interview_at",
    "offer_received": "offer_at",
}


class OutcomeTracker:
    """
    Tracks and analyzes application outcomes.

    Enables measuring annotation effectiveness:
    - Response rate by annotation density
    - Interview rate by gap count
    - Offer rate by core_strength count
    """

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        db_name: str = "jobs",
        job_repository: Optional[JobRepositoryInterface] = None,
    ):
        """
        Initialize the outcome tracker.

        Args:
            mongodb_uri: MongoDB connection URI (deprecated, use job_repository)
            db_name: Database name (deprecated, use job_repository)
            job_repository: Optional job repository for level-2 operations
        """
        self._job_repository = job_repository

    def _get_job_repository(self) -> JobRepositoryInterface:
        """Get job repository, using singleton if not provided."""
        if self._job_repository is not None:
            return self._job_repository
        return get_job_repository()

    def get_job_outcome(self, job_id: str) -> Optional[ApplicationOutcome]:
        """
        Get current application outcome for a job.

        Args:
            job_id: MongoDB job document ID (ObjectId string)

        Returns:
            ApplicationOutcome if exists, None otherwise
        """
        try:
            object_id = ObjectId(job_id)
            repo = self._get_job_repository()
            job = repo.find_one({"_id": object_id})
            if not job:
                return None

            outcome = job.get("application_outcome")
            if outcome:
                return outcome

            # Return default outcome
            return self._create_default_outcome()

        except Exception as e:
            logger.error(f"Failed to get outcome for job {job_id}: {e}")
            return None

    def update_outcome(
        self,
        job_id: str,
        status: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[ApplicationOutcome]:
        """
        Update application outcome for a job.

        Args:
            job_id: MongoDB job document ID
            status: New outcome status (optional)
            **kwargs: Additional fields (applied_via, notes, etc.)

        Returns:
            Updated outcome document or None on error
        """
        try:
            object_id = ObjectId(job_id)
            repo = self._get_job_repository()

            # Get current job
            job = repo.find_one({"_id": object_id})
            if not job:
                logger.error(f"Job {job_id} not found")
                return None

            # Get current outcome or initialize
            outcome: Dict[str, Any] = job.get("application_outcome") or self._create_default_outcome()
            now = datetime.utcnow().isoformat()

            # Update status if provided
            if status:
                if status not in VALID_STATUSES:
                    logger.warning(f"Invalid status: {status}. Using 'not_applied'")
                    status = "not_applied"
                outcome["status"] = status

                # Set appropriate timestamp based on status
                if status in STATUS_TIMESTAMP_MAP:
                    field = STATUS_TIMESTAMP_MAP[status]
                    if not outcome.get(field):  # Don't overwrite existing
                        outcome[field] = now

                # Set final_status_at for terminal statuses
                if status in {"offer_accepted", "rejected", "withdrawn"}:
                    outcome["final_status_at"] = now

            # Update any additional fields
            allowed_fields = {
                "applied_via",
                "response_type",
                "interview_rounds",
                "offer_details",
                "notes",
            }
            for key, value in kwargs.items():
                if key in allowed_fields:
                    outcome[key] = value

            # Calculate derived metrics
            outcome = self._calculate_metrics(outcome)

            # Save to database
            result = repo.update_one(
                {"_id": object_id},
                {"$set": {"application_outcome": outcome}},
            )

            if result.modified_count > 0 or result.matched_count > 0:
                logger.info(f"Updated outcome for job {job_id}: status={outcome.get('status')}")

                # Update analytics collection
                self._update_analytics(job_id, job, outcome)

                return outcome
            else:
                logger.error(f"Failed to update outcome for job {job_id}")
                return None

        except Exception as e:
            logger.error(f"Error updating outcome for job {job_id}: {e}")
            return None

    def get_effectiveness_report(
        self,
        date_range_days: int = 90,
    ) -> Dict[str, Any]:
        """
        Generate annotation effectiveness report.

        Args:
            date_range_days: Number of days to include (default 90)

        Returns:
            Report with conversion rates by annotation profile
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=date_range_days)

            # Aggregate outcomes by annotation profile
            pipeline = [
                # Match jobs with outcomes and within date range
                {
                    "$match": {
                        "application_outcome.status": {"$ne": "not_applied"},
                        "updatedAt": {"$gte": cutoff_date},
                    }
                },
                # Project annotation counts and outcome data
                {
                    "$project": {
                        "annotation_count": {
                            "$size": {"$ifNull": ["$jd_annotations.annotations", []]}
                        },
                        "core_strength_count": {
                            "$size": {
                                "$filter": {
                                    "input": {
                                        "$ifNull": ["$jd_annotations.annotations", []]
                                    },
                                    "as": "a",
                                    "cond": {"$eq": ["$$a.relevance", "core_strength"]},
                                }
                            }
                        },
                        "gap_count": {"$ifNull": ["$jd_annotations.gap_count", 0]},
                        "outcome": "$application_outcome",
                    }
                },
                # Group by annotation density bucket
                {
                    "$group": {
                        "_id": {
                            "annotation_bucket": {
                                "$switch": {
                                    "branches": [
                                        {
                                            "case": {"$gte": ["$annotation_count", 10]},
                                            "then": "high",
                                        },
                                        {
                                            "case": {"$gte": ["$annotation_count", 5]},
                                            "then": "medium",
                                        },
                                    ],
                                    "default": "low",
                                }
                            }
                        },
                        "total": {"$sum": 1},
                        "responses": {
                            "$sum": {
                                "$cond": [
                                    {"$ne": ["$outcome.response_at", None]},
                                    1,
                                    0,
                                ]
                            }
                        },
                        "interviews": {
                            "$sum": {
                                "$cond": [
                                    {"$ne": ["$outcome.interview_at", None]},
                                    1,
                                    0,
                                ]
                            }
                        },
                        "offers": {
                            "$sum": {
                                "$cond": [{"$ne": ["$outcome.offer_at", None]}, 1, 0]
                            }
                        },
                    }
                },
            ]

            repo = self._get_job_repository()
            results = repo.aggregate(pipeline)
            return self._format_effectiveness_report(results, date_range_days)

        except Exception as e:
            logger.error(f"Failed to generate effectiveness report: {e}")
            return {
                "success": False,
                "error": str(e),
                "date_range_days": date_range_days,
            }

    def get_conversion_funnel(self, date_range_days: int = 90) -> Dict[str, Any]:
        """
        Get application funnel metrics.

        Returns counts at each stage: applied -> response -> interview -> offer
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=date_range_days)

            # Count applications at each stage
            pipeline = [
                {
                    "$match": {
                        "application_outcome.status": {"$ne": "not_applied"},
                        "updatedAt": {"$gte": cutoff_date},
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "applied": {"$sum": 1},
                        "responses": {
                            "$sum": {
                                "$cond": [
                                    {"$ne": ["$application_outcome.response_at", None]},
                                    1,
                                    0,
                                ]
                            }
                        },
                        "interviews": {
                            "$sum": {
                                "$cond": [
                                    {"$ne": ["$application_outcome.interview_at", None]},
                                    1,
                                    0,
                                ]
                            }
                        },
                        "offers": {
                            "$sum": {
                                "$cond": [
                                    {"$ne": ["$application_outcome.offer_at", None]},
                                    1,
                                    0,
                                ]
                            }
                        },
                        "avg_days_to_response": {
                            "$avg": "$application_outcome.days_to_response"
                        },
                        "avg_days_to_interview": {
                            "$avg": "$application_outcome.days_to_interview"
                        },
                    }
                },
            ]

            repo = self._get_job_repository()
            results = repo.aggregate(pipeline)

            if not results:
                return {
                    "funnel": {
                        "applied": 0,
                        "responses": 0,
                        "interviews": 0,
                        "offers": 0,
                    },
                    "conversion_rates": {
                        "response_rate": 0.0,
                        "interview_rate": 0.0,
                        "offer_rate": 0.0,
                    },
                    "avg_days": {
                        "to_response": None,
                        "to_interview": None,
                    },
                    "date_range_days": date_range_days,
                }

            data = results[0]
            applied = data.get("applied", 0) or 1  # Avoid division by zero

            return {
                "funnel": {
                    "applied": data.get("applied", 0),
                    "responses": data.get("responses", 0),
                    "interviews": data.get("interviews", 0),
                    "offers": data.get("offers", 0),
                },
                "conversion_rates": {
                    "response_rate": round((data.get("responses", 0) / applied) * 100, 1),
                    "interview_rate": round((data.get("interviews", 0) / applied) * 100, 1),
                    "offer_rate": round((data.get("offers", 0) / applied) * 100, 1),
                },
                "avg_days": {
                    "to_response": round(data.get("avg_days_to_response") or 0, 1)
                    if data.get("avg_days_to_response")
                    else None,
                    "to_interview": round(data.get("avg_days_to_interview") or 0, 1)
                    if data.get("avg_days_to_interview")
                    else None,
                },
                "date_range_days": date_range_days,
            }

        except Exception as e:
            logger.error(f"Failed to get conversion funnel: {e}")
            return {"success": False, "error": str(e)}

    def _create_default_outcome(self) -> Dict[str, Any]:
        """Create a default outcome structure."""
        return {
            "status": "not_applied",
            "applied_at": None,
            "applied_via": None,
            "response_at": None,
            "response_type": None,
            "screening_at": None,
            "interview_at": None,
            "interview_rounds": 0,
            "offer_at": None,
            "offer_details": None,
            "final_status_at": None,
            "notes": None,
            "days_to_response": None,
            "days_to_interview": None,
            "days_to_offer": None,
        }

    def _calculate_metrics(self, outcome: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate derived metrics for outcome.

        Computes days_to_response, days_to_interview, days_to_offer
        based on timestamps.
        """
        applied_at = outcome.get("applied_at")
        if not applied_at:
            return outcome

        try:
            applied_dt = datetime.fromisoformat(applied_at.replace("Z", "+00:00"))

            # Days to response
            response_at = outcome.get("response_at")
            if response_at:
                response_dt = datetime.fromisoformat(response_at.replace("Z", "+00:00"))
                outcome["days_to_response"] = (response_dt - applied_dt).days

            # Days to interview
            interview_at = outcome.get("interview_at")
            if interview_at:
                interview_dt = datetime.fromisoformat(interview_at.replace("Z", "+00:00"))
                outcome["days_to_interview"] = (interview_dt - applied_dt).days

            # Days to offer
            offer_at = outcome.get("offer_at")
            if offer_at:
                offer_dt = datetime.fromisoformat(offer_at.replace("Z", "+00:00"))
                outcome["days_to_offer"] = (offer_dt - applied_dt).days

        except Exception as e:
            logger.warning(f"Failed to calculate metrics: {e}")

        return outcome

    def _update_analytics(
        self,
        job_id: str,
        job: Dict[str, Any],
        outcome: Dict[str, Any],
    ) -> None:
        """
        Update the analytics collection for aggregation queries.

        Creates/updates a document in annotation_analytics collection
        that captures the annotation profile + outcome snapshot.
        """
        try:
            # Build annotation profile
            jd_annotations = job.get("jd_annotations") or {}
            annotations = jd_annotations.get("annotations", [])

            # Count by relevance type
            core_strength_count = sum(
                1 for a in annotations if a.get("relevance") == "core_strength"
            )
            gap_count = sum(1 for a in annotations if a.get("relevance") == "gap")
            reframe_count = sum(1 for a in annotations if a.get("has_reframe"))

            # Calculate section coverage
            section_summaries = jd_annotations.get("section_summaries", {})
            if section_summaries:
                coverages = [
                    s.get("coverage_percentage", 0)
                    for s in section_summaries.values()
                ]
                section_coverage = sum(coverages) / len(coverages) if coverages else 0
            else:
                section_coverage = 0

            analytics_doc = {
                "_id": job_id,
                "annotation_profile": {
                    "annotation_count": len(annotations),
                    "core_strength_count": core_strength_count,
                    "gap_count": gap_count,
                    "reframe_count": reframe_count,
                    "section_coverage": section_coverage,
                },
                "outcome_snapshot": {
                    "status": outcome.get("status"),
                    "applied_at": outcome.get("applied_at"),
                    "response_at": outcome.get("response_at"),
                    "interview_at": outcome.get("interview_at"),
                    "offer_at": outcome.get("offer_at"),
                },
                "computed_at": datetime.utcnow().isoformat(),
            }

            # Upsert to analytics collection (separate from level-2)
            # Uses direct MongoDB access since annotation_analytics is a separate utility collection
            config = Config()
            client = MongoClient(config.get("MONGODB_URI"))
            db = client["jobs"]
            analytics_collection = db["annotation_analytics"]
            analytics_collection.update_one(
                {"_id": job_id},
                {"$set": analytics_doc},
                upsert=True,
            )

        except Exception as e:
            # Don't fail main operation if analytics update fails
            logger.warning(f"Failed to update analytics for job {job_id}: {e}")

    def _format_effectiveness_report(
        self,
        results: List[Dict[str, Any]],
        date_range_days: int,
    ) -> Dict[str, Any]:
        """Format aggregation results into effectiveness report."""
        by_bucket = {}
        total_applied = 0
        total_responses = 0
        total_interviews = 0
        total_offers = 0

        for row in results:
            bucket = row["_id"]["annotation_bucket"]
            total = row.get("total", 0)
            responses = row.get("responses", 0)
            interviews = row.get("interviews", 0)
            offers = row.get("offers", 0)

            by_bucket[bucket] = {
                "total": total,
                "responses": responses,
                "interviews": interviews,
                "offers": offers,
                "response_rate": round((responses / total * 100), 1) if total > 0 else 0,
                "interview_rate": round((interviews / total * 100), 1) if total > 0 else 0,
                "offer_rate": round((offers / total * 100), 1) if total > 0 else 0,
            }

            total_applied += total
            total_responses += responses
            total_interviews += interviews
            total_offers += offers

        return {
            "success": True,
            "date_range_days": date_range_days,
            "summary": {
                "total_applied": total_applied,
                "total_responses": total_responses,
                "total_interviews": total_interviews,
                "total_offers": total_offers,
                "response_rate": round((total_responses / total_applied * 100), 1)
                if total_applied > 0
                else 0,
                "interview_rate": round((total_interviews / total_applied * 100), 1)
                if total_applied > 0
                else 0,
                "offer_rate": round((total_offers / total_applied * 100), 1)
                if total_applied > 0
                else 0,
            },
            "by_annotation_density": by_bucket,
            "recommendation": self._generate_recommendation(by_bucket),
        }

    def _generate_recommendation(self, by_bucket: Dict[str, Any]) -> str:
        """Generate recommendation based on effectiveness data."""
        high = by_bucket.get("high", {})
        low = by_bucket.get("low", {})

        high_response = high.get("response_rate", 0)
        low_response = low.get("response_rate", 0)

        if high_response > low_response * 1.5:
            return "High annotation density correlates with better response rates. Continue annotating JDs thoroughly."
        elif low_response > high_response:
            return "Lower annotation density shows comparable or better results. Consider focusing on quality over quantity."
        elif not high and not low:
            return "Not enough data to generate recommendations. Continue tracking outcomes."
        else:
            return "No significant correlation found between annotation density and outcomes yet."
