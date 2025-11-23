"""
Unit tests for src/common/utils.py
"""

import pytest
from src.common.utils import sanitize_path_component


class TestSanitizePathComponent:
    """Tests for the sanitize_path_component utility function."""

    def test_replaces_forward_slash(self):
        """Should replace forward slashes with underscores."""
        result = sanitize_path_component("Technology Strategy/Enterprise Architect")
        assert "/" not in result
        assert result == "Technology_Strategy_Enterprise_Architect"

    def test_replaces_backslash(self):
        """Should replace backslashes with underscores."""
        result = sanitize_path_component("Some\\Path\\Here")
        assert "\\" not in result
        assert result == "Some_Path_Here"

    def test_replaces_spaces(self):
        """Should replace spaces with underscores."""
        result = sanitize_path_component("Senior Software Engineer")
        assert " " not in result
        assert result == "Senior_Software_Engineer"

    def test_removes_commas(self):
        """Should remove commas entirely."""
        result = sanitize_path_component("Engineer, Senior")
        assert "," not in result
        assert result == "Engineer_Senior"

    def test_removes_dots(self):
        """Should remove dots entirely."""
        result = sanitize_path_component("Sr. Engineer")
        assert "." not in result
        assert result == "Sr_Engineer"

    def test_truncates_to_max_length(self):
        """Should truncate to max_length."""
        long_title = "A" * 100
        result = sanitize_path_component(long_title, max_length=80)
        assert len(result) == 80

    def test_custom_max_length(self):
        """Should respect custom max_length."""
        long_title = "A" * 100
        result = sanitize_path_component(long_title, max_length=50)
        assert len(result) == 50

    def test_returns_unknown_for_empty_string(self):
        """Should return 'unknown' for empty strings."""
        result = sanitize_path_component("")
        assert result == "unknown"

    def test_returns_unknown_after_sanitization_if_empty(self):
        """Should return 'unknown' if sanitization results in empty string."""
        result = sanitize_path_component("...,,,")
        assert result == "unknown"

    def test_real_job_title_consistency(self):
        """
        Ensure the exact job title that caused the bug now produces consistent output.
        This is the regression test for the duplicate folder issue.
        """
        title = "Technology Strategy/Enterprise Architect Consultant"

        # Both Layer 6 and Layer 7 should produce identical output
        result = sanitize_path_component(title, max_length=80)

        # Should NOT be truncated (51 chars < 80)
        assert result == "Technology_Strategy_Enterprise_Architect_Consultant"
        assert len(result) == 51

        # Should NOT match the buggy truncated version (50 chars)
        assert result != "Technology_Strategy_Enterprise_Architect_Consultan"
