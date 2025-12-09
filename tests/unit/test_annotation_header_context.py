"""
Unit tests for annotation header context (Phase 4.5).

Tests the AnnotationHeaderContextBuilder and related functions for:
- Priority extraction and ranking
- Reframe map building
- Gap mitigation generation
- ATS requirements building
- Prompt formatting utilities
"""

import pytest
from typing import Dict, List, Any
from dataclasses import dataclass

from src.layer6_v2.annotation_header_context import (
    AnnotationHeaderContextBuilder,
    build_header_context,
    format_priorities_for_prompt,
    format_ats_guidance_for_prompt,
    calculate_priority_score,
    extract_star_snippet,
    WEIGHT_RELEVANCE,
    WEIGHT_REQUIREMENT,
    WEIGHT_USER_PRIORITY,
    WEIGHT_STAR_EVIDENCE,
    RELEVANCE_SCORES,
    REQUIREMENT_SCORES,
)
from src.layer6_v2.types import (
    AnnotationPriority,
    HeaderGenerationContext,
    ATSRequirement,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def sample_jd_annotations() -> Dict[str, Any]:
    """Create sample JD annotations for testing."""
    return {
        "annotation_version": 1,
        "annotations": [
            {
                "id": "ann-001",
                "is_active": True,
                "status": "approved",
                "target": {"text": "5+ years experience with Kubernetes"},
                "relevance": "core_strength",
                "requirement_type": "must_have",
                "priority": 1,
                "matching_skill": "Kubernetes",
                "reframe_note": None,
                "ats_variants": ["K8s", "kubernetes"],
                "star_ids": ["star-001"],
                "suggested_keywords": ["Kubernetes", "K8s"],
            },
            {
                "id": "ann-002",
                "is_active": True,
                "status": "approved",
                "target": {"text": "Experience with CI/CD pipelines"},
                "relevance": "extremely_relevant",
                "requirement_type": "must_have",
                "priority": 2,
                "matching_skill": "CI/CD",
                "reframe_note": "Frame as 'DevOps automation expertise'",
                "reframe_from": "CI/CD",
                "reframe_to": "DevOps automation expertise",
                "ats_variants": ["continuous integration", "continuous deployment"],
                "star_ids": [],
                "suggested_keywords": ["CI/CD", "DevOps"],
            },
            {
                "id": "ann-003",
                "is_active": True,
                "status": "approved",
                "target": {"text": "GraphQL experience preferred"},
                "relevance": "gap",
                "requirement_type": "nice_to_have",
                "priority": 3,
                "matching_skill": None,
                "reframe_note": "Frame as REST API expertise",
                "reframe_from": "GraphQL",
                "reframe_to": "REST API design",
                "ats_variants": [],
                "star_ids": [],
                "suggested_keywords": [],
            },
            {
                "id": "ann-004",
                "is_active": False,  # Inactive annotation - should be ignored
                "status": "draft",
                "target": {"text": "Java experience"},
                "relevance": "relevant",
                "requirement_type": "must_have",
                "priority": 1,
                "matching_skill": "Java",
                "reframe_note": None,
                "ats_variants": [],
                "star_ids": [],
                "suggested_keywords": [],
            },
            {
                "id": "ann-005",
                "is_active": True,
                "status": "rejected",  # Rejected annotation - should be ignored
                "target": {"text": "Scala experience"},
                "relevance": "core_strength",
                "requirement_type": "must_have",
                "priority": 1,
                "matching_skill": "Scala",
                "reframe_note": None,
                "ats_variants": [],
                "star_ids": [],
                "suggested_keywords": [],
            },
        ],
        "settings": {
            "job_priority": "high",
            "conflict_resolution": "max_boost",
        },
    }


@pytest.fixture
def sample_stars() -> List[Dict[str, Any]]:
    """Create sample STAR records for testing."""
    return [
        {
            "id": "star-001",
            "title": "Kubernetes Migration",
            "metrics": ["Reduced deployment time by 75%", "Zero downtime migration"],
            "impact_summary": "Led team to migrate 50+ services to K8s",
            "condensed_version": "Kubernetes migration achieving 75% faster deployments",
        },
        {
            "id": "star-002",
            "title": "Performance Optimization",
            "metrics": ["Improved API latency by 40%"],
            "impact_summary": "Optimized backend services",
            "condensed_version": "Backend optimization with 40% latency reduction",
        },
    ]


@pytest.fixture
def empty_annotations() -> Dict[str, Any]:
    """Create empty annotations dict."""
    return {
        "annotation_version": 1,
        "annotations": [],
        "settings": {},
    }


# =============================================================================
# PRIORITY SCORE CALCULATION TESTS
# =============================================================================

class TestPriorityScoreCalculation:
    """Tests for the priority score calculation function."""

    def test_maximum_score(self):
        """Core strength + must have + highest priority + STAR evidence = max score."""
        score = calculate_priority_score(
            relevance="core_strength",
            requirement_type="must_have",
            user_priority=1,
            has_star_evidence=True,
        )
        # Expected: 5.0*0.4 + 5.0*0.3 + 5.0*0.2 + 1.0*0.1 = 2.0 + 1.5 + 1.0 + 0.1 = 4.6
        expected = (
            RELEVANCE_SCORES["core_strength"] * WEIGHT_RELEVANCE +
            REQUIREMENT_SCORES["must_have"] * WEIGHT_REQUIREMENT +
            (6 - 1) * WEIGHT_USER_PRIORITY +  # 5 * 0.2 = 1.0
            1.0 * WEIGHT_STAR_EVIDENCE
        )
        assert abs(score - expected) < 0.01

    def test_minimum_score(self):
        """Gap + disqualifier + lowest priority + no evidence = minimum score."""
        score = calculate_priority_score(
            relevance="gap",
            requirement_type="disqualifier",
            user_priority=5,
            has_star_evidence=False,
        )
        # Expected: 1.0*0.4 + 0.0*0.3 + 1.0*0.2 + 0.0*0.1 = 0.4 + 0 + 0.2 + 0 = 0.6
        expected = (
            RELEVANCE_SCORES["gap"] * WEIGHT_RELEVANCE +
            REQUIREMENT_SCORES["disqualifier"] * WEIGHT_REQUIREMENT +
            (6 - 5) * WEIGHT_USER_PRIORITY +  # 1 * 0.2 = 0.2
            0.0 * WEIGHT_STAR_EVIDENCE
        )
        assert abs(score - expected) < 0.01

    def test_middle_score(self):
        """Relevant + nice_to_have + priority 3 + no evidence."""
        score = calculate_priority_score(
            relevance="relevant",
            requirement_type="nice_to_have",
            user_priority=3,
            has_star_evidence=False,
        )
        # Expected: 3.0*0.4 + 3.0*0.3 + 3.0*0.2 + 0 = 1.2 + 0.9 + 0.6 = 2.7
        expected = (
            RELEVANCE_SCORES["relevant"] * WEIGHT_RELEVANCE +
            REQUIREMENT_SCORES["nice_to_have"] * WEIGHT_REQUIREMENT +
            (6 - 3) * WEIGHT_USER_PRIORITY +
            0.0 * WEIGHT_STAR_EVIDENCE
        )
        assert abs(score - expected) < 0.01


# =============================================================================
# STAR SNIPPET EXTRACTION TESTS
# =============================================================================

class TestStarSnippetExtraction:
    """Tests for STAR snippet extraction."""

    def test_extract_metric_from_star(self, sample_stars):
        """Should extract first metric with numbers."""
        snippet = extract_star_snippet(sample_stars[0])
        assert "75%" in snippet

    def test_extract_from_star_without_metrics(self):
        """Should fall back to impact_summary if no metrics."""
        star = {
            "id": "star-no-metrics",
            "metrics": [],
            "impact_summary": "Led a team of 10 engineers",
            "condensed_version": "Leadership role",
        }
        snippet = extract_star_snippet(star)
        assert "Led a team" in snippet

    def test_extract_from_minimal_star(self):
        """Should handle minimal STAR record."""
        star = {
            "id": "star-minimal",
            "metrics": [],
            "impact_summary": "",
            "condensed_version": "Some achievement",
        }
        snippet = extract_star_snippet(star)
        assert "Some achievement" in snippet

    def test_truncate_long_snippet(self):
        """Should truncate snippets over 100 chars."""
        star = {
            "id": "star-long",
            "metrics": [],
            "impact_summary": "A" * 150,  # Long string
            "condensed_version": "",
        }
        snippet = extract_star_snippet(star)
        assert len(snippet) <= 103  # 100 chars + "..."


# =============================================================================
# CONTEXT BUILDER TESTS
# =============================================================================

class TestAnnotationHeaderContextBuilder:
    """Tests for the AnnotationHeaderContextBuilder class."""

    def test_build_context_with_annotations(self, sample_jd_annotations, sample_stars):
        """Should build context with priorities ranked correctly."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations, sample_stars)
        context = builder.build_context()

        assert context.has_annotations
        assert len(context.priorities) >= 2  # At least 2 active annotations

    def test_build_context_empty_annotations(self, empty_annotations):
        """Should return empty context for empty annotations."""
        builder = AnnotationHeaderContextBuilder(empty_annotations)
        context = builder.build_context()

        assert not context.has_annotations
        assert len(context.priorities) == 0

    def test_build_context_none_annotations(self):
        """Should handle None annotations gracefully."""
        builder = AnnotationHeaderContextBuilder(None)
        context = builder.build_context()

        assert not context.has_annotations
        assert len(context.priorities) == 0

    def test_priorities_sorted_by_score(self, sample_jd_annotations, sample_stars):
        """Priorities should be sorted by score descending."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations, sample_stars)
        context = builder.build_context()

        scores = [p.priority_score for p in context.priorities]
        assert scores == sorted(scores, reverse=True)

    def test_ranks_assigned_correctly(self, sample_jd_annotations, sample_stars):
        """Ranks should be 1, 2, 3, etc."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations, sample_stars)
        context = builder.build_context()

        ranks = [p.rank for p in context.priorities]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_inactive_annotations_excluded(self, sample_jd_annotations):
        """Inactive annotations should not be included."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations)
        context = builder.build_context()

        matching_skills = [p.matching_skill for p in context.priorities]
        assert "Java" not in matching_skills  # ann-004 is inactive

    def test_rejected_annotations_excluded(self, sample_jd_annotations):
        """Rejected annotations should not be included."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations)
        context = builder.build_context()

        matching_skills = [p.matching_skill for p in context.priorities]
        assert "Scala" not in matching_skills  # ann-005 is rejected

    def test_star_snippets_extracted(self, sample_jd_annotations, sample_stars):
        """STAR snippets should be extracted for linked stars."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations, sample_stars)
        context = builder.build_context()

        # Find the Kubernetes priority (ann-001 has star-001 linked)
        k8s_priority = next(
            (p for p in context.priorities if p.matching_skill == "Kubernetes"),
            None
        )
        assert k8s_priority is not None
        assert len(k8s_priority.star_snippets) > 0
        assert any("75%" in s for s in k8s_priority.star_snippets)


# =============================================================================
# REFRAME MAP TESTS
# =============================================================================

class TestReframeMap:
    """Tests for reframe map building."""

    def test_reframe_map_built(self, sample_jd_annotations):
        """Should build reframe map from annotations with reframe notes."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations)
        context = builder.build_context()

        assert len(context.reframe_map) > 0
        # CI/CD should have a reframe
        assert "ci/cd" in context.reframe_map or "devops" in str(context.reframe_map).lower()

    def test_reframe_map_by_skill(self, sample_jd_annotations):
        """Should map by matching skill."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations)
        context = builder.build_context()

        # The CI/CD annotation has reframe_from="CI/CD" and reframe_to="DevOps automation expertise"
        # get_reframe expects lowercase key since reframe_map stores lowercase keys
        reframe = context.get_reframe("ci/cd")
        assert reframe is not None


# =============================================================================
# GAP MITIGATION TESTS
# =============================================================================

class TestGapMitigation:
    """Tests for gap mitigation generation."""

    def test_gap_mitigation_with_reframe(self, sample_jd_annotations):
        """Should generate mitigation for gaps with reframe notes."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations)
        context = builder.build_context()

        # ann-003 is a gap with reframe_note
        if context.gap_mitigation:
            assert "REST API" in context.gap_mitigation or "foundation" in context.gap_mitigation.lower()

    def test_gap_mitigation_annotation_id_tracked(self, sample_jd_annotations):
        """Should track the annotation ID used for gap mitigation."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations)
        context = builder.build_context()

        if context.gap_mitigation:
            assert context.gap_mitigation_annotation_id is not None

    def test_no_gap_mitigation_without_reframe(self):
        """Gaps without reframe notes should not generate mitigation."""
        annotations = {
            "annotations": [
                {
                    "id": "gap-no-reframe",
                    "is_active": True,
                    "status": "approved",
                    "target": {"text": "5+ years Java"},
                    "relevance": "gap",
                    "requirement_type": "must_have",
                    "priority": 1,
                    "matching_skill": None,
                    "reframe_note": None,  # No reframe
                    "ats_variants": [],
                    "star_ids": [],
                    "suggested_keywords": [],
                }
            ]
        }
        builder = AnnotationHeaderContextBuilder(annotations)
        context = builder.build_context()

        # No mitigation because gap has no reframe
        assert context.gap_mitigation is None


# =============================================================================
# ATS REQUIREMENTS TESTS
# =============================================================================

class TestATSRequirements:
    """Tests for ATS requirements building."""

    def test_ats_requirements_built(self, sample_jd_annotations):
        """Should build ATS requirements from annotations."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations)
        context = builder.build_context()

        assert len(context.ats_requirements) > 0

    def test_ats_variants_included(self, sample_jd_annotations):
        """Should include ATS variants in requirements."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations)
        context = builder.build_context()

        # Check that Kubernetes requirements include K8s variant
        k8s_req = context.ats_requirements.get("kubernetes")
        if k8s_req:
            assert "K8s" in k8s_req.variants or "k8s" in [v.lower() for v in k8s_req.variants]


# =============================================================================
# PROMPT FORMATTING TESTS
# =============================================================================

class TestPromptFormatting:
    """Tests for prompt formatting utilities."""

    def test_format_priorities_for_prompt(self, sample_jd_annotations, sample_stars):
        """Should format priorities for LLM prompt injection."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations, sample_stars)
        context = builder.build_context()

        prompt_text = format_priorities_for_prompt(context)

        assert "MUST-HAVE" in prompt_text
        assert "Kubernetes" in prompt_text or "CI/CD" in prompt_text

    def test_format_priorities_empty_context(self):
        """Should return empty string for empty context."""
        context = HeaderGenerationContext()
        prompt_text = format_priorities_for_prompt(context)

        assert prompt_text == ""

    def test_format_ats_guidance(self, sample_jd_annotations):
        """Should format ATS requirements for prompt."""
        builder = AnnotationHeaderContextBuilder(sample_jd_annotations)
        context = builder.build_context()

        ats_text = format_ats_guidance_for_prompt(context)

        # Should include guidance text if there are ATS requirements
        if context.ats_requirements:
            assert "ATS" in ats_text or "keyword" in ats_text.lower()


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_build_header_context_function(self, sample_jd_annotations, sample_stars):
        """Should work as a convenience function."""
        context = build_header_context(sample_jd_annotations, sample_stars)

        assert isinstance(context, HeaderGenerationContext)
        assert context.has_annotations

    def test_build_header_context_none(self):
        """Should handle None gracefully."""
        context = build_header_context(None)

        assert isinstance(context, HeaderGenerationContext)
        assert not context.has_annotations


# =============================================================================
# ANNOTATION PRIORITY PROPERTIES TESTS
# =============================================================================

class TestAnnotationPriorityProperties:
    """Tests for AnnotationPriority dataclass properties."""

    def test_is_must_have(self):
        """Should correctly identify must-have priorities."""
        priority = AnnotationPriority(
            rank=1,
            jd_text="test",
            relevance="core_strength",
            requirement_type="must_have",
        )
        assert priority.is_must_have

    def test_is_gap(self):
        """Should correctly identify gap priorities."""
        priority = AnnotationPriority(
            rank=1,
            jd_text="test",
            relevance="gap",
            requirement_type="nice_to_have",
        )
        assert priority.is_gap

    def test_is_core_strength(self):
        """Should correctly identify core strength priorities."""
        priority = AnnotationPriority(
            rank=1,
            jd_text="test",
            relevance="core_strength",
            requirement_type="neutral",
        )
        assert priority.is_core_strength

    def test_has_star_evidence(self):
        """Should correctly identify priorities with STAR evidence."""
        priority = AnnotationPriority(
            rank=1,
            jd_text="test",
            star_snippets=["Reduced latency by 40%"],
        )
        assert priority.has_star_evidence

    def test_has_reframe(self):
        """Should correctly identify priorities with reframe notes."""
        priority = AnnotationPriority(
            rank=1,
            jd_text="test",
            reframe_note="Frame as leadership",
        )
        assert priority.has_reframe

    def test_to_dict(self):
        """Should serialize to dictionary correctly."""
        priority = AnnotationPriority(
            rank=1,
            jd_text="5+ years Kubernetes",
            matching_skill="Kubernetes",
            relevance="core_strength",
            requirement_type="must_have",
            priority_score=4.5,
        )
        d = priority.to_dict()

        assert d["rank"] == 1
        assert d["jd_text"] == "5+ years Kubernetes"
        assert d["matching_skill"] == "Kubernetes"
        assert d["is_must_have"] is True
        assert d["is_core_strength"] is True


# =============================================================================
# HEADER GENERATION CONTEXT PROPERTIES TESTS
# =============================================================================

class TestHeaderGenerationContextProperties:
    """Tests for HeaderGenerationContext dataclass properties."""

    def test_must_have_priorities(self):
        """Should filter to must-have priorities."""
        context = HeaderGenerationContext(
            priorities=[
                AnnotationPriority(rank=1, jd_text="a", requirement_type="must_have"),
                AnnotationPriority(rank=2, jd_text="b", requirement_type="nice_to_have"),
                AnnotationPriority(rank=3, jd_text="c", requirement_type="must_have"),
            ]
        )
        must_haves = context.must_have_priorities
        assert len(must_haves) == 2

    def test_core_strength_priorities(self):
        """Should filter to core strength priorities."""
        context = HeaderGenerationContext(
            priorities=[
                AnnotationPriority(rank=1, jd_text="a", relevance="core_strength"),
                AnnotationPriority(rank=2, jd_text="b", relevance="relevant"),
                AnnotationPriority(rank=3, jd_text="c", relevance="core_strength"),
            ]
        )
        core_strengths = context.core_strength_priorities
        assert len(core_strengths) == 2

    def test_gap_priorities(self):
        """Should filter to gap priorities."""
        context = HeaderGenerationContext(
            priorities=[
                AnnotationPriority(rank=1, jd_text="a", relevance="gap"),
                AnnotationPriority(rank=2, jd_text="b", relevance="relevant"),
            ]
        )
        gaps = context.gap_priorities
        assert len(gaps) == 1

    def test_top_keywords(self):
        """Should extract top keywords from priorities."""
        context = HeaderGenerationContext(
            priorities=[
                AnnotationPriority(rank=1, jd_text="a", matching_skill="Kubernetes"),
                AnnotationPriority(rank=2, jd_text="b", matching_skill="Docker"),
            ]
        )
        keywords = context.top_keywords
        assert "Kubernetes" in keywords
        assert "Docker" in keywords

    def test_has_annotations(self):
        """Should correctly report if annotations exist."""
        empty = HeaderGenerationContext()
        assert not empty.has_annotations

        with_priorities = HeaderGenerationContext(
            priorities=[AnnotationPriority(rank=1, jd_text="test")]
        )
        assert with_priorities.has_annotations

    def test_to_dict(self):
        """Should serialize to dictionary correctly."""
        context = HeaderGenerationContext(
            priorities=[AnnotationPriority(rank=1, jd_text="test")],
            gap_mitigation="Strong foundation in API design",
        )
        d = context.to_dict()

        assert "priorities" in d
        assert d["gap_mitigation"] == "Strong foundation in API design"
        assert d["has_annotations"] is True
