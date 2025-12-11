"""
Tests for Annotation Tracking Service (P2 implementation).

Tests:
1. PersonaVariant creation from annotations
2. ApplicationTracking record creation
3. Outcome updates and propagation
4. Effectiveness calculations (without database)
"""

import pytest
from datetime import datetime

from src.services.annotation_tracking_service import (
    AnnotationTrackingService,
    PersonaVariant,
    AnnotationOutcome,
    ApplicationTracking,
    ApplicationOutcome,
    AnnotationEffectivenessStats,
    OUTCOME_SCORES,
)


class TestPersonaVariant:
    """Tests for PersonaVariant dataclass."""

    def test_from_annotations_extracts_identity_keywords(self):
        """Should extract identity keywords from annotations."""
        jd_annotations = {
            "annotations": [
                {"matching_skill": "Python", "identity": "core_identity", "is_active": True},
                {"matching_skill": "Leadership", "identity": "strong_identity", "is_active": True},
                {"matching_skill": "AWS", "identity": "peripheral", "is_active": True},
            ]
        }

        variant = PersonaVariant.from_annotations(jd_annotations)

        assert "Python" in variant.identity_keywords
        assert "Leadership" in variant.identity_keywords
        assert "AWS" not in variant.identity_keywords

    def test_from_annotations_extracts_passion_keywords(self):
        """Should extract passion keywords from annotations."""
        jd_annotations = {
            "annotations": [
                {"matching_skill": "Machine Learning", "passion": "love_it", "is_active": True},
                {"matching_skill": "Data Science", "passion": "enjoy", "is_active": True},
                {"matching_skill": "Testing", "passion": "neutral", "is_active": True},
            ]
        }

        variant = PersonaVariant.from_annotations(jd_annotations)

        assert "Machine Learning" in variant.passion_keywords
        assert "Data Science" in variant.passion_keywords
        assert "Testing" not in variant.passion_keywords

    def test_from_annotations_extracts_core_strengths(self):
        """Should extract core strength keywords from annotations."""
        jd_annotations = {
            "annotations": [
                {"matching_skill": "Python", "relevance": "core_strength", "is_active": True},
                {"matching_skill": "AWS", "relevance": "extremely_relevant", "is_active": True},
                {"matching_skill": "Go", "relevance": "relevant", "is_active": True},
            ]
        }

        variant = PersonaVariant.from_annotations(jd_annotations)

        assert "Python" in variant.core_strength_keywords
        assert "AWS" in variant.core_strength_keywords
        assert "Go" not in variant.core_strength_keywords

    def test_from_annotations_skips_inactive(self):
        """Should skip inactive annotations."""
        jd_annotations = {
            "annotations": [
                {"matching_skill": "Python", "identity": "core_identity", "is_active": True},
                {"matching_skill": "Java", "identity": "core_identity", "is_active": False},
            ]
        }

        variant = PersonaVariant.from_annotations(jd_annotations)

        assert "Python" in variant.identity_keywords
        assert "Java" not in variant.identity_keywords

    def test_variant_id_is_deterministic(self):
        """Same configuration should produce same variant_id."""
        jd_annotations = {
            "annotations": [
                {"matching_skill": "Python", "identity": "core_identity", "is_active": True},
            ]
        }

        variant1 = PersonaVariant.from_annotations(jd_annotations)
        variant2 = PersonaVariant.from_annotations(jd_annotations)

        assert variant1.variant_id == variant2.variant_id

    def test_to_dict_and_from_dict_roundtrip(self):
        """Should survive dict serialization roundtrip."""
        variant = PersonaVariant(
            variant_id="abc123",
            identity_keywords=["Python", "Leadership"],
            passion_keywords=["ML"],
            core_strength_keywords=["Python"],
            persona_summary="Test persona",
            model_used="test-model",
        )

        data = variant.to_dict()
        restored = PersonaVariant.from_dict(data)

        assert restored.variant_id == variant.variant_id
        assert restored.identity_keywords == variant.identity_keywords
        assert restored.passion_keywords == variant.passion_keywords
        assert restored.persona_summary == variant.persona_summary


