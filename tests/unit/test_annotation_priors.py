"""
Unit tests for src/services/annotation_priors.py

Tests priors management including:
- Loading and saving priors from MongoDB
- Rebuilding sentence index and skill priors
- Capturing feedback from user edits
- Computing statistics and rebuild triggers
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.services.annotation_priors import (
    CHUNK_SIZE,
    MAX_EMBEDDING_ANNOTATIONS,
    PRIORS_DOC_ID,
    DeletionResponse,
    _aggregate_dimension,
    _delete_old_chunks,
    _EmbeddingCache,
    _empty_priors,
    _extract_primary_skill,
    _recompute_skill_priors,
    _write_embedding_chunks,
    capture_feedback,
    determine_deletion_response,
    get_owned_skills,
    get_priors_stats,
    load_priors,
    load_sentence_index_from_chunks,
    migrate_inline_to_chunks,
    rebuild_priors,
    save_priors,
    should_rebuild_priors,
)


class TestLoadPriors:
    """Tests for load_priors function."""

    @pytest.fixture(autouse=True)
    def reset_repo(self):
        """Reset repository singleton before each test."""
        from src.common.repositories import reset_priors_repository
        reset_priors_repository()
        yield
        reset_priors_repository()

    @pytest.fixture
    def mock_repo(self):
        """Mock priors repository."""
        mock_repository = MagicMock()
        # Patch at both re-export and source config module to ensure the mock
        # intercepts under parallel test execution (pytest-xdist)
        with patch("src.common.repositories.get_priors_repository", return_value=mock_repository), \
             patch("src.common.repositories.config.get_priors_repository", return_value=mock_repository):
            yield mock_repository

    def test_loads_existing_priors(self, mock_repo):
        """Should load priors document from MongoDB when it exists."""
        # Arrange
        # Include "embeddings" key to prevent load_sentence_index_from_chunks()
        # from being called (which would try to connect to real MongoDB)
        existing_priors = {
            "_id": PRIORS_DOC_ID,
            "version": 2,
            "sentence_index": {"count": 100, "embeddings": [[0.1, 0.2]], "texts": ["test"], "metadata": [{}]},
            "skill_priors": {"python": {}},
            "stats": {"total_annotations_at_build": 100},
        }
        mock_repo.find_one.return_value = existing_priors

        # Act
        result = load_priors()

        # Assert
        mock_repo.find_one.assert_called_once_with({"_id": PRIORS_DOC_ID})
        assert result["_id"] == PRIORS_DOC_ID
        assert result["version"] == 2
        assert result["sentence_index"]["count"] == 100

    def test_creates_empty_priors_when_not_exists(self, mock_repo):
        """Should create and insert empty priors when none exists."""
        # Arrange
        mock_repo.find_one.return_value = None

        # Act
        result = load_priors()

        # Assert
        mock_repo.find_one.assert_called_once_with({"_id": PRIORS_DOC_ID})
        mock_repo.insert_one.assert_called_once()
        assert result["_id"] == PRIORS_DOC_ID
        assert result["version"] == 1
        assert result["sentence_index"]["count"] == 0
        assert result["skill_priors"] == {}
        assert result["stats"]["total_annotations_at_build"] == 0

    def test_handles_mongodb_error_gracefully(self, mock_repo):
        """Should return empty priors on MongoDB error."""
        # Arrange
        mock_repo.find_one.side_effect = Exception("Connection failed")

        # Act
        result = load_priors()

        # Assert
        assert result["_id"] == PRIORS_DOC_ID
        assert result["version"] == 1
        assert result["sentence_index"]["count"] == 0


class TestSavePriors:
    """Tests for save_priors function."""

    @pytest.fixture(autouse=True)
    def reset_repo(self):
        """Reset repository singleton before each test."""
        from src.common.repositories import reset_priors_repository
        reset_priors_repository()
        yield
        reset_priors_repository()

    @pytest.fixture
    def mock_repo(self):
        """Mock priors repository."""
        from src.common.repositories import WriteResult
        mock_repository = MagicMock()
        # Default return value for replace_one
        mock_repository.replace_one.return_value = WriteResult(matched_count=1, modified_count=1)
        # Patch at the source module since the import happens inside the function
        with patch("src.common.repositories.get_priors_repository", return_value=mock_repository):
            yield mock_repository

    @pytest.fixture
    def sample_priors(self):
        """Sample priors document."""
        return _empty_priors()

    def test_saves_priors_with_upsert(self, mock_repo, sample_priors):
        """Should save priors using replace_one with upsert=True."""
        # Act
        result = save_priors(sample_priors)

        # Assert
        mock_repo.replace_one.assert_called_once()
        call_args = mock_repo.replace_one.call_args
        assert call_args[0][0] == {"_id": PRIORS_DOC_ID}
        assert call_args[1]["upsert"] is True
        assert result is True
        # Saved doc should have stripped embeddings
        saved_doc = call_args[0][1]
        assert saved_doc["sentence_index"]["embeddings"] == []

    def test_updates_timestamp_on_save(self, mock_repo, sample_priors):
        """Should update updated_at timestamp when saving."""
        # Arrange
        import time
        original_timestamp = sample_priors["updated_at"]
        # Force a measurable gap so save_priors's datetime.now() falls in a
        # later microsecond than the fixture's _empty_priors() call. Without
        # this the test is flaky on fast machines where both timestamps land
        # in the same microsecond.
        time.sleep(0.001)

        # Act
        save_priors(sample_priors)

        # Assert
        assert sample_priors["updated_at"] != original_timestamp
        # Verify it's a valid ISO timestamp
        datetime.fromisoformat(sample_priors["updated_at"].replace("Z", "+00:00"))

    def test_handles_mongodb_error_on_save(self, mock_repo, sample_priors):
        """Should return False on MongoDB error."""
        # Arrange
        mock_repo.replace_one.side_effect = Exception("Write failed")

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
        """Should rebuild when no embeddings exist and count is 0."""
        # Arrange
        base_priors["sentence_index"]["embeddings"] = []
        base_priors["sentence_index"]["count"] = 0

        # Act
        result = should_rebuild_priors(base_priors)

        # Assert
        assert result is True

    def test_no_rebuild_when_chunked_format(self, base_priors):
        """Should NOT rebuild when embeddings empty but count > 0 (chunked format)."""
        # Arrange - chunked format: embeddings stored in embedding_chunks collection
        base_priors["sentence_index"]["embeddings"] = []
        base_priors["sentence_index"]["count"] = 5000

        # Act
        result = should_rebuild_priors(base_priors)

        # Assert
        assert result is False

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

    def test_marks_skill_as_avoid_on_delete_full_learning(self, base_priors, auto_annotation):
        """Should mark skill as avoid when annotation deleted from requirements section and user doesn't own skill."""
        # Arrange - use a skill the user doesn't own, in requirements section
        auto_annotation["original_values"]["matched_keyword"] = "rust"
        auto_annotation["original_values"]["match_method"] = "keyword_prior"
        auto_annotation["target"]["text"] = "Experience with Rust programming"
        auto_annotation["target"]["section"] = "requirements"  # Triggers FULL_LEARNING for missing skills

        # Act
        result = capture_feedback(auto_annotation, "delete", base_priors)

        # Assert - FULL_LEARNING applies: avoid=True, 0.3x penalty
        assert "rust" in result["skill_priors"]
        assert result["skill_priors"]["rust"]["avoid"] is True
        assert result["stats"]["deleted"] == 1
        assert result["stats"]["deleted_full"] == 1

    def test_soft_penalty_on_delete_unknown_section(self, base_priors, auto_annotation):
        """Should apply soft penalty (0.8x) when section is unknown."""
        # Arrange - no section means unknown, defaults to SOFT_PENALTY
        base_priors["skill_priors"]["python"] = {
            "relevance": {"value": "relevant", "confidence": 0.8, "n": 5},
            "passion": {"value": "moderate", "confidence": 0.7, "n": 3},
            "identity": {"value": "core", "confidence": 0.9, "n": 4},
            "requirement": {"value": "neutral", "confidence": 0.6, "n": 2},
            "avoid": False,
        }
        auto_annotation["original_values"]["matched_keyword"] = "python"
        auto_annotation["original_values"]["match_method"] = "keyword_prior"
        # No section in target -> unknown section -> SOFT_PENALTY

        # Act
        result = capture_feedback(auto_annotation, "delete", base_priors)

        # Assert - SOFT_PENALTY applies: avoid=False, 0.8x penalty
        python_prior = result["skill_priors"]["python"]
        assert python_prior["avoid"] is False  # Soft penalty doesn't set avoid
        assert python_prior["relevance"]["confidence"] == 0.8 * 0.8
        assert python_prior["passion"]["confidence"] == 0.7 * 0.8
        assert python_prior["identity"]["confidence"] == 0.9 * 0.8
        assert result["stats"]["deleted_soft"] == 1

    def test_no_learning_on_delete_from_benefits_section(self, base_priors, auto_annotation):
        """Should not learn when annotation deleted from non-skill sections like benefits."""
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
        auto_annotation["target"]["section"] = "benefits"  # NO_LEARNING section

        # Act
        result = capture_feedback(auto_annotation, "delete", base_priors)

        # Assert - NO_LEARNING: confidence unchanged
        python_prior = result["skill_priors"]["python"]
        assert python_prior["avoid"] is False
        assert python_prior["relevance"]["confidence"] == 0.8  # Unchanged
        assert python_prior["passion"]["confidence"] == 0.7  # Unchanged
        assert result["stats"]["deleted_no_learning"] == 1

    def test_full_learning_on_delete_from_requirements(self, base_priors, auto_annotation):
        """Should apply full learning (0.3x + avoid) when skill gap detected in requirements."""
        # Arrange - Use confidence < 0.7 so golang is NOT treated as "owned"
        # (get_owned_skills includes high-confidence priors >= 0.7 as owned)
        base_priors["skill_priors"]["golang"] = {
            "relevance": {"value": "relevant", "confidence": 0.6, "n": 5},
            "passion": {"value": "moderate", "confidence": 0.5, "n": 3},
            "identity": {"value": "core", "confidence": 0.6, "n": 4},
            "requirement": {"value": "neutral", "confidence": 0.5, "n": 2},
            "avoid": False,
        }
        auto_annotation["original_values"]["matched_keyword"] = "golang"
        auto_annotation["original_values"]["match_method"] = "keyword_prior"
        auto_annotation["target"]["text"] = "Experience with Golang"
        auto_annotation["target"]["section"] = "requirements"  # FULL_LEARNING for unowned skills

        # Act
        result = capture_feedback(auto_annotation, "delete", base_priors)

        # Assert - FULL_LEARNING applies: avoid=True, 0.3x penalty
        golang_prior = result["skill_priors"]["golang"]
        assert golang_prior["avoid"] is True
        assert golang_prior["relevance"]["confidence"] == 0.6 * 0.3
        assert golang_prior["passion"]["confidence"] == 0.5 * 0.3
        assert golang_prior["identity"]["confidence"] == 0.6 * 0.3
        assert result["stats"]["deleted_full"] == 1

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

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset embedding cache before each test."""
        _EmbeddingCache.get().invalidate()
        yield
        _EmbeddingCache.get().invalidate()

    @pytest.fixture
    def mock_chunks_repo(self):
        """Mock embedding chunks repository."""
        from src.common.repositories import WriteResult
        mock_repository = MagicMock()
        mock_repository.insert_many.return_value = WriteResult(matched_count=0, modified_count=2)
        mock_repository.delete_many.return_value = 0
        with patch("src.common.repositories.get_embedding_chunks_repository", return_value=mock_repository):
            yield mock_repository

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

    def test_rebuilds_sentence_index(self, mock_load_annotations, mock_embeddings, mock_chunks_repo):
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

    def test_writes_chunks(self, mock_load_annotations, mock_embeddings, mock_chunks_repo):
        """Should write embedding chunks to the chunks collection."""
        # Arrange
        priors = _empty_priors()

        # Act
        rebuild_priors(priors)

        # Assert
        mock_chunks_repo.insert_many.assert_called_once()
        chunks = mock_chunks_repo.insert_many.call_args[0][0]
        assert len(chunks) == 1  # 2 annotations < CHUNK_SIZE, so 1 chunk
        assert chunks[0]["version"] == 2  # version incremented from 1
        assert chunks[0]["chunk_index"] == 0
        assert chunks[0]["count"] == 2

    def test_deletes_old_chunks(self, mock_load_annotations, mock_embeddings, mock_chunks_repo):
        """Should delete old version chunks after rebuild."""
        # Arrange
        priors = _empty_priors()

        # Act
        rebuild_priors(priors)

        # Assert
        mock_chunks_repo.delete_many.assert_called_once_with({"version": {"$lt": 2}})

    def test_updates_cache(self, mock_load_annotations, mock_embeddings, mock_chunks_repo):
        """Should update the in-memory embedding cache after rebuild."""
        # Arrange
        priors = _empty_priors()

        # Act
        result = rebuild_priors(priors)

        # Assert
        cache = _EmbeddingCache.get()
        assert cache.is_valid(result["version"])
        assert cache.sentence_index["count"] == 2

    def test_recomputes_skill_priors(self, mock_load_annotations, mock_embeddings, mock_chunks_repo):
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

    def test_updates_stats(self, mock_load_annotations, mock_embeddings, mock_chunks_repo):
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

    def test_increments_version(self, mock_load_annotations, mock_embeddings, mock_chunks_repo):
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


class TestDetermineDeleteResponse:
    """Tests for determine_deletion_response function."""

    def test_no_learning_for_about_company_section(self):
        """Should return NO_LEARNING for about_company section."""
        response, reason = determine_deletion_response("python", "about_company", {"python"})
        assert response == DeletionResponse.NO_LEARNING
        assert "non_skill_section" in reason

    def test_no_learning_for_benefits_section(self):
        """Should return NO_LEARNING for benefits section."""
        response, reason = determine_deletion_response("python", "benefits", {"python"})
        assert response == DeletionResponse.NO_LEARNING
        assert "benefits" in reason

    def test_no_learning_for_nice_to_have_section(self):
        """Should return NO_LEARNING for nice_to_have section."""
        response, reason = determine_deletion_response("any_skill", "nice_to_have", set())
        assert response == DeletionResponse.NO_LEARNING

    def test_full_learning_for_requirements_without_skill(self):
        """Should return FULL_LEARNING when user doesn't own skill in requirements."""
        response, reason = determine_deletion_response("rust", "requirements", {"python"})
        assert response == DeletionResponse.FULL_LEARNING
        assert reason == "skill_gap"

    def test_soft_penalty_for_requirements_with_skill(self):
        """Should return SOFT_PENALTY when user owns skill in requirements."""
        response, reason = determine_deletion_response("python", "requirements", {"python"})
        assert response == DeletionResponse.SOFT_PENALTY
        assert reason == "has_skill_noise"

    def test_full_learning_for_qualifications_without_skill(self):
        """Should return FULL_LEARNING for qualifications when user doesn't own skill."""
        response, reason = determine_deletion_response("golang", "qualifications", {"python"})
        assert response == DeletionResponse.FULL_LEARNING
        assert reason == "skill_gap"

    def test_no_learning_for_responsibilities_with_skill(self):
        """Should return NO_LEARNING for responsibilities when user owns skill."""
        response, reason = determine_deletion_response("python", "responsibilities", {"python"})
        assert response == DeletionResponse.NO_LEARNING
        assert reason == "responsibility_has_skill"

    def test_soft_penalty_for_responsibilities_without_skill(self):
        """Should return SOFT_PENALTY for responsibilities when user doesn't own skill."""
        response, reason = determine_deletion_response("rust", "responsibilities", {"python"})
        assert response == DeletionResponse.SOFT_PENALTY
        assert reason == "responsibility_uncertain"

    def test_soft_penalty_for_unknown_section(self):
        """Should return SOFT_PENALTY for unknown sections."""
        response, reason = determine_deletion_response("python", "unknown_section", {"python"})
        assert response == DeletionResponse.SOFT_PENALTY
        assert "unknown_section" in reason

    def test_handles_none_section(self):
        """Should handle None section gracefully."""
        response, reason = determine_deletion_response("python", None, {"python"})
        assert response == DeletionResponse.SOFT_PENALTY

    def test_handles_empty_skill(self):
        """Should handle empty skill string."""
        response, reason = determine_deletion_response("", "requirements", {"python"})
        # Empty skill means no skill to check ownership, so SOFT_PENALTY
        assert response == DeletionResponse.SOFT_PENALTY

    def test_case_insensitive_section_matching(self):
        """Should match sections case-insensitively."""
        response, reason = determine_deletion_response("python", "BENEFITS", {"python"})
        assert response == DeletionResponse.NO_LEARNING

    def test_case_insensitive_skill_matching(self):
        """Should match skills case-insensitively."""
        response, reason = determine_deletion_response("Python", "requirements", {"python"})
        assert response == DeletionResponse.SOFT_PENALTY  # User owns Python


