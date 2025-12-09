"""
Unit tests for Analytics: Outcome Tracker (Phase 7)

Tests outcome tracking, metrics calculation, and effectiveness reporting
with mocked MongoDB operations.
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


# ===== FIXTURES =====


@pytest.fixture
def mock_mongodb():
    """Mock MongoDB client and collection."""
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_analytics_collection = MagicMock()

    mock_client.__getitem__.return_value = mock_db
    mock_db.__getitem__.side_effect = lambda name: (
        mock_collection if name == "level-2" else mock_analytics_collection
    )

    return mock_client, mock_db, mock_collection, mock_analytics_collection


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

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_init_with_default_uri(self, mock_config, mock_mongo):
        """Should use Config.MONGODB_URI by default."""
        mock_config.MONGODB_URI = "mongodb://localhost:27017"

        tracker = OutcomeTracker()

        mock_mongo.assert_called_once_with("mongodb://localhost:27017")

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_init_with_custom_uri(self, mock_mongo):
        """Should accept custom MongoDB URI."""
        tracker = OutcomeTracker(mongodb_uri="mongodb://custom:27017")

        mock_mongo.assert_called_once_with("mongodb://custom:27017")

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_init_with_custom_db_name(self, mock_mongo):
        """Should accept custom database name."""
        mock_client = MagicMock()
        mock_mongo.return_value = mock_client

        tracker = OutcomeTracker(
            mongodb_uri="mongodb://localhost:27017", db_name="custom_db"
        )

        mock_client.__getitem__.assert_called_with("custom_db")

    @patch("src.analytics.outcome_tracker.Config")
    def test_init_missing_uri_raises(self, mock_config):
        """Should raise ValueError if no URI configured."""
        mock_config.MONGODB_URI = ""

        with pytest.raises(ValueError, match="MONGODB_URI not configured"):
            OutcomeTracker(mongodb_uri=None)


# ===== GET JOB OUTCOME TESTS =====


class TestGetJobOutcome:
    """Test get_job_outcome method."""

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_get_existing_outcome(self, mock_mongo, sample_job_with_outcome, sample_outcome):
        """Should return existing outcome."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job_with_outcome
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection

        result = tracker.get_job_outcome("507f1f77bcf86cd799439011")

        assert result is not None
        assert result["status"] == "applied"
        assert result["applied_via"] == "linkedin"

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_get_no_outcome_returns_default(self, mock_mongo, sample_job_doc):
        """Should return default outcome when none exists."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job_doc
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection

        result = tracker.get_job_outcome("507f1f77bcf86cd799439011")

        assert result is not None
        assert result["status"] == "not_applied"

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_get_job_not_found(self, mock_mongo):
        """Should return None when job not found."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection

        result = tracker.get_job_outcome("507f1f77bcf86cd799439011")

        assert result is None


# ===== UPDATE OUTCOME TESTS =====


