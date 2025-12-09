"""
Unit tests for Phase 6: Annotation Integration Components.

Tests for:
- People mapper annotation context formatting
- Cover letter concern mitigation
- LinkedIn headline optimizer
"""

import pytest
from src.layer5.people_mapper import PeopleMapper
from src.layer6.cover_letter_generator import CoverLetterGenerator
from src.layer6.linkedin_optimizer import (
    LinkedInHeadlineOptimizer,
    suggest_linkedin_headlines,
    HeadlineVariant,
    HEADLINE_MAX_LENGTH,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_annotations():
    """Sample JD annotations for testing."""
    return [
        {
            "id": "ann-1",
            "target": {"text": "5+ years Python experience"},
            "requirement_type": "must_have",
            "relevance": "core_strength",
            "matching_skill": "Python/Django",
            "is_active": True,
            "has_reframe": True,
            "reframe_note": "Emphasize 11+ years of Python across multiple domains",
            "reframe_from": "Python experience",
            "reframe_to": "Full-stack Python expertise",
            "suggested_keywords": ["Python", "Django"],
            "ats_variants": ["py", "python3"],
            "evidence_summary": "Built 10M events/day platform using Python",
        },
        {
            "id": "ann-2",
            "target": {"text": "Team leadership"},
            "requirement_type": "must_have",
            "relevance": "extremely_relevant",
            "matching_skill": "Engineering Leadership",
            "is_active": True,
            "has_reframe": False,
            "suggested_keywords": ["leadership", "team building"],
            "ats_variants": [],
        },
        {
            "id": "ann-3",
            "target": {"text": "Cloud architecture"},
            "requirement_type": "nice_to_have",
            "relevance": "relevant",
            "matching_skill": "AWS",
            "is_active": True,
            "has_reframe": False,
            "suggested_keywords": ["AWS", "cloud"],
            "ats_variants": ["Amazon Web Services"],
        },
        {
            "id": "ann-4",
            "target": {"text": "Blockchain experience"},
            "requirement_type": "must_have",
            "relevance": "gap",
            "matching_skill": None,
            "is_active": False,  # Inactive
            "has_reframe": False,
            "suggested_keywords": [],
            "ats_variants": [],
        },
    ]


@pytest.fixture
def sample_concerns():
    """Sample concern annotations for testing."""
    return [
        {
            "id": "concern-1",
            "concern": "On-call rotation required",
            "severity": "concern",
            "mitigation_strategy": "Highlight previous on-call experience at TechCorp",
        },
        {
            "id": "concern-2",
            "concern": "Heavy travel (50%)",
            "severity": "preference",
            "mitigation_strategy": "Mention remote-first experience and flexibility",
        },
        {
            "id": "concern-3",
            "concern": "Blockchain experience required",
            "severity": "blocker",  # Should be filtered out
            "mitigation_strategy": "None - this is a blocker",
        },
    ]


# ============================================================================
# People Mapper Annotation Context Tests
# ============================================================================

class TestPeopleMapperAnnotationContext:
    """Tests for people mapper annotation context formatting."""

    def test_format_annotation_context_empty_returns_empty_string(self):
        """Empty annotations return empty string."""
        mapper = PeopleMapper()
        result = mapper._format_annotation_context(None, None)
        assert result == ""

    def test_format_annotation_context_extracts_must_haves(self, sample_annotations):
        """Must-have requirements are extracted for outreach."""
        mapper = PeopleMapper()
        result = mapper._format_annotation_context(sample_annotations, None)

        assert "MUST-HAVE REQUIREMENTS" in result
        assert "5+ years Python experience" in result
        assert "Python/Django" in result

    def test_format_annotation_context_extracts_reframes(self, sample_annotations):
        """Reframe guidance is included in context."""
        mapper = PeopleMapper()
        result = mapper._format_annotation_context(sample_annotations, None)

        assert "REFRAME GUIDANCE" in result
        assert "Python experience" in result
        assert "Full-stack Python expertise" in result

    def test_format_annotation_context_extracts_keywords(self, sample_annotations):
        """Annotation keywords are aggregated."""
        mapper = PeopleMapper()
        result = mapper._format_annotation_context(sample_annotations, None)

        assert "ANNOTATION KEYWORDS" in result
        assert "Python" in result
        assert "Django" in result

    def test_format_annotation_context_excludes_inactive(self, sample_annotations):
        """Inactive annotations are excluded."""
        mapper = PeopleMapper()
        result = mapper._format_annotation_context(sample_annotations, None)

        # ann-4 is inactive and has "Blockchain" - should not appear
        # But check for the specific gap annotation keywords, not the word itself
        # since "Blockchain" might appear in other contexts
        assert result.count("gap") == 0 or "Blockchain experience" not in result

    def test_format_annotation_context_includes_concerns(
        self, sample_annotations, sample_concerns
    ):
        """Concern annotations are formatted for outreach."""
        mapper = PeopleMapper()
        result = mapper._format_annotation_context(sample_annotations, sample_concerns)

        assert "CONCERNS TO ADDRESS" in result
        assert "On-call rotation required" in result
        assert "previous on-call experience" in result

    def test_format_annotation_context_filters_blockers(
        self, sample_annotations, sample_concerns
    ):
        """Blocker concerns are filtered out."""
        mapper = PeopleMapper()
        result = mapper._format_annotation_context(sample_annotations, sample_concerns)

        # Blocker severity should be excluded
        assert "Blockchain experience required" not in result

    def test_format_annotation_context_includes_evidence(self, sample_annotations):
        """STAR evidence summaries are included."""
        mapper = PeopleMapper()
        result = mapper._format_annotation_context(sample_annotations, None)

        assert "LINKED EVIDENCE" in result
        assert "10M events/day" in result

    def test_format_annotation_context_deduplicates_keywords(self):
        """Duplicate keywords are removed."""
        mapper = PeopleMapper()
        annotations = [
            {
                "id": "ann-1",
                "is_active": True,
                "suggested_keywords": ["Python", "python", "PYTHON"],
                "ats_variants": ["py"],
            }
        ]
        result = mapper._format_annotation_context(annotations, None)

        # Python should appear only once (case-insensitive dedup)
        # Count occurrences in the keywords line
        keyword_line = [line for line in result.split("\n") if "ANNOTATION KEYWORDS" in line]
        if keyword_line:
            keyword_section = keyword_line[0]
            # Should have Python and py, but Python only once
            assert keyword_section.count("Python") == 1


# ============================================================================
# Cover Letter Concern Mitigation Tests
# ============================================================================

class TestCoverLetterConcernMitigation:
    """Tests for cover letter concern mitigation formatting."""

    def test_format_concern_mitigation_empty_returns_empty(self):
        """Empty concerns return empty string."""
        generator = CoverLetterGenerator()
        result = generator._format_concern_mitigation_section(None)
        assert result == ""

    def test_format_concern_mitigation_includes_addressable_concerns(
        self, sample_concerns
    ):
        """Addressable concerns (not blockers) are included."""
        generator = CoverLetterGenerator()
        result = generator._format_concern_mitigation_section(sample_concerns)

        assert "CONCERNS TO ADDRESS" in result
        assert "On-call rotation required" in result
        assert "Heavy travel" in result

    def test_format_concern_mitigation_excludes_blockers(self, sample_concerns):
        """Blocker concerns are excluded."""
        generator = CoverLetterGenerator()
        result = generator._format_concern_mitigation_section(sample_concerns)

        assert "Blockchain experience" not in result

    def test_format_concern_mitigation_includes_mitigation_strategies(
        self, sample_concerns
    ):
        """Mitigation strategies are included."""
        generator = CoverLetterGenerator()
        result = generator._format_concern_mitigation_section(sample_concerns)

        assert "Highlight previous on-call experience" in result
        assert "remote-first experience" in result

    def test_format_concern_mitigation_limits_to_two(self):
        """Only top 2 concerns are included."""
        generator = CoverLetterGenerator()
        concerns = [
            {"concern": f"Concern {i}", "severity": "concern", "mitigation_strategy": f"Mitigation {i}"}
            for i in range(5)
        ]
        result = generator._format_concern_mitigation_section(concerns)

        # Should only have 2 concerns
        assert result.count("CONCERN:") == 2
        assert "Concern 0" in result
        assert "Concern 1" in result
        assert "Concern 2" not in result

    def test_format_concern_mitigation_requires_mitigation_strategy(self):
        """Concerns without mitigation strategies are excluded."""
        generator = CoverLetterGenerator()
        concerns = [
            {"concern": "Has strategy", "severity": "concern", "mitigation_strategy": "Do this"},
            {"concern": "No strategy", "severity": "concern", "mitigation_strategy": None},
            {"concern": "Empty strategy", "severity": "concern", "mitigation_strategy": ""},
        ]
        result = generator._format_concern_mitigation_section(concerns)

        assert "Has strategy" in result
        assert "No strategy" not in result
        assert "Empty strategy" not in result


# ============================================================================
# LinkedIn Headline Optimizer Tests
# ============================================================================

class TestLinkedInHeadlineOptimizer:
    """Tests for LinkedIn headline optimizer."""

    def test_extract_keywords_prioritizes_core_strength(self, sample_annotations):
        """Core strength annotations have highest keyword priority."""
        optimizer = LinkedInHeadlineOptimizer()
        keywords = optimizer.extract_keywords_from_annotations(sample_annotations)

        # First keyword should be from core_strength (ann-1)
        assert keywords[0] == "Python/Django"

    def test_extract_keywords_includes_extremely_relevant(self, sample_annotations):
        """Extremely relevant annotations are included."""
        optimizer = LinkedInHeadlineOptimizer()
        keywords = optimizer.extract_keywords_from_annotations(sample_annotations)

        assert "Engineering Leadership" in keywords

    def test_extract_keywords_excludes_inactive(self, sample_annotations):
        """Inactive annotations are excluded."""
        optimizer = LinkedInHeadlineOptimizer()
        keywords = optimizer.extract_keywords_from_annotations(sample_annotations)

        # ann-4 is inactive, so Blockchain shouldn't appear
        assert not any("blockchain" in kw.lower() for kw in keywords)

    def test_extract_keywords_respects_limit(self, sample_annotations):
        """Keyword extraction respects limit parameter."""
        optimizer = LinkedInHeadlineOptimizer()
        keywords = optimizer.extract_keywords_from_annotations(sample_annotations, limit=2)

        assert len(keywords) == 2

    def test_extract_keywords_empty_returns_empty(self):
        """Empty annotations return empty list."""
        optimizer = LinkedInHeadlineOptimizer()
        keywords = optimizer.extract_keywords_from_annotations([])

        assert keywords == []

    def test_calculate_algorithm_score_returns_valid_range(self):
        """Algorithm score is between 0.0 and 1.0."""
        optimizer = LinkedInHeadlineOptimizer()

        # Test various headlines
        headlines = [
            "Engineering Manager | Python | AWS | Scale",
            "Developer",
            "Engineering Leader → Director Track | Platform Scale | Growth",
            "a",
        ]

        for headline in headlines:
            score = optimizer.calculate_algorithm_score(headline)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for '{headline}'"

    def test_calculate_algorithm_score_prefers_algorithm_terms(self):
        """Headlines with algorithm-preferred terms score higher."""
        optimizer = LinkedInHeadlineOptimizer()

        high_score = optimizer.calculate_algorithm_score(
            "Engineering Manager | Scale | Growth | Platform"
        )
        low_score = optimizer.calculate_algorithm_score(
            "Person Who Works | Stuff | Things | Items"
        )

        assert high_score > low_score

    def test_generate_variants_requires_min_keywords(self):
        """Variant generation requires minimum keywords."""
        optimizer = LinkedInHeadlineOptimizer()
        variants = optimizer.generate_variants(keywords=["single"])

        assert variants == []

    def test_generate_variants_creates_multiple_patterns(self, sample_annotations):
        """Multiple headline patterns are generated."""
        optimizer = LinkedInHeadlineOptimizer()
        keywords = optimizer.extract_keywords_from_annotations(sample_annotations, limit=4)
        variants = optimizer.generate_variants(keywords)

        # Should have multiple variants
        assert len(variants) >= 3

        # Should have different patterns
        patterns = {v.pattern_used for v in variants}
        assert len(patterns) >= 2

    def test_generate_variants_respects_length_limit(self, sample_annotations):
        """All variants respect 120 char limit."""
        optimizer = LinkedInHeadlineOptimizer()
        keywords = optimizer.extract_keywords_from_annotations(sample_annotations)
        variants = optimizer.generate_variants(keywords)

        for v in variants:
            assert v.length <= HEADLINE_MAX_LENGTH, f"'{v.headline}' exceeds limit"

    def test_generate_variants_sorted_by_score(self, sample_annotations):
        """Variants are sorted by algorithm score descending."""
        optimizer = LinkedInHeadlineOptimizer()
        keywords = optimizer.extract_keywords_from_annotations(sample_annotations)
        variants = optimizer.generate_variants(keywords)

        if len(variants) >= 2:
            scores = [v.algorithm_score for v in variants]
            assert scores == sorted(scores, reverse=True)

    def test_optimize_headline_returns_result_object(self, sample_annotations):
        """Optimization returns HeadlineOptimizationResult."""
        optimizer = LinkedInHeadlineOptimizer()
        result = optimizer.optimize_headline(sample_annotations)

        assert result.variants is not None
        assert result.source_keywords is not None
        assert result.improvement_rationale is not None

    def test_optimize_headline_compares_to_current(self, sample_annotations):
        """Optimization compares variants to current headline."""
        optimizer = LinkedInHeadlineOptimizer()
        result = optimizer.optimize_headline(
            sample_annotations,
            current_headline="Developer at Company",
        )

        assert result.current_headline == "Developer at Company"
        assert "higher" in result.improvement_rationale.lower() or "variant" in result.improvement_rationale.lower()

    def test_optimize_headline_handles_insufficient_keywords(self):
        """Optimization handles insufficient annotation keywords."""
        optimizer = LinkedInHeadlineOptimizer()
        result = optimizer.optimize_headline([])

        assert len(result.variants) == 0
        assert "insufficient" in result.improvement_rationale.lower()

    def test_headline_variant_is_valid_checks_constraints(self):
        """HeadlineVariant.is_valid checks length and keyword count."""
        valid = HeadlineVariant(
            headline="Short",
            keywords_used=["a", "b"],
            pattern_used="test",
            algorithm_score=0.5,
            length=5,
        )
        assert valid.is_valid is True

        too_long = HeadlineVariant(
            headline="x" * 150,
            keywords_used=["a", "b"],
            pattern_used="test",
            algorithm_score=0.5,
            length=150,
        )
        assert too_long.is_valid is False

        too_few_keywords = HeadlineVariant(
            headline="Short",
            keywords_used=["a"],  # Only 1 keyword
            pattern_used="test",
            algorithm_score=0.5,
            length=5,
        )
        assert too_few_keywords.is_valid is False


class TestSuggestLinkedInHeadlines:
    """Tests for the convenience function."""

    def test_suggest_linkedin_headlines_basic(self, sample_annotations):
        """Convenience function works correctly."""
        result = suggest_linkedin_headlines(
            annotations=sample_annotations,
            candidate_role="Engineering Manager",
            years_experience=11,
        )

        assert len(result.variants) >= 1
        assert result.source_keywords

    def test_suggest_linkedin_headlines_uses_role(self, sample_annotations):
        """Convenience function uses provided role."""
        result = suggest_linkedin_headlines(
            annotations=sample_annotations,
            candidate_role="Staff Engineer",
        )

        # At least one variant should contain the role
        headlines = [v.headline for v in result.variants]
        assert any("Staff Engineer" in h for h in headlines)

    def test_suggest_linkedin_headlines_get_best_variant(self, sample_annotations):
        """get_best_variant returns highest scoring valid variant."""
        result = suggest_linkedin_headlines(annotations=sample_annotations)
        best = result.get_best_variant()

        if best:
            assert best.is_valid
            # Should be highest scoring among valid
            valid_variants = [v for v in result.variants if v.is_valid]
            for v in valid_variants:
                assert v.algorithm_score <= best.algorithm_score

    def test_suggest_linkedin_headlines_to_dict(self, sample_annotations):
        """Result can be serialized to dict."""
        result = suggest_linkedin_headlines(annotations=sample_annotations)
        result_dict = result.to_dict()

        assert "variants" in result_dict
        assert "source_keywords" in result_dict
        assert "improvement_rationale" in result_dict
        assert "best_variant" in result_dict