class TestGetOwnedSkills:
    """Tests for get_owned_skills function."""

    @pytest.fixture
    def sample_priors(self):
        """Sample priors with some high-confidence skills."""
        return {
            "skill_priors": {
                "python": {
                    "relevance": {"value": "core_strength", "confidence": 0.9, "n": 10},
                    "avoid": False,
                },
                "java": {
                    "relevance": {"value": "relevant", "confidence": 0.5, "n": 2},
                    "avoid": False,
                },
                "rust": {
                    "relevance": {"value": "core_strength", "confidence": 0.8, "n": 5},
                    "avoid": True,  # Should be excluded
                },
            }
        }

    def test_includes_high_confidence_skills(self, sample_priors):
        """Should include skills with confidence >= 0.7."""
        with patch("src.common.master_cv_store.get_metadata", return_value=None):
            # Clear cache to force reload
            import src.services.annotation_priors as priors_module
            priors_module._owned_skills_cache = None

            owned = get_owned_skills(sample_priors)

            assert "python" in owned  # 0.9 >= 0.7
            assert "java" not in owned  # 0.5 < 0.7

    def test_excludes_avoided_skills(self, sample_priors):
        """Should exclude skills marked as avoid even if high confidence."""
        with patch("src.common.master_cv_store.get_metadata", return_value=None):
            import src.services.annotation_priors as priors_module
            priors_module._owned_skills_cache = None

            owned = get_owned_skills(sample_priors)

            assert "rust" not in owned  # Has avoid=True

    def test_includes_skills_from_master_cv(self, sample_priors):
        """Should include skills from master CV metadata."""
        mock_metadata = {
            "roles": [
                {
                    "hard_skills": ["TypeScript", "React"],
                    "soft_skills": ["Leadership"],
                    "keywords": ["Full Stack"],
                }
            ]
        }

        with patch("src.common.master_cv_store.get_metadata", return_value=mock_metadata):
            import src.services.annotation_priors as priors_module
            priors_module._owned_skills_cache = None

            owned = get_owned_skills(sample_priors)

            assert "typescript" in owned
            assert "react" in owned
            assert "leadership" in owned
            assert "full stack" in owned

    def test_handles_missing_metadata_gracefully(self, sample_priors):
        """Should handle errors loading master CV gracefully."""
        with patch("src.common.master_cv_store.get_metadata", side_effect=Exception("DB error")):
            import src.services.annotation_priors as priors_module
            priors_module._owned_skills_cache = None

            # Should not raise, should still return priors-based skills
            owned = get_owned_skills(sample_priors)

            assert "python" in owned

    def test_caches_results(self, sample_priors):
        """Should cache results for performance."""
        with patch("src.common.master_cv_store.get_metadata", return_value=None) as mock_get:
            import src.services.annotation_priors as priors_module
            priors_module._owned_skills_cache = None

            # First call
            owned1 = get_owned_skills(sample_priors)
            # Second call should use cache
            owned2 = get_owned_skills(sample_priors)

            # Metadata should only be called once due to caching
            assert mock_get.call_count == 1
            assert owned1 == owned2

    def test_returns_lowercase_skills(self, sample_priors):
        """Should return all skills in lowercase."""
        mock_metadata = {
            "roles": [{"hard_skills": ["TypeScript", "PYTHON"], "soft_skills": [], "keywords": []}]
        }

        with patch("src.common.master_cv_store.get_metadata", return_value=mock_metadata):
            import src.services.annotation_priors as priors_module
            priors_module._owned_skills_cache = None

            owned = get_owned_skills(sample_priors)

            # All should be lowercase
            for skill in owned:
                assert skill == skill.lower()


