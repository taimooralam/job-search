"""
Unit tests for src/services/annotation_suggester.py

Tests annotation suggestion matching including:
- Selective generation logic (should_generate_annotation)
- Semantic and keyword-based matching (find_best_match)
- Full annotation generation pipeline (generate_annotations_for_job)
"""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from src.services.annotation_suggester import (
    should_generate_annotation,
    find_best_match,
    _cosine_similarity,
    _extract_keywords,
    _create_annotation,
    MatchResult,
    MatchContext,
    SIMILARITY_THRESHOLD,
    KEYWORD_CONFIDENCE_THRESHOLD,
)


class TestShouldGenerateAnnotation:
    """Tests for should_generate_annotation function."""

    @pytest.fixture
    def master_cv(self):
        """Sample master CV data."""
        return {
            "jd_signals": {
                "Leadership": ["team leadership", "mentoring", "hiring"],
                "Technical": ["system design", "architecture", "scalability"],
            },
            "hard_skills": {"Python", "AWS", "Docker", "Kubernetes"},
            "soft_skills": {"Communication", "Problem Solving", "Leadership"},
            "skill_aliases": {
                "Python": ["python3", "py"],
                "AWS": ["amazon web services", "ec2"],
            },
            "keywords": set(),
        }

    @pytest.fixture
    def priors(self):
        """Sample priors document."""
        return {
            "skill_priors": {
                "machine learning": {
                    "relevance": {"value": "relevant", "confidence": 0.8, "n": 5},
                    "avoid": False,
                },
                "java": {
                    "relevance": {"value": "relevant", "confidence": 0.4, "n": 2},
                    "avoid": False,
                },
                "php": {
                    "relevance": {"value": "relevant", "confidence": 0.7, "n": 3},
                    "avoid": True,  # User marked to avoid
                },
            }
        }

    def test_matches_jd_signal(self, master_cv, priors):
        """Should match JD signals from taxonomy."""
        # Arrange
        jd_item = "Responsible for team leadership and hiring decisions"

        # Act
        should_gen, context = should_generate_annotation(jd_item, master_cv, priors)

        # Assert
        assert should_gen is True
        assert context is not None
        assert context.type == "jd_signal"
        assert context.match in ["team leadership", "hiring"]
        assert context.source == "taxonomy"
        assert context.section == "Leadership"

    def test_matches_hard_skill(self, master_cv, priors):
        """Should match hard skills from role metadata."""
        # Arrange
        jd_item = "Strong Python programming experience required"

        # Act
        should_gen, context = should_generate_annotation(jd_item, master_cv, priors)

        # Assert
        assert should_gen is True
        assert context.type == "hard_skill"
        assert context.match == "Python"
        assert context.source == "master_cv"

    def test_matches_soft_skill(self, master_cv, priors):
        """Should match soft skills from role metadata."""
        # Arrange
        jd_item = "Excellent communication and problem solving abilities"

        # Act
        should_gen, context = should_generate_annotation(jd_item, master_cv, priors)

        # Assert
        assert should_gen is True
        assert context.type == "soft_skill"
        assert context.match in ["Communication", "Problem Solving"]
        assert context.source == "master_cv"

    def test_matches_learned_prior(self, master_cv, priors):
        """Should match learned priors with high confidence."""
        # Arrange
        jd_item = "Machine learning expertise for recommendation systems"

        # Act
        should_gen, context = should_generate_annotation(jd_item, master_cv, priors)

        # Assert
        assert should_gen is True
        assert context.type == "prior"
        assert context.match == "machine learning"
        assert context.source == "priors"

    def test_skips_low_confidence_priors(self, master_cv, priors):
        """Should skip priors with confidence <= 0.5."""
        # Arrange
        jd_item = "Java development experience preferred"

        # Act
        should_gen, context = should_generate_annotation(jd_item, master_cv, priors)

        # Assert
        # Java prior has confidence 0.4, should not match
        assert should_gen is False
        assert context is None

    def test_skips_avoided_skills(self, master_cv, priors):
        """Should skip skills marked as avoid in priors."""
        # Arrange
        jd_item = "PHP backend development experience"

        # Act
        should_gen, context = should_generate_annotation(jd_item, master_cv, priors)

        # Assert
        # PHP is marked avoid=True in priors
        assert should_gen is False
        assert context is None

    def test_skips_unmatched_items(self, master_cv, priors):
        """Should skip items that don't match any criteria."""
        # Arrange
        jd_item = "General office duties and administrative tasks"

        # Act
        should_gen, context = should_generate_annotation(jd_item, master_cv, priors)

        # Assert
        assert should_gen is False
        assert context is None

    def test_case_insensitive_matching(self, master_cv, priors):
        """Should perform case-insensitive matching."""
        # Arrange
        jd_item = "PYTHON PROGRAMMING AND DOCKER CONTAINERIZATION"

        # Act
        should_gen, context = should_generate_annotation(jd_item, master_cv, priors)

        # Assert
        assert should_gen is True
        assert context.match in ["Python", "Docker"]


