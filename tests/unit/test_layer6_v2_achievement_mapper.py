"""
Unit tests for Achievement to Pain Point Mapper.

Tests the pre-computation of achievement-to-pain-point mappings
that reduce LLM cognitive load during CV bullet generation.
"""

import pytest
from src.layer6_v2.achievement_mapper import (
    AchievementMapper,
    AchievementMapping,
    AchievementPainPointMatch,
    map_achievements_to_pain_points,
)


class TestAchievementPainPointMatch:
    """Tests for the AchievementPainPointMatch dataclass."""

    def test_confidence_level_high(self):
        """Test high confidence level classification."""
        match = AchievementPainPointMatch(
            achievement="test",
            pain_point="test",
            confidence=0.75,
            reason="keyword overlap",
        )
        assert match.confidence_level == "high"

    def test_confidence_level_medium(self):
        """Test medium confidence level classification."""
        match = AchievementPainPointMatch(
            achievement="test",
            pain_point="test",
            confidence=0.5,
            reason="semantic similarity",
        )
        assert match.confidence_level == "medium"

    def test_confidence_level_low(self):
        """Test low confidence level classification."""
        match = AchievementPainPointMatch(
            achievement="test",
            pain_point="test",
            confidence=0.2,
            reason="partial match",
        )
        assert match.confidence_level == "low"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        match = AchievementPainPointMatch(
            achievement="Built scalable platform",
            pain_point="Need to scale platform",
            confidence=0.8,
            reason="keyword overlap",
            matched_keywords=["scale", "platform"],
        )
        result = match.to_dict()

        assert result["achievement"] == "Built scalable platform"
        assert result["pain_point"] == "Need to scale platform"
        assert result["confidence"] == 0.8
        assert result["confidence_level"] == "high"
        assert result["matched_keywords"] == ["scale", "platform"]


class TestAchievementMapping:
    """Tests for the AchievementMapping dataclass."""

    def test_has_match_true(self):
        """Test has_match when there is a best match."""
        mapping = AchievementMapping(
            achievement="test achievement",
            best_match=AchievementPainPointMatch(
                achievement="test",
                pain_point="test pain",
                confidence=0.7,
                reason="test",
            ),
        )
        assert mapping.has_match is True
        assert mapping.unmatched is False

    def test_has_match_false(self):
        """Test has_match when there is no match."""
        mapping = AchievementMapping(
            achievement="test achievement",
            best_match=None,
            unmatched=True,
        )
        assert mapping.has_match is False
        assert mapping.unmatched is True


