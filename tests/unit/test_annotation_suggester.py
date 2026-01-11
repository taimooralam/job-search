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
    infer_requirement_type,
    suggest_keywords_for_item,
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


class TestInferRequirementType:
    """Tests for infer_requirement_type function."""

    def test_matches_qualifications_list_must_have(self):
        """Should return must_have when item matches qualifications list."""
        # Arrange
        jd_item = "5+ years of Python development experience"
        section_type = "requirements"
        extracted_jd = {
            "qualifications": [
                "5+ years of Python development experience",
                "Bachelor's degree in Computer Science",
            ],
            "nice_to_haves": ["AWS certification"],
        }

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "must_have"

    def test_matches_qualifications_with_partial_overlap(self):
        """Should return must_have when >50% word overlap with qualifications."""
        # Arrange
        jd_item = "Python programming experience required"
        section_type = "requirements"
        extracted_jd = {
            "qualifications": [
                "Strong Python programming and development skills",
            ],
            "nice_to_haves": [],
        }

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "must_have"

    def test_matches_nice_to_haves_list(self):
        """Should return nice_to_have when item matches nice_to_haves list."""
        # Arrange
        jd_item = "AWS certification preferred"
        section_type = "requirements"
        extracted_jd = {
            "qualifications": ["5+ years experience"],
            "nice_to_haves": ["AWS certification preferred", "Startup experience"],
        }

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "nice_to_have"

    def test_matches_nice_to_haves_with_partial_overlap(self):
        """Should return nice_to_have when >50% word overlap with nice_to_haves."""
        # Arrange
        jd_item = "Startup experience preferred"  # 3 words
        section_type = "requirements"
        extracted_jd = {
            "qualifications": [],
            "nice_to_haves": ["Startup experience"],  # 2 words, 2/2 = 100% overlap > 50%
        }

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "nice_to_have"

    def test_falls_back_to_section_default_requirements(self):
        """Should use section default when no match in extracted_jd."""
        # Arrange
        jd_item = "Database design skills"
        section_type = "requirements"
        extracted_jd = {
            "qualifications": ["Python experience"],
            "nice_to_haves": ["AWS knowledge"],
        }

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "must_have"  # requirements section default

    def test_falls_back_to_section_default_nice_to_have(self):
        """Should use section default for nice_to_have section."""
        # Arrange
        jd_item = "Some skill mentioned"
        section_type = "nice_to_have"
        extracted_jd = {
            "qualifications": ["Other skill"],
            "nice_to_haves": ["Different skill"],
        }

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "nice_to_have"  # nice_to_have section default

    def test_falls_back_to_section_default_responsibilities(self):
        """Should use must_have for responsibilities section."""
        # Arrange
        jd_item = "Lead technical architecture decisions"
        section_type = "responsibilities"
        extracted_jd = None

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "must_have"

    def test_handles_none_extracted_jd(self):
        """Should use section default when extracted_jd is None."""
        # Arrange
        jd_item = "Any requirement"
        section_type = "requirements"
        extracted_jd = None

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "must_have"

    def test_handles_empty_extracted_jd(self):
        """Should use section default when extracted_jd is empty dict."""
        # Arrange
        jd_item = "Any requirement"
        section_type = "requirements"
        extracted_jd = {}

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "must_have"

    def test_handles_none_qualifications_list(self):
        """Should handle None qualifications list gracefully."""
        # Arrange
        jd_item = "Python skills"
        section_type = "requirements"
        extracted_jd = {
            "qualifications": None,
            "nice_to_haves": None,
        }

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "must_have"

    def test_returns_neutral_for_unknown_section(self):
        """Should return neutral for unknown section types."""
        # Arrange
        jd_item = "Some text"
        section_type = "unknown_section"
        extracted_jd = None

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "neutral"

    def test_prioritizes_qualifications_over_nice_to_haves(self):
        """Should prioritize qualifications when item appears in both lists."""
        # Arrange
        jd_item = "Python experience"
        section_type = "requirements"
        extracted_jd = {
            "qualifications": ["Python experience required"],
            "nice_to_haves": ["Python experience a plus"],
        }

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "must_have"  # Qualifications checked first

    def test_case_insensitive_matching(self):
        """Should perform case-insensitive matching."""
        # Arrange
        jd_item = "PYTHON PROGRAMMING"
        section_type = "requirements"
        extracted_jd = {
            "qualifications": ["python programming experience"],
            "nice_to_haves": [],
        }

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "must_have"

    def test_handles_benefits_section(self):
        """Should return nice_to_have for benefits section."""
        # Arrange
        jd_item = "Health insurance"
        section_type = "benefits"
        extracted_jd = None

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "nice_to_have"

    def test_handles_education_section(self):
        """Should return nice_to_have for education section."""
        # Arrange
        jd_item = "Bachelor's degree"
        section_type = "education"
        extracted_jd = None

        # Act
        result = infer_requirement_type(jd_item, section_type, extracted_jd)

        # Assert
        assert result == "nice_to_have"


