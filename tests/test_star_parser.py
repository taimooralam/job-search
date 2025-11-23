"""
Unit tests for STAR record parser and validation.

Tests the canonical STAR parser against knowledge-base.md and validates
that all records conform to the STARRecord schema.
"""

import pytest
from pathlib import Path
from typing import List

from src.common.star_parser import parse_star_records, validate_star_record, _parse_single_star
from src.common.types import STARRecord, OUTCOME_TYPES


@pytest.fixture
def knowledge_base_path() -> str:
    """Path to the knowledge base file."""
    return str(Path(__file__).parent.parent / "knowledge-base.md")


@pytest.fixture
def parsed_stars(knowledge_base_path: str) -> List[STARRecord]:
    """Parse all STAR records from knowledge base."""
    return parse_star_records(knowledge_base_path)


class TestSTARParser:
    """Test suite for STAR record parsing."""

    def test_parse_all_records(self, parsed_stars: List[STARRecord]):
        """Test that all 11 STAR records are parsed successfully."""
        assert len(parsed_stars) == 11, f"Expected 11 records, got {len(parsed_stars)}"

    def test_first_star_id(self, parsed_stars: List[STARRecord]):
        """Test that first STAR has expected ID."""
        expected_id = "b7e9df84-84b3-4957-93f1-7f1adfe5588c"
        assert parsed_stars[0]['id'] == expected_id

    def test_all_stars_have_required_fields(self, parsed_stars: List[STARRecord]):
        """Test that all STARs have required fields populated."""
        required_fields = ['id', 'company', 'role_title', 'period']

        for i, star in enumerate(parsed_stars, 1):
            for field in required_fields:
                assert star[field], f"STAR #{i} missing required field: {field}"

    def test_all_stars_have_pain_points(self, parsed_stars: List[STARRecord]):
        """Test that all STARs have at least one pain point addressed."""
        for i, star in enumerate(parsed_stars, 1):
            pain_points = star['pain_points_addressed']
            assert len(pain_points) >= 1, f"STAR #{i} has no pain points"
            assert len(pain_points) <= 3, f"STAR #{i} has too many pain points ({len(pain_points)})"

    def test_all_stars_have_outcome_types(self, parsed_stars: List[STARRecord]):
        """Test that all STARs have at least one outcome type."""
        for i, star in enumerate(parsed_stars, 1):
            outcome_types = star['outcome_types']
            assert len(outcome_types) >= 1, f"STAR #{i} has no outcome types"

    def test_outcome_types_are_valid(self, parsed_stars: List[STARRecord]):
        """Test that all outcome types are from the canonical list."""
        for i, star in enumerate(parsed_stars, 1):
            for ot in star['outcome_types']:
                assert ot in OUTCOME_TYPES, f"STAR #{i} has invalid outcome type: {ot}"

    def test_all_stars_have_metrics(self, parsed_stars: List[STARRecord]):
        """Test that all STARs have at least one quantified metric."""
        for i, star in enumerate(parsed_stars, 1):
            assert len(star['metrics']) >= 1, f"STAR #{i} has no metrics"

    def test_all_stars_have_condensed_version(self, parsed_stars: List[STARRecord]):
        """Test that all STARs have a condensed version."""
        for i, star in enumerate(parsed_stars, 1):
            condensed = star['condensed_version']
            assert condensed, f"STAR #{i} has no condensed version"
            assert len(condensed) >= 50, f"STAR #{i} condensed version too short"

    def test_all_stars_have_hard_skills(self, parsed_stars: List[STARRecord]):
        """Test that all STARs have hard skills listed."""
        for i, star in enumerate(parsed_stars, 1):
            assert len(star['hard_skills']) >= 1, f"STAR #{i} has no hard skills"

    def test_all_stars_have_soft_skills(self, parsed_stars: List[STARRecord]):
        """Test that all STARs have soft skills listed."""
        for i, star in enumerate(parsed_stars, 1):
            assert len(star['soft_skills']) >= 1, f"STAR #{i} has no soft skills"

    def test_all_stars_have_actions(self, parsed_stars: List[STARRecord]):
        """Test that all STARs have action items listed."""
        for i, star in enumerate(parsed_stars, 1):
            assert len(star['actions']) >= 1, f"STAR #{i} has no actions"

    def test_all_stars_have_results(self, parsed_stars: List[STARRecord]):
        """Test that all STARs have results listed."""
        for i, star in enumerate(parsed_stars, 1):
            assert len(star['results']) >= 1, f"STAR #{i} has no results"

    def test_validator_function(self, parsed_stars: List[STARRecord]):
        """Test that validate_star_record returns no issues for valid records."""
        for i, star in enumerate(parsed_stars, 1):
            issues = validate_star_record(star)
            assert len(issues) == 0, f"STAR #{i} has validation issues: {issues}"

    def test_embedding_field_optional(self, parsed_stars: List[STARRecord]):
        """Test that embedding field is optional (None by default)."""
        for star in parsed_stars:
            # Should be None or a list of floats
            assert star['embedding'] is None or isinstance(star['embedding'], list)


