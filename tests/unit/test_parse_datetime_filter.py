"""
Unit tests for parse_datetime_filter helper function.

Tests the module-level date parsing function used by:
- job_rows_partial() for job filtering
- get_locations() for location filtering by date
"""

import pytest
from datetime import datetime


# Import the function from frontend app
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from frontend.app import parse_datetime_filter


class TestParseDatetimeFilterBasic:
    """Test basic parsing functionality."""

    def test_parses_full_iso_datetime_with_z(self):
        """Parse ISO datetime with Z suffix."""
        result = parse_datetime_filter("2025-12-12T14:30:00.000Z")
        assert result == datetime(2025, 12, 12, 14, 30, 0, 0)

    def test_parses_full_iso_datetime_with_milliseconds(self):
        """Parse ISO datetime with milliseconds."""
        result = parse_datetime_filter("2025-11-30T14:30:00.709Z")
        assert result == datetime(2025, 11, 30, 14, 30, 0, 709000)

    def test_parses_iso_datetime_without_milliseconds(self):
        """Parse ISO datetime without milliseconds."""
        result = parse_datetime_filter("2025-12-12T10:00:00")
        assert result == datetime(2025, 12, 12, 10, 0, 0)

    def test_parses_iso_datetime_short_form(self):
        """Parse ISO datetime in short form (no seconds)."""
        result = parse_datetime_filter("2025-12-12T10:00")
        assert result == datetime(2025, 12, 12, 10, 0, 0)

    def test_parses_date_only_start_of_day(self):
        """Parse date-only string as start of day."""
        result = parse_datetime_filter("2025-12-12", is_end_of_day=False)
        assert result == datetime(2025, 12, 12, 0, 0, 0)

    def test_parses_date_only_end_of_day(self):
        """Parse date-only string as end of day."""
        result = parse_datetime_filter("2025-12-12", is_end_of_day=True)
        assert result == datetime(2025, 12, 12, 23, 59, 59, 999999)


class TestParseDatetimeFilterEdgeCases:
    """Test edge cases and error handling."""

    def test_returns_none_for_empty_string(self):
        """Return None for empty string input."""
        result = parse_datetime_filter("")
        assert result is None

    def test_returns_none_for_whitespace_only(self):
        """Return None for whitespace-only input."""
        result = parse_datetime_filter("   ")
        assert result is None

    def test_returns_none_for_none_input(self):
        """Return None for None input."""
        result = parse_datetime_filter(None)
        assert result is None

    def test_returns_none_for_invalid_format(self):
        """Return None for invalid date format."""
        result = parse_datetime_filter("not-a-date")
        assert result is None

    def test_returns_none_for_invalid_date_values(self):
        """Return None for invalid date values (e.g., month 13)."""
        result = parse_datetime_filter("2025-13-45")
        assert result is None

    def test_handles_timezone_offset(self):
        """Handle +00:00 timezone offset."""
        result = parse_datetime_filter("2025-12-12T14:30:00+00:00")
        assert result == datetime(2025, 12, 12, 14, 30, 0)

    def test_handles_various_millisecond_lengths(self):
        """Handle different millisecond precision."""
        # 3 digits
        result1 = parse_datetime_filter("2025-12-12T14:30:00.123Z")
        assert result1.microsecond == 123000

        # 6 digits
        result2 = parse_datetime_filter("2025-12-12T14:30:00.123456Z")
        assert result2.microsecond == 123456

        # 1 digit
        result3 = parse_datetime_filter("2025-12-12T14:30:00.1Z")
        assert result3.microsecond == 100000


class TestParseDatetimeFilterIsEndOfDay:
    """Test is_end_of_day parameter behavior."""

    def test_is_end_of_day_only_affects_date_only_input(self):
        """is_end_of_day parameter only affects date-only inputs."""
        # Full datetime: is_end_of_day should have no effect
        result_with_flag = parse_datetime_filter("2025-12-12T10:00:00", is_end_of_day=True)
        result_without_flag = parse_datetime_filter("2025-12-12T10:00:00", is_end_of_day=False)
        assert result_with_flag == result_without_flag

    def test_date_only_default_is_start_of_day(self):
        """Date-only defaults to start of day (00:00:00)."""
        result = parse_datetime_filter("2025-12-12")
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0

    def test_date_only_with_end_of_day_flag(self):
        """Date-only with is_end_of_day=True uses 23:59:59.999999."""
        result = parse_datetime_filter("2025-12-12", is_end_of_day=True)
        assert result.hour == 23
        assert result.minute == 59
        assert result.second == 59
        assert result.microsecond == 999999