# ============================================================================
# CHUNKED STORAGE TESTS
# ============================================================================


class TestEmbeddingCache:
    """Tests for _EmbeddingCache class."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset cache between tests."""
        _EmbeddingCache.get().invalidate()
        yield
        _EmbeddingCache.get().invalidate()

    def test_invalid_by_default(self):
        """Cache should be invalid by default."""
        cache = _EmbeddingCache.get()
        assert not cache.is_valid(1)

    def test_store_and_retrieve(self):
        """Should store and retrieve sentence index by version."""
        cache = _EmbeddingCache.get()
        index = {"embeddings": [[0.1] * 384], "texts": ["test"], "metadata": [], "count": 1}
        cache.store(42, index)
        assert cache.is_valid(42)
        assert cache.sentence_index == index

    def test_invalid_for_different_version(self):
        """Should be invalid when queried with different version."""
        cache = _EmbeddingCache.get()
        cache.store(1, {"count": 1})
        assert not cache.is_valid(2)

    def test_invalidate_clears_cache(self):
        """Should clear cache on invalidate."""
        cache = _EmbeddingCache.get()
        cache.store(1, {"count": 1})
        cache.invalidate()
        assert not cache.is_valid(1)

    def test_singleton_pattern(self):
        """Should return same instance."""
        a = _EmbeddingCache.get()
        b = _EmbeddingCache.get()
        assert a is b