class TestSTARParserEdgeCases:
    """Test edge cases and error handling."""

    def test_parse_missing_file(self):
        """Test that parser raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            parse_star_records("/nonexistent/path/to/file.md")

    def test_parse_malformed_markdown(self, tmp_path):
        """Test that parser handles malformed markdown gracefully."""
        # Create a temporary malformed file
        malformed_file = tmp_path / "malformed.md"
        malformed_file.write_text("This is not a STAR record format")

        with pytest.raises(ValueError, match="No STAR records found"):
            parse_star_records(str(malformed_file))

    def test_parse_incomplete_record(self, tmp_path):
        """Test that parser warns about incomplete records."""
        # Create a record missing required fields
        incomplete_file = tmp_path / "incomplete.md"
        incomplete_file.write_text("""
================================================================================
STAR RECORD #1
================================================================================

ID: test-id-123

COMPANY: Test Company

SITUATION:
This is a test situation.
""")

        # Parser should raise ValueError when no valid records found
        with pytest.raises(ValueError, match="Failed to parse any STAR records"):
            parse_star_records(str(incomplete_file))


class TestSTARValidation:
    """Test validation function behavior."""

    def test_validate_complete_record(self, parsed_stars: List[STARRecord]):
        """Test validation of complete record."""
        star = parsed_stars[0]
        issues = validate_star_record(star)
        assert len(issues) == 0

    def test_validate_missing_id(self):
        """Test validation catches missing ID."""
        star = STARRecord(
            id="",
            company="Test",
            role_title="Test Role",
            period="2020-2021",
            domain_areas=["Test"],
            background_context="Test",
            situation="Test",
            tasks=["Test"],
            actions=["Test"],
            results=["Test"],
            impact_summary="Test",
            condensed_version="Test",
            ats_keywords=["Test"],
            categories=["Test"],
            hard_skills=["Test"],
            soft_skills=["Test"],
            metrics=["Test"],
            pain_points_addressed=["Test"],
            outcome_types=["cost_reduction"],
            target_roles=["Test"],
            metadata={},
            embedding=None
        )
        issues = validate_star_record(star)
        assert "Missing ID" in issues

    def test_validate_missing_metrics(self):
        """Test validation catches missing metrics."""
        star = STARRecord(
            id="test-123",
            company="Test",
            role_title="Test Role",
            period="2020-2021",
            domain_areas=["Test"],
            background_context="Test",
            situation="Test",
            tasks=["Test"],
            actions=["Test"],
            results=["Test"],
            impact_summary="Test",
            condensed_version="Test",
            ats_keywords=["Test"],
            categories=["Test"],
            hard_skills=["Test"],
            soft_skills=["Test"],
            metrics=[],
            pain_points_addressed=["Test"],
            outcome_types=["cost_reduction"],
            target_roles=["Test"],
            metadata={},
            embedding=None
        )
        issues = validate_star_record(star)
        assert "Missing quantified metrics" in issues

    def test_validate_missing_pain_points(self):
        """Test validation catches missing pain points."""
        star = STARRecord(
            id="test-123",
            company="Test",
            role_title="Test Role",
            period="2020-2021",
            domain_areas=["Test"],
            background_context="Test",
            situation="Test",
            tasks=["Test"],
            actions=["Test"],
            results=["Test"],
            impact_summary="Test",
            condensed_version="Test",
            ats_keywords=["Test"],
            categories=["Test"],
            hard_skills=["Test"],
            soft_skills=["Test"],
            metrics=["Test"],
            pain_points_addressed=[],
            outcome_types=["cost_reduction"],
            target_roles=["Test"],
            metadata={},
            embedding=None
        )
        issues = validate_star_record(star)
        assert "Missing pain points addressed" in issues


class TestSTARSchema:
    """Test that STARRecord schema is correctly defined."""

    def test_star_record_fields(self, parsed_stars: List[STARRecord]):
        """Test that all expected fields exist in parsed records."""
        expected_fields = [
            'id', 'company', 'role_title', 'period', 'domain_areas',
            'background_context', 'situation', 'tasks', 'actions', 'results',
            'impact_summary', 'condensed_version', 'ats_keywords', 'categories',
            'hard_skills', 'soft_skills', 'metrics', 'pain_points_addressed',
            'outcome_types', 'target_roles', 'metadata', 'embedding'
        ]

        star = parsed_stars[0]
        for field in expected_fields:
            assert field in star, f"Field '{field}' not in STARRecord"

    def test_list_fields_are_lists(self, parsed_stars: List[STARRecord]):
        """Test that list fields are actually lists."""
        list_fields = [
            'domain_areas', 'tasks', 'actions', 'results', 'ats_keywords',
            'categories', 'hard_skills', 'soft_skills', 'metrics',
            'pain_points_addressed', 'outcome_types', 'target_roles'
        ]

        star = parsed_stars[0]
        for field in list_fields:
            assert isinstance(star[field], list), f"Field '{field}' should be a list"

    def test_string_fields_are_strings(self, parsed_stars: List[STARRecord]):
        """Test that string fields are actually strings."""
        string_fields = [
            'id', 'company', 'role_title', 'period', 'background_context',
            'situation', 'impact_summary', 'condensed_version'
        ]

        star = parsed_stars[0]
        for field in string_fields:
            assert isinstance(star[field], str), f"Field '{field}' should be a string"

    def test_metadata_is_dict(self, parsed_stars: List[STARRecord]):
        """Test that metadata field is a dict."""
        star = parsed_stars[0]
        assert isinstance(star['metadata'], dict)

    def test_embedding_is_optional_list(self, parsed_stars: List[STARRecord]):
        """Test that embedding field is optional list of floats."""
        star = parsed_stars[0]
        assert star['embedding'] is None or isinstance(star['embedding'], list)


class TestSTARLibraryStatistics:
    """Test overall library statistics and quality."""

    def test_average_pain_points_per_star(self, parsed_stars: List[STARRecord]):
        """Test that average pain points per STAR is reasonable (1-3)."""
        total = sum(len(s['pain_points_addressed']) for s in parsed_stars)
        avg = total / len(parsed_stars)
        assert 1.0 <= avg <= 3.5, f"Average pain points ({avg}) outside reasonable range"

    def test_outcome_type_distribution(self, parsed_stars: List[STARRecord]):
        """Test that outcome types are distributed across multiple categories."""
        outcome_counts = {}
        for star in parsed_stars:
            for ot in star['outcome_types']:
                outcome_counts[ot] = outcome_counts.get(ot, 0) + 1

        # Should have at least 5 different outcome types across all STARs
        assert len(outcome_counts) >= 5, "Too few outcome type categories used"

    def test_companies_represented(self, parsed_stars: List[STARRecord]):
        """Test that STARs represent multiple companies."""
        companies = {s['company'] for s in parsed_stars}
        assert len(companies) >= 3, "STARs should represent multiple companies"

    def test_domain_coverage(self, parsed_stars: List[STARRecord]):
        """Test that STARs cover multiple domain areas."""
        all_domains = set()
        for star in parsed_stars:
            all_domains.update(star['domain_areas'])

        assert len(all_domains) >= 5, "STARs should cover multiple domain areas"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