class TestUpdateOutcome:
    """Test update_outcome method."""

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_update_status(self, mock_mongo, sample_job_doc):
        """Should update outcome status."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job_doc
        mock_collection.update_one.return_value = MagicMock(modified_count=1, matched_count=1)
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection
        tracker.db = {"annotation_analytics": MagicMock()}

        result = tracker.update_outcome("507f1f77bcf86cd799439011", status="applied")

        assert result is not None
        assert result["status"] == "applied"
        assert result["applied_at"] is not None  # Timestamp auto-set

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_update_with_additional_fields(self, mock_mongo, sample_job_doc):
        """Should update with additional fields."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job_doc
        mock_collection.update_one.return_value = MagicMock(modified_count=1, matched_count=1)
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection
        tracker.db = {"annotation_analytics": MagicMock()}

        result = tracker.update_outcome(
            "507f1f77bcf86cd799439011",
            status="applied",
            applied_via="linkedin",
            notes="Good opportunity",
        )

        assert result["applied_via"] == "linkedin"
        assert result["notes"] == "Good opportunity"

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_update_invalid_status_defaults(self, mock_mongo, sample_job_doc):
        """Should default to not_applied for invalid status."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job_doc
        mock_collection.update_one.return_value = MagicMock(modified_count=1, matched_count=1)
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection
        tracker.db = {"annotation_analytics": MagicMock()}

        result = tracker.update_outcome("507f1f77bcf86cd799439011", status="invalid_status")

        assert result["status"] == "not_applied"

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_update_sets_final_status_at(self, mock_mongo, sample_job_doc):
        """Should set final_status_at for terminal statuses."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job_doc
        mock_collection.update_one.return_value = MagicMock(modified_count=1, matched_count=1)
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection
        tracker.db = {"annotation_analytics": MagicMock()}

        for status in ["offer_accepted", "rejected", "withdrawn"]:
            sample_job_doc["application_outcome"] = None  # Reset
            result = tracker.update_outcome("507f1f77bcf86cd799439011", status=status)
            assert result["final_status_at"] is not None

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_update_job_not_found(self, mock_mongo):
        """Should return None when job not found."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection

        result = tracker.update_outcome("507f1f77bcf86cd799439011", status="applied")

        assert result is None


# ===== METRICS CALCULATION TESTS =====


class TestCalculateMetrics:
    """Test _calculate_metrics method."""

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_calculate_days_to_response(self, mock_mongo):
        """Should calculate days to response."""
        tracker = OutcomeTracker(mongodb_uri="mongodb://test")

        outcome = {
            "applied_at": "2024-01-15T10:00:00",
            "response_at": "2024-01-20T10:00:00",
        }

        result = tracker._calculate_metrics(outcome)

        assert result["days_to_response"] == 5

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_calculate_days_to_interview(self, mock_mongo):
        """Should calculate days to interview."""
        tracker = OutcomeTracker(mongodb_uri="mongodb://test")

        outcome = {
            "applied_at": "2024-01-15T10:00:00",
            "interview_at": "2024-01-25T10:00:00",
        }

        result = tracker._calculate_metrics(outcome)

        assert result["days_to_interview"] == 10

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_calculate_days_to_offer(self, mock_mongo):
        """Should calculate days to offer."""
        tracker = OutcomeTracker(mongodb_uri="mongodb://test")

        outcome = {
            "applied_at": "2024-01-15T10:00:00",
            "offer_at": "2024-02-15T10:00:00",
        }

        result = tracker._calculate_metrics(outcome)

        assert result["days_to_offer"] == 31

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_calculate_no_applied_at(self, mock_mongo):
        """Should handle missing applied_at."""
        tracker = OutcomeTracker(mongodb_uri="mongodb://test")

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

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_report_with_data(self, mock_mongo):
        """Should generate report from aggregation results."""
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = [
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
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection

        result = tracker.get_effectiveness_report(date_range_days=90)

        assert result["success"] is True
        assert result["date_range_days"] == 90
        assert "by_annotation_density" in result
        assert "high" in result["by_annotation_density"]
        assert "low" in result["by_annotation_density"]
        assert result["summary"]["total_applied"] == 30
        assert result["summary"]["total_responses"] == 9

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_report_empty_data(self, mock_mongo):
        """Should handle empty aggregation results."""
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = []
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection

        result = tracker.get_effectiveness_report()

        assert result["success"] is True
        assert result["summary"]["total_applied"] == 0

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_report_error_handling(self, mock_mongo):
        """Should handle aggregation errors gracefully."""
        mock_collection = MagicMock()
        mock_collection.aggregate.side_effect = Exception("Aggregation error")
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection

        result = tracker.get_effectiveness_report()

        assert result["success"] is False
        assert "error" in result


# ===== CONVERSION FUNNEL TESTS =====


class TestGetConversionFunnel:
    """Test get_conversion_funnel method."""

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_funnel_with_data(self, mock_mongo):
        """Should calculate funnel metrics."""
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = [
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
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection

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

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_funnel_empty_data(self, mock_mongo):
        """Should return zeros for empty data."""
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = []
        mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
            mock_collection
        )

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.collection = mock_collection

        result = tracker.get_conversion_funnel()

        assert result["funnel"]["applied"] == 0
        assert result["conversion_rates"]["response_rate"] == 0.0


# ===== DEFAULT OUTCOME TESTS =====


class TestCreateDefaultOutcome:
    """Test _create_default_outcome method."""

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_default_outcome_structure(self, mock_mongo):
        """Should create valid default outcome structure."""
        tracker = OutcomeTracker(mongodb_uri="mongodb://test")

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
    def test_updates_analytics_collection(self, mock_mongo, sample_job_doc, sample_outcome):
        """Should update analytics collection with annotation profile."""
        mock_analytics = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_analytics
        mock_mongo.return_value.__getitem__.return_value = mock_db

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.db = mock_db

        tracker._update_analytics("test_job_id", sample_job_doc, sample_outcome)

        # Verify upsert was called
        mock_analytics.update_one.assert_called_once()
        call_args = mock_analytics.update_one.call_args
        assert call_args[1]["upsert"] is True

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_calculates_annotation_profile(self, mock_mongo, sample_job_doc, sample_outcome):
        """Should calculate annotation profile correctly."""
        mock_analytics = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_analytics
        mock_mongo.return_value.__getitem__.return_value = mock_db

        tracker = OutcomeTracker(mongodb_uri="mongodb://test")
        tracker.db = mock_db

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

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_high_annotation_recommendation(self, mock_mongo):
        """Should recommend annotation when high density shows better results."""
        tracker = OutcomeTracker(mongodb_uri="mongodb://test")

        by_bucket = {
            "high": {"response_rate": 50.0},
            "low": {"response_rate": 20.0},
        }

        recommendation = tracker._generate_recommendation(by_bucket)

        assert "annotation density" in recommendation.lower()
        assert "better" in recommendation.lower() or "continue" in recommendation.lower()

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_low_annotation_recommendation(self, mock_mongo):
        """Should note when low density shows better results."""
        tracker = OutcomeTracker(mongodb_uri="mongodb://test")

        by_bucket = {
            "high": {"response_rate": 20.0},
            "low": {"response_rate": 50.0},
        }

        recommendation = tracker._generate_recommendation(by_bucket)

        assert "lower" in recommendation.lower() or "quality" in recommendation.lower()

    @patch("src.analytics.outcome_tracker.MongoClient")
    def test_no_data_recommendation(self, mock_mongo):
        """Should return default message when no data."""
        tracker = OutcomeTracker(mongodb_uri="mongodb://test")

        recommendation = tracker._generate_recommendation({})

        assert "not enough data" in recommendation.lower()
