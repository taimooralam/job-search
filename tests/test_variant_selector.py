"""
Unit tests for VariantSelector.

Tests the variant selection algorithm that chooses optimal achievement
variants based on JD requirements.
"""

import pytest
from pathlib import Path

from src.layer6_v2.variant_parser import (
    Achievement,
    AchievementVariant,
    EnhancedRoleData,
    RoleMetadata,
    SelectionGuide,
    parse_role_file,
)
from src.layer6_v2.variant_selector import (
    VariantSelector,
    VariantScore,
    SelectedVariant,
    SelectionResult,
    select_variants_for_role,
    select_variants_for_all_roles,
    VARIANT_PREFERENCES,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_achievement():
    """Create a sample achievement with variants."""
    return Achievement(
        id="achievement_1",
        title="Platform Modernization",
        core_fact="Led migration of legacy monolith to microservices.",
        variants={
            "Technical": AchievementVariant(
                variant_type="Technical",
                text="Architected microservices migration using Kubernetes and AWS Lambda, reducing incidents by 75%",
            ),
            "Architecture": AchievementVariant(
                variant_type="Architecture",
                text="Designed distributed system architecture handling 10M requests/day with zero downtime",
            ),
            "Impact": AchievementVariant(
                variant_type="Impact",
                text="Reduced operational incidents by 75% through platform modernization initiative",
            ),
            "Leadership": AchievementVariant(
                variant_type="Leadership",
                text="Led 12-person team through 18-month platform transformation",
            ),
            "Short": AchievementVariant(
                variant_type="Short",
                text="Microservices migration—75% fewer incidents, zero downtime",
            ),
        },
        keywords=["microservices", "Kubernetes", "AWS Lambda", "architecture", "migration"],
    )


@pytest.fixture
def sample_role(sample_achievement):
    """Create a sample enhanced role."""
    achievement2 = Achievement(
        id="achievement_2",
        title="Observability Pipeline",
        core_fact="Built real-time observability pipeline.",
        variants={
            "Technical": AchievementVariant(
                variant_type="Technical",
                text="Architected event streaming pipeline using OpenSearch, processing billions of daily events",
            ),
            "Impact": AchievementVariant(
                variant_type="Impact",
                text="Enabled 10x cost reduction through real-time debugging capabilities",
            ),
        },
        keywords=["observability", "OpenSearch", "event streaming", "monitoring"],
    )

    achievement3 = Achievement(
        id="achievement_3",
        title="Team Leadership",
        core_fact="Mentored engineers and led hiring initiatives.",
        variants={
            "Leadership": AchievementVariant(
                variant_type="Leadership",
                text="Mentored 8 engineers and led hiring initiatives growing team from 5 to 15",
            ),
            "Impact": AchievementVariant(
                variant_type="Impact",
                text="Grew engineering team 3x while maintaining high performance standards",
            ),
        },
        keywords=["mentoring", "hiring", "team growth", "leadership"],
    )

    return EnhancedRoleData(
        id="test_role",
        metadata=RoleMetadata(
            company="Test Company",
            title="Senior Software Engineer",
            location="Munich, DE",
            period="2020-Present",
            is_current=True,
            career_stage="Senior",
        ),
        achievements=[sample_achievement, achievement2, achievement3],
        hard_skills=["Python", "Kubernetes", "AWS"],
        soft_skills=["Leadership", "Communication"],
        selection_guide=SelectionGuide(
            mappings={
                "Backend/Infrastructure": ["achievement_1", "achievement_2"],
                "Leadership/Management": ["achievement_3"],
            }
        ),
    )


@pytest.fixture
def sample_jd_technical():
    """Sample JD for a technical IC role."""
    return {
        "title": "Senior Software Engineer",
        "company": "Tech Corp",
        "role_category": "senior_engineer",
        "top_keywords": [
            "kubernetes", "microservices", "aws", "python",
            "architecture", "scalability", "monitoring"
        ],
        "technical_skills": ["Kubernetes", "AWS", "Python", "Docker"],
        "soft_skills": ["communication", "teamwork"],
        "implied_pain_points": [
            "Need to modernize legacy systems",
            "Improve system reliability and reduce incidents",
            "Scale infrastructure to handle growth",
        ],
    }


@pytest.fixture
def sample_jd_leadership():
    """Sample JD for a leadership role."""
    return {
        "title": "Engineering Manager",
        "company": "Growth Corp",
        "role_category": "engineering_manager",
        "top_keywords": [
            "leadership", "team building", "hiring", "mentoring",
            "agile", "delivery", "strategy"
        ],
        "technical_skills": ["Python", "AWS"],
        "soft_skills": ["leadership", "communication", "mentoring"],
        "implied_pain_points": [
            "Need to grow and scale engineering team",
            "Improve delivery predictability",
            "Build strong engineering culture",
        ],
    }


@pytest.fixture
def selector():
    """Create a VariantSelector instance."""
    return VariantSelector()


# ============================================================================
# TESTS: SCORING ALGORITHM
# ============================================================================

class TestVariantScoring:
    """Tests for the variant scoring algorithm."""

    def test_keyword_overlap_increases_score(self, selector, sample_role, sample_jd_technical):
        """Variants with more JD keywords should score higher."""
        result = selector.select_variants(sample_role, sample_jd_technical, target_count=3)

        # The Technical variant of achievement_1 mentions kubernetes, microservices, aws
        # which are in the JD keywords, so it should score well
        selected_ids = [v.achievement_id for v in result.selected_variants]
        assert "achievement_1" in selected_ids

    def test_pain_point_alignment_affects_score(self, selector, sample_role, sample_jd_technical):
        """Variants aligned with pain points should score higher."""
        # The JD mentions "modernize legacy systems" which aligns with achievement_1
        result = selector.select_variants(sample_role, sample_jd_technical, target_count=3)

        # Check that pain point matching works
        achievement_1_selection = next(
            (v for v in result.selected_variants if v.achievement_id == "achievement_1"),
            None
        )
        assert achievement_1_selection is not None
        # Score should have some pain point contribution
        assert achievement_1_selection.score.pain_point_score > 0

    def test_role_category_affects_variant_type(self, selector, sample_role):
        """Role category should influence which variant type is preferred."""
        # Technical JD should prefer Technical variants
        technical_jd = {
            "role_category": "senior_engineer",
            "top_keywords": ["python", "architecture"],
            "implied_pain_points": [],
        }
        result = selector.select_variants(sample_role, technical_jd, target_count=3)

        # Most selected variants should be Technical type
        technical_count = sum(
            1 for v in result.selected_variants if v.variant_type == "Technical"
        )
        assert technical_count >= 1

    def test_leadership_jd_prefers_leadership_variants(self, selector, sample_role, sample_jd_leadership):
        """Leadership JDs should prefer Leadership variants."""
        result = selector.select_variants(sample_role, sample_jd_leadership, target_count=3)

        # Should select achievement_3 which has leadership focus
        selected_ids = [v.achievement_id for v in result.selected_variants]
        assert "achievement_3" in selected_ids

        # The achievement_3 selection should use Leadership variant
        achievement_3_selection = next(
            v for v in result.selected_variants if v.achievement_id == "achievement_3"
        )
        assert achievement_3_selection.variant_type == "Leadership"


# ============================================================================
# TESTS: SELECTION BEHAVIOR
# ============================================================================

class TestVariantSelection:
    """Tests for variant selection behavior."""

    def test_selects_correct_count(self, selector, sample_role, sample_jd_technical):
        """Selector should return requested number of variants."""
        result = selector.select_variants(sample_role, sample_jd_technical, target_count=2)
        assert result.selection_count == 2

    def test_no_duplicate_achievements(self, selector, sample_role, sample_jd_technical):
        """Should not select multiple variants from same achievement."""
        result = selector.select_variants(sample_role, sample_jd_technical, target_count=5)

        achievement_ids = [v.achievement_id for v in result.selected_variants]
        # All IDs should be unique
        assert len(achievement_ids) == len(set(achievement_ids))

    def test_respects_min_score_threshold(self, selector, sample_role):
        """Should not select variants below minimum score."""
        # Use empty JD to get very low scores
        empty_jd = {
            "role_category": "default",
            "top_keywords": ["xyz123", "nonexistent"],
            "implied_pain_points": [],
        }
        result = selector.select_variants(
            sample_role, empty_jd, target_count=10, min_score=0.5
        )

        # With high min_score and unrelated keywords, few/no variants selected
        for variant in result.selected_variants:
            assert variant.total_score >= 0.5

    def test_sorted_by_score_descending(self, selector, sample_role, sample_jd_technical):
        """Selected variants should be sorted by score (highest first)."""
        result = selector.select_variants(sample_role, sample_jd_technical, target_count=3)

        scores = [v.total_score for v in result.selected_variants]
        assert scores == sorted(scores, reverse=True)


# ============================================================================
# TESTS: SELECTION RESULT
# ============================================================================

class TestSelectionResult:
    """Tests for SelectionResult data class."""

    def test_keyword_coverage_calculation(self, selector, sample_role, sample_jd_technical):
        """Should correctly calculate keyword coverage."""
        result = selector.select_variants(sample_role, sample_jd_technical, target_count=3)

        # Should have some covered and some missing keywords
        assert len(result.jd_keywords_covered) > 0
        assert result.keyword_coverage > 0
        assert result.keyword_coverage <= 1.0

    def test_get_bullet_texts(self, selector, sample_role, sample_jd_technical):
        """get_bullet_texts should return just the text strings."""
        result = selector.select_variants(sample_role, sample_jd_technical, target_count=2)

        texts = result.get_bullet_texts()
        assert len(texts) == 2
        assert all(isinstance(t, str) for t in texts)

    def test_to_dict_serialization(self, selector, sample_role, sample_jd_technical):
        """to_dict should produce valid dictionary."""
        result = selector.select_variants(sample_role, sample_jd_technical, target_count=2)

        data = result.to_dict()
        assert "role_id" in data
        assert "selected_variants" in data
        assert "keyword_coverage" in data
        assert data["selection_count"] == 2


# ============================================================================
# TESTS: SELECTION GUIDE
# ============================================================================

class TestSelectionGuide:
    """Tests for selection guide integration."""

    def test_uses_selection_guide_when_available(self, selector, sample_role):
        """Should use selection guide to prioritize achievements."""
        # JD that matches "Backend/Infrastructure"
        backend_jd = {
            "role_category": "Backend/Infrastructure",
            "top_keywords": ["python", "aws"],
            "implied_pain_points": [],
        }

        result = selector.select_with_selection_guide(sample_role, backend_jd, target_count=2)

        # Should prioritize achievement_1 and achievement_2 per selection guide
        selected_ids = [v.achievement_id for v in result.selected_variants]
        assert "achievement_1" in selected_ids or "achievement_2" in selected_ids

    def test_fallback_when_no_guide_match(self, selector, sample_role):
        """Should fall back to standard selection when guide doesn't match."""
        # JD with category not in selection guide
        unknown_jd = {
            "role_category": "unknown_category",
            "top_keywords": ["python"],
            "implied_pain_points": [],
        }

        result = selector.select_with_selection_guide(sample_role, unknown_jd, target_count=2)

        # Should still return results using standard algorithm
        assert result.selection_count == 2


# ============================================================================
# TESTS: VARIANT PREFERENCES
# ============================================================================

class TestVariantPreferences:
    """Tests for variant type preferences by role category."""

    def test_ic_roles_prefer_technical(self):
        """IC roles should prefer Technical variants."""
        ic_roles = ["staff_principal_engineer", "senior_engineer", "software_architect"]

        for role in ic_roles:
            prefs = VARIANT_PREFERENCES.get(role, [])
            assert "Technical" in prefs or "Architecture" in prefs

    def test_management_roles_prefer_leadership(self):
        """Management roles should prefer Leadership variants."""
        mgmt_roles = ["engineering_manager", "director_of_engineering", "head_of_engineering"]

        for role in mgmt_roles:
            prefs = VARIANT_PREFERENCES.get(role, [])
            assert "Leadership" in prefs[:2]  # Leadership in top 2 preferences

    def test_default_preferences_exist(self):
        """Should have default preferences for unknown roles."""
        assert "default" in VARIANT_PREFERENCES
        assert len(VARIANT_PREFERENCES["default"]) >= 3


# ============================================================================
# TESTS: CONVENIENCE FUNCTIONS
# ============================================================================

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_select_variants_for_role(self, sample_role, sample_jd_technical):
        """select_variants_for_role convenience function should work."""
        result = select_variants_for_role(sample_role, sample_jd_technical, target_count=2)

        assert isinstance(result, SelectionResult)
        assert result.selection_count == 2

    def test_select_variants_for_all_roles(self, sample_role, sample_jd_technical):
        """select_variants_for_all_roles should process multiple roles."""
        roles = {"test_role": sample_role}

        results = select_variants_for_all_roles(
            roles, sample_jd_technical, bullet_counts={"test_role": 2}
        )

        assert "test_role" in results
        assert results["test_role"].selection_count == 2


# ============================================================================
# TESTS: REAL ROLE FILES (INTEGRATION)
# ============================================================================

class TestRealRoleIntegration:
    """Integration tests with actual role files."""

    @pytest.fixture
    def real_role(self):
        """Load a real role file."""
        role_path = Path("data/master-cv/roles/01_seven_one_entertainment.md")
        if not role_path.exists():
            pytest.skip("Real role file not available")
        return parse_role_file(role_path)

    @pytest.mark.skipif(
        not Path("data/master-cv/roles").exists(),
        reason="Real role files not available"
    )
    def test_real_role_selection(self, selector, real_role):
        """Should successfully select variants from real role file."""
        jd = {
            "role_category": "tech_lead",
            "top_keywords": [
                "typescript", "aws", "microservices", "leadership",
                "architecture", "observability", "kubernetes"
            ],
            "technical_skills": ["TypeScript", "AWS", "Kubernetes"],
            "soft_skills": ["leadership", "communication"],
            "implied_pain_points": [
                "Need to modernize legacy systems",
                "Scale infrastructure",
                "Build high-performing team",
            ],
        }

        result = selector.select_variants(real_role, jd, target_count=6)

        assert result.selection_count == 6
        assert result.average_score > 0
        assert result.keyword_coverage > 0

        # Verify each selected variant has valid data
        for variant in result.selected_variants:
            assert variant.text
            assert variant.achievement_title
            assert variant.total_score > 0

    @pytest.mark.skipif(
        not Path("data/master-cv/roles").exists(),
        reason="Real role files not available"
    )
    def test_real_role_keyword_coverage(self, selector, real_role):
        """Should achieve reasonable keyword coverage with real data."""
        jd = {
            "role_category": "senior_engineer",
            "top_keywords": ["aws", "typescript", "microservices", "architecture"],
            "implied_pain_points": [],
        }

        result = selector.select_variants(real_role, jd, target_count=5)

        # Should cover at least some keywords
        assert len(result.jd_keywords_covered) >= 1
        # Coverage should be reasonable
        assert result.keyword_coverage >= 0.25
