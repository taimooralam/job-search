"""
Unit tests for should_include_github conditional logic.

Tests the hybrid logic that determines whether to include GitHub
in the CV header based on job title and JD content analysis.
"""

import pytest
from src.layer6_v2.orchestrator import should_include_github


class TestShouldIncludeGithub:
    """Tests for should_include_github function."""

    def test_technical_titles_include_github(self):
        """Technical titles should always include GitHub."""
        technical_titles = [
            "Senior Software Engineer",
            "Backend Developer",
            "Solutions Architect",
            "SRE Engineer",
            "Data Scientist",
            "Machine Learning Engineer",
            "Platform Engineer",
            "DevOps Engineer",
            "Full Stack Developer",
            "Staff Engineer",
            "Principal Engineer",
        ]
        for title in technical_titles:
            assert should_include_github(title) is True, f"Expected True for '{title}'"

    def test_non_technical_titles_exclude_github(self):
        """Non-technical titles should exclude GitHub."""
        non_technical_titles = [
            "Product Manager",
            "HR Director",
            "Marketing Manager",
            "Sales Director",
            "Operations Manager",
            "Finance Manager",
        ]
        for title in non_technical_titles:
            assert should_include_github(title) is False, f"Expected False for '{title}'"

    def test_ambiguous_titles_without_jd_exclude_github(self):
        """Ambiguous titles without JD should exclude GitHub."""
        ambiguous_titles = [
            "Engineering Manager",
            "Director of Engineering",
            "Head of Engineering",
            "VP Engineering",
            "CTO",
            "Technical Program Manager",
        ]
        for title in ambiguous_titles:
            assert should_include_github(title) is False, f"Expected False for '{title}' without JD"

    def test_ambiguous_titles_with_technical_signals_include_github(self):
        """Ambiguous titles with technical JD signals should include GitHub."""
        test_cases = [
            ("Engineering Manager", "hands-on coding"),
            ("Director of Engineering", "code review experience required"),
            ("Head of Engineering", "pull request reviews"),
            ("VP Engineering", "architecture review sessions"),
            ("CTO", "still code occasionally"),
            ("Technical Program Manager", "system design discussions"),
        ]
        for title, jd in test_cases:
            assert should_include_github(title, jd) is True, f"Expected True for '{title}' with '{jd}'"

    def test_ambiguous_titles_with_non_technical_jd_exclude_github(self):
        """Ambiguous titles with non-technical JD should exclude GitHub."""
        test_cases = [
            ("Engineering Manager", "People management and team building"),
            ("Director of Engineering", "Strategic planning and budget management"),
            ("CTO", "Board presentations and investor relations"),
        ]
        for title, jd in test_cases:
            assert should_include_github(title, jd) is False, f"Expected False for '{title}' with '{jd}'"

    def test_case_insensitivity(self):
        """Title matching should be case-insensitive."""
        assert should_include_github("SENIOR SOFTWARE ENGINEER") is True
        assert should_include_github("senior software engineer") is True
        assert should_include_github("Senior Software ENGINEER") is True

    def test_partial_matches(self):
        """Should handle partial matches correctly."""
        # "engineer" should match in "Software Engineer"
        assert should_include_github("Software Engineer") is True
        # "architect" should match
        assert should_include_github("Cloud Architect") is True

    def test_jd_signal_detection(self):
        """Should detect technical signals in JD content."""
        technical_jds = [
            "The role requires hands-on development experience",
            "You'll participate in code review sessions",
            "Contribute to open source projects",
            "Deep technical expertise in system design",
            "You should still write code 20% of the time",
        ]
        for jd in technical_jds:
            assert should_include_github("Engineering Manager", jd) is True, f"Expected True with JD: '{jd}'"