class TestLoadSentenceIndexFromChunks:
    """Tests for load_sentence_index_from_chunks function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset cache between tests."""
        _EmbeddingCache.get().invalidate()
        yield
        _EmbeddingCache.get().invalidate()

    @pytest.fixture
    def mock_chunks_repo(self):
        """Mock embedding chunks repository."""
        mock_repository = MagicMock()
        with patch("src.common.repositories.get_embedding_chunks_repository", return_value=mock_repository):
            yield mock_repository

    def test_loads_and_concatenates_chunks(self, mock_chunks_repo):
        """Should load chunks and concatenate into single SentenceIndex."""
        # Arrange
        mock_chunks_repo.find.return_value = [
            {
                "version": 1,
                "chunk_index": 0,
                "embeddings": [[0.1] * 384, [0.2] * 384],
                "texts": ["text1", "text2"],
                "metadata": [{"relevance": "r1"}, {"relevance": "r2"}],
                "created_at": "2024-01-01T00:00:00Z",
            },
            {
                "version": 1,
                "chunk_index": 1,
                "embeddings": [[0.3] * 384],
                "texts": ["text3"],
                "metadata": [{"relevance": "r3"}],
                "created_at": "2024-01-01T00:00:00Z",
            },
        ]

        # Act
        result = load_sentence_index_from_chunks(1)

        # Assert
        assert result is not None
        assert result["count"] == 3
        assert len(result["embeddings"]) == 3
        assert len(result["texts"]) == 3
        assert result["texts"] == ["text1", "text2", "text3"]

    def test_returns_none_when_no_chunks(self, mock_chunks_repo):
        """Should return None when no chunks found."""
        mock_chunks_repo.find.return_value = []
        result = load_sentence_index_from_chunks(1)
        assert result is None

    def test_caches_result(self, mock_chunks_repo):
        """Should cache result and return from cache on second call."""
        mock_chunks_repo.find.return_value = [
            {
                "version": 1,
                "chunk_index": 0,
                "embeddings": [[0.1] * 384],
                "texts": ["text1"],
                "metadata": [{"relevance": "r1"}],
                "created_at": "2024-01-01T00:00:00Z",
            },
        ]

        # First call loads from repo
        result1 = load_sentence_index_from_chunks(1)
        # Second call should use cache
        result2 = load_sentence_index_from_chunks(1)

        assert result1 == result2
        mock_chunks_repo.find.assert_called_once()  # Only called once

    def test_queries_with_correct_filter_and_sort(self, mock_chunks_repo):
        """Should query with version filter and chunk_index sort."""
        mock_chunks_repo.find.return_value = []
        load_sentence_index_from_chunks(42)

        mock_chunks_repo.find.assert_called_once_with(
            {"version": 42},
            sort=[("chunk_index", 1)],
        )