class TestAchievementMapper:
    """Tests for the AchievementMapper class."""

    @pytest.fixture
    def mapper(self):
        """Create a mapper instance for tests."""
        return AchievementMapper()

    @pytest.fixture
    def sample_achievements(self):
        """Sample achievements for testing."""
        return [
            "Built event-driven platform processing 10M events/day with 99.9% uptime",
            "Led team of 12 engineers through major replatforming initiative",
            "Reduced deployment time from 2 hours to 15 minutes using CI/CD automation",
            "Grew team from 5 to 15 engineers while maintaining team satisfaction scores",
            "Architected microservices migration reducing technical debt by 40%",
        ]

    @pytest.fixture
    def sample_pain_points(self):
        """Sample pain points for testing."""
        return [
            "Need to scale platform to handle 100x growth",
            "Technical debt from rapid growth phase",
            "Team retention challenges during hypergrowth",
            "Reliability issues affecting customer trust",
            "Slow deployment velocity impacting time-to-market",
        ]

    def test_normalize_text(self, mapper):
        """Test text normalization."""
        text = "Built Platform! With 99.9% uptime?"
        normalized = mapper._normalize_text(text)
        assert normalized == "built platform with 99 9 uptime"

    def test_extract_keywords(self, mapper):
        """Test keyword extraction."""
        text = "Built scalable platform using Kubernetes with 99.9% availability"
        keywords = mapper._extract_keywords(text)

        assert "built" in keywords
        assert "scalable" in keywords
        assert "platform" in keywords
        assert "kubernetes" in keywords
        # Words with 3 or fewer chars should be filtered
        assert "99" not in keywords  # Single digit numbers filtered

    def test_extract_metrics(self, mapper):
        """Test metric extraction."""
        text = "Reduced costs by 40% saving $2M with 3x performance improvement"
        metrics = mapper._extract_metrics(text)

        assert "40%" in metrics
        assert "$2M" in metrics
        assert "3x" in metrics

    def test_calculate_keyword_overlap_high(self, mapper):
        """Test keyword overlap with matching terms."""
        achievement = "Scaled platform to handle 10x traffic growth"
        pain_point = "Need to scale platform to handle traffic growth"

        # Phase 5: Now returns 3 values (score, matched_keywords, annotation_keywords)
        score, matched, annotation_kw = mapper._calculate_keyword_overlap(achievement, pain_point)

        assert score > 0.1  # Should have some overlap
        assert len(matched) >= 2  # Should have multiple matching keywords

    def test_calculate_keyword_overlap_low(self, mapper):
        """Test keyword overlap with low match."""
        achievement = "Mentored junior engineers on code review practices"
        pain_point = "Need to scale platform infrastructure"

        # Phase 5: Now returns 3 values (score, matched_keywords, annotation_keywords)
        score, matched, annotation_kw = mapper._calculate_keyword_overlap(achievement, pain_point)

        assert score < 0.2  # Should have low overlap

    def test_map_achievement_with_match(self, mapper):
        """Test mapping a single achievement with a matching pain point."""
        # Use very similar text to ensure match
        achievement = "Scaled the platform to handle 100x traffic growth"
        pain_points = [
            "Need to scale platform to handle 100x growth",
            "Team retention challenges",
        ]
        mapping = mapper.map_achievement(achievement, pain_points)

        assert mapping.has_match is True
        assert mapping.best_match is not None
        assert "scale" in mapping.best_match.pain_point.lower()

    def test_map_achievement_no_match(self, mapper):
        """Test mapping an achievement with no matching pain points."""
        achievement = "Organized team building events improving morale"
        pain_points = ["Need advanced ML capabilities", "Require real-time analytics"]

        mapping = mapper.map_achievement(achievement, pain_points)

        # Should have no match or very low confidence match
        if mapping.has_match:
            assert mapping.best_match.confidence < 0.3

    def test_map_achievement_empty_pain_points(self, mapper):
        """Test mapping with empty pain points list."""
        achievement = "Built scalable platform"
        mapping = mapper.map_achievement(achievement, [])

        assert mapping.unmatched is True
        assert mapping.has_match is False

    def test_map_all_achievements(self, mapper):
        """Test mapping all achievements."""
        achievements = [
            "Scaled platform infrastructure to handle growth",
            "Reduced technical debt through refactoring",
            "Led team through hiring growth period",
        ]
        pain_points = [
            "Need to scale platform",
            "Technical debt from rapid growth",
            "Team scaling challenges",
        ]
        mappings = mapper.map_all_achievements(achievements, pain_points)

        assert len(mappings) == len(achievements)

        # At least some should have matches
        matched_count = sum(1 for m in mappings if m.has_match)
        assert matched_count >= 1  # At least one should match

    def test_get_pain_point_coverage(
        self, mapper, sample_achievements, sample_pain_points
    ):
        """Test pain point coverage calculation."""
        mappings = mapper.map_all_achievements(sample_achievements, sample_pain_points)
        coverage = mapper.get_pain_point_coverage(mappings, sample_pain_points)

        assert len(coverage) == len(sample_pain_points)
        # Each key should be a pain point
        for pain_point in sample_pain_points:
            assert pain_point in coverage

    def test_format_for_prompt(
        self, mapper, sample_achievements, sample_pain_points
    ):
        """Test prompt formatting."""
        mappings = mapper.map_all_achievements(sample_achievements, sample_pain_points)
        prompt_text = mapper.format_for_prompt(mappings, sample_pain_points)

        # Should contain the mapping header
        assert "ACHIEVEMENT TO PAIN POINT MAPPING" in prompt_text
        # Should contain achievement excerpts
        assert "Built event-driven platform" in prompt_text
        # Should indicate confidence levels
        assert any(level in prompt_text for level in ["high", "medium", "low"])


