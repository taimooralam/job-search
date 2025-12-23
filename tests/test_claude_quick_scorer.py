"""
Tests for ClaudeQuickScorer.

Tests the Claude CLI-based job scoring functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.claude_quick_scorer import (
    ClaudeQuickScorer,
    derive_tier_from_score,
    QUICK_SCORE_SYSTEM,
    QUICK_SCORE_USER,
)


class TestDeriveScore:
    """Test tier derivation from score."""

    def test_tier_a_high_score(self):
        assert derive_tier_from_score(100) == "A"
        assert derive_tier_from_score(85) == "A"
        assert derive_tier_from_score(80) == "A"

    def test_tier_b_good_score(self):
        assert derive_tier_from_score(79) == "B"
        assert derive_tier_from_score(70) == "B"
        assert derive_tier_from_score(60) == "B"

    def test_tier_c_moderate_score(self):
        assert derive_tier_from_score(59) == "C"
        assert derive_tier_from_score(50) == "C"
        assert derive_tier_from_score(40) == "C"

    def test_tier_d_low_score(self):
        assert derive_tier_from_score(39) == "D"
        assert derive_tier_from_score(20) == "D"
        assert derive_tier_from_score(0) == "D"

    def test_none_score(self):
        assert derive_tier_from_score(None) is None


class TestClaudeQuickScorer:
    """Test ClaudeQuickScorer class."""

    @pytest.fixture
    def mock_llm_result(self):
        """Create a mock LLM result."""
        result = MagicMock()
        result.success = True
        result.content = "SCORE: 85\nRATIONALE: Strong match on Python and ML skills."
        result.backend = "claude_cli"
        result.duration_ms = 1500
        return result

    @pytest.fixture
    def mock_llm_result_failure(self):
        """Create a mock failed LLM result."""
        result = MagicMock()
        result.success = False
        result.error = "CLI timeout"
        return result

    @pytest.mark.asyncio
    async def test_score_job_success(self, mock_llm_result):
        """Test successful job scoring."""
        with patch("src.services.claude_quick_scorer.UnifiedLLM") as MockLLM:
            mock_instance = MagicMock()
            mock_instance.invoke = AsyncMock(return_value=mock_llm_result)
            MockLLM.return_value = mock_instance

            scorer = ClaudeQuickScorer()
            score, rationale = await scorer.score_job(
                title="Senior ML Engineer",
                company="Acme AI",
                location="Remote",
                description="Build ML pipelines using Python and TensorFlow.",
                candidate_profile="Python expert with ML experience.",
            )

            assert score == 85
            assert "Strong match" in rationale
            mock_instance.invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_score_job_failure(self, mock_llm_result_failure):
        """Test handling of scoring failure."""
        with patch("src.services.claude_quick_scorer.UnifiedLLM") as MockLLM:
            mock_instance = MagicMock()
            mock_instance.invoke = AsyncMock(return_value=mock_llm_result_failure)
            MockLLM.return_value = mock_instance

            scorer = ClaudeQuickScorer()
            score, rationale = await scorer.score_job(
                title="Job",
                company="Company",
                location="Location",
                description="Description",
                candidate_profile="Profile",
            )

            assert score is None
            assert rationale is None

    def test_parse_score_response_valid(self):
        """Test parsing valid LLM response."""
        scorer = ClaudeQuickScorer.__new__(ClaudeQuickScorer)

        response = """SCORE: 75
RATIONALE: Good technical fit. Some gaps in leadership experience."""

        score, rationale = scorer._parse_score_response(response)
        assert score == 75
        assert "Good technical fit" in rationale

    def test_parse_score_response_out_of_range(self):
        """Test score clamping to valid range."""
        scorer = ClaudeQuickScorer.__new__(ClaudeQuickScorer)

        response = "SCORE: 150\nRATIONALE: Over the top match."
        score, _ = scorer._parse_score_response(response)
        assert score == 100  # Clamped to max

    def test_parse_score_response_zero(self):
        """Test handling of zero score."""
        scorer = ClaudeQuickScorer.__new__(ClaudeQuickScorer)

        response = "SCORE: 0\nRATIONALE: No match at all."
        score, _ = scorer._parse_score_response(response)
        assert score == 0

    def test_parse_score_response_no_score(self):
        """Test handling missing score in response."""
        scorer = ClaudeQuickScorer.__new__(ClaudeQuickScorer)

        response = "The candidate seems like a good fit overall."
        score, rationale = scorer._parse_score_response(response)
        assert score is None

    def test_format_profile_as_text(self):
        """Test profile formatting."""
        scorer = ClaudeQuickScorer.__new__(ClaudeQuickScorer)

        profile = {
            "name": "John Doe",
            "summary": "Experienced engineer.",
            "skills": ["Python", "ML", "AWS"],
            "roles": [
                {
                    "company": "TechCorp",
                    "title": "Senior Engineer",
                    "period": "2020-2023",
                    "achievements": ["Built ML pipeline", "Led team of 5"],
                }
            ],
        }

        text = scorer._format_profile_as_text(profile)
        assert "John Doe" in text
        assert "Experienced engineer" in text
        assert "Python" in text
        assert "TechCorp" in text
        assert "Built ML pipeline" in text


class TestQuickScorePrompts:
    """Test that prompts are properly defined."""

    def test_system_prompt_contains_scoring_guidelines(self):
        assert "SCORING GUIDELINES" in QUICK_SCORE_SYSTEM
        assert "80-100" in QUICK_SCORE_SYSTEM
        assert "60-79" in QUICK_SCORE_SYSTEM

    def test_user_prompt_template_has_placeholders(self):
        assert "{title}" in QUICK_SCORE_USER
        assert "{company}" in QUICK_SCORE_USER
        assert "{description}" in QUICK_SCORE_USER
        assert "{candidate_profile}" in QUICK_SCORE_USER