class TestWriteEmbeddingChunks:
    """Tests for _write_embedding_chunks function."""

    @pytest.fixture
    def mock_chunks_repo(self):
        """Mock embedding chunks repository."""
        from src.common.repositories import WriteResult
        mock_repository = MagicMock()
        mock_repository.insert_many.return_value = WriteResult(matched_count=0, modified_count=1)
        with patch("src.common.repositories.get_embedding_chunks_repository", return_value=mock_repository):
            yield mock_repository

    def test_single_chunk_for_small_data(self, mock_chunks_repo):
        """Should produce 1 chunk for data smaller than CHUNK_SIZE."""
        texts = [f"text{i}" for i in range(100)]
        embeddings = [[0.1] * 384 for _ in range(100)]
        annotations = [
            {"text": f"text{i}", "relevance": "r", "requirement": "m",
             "passion": "n", "identity": "p", "job_id": f"j{i}"}
            for i in range(100)
        ]

        count = _write_embedding_chunks(1, texts, embeddings, annotations)

        assert count == 1
        mock_chunks_repo.insert_many.assert_called_once()
        chunks = mock_chunks_repo.insert_many.call_args[0][0]
        assert len(chunks) == 1
        assert chunks[0]["count"] == 100
        assert chunks[0]["version"] == 1
        assert chunks[0]["chunk_index"] == 0

    def test_multiple_chunks_for_large_data(self, mock_chunks_repo):
        """Should split into multiple chunks when exceeding CHUNK_SIZE."""
        n = CHUNK_SIZE + 500  # 1500 items = 2 chunks
        texts = [f"text{i}" for i in range(n)]
        embeddings = [[0.1] * 384 for _ in range(n)]
        annotations = [
            {"text": f"text{i}", "relevance": "r", "requirement": "m",
             "passion": "n", "identity": "p", "job_id": f"j{i}"}
            for i in range(n)
        ]

        count = _write_embedding_chunks(1, texts, embeddings, annotations)

        assert count == 2
        chunks = mock_chunks_repo.insert_many.call_args[0][0]
        assert chunks[0]["count"] == CHUNK_SIZE
        assert chunks[0]["chunk_index"] == 0
        assert chunks[1]["count"] == 500
        assert chunks[1]["chunk_index"] == 1

    def test_empty_data_writes_nothing(self, mock_chunks_repo):
        """Should not call insert_many for empty data."""
        count = _write_embedding_chunks(1, [], [], [])
        assert count == 0
        mock_chunks_repo.insert_many.assert_not_called()