class TestConvenienceFunction:
    """Tests for the map_achievements_to_pain_points convenience function."""

    def test_returns_tuple(self):
        """Test that function returns correct tuple structure."""
        achievements = ["Built scalable platform"]
        pain_points = ["Need to scale"]

        mappings, prompt_text = map_achievements_to_pain_points(
            achievements, pain_points
        )

        assert isinstance(mappings, list)
        assert isinstance(prompt_text, str)
        assert len(mappings) == 1

    def test_prompt_text_formatting(self):
        """Test that prompt text is properly formatted."""
        # Use more similar text to ensure matches
        achievements = [
            "Scaled platform to handle traffic growth",
            "Led migration to microservices architecture",
        ]
        pain_points = [
            "Need to scale platform for growth",
            "Technical debt from monolith architecture",
        ]

        _, prompt_text = map_achievements_to_pain_points(achievements, pain_points)

        # Should have proper sections
        assert "===" in prompt_text
        assert "->" in prompt_text
        # Should have either "confidence" (when matched) or "no direct" (when unmatched)
        assert "confidence" in prompt_text.lower() or "no direct" in prompt_text.lower()


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_achievements(self):
        """Test with empty achievements list."""
        mapper = AchievementMapper()
        mappings = mapper.map_all_achievements([], ["pain point 1"])
        assert mappings == []

    def test_very_short_text(self):
        """Test with very short achievement text."""
        mapper = AchievementMapper()
        mapping = mapper.map_achievement("Built app", ["Scale issues"])
        # Should handle gracefully, not crash
        assert mapping is not None

    def test_special_characters(self):
        """Test with special characters in text."""
        mapper = AchievementMapper()
        achievement = "Built API @ 10K req/sec (99.9% SLA)"
        pain_points = ["Need high-performance APIs"]

        mapping = mapper.map_achievement(achievement, pain_points)
        assert mapping is not None

    def test_unicode_text(self):
        """Test with unicode characters."""
        mapper = AchievementMapper()
        achievement = "Led team in Berlin office"
        pain_points = ["Team coordination challenges"]

        mapping = mapper.map_achievement(achievement, pain_points)
        assert mapping is not None

    def test_custom_threshold(self):
        """Test with custom match threshold."""
        mapper = AchievementMapper(match_threshold=0.5)  # Higher threshold

        achievement = "Built something"
        pain_points = ["Need different thing"]

        mapping = mapper.map_achievement(achievement, pain_points)
        # Higher threshold should result in fewer matches
        if mapping.has_match:
            assert mapping.best_match.confidence >= 0.5


class TestTechnicalKeywordMatching:
    """Tests for technical keyword matching behavior."""

    def test_technical_keywords_weighted_higher(self):
        """Test that technical keywords get weighted higher."""
        mapper = AchievementMapper()

        # Achievement with technical keyword
        tech_achievement = "Improved scalability using Kubernetes"
        # Achievement without technical keyword
        general_achievement = "Improved something using tools"

        pain_point = "Scale platform to handle growth"

        tech_mapping = mapper.map_achievement(tech_achievement, [pain_point])
        general_mapping = mapper.map_achievement(general_achievement, [pain_point])

        # Technical keyword match should score higher
        if tech_mapping.has_match and general_mapping.has_match:
            assert tech_mapping.best_match.confidence >= general_mapping.best_match.confidence

    def test_team_related_matching(self):
        """Test matching for team-related achievements."""
        mapper = AchievementMapper()

        achievement = "Grew engineering team from 5 to 15 engineers"
        pain_points = [
            "Team retention challenges",
            "Need to hire quickly",
            "Platform scaling needs",
        ]

        mapping = mapper.map_achievement(achievement, pain_points)

        # Should match team-related pain points
        assert mapping.has_match
        assert any(
            keyword in mapping.best_match.pain_point.lower()
            for keyword in ["team", "hire", "retention"]
        )