class TestAnnotationOutcome:
    """Tests for AnnotationOutcome dataclass."""

    def test_to_dict_includes_all_fields(self):
        """Should include all fields in dict output."""
        outcome = AnnotationOutcome(
            annotation_id="ann_123",
            job_id="job_456",
            keyword="Python",
            relevance="core_strength",
            requirement_type="must_have",
            passion="love_it",
            identity="core_identity",
            found_in_headline=True,
            found_in_narrative=True,
            placement_score=70,
        )

        data = outcome.to_dict()

        assert data["annotation_id"] == "ann_123"
        assert data["keyword"] == "Python"
        assert data["found_in_headline"] is True
        assert data["placement_score"] == 70
        assert data["outcome"] == "pending"

    def test_from_dict_restores_outcome(self):
        """Should restore ApplicationOutcome enum correctly."""
        data = {
            "annotation_id": "ann_123",
            "job_id": "job_456",
            "keyword": "Python",
            "outcome": "interview",
            "outcome_score": 0.5,
        }

        outcome = AnnotationOutcome.from_dict(data)

        assert outcome.outcome == ApplicationOutcome.INTERVIEW
        assert outcome.outcome_score == 0.5


class TestApplicationTracking:
    """Tests for ApplicationTracking dataclass."""

    def test_update_outcome_propagates_to_annotations(self):
        """Should update all annotation outcomes when application outcome changes."""
        ann1 = AnnotationOutcome(
            annotation_id="ann_1", job_id="job_123", keyword="Python"
        )
        ann2 = AnnotationOutcome(
            annotation_id="ann_2", job_id="job_123", keyword="AWS"
        )

        tracking = ApplicationTracking(
            job_id="job_123",
            company="Test Corp",
            title="Engineer",
            annotation_outcomes=[ann1, ann2],
        )

        tracking.update_outcome(ApplicationOutcome.INTERVIEW)

        assert tracking.outcome == ApplicationOutcome.INTERVIEW
        assert tracking.annotation_outcomes[0].outcome == ApplicationOutcome.INTERVIEW
        assert tracking.annotation_outcomes[1].outcome == ApplicationOutcome.INTERVIEW
        assert tracking.annotation_outcomes[0].outcome_score == OUTCOME_SCORES[ApplicationOutcome.INTERVIEW]

    def test_update_outcome_sets_timestamp(self):
        """Should set outcome timestamp when updated."""
        tracking = ApplicationTracking(job_id="job_123")

        tracking.update_outcome(ApplicationOutcome.OFFER)

        assert tracking.outcome_timestamp != ""
        assert tracking.updated_at != ""

    def test_to_dict_and_from_dict_roundtrip(self):
        """Should survive dict serialization roundtrip."""
        variant = PersonaVariant(
            variant_id="var_123",
            identity_keywords=["Python"],
        )
        ann = AnnotationOutcome(
            annotation_id="ann_1",
            job_id="job_123",
            keyword="Python",
        )

        tracking = ApplicationTracking(
            job_id="job_123",
            company="Test Corp",
            title="Engineer",
            persona_variant=variant,
            annotation_outcomes=[ann],
            keyword_placement_score=85,
            ats_score=90,
        )

        data = tracking.to_dict()
        restored = ApplicationTracking.from_dict(data)

        assert restored.job_id == tracking.job_id
        assert restored.company == tracking.company
        assert restored.persona_variant.variant_id == variant.variant_id
        assert len(restored.annotation_outcomes) == 1
        assert restored.annotation_outcomes[0].keyword == "Python"


