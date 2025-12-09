"""
Unit tests for the JD Annotation System - Phase 1 components.

Tests cover:
1. annotation_types.py - Type definitions and constants
2. annotation_validator.py - Validation rules (lints) and boost calculations
3. jd_processor.py - JD structuring into annotatable sections
"""

import pytest
from datetime import datetime
from uuid import uuid4

from src.common.annotation_types import (
    JDAnnotation,
    JDAnnotations,
    TextSpan,
    AnnotationSettings,
    ConcernAnnotation,
    RELEVANCE_MULTIPLIERS,
    REQUIREMENT_MULTIPLIERS,
    PRIORITY_MULTIPLIERS,
    TYPE_MODIFIERS,
    RELEVANCE_COLORS,
)
from src.common.annotation_validator import (
    validate_core_strength_has_star,
    validate_gap_has_mitigation,
    validate_must_have_gap_warning,
    validate_no_overlapping_spans,
    validate_single_annotation,
    validate_annotations,
    calculate_annotation_boost,
    aggregate_annotation_boosts,
    ValidationSeverity,
    ValidationResult,
)
from src.layer1_4.jd_processor import (
    process_jd_sync,
    JDSectionType,
    detect_section_type,
    split_into_items,
    parse_jd_sections_rule_based,
    generate_processed_html,
    processed_jd_to_dict,
    dict_to_processed_jd,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_text_span() -> TextSpan:
    """Create a sample text span for testing."""
    return {
        "section": "responsibilities",
        "index": 0,
        "text": "Lead a team of 10+ engineers",
        "char_start": 100,
        "char_end": 130,
    }


@pytest.fixture
def sample_annotation(sample_text_span) -> JDAnnotation:
    """Create a sample annotation for testing."""
    return {
        "id": str(uuid4()),
        "target": sample_text_span,
        "created_at": datetime.now().isoformat(),
        "created_by": "human",
        "updated_at": datetime.now().isoformat(),
        "status": "draft",
        "last_reviewed_by": None,
        "review_note": None,
        "annotation_type": "skill_match",
        "relevance": "core_strength",
        "requirement_type": "must_have",
        "matching_skill": "Team Leadership",
        "has_reframe": False,
        "reframe_note": None,
        "reframe_from": None,
        "reframe_to": None,
        "star_ids": ["star-001", "star-002"],
        "evidence_summary": "Led 15-person team at Company X",
        "suggested_keywords": ["team lead", "engineering manager"],
        "ats_variants": [],
        "min_occurrences": None,
        "max_occurrences": None,
        "preferred_sections": [],
        "exact_phrase_match": False,
        "achievement_context": None,
        "comment": None,
        "highlight_color": None,
        "is_active": True,
        "priority": 1,
        "confidence": 0.95,
    }


@pytest.fixture
def sample_gap_annotation(sample_text_span) -> JDAnnotation:
    """Create a sample gap annotation for testing."""
    return {
        "id": str(uuid4()),
        "target": sample_text_span,
        "created_at": datetime.now().isoformat(),
        "created_by": "human",
        "updated_at": datetime.now().isoformat(),
        "status": "draft",
        "last_reviewed_by": None,
        "review_note": None,
        "annotation_type": "skill_match",
        "relevance": "gap",
        "requirement_type": "must_have",
        "matching_skill": "AWS Certification",
        "has_reframe": False,
        "reframe_note": None,  # Missing mitigation - should fail validation
        "reframe_from": None,
        "reframe_to": None,
        "star_ids": [],
        "evidence_summary": None,
        "suggested_keywords": ["AWS", "cloud"],
        "ats_variants": [],
        "min_occurrences": None,
        "max_occurrences": None,
        "preferred_sections": [],
        "exact_phrase_match": False,
        "achievement_context": None,
        "comment": None,
        "highlight_color": None,
        "is_active": True,
        "priority": 2,
        "confidence": 0.8,
    }


@pytest.fixture
def sample_jd_text() -> str:
    """Sample job description text for testing."""
    return """
    About the Role

    We are looking for a Senior Engineering Manager to lead our platform team.

    Responsibilities:
    - Lead a team of 10+ engineers building real-time data pipelines
    - Define technical strategy and roadmap
    - Partner with product to deliver features
    - Mentor and grow team members

    Qualifications:
    - 5+ years of engineering management experience
    - Strong background in distributed systems
    - Experience with Python and cloud platforms

    Nice to Have:
    - Experience with Kubernetes
    - AdTech background
    """


# =============================================================================
# TEST: ANNOTATION TYPES
# =============================================================================

class TestAnnotationTypes:
    """Tests for annotation_types.py type definitions and constants."""

    def test_relevance_multipliers_complete(self):
        """Verify all relevance levels have multipliers."""
        expected = {"core_strength", "extremely_relevant", "relevant", "tangential", "gap"}
        assert set(RELEVANCE_MULTIPLIERS.keys()) == expected

    def test_relevance_multipliers_values(self):
        """Verify multiplier values match spec."""
        assert RELEVANCE_MULTIPLIERS["core_strength"] == 3.0
        assert RELEVANCE_MULTIPLIERS["extremely_relevant"] == 2.0
        assert RELEVANCE_MULTIPLIERS["relevant"] == 1.5
        assert RELEVANCE_MULTIPLIERS["tangential"] == 1.0
        assert RELEVANCE_MULTIPLIERS["gap"] == 0.3

    def test_requirement_multipliers_complete(self):
        """Verify all requirement types have multipliers."""
        expected = {"must_have", "nice_to_have", "disqualifier", "neutral"}
        assert set(REQUIREMENT_MULTIPLIERS.keys()) == expected

    def test_requirement_multipliers_values(self):
        """Verify requirement multiplier values."""
        assert REQUIREMENT_MULTIPLIERS["must_have"] == 1.5
        assert REQUIREMENT_MULTIPLIERS["nice_to_have"] == 1.0
        assert REQUIREMENT_MULTIPLIERS["disqualifier"] == 0.0
        assert REQUIREMENT_MULTIPLIERS["neutral"] == 1.0

    def test_priority_multipliers_complete(self):
        """Verify all priority levels have multipliers."""
        expected = {1, 2, 3, 4, 5}
        assert set(PRIORITY_MULTIPLIERS.keys()) == expected

    def test_relevance_colors_complete(self):
        """Verify all relevance levels have color definitions."""
        expected = {"core_strength", "extremely_relevant", "relevant", "tangential", "gap"}
        assert set(RELEVANCE_COLORS.keys()) == expected

    def test_relevance_colors_have_required_keys(self):
        """Verify each color definition has required keys."""
        required_keys = {"bg", "border", "badge", "hex"}
        for level, colors in RELEVANCE_COLORS.items():
            assert set(colors.keys()) == required_keys, f"Missing keys for {level}"


# =============================================================================
# TEST: ANNOTATION VALIDATOR
# =============================================================================

class TestAnnotationValidator:
    """Tests for annotation_validator.py validation rules."""

    def test_core_strength_with_star_passes(self, sample_annotation):
        """Core strength with STAR link should pass."""
        result = validate_core_strength_has_star(sample_annotation)
        assert result.passed is True
        assert result.severity == ValidationSeverity.ERROR

    def test_core_strength_without_star_fails(self, sample_annotation):
        """Core strength without STAR link should fail."""
        sample_annotation["star_ids"] = []
        result = validate_core_strength_has_star(sample_annotation)
        assert result.passed is False
        assert result.severity == ValidationSeverity.ERROR
        assert "STAR" in result.message

    def test_non_core_strength_skips_star_check(self, sample_annotation):
        """Non-core-strength annotations skip STAR check."""
        sample_annotation["relevance"] = "relevant"
        sample_annotation["star_ids"] = []
        result = validate_core_strength_has_star(sample_annotation)
        assert result.passed is True

    def test_gap_with_mitigation_passes(self, sample_gap_annotation):
        """Gap with mitigation strategy should pass."""
        sample_gap_annotation["reframe_note"] = "I have 2 years experience plus adjacent skills..."
        result = validate_gap_has_mitigation(sample_gap_annotation)
        assert result.passed is True

    def test_gap_without_mitigation_fails(self, sample_gap_annotation):
        """Gap without mitigation should fail."""
        result = validate_gap_has_mitigation(sample_gap_annotation)
        assert result.passed is False
        assert result.severity == ValidationSeverity.ERROR
        assert "mitigation" in result.message.lower()

    def test_must_have_gap_triggers_warning(self, sample_gap_annotation):
        """Must-have gap should trigger warning."""
        result = validate_must_have_gap_warning(sample_gap_annotation)
        assert result.passed is False
        assert result.severity == ValidationSeverity.WARNING
        assert "must-have gap" in result.message.lower()

    def test_nice_to_have_gap_no_warning(self, sample_gap_annotation):
        """Nice-to-have gap should not trigger warning."""
        sample_gap_annotation["requirement_type"] = "nice_to_have"
        result = validate_must_have_gap_warning(sample_gap_annotation)
        assert result.passed is True

    def test_validate_single_annotation_complete(self, sample_annotation):
        """Single annotation validation runs all rules."""
        report = validate_single_annotation(sample_annotation)
        assert report.passed is True
        assert report.error_count == 0

    def test_validate_single_annotation_fails_on_error(self, sample_annotation):
        """Single annotation validation fails on error."""
        sample_annotation["star_ids"] = []
        report = validate_single_annotation(sample_annotation)
        assert report.passed is False
        assert report.error_count > 0


class TestOverlappingSpans:
    """Tests for overlapping span detection."""

    def test_non_overlapping_passes(self, sample_annotation):
        """Non-overlapping annotations should pass."""
        ann1 = sample_annotation.copy()
        ann1["target"] = {"section": "responsibilities", "char_start": 0, "char_end": 50, "index": 0, "text": "text1"}

        ann2 = sample_annotation.copy()
        ann2["id"] = str(uuid4())
        ann2["target"] = {"section": "responsibilities", "char_start": 60, "char_end": 100, "index": 1, "text": "text2"}

        results = validate_no_overlapping_spans([ann1, ann2])
        warnings = [r for r in results if not r.passed]
        assert len(warnings) == 0

    def test_overlapping_triggers_warning(self, sample_annotation):
        """Significantly overlapping annotations should trigger warning."""
        ann1 = sample_annotation.copy()
        ann1["target"] = {"section": "responsibilities", "char_start": 0, "char_end": 100, "index": 0, "text": "text1"}

        ann2 = sample_annotation.copy()
        ann2["id"] = str(uuid4())
        ann2["target"] = {"section": "responsibilities", "char_start": 20, "char_end": 80, "index": 1, "text": "text2"}

        results = validate_no_overlapping_spans([ann1, ann2])
        warnings = [r for r in results if not r.passed]
        assert len(warnings) > 0

    def test_different_sections_no_overlap(self, sample_annotation):
        """Annotations in different sections don't overlap."""
        ann1 = sample_annotation.copy()
        ann1["target"] = {"section": "responsibilities", "char_start": 0, "char_end": 100, "index": 0, "text": "text1"}

        ann2 = sample_annotation.copy()
        ann2["id"] = str(uuid4())
        ann2["target"] = {"section": "qualifications", "char_start": 0, "char_end": 100, "index": 0, "text": "text2"}

        results = validate_no_overlapping_spans([ann1, ann2])
        warnings = [r for r in results if not r.passed]
        assert len(warnings) == 0


class TestBoostCalculation:
    """Tests for annotation boost calculations."""

    def test_core_strength_must_have_priority_1(self, sample_annotation):
        """Core strength + must-have + priority 1 gives maximum boost."""
        boost, metadata = calculate_annotation_boost(sample_annotation)
        # 3.0 * 1.5 * 1.5 * 1.0 = 6.75
        assert boost == pytest.approx(6.75, rel=0.01)

    def test_gap_gets_penalty(self, sample_gap_annotation):
        """Gap annotation gets penalty multiplier."""
        boost, metadata = calculate_annotation_boost(sample_gap_annotation)
        # 0.3 * 1.5 * 1.3 * 1.0 = 0.585 (gap * must_have * priority_2 * skill_match)
        assert boost < 1.0
        assert metadata["relevance"] == "gap"

    def test_disqualifier_gets_zero(self, sample_annotation):
        """Disqualifier requirement type gives zero boost."""
        sample_annotation["requirement_type"] = "disqualifier"
        boost, metadata = calculate_annotation_boost(sample_annotation)
        assert boost == 0.0

    def test_metadata_includes_all_factors(self, sample_annotation):
        """Boost metadata includes all calculation factors."""
        _, metadata = calculate_annotation_boost(sample_annotation)
        assert "annotation_id" in metadata
        assert "relevance" in metadata
        assert "relevance_mult" in metadata
        assert "requirement_type" in metadata
        assert "total_boost" in metadata

    def test_aggregate_boosts_max_strategy(self, sample_annotation):
        """Aggregate with max_boost strategy uses highest boost."""
        ann1 = sample_annotation.copy()
        ann1["relevance"] = "core_strength"

        ann2 = sample_annotation.copy()
        ann2["id"] = str(uuid4())
        ann2["relevance"] = "relevant"

        result = aggregate_annotation_boosts([ann1, ann2], "max_boost")
        # Should have entries for both annotations
        assert len(result) > 0


# =============================================================================
# TEST: JD PROCESSOR
# =============================================================================

class TestJDProcessor:
    """Tests for jd_processor.py JD structuring."""

    def test_detect_section_type_responsibilities(self):
        """Detect responsibilities section."""
        assert detect_section_type("Responsibilities") == JDSectionType.RESPONSIBILITIES
        assert detect_section_type("What You'll Do") == JDSectionType.RESPONSIBILITIES
        assert detect_section_type("Your Role") == JDSectionType.RESPONSIBILITIES

    def test_detect_section_type_qualifications(self):
        """Detect qualifications section (includes 'requirements' as synonym)."""
        assert detect_section_type("Qualifications") == JDSectionType.QUALIFICATIONS
        assert detect_section_type("What We're Looking For") == JDSectionType.QUALIFICATIONS
        # "Requirements" maps to QUALIFICATIONS as they're used interchangeably in JDs
        assert detect_section_type("Requirements") == JDSectionType.QUALIFICATIONS

    def test_detect_section_type_nice_to_have(self):
        """Detect nice-to-have section."""
        assert detect_section_type("Nice to Have") == JDSectionType.NICE_TO_HAVE
        assert detect_section_type("Preferred") == JDSectionType.NICE_TO_HAVE
        assert detect_section_type("Bonus") == JDSectionType.NICE_TO_HAVE

    def test_detect_section_type_fallback(self):
        """Unknown headers fall back to OTHER."""
        assert detect_section_type("Random Header") == JDSectionType.OTHER

    def test_split_into_items_bullets(self):
        """Split bullet point content."""
        content = """- Item one
        - Item two
        - Item three"""
        items = split_into_items(content)
        assert len(items) == 3
        assert "Item one" in items[0]

    def test_split_into_items_numbered(self):
        """Split numbered list content."""
        content = """1. First item
        2. Second item
        3. Third item"""
        items = split_into_items(content)
        assert len(items) == 3

    def test_process_jd_sync_basic(self, sample_jd_text):
        """Basic JD processing works."""
        result = process_jd_sync(sample_jd_text)
        assert result.raw_text == sample_jd_text
        assert len(result.sections) > 0
        assert result.html is not None
        assert result.content_hash is not None

    def test_process_jd_sync_sections_have_required_fields(self, sample_jd_text):
        """Processed sections have all required fields."""
        result = process_jd_sync(sample_jd_text)
        for section in result.sections:
            assert section.section_type is not None
            assert section.header is not None
            assert section.content is not None
            assert section.char_start >= 0
            assert section.char_end > section.char_start
            assert section.index >= 0

    def test_process_jd_sync_html_has_sections(self, sample_jd_text):
        """Generated HTML contains section tags."""
        result = process_jd_sync(sample_jd_text)
        assert "<section" in result.html
        assert "data-section-type" in result.html
        assert "data-char-start" in result.html

    def test_process_jd_sync_detects_responsibilities(self, sample_jd_text):
        """Responsibilities section is detected."""
        result = process_jd_sync(sample_jd_text)
        section_types = [s.section_type for s in result.sections]
        assert JDSectionType.RESPONSIBILITIES in section_types

    def test_process_jd_sync_detects_qualifications(self, sample_jd_text):
        """Qualifications section is detected."""
        result = process_jd_sync(sample_jd_text)
        section_types = [s.section_type for s in result.sections]
        assert JDSectionType.QUALIFICATIONS in section_types

    def test_processed_jd_serialization(self, sample_jd_text):
        """ProcessedJD can be serialized and deserialized."""
        original = process_jd_sync(sample_jd_text)
        as_dict = processed_jd_to_dict(original)
        restored = dict_to_processed_jd(as_dict)

        assert restored.raw_text == original.raw_text
        assert restored.content_hash == original.content_hash
        assert len(restored.sections) == len(original.sections)

    def test_process_jd_sync_empty_input(self):
        """Empty JD text creates single 'other' section."""
        result = process_jd_sync("")
        assert len(result.sections) == 1
        assert result.sections[0].section_type == JDSectionType.OTHER


class TestJDProcessorHTMLGeneration:
    """Tests for HTML generation in jd_processor."""

    def test_html_escapes_special_chars(self):
        """HTML special characters are escaped."""
        jd_text = """Responsibilities:
        - Work with <script> tags & "quotes"
        """
        result = process_jd_sync(jd_text)
        assert "<script>" not in result.html
        assert "&lt;script&gt;" in result.html or "&amp;" in result.html

    def test_html_has_item_data_attributes(self, sample_jd_text):
        """HTML items have data attributes for annotation targeting."""
        result = process_jd_sync(sample_jd_text)
        assert "data-item-index" in result.html
        assert "data-char-start" in result.html
        assert "data-char-end" in result.html

    def test_html_section_ids_unique(self, sample_jd_text):
        """Section IDs in HTML are unique."""
        result = process_jd_sync(sample_jd_text)
        import re
        ids = re.findall(r'id="([^"]+)"', result.html)
        assert len(ids) == len(set(ids)), "Duplicate IDs found"


# =============================================================================
# TEST: COMPLETE VALIDATION FLOW
# =============================================================================

class TestCompleteValidationFlow:
    """Integration tests for complete annotation validation flow."""

    def test_valid_annotation_set_passes(self, sample_annotation):
        """Valid annotation set passes all validations."""
        annotations = {
            "annotation_version": 1,
            "processed_jd_html": "<p>test</p>",
            "annotations": [sample_annotation],
            "concerns": [],
            "settings": {
                "job_priority": "high",
                "deadline": None,
                "require_full_section_coverage": False,
                "section_coverage": {},
                "auto_approve_presets": True,
                "conflict_resolution": "max_boost",
            },
            "section_summaries": {},
            "relevance_counts": {},
            "type_counts": {},
            "reframe_count": 0,
            "gap_count": 0,
            "validation_passed": True,
            "validation_errors": [],
            "ats_readiness_score": 85,
        }

        report = validate_annotations(annotations)
        assert report.passed is True
        assert report.error_count == 0

    def test_invalid_annotation_set_fails(self, sample_annotation):
        """Invalid annotation set fails validation."""
        # Make annotation invalid: core_strength without STAR
        sample_annotation["relevance"] = "core_strength"
        sample_annotation["star_ids"] = []

        annotations = {
            "annotation_version": 1,
            "processed_jd_html": "<p>test</p>",
            "annotations": [sample_annotation],
            "concerns": [],
            "settings": {},
            "section_summaries": {},
            "relevance_counts": {},
            "type_counts": {},
            "reframe_count": 0,
            "gap_count": 0,
            "validation_passed": False,
            "validation_errors": [],
            "ats_readiness_score": None,
        }

        report = validate_annotations(annotations)
        assert report.passed is False
        assert report.error_count > 0
        assert any("STAR" in e for e in report.error_messages)