class TestDeleteOldChunks:
    """Tests for _delete_old_chunks function."""

    @pytest.fixture
    def mock_chunks_repo(self):
        mock_repository = MagicMock()
        mock_repository.delete_many.return_value = 5
        with patch("src.common.repositories.get_embedding_chunks_repository", return_value=mock_repository):
            yield mock_repository

    def test_deletes_older_versions(self, mock_chunks_repo):
        """Should delete chunks with version < current."""
        deleted = _delete_old_chunks(3)
        mock_chunks_repo.delete_many.assert_called_once_with({"version": {"$lt": 3}})
        assert deleted == 5


class TestSavePriorsStripsEmbeddings:
    """Tests that save_priors strips embeddings before saving."""

    @pytest.fixture(autouse=True)
    def reset_repo(self):
        from src.common.repositories import reset_priors_repository
        reset_priors_repository()
        yield
        reset_priors_repository()

    @pytest.fixture
    def mock_repo(self):
        from src.common.repositories import WriteResult
        mock_repository = MagicMock()
        mock_repository.replace_one.return_value = WriteResult(matched_count=1, modified_count=1)
        with patch("src.common.repositories.get_priors_repository", return_value=mock_repository):
            yield mock_repository

    def test_strips_embeddings_from_saved_doc(self, mock_repo):
        """Saved document should have empty embeddings (stored in chunks)."""
        priors = _empty_priors()
        priors["sentence_index"]["embeddings"] = [[0.1] * 384, [0.2] * 384]
        priors["sentence_index"]["texts"] = ["text1", "text2"]
        priors["sentence_index"]["metadata"] = [{"r": 1}, {"r": 2}]
        priors["sentence_index"]["count"] = 2

        save_priors(priors)

        # Check what was actually saved
        saved_doc = mock_repo.replace_one.call_args[0][1]
        assert saved_doc["sentence_index"]["embeddings"] == []
        assert saved_doc["sentence_index"]["texts"] == []
        assert saved_doc["sentence_index"]["metadata"] == []
        assert saved_doc["sentence_index"]["count"] == 2  # Count preserved

    def test_preserves_in_memory_embeddings(self, mock_repo):
        """Original priors dict should retain embeddings in-memory."""
        priors = _empty_priors()
        original_embeddings = [[0.1] * 384, [0.2] * 384]
        priors["sentence_index"]["embeddings"] = original_embeddings

        save_priors(priors)

        # In-memory priors should still have embeddings
        assert priors["sentence_index"]["embeddings"] == original_embeddings


