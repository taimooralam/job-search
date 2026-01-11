"""
Unit tests for Analytics: Outcome Tracker (Phase 7)

Tests outcome tracking, metrics calculation, and effectiveness reporting
with mocked repository operations.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId

from src.analytics.outcome_tracker import (
    OutcomeTracker,
    VALID_STATUSES,
    STATUS_TIMESTAMP_MAP,
)
from src.common.repositories.base import WriteResult


# ===== FIXTURES =====


@pytest.fixture
def mock_job_repository():
    """Mock job repository for level-2 operations."""
    mock_repo = MagicMock()
    mock_repo.find_one.return_value = None
    mock_repo.update_one.return_value = WriteResult(
        matched_count=1, modified_count=1, atlas_success=True
    )
    mock_repo.aggregate.return_value = []
    return mock_repo


@pytest.fixture
def sample_job_doc():
    """Sample job document from MongoDB."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "title": "Senior Engineer",
        "company": "Test Corp",
        "jd_annotations": {
            "annotations": [
                {"id": "a1", "relevance": "core_strength"},
                {"id": "a2", "relevance": "core_strength"},
                {"id": "a3", "relevance": "gap"},
                {"id": "a4", "relevance": "relevant", "has_reframe": True},
            ],
            "section_summaries": {
                "responsibilities": {"coverage_percentage": 0.8},
                "qualifications": {"coverage_percentage": 0.6},
            },
        },
        "application_outcome": None,
    }


@pytest.fixture
def sample_outcome():
    """Sample application outcome."""
    return {
        "status": "applied",
        "applied_at": "2024-01-15T10:00:00",
        "applied_via": "linkedin",
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


@pytest.fixture
def sample_job_with_outcome(sample_job_doc, sample_outcome):
    """Job document with existing outcome."""
    doc = sample_job_doc.copy()
    doc["application_outcome"] = sample_outcome
    return doc


# ===== CONSTANTS TESTS =====


class TestConstants:
    """Test module constants."""

    def test_valid_statuses_defined(self):
        """All valid statuses should be defined."""
        expected = {
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
        assert VALID_STATUSES == expected

    def test_status_timestamp_map_defined(self):
        """Status to timestamp mapping should be defined."""
        assert STATUS_TIMESTAMP_MAP["applied"] == "applied_at"
        assert STATUS_TIMESTAMP_MAP["response_received"] == "response_at"
        assert STATUS_TIMESTAMP_MAP["interview_scheduled"] == "interview_at"
        assert STATUS_TIMESTAMP_MAP["offer_received"] == "offer_at"


# ===== OUTCOME TRACKER INITIALIZATION TESTS =====


class TestOutcomeTrackerInit:
    """Test OutcomeTracker initialization."""

    def test_init_with_default_repository(self):
        """Should use get_job_repository singleton by default."""
        tracker = OutcomeTracker()
        # No exception means success - repository is lazy-loaded
        assert tracker._job_repository is None

    def test_init_with_injected_repository(self, mock_job_repository):
        """Should accept injected repository."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)
        assert tracker._job_repository is mock_job_repository

    def test_init_with_legacy_params(self, mock_job_repository):
        """Should accept legacy mongodb_uri and db_name params (ignored)."""
        tracker = OutcomeTracker(
            mongodb_uri="mongodb://test", db_name="test_db", job_repository=mock_job_repository
        )
        # Legacy params are ignored when repository is provided
        assert tracker._job_repository is mock_job_repository

    def test_get_job_repository_uses_injected(self, mock_job_repository):
        """Should use injected repository from _get_job_repository."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)
        assert tracker._get_job_repository() is mock_job_repository


# ===== GET JOB OUTCOME TESTS =====


class TestGetJobOutcome:
    """Test get_job_outcome method."""

    def test_get_existing_outcome(self, mock_job_repository, sample_job_with_outcome, sample_outcome):
        """Should return existing outcome."""
        mock_job_repository.find_one.return_value = sample_job_with_outcome

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_job_outcome("507f1f77bcf86cd799439011")

        assert result is not None
        assert result["status"] == "applied"
        assert result["applied_via"] == "linkedin"

    def test_get_no_outcome_returns_default(self, mock_job_repository, sample_job_doc):
        """Should return default outcome when none exists."""
        mock_job_repository.find_one.return_value = sample_job_doc

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_job_outcome("507f1f77bcf86cd799439011")

        assert result is not None
        assert result["status"] == "not_applied"

    def test_get_job_not_found(self, mock_job_repository):
        """Should return None when job not found."""
        mock_job_repository.find_one.return_value = None

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_job_outcome("507f1f77bcf86cd799439011")

        assert result is None


# ===== UPDATE OUTCOME TESTS =====


class TestUpdateOutcome:
    """Test update_outcome method."""

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_status(self, mock_config, mock_mongo_client, mock_job_repository, sample_job_doc):
        """Should update outcome status."""
        mock_job_repository.find_one.return_value = sample_job_doc
        mock_job_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1, atlas_success=True
        )
        # Mock the analytics collection access
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.update_outcome("507f1f77bcf86cd799439011", status="applied")

        assert result is not None
        assert result["status"] == "applied"
        assert result["applied_at"] is not None  # Timestamp auto-set

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_with_additional_fields(self, mock_config, mock_mongo_client, mock_job_repository, sample_job_doc):
        """Should update with additional fields."""
        mock_job_repository.find_one.return_value = sample_job_doc
        mock_job_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1, atlas_success=True
        )
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.update_outcome(
            "507f1f77bcf86cd799439011",
            status="applied",
            applied_via="linkedin",
            notes="Good opportunity",
        )

        assert result["applied_via"] == "linkedin"
        assert result["notes"] == "Good opportunity"

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_invalid_status_defaults(self, mock_config, mock_mongo_client, mock_job_repository, sample_job_doc):
        """Should default to not_applied for invalid status."""
        mock_job_repository.find_one.return_value = sample_job_doc
        mock_job_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1, atlas_success=True
        )
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.update_outcome("507f1f77bcf86cd799439011", status="invalid_status")

        assert result["status"] == "not_applied"

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_sets_final_status_at(self, mock_config, mock_mongo_client, mock_job_repository, sample_job_doc):
        """Should set final_status_at for terminal statuses."""
        mock_job_repository.find_one.return_value = sample_job_doc
        mock_job_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1, atlas_success=True
        )
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)

        for status in ["offer_accepted", "rejected", "withdrawn"]:
            sample_job_doc["application_outcome"] = None  # Reset
            result = tracker.update_outcome("507f1f77bcf86cd799439011", status=status)
            assert result["final_status_at"] is not None

    def test_update_job_not_found(self, mock_job_repository):
        """Should return None when job not found."""
        mock_job_repository.find_one.return_value = None

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.update_outcome("507f1f77bcf86cd799439011", status="applied")

        assert result is None