class TestFindBestMatch:
    """Tests for find_best_match function."""

    @pytest.fixture
    def priors_with_index(self):
        """Priors with populated sentence index."""
        return {
            "sentence_index": {
                "embeddings": [
                    [0.1] * 384,  # Embedding 1
                    [0.2] * 384,  # Embedding 2
                    [0.3] * 384,  # Embedding 3
                ],
                "texts": [
                    "Experience with Python and Django",
                    "AWS cloud architecture expertise",
                    "Team leadership and mentoring",
                ],
                "metadata": [
                    {
                        "relevance": "relevant",
                        "requirement": "must_have",
                        "passion": "moderate",
                        "identity": "core_strength",
                        "job_id": "job1",
                    },
                    {
                        "relevance": "relevant",
                        "requirement": "nice_to_have",
                        "passion": "low",
                        "identity": "peripheral",
                        "job_id": "job2",
                    },
                    {
                        "relevance": "relevant",
                        "requirement": "must_have",
                        "passion": "high",
                        "identity": "core_strength",
                        "job_id": "job3",
                    },
                ],
                "built_at": "2024-01-01T00:00:00Z",
                "model": "all-MiniLM-L6-v2",
                "count": 3,
            },
            "skill_priors": {
                "python": {
                    "relevance": {"value": "relevant", "confidence": 0.8, "n": 10},
                    "requirement": {"value": "must_have", "confidence": 0.7, "n": 8},
                    "passion": {"value": "moderate", "confidence": 0.6, "n": 5},
                    "identity": {"value": "core_strength", "confidence": 0.9, "n": 12},
                    "avoid": False,
                },
                "aws": {
                    "relevance": {"value": "relevant", "confidence": 0.75, "n": 8},
                    "requirement": {"value": "nice_to_have", "confidence": 0.65, "n": 6},
                    "passion": {"value": "low", "confidence": 0.55, "n": 4},
                    "identity": {"value": "peripheral", "confidence": 0.5, "n": 3},
                    "avoid": False,
                },
            },
        }

    @pytest.fixture
    def mock_embedding_model(self):
        """Mock SentenceTransformer model."""
        mock_model = MagicMock()
        # Return a random embedding
        mock_model.encode.return_value = np.random.rand(384)
        return mock_model

    def test_matches_via_sentence_similarity(self, priors_with_index, mock_embedding_model):
        """Should match via sentence similarity when above threshold."""
        # Arrange
        jd_item = "Strong Python and Django background required"

        # Mock cosine similarity to return high score for first embedding
        with patch("src.services.annotation_suggester._cosine_similarity") as mock_cosine:
            mock_cosine.return_value = np.array([0.9, 0.5, 0.3])  # First match > threshold

            # Act
            result = find_best_match(jd_item, priors_with_index, mock_embedding_model)

        # Assert
        assert result is not None
        assert result.method == "sentence_similarity"
        assert result.relevance == "relevant"
        assert result.requirement == "must_have"
        assert result.passion == "moderate"
        assert result.identity == "core_strength"
        assert result.confidence == 0.9
        assert result.matched_text == "Experience with Python and Django"
        assert result.matched_score == 0.9

    def test_falls_back_to_keyword_prior(self, priors_with_index, mock_embedding_model):
        """Should fall back to keyword prior when similarity below threshold."""
        # Arrange
        jd_item = "AWS cloud experience required"

        # Mock cosine similarity to return low scores
        with patch("src.services.annotation_suggester._cosine_similarity") as mock_cosine:
            mock_cosine.return_value = np.array([0.5, 0.6, 0.4])  # All below threshold

            # Act
            result = find_best_match(jd_item, priors_with_index, mock_embedding_model)

        # Assert
        assert result is not None
        assert result.method == "keyword_prior"
        assert result.relevance == "relevant"
        assert result.requirement == "nice_to_have"
        assert result.confidence < 0.75  # Discounted
        assert result.matched_keyword == "aws"

    def test_skips_low_confidence_keyword_priors(self, priors_with_index, mock_embedding_model):
        """Should skip keyword priors with confidence below threshold."""
        # Arrange
        jd_item = "Low confidence skill mentioned here"
        # Add low confidence skill prior
        priors_with_index["skill_priors"]["skill"] = {
            "relevance": {"value": "relevant", "confidence": 0.3, "n": 1},
            "avoid": False,
        }

        # Mock cosine similarity to return low scores
        with patch("src.services.annotation_suggester._cosine_similarity") as mock_cosine:
            mock_cosine.return_value = np.array([0.5, 0.5, 0.5])

            # Act
            result = find_best_match(jd_item, priors_with_index, mock_embedding_model)

        # Assert
        # Should return None since keyword confidence too low
        assert result is None

    def test_returns_none_when_no_embeddings(self):
        """Should return None when sentence index has no embeddings."""
        # Arrange
        priors = {
            "sentence_index": {"embeddings": []},
            "skill_priors": {},
        }
        jd_item = "Some job requirement"

        # Act
        result = find_best_match(jd_item, priors)

        # Assert
        assert result is None

    def test_handles_sentence_similarity_error(self, priors_with_index, mock_embedding_model):
        """Should handle errors in sentence similarity gracefully."""
        # Arrange
        jd_item = "Python development"

        # Mock encode to raise exception
        mock_embedding_model.encode.side_effect = Exception("Model error")

        # Act
        result = find_best_match(jd_item, priors_with_index, mock_embedding_model)

        # Assert
        # Should fall back to keyword matching
        assert result is not None
        assert result.method == "keyword_prior"