class TestLoadPriorsChunkedFormat:
    """Tests that load_priors hydrates from chunks when in chunked format."""

    @pytest.fixture(autouse=True)
    def reset_repos(self):
        from src.common.repositories import reset_priors_repository
        reset_priors_repository()
        _EmbeddingCache.get().invalidate()
        yield
        reset_priors_repository()
        _EmbeddingCache.get().invalidate()

    def test_hydrates_from_chunks(self):
        """Should load embeddings from chunks when inline embeddings are empty."""
        mock_priors_repo = MagicMock()
        mock_priors_repo.find_one.return_value = {
            "_id": PRIORS_DOC_ID,
            "version": 3,
            "sentence_index": {
                "embeddings": [],
                "texts": [],
                "metadata": [],
                "count": 2,
                "built_at": "2024-01-01T00:00:00Z",
                "model": "all-MiniLM-L6-v2",
            },
            "skill_priors": {},
            "stats": {"total_annotations_at_build": 2},
        }

        mock_chunks_repo = MagicMock()
        mock_chunks_repo.find.return_value = [
            {
                "version": 3,
                "chunk_index": 0,
                "embeddings": [[0.1] * 384, [0.2] * 384],
                "texts": ["text1", "text2"],
                "metadata": [{"relevance": "r1"}, {"relevance": "r2"}],
                "created_at": "2024-01-01T00:00:00Z",
            },
        ]

        with patch("src.common.repositories.get_priors_repository", return_value=mock_priors_repo), \
             patch("src.common.repositories.get_embedding_chunks_repository", return_value=mock_chunks_repo):
            result = load_priors()

        assert len(result["sentence_index"]["embeddings"]) == 2
        assert result["sentence_index"]["texts"] == ["text1", "text2"]
        assert result["sentence_index"]["count"] == 2

    def test_no_hydration_when_inline(self):
        """Should use inline embeddings when they exist (legacy format)."""
        mock_priors_repo = MagicMock()
        inline_embeddings = [[0.5] * 384]
        mock_priors_repo.find_one.return_value = {
            "_id": PRIORS_DOC_ID,
            "version": 1,
            "sentence_index": {
                "embeddings": inline_embeddings,
                "texts": ["inline_text"],
                "metadata": [{"relevance": "r"}],
                "count": 1,
                "built_at": "2024-01-01T00:00:00Z",
                "model": "all-MiniLM-L6-v2",
            },
            "skill_priors": {},
            "stats": {"total_annotations_at_build": 1},
        }

        with patch("src.common.repositories.get_priors_repository", return_value=mock_priors_repo):
            result = load_priors()

        # Should use inline, not try to load chunks
        assert result["sentence_index"]["embeddings"] == inline_embeddings