# ===== METRICS CALCULATION TESTS =====


class TestCalculateMetrics:
    """Test _calculate_metrics method."""

    def test_calculate_days_to_response(self, mock_job_repository):
        """Should calculate days to response."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": "2024-01-15T10:00:00",
            "response_at": "2024-01-20T10:00:00",
        }

        result = tracker._calculate_metrics(outcome)

        assert result["days_to_response"] == 5

    def test_calculate_days_to_interview(self, mock_job_repository):
        """Should calculate days to interview."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": "2024-01-15T10:00:00",
            "interview_at": "2024-01-25T10:00:00",
        }

        result = tracker._calculate_metrics(outcome)

        assert result["days_to_interview"] == 10

    def test_calculate_days_to_offer(self, mock_job_repository):
        """Should calculate days to offer."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": "2024-01-15T10:00:00",
            "offer_at": "2024-02-15T10:00:00",
        }

        result = tracker._calculate_metrics(outcome)

        assert result["days_to_offer"] == 31

    def test_calculate_no_applied_at(self, mock_job_repository):
        """Should handle missing applied_at."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": None,
            "response_at": "2024-01-20T10:00:00",
        }

        result = tracker._calculate_metrics(outcome)

        # Should not calculate metrics without applied_at
        assert result.get("days_to_response") is None


# ===== EFFECTIVENESS REPORT TESTS =====


class TestGetEffectivenessReport:
    """Test get_effectiveness_report method."""

    def test_report_with_data(self, mock_job_repository):
        """Should generate report from aggregation results."""
        mock_job_repository.aggregate.return_value = [
            {
                "_id": {"annotation_bucket": "high"},
                "total": 10,
                "responses": 5,
                "interviews": 3,
                "offers": 1,
            },
            {
                "_id": {"annotation_bucket": "low"},
                "total": 20,
                "responses": 4,
                "interviews": 1,
                "offers": 0,
            },
        ]

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_effectiveness_report(date_range_days=90)

        assert result["success"] is True
        assert result["date_range_days"] == 90
        assert "by_annotation_density" in result
        assert "high" in result["by_annotation_density"]
        assert "low" in result["by_annotation_density"]
        assert result["summary"]["total_applied"] == 30
        assert result["summary"]["total_responses"] == 9

    def test_report_empty_data(self, mock_job_repository):
        """Should handle empty aggregation results."""
        mock_job_repository.aggregate.return_value = []

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_effectiveness_report()

        assert result["success"] is True
        assert result["summary"]["total_applied"] == 0

    def test_report_error_handling(self, mock_job_repository):
        """Should handle aggregation errors gracefully."""
        mock_job_repository.aggregate.side_effect = Exception("Aggregation error")

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_effectiveness_report()

        assert result["success"] is False
        assert "error" in result


