"""
Annotation Tracking Service - P2 Implementation.

Provides:
1. Persona A/B Testing Framework - Track which persona configurations lead to outcomes
2. Annotation Outcome Tracking - Link annotations to application outcomes
3. Annotation Effectiveness Analytics - Analyze which annotations correlate with success

This service enables learning from past applications to improve future personalization.
"""

import hashlib
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ApplicationOutcome(str, Enum):
    """Application outcome stages for tracking."""
    PENDING = "pending"           # Application submitted, awaiting response
    REJECTED = "rejected"         # Application rejected
    SCREENING = "screening"       # Passed to screening call
    INTERVIEW = "interview"       # Invited to interview
    FINAL_ROUND = "final_round"   # Reached final interview round
    OFFER = "offer"               # Received offer
    ACCEPTED = "accepted"         # Offer accepted
    WITHDRAWN = "withdrawn"       # Candidate withdrew


# Outcome scores for effectiveness calculation
OUTCOME_SCORES: Dict[ApplicationOutcome, float] = {
    ApplicationOutcome.PENDING: 0.0,
    ApplicationOutcome.REJECTED: 0.0,
    ApplicationOutcome.SCREENING: 0.3,
    ApplicationOutcome.INTERVIEW: 0.5,
    ApplicationOutcome.FINAL_ROUND: 0.7,
    ApplicationOutcome.OFFER: 1.0,
    ApplicationOutcome.ACCEPTED: 1.0,
    ApplicationOutcome.WITHDRAWN: 0.2,  # Partial credit - they were interested
}