class TestMigrateInlineToChunks:
    """Tests for migrate_inline_to_chunks function."""

    @pytest.fixture
    def mock_chunks_repo(self):
        from src.common.repositories import WriteResult
        mock_repository = MagicMock()
        mock_repository.insert_many.return_value = WriteResult(matched_count=0, modified_count=1)
        with patch("src.common.repositories.get_embedding_chunks_repository", return_value=mock_repository):
            yield mock_repository

    def test_migrates_inline_embeddings(self, mock_chunks_repo):
        """Should write inline embeddings as chunks."""
        priors = _empty_priors()
        priors["version"] = 5
        priors["sentence_index"]["embeddings"] = [[0.1] * 384, [0.2] * 384]
        priors["sentence_index"]["texts"] = ["text1", "text2"]
        priors["sentence_index"]["metadata"] = [
            {"relevance": "r1", "requirement": "m1", "passion": "p1", "identity": "i1", "job_id": "j1"},
            {"relevance": "r2", "requirement": "m2", "passion": "p2", "identity": "i2", "job_id": "j2"},
        ]

        result = migrate_inline_to_chunks(priors)

        assert result is True
        mock_chunks_repo.insert_many.assert_called_once()
        chunks = mock_chunks_repo.insert_many.call_args[0][0]
        assert chunks[0]["version"] == 5
        assert chunks[0]["count"] == 2

    def test_returns_false_when_already_chunked(self, mock_chunks_repo):
        """Should return False when embeddings are already empty (chunked)."""
        priors = _empty_priors()
        priors["sentence_index"]["embeddings"] = []

        result = migrate_inline_to_chunks(priors)

        assert result is False
        mock_chunks_repo.insert_many.assert_not_called()

    def test_caps_at_max_annotations(self, mock_chunks_repo):
        """Should cap migration at MAX_EMBEDDING_ANNOTATIONS."""
        n = MAX_EMBEDDING_ANNOTATIONS + 500
        priors = _empty_priors()
        priors["sentence_index"]["embeddings"] = [[0.1] * 384] * n
        priors["sentence_index"]["texts"] = [f"text{i}" for i in range(n)]
        priors["sentence_index"]["metadata"] = [
            {"relevance": "r", "requirement": "m", "passion": "p", "identity": "i", "job_id": "j"}
        ] * n

        migrate_inline_to_chunks(priors)

        chunks = mock_chunks_repo.insert_many.call_args[0][0]
        total_count = sum(c["count"] for c in chunks)
        assert total_count == MAX_EMBEDDING_ANNOTATIONS