class TestAnnotationTrackingService:
    """Tests for AnnotationTrackingService."""

    def test_create_tracking_record_basic(self):
        """Should create a basic tracking record."""
        service = AnnotationTrackingService(db=None)

        tracking = service.create_tracking_record(
            job_id="job_123",
            company="Test Corp",
            title="Senior Engineer",
        )

        assert tracking.job_id == "job_123"
        assert tracking.company == "Test Corp"
        assert tracking.title == "Senior Engineer"
        assert tracking.outcome == ApplicationOutcome.PENDING

    def test_create_tracking_record_with_annotations(self):
        """Should create tracking with annotation outcomes."""
        service = AnnotationTrackingService(db=None)

        jd_annotations = {
            "annotations": [
                {
                    "id": "ann_1",
                    "matching_skill": "Python",
                    "relevance": "core_strength",
                    "requirement_type": "must_have",
                    "passion": "love_it",
                    "identity": "core_identity",
                    "is_active": True,
                },
                {
                    "id": "ann_2",
                    "matching_skill": "AWS",
                    "relevance": "relevant",
                    "is_active": True,
                },
            ]
        }

        tracking = service.create_tracking_record(
            job_id="job_123",
            company="Test Corp",
            title="Engineer",
            jd_annotations=jd_annotations,
        )

        assert tracking.persona_variant is not None
        assert "Python" in tracking.persona_variant.identity_keywords
        assert "Python" in tracking.persona_variant.passion_keywords
        assert len(tracking.annotation_outcomes) == 2

    def test_create_tracking_record_with_placement_results(self):
        """Should incorporate placement validation results."""
        service = AnnotationTrackingService(db=None)

        jd_annotations = {
            "annotations": [
                {"id": "ann_1", "matching_skill": "Python", "is_active": True},
            ]
        }

        keyword_placement_result = {
            "overall_score": 85,
            "must_have_score": 100,
            "identity_score": 90,
            "placements": [
                {
                    "keyword": "Python",
                    "found_in_headline": True,
                    "found_in_narrative": True,
                    "found_in_competencies": False,
                    "found_in_first_role": True,
                    "placement_score": 80,
                }
            ],
        }

        tracking = service.create_tracking_record(
            job_id="job_123",
            company="Test Corp",
            title="Engineer",
            jd_annotations=jd_annotations,
            keyword_placement_result=keyword_placement_result,
        )

        assert tracking.keyword_placement_score == 85
        assert tracking.must_have_coverage == 100
        assert tracking.identity_coverage == 90
        assert len(tracking.annotation_outcomes) == 1
        assert tracking.annotation_outcomes[0].found_in_headline is True
        assert tracking.annotation_outcomes[0].placement_score == 80

    def test_update_outcome_without_db_returns_none(self):
        """Should return None when updating without database."""
        service = AnnotationTrackingService(db=None)

        result = service.update_outcome("job_123", ApplicationOutcome.INTERVIEW)

        assert result is None


class TestOutcomeScores:
    """Tests for outcome score values."""

    def test_offer_has_highest_score(self):
        """Offer and accepted should have score of 1.0."""
        assert OUTCOME_SCORES[ApplicationOutcome.OFFER] == 1.0
        assert OUTCOME_SCORES[ApplicationOutcome.ACCEPTED] == 1.0

    def test_rejected_has_zero_score(self):
        """Rejected should have score of 0.0."""
        assert OUTCOME_SCORES[ApplicationOutcome.REJECTED] == 0.0

    def test_interview_has_partial_score(self):
        """Interview should have score between 0 and 1."""
        assert 0 < OUTCOME_SCORES[ApplicationOutcome.INTERVIEW] < 1

    def test_final_round_higher_than_interview(self):
        """Final round should score higher than initial interview."""
        assert OUTCOME_SCORES[ApplicationOutcome.FINAL_ROUND] > OUTCOME_SCORES[ApplicationOutcome.INTERVIEW]


class TestAnnotationEffectivenessStats:
    """Tests for AnnotationEffectivenessStats dataclass."""

    def test_to_dict_includes_all_metrics(self):
        """Should include all effectiveness metrics in dict."""
        stats = AnnotationEffectivenessStats(
            keyword="Python",
            total_uses=10,
            interviews=4,
            offers=2,
            rejections=4,
            interview_rate=0.4,
            offer_rate=0.2,
            avg_outcome_score=0.35,
            headline_interview_rate=0.6,
            identity_interview_rate=0.5,
        )

        data = stats.to_dict()

        assert data["keyword"] == "Python"
        assert data["total_uses"] == 10
        assert data["interview_rate"] == 0.4
        assert data["headline_interview_rate"] == 0.6
