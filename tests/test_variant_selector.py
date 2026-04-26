"""
Unit tests for VariantSelector.

Tests the variant selection algorithm that chooses optimal achievement
variants based on JD requirements.
"""

from pathlib import Path

import pytest

from src.layer6_v2.variant_parser import (
    Achievement,
    AchievementVariant,
    EnhancedRoleData,
    RoleMetadata,
    SelectionGuide,
    parse_role_file,
)
from src.layer6_v2.variant_selector import (
    VARIANT_PREFERENCES,
    SelectedVariant,
    SelectionResult,
    VariantScore,
    VariantSelector,
    select_variants_for_all_roles,
    select_variants_for_role,
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

    def test_ai_leadership_preferences_prioritize_leadership(self):
        """AI leadership roles should prefer leadership-first variants."""
        assert VARIANT_PREFERENCES["ai_leadership"] == [
            "Leadership",
            "Architecture",
            "Technical",
            "Impact",
        ]


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


# ============================================================================
# TESTS: PAIN POINT REBALANCING
# ============================================================================


def _make_achievement(aid, title, variants_dict, keywords=None):
    """Helper: build an Achievement with given variants."""
    variants = {
        vt: AchievementVariant(variant_type=vt, text=text)
        for vt, text in variants_dict.items()
    }
    return Achievement(
        id=aid, title=title, core_fact=title,
        variants=variants, keywords=keywords or [],
    )


def _make_score(aid, vtype, text, keyword_score=0.3, pain_score=0.0, role_cat_score=0.5,
                ach_kw_score=0.2, matched_pp="", arch_boost=1.0, anno_boost=1.0):
    """Helper: build a VariantScore with controllable components."""
    return VariantScore(
        achievement_id=aid, variant_type=vtype, variant_text=text,
        keyword_score=keyword_score, pain_point_score=pain_score,
        role_category_score=role_cat_score, achievement_keyword_score=ach_kw_score,
        matched_pain_point=matched_pp, architecture_boost=arch_boost,
        annotation_boost=anno_boost,
    )


def _make_selected(aid, title, vtype, text, score):
    """Helper: build a SelectedVariant."""
    return SelectedVariant(
        achievement_id=aid, achievement_title=title,
        variant_type=vtype, text=text, score=score,
        core_fact=title, keywords=[],
    )


class TestPainPointRebalancing:
    """Tests for the pain point rebalancing post-selection pass."""

    @pytest.fixture
    def selector(self):
        return VariantSelector()

    @pytest.fixture
    def five_pain_points(self):
        return [
            "Need to modernize legacy systems",
            "Improve system reliability and reduce incidents",
            "Scale infrastructure to handle growth",
            "Build AI platform for enterprise",
            "Establish engineering culture and mentoring",
        ]

    @pytest.fixture
    def role_with_diverse_achievements(self):
        """Role with 6 achievements — some address pain points, some don't."""
        return EnhancedRoleData(
            id="test_role",
            metadata=RoleMetadata(
                company="Test Co", title="Engineer", location="Munich",
                period="2020-Present", is_current=True, career_stage="Senior",
            ),
            achievements=[
                _make_achievement("ach_1", "Platform Modernization", {
                    "Technical": "Architected microservices migration modernize legacy reducing incidents by 75%",
                    "Architecture": "Designed distributed platform modernize legacy with zero downtime",
                }),
                _make_achievement("ach_2", "Observability", {
                    "Technical": "Built observability pipeline processing billions of events",
                }),
                _make_achievement("ach_3", "Team Leadership", {
                    "Leadership": "Mentored 10 engineers establishing engineering culture and mentoring programs",
                }),
                _make_achievement("ach_4", "Scaling", {
                    "Technical": "Scaled infrastructure auto-scaling handling growth to 10M requests daily",
                }),
                _make_achievement("ach_5", "AI Platform", {
                    "Technical": "Built AI platform enterprise with RAG and semantic caching for 2000 users",
                }),
                _make_achievement("ach_6", "Compliance", {
                    "Technical": "Led GDPR compliance program protecting revenue across product lines",
                }),
            ],
            hard_skills=["Python", "AWS"],
            soft_skills=["Leadership"],
        )

    def test_rebalance_improves_coverage(self, selector, role_with_diverse_achievements, five_pain_points):
        """Selection with low pain point coverage should improve after rebalancing."""
        jd = {
            "role_category": "senior_engineer",
            "top_keywords": ["microservices", "aws", "python", "observability"],
            "implied_pain_points": five_pain_points,
        }
        result = selector.select_variants(role_with_diverse_achievements, jd, target_count=5)

        # Count how many pain points are addressed
        addressed = {
            sv.score.matched_pain_point
            for sv in result.selected_variants
            if sv.score.matched_pain_point
        }
        # Should cover more than 1 (rebalancing should help)
        assert len(addressed) >= 2

    def test_rebalance_noop_when_coverage_sufficient(self, selector):
        """If pain point coverage is already >= 60%, no swaps should happen."""
        pain_points = ["modernize systems", "improve reliability"]

        # All selected cover pain points
        selected = [
            _make_selected("a1", "T1", "Technical", "modernize systems architecture",
                           _make_score("a1", "Technical", "modernize systems architecture",
                                       matched_pp="modernize systems")),
            _make_selected("a2", "T2", "Technical", "improve reliability with monitoring",
                           _make_score("a2", "Technical", "improve reliability with monitoring",
                                       matched_pp="improve reliability")),
        ]
        all_scores = []  # Empty — no candidates

        result = selector._rebalance_for_pain_points(
            selected=selected, all_scores=all_scores,
            pain_points=pain_points, role_id="test", role_category="senior_engineer",
        )
        assert len(result) == 2  # Unchanged

    def test_rebalance_noop_with_empty_pain_points(self, selector):
        """Empty pain points list should return selection unchanged."""
        selected = [
            _make_selected("a1", "T1", "Technical", "some bullet",
                           _make_score("a1", "Technical", "some bullet")),
        ]
        result = selector._rebalance_for_pain_points(
            selected=selected, all_scores=[], pain_points=[],
            role_id="test", role_category="senior_engineer",
        )
        assert result is selected  # Same object, no copy

    def test_rebalance_preserves_forced_ai_achievements(self, selector):
        """Forced AI achievements (15-18) on Seven.One should never be swapped out."""
        pain_points = ["need cloud migration", "need team leadership", "need AI platform"]

        # Simulate: achievement_15 is selected (forced), covers "need AI platform"
        # achievement_1 is selected, covers nothing
        selected = [
            _make_selected("achievement_15", "AI Platform", "Technical",
                           "Built AI platform enterprise",
                           _make_score("achievement_15", "Technical",
                                       "Built AI platform enterprise",
                                       keyword_score=0.1, matched_pp="need AI platform")),
            _make_selected("ach_1", "Generic", "Technical",
                           "Did some generic work",
                           _make_score("ach_1", "Technical", "Did some generic work",
                                       keyword_score=0.1)),
        ]

        # Candidate covers "need cloud migration"
        candidate_ach = _make_achievement("ach_99", "Cloud", {
            "Technical": "cloud migration infrastructure scaling",
        })
        candidate_score = _make_score("ach_99", "Technical",
                                      "cloud migration infrastructure scaling",
                                      keyword_score=0.3, matched_pp="need cloud migration")
        all_scores = [(candidate_ach, candidate_ach.variants["Technical"], candidate_score)]

        result = selector._rebalance_for_pain_points(
            selected=selected, all_scores=all_scores, pain_points=pain_points,
            role_id="01_seven_one_entertainment", role_category="ai_architect",
        )

        # achievement_15 must still be present
        ids = [sv.achievement_id for sv in result]
        assert "achievement_15" in ids

    def test_rebalance_sole_coverage_protection(self, selector):
        """A bullet that uniquely covers a pain point should not be swapped out."""
        pain_points = ["modernize legacy", "build AI platform", "improve reliability"]

        # ach_1 is the SOLE coverage for "modernize legacy" — must not be swapped
        # ach_2 covers nothing — can be swapped
        selected = [
            _make_selected("ach_1", "Modernize", "Technical",
                           "Modernized legacy systems end to end",
                           _make_score("ach_1", "Technical",
                                       "Modernized legacy systems end to end",
                                       keyword_score=0.2, matched_pp="modernize legacy")),
            _make_selected("ach_2", "Generic", "Technical",
                           "Generic task with no pain point",
                           _make_score("ach_2", "Technical",
                                       "Generic task with no pain point",
                                       keyword_score=0.2)),
        ]

        # Candidate covers "build AI platform"
        candidate_ach = _make_achievement("ach_99", "AI", {
            "Technical": "build AI platform enterprise with RAG",
        })
        candidate_score = _make_score("ach_99", "Technical",
                                      "build AI platform enterprise with RAG",
                                      keyword_score=0.3, matched_pp="build AI platform")
        all_scores = [(candidate_ach, candidate_ach.variants["Technical"], candidate_score)]

        result = selector._rebalance_for_pain_points(
            selected=selected, all_scores=all_scores, pain_points=pain_points,
            role_id="test", role_category="senior_engineer",
        )

        # ach_1 must still be present (sole coverage for "modernize legacy")
        ids = [sv.achievement_id for sv in result]
        assert "ach_1" in ids
        # ach_2 should have been swapped for ach_99
        assert "ach_99" in ids

    def test_rebalance_score_threshold(self, selector):
        """Candidate with too large a score drop should not be swapped in."""
        pain_points = ["need AI platform", "need leadership"]

        # Strong selected bullet (high base score)
        selected = [
            _make_selected("ach_1", "Strong", "Technical",
                           "Strong bullet with great keywords",
                           _make_score("ach_1", "Technical",
                                       "Strong bullet with great keywords",
                                       keyword_score=0.8, pain_score=0.0,
                                       role_cat_score=0.8, ach_kw_score=0.5)),
        ]

        # Weak candidate (very low base score but matches pain point)
        candidate_ach = _make_achievement("ach_99", "Weak", {
            "Technical": "need AI platform basic work",
        })
        candidate_score = _make_score("ach_99", "Technical",
                                      "need AI platform basic work",
                                      keyword_score=0.05, pain_score=0.1,
                                      role_cat_score=0.1, ach_kw_score=0.0,
                                      matched_pp="need AI platform")
        all_scores = [(candidate_ach, candidate_ach.variants["Technical"], candidate_score)]

        result = selector._rebalance_for_pain_points(
            selected=selected, all_scores=all_scores, pain_points=pain_points,
            role_id="test", role_category="senior_engineer",
        )

        # Score drop too large — should NOT swap
        assert result[0].achievement_id == "ach_1"

    def test_rebalance_same_achievement_variant_swap(self, selector):
        """Should allow swapping to a different variant of the same achievement."""
        pain_points = ["build AI platform", "improve reliability"]

        # ach_1 Technical variant selected — covers nothing
        selected = [
            _make_selected("ach_1", "Platform", "Technical",
                           "Generic technical implementation details",
                           _make_score("ach_1", "Technical",
                                       "Generic technical implementation details",
                                       keyword_score=0.3)),
        ]

        # ach_1 Architecture variant covers "build AI platform"
        ach = _make_achievement("ach_1", "Platform", {
            "Technical": "Generic technical implementation details",
            "Architecture": "build AI platform architecture with enterprise RAG",
        })
        alt_score = _make_score("ach_1", "Architecture",
                                "build AI platform architecture with enterprise RAG",
                                keyword_score=0.3, matched_pp="build AI platform")
        all_scores = [(ach, ach.variants["Architecture"], alt_score)]

        result = selector._rebalance_for_pain_points(
            selected=selected, all_scores=all_scores, pain_points=pain_points,
            role_id="test", role_category="senior_engineer", target_count=5,
        )

        # Fill phase skips same-achievement, but swap phase replaces the variant in-place
        # Result: same achievement_id, different variant_type
        assert any(sv.variant_type == "Architecture" for sv in result)

    def test_rebalance_fill_before_swap(self, selector):
        """When selection is underfilled, should append instead of swapping."""
        pain_points = ["modernize legacy", "build AI platform"]

        # Only 1 selected out of target_count=3
        selected = [
            _make_selected("ach_1", "T1", "Technical",
                           "Modernize legacy systems architecture",
                           _make_score("ach_1", "Technical",
                                       "Modernize legacy systems architecture",
                                       matched_pp="modernize legacy")),
        ]

        # Candidate from different achievement covers "build AI platform"
        candidate_ach = _make_achievement("ach_99", "AI", {
            "Technical": "build AI platform enterprise with semantic caching",
        })
        candidate_score = _make_score("ach_99", "Technical",
                                      "build AI platform enterprise with semantic caching",
                                      keyword_score=0.3, matched_pp="build AI platform")
        all_scores = [(candidate_ach, candidate_ach.variants["Technical"], candidate_score)]

        result = selector._rebalance_for_pain_points(
            selected=selected, all_scores=all_scores, pain_points=pain_points,
            role_id="test", role_category="senior_engineer", target_count=3,
        )

        # Should have appended (not swapped) since len(selected) < target_count
        assert len(result) == 2
        ids = [sv.achievement_id for sv in result]
        assert "ach_1" in ids
        assert "ach_99" in ids

    def test_rebalance_all_protected_no_swap(self, selector):
        """If all bullets are forced or sole-coverage, no swap should happen."""
        pain_points = ["modernize legacy", "build AI platform", "need leadership"]

        # Both bullets are sole-coverage for their respective pain points
        selected = [
            _make_selected("ach_1", "T1", "Technical",
                           "Modernize legacy platform",
                           _make_score("ach_1", "Technical",
                                       "Modernize legacy platform",
                                       matched_pp="modernize legacy")),
            _make_selected("ach_2", "T2", "Technical",
                           "Build AI platform for enterprise",
                           _make_score("ach_2", "Technical",
                                       "Build AI platform for enterprise",
                                       matched_pp="build AI platform")),
        ]

        # Candidate covers "need leadership"
        candidate_ach = _make_achievement("ach_99", "Leadership", {
            "Leadership": "need leadership mentoring team building",
        })
        candidate_score = _make_score("ach_99", "Leadership",
                                      "need leadership mentoring team building",
                                      keyword_score=0.3, matched_pp="need leadership")
        all_scores = [(candidate_ach, candidate_ach.variants["Leadership"], candidate_score)]

        result = selector._rebalance_for_pain_points(
            selected=selected, all_scores=all_scores, pain_points=pain_points,
            role_id="test", role_category="senior_engineer", target_count=2,
        )

        # Both are sole-coverage — no legal swap, selection unchanged
        ids = [sv.achievement_id for sv in result]
        assert "ach_1" in ids
        assert "ach_2" in ids
        assert len(result) == 2

    def test_rebalance_stale_candidate_skipped(self, selector):
        """Candidate that becomes redundant after an earlier swap should be skipped."""
        pain_points = ["build AI platform", "need leadership"]

        # Two generic bullets, neither covers pain points
        selected = [
            _make_selected("ach_1", "T1", "Technical", "generic work one",
                           _make_score("ach_1", "Technical", "generic work one",
                                       keyword_score=0.2)),
            _make_selected("ach_2", "T2", "Technical", "generic work two",
                           _make_score("ach_2", "Technical", "generic work two",
                                       keyword_score=0.2)),
        ]

        # Two candidates both cover "build AI platform" — only first should swap in
        cand_ach_1 = _make_achievement("ach_91", "AI1", {
            "Technical": "build AI platform with RAG enterprise",
        })
        cand_score_1 = _make_score("ach_91", "Technical",
                                   "build AI platform with RAG enterprise",
                                   keyword_score=0.3, matched_pp="build AI platform")
        cand_ach_2 = _make_achievement("ach_92", "AI2", {
            "Technical": "build AI platform with semantic caching",
        })
        cand_score_2 = _make_score("ach_92", "Technical",
                                   "build AI platform with semantic caching",
                                   keyword_score=0.25, matched_pp="build AI platform")

        all_scores = [
            (cand_ach_1, cand_ach_1.variants["Technical"], cand_score_1),
            (cand_ach_2, cand_ach_2.variants["Technical"], cand_score_2),
        ]

        result = selector._rebalance_for_pain_points(
            selected=selected, all_scores=all_scores, pain_points=pain_points,
            role_id="test", role_category="senior_engineer",
        )

        # Only one AI candidate should have been swapped in (second is stale)
        ai_ids = [sv.achievement_id for sv in result if sv.achievement_id.startswith("ach_9")]
        assert len(ai_ids) == 1

    def test_rebalance_architecture_boost_interaction(self, selector):
        """Swap eligibility should use base_score, not boosted total_score."""
        pain_points = ["need leadership mentoring"]

        # Architecture-boosted bullet (1.5x) — high total but same base as candidate
        selected = [
            _make_selected("ach_1", "Arch", "Architecture",
                           "Architected distributed system design",
                           _make_score("ach_1", "Architecture",
                                       "Architected distributed system design",
                                       keyword_score=0.3, pain_score=0.0,
                                       role_cat_score=0.5, ach_kw_score=0.2,
                                       arch_boost=1.5)),
        ]

        # Candidate with similar base score but covers pain point
        candidate_ach = _make_achievement("ach_99", "Leadership", {
            "Leadership": "need leadership mentoring team building culture",
        })
        candidate_score = _make_score("ach_99", "Leadership",
                                      "need leadership mentoring team building culture",
                                      keyword_score=0.25, pain_score=0.3,
                                      role_cat_score=0.4, ach_kw_score=0.2,
                                      matched_pp="need leadership mentoring")
        all_scores = [(candidate_ach, candidate_ach.variants["Leadership"], candidate_score)]

        # Base scores are close: ach_1 = 0.3*0.4+0*0.3+0.5*0.2+0.2*0.1 = 0.24
        # ach_99 = 0.25*0.4+0.3*0.3+0.4*0.2+0.2*0.1 = 0.29
        # If using total_score, ach_1 = 0.24*1.5 = 0.36, so 0.36-0.29=0.07 > threshold? No.
        # But with base_score: 0.24-0.29 = -0.05 (candidate is STRONGER) — swap should happen
        result = selector._rebalance_for_pain_points(
            selected=selected, all_scores=all_scores, pain_points=pain_points,
            role_id="test", role_category="ai_architect", target_count=5,
        )

        # Should have appended (fill phase) since len < target
        assert len(result) == 2
        ids = [sv.achievement_id for sv in result]
        assert "ach_99" in ids

    def test_role_generator_propagates_pain_point(self):
        """GeneratedBullet.pain_point_addressed should be populated from variant score."""
        # This tests the role_generator.py line 574 change
        from src.layer6_v2.types import GeneratedBullet

        # Simulate what role_generator does with a selected variant
        score = _make_score("a1", "Technical", "some text", matched_pp="modernize legacy")
        bullet = GeneratedBullet(
            text="some text",
            source_text="core fact",
            pain_point_addressed=score.matched_pain_point or None,
        )
        assert bullet.pain_point_addressed == "modernize legacy"

        # Empty matched_pain_point should become None
        score_empty = _make_score("a2", "Technical", "other text", matched_pp="")
        bullet_empty = GeneratedBullet(
            text="other text",
            source_text="core fact",
            pain_point_addressed=score_empty.matched_pain_point or None,
        )
        assert bullet_empty.pain_point_addressed is None
