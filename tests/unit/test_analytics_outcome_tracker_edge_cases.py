"""
Edge case tests for Analytics: Outcome Tracker.

Tests error handling, date/time edge cases, and boundary conditions
not covered in the main test file.
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
def sample_job_with_malformed_outcome():
    """Job with malformed outcome data."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "title": "Engineer",
        "company": "Test",
        "application_outcome": {
            "status": "applied",
            "applied_at": "invalid-date-format",  # Invalid date
            "response_at": None,
            # Missing required fields
        },
    }


@pytest.fixture
def sample_job_with_timezone_dates():
    """Job with various timezone formats."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "title": "Engineer",
        "company": "Test",
        "application_outcome": {
            "status": "interview_scheduled",
            "applied_at": "2024-01-15T10:00:00Z",  # UTC
            "response_at": "2024-01-20T15:30:00+05:30",  # IST
            "interview_at": "2024-01-25T09:00:00-08:00",  # PST
        },
    }


# ===== DATE/TIME EDGE CASES =====


class TestDateTimeEdgeCases:
    """Test date and time handling edge cases."""

    def test_calculate_metrics_invalid_date_format(self, mock_job_repository):
        """Should handle invalid date formats gracefully."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": "invalid-date",
            "response_at": "2024-01-20T10:00:00",
        }

        result = tracker._calculate_metrics(outcome)

        # Should not crash, metrics should be None
        assert result.get("days_to_response") is None

    def test_calculate_metrics_timezone_aware(self, mock_job_repository):
        """Should handle timezone-aware dates."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": "2024-01-15T10:00:00+00:00",
            "response_at": "2024-01-20T10:00:00+00:00",
        }

        result = tracker._calculate_metrics(outcome)

        assert result["days_to_response"] == 5

    def test_calculate_metrics_with_z_suffix(self, mock_job_repository):
        """Should handle dates with Z suffix (UTC)."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": "2024-01-15T10:00:00Z",
            "response_at": "2024-01-20T10:00:00Z",
        }

        result = tracker._calculate_metrics(outcome)

        assert result["days_to_response"] == 5

    def test_calculate_metrics_same_day_application_response(self, mock_job_repository):
        """Should handle same-day application and response."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": "2024-01-15T10:00:00",
            "response_at": "2024-01-15T18:00:00",
        }

        result = tracker._calculate_metrics(outcome)

        # Same day should be 0 days
        assert result["days_to_response"] == 0

    def test_calculate_metrics_negative_duration(self, mock_job_repository):
        """Should handle response_at before applied_at (data error)."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": "2024-01-20T10:00:00",
            "response_at": "2024-01-15T10:00:00",  # Before applied
        }

        result = tracker._calculate_metrics(outcome)

        # Should calculate negative days (indicates data issue)
        assert result["days_to_response"] == -5

    def test_calculate_metrics_very_long_duration(self, mock_job_repository):
        """Should handle very long durations."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": "2023-01-01T10:00:00",
            "offer_at": "2024-12-31T10:00:00",  # ~2 years
        }

        result = tracker._calculate_metrics(outcome)

        # Should calculate large number of days
        assert result["days_to_offer"] > 700

    def test_calculate_metrics_missing_applied_at(self, mock_job_repository):
        """Should handle missing applied_at."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": None,
            "response_at": "2024-01-20T10:00:00",
            "interview_at": "2024-01-25T10:00:00",
        }

        result = tracker._calculate_metrics(outcome)

        # Should not calculate any metrics
        assert result.get("days_to_response") is None
        assert result.get("days_to_interview") is None

    def test_calculate_metrics_partial_timestamps(self, mock_job_repository):
        """Should handle partial timestamp data."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        outcome = {
            "applied_at": "2024-01-15T10:00:00",
            "response_at": "2024-01-20T10:00:00",
            "interview_at": None,  # Not scheduled yet
            "offer_at": None,
        }

        result = tracker._calculate_metrics(outcome)

        assert result["days_to_response"] == 5
        assert result.get("days_to_interview") is None
        assert result.get("days_to_offer") is None


# ===== MONGODB ERROR HANDLING =====


class TestMongoDBErrorHandling:
    """Test MongoDB error handling."""

    def test_init_connection_failure(self, mock_job_repository):
        """Should not fail on init - repository is lazy-loaded."""
        # With repository pattern, init doesn't connect immediately
        tracker = OutcomeTracker(job_repository=mock_job_repository)
        assert tracker._job_repository is mock_job_repository

    def test_get_job_outcome_invalid_objectid(self, mock_job_repository):
        """Should handle invalid ObjectId format."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        # Invalid ObjectId
        result = tracker.get_job_outcome("invalid-id-format")

        # Should return None or handle gracefully
        assert result is None or isinstance(result, dict)

    def test_update_outcome_invalid_objectid(self, mock_job_repository):
        """Should handle invalid ObjectId on update."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        result = tracker.update_outcome("invalid-id", status="applied")

        assert result is None

    def test_update_outcome_database_error(self, mock_job_repository):
        """Should handle database errors during update."""
        mock_job_repository.find_one.side_effect = Exception("Database error")

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.update_outcome("507f1f77bcf86cd799439011", status="applied")

        assert result is None

    def test_get_effectiveness_report_aggregation_error(self, mock_job_repository):
        """Should handle aggregation pipeline errors."""
        mock_job_repository.aggregate.side_effect = Exception("Aggregation failed")

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_effectiveness_report()

        assert result["success"] is False
        assert "error" in result


# ===== STATUS TRANSITION EDGE CASES =====


class TestStatusTransitions:
    """Test status transition edge cases."""

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_same_status_twice(self, mock_config, mock_mongo_client, mock_job_repository):
        """Should handle updating to same status."""
        job = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "application_outcome": {
                "status": "applied",
                "applied_at": "2024-01-15T10:00:00",
            },
        }
        mock_job_repository.find_one.return_value = job
        mock_job_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1, atlas_success=True
        )
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)

        # Update to same status
        result = tracker.update_outcome("507f1f77bcf86cd799439011", status="applied")

        assert result["status"] == "applied"
        # Timestamp should not be overwritten
        assert result["applied_at"] == "2024-01-15T10:00:00"

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_backwards_status_transition(self, mock_config, mock_mongo_client, mock_job_repository):
        """Should allow backwards status transitions (data corrections)."""
        job = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "application_outcome": {
                "status": "interview_scheduled",
                "applied_at": "2024-01-15T10:00:00",
                "interview_at": "2024-01-25T10:00:00",
            },
        }
        mock_job_repository.find_one.return_value = job
        mock_job_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1, atlas_success=True
        )
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)

        # Revert to earlier status
        result = tracker.update_outcome(
            "507f1f77bcf86cd799439011", status="response_received"
        )

        assert result["status"] == "response_received"

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_all_terminal_statuses(self, mock_config, mock_mongo_client, mock_job_repository):
        """Should handle all terminal statuses."""
        job = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "application_outcome": None,
        }
        mock_job_repository.find_one.return_value = job
        mock_job_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1, atlas_success=True
        )
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)

        terminal_statuses = ["offer_accepted", "rejected", "withdrawn"]

        for status in terminal_statuses:
            job["application_outcome"] = None  # Reset
            result = tracker.update_outcome("507f1f77bcf86cd799439011", status=status)

            assert result["status"] == status
            assert result["final_status_at"] is not None


# ===== ANNOTATION PROFILE EDGE CASES =====


class TestAnnotationProfileEdgeCases:
    """Test annotation profile calculation edge cases."""

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_analytics_missing_annotations(self, mock_config, mock_mongo_client, mock_job_repository):
        """Should handle missing jd_annotations field."""
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)

        job = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Engineer",
            # No jd_annotations
        }

        outcome = {"status": "applied", "applied_at": "2024-01-15T10:00:00"}

        # Should not crash
        tracker._update_analytics("test_id", job, outcome)

        # Should still call update_one
        mock_analytics.update_one.assert_called_once()

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_analytics_empty_annotations(self, mock_config, mock_mongo_client, mock_job_repository):
        """Should handle empty annotations list."""
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)

        job = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "jd_annotations": {"annotations": []},  # Empty
        }

        outcome = {"status": "applied", "applied_at": "2024-01-15T10:00:00"}

        tracker._update_analytics("test_id", job, outcome)

        call_args = mock_analytics.update_one.call_args
        doc = call_args[0][1]["$set"]

        assert doc["annotation_profile"]["annotation_count"] == 0
        assert doc["annotation_profile"]["core_strength_count"] == 0

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_analytics_malformed_annotations(self, mock_config, mock_mongo_client, mock_job_repository):
        """Should handle malformed annotation objects."""
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)

        job = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "jd_annotations": {
                "annotations": [
                    {},  # Empty annotation
                    {"relevance": None},  # None relevance
                    {"other_field": "value"},  # Missing relevance
                ]
            },
        }

        outcome = {"status": "applied", "applied_at": "2024-01-15T10:00:00"}

        # Should not crash
        tracker._update_analytics("test_id", job, outcome)

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_analytics_no_section_summaries(self, mock_config, mock_mongo_client, mock_job_repository):
        """Should handle missing section_summaries."""
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)

        job = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "jd_annotations": {
                "annotations": [{"relevance": "core_strength"}],
                # No section_summaries
            },
        }

        outcome = {"status": "applied", "applied_at": "2024-01-15T10:00:00"}

        tracker._update_analytics("test_id", job, outcome)

        call_args = mock_analytics.update_one.call_args
        doc = call_args[0][1]["$set"]

        # Section coverage should be 0
        assert doc["annotation_profile"]["section_coverage"] == 0

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_analytics_error_does_not_propagate(self, mock_config, mock_mongo_client, mock_job_repository):
        """Analytics update error should not fail main operation."""
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_analytics.update_one.side_effect = Exception("Analytics failed")
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)

        job = {"_id": ObjectId("507f1f77bcf86cd799439011")}
        outcome = {"status": "applied"}

        # Should not raise exception
        tracker._update_analytics("test_id", job, outcome)


# ===== REPORT GENERATION EDGE CASES =====


class TestReportGenerationEdgeCases:
    """Test effectiveness report generation edge cases."""

    def test_report_single_bucket(self, mock_job_repository):
        """Should handle report with only one bucket."""
        mock_job_repository.aggregate.return_value = [
            {
                "_id": {"annotation_bucket": "high"},
                "total": 10,
                "responses": 5,
                "interviews": 3,
                "offers": 1,
            }
        ]

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_effectiveness_report()

        assert result["success"] is True
        assert "high" in result["by_annotation_density"]
        assert len(result["by_annotation_density"]) == 1

    def test_report_zero_totals(self, mock_job_repository):
        """Should handle buckets with zero applications."""
        mock_job_repository.aggregate.return_value = [
            {
                "_id": {"annotation_bucket": "high"},
                "total": 0,  # Zero
                "responses": 0,
                "interviews": 0,
                "offers": 0,
            }
        ]

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_effectiveness_report()

        # Should handle division by zero
        assert result["by_annotation_density"]["high"]["response_rate"] == 0

    def test_generate_recommendation_equal_rates(self, mock_job_repository):
        """Should handle equal response rates."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        by_bucket = {
            "high": {"response_rate": 30.0},
            "low": {"response_rate": 30.0},  # Equal
        }

        recommendation = tracker._generate_recommendation(by_bucket)

        assert "no significant correlation" in recommendation.lower()

    def test_generate_recommendation_only_high(self, mock_job_repository):
        """Should handle when only high bucket has data."""
        tracker = OutcomeTracker(job_repository=mock_job_repository)

        by_bucket = {
            "high": {"response_rate": 50.0},
            # No low bucket
        }

        recommendation = tracker._generate_recommendation(by_bucket)

        assert isinstance(recommendation, str)

    def test_funnel_single_application(self, mock_job_repository):
        """Should handle funnel with single application."""
        mock_job_repository.aggregate.return_value = [
            {
                "_id": None,
                "applied": 1,
                "responses": 0,
                "interviews": 0,
                "offers": 0,
                "avg_days_to_response": None,
                "avg_days_to_interview": None,
            }
        ]

        tracker = OutcomeTracker(job_repository=mock_job_repository)
        result = tracker.get_conversion_funnel()

        assert result["funnel"]["applied"] == 1
        assert result["conversion_rates"]["response_rate"] == 0.0