# ===== CONVERSION FUNNEL TESTS =====


class TestGetConversionFunnel:
    """Test get_conversion_funnel method."""

    def test_funnel_with_data(self, mock_job_repository):
        """Should calculate funnel metrics."""
        mock_job_repository.aggregate.return_value = [
            {
                "_id": None,
                "applied": 100,
                "responses": 30,
                "interviews": 10,
                "offers": 3,
                "avg_days_to_response": 5.5,
                "avg_days_to_interview": 15.2,
            }
        ]

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_conversion_funnel(date_range_days=90)

        assert result["funnel"]["applied"] == 100
        assert result["funnel"]["responses"] == 30
        assert result["funnel"]["interviews"] == 10
        assert result["funnel"]["offers"] == 3
        assert result["conversion_rates"]["response_rate"] == 30.0
        assert result["conversion_rates"]["interview_rate"] == 10.0
        assert result["conversion_rates"]["offer_rate"] == 3.0
        assert result["avg_days"]["to_response"] == 5.5
        assert result["avg_days"]["to_interview"] == 15.2

    def test_funnel_empty_data(self, mock_job_repository):
        """Should return zeros for empty data."""
        mock_job_repository.aggregate.return_value = []

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_conversion_funnel()

        assert result["funnel"]["applied"] == 0
        assert result["conversion_rates"]["response_rate"] == 0.0


# ===== DEFAULT OUTCOME TESTS =====


class TestCreateDefaultOutcome:
    """Test _create_default_outcome method."""

    def test_default_outcome_structure(self, mock_job_repository):
        """Should create valid default outcome structure."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = tracker._create_default_outcome()

        assert outcome["status"] == "not_applied"
        assert outcome["applied_at"] is None
        assert outcome["interview_rounds"] == 0
        assert "days_to_response" in outcome
        assert "days_to_interview" in outcome
        assert "days_to_offer" in outcome


# ===== ANALYTICS UPDATE TESTS =====


class TestUpdateAnalytics:
    """Test _update_analytics method."""

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_updates_analytics_collection(self, mock_config, mock_mongo_client, mock_job_repository, sample_job_doc, sample_outcome):
        """Should update analytics collection with annotation profile."""
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        tracker._update_analytics("test_job_id", sample_job_doc, sample_outcome)

        # Verify upsert was called
        mock_analytics.update_one.assert_called_once()
        call_args = mock_analytics.update_one.call_args
        assert call_args[1]["upsert"] is True

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_calculates_annotation_profile(self, mock_config, mock_mongo_client, mock_job_repository, sample_job_doc, sample_outcome):
        """Should calculate annotation profile correctly."""
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        tracker._update_analytics("test_job_id", sample_job_doc, sample_outcome)

        # Get the document that was written
        call_args = mock_analytics.update_one.call_args
        doc = call_args[0][1]["$set"]

        assert doc["annotation_profile"]["annotation_count"] == 4
        assert doc["annotation_profile"]["core_strength_count"] == 2
        assert doc["annotation_profile"]["gap_count"] == 1
        assert doc["annotation_profile"]["reframe_count"] == 1


# ===== RECOMMENDATION GENERATION TESTS =====


class TestGenerateRecommendation:
    """Test _generate_recommendation method."""

    def test_high_annotation_recommendation(self, mock_job_repository):
        """Should recommend annotation when high density shows better results."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        by_bucket = {
            "high": {"response_rate": 50.0},
            "low": {"response_rate": 20.0},
        }

        recommendation = tracker._generate_recommendation(by_bucket)

        assert "annotation density" in recommendation.lower()
        assert "better" in recommendation.lower() or "continue" in recommendation.lower()

    def test_low_annotation_recommendation(self, mock_job_repository):
        """Should note when low density shows better results."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        by_bucket = {
            "high": {"response_rate": 20.0},
            "low": {"response_rate": 50.0},
        }

        recommendation = tracker._generate_recommendation(by_bucket)

        assert "lower" in recommendation.lower() or "quality" in recommendation.lower()

    def test_no_data_recommendation(self, mock_job_repository):
        """Should return default message when no data."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        recommendation = tracker._generate_recommendation({})

        assert "not enough data" in recommendation.lower()