class TestCosineSimilarity:
    """Tests for _cosine_similarity function."""

    def test_computes_similarity_correctly(self):
        """Should compute cosine similarity between vector and matrix."""
        # Arrange
        vec = np.array([1.0, 0.0, 0.0])
        matrix = np.array([
            [1.0, 0.0, 0.0],  # Identical vector (similarity = 1.0)
            [0.0, 1.0, 0.0],  # Orthogonal (similarity = 0.0)
            [-1.0, 0.0, 0.0], # Opposite (similarity = -1.0)
        ])

        # Act
        result = _cosine_similarity(vec, matrix)

        # Assert
        assert len(result) == 3
        assert abs(result[0] - 1.0) < 0.01
        assert abs(result[1] - 0.0) < 0.01
        assert abs(result[2] - (-1.0)) < 0.01

    def test_handles_zero_vectors(self):
        """Should handle zero vectors without crashing."""
        # Arrange
        vec = np.array([0.0, 0.0, 0.0])
        matrix = np.array([[1.0, 2.0, 3.0]])

        # Act
        result = _cosine_similarity(vec, matrix)

        # Assert
        # Should return 0 due to epsilon in normalization
        assert len(result) == 1
        assert abs(result[0]) < 0.01


class TestExtractKeywords:
    """Tests for _extract_keywords function."""

    def test_extracts_words_longer_than_3_chars(self):
        """Should extract words with 3+ characters."""
        # Arrange
        text = "Python or AWS cloud expertise required"

        # Act
        result = _extract_keywords(text)

        # Assert
        assert "python" in result
        assert "aws" in result
        assert "cloud" in result
        assert "or" not in result  # Only 2 chars
        assert len([k for k in result if len(k) < 3]) == 0

    def test_returns_lowercase(self):
        """Should convert all keywords to lowercase."""
        # Arrange
        text = "Python AWS Docker"

        # Act
        result = _extract_keywords(text)

        # Assert
        assert all(k.islower() for k in result)

    def test_deduplicates_keywords(self):
        """Should deduplicate keywords while preserving order."""
        # Arrange
        text = "Python Python Python AWS"

        # Act
        result = _extract_keywords(text)

        # Assert
        assert result.count("python") == 1
        assert result.index("python") < result.index("aws")

    def test_handles_special_characters(self):
        """Should handle text with special characters."""
        # Arrange
        text = "Python, AWS & Docker (containerization)"

        # Act
        result = _extract_keywords(text)

        # Assert
        assert "python" in result
        assert "aws" in result
        assert "docker" in result
        assert "containerization" in result


