"""
Unit tests for src/services/annotation_priors.py

Tests priors management including:
- Loading and saving priors from MongoDB
- Rebuilding sentence index and skill priors
- Capturing feedback from user edits
- Computing statistics and rebuild triggers
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call
import numpy as np

from src.services.annotation_priors import (
    load_priors,
    save_priors,
    should_rebuild_priors,
    capture_feedback,
    _aggregate_dimension,
    get_priors_stats,
    _empty_priors,
    rebuild_priors,
    _recompute_skill_priors,
    _extract_primary_skill,
    PRIORS_DOC_ID,
)


class TestLoadPriors:
    """Tests for load_priors function."""

    @pytest.fixture
    def mock_collection(self):
        """Mock MongoDB collection."""
        with patch("src.services.annotation_priors._get_collection") as mock:
            yield mock.return_value

    def test_loads_existing_priors(self, mock_collection):
        """Should load priors document from MongoDB when it exists."""
        # Arrange
        existing_priors = {
            "_id": PRIORS_DOC_ID,
            "version": 2,
            "sentence_index": {"count": 100},
            "skill_priors": {"python": {}},
            "stats": {"total_annotations_at_build": 100},
        }
        mock_collection.find_one.return_value = existing_priors

        # Act
        result = load_priors()

        # Assert
        mock_collection.find_one.assert_called_once_with({"_id": PRIORS_DOC_ID})
        assert result["_id"] == PRIORS_DOC_ID
        assert result["version"] == 2
        assert result["sentence_index"]["count"] == 100

    def test_creates_empty_priors_when_not_exists(self, mock_collection):
        """Should create and insert empty priors when none exists."""
        # Arrange
        mock_collection.find_one.return_value = None

        # Act
        result = load_priors()

        # Assert
        mock_collection.find_one.assert_called_once_with({"_id": PRIORS_DOC_ID})
        mock_collection.insert_one.assert_called_once()
        assert result["_id"] == PRIORS_DOC_ID
        assert result["version"] == 1
        assert result["sentence_index"]["count"] == 0
        assert result["skill_priors"] == {}
        assert result["stats"]["total_annotations_at_build"] == 0

    def test_handles_mongodb_error_gracefully(self, mock_collection):
        """Should return empty priors on MongoDB error."""
        # Arrange
        mock_collection.find_one.side_effect = Exception("Connection failed")

        # Act
        result = load_priors()

        # Assert
        assert result["_id"] == PRIORS_DOC_ID
        assert result["version"] == 1
        assert result["sentence_index"]["count"] == 0


class TestSavePriors:
    """Tests for save_priors function."""

    @pytest.fixture
    def mock_collection(self):
        """Mock MongoDB collection."""
        with patch("src.services.annotation_priors._get_collection") as mock:
            yield mock.return_value

    @pytest.fixture
    def sample_priors(self):
        """Sample priors document."""
        return _empty_priors()

    def test_saves_priors_with_upsert(self, mock_collection, sample_priors):
        """Should save priors using replace_one with upsert=True."""
        # Arrange
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_result.modified_count = 1
        mock_collection.replace_one.return_value = mock_result

        # Act
        result = save_priors(sample_priors)

        # Assert
        mock_collection.replace_one.assert_called_once()
        call_args = mock_collection.replace_one.call_args
        assert call_args[0][0] == {"_id": PRIORS_DOC_ID}
        assert call_args[1]["upsert"] is True
        assert result is True

    def test_updates_timestamp_on_save(self, mock_collection, sample_priors):
        """Should update updated_at timestamp when saving."""
        # Arrange
        mock_collection.replace_one.return_value = MagicMock()
        original_timestamp = sample_priors["updated_at"]

        # Act
        save_priors(sample_priors)

        # Assert
        assert sample_priors["updated_at"] != original_timestamp
        # Verify it's a valid ISO timestamp
        datetime.fromisoformat(sample_priors["updated_at"].replace("Z", "+00:00"))

    def test_handles_mongodb_error_on_save(self, mock_collection, sample_priors):
        """Should return False on MongoDB error."""
        # Arrange
        mock_collection.replace_one.side_effect = Exception("Write failed")

        # Act
        result = save_priors(sample_priors)

        # Assert
        assert result is False


class TestShouldRebuildPriors:
    """Tests for should_rebuild_priors function."""

    @pytest.fixture
    def base_priors(self):
        """Base priors document with valid index."""
        now = datetime.now(timezone.utc).isoformat()
        return {
            "sentence_index": {
                "embeddings": [[0.1] * 384],  # Non-empty
                "texts": ["test"],
                "built_at": now,
                "count": 1,
            },
            "stats": {
                "annotations_since_build": 0,
            },
        }

    def test_rebuild_when_no_embeddings(self, base_priors):
        """Should rebuild when no embeddings exist."""
        # Arrange
        base_priors["sentence_index"]["embeddings"] = []

        # Act
        result = should_rebuild_priors(base_priors)

        # Assert
        assert result is True

    def test_rebuild_when_no_built_at(self, base_priors):
        """Should rebuild when built_at timestamp is missing."""
        # Arrange
        del base_priors["sentence_index"]["built_at"]

        # Act
        result = should_rebuild_priors(base_priors)

        # Assert
        assert result is True

    def test_rebuild_when_stale_with_enough_new_annotations(self, base_priors):
        """Should rebuild when >24h old AND >20 new annotations."""
        # Arrange
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        base_priors["sentence_index"]["built_at"] = old_time.isoformat()
        base_priors["stats"]["annotations_since_build"] = 25

        # Act
        result = should_rebuild_priors(base_priors)

        # Assert
        assert result is True

    def test_no_rebuild_when_stale_but_few_annotations(self, base_priors):
        """Should NOT rebuild when >24h old but only few new annotations."""
        # Arrange
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        base_priors["sentence_index"]["built_at"] = old_time.isoformat()
        base_priors["stats"]["annotations_since_build"] = 10

        # Act
        result = should_rebuild_priors(base_priors)

        # Assert
        assert result is False

    def test_rebuild_when_many_new_annotations_regardless_of_time(self, base_priors):
        """Should rebuild when >100 new annotations regardless of age."""
        # Arrange
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        base_priors["sentence_index"]["built_at"] = recent_time.isoformat()
        base_priors["stats"]["annotations_since_build"] = 150

        # Act
        result = should_rebuild_priors(base_priors)

        # Assert
        assert result is True

    def test_no_rebuild_when_fresh_and_few_annotations(self, base_priors):
        """Should NOT rebuild when fresh and few new annotations."""
        # Arrange
        recent_time = datetime.now(timezone.utc) - timedelta(hours=2)
        base_priors["sentence_index"]["built_at"] = recent_time.isoformat()
        base_priors["stats"]["annotations_since_build"] = 5

        # Act
        result = should_rebuild_priors(base_priors)

        # Assert
        assert result is False

    def test_handles_invalid_timestamp(self, base_priors):
        """Should trigger rebuild on invalid built_at timestamp."""
        # Arrange
        base_priors["sentence_index"]["built_at"] = "invalid-timestamp"

        # Act
        result = should_rebuild_priors(base_priors)

        # Assert
        assert result is True


class TestCaptureFeedback:
    """Tests for capture_feedback function."""

    @pytest.fixture
    def base_priors(self):
        """Base priors document."""
        return {
            "skill_priors": {},
            "stats": {
                "deleted": 0,
                "edited": 0,
                "accepted_unchanged": 0,
                "annotations_since_build": 0,
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @pytest.fixture
    def auto_annotation(self):
        """Auto-generated annotation."""
        return {
            "source": "auto_generated",
            "target": {"text": "Experience with Python and Django"},
            "relevance": "relevant",
            "passion": "moderate",
            "identity": "core_strength",
            "original_values": {
                "relevance": "relevant",
                "passion": "moderate",
                "identity": "peripheral",
                "match_method": "sentence_similarity",
                "matched_text": "Python development experience",
            },
            "feedback_captured": False,
        }

    def test_ignores_manual_annotations(self, base_priors):
        """Should ignore annotations not from auto_generated source."""
        # Arrange
        manual_annotation = {
            "source": "manual",
            "target": {"text": "Python"},
        }

        # Act
        result = capture_feedback(manual_annotation, "save", base_priors)

        # Assert
        assert result == base_priors
        assert len(base_priors["skill_priors"]) == 0

    def test_marks_skill_as_avoid_on_delete(self, base_priors, auto_annotation):
        """Should mark skill as avoid when annotation is deleted."""
        # Arrange
        auto_annotation["original_values"]["matched_keyword"] = "python"
        auto_annotation["original_values"]["match_method"] = "keyword_prior"

        # Act
        result = capture_feedback(auto_annotation, "delete", base_priors)

        # Assert
        assert "python" in result["skill_priors"]
        assert result["skill_priors"]["python"]["avoid"] is True
        assert result["stats"]["deleted"] == 1

    def test_decreases_confidence_on_delete(self, base_priors, auto_annotation):
        """Should decrease confidence for all dimensions on delete."""
        # Arrange
        base_priors["skill_priors"]["python"] = {
            "relevance": {"value": "relevant", "confidence": 0.8, "n": 5},
            "passion": {"value": "moderate", "confidence": 0.7, "n": 3},
            "identity": {"value": "core", "confidence": 0.9, "n": 4},
            "requirement": {"value": "neutral", "confidence": 0.6, "n": 2},
            "avoid": False,
        }
        auto_annotation["original_values"]["matched_keyword"] = "python"
        auto_annotation["original_values"]["match_method"] = "keyword_prior"

        # Act
        result = capture_feedback(auto_annotation, "delete", base_priors)

        # Assert
        python_prior = result["skill_priors"]["python"]
        assert python_prior["relevance"]["confidence"] == 0.8 * 0.3
        assert python_prior["passion"]["confidence"] == 0.7 * 0.3
        assert python_prior["identity"]["confidence"] == 0.9 * 0.3

    def test_adopts_new_value_when_confidence_low(self, base_priors, auto_annotation):
        """Should adopt new value when confidence drops below threshold."""
        # Arrange
        base_priors["skill_priors"]["python"] = {
            "relevance": {"value": "relevant", "confidence": 0.35, "n": 2},
            "passion": {"value": "moderate", "confidence": 0.3, "n": 1},
            "identity": {"value": "peripheral", "confidence": 0.25, "n": 1},
            "requirement": {"value": "neutral", "confidence": 0.5, "n": 1},
            "avoid": False,
        }
        # User changed identity from "peripheral" to "core_strength"
        auto_annotation["identity"] = "core_strength"
        auto_annotation["original_values"] = {
            "relevance": "relevant",
            "passion": "moderate",
            "identity": "peripheral",
            "match_method": "keyword_prior",
            "matched_keyword": "python",
        }

        # Act
        result = capture_feedback(auto_annotation, "save", base_priors)

        # Assert
        python_prior = result["skill_priors"]["python"]
        assert python_prior["identity"]["value"] == "core_strength"
        assert python_prior["identity"]["confidence"] == 0.5  # Reset to neutral

    def test_initializes_new_skill_prior(self, base_priors, auto_annotation):
        """Should initialize skill prior if not exists."""
        # Arrange
        auto_annotation["original_values"]["matched_keyword"] = "python"
        auto_annotation["original_values"]["match_method"] = "keyword_prior"

        # Act
        result = capture_feedback(auto_annotation, "save", base_priors)

        # Assert
        assert "python" in result["skill_priors"]
        assert result["skill_priors"]["python"]["relevance"]["value"] is None
        assert result["skill_priors"]["python"]["avoid"] is False


class TestAggregateDimension:
    """Tests for _aggregate_dimension function."""

    def test_returns_default_for_empty_list(self):
        """Should return None value with 0.5 confidence for empty list."""
        # Act
        result = _aggregate_dimension([])

        # Assert
        assert result["value"] is None
        assert result["confidence"] == 0.5
        assert result["n"] == 0

    def test_majority_voting_with_clear_winner(self):
        """Should select most common value and calculate confidence."""
        # Arrange
        values = ["relevant", "relevant", "relevant", "tangential"]

        # Act
        result = _aggregate_dimension(values)

        # Assert
        assert result["value"] == "relevant"
        assert result["confidence"] == 0.75  # 3/4
        assert result["n"] == 4

    def test_majority_voting_with_tie(self):
        """Should select one of tied values (first in Counter order)."""
        # Arrange
        values = ["relevant", "tangential"]

        # Act
        result = _aggregate_dimension(values)

        # Assert
        assert result["value"] in ["relevant", "tangential"]
        assert result["confidence"] == 0.5  # 1/2
        assert result["n"] == 2

    def test_single_value(self):
        """Should return 100% confidence for single value."""
        # Arrange
        values = ["core_strength"]

        # Act
        result = _aggregate_dimension(values)

        # Assert
        assert result["value"] == "core_strength"
        assert result["confidence"] == 1.0
        assert result["n"] == 1

    def test_rounds_confidence_to_three_decimals(self):
        """Should round confidence to 3 decimal places."""
        # Arrange
        values = ["a", "a", "b", "b", "b", "c"]  # 3/6 = 0.5

        # Act
        result = _aggregate_dimension(values)

        # Assert
        assert result["value"] == "b"
        assert isinstance(result["confidence"], float)
        # Verify rounding (3 decimals)
        assert len(str(result["confidence"]).split(".")[-1]) <= 3


class TestGetPriorsStats:
    """Tests for get_priors_stats function."""

    @pytest.fixture
    def sample_priors(self):
        """Sample priors with stats."""
        return {
            "sentence_index": {"count": 500},
            "skill_priors": {"python": {}, "javascript": {}, "aws": {}},
            "stats": {
                "total_suggestions_made": 100,
                "accepted_unchanged": 70,
                "edited": 20,
                "deleted": 10,
                "last_rebuild": "2024-01-01T00:00:00Z",
            },
        }

    def test_calculates_accuracy(self, sample_priors):
        """Should calculate accuracy as accepted_unchanged / total_feedback."""
        # Act
        result = get_priors_stats(sample_priors)

        # Assert
        # 70 accepted / (70 + 20 + 10) = 0.7
        assert result["accuracy"] == 0.7

    def test_returns_zero_accuracy_when_no_feedback(self):
        """Should return 0.0 accuracy when no feedback exists."""
        # Arrange
        priors = {
            "sentence_index": {"count": 0},
            "skill_priors": {},
            "stats": {
                "total_suggestions_made": 10,
                "accepted_unchanged": 0,
                "edited": 0,
                "deleted": 0,
            },
        }

        # Act
        result = get_priors_stats(priors)

        # Assert
        assert result["accuracy"] == 0.0

    def test_includes_all_metrics(self, sample_priors):
        """Should include all expected metrics."""
        # Act
        result = get_priors_stats(sample_priors)

        # Assert
        assert result["total_suggestions"] == 100
        assert result["accepted_unchanged"] == 70
        assert result["edited"] == 20
        assert result["deleted"] == 10
        assert result["annotations_indexed"] == 500
        assert result["skills_tracked"] == 3
        assert "needs_rebuild" in result
        assert result["last_rebuild"] == "2024-01-01T00:00:00Z"

    def test_handles_missing_stats(self):
        """Should handle missing stats gracefully."""
        # Arrange
        priors = {
            "sentence_index": {},
            "skill_priors": {},
            "stats": {},
        }

        # Act
        result = get_priors_stats(priors)

        # Assert
        assert result["accuracy"] == 0.0
        assert result["total_suggestions"] == 0
        assert result["annotations_indexed"] == 0
        assert result["skills_tracked"] == 0


class TestRebuildPriors:
    """Tests for rebuild_priors function."""

    @pytest.fixture
    def mock_load_annotations(self):
        """Mock _load_all_annotations."""
        with patch("src.services.annotation_priors._load_all_annotations") as mock:
            mock.return_value = [
                {
                    "text": "Experience with Python and Django",
                    "relevance": "relevant",
                    "requirement": "must_have",
                    "passion": "moderate",
                    "identity": "core_strength",
                    "job_id": "job1",
                },
                {
                    "text": "Strong Python background required",
                    "relevance": "relevant",
                    "requirement": "must_have",
                    "passion": "high",
                    "identity": "core_strength",
                    "job_id": "job2",
                },
            ]
            yield mock

    @pytest.fixture
    def mock_embeddings(self):
        """Mock _compute_embeddings."""
        with patch("src.services.annotation_priors._compute_embeddings") as mock:
            # Return 2 embeddings of dimension 384
            mock.return_value = np.random.rand(2, 384)
            yield mock

    def test_rebuilds_sentence_index(self, mock_load_annotations, mock_embeddings):
        """Should rebuild sentence_index with embeddings and metadata."""
        # Arrange
        priors = _empty_priors()

        # Act
        result = rebuild_priors(priors)

        # Assert
        assert result["sentence_index"]["count"] == 2
        assert len(result["sentence_index"]["embeddings"]) == 2
        assert len(result["sentence_index"]["texts"]) == 2
        assert len(result["sentence_index"]["metadata"]) == 2
        assert result["sentence_index"]["model"] == "all-MiniLM-L6-v2"
        assert result["sentence_index"]["built_at"] is not None

    def test_recomputes_skill_priors(self, mock_load_annotations, mock_embeddings):
        """Should recompute skill_priors from annotations."""
        # Arrange
        priors = _empty_priors()

        # Act
        with patch("src.services.annotation_priors._get_skill_keywords") as mock_keywords:
            mock_keywords.return_value = ["python", "django"]
            result = rebuild_priors(priors)

        # Assert
        assert "skill_priors" in result
        # Python appears in both annotations
        assert "python" in result["skill_priors"]

    def test_updates_stats(self, mock_load_annotations, mock_embeddings):
        """Should update stats after rebuild."""
        # Arrange
        priors = _empty_priors()
        priors["stats"]["annotations_since_build"] = 50

        # Act
        result = rebuild_priors(priors)

        # Assert
        assert result["stats"]["total_annotations_at_build"] == 2
        assert result["stats"]["annotations_since_build"] == 0
        assert result["stats"]["last_rebuild"] is not None

    def test_increments_version(self, mock_load_annotations, mock_embeddings):
        """Should increment version number."""
        # Arrange
        priors = _empty_priors()
        original_version = priors["version"]

        # Act
        result = rebuild_priors(priors)

        # Assert
        assert result["version"] == original_version + 1

    def test_handles_no_annotations(self):
        """Should handle case with no annotations gracefully."""
        # Arrange
        priors = _empty_priors()

        # Act
        with patch("src.services.annotation_priors._load_all_annotations") as mock_load:
            mock_load.return_value = []
            result = rebuild_priors(priors)

        # Assert
        # Should return priors unchanged
        assert result == priors


class TestExtractPrimarySkill:
    """Tests for _extract_primary_skill function."""

    def test_extracts_first_matching_skill(self):
        """Should extract first matching skill keyword."""
        # Arrange
        text = "Experience with Python and AWS required"

        # Act
        with patch("src.services.annotation_priors._get_skill_keywords") as mock_keywords:
            mock_keywords.return_value = ["python", "aws", "docker"]
            result = _extract_primary_skill(text)

        # Assert
        assert result in ["python", "aws"]

    def test_returns_none_for_no_match(self):
        """Should return None when no skill matches."""
        # Arrange
        text = "General software development"

        # Act
        with patch("src.services.annotation_priors._get_skill_keywords") as mock_keywords:
            mock_keywords.return_value = ["python", "aws", "docker"]
            result = _extract_primary_skill(text)

        # Assert
        assert result is None

    def test_handles_empty_text(self):
        """Should return None for empty text."""
        # Act
        result = _extract_primary_skill("")

        # Assert
        assert result is None


class TestRecomputeSkillPriors:
    """Tests for _recompute_skill_priors function."""

    @pytest.fixture
    def sample_annotations(self):
        """Sample annotations."""
        return [
            {
                "text": "Strong Python programming skills required",
                "relevance": "relevant",
                "passion": "moderate",
                "identity": "core_strength",
                "requirement": "must_have",
            },
            {
                "text": "Python and Django experience preferred",
                "relevance": "relevant",
                "passion": "high",
                "identity": "core_strength",
                "requirement": "nice_to_have",
            },
            {
                "text": "Proficiency in AWS cloud services",
                "relevance": "relevant",
                "passion": None,
                "identity": "peripheral",
                "requirement": "must_have",
            },
        ]

    def test_aggregates_skill_priors(self, sample_annotations):
        """Should aggregate priors for skills found in annotations."""
        # Act
        with patch("src.services.annotation_priors._get_skill_keywords") as mock_keywords:
            mock_keywords.return_value = ["python", "django", "aws"]
            result = _recompute_skill_priors(sample_annotations)

        # Assert
        assert "python" in result
        assert "aws" in result
        # Python appears in 2 annotations with "relevant" relevance
        assert result["python"]["relevance"]["value"] == "relevant"
        assert result["python"]["relevance"]["n"] == 2

    def test_avoids_skill_defaults_to_false(self, sample_annotations):
        """Should set avoid to False by default."""
        # Act
        with patch("src.services.annotation_priors._get_skill_keywords") as mock_keywords:
            mock_keywords.return_value = ["python"]
            result = _recompute_skill_priors(sample_annotations)

        # Assert
        assert result["python"]["avoid"] is False

    def test_handles_empty_annotations(self):
        """Should handle empty annotations list."""
        # Act
        with patch("src.services.annotation_priors._get_skill_keywords") as mock_keywords:
            mock_keywords.return_value = ["python"]
            result = _recompute_skill_priors([])

        # Assert
        assert len(result) == 0