class TestSuggestKeywordsForItem:
    """Tests for suggest_keywords_for_item function."""

    def test_returns_matching_keywords_from_top_keywords(self):
        """Should return keywords that appear in the item text."""
        # Arrange
        jd_item = "Experience with Python, Docker, and Kubernetes required"
        extracted_jd = {
            "top_keywords": ["Python", "Docker", "Kubernetes", "AWS", "Terraform"],
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd)

        # Assert
        assert "Python" in result
        assert "Docker" in result
        assert "Kubernetes" in result
        assert "AWS" not in result  # Not in item text
        assert "Terraform" not in result

    def test_respects_max_keywords_limit(self):
        """Should respect max_keywords limit."""
        # Arrange
        jd_item = "Python AWS Docker Kubernetes Terraform experience"
        extracted_jd = {
            "top_keywords": ["Python", "AWS", "Docker", "Kubernetes", "Terraform"],
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd, max_keywords=3)

        # Assert
        assert len(result) == 3
        # Should return first 3 matches in order
        assert result == ["Python", "AWS", "Docker"]

    def test_preserves_top_keywords_order(self):
        """Should preserve order from top_keywords (earlier = more important)."""
        # Arrange
        jd_item = "Kubernetes Docker Python"  # Different order in text
        extracted_jd = {
            "top_keywords": ["Python", "Docker", "Kubernetes"],  # Priority order
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd)

        # Assert
        # Should match top_keywords order, not text order
        assert result == ["Python", "Docker", "Kubernetes"]

    def test_case_insensitive_matching(self):
        """Should perform case-insensitive matching."""
        # Arrange
        jd_item = "PYTHON and docker experience"
        extracted_jd = {
            "top_keywords": ["Python", "Docker", "AWS"],
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd)

        # Assert
        assert "Python" in result
        assert "Docker" in result

    def test_returns_empty_list_when_no_matches(self):
        """Should return empty list when no keywords match."""
        # Arrange
        jd_item = "General office duties"
        extracted_jd = {
            "top_keywords": ["Python", "AWS", "Docker"],
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd)

        # Assert
        assert result == []

    def test_returns_empty_list_when_extracted_jd_none(self):
        """Should return empty list when extracted_jd is None."""
        # Arrange
        jd_item = "Python experience"
        extracted_jd = None

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd)

        # Assert
        assert result == []

    def test_returns_empty_list_when_extracted_jd_empty(self):
        """Should return empty list when extracted_jd is empty dict."""
        # Arrange
        jd_item = "Python experience"
        extracted_jd = {}

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd)

        # Assert
        assert result == []

    def test_handles_none_top_keywords(self):
        """Should handle None top_keywords gracefully."""
        # Arrange
        jd_item = "Python experience"
        extracted_jd = {
            "top_keywords": None,
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd)

        # Assert
        assert result == []

    def test_handles_empty_top_keywords_list(self):
        """Should handle empty top_keywords list."""
        # Arrange
        jd_item = "Python experience"
        extracted_jd = {
            "top_keywords": [],
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd)

        # Assert
        assert result == []

    def test_partial_keyword_matching(self):
        """Should match keywords that are substrings in text."""
        # Arrange
        jd_item = "Experienced Python programmer with AWS expertise"
        extracted_jd = {
            "top_keywords": ["Python", "AWS"],
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd)

        # Assert
        assert "Python" in result
        assert "AWS" in result

    def test_stops_at_max_keywords_even_if_more_matches(self):
        """Should stop at max_keywords even if more matches exist."""
        # Arrange
        jd_item = "Python AWS Docker Kubernetes Terraform"
        extracted_jd = {
            "top_keywords": ["Python", "AWS", "Docker", "Kubernetes", "Terraform"],
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd, max_keywords=2)

        # Assert
        assert len(result) == 2
        assert result == ["Python", "AWS"]

    def test_returns_less_than_max_if_fewer_matches(self):
        """Should return fewer than max_keywords if fewer matches exist."""
        # Arrange
        jd_item = "Python experience"
        extracted_jd = {
            "top_keywords": ["Python", "AWS", "Docker"],
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd, max_keywords=5)

        # Assert
        assert len(result) == 1
        assert result == ["Python"]

    def test_handles_multi_word_keywords(self):
        """Should match multi-word keywords."""
        # Arrange
        jd_item = "Machine learning and data science expertise"
        extracted_jd = {
            "top_keywords": ["machine learning", "data science", "Python"],
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd)

        # Assert
        assert "machine learning" in result
        assert "data science" in result

    def test_default_max_keywords_is_three(self):
        """Should use max_keywords=3 as default."""
        # Arrange
        jd_item = "Python AWS Docker Kubernetes Terraform experience"
        extracted_jd = {
            "top_keywords": ["Python", "AWS", "Docker", "Kubernetes", "Terraform"],
        }

        # Act
        result = suggest_keywords_for_item(jd_item, extracted_jd)  # No max_keywords param

        # Assert
        assert len(result) == 3
