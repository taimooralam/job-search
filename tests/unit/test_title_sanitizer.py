"""Tests for the title sanitizer regex pass."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.layer6_v2.title_sanitizer import sanitize_job_title, sanitize_job_title_llm


@pytest.mark.parametrize(
    "raw_title, expected",
    [
        # Gender markers
        ("AI Architect (m/w/d)", "AI Architect"),
        ("Senior Engineer (f/m/x)", "Senior Engineer"),
        ("Tech Lead (alle Geschlechter)", "Tech Lead"),
        # Language with "with/mit"
        ("AI Architect with French", "AI Architect"),
        ("Engineering Manager mit Deutsch", "Engineering Manager"),
        ("Data Scientist with fluent German", "Data Scientist"),
        # Location after dash
        ("Principal Engineer - Schweiz", "Principal Engineer"),
        ("AI Architect - Berlin", "AI Architect"),
        ("CTO \u2013 DACH", "CTO"),
        # Work-mode/contract tags
        ("AI Engineer (Remote)", "AI Engineer"),
        ("Backend Developer (Hybrid)", "Backend Developer"),
        ("Platform Engineer (Contract)", "Platform Engineer"),
        # Trailing country codes
        ("AI Architect, DE", "AI Architect"),
        ("Senior Engineer, CH", "Senior Engineer"),
        # Combo: multiple patterns
        ("AI Architect with French (m/w/d) - Schweiz", "AI Architect"),
        ("Senior Engineer (f/m/x) (Remote), DE", "Senior Engineer"),
        # No-op: already clean titles
        ("Principal Generative AI Engineer", "Principal Generative AI Engineer"),
        ("Engineering Manager", "Engineering Manager"),
        ("Staff Software Engineer", "Staff Software Engineer"),
        # Edge: empty/whitespace
        ("", ""),
        ("  ", ""),
    ],
)
def test_sanitize_job_title_regex(raw_title: str, expected: str):
    """Test regex-based title sanitization with parametrized cases."""
    result = sanitize_job_title(raw_title)
    assert result == expected, f"Expected '{expected}', got '{result}' for input '{raw_title}'"


@pytest.mark.asyncio(loop_scope="function")
async def test_sanitize_job_title_llm_substring_validation():
    """Test that LLM result is discarded if not a substring of original."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.content = "AI Systems Architect"  # Not a substring of original

    with patch("src.common.unified_llm.UnifiedLLM") as MockLLM:
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        MockLLM.return_value = mock_llm_instance

        result = await sanitize_job_title_llm(
            "AI Architect with French",
            "AI Architect",  # regex result
        )
        # Should fall back to regex result since LLM output is not a substring
        assert result == "AI Architect"


@pytest.mark.asyncio(loop_scope="function")
async def test_sanitize_job_title_llm_valid_substring():
    """Test that LLM result is accepted when it's a valid substring."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.content = "AI Architect"  # Valid substring

    with patch("src.common.unified_llm.UnifiedLLM") as MockLLM:
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        MockLLM.return_value = mock_llm_instance

        result = await sanitize_job_title_llm(
            "AI Architect with French",
            "AI Architect",
        )
        assert result == "AI Architect"


@pytest.mark.asyncio(loop_scope="function")
async def test_sanitize_job_title_llm_failure_fallback():
    """Test that LLM failure falls back to regex result."""
    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error = "API error"
    mock_result.content = None

    with patch("src.common.unified_llm.UnifiedLLM") as MockLLM:
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        MockLLM.return_value = mock_llm_instance

        result = await sanitize_job_title_llm(
            "AI Architect with French",
            "AI Architect",
        )
        assert result == "AI Architect"
