"""
Tests for Annotation Boost Calculator.

Tests the Phase 4 annotation boost calculation logic used in the pipeline.
"""

import pytest
from src.common.annotation_boost import (
    AnnotationBoostCalculator,
    BoostResult,
    get_annotation_boost,
    get_annotation_keywords,
    apply_annotation_boost_to_score,
)
from src.common.annotation_types import (
    RELEVANCE_MULTIPLIERS,
    REQUIREMENT_MULTIPLIERS,
    PRIORITY_MULTIPLIERS,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_annotation():
    """Create a sample annotation for testing."""
    return {
        "id": "ann-001",
        "relevance": "core_strength",
        "requirement_type": "must_have",
        "priority": 1,
        "annotation_type": "skill_match",
        "is_active": True,
        "star_ids": ["star-001", "star-002"],
        "suggested_keywords": ["kubernetes", "docker"],
        "ats_variants": ["K8s", "k8s", "Kubernetes"],
        "has_reframe": False,
        "reframe_note": None,
    }


@pytest.fixture
def sample_gap_annotation():
    """Create a gap annotation for testing."""
    return {
        "id": "ann-002",
        "relevance": "gap",
        "requirement_type": "must_have",
        "priority": 2,
        "annotation_type": "skill_match",
        "is_active": True,
        "star_ids": [],
        "suggested_keywords": ["terraform"],
        "ats_variants": ["Terraform", "TF"],
        "has_reframe": True,
        "reframe_note": "Reframe as infrastructure-as-code experience",
    }


@pytest.fixture
def sample_jd_annotations(sample_annotation, sample_gap_annotation):
    """Create a full JDAnnotations structure."""
    return {
        "annotation_version": 1,
        "annotations": [sample_annotation, sample_gap_annotation],
        "settings": {
            "conflict_resolution": "max_boost",
        },
    }


@pytest.fixture
def inactive_annotation():
    """Create an inactive annotation."""
    return {
        "id": "ann-inactive",
        "relevance": "core_strength",
        "requirement_type": "must_have",
        "priority": 1,
        "annotation_type": "skill_match",
        "is_active": False,  # Inactive!
        "star_ids": ["star-003"],
        "suggested_keywords": ["python"],
        "ats_variants": [],
    }


# =============================================================================
# CALCULATOR INITIALIZATION TESTS
# =============================================================================

class TestCalculatorInitialization:
    """Tests for AnnotationBoostCalculator initialization."""

    def test_empty_annotations(self):
        """Calculator handles empty annotations gracefully."""
        calculator = AnnotationBoostCalculator(None)
        assert calculator.has_annotations() is False
        assert calculator.get_annotation_keywords() == set()

    def test_empty_list_annotations(self):
        """Calculator handles empty annotation list."""
        calculator = AnnotationBoostCalculator({"annotations": []})
        assert calculator.has_annotations() is False

    def test_active_annotation_detection(self, sample_jd_annotations):
        """Calculator correctly detects active annotations."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)
        assert calculator.has_annotations() is True
        stats = calculator.get_stats()
        assert stats["total_active"] == 2

    def test_inactive_annotations_filtered(self, inactive_annotation):
        """Inactive annotations are not included in context."""
        calculator = AnnotationBoostCalculator({
            "annotations": [inactive_annotation]
        })
        assert calculator.has_annotations() is False
        assert "python" not in calculator.get_annotation_keywords()


# =============================================================================
# BOOST CALCULATION TESTS
# =============================================================================

class TestBoostCalculation:
    """Tests for individual boost calculations."""

    def test_core_strength_boost(self, sample_annotation):
        """Core strength gives 3.0x boost."""
        calculator = AnnotationBoostCalculator({"annotations": [sample_annotation]})
        boost = calculator.calculate_boost(sample_annotation)

        # 3.0 (core_strength) * 1.5 (must_have) * 1.5 (priority 1) * 1.0 (skill_match)
        expected = 3.0 * 1.5 * 1.5 * 1.0
        assert boost == expected

    def test_gap_boost(self, sample_gap_annotation):
        """Gap gives 0.3x penalty."""
        calculator = AnnotationBoostCalculator({"annotations": [sample_gap_annotation]})
        boost = calculator.calculate_boost(sample_gap_annotation)

        # 0.3 (gap) * 1.5 (must_have) * 1.3 (priority 2) * 1.0 (skill_match)
        expected = 0.3 * 1.5 * 1.3 * 1.0
        assert boost == pytest.approx(expected, rel=0.01)

    def test_disqualifier_returns_zero(self):
        """Disqualifier requirement returns 0.0 boost."""
        ann = {
            "id": "ann-disq",
            "relevance": "core_strength",
            "requirement_type": "disqualifier",
            "priority": 3,
            "annotation_type": "skill_match",
            "is_active": True,
        }
        calculator = AnnotationBoostCalculator({"annotations": [ann]})
        boost = calculator.calculate_boost(ann)
        assert boost == 0.0

    def test_default_values_used_when_missing(self):
        """Default values are used when fields are missing."""
        ann = {
            "id": "ann-minimal",
            "is_active": True,
            "suggested_keywords": ["test"],
        }
        calculator = AnnotationBoostCalculator({"annotations": [ann]})
        boost = calculator.calculate_boost(ann)
        # Defaults: relevant (1.5) * neutral (1.0) * priority 3 (1.0) * skill_match (1.0)
        assert boost == 1.5


# =============================================================================
# STAR ID BOOST TESTS
# =============================================================================

class TestStarIdBoost:
    """Tests for STAR record boost lookup."""

    def test_linked_star_gets_boost(self, sample_jd_annotations):
        """STAR linked to annotation gets boost."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)
        result = calculator.get_boost_for_star("star-001")

        assert result.boost > 1.0
        assert "ann-001" in result.contributing_annotations

    def test_unlinked_star_no_boost(self, sample_jd_annotations):
        """STAR not linked to annotation gets no boost."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)
        result = calculator.get_boost_for_star("star-unlinked")

        assert result.boost == 1.0
        assert result.contributing_annotations == []

    def test_multiple_annotations_same_star(self):
        """Multiple annotations linking to same STAR."""
        annotations = [
            {
                "id": "ann-1",
                "relevance": "core_strength",
                "requirement_type": "must_have",
                "priority": 1,
                "is_active": True,
                "star_ids": ["star-shared"],
            },
            {
                "id": "ann-2",
                "relevance": "extremely_relevant",
                "requirement_type": "nice_to_have",
                "priority": 2,
                "is_active": True,
                "star_ids": ["star-shared"],
            },
        ]
        calculator = AnnotationBoostCalculator({"annotations": annotations})
        result = calculator.get_boost_for_star("star-shared")

        # With max_boost, should get the higher boost
        assert len(result.contributing_annotations) == 2


# =============================================================================
# TEXT KEYWORD BOOST TESTS
# =============================================================================

class TestTextKeywordBoost:
    """Tests for text-based keyword boost lookup."""

    def test_text_with_keyword_gets_boost(self, sample_jd_annotations):
        """Text containing annotation keyword gets boost."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)

        text = "Deployed applications using Kubernetes and Docker containers"
        result = calculator.get_boost_for_text(text)

        assert result.boost > 1.0
        assert "kubernetes" in result.matched_keywords or "docker" in result.matched_keywords

    def test_text_without_keyword_no_boost(self, sample_jd_annotations):
        """Text without annotation keywords gets no boost."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)

        text = "Managed team of engineers and improved processes"
        result = calculator.get_boost_for_text(text)

        assert result.boost == 1.0

    def test_ats_variants_matched(self, sample_jd_annotations):
        """ATS variants are matched in text."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)

        text = "Experience with K8s cluster management"
        result = calculator.get_boost_for_text(text)

        # Should match "k8s" variant
        assert "k8s" in result.matched_keywords

    def test_case_insensitive_matching(self, sample_jd_annotations):
        """Keyword matching is case-insensitive."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)

        text = "KUBERNETES deployment experience"
        result = calculator.get_boost_for_text(text)

        assert result.boost > 1.0


# =============================================================================
# REFRAME GUIDANCE TESTS
# =============================================================================

class TestReframeGuidance:
    """Tests for reframe note retrieval."""

    def test_reframe_notes_returned(self, sample_jd_annotations):
        """Reframe notes are returned for matching keywords."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)

        text = "Experience with Terraform infrastructure"
        result = calculator.get_boost_for_text(text)

        assert len(result.reframe_notes) > 0
        assert "infrastructure-as-code" in result.reframe_notes[0]

    def test_no_reframe_when_not_present(self, sample_jd_annotations):
        """No reframe notes when annotation doesn't have them."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)

        text = "Kubernetes container orchestration"
        result = calculator.get_boost_for_text(text)

        # Kubernetes annotation has no reframe
        # (might include terraform reframe if text matches both)


# =============================================================================
# KEYWORD EXTRACTION TESTS
# =============================================================================

class TestKeywordExtraction:
    """Tests for keyword extraction methods."""

    def test_get_all_keywords(self, sample_jd_annotations):
        """Get all keywords from active annotations."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)
        keywords = calculator.get_annotation_keywords()

        assert "kubernetes" in keywords
        assert "docker" in keywords
        assert "terraform" in keywords

    def test_get_keywords_with_variants(self, sample_jd_annotations):
        """Get keywords including ATS variants."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)
        all_keywords = calculator.get_annotation_keywords_with_variants()

        assert "kubernetes" in all_keywords
        assert "k8s" in all_keywords
        assert "tf" in all_keywords


# =============================================================================
# GAP AND CORE STRENGTH ACCESS TESTS
# =============================================================================

class TestGapAndCoreStrength:
    """Tests for gap and core strength retrieval."""

    def test_get_gaps(self, sample_jd_annotations):
        """Get all gap annotations."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)
        gaps = calculator.get_gaps()

        assert len(gaps) == 1
        assert gaps[0]["id"] == "ann-002"

    def test_get_core_strengths(self, sample_jd_annotations):
        """Get all core strength annotations."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)
        strengths = calculator.get_core_strengths()

        assert len(strengths) == 1
        assert strengths[0]["id"] == "ann-001"


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_annotation_boost_for_star(self, sample_jd_annotations):
        """Convenience function for STAR boost."""
        boost = get_annotation_boost(
            sample_jd_annotations,
            star_id="star-001"
        )
        assert boost > 1.0

    def test_get_annotation_boost_for_text(self, sample_jd_annotations):
        """Convenience function for text boost."""
        boost = get_annotation_boost(
            sample_jd_annotations,
            text="Kubernetes deployment"
        )
        assert boost > 1.0

    def test_get_annotation_keywords_function(self, sample_jd_annotations):
        """Convenience function for keywords."""
        keywords = get_annotation_keywords(sample_jd_annotations)
        assert "kubernetes" in keywords

    def test_apply_annotation_boost_to_score(self, sample_jd_annotations):
        """Apply boost to a base score."""
        base_score = 10.0
        boosted, result = apply_annotation_boost_to_score(
            base_score,
            sample_jd_annotations,
            text="Kubernetes container management"
        )

        assert boosted > base_score
        assert result.boost > 1.0


# =============================================================================
# CONFLICT RESOLUTION TESTS
# =============================================================================

class TestConflictResolution:
    """Tests for boost conflict resolution strategies."""

    def test_max_boost_strategy(self):
        """Max boost strategy uses highest boost."""
        annotations = [
            {"id": "ann-1", "relevance": "core_strength", "is_active": True,
             "suggested_keywords": ["python"]},
            {"id": "ann-2", "relevance": "relevant", "is_active": True,
             "suggested_keywords": ["python"]},
        ]
        calculator = AnnotationBoostCalculator(
            {"annotations": annotations},
            conflict_resolution="max_boost"
        )

        result = calculator.get_boost_for_text("python programming")
        # Should use core_strength (3.0x), not relevant (1.5x)
        assert result.boost == 3.0

    def test_avg_boost_strategy(self):
        """Average boost strategy averages all boosts."""
        annotations = [
            {"id": "ann-1", "relevance": "core_strength", "is_active": True,
             "suggested_keywords": ["python"]},
            {"id": "ann-2", "relevance": "relevant", "is_active": True,
             "suggested_keywords": ["python"]},
        ]
        calculator = AnnotationBoostCalculator(
            {"annotations": annotations},
            conflict_resolution="avg_boost"
        )

        result = calculator.get_boost_for_text("python programming")
        # Should average 3.0 and 1.5 = 2.25
        assert result.boost == pytest.approx(2.25, rel=0.01)


# =============================================================================
# STATS TESTS
# =============================================================================

class TestStats:
    """Tests for statistics retrieval."""

    def test_get_stats(self, sample_jd_annotations):
        """Get complete statistics."""
        calculator = AnnotationBoostCalculator(sample_jd_annotations)
        stats = calculator.get_stats()

        assert stats["total_active"] == 2
        assert stats["core_strengths"] == 1
        assert stats["gaps"] == 1
        assert stats["total_keywords"] > 0
        assert stats["stars_linked"] > 0


# =============================================================================
# DISQUALIFIER TESTS
# =============================================================================

class TestDisqualifier:
    """Tests for disqualifier handling."""

    def test_disqualifier_returns_zero_in_combined(self):
        """Disqualifier in combined boost returns 0."""
        annotations = [
            {"id": "ann-1", "relevance": "core_strength", "requirement_type": "must_have",
             "is_active": True, "suggested_keywords": ["python"]},
            {"id": "ann-2", "relevance": "relevant", "requirement_type": "disqualifier",
             "is_active": True, "suggested_keywords": ["python"]},
        ]
        calculator = AnnotationBoostCalculator({"annotations": annotations})

        result = calculator.get_boost_for_text("python programming")
        assert result.boost == 0.0
        assert result.is_disqualifier is True