@dataclass
class PersonaVariant:
    """
    A specific persona configuration used for an application.

    This captures the "experiment" side of A/B testing - what persona
    configuration was used for this specific application.
    """

    variant_id: str                           # Unique ID for this variant
    identity_keywords: List[str] = field(default_factory=list)  # Core identity terms used
    passion_keywords: List[str] = field(default_factory=list)   # Passion terms used
    core_strength_keywords: List[str] = field(default_factory=list)  # Strengths highlighted
    persona_summary: str = ""                 # The synthesized persona text

    # Generation metadata
    generation_timestamp: str = ""
    model_used: str = ""

    @classmethod
    def from_annotations(
        cls,
        jd_annotations: Dict[str, Any],
        persona_summary: str = "",
        model: str = "",
    ) -> "PersonaVariant":
        """Create a PersonaVariant from JD annotations."""
        annotations = jd_annotations.get("annotations", [])

        identity_keywords = []
        passion_keywords = []
        core_strength_keywords = []

        for ann in annotations:
            if not ann.get("is_active", True):
                continue

            keyword = ann.get("matching_skill") or ""
            identity = ann.get("identity", "")
            passion = ann.get("passion", "")
            relevance = ann.get("relevance", "")

            if identity in ("core_identity", "strong_identity"):
                identity_keywords.append(keyword)
            if passion in ("love_it", "enjoy"):
                passion_keywords.append(keyword)
            if relevance in ("core_strength", "extremely_relevant"):
                core_strength_keywords.append(keyword)

        # Create deterministic variant ID from configuration
        config_str = f"{sorted(identity_keywords)}{sorted(passion_keywords)}{sorted(core_strength_keywords)}"
        variant_id = hashlib.md5(config_str.encode()).hexdigest()[:12]

        return cls(
            variant_id=variant_id,
            identity_keywords=identity_keywords,
            passion_keywords=passion_keywords,
            core_strength_keywords=core_strength_keywords,
            persona_summary=persona_summary,
            generation_timestamp=datetime.now(timezone.utc).isoformat(),
            model_used=model,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        return {
            "variant_id": self.variant_id,
            "identity_keywords": self.identity_keywords,
            "passion_keywords": self.passion_keywords,
            "core_strength_keywords": self.core_strength_keywords,
            "persona_summary": self.persona_summary,
            "generation_timestamp": self.generation_timestamp,
            "model_used": self.model_used,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaVariant":
        """Create from dictionary (MongoDB document)."""
        return cls(
            variant_id=data.get("variant_id", ""),
            identity_keywords=data.get("identity_keywords", []),
            passion_keywords=data.get("passion_keywords", []),
            core_strength_keywords=data.get("core_strength_keywords", []),
            persona_summary=data.get("persona_summary", ""),
            generation_timestamp=data.get("generation_timestamp", ""),
            model_used=data.get("model_used", ""),
        )


@dataclass
class AnnotationOutcome:
    """
    Tracks the outcome of a specific annotation usage.

    Links individual annotations to application outcomes for
    effectiveness analysis.
    """

    annotation_id: str                        # Unique annotation ID
    job_id: str                               # Job this was used for
    keyword: str                              # The keyword/skill annotated
    relevance: str = ""                       # core_strength, extremely_relevant, etc.
    requirement_type: str = ""                # must_have, nice_to_have, neutral
    passion: str = ""                         # love_it, enjoy, neutral, avoid
    identity: str = ""                        # core_identity, strong_identity, etc.

    # Placement tracking (from KeywordPlacementValidator)
    found_in_headline: bool = False
    found_in_narrative: bool = False
    found_in_competencies: bool = False
    found_in_first_role: bool = False
    placement_score: int = 0

    # Outcome tracking
    outcome: ApplicationOutcome = ApplicationOutcome.PENDING
    outcome_score: float = 0.0
    outcome_timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        return {
            "annotation_id": self.annotation_id,
            "job_id": self.job_id,
            "keyword": self.keyword,
            "relevance": self.relevance,
            "requirement_type": self.requirement_type,
            "passion": self.passion,
            "identity": self.identity,
            "found_in_headline": self.found_in_headline,
            "found_in_narrative": self.found_in_narrative,
            "found_in_competencies": self.found_in_competencies,
            "found_in_first_role": self.found_in_first_role,
            "placement_score": self.placement_score,
            "outcome": self.outcome.value,
            "outcome_score": self.outcome_score,
            "outcome_timestamp": self.outcome_timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnnotationOutcome":
        """Create from dictionary (MongoDB document)."""
        return cls(
            annotation_id=data.get("annotation_id", ""),
            job_id=data.get("job_id", ""),
            keyword=data.get("keyword", ""),
            relevance=data.get("relevance", ""),
            requirement_type=data.get("requirement_type", ""),
            passion=data.get("passion", ""),
            identity=data.get("identity", ""),
            found_in_headline=data.get("found_in_headline", False),
            found_in_narrative=data.get("found_in_narrative", False),
            found_in_competencies=data.get("found_in_competencies", False),
            found_in_first_role=data.get("found_in_first_role", False),
            placement_score=data.get("placement_score", 0),
            outcome=ApplicationOutcome(data.get("outcome", "pending")),
            outcome_score=data.get("outcome_score", 0.0),
            outcome_timestamp=data.get("outcome_timestamp", ""),
        )


@dataclass
class ApplicationTracking:
    """
    Complete tracking record for an application.

    Combines persona variant, annotation outcomes, and placement validation
    for comprehensive A/B testing and effectiveness analysis.
    """

    job_id: str
    company: str = ""
    title: str = ""

    # Persona A/B testing
    persona_variant: Optional[PersonaVariant] = None

    # Annotation outcomes
    annotation_outcomes: List[AnnotationOutcome] = field(default_factory=list)

    # Placement validation summary
    keyword_placement_score: int = 0
    must_have_coverage: int = 0
    identity_coverage: int = 0

    # ATS validation summary
    ats_score: int = 0

    # Overall outcome
    outcome: ApplicationOutcome = ApplicationOutcome.PENDING
    outcome_timestamp: str = ""

    # Timestamps
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def update_outcome(self, outcome: ApplicationOutcome) -> None:
        """Update the application outcome and propagate to annotations."""
        self.outcome = outcome
        self.outcome_timestamp = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.outcome_timestamp

        outcome_score = OUTCOME_SCORES.get(outcome, 0.0)
        for ann_outcome in self.annotation_outcomes:
            ann_outcome.outcome = outcome
            ann_outcome.outcome_score = outcome_score
            ann_outcome.outcome_timestamp = self.outcome_timestamp

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        return {
            "job_id": self.job_id,
            "company": self.company,
            "title": self.title,
            "persona_variant": self.persona_variant.to_dict() if self.persona_variant else None,
            "annotation_outcomes": [ao.to_dict() for ao in self.annotation_outcomes],
            "keyword_placement_score": self.keyword_placement_score,
            "must_have_coverage": self.must_have_coverage,
            "identity_coverage": self.identity_coverage,
            "ats_score": self.ats_score,
            "outcome": self.outcome.value,
            "outcome_timestamp": self.outcome_timestamp,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApplicationTracking":
        """Create from dictionary (MongoDB document)."""
        persona_data = data.get("persona_variant")
        persona_variant = PersonaVariant.from_dict(persona_data) if persona_data else None

        annotation_outcomes = [
            AnnotationOutcome.from_dict(ao)
            for ao in data.get("annotation_outcomes", [])
        ]

        return cls(
            job_id=data.get("job_id", ""),
            company=data.get("company", ""),
            title=data.get("title", ""),
            persona_variant=persona_variant,
            annotation_outcomes=annotation_outcomes,
            keyword_placement_score=data.get("keyword_placement_score", 0),
            must_have_coverage=data.get("must_have_coverage", 0),
            identity_coverage=data.get("identity_coverage", 0),
            ats_score=data.get("ats_score", 0),
            outcome=ApplicationOutcome(data.get("outcome", "pending")),
            outcome_timestamp=data.get("outcome_timestamp", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class AnnotationEffectivenessStats:
    """
    Aggregated statistics for annotation effectiveness analysis.

    Used to answer questions like:
    - Which identity keywords correlate with interviews?
    - Does passion alignment improve outcomes?
    - Which placement positions are most effective?
    """

    keyword: str
    total_uses: int = 0

    # Outcome counts
    interviews: int = 0
    offers: int = 0
    rejections: int = 0

    # Effectiveness scores
    interview_rate: float = 0.0      # interviews / total_uses
    offer_rate: float = 0.0          # offers / total_uses
    avg_outcome_score: float = 0.0   # Average outcome score

    # Placement correlation
    headline_interview_rate: float = 0.0   # Interview rate when in headline
    narrative_interview_rate: float = 0.0  # Interview rate when in narrative

    # Identity/passion correlation
    identity_interview_rate: float = 0.0   # Rate when marked as identity
    passion_interview_rate: float = 0.0    # Rate when marked as passion

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "keyword": self.keyword,
            "total_uses": self.total_uses,
            "interviews": self.interviews,
            "offers": self.offers,
            "rejections": self.rejections,
            "interview_rate": self.interview_rate,
            "offer_rate": self.offer_rate,
            "avg_outcome_score": self.avg_outcome_score,
            "headline_interview_rate": self.headline_interview_rate,
            "narrative_interview_rate": self.narrative_interview_rate,
            "identity_interview_rate": self.identity_interview_rate,
            "passion_interview_rate": self.passion_interview_rate,
        }


class AnnotationTrackingService:
    """
    Service for tracking annotation effectiveness and persona A/B testing.

    Provides methods to:
    1. Record application tracking data
    2. Update outcomes when application status changes
    3. Calculate effectiveness analytics
    4. Compare persona variants
    """

    def __init__(self, db=None, repository=None):
        """
        Initialize the tracking service.

        Args:
            db: MongoDB database instance (deprecated, use repository)
            repository: Optional annotation tracking repository
        """
        self._db = db
        self._repository = repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _get_repository(self):
        """Get the annotation tracking repository instance."""
        if self._repository is not None:
            return self._repository
        # Import here to avoid circular dependency
        from src.common.repositories import get_annotation_tracking_repository
        return get_annotation_tracking_repository()

    def create_tracking_record(
        self,
        job_id: str,
        company: str,
        title: str,
        jd_annotations: Optional[Dict[str, Any]] = None,
        keyword_placement_result: Optional[Dict[str, Any]] = None,
        ats_validation: Optional[Dict[str, Any]] = None,
        persona_summary: str = "",
        model: str = "",
    ) -> ApplicationTracking:
        """
        Create a tracking record for a new application.

        Args:
            job_id: Unique job identifier
            company: Company name
            title: Job title
            jd_annotations: JD annotations used for this application
            keyword_placement_result: Result from KeywordPlacementValidator
            ats_validation: Result from ATS validation
            persona_summary: Generated persona summary text
            model: Model used for generation

        Returns:
            ApplicationTracking record
        """
        # Create persona variant
        persona_variant = None
        if jd_annotations:
            persona_variant = PersonaVariant.from_annotations(
                jd_annotations, persona_summary, model
            )

        # Create annotation outcomes
        annotation_outcomes = []
        if jd_annotations:
            placements = keyword_placement_result.get("placements", []) if keyword_placement_result else []
            placement_map = {p.get("keyword", ""): p for p in placements}

            for ann in jd_annotations.get("annotations", []):
                if not ann.get("is_active", True):
                    continue

                # Note: Must handle empty suggested_keywords list - .get() returns [] if key exists
                suggested = ann.get("suggested_keywords") or []
                keyword = ann.get("matching_skill") or (suggested[0] if suggested else "")
                if not keyword:
                    continue

                placement = placement_map.get(keyword, {})

                annotation_outcomes.append(AnnotationOutcome(
                    annotation_id=ann.get("id", ""),
                    job_id=job_id,
                    keyword=keyword,
                    relevance=ann.get("relevance", ""),
                    requirement_type=ann.get("requirement_type", ""),
                    passion=ann.get("passion", ""),
                    identity=ann.get("identity", ""),
                    found_in_headline=placement.get("found_in_headline", False),
                    found_in_narrative=placement.get("found_in_narrative", False),
                    found_in_competencies=placement.get("found_in_competencies", False),
                    found_in_first_role=placement.get("found_in_first_role", False),
                    placement_score=placement.get("placement_score", 0),
                ))

        # Create tracking record
        tracking = ApplicationTracking(
            job_id=job_id,
            company=company,
            title=title,
            persona_variant=persona_variant,
            annotation_outcomes=annotation_outcomes,
            keyword_placement_score=keyword_placement_result.get("overall_score", 0) if keyword_placement_result else 0,
            must_have_coverage=keyword_placement_result.get("must_have_score", 0) if keyword_placement_result else 0,
            identity_coverage=keyword_placement_result.get("identity_score", 0) if keyword_placement_result else 0,
            ats_score=ats_validation.get("ats_score", 0) if ats_validation else 0,
        )

        # Persist if database available
        if self._db:
            self._save_tracking(tracking)

        self._logger.info(
            f"Created tracking record for {company}/{title} "
            f"(variant={persona_variant.variant_id if persona_variant else 'none'}, "
            f"annotations={len(annotation_outcomes)})"
        )

        return tracking

    def update_outcome(
        self,
        job_id: str,
        outcome: ApplicationOutcome,
    ) -> Optional[ApplicationTracking]:
        """
        Update the outcome for an application.

        Args:
            job_id: Job identifier
            outcome: New application outcome

        Returns:
            Updated ApplicationTracking or None if not found
        """
        tracking = self._load_tracking(job_id)
        if not tracking:
            self._logger.warning(f"No tracking record found for job_id={job_id}")
            return None

        tracking.update_outcome(outcome)

        if self._db:
            self._save_tracking(tracking)

        self._logger.info(f"Updated outcome for {job_id}: {outcome.value}")
        return tracking

    def calculate_keyword_effectiveness(
        self,
        min_uses: int = 3,
    ) -> List[AnnotationEffectivenessStats]:
        """
        Calculate effectiveness statistics for all keywords.

        Args:
            min_uses: Minimum uses to include in analysis

        Returns:
            List of AnnotationEffectivenessStats sorted by interview rate
        """
        if not self._db:
            self._logger.warning("No database - cannot calculate effectiveness")
            return []

        # Aggregate annotation outcomes
        keyword_data: Dict[str, Dict[str, Any]] = {}

        for tracking in self._load_all_tracking():
            for ann in tracking.annotation_outcomes:
                if ann.keyword not in keyword_data:
                    keyword_data[ann.keyword] = {
                        "total": 0,
                        "interviews": 0,
                        "offers": 0,
                        "rejections": 0,
                        "outcome_scores": [],
                        "headline_interviews": 0,
                        "headline_total": 0,
                        "narrative_interviews": 0,
                        "narrative_total": 0,
                        "identity_interviews": 0,
                        "identity_total": 0,
                        "passion_interviews": 0,
                        "passion_total": 0,
                    }

                data = keyword_data[ann.keyword]
                data["total"] += 1
                data["outcome_scores"].append(ann.outcome_score)

                is_interview = ann.outcome in (
                    ApplicationOutcome.INTERVIEW,
                    ApplicationOutcome.FINAL_ROUND,
                    ApplicationOutcome.OFFER,
                    ApplicationOutcome.ACCEPTED,
                )

                if is_interview:
                    data["interviews"] += 1
                if ann.outcome in (ApplicationOutcome.OFFER, ApplicationOutcome.ACCEPTED):
                    data["offers"] += 1
                if ann.outcome == ApplicationOutcome.REJECTED:
                    data["rejections"] += 1

                # Track placement correlations
                if ann.found_in_headline:
                    data["headline_total"] += 1
                    if is_interview:
                        data["headline_interviews"] += 1

                if ann.found_in_narrative:
                    data["narrative_total"] += 1
                    if is_interview:
                        data["narrative_interviews"] += 1

                # Track identity/passion correlations
                if ann.identity in ("core_identity", "strong_identity"):
                    data["identity_total"] += 1
                    if is_interview:
                        data["identity_interviews"] += 1

                if ann.passion in ("love_it", "enjoy"):
                    data["passion_total"] += 1
                    if is_interview:
                        data["passion_interviews"] += 1

        # Calculate stats
        stats = []
        for keyword, data in keyword_data.items():
            if data["total"] < min_uses:
                continue

            stats.append(AnnotationEffectivenessStats(
                keyword=keyword,
                total_uses=data["total"],
                interviews=data["interviews"],
                offers=data["offers"],
                rejections=data["rejections"],
                interview_rate=data["interviews"] / data["total"] if data["total"] > 0 else 0,
                offer_rate=data["offers"] / data["total"] if data["total"] > 0 else 0,
                avg_outcome_score=sum(data["outcome_scores"]) / len(data["outcome_scores"]) if data["outcome_scores"] else 0,
                headline_interview_rate=data["headline_interviews"] / data["headline_total"] if data["headline_total"] > 0 else 0,
                narrative_interview_rate=data["narrative_interviews"] / data["narrative_total"] if data["narrative_total"] > 0 else 0,
                identity_interview_rate=data["identity_interviews"] / data["identity_total"] if data["identity_total"] > 0 else 0,
                passion_interview_rate=data["passion_interviews"] / data["passion_total"] if data["passion_total"] > 0 else 0,
            ))

        # Sort by interview rate
        stats.sort(key=lambda s: s.interview_rate, reverse=True)
        return stats

    def compare_persona_variants(self) -> Dict[str, Any]:
        """
        Compare effectiveness of different persona variants.

        Returns:
            Dict with variant comparison data
        """
        if not self._db:
            return {"error": "No database available"}

        variant_data: Dict[str, Dict[str, Any]] = {}

        for tracking in self._load_all_tracking():
            if not tracking.persona_variant:
                continue

            variant_id = tracking.persona_variant.variant_id
            if variant_id not in variant_data:
                variant_data[variant_id] = {
                    "variant": tracking.persona_variant.to_dict(),
                    "applications": 0,
                    "interviews": 0,
                    "offers": 0,
                    "outcome_scores": [],
                }

            data = variant_data[variant_id]
            data["applications"] += 1
            data["outcome_scores"].append(OUTCOME_SCORES.get(tracking.outcome, 0))

            if tracking.outcome in (
                ApplicationOutcome.INTERVIEW,
                ApplicationOutcome.FINAL_ROUND,
                ApplicationOutcome.OFFER,
                ApplicationOutcome.ACCEPTED,
            ):
                data["interviews"] += 1

            if tracking.outcome in (ApplicationOutcome.OFFER, ApplicationOutcome.ACCEPTED):
                data["offers"] += 1

        # Calculate rates
        results = []
        for variant_id, data in variant_data.items():
            results.append({
                "variant_id": variant_id,
                "identity_keywords": data["variant"].get("identity_keywords", []),
                "passion_keywords": data["variant"].get("passion_keywords", []),
                "applications": data["applications"],
                "interview_rate": data["interviews"] / data["applications"] if data["applications"] > 0 else 0,
                "offer_rate": data["offers"] / data["applications"] if data["applications"] > 0 else 0,
                "avg_outcome_score": sum(data["outcome_scores"]) / len(data["outcome_scores"]) if data["outcome_scores"] else 0,
            })

        # Sort by interview rate
        results.sort(key=lambda r: r["interview_rate"], reverse=True)

        return {
            "variants": results,
            "total_variants": len(results),
            "best_variant": results[0] if results else None,
        }

    def get_placement_effectiveness(self) -> Dict[str, Any]:
        """
        Analyze which keyword placements correlate with better outcomes.

        Returns:
            Dict with placement analysis
        """
        if not self._db:
            return {"error": "No database available"}

        placements = {
            "headline": {"total": 0, "interviews": 0},
            "narrative": {"total": 0, "interviews": 0},
            "competencies": {"total": 0, "interviews": 0},
            "first_role": {"total": 0, "interviews": 0},
        }

        for tracking in self._load_all_tracking():
            is_interview = tracking.outcome in (
                ApplicationOutcome.INTERVIEW,
                ApplicationOutcome.FINAL_ROUND,
                ApplicationOutcome.OFFER,
                ApplicationOutcome.ACCEPTED,
            )

            for ann in tracking.annotation_outcomes:
                if ann.found_in_headline:
                    placements["headline"]["total"] += 1
                    if is_interview:
                        placements["headline"]["interviews"] += 1

                if ann.found_in_narrative:
                    placements["narrative"]["total"] += 1
                    if is_interview:
                        placements["narrative"]["interviews"] += 1

                if ann.found_in_competencies:
                    placements["competencies"]["total"] += 1
                    if is_interview:
                        placements["competencies"]["interviews"] += 1

                if ann.found_in_first_role:
                    placements["first_role"]["total"] += 1
                    if is_interview:
                        placements["first_role"]["interviews"] += 1

        return {
            "headline": {
                "total": placements["headline"]["total"],
                "interview_rate": (
                    placements["headline"]["interviews"] / placements["headline"]["total"]
                    if placements["headline"]["total"] > 0 else 0
                ),
            },
            "narrative": {
                "total": placements["narrative"]["total"],
                "interview_rate": (
                    placements["narrative"]["interviews"] / placements["narrative"]["total"]
                    if placements["narrative"]["total"] > 0 else 0
                ),
            },
            "competencies": {
                "total": placements["competencies"]["total"],
                "interview_rate": (
                    placements["competencies"]["interviews"] / placements["competencies"]["total"]
                    if placements["competencies"]["total"] > 0 else 0
                ),
            },
            "first_role": {
                "total": placements["first_role"]["total"],
                "interview_rate": (
                    placements["first_role"]["interviews"] / placements["first_role"]["total"]
                    if placements["first_role"]["total"] > 0 else 0
                ),
            },
        }

    # ==================== Persistence Methods ====================

    def _save_tracking(self, tracking: ApplicationTracking) -> None:
        """Save tracking record to database."""
        try:
            repo = self._get_repository()
            repo.upsert_tracking(tracking.job_id, tracking.to_dict())
        except Exception as e:
            self._logger.warning(f"Error saving tracking (no repository?): {e}")

    def _load_tracking(self, job_id: str) -> Optional[ApplicationTracking]:
        """Load tracking record from database."""
        try:
            repo = self._get_repository()
            doc = repo.find_by_job_id(job_id)
            if doc:
                return ApplicationTracking.from_dict(doc)
            return None
        except Exception as e:
            self._logger.warning(f"Error loading tracking (no repository?): {e}")
            return None

    def _load_all_tracking(self) -> List[ApplicationTracking]:
        """Load all tracking records from database."""
        try:
            repo = self._get_repository()
            return [ApplicationTracking.from_dict(doc) for doc in repo.find_all()]
        except Exception as e:
            self._logger.warning(f"Error loading all tracking (no repository?): {e}")
            return []