# ===== FIELD VALIDATION TESTS =====


class TestFieldValidation:
    """Test field validation and sanitization."""

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_with_disallowed_fields(self, mock_config, mock_mongo_client, mock_job_repository):
        """Should ignore disallowed fields in update."""
        job = {"_id": ObjectId("507f1f77bcf86cd799439011"), "application_outcome": None}
        mock_job_repository.find_one.return_value = job
        mock_job_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1, atlas_success=True
        )
        mock_config.return_value.get.return_value = "mongodb://test"
        mock_analytics = MagicMock()
        mock_mongo_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_analytics

        tracker = OutcomeTracker(job_repository=mock_job_repository)

        # Try to pass disallowed fields
        result = tracker.update_outcome(
            "507f1f77bcf86cd799439011",
            status="applied",
            malicious_field="hacked",  # Should be ignored
            _id="fake",  # Should be ignored
        )

        # Disallowed fields should not be in outcome
        assert "malicious_field" not in result
        # _id is not part of outcome subdocument, so it won't be there
        assert "_id" not in result

    @patch("src.analytics.outcome_tracker.MongoClient")
    @patch("src.analytics.outcome_tracker.Config")
    def test_update_with_none_values(self, mock_config, mock_mongo_client, mock_job_repository):
        """Should handle None values in update."""
        job = {"_id": ObjectId("507f1f77bcf86cd799439011"), "application_outcome": None}
        mock_job_repository.find_one.return_value = job
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
            notes=None,  # Explicitly None
        )

        assert result["notes"] is None