class TestCreateAnnotation:
    """Tests for _create_annotation function."""

    @pytest.fixture
    def match_result(self):
        """Sample MatchResult."""
        return MatchResult(
            relevance="relevant",
            requirement="must_have",
            passion="moderate",
            identity="core_strength",
            confidence=0.85,
            method="sentence_similarity",
            matched_text="Python development experience",
            matched_keyword=None,
            matched_score=0.85,
        )

    @pytest.fixture
    def match_context(self):
        """Sample MatchContext."""
        return MatchContext(
            type="hard_skill",
            match="Python",
            source="master_cv",
            section=None,
        )

    def test_creates_annotation_with_match_result(self, match_result, match_context):
        """Should create annotation with values from match result."""
        # Arrange
        text = "Strong Python programming required"
        section = "requirements"

        # Act
        result = _create_annotation(text, section, match_result, match_context, None)

        # Assert
        assert result["target"]["text"] == text
        assert result["target"]["section"] == section
        assert result["relevance"] == "relevant"
        assert result["requirement_type"] == "must_have"
        assert result["passion"] == "moderate"
        assert result["identity"] == "core_strength"
        assert result["source"] == "auto_generated"
        assert result["feedback_captured"] is False

    def test_stores_original_values(self, match_result, match_context):
        """Should store original values for feedback tracking."""
        # Act
        result = _create_annotation("text", "section", match_result, match_context, None)

        # Assert
        orig = result["original_values"]
        assert orig["relevance"] == "relevant"
        assert orig["confidence"] == 0.85
        assert orig["match_method"] == "sentence_similarity"
        assert orig["matched_text"] == "Python development experience"

    def test_uses_section_defaults_when_no_match(self, match_context):
        """Should use section-based defaults when no match result."""
        # Act
        result = _create_annotation(
            "text",
            "responsibilities",
            match_result=None,
            match_ctx=match_context,
            item_dict=None,
        )

        # Assert
        assert result["relevance"] == "relevant"
        assert result["requirement_type"] == "must_have"
        assert result["original_values"]["match_method"] == "default"

    def test_includes_position_info_when_available(self, match_result, match_context):
        """Should include char_start/char_end when provided in item_dict."""
        # Arrange
        item_dict = {
            "text": "text",
            "char_start": 100,
            "char_end": 150,
        }

        # Act
        result = _create_annotation("text", "section", match_result, match_context, item_dict)

        # Assert
        assert result["target"]["char_start"] == 100
        assert result["target"]["char_end"] == 150

    def test_generates_unique_id(self, match_result, match_context):
        """Should generate unique annotation ID."""
        # Act
        result1 = _create_annotation("text", "section", match_result, match_context, None)
        result2 = _create_annotation("text", "section", match_result, match_context, None)

        # Assert
        assert result1["id"] != result2["id"]
        assert result1["id"].startswith("ann_")
