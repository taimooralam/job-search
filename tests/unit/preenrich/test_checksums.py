"""
T3 — Checksum utilities.

Validates:
- normalize_jd is deterministic and whitespace-stable
- jd_checksum produces consistent results across minor formatting variants
- company_checksum is case-insensitive and whitespace-tolerant
"""

import pytest

from src.preenrich.checksums import normalize_jd, jd_checksum, company_checksum


# ---------------------------------------------------------------------------
# normalize_jd
# ---------------------------------------------------------------------------


def test_normalize_jd_deterministic():
    """Same input always produces same output."""
    text = "We are looking for an AI Engineer with 5+ years experience."
    assert normalize_jd(text) == normalize_jd(text)


def test_normalize_jd_strips_leading_trailing_whitespace():
    """Leading/trailing whitespace is stripped."""
    assert normalize_jd("  hello world  ") == "hello world"


def test_normalize_jd_collapses_internal_whitespace():
    """Multiple consecutive spaces are collapsed to one."""
    assert normalize_jd("hello   world") == "hello world"


def test_normalize_jd_collapses_newlines():
    """Newlines and tabs are collapsed to single spaces."""
    assert normalize_jd("hello\n\nworld\ttab") == "hello world tab"


def test_normalize_jd_lowercases():
    """Text is lowercased so casing variants are identical."""
    assert normalize_jd("AI Engineer") == "ai engineer"


def test_normalize_jd_empty_string():
    """Empty string returns empty string."""
    assert normalize_jd("") == ""


def test_normalize_jd_stable_across_minor_formatting():
    """Two JDs that differ only in formatting produce the same normalized form."""
    jd1 = "  We are  hiring an AI Engineer.  "
    jd2 = "we are hiring an ai engineer."
    assert normalize_jd(jd1) == normalize_jd(jd2)


# ---------------------------------------------------------------------------
# jd_checksum
# ---------------------------------------------------------------------------


def test_jd_checksum_stable():
    """Same text always produces same checksum."""
    cs1 = jd_checksum("Looking for ML Engineer")
    cs2 = jd_checksum("Looking for ML Engineer")
    assert cs1 == cs2


def test_jd_checksum_prefixed():
    """Checksum is prefixed with 'sha256:'."""
    cs = jd_checksum("hello")
    assert cs.startswith("sha256:")


def test_jd_checksum_64_char_hex():
    """Checksum suffix is 64 hex characters."""
    cs = jd_checksum("hello")
    hex_part = cs[len("sha256:"):]
    assert len(hex_part) == 64
    assert all(c in "0123456789abcdef" for c in hex_part)


def test_jd_checksum_whitespace_stable():
    """Minor whitespace changes do not alter the checksum."""
    cs1 = jd_checksum("We are hiring   ML engineers.")
    cs2 = jd_checksum("We are hiring ML engineers.")
    assert cs1 == cs2


def test_jd_checksum_case_stable():
    """Case differences do not alter the checksum."""
    cs1 = jd_checksum("AI Engineer")
    cs2 = jd_checksum("ai engineer")
    assert cs1 == cs2


def test_jd_checksum_different_text_differs():
    """Different text produces different checksums."""
    cs1 = jd_checksum("Job A")
    cs2 = jd_checksum("Job B")
    assert cs1 != cs2


def test_jd_checksum_empty():
    """Empty text produces a valid checksum (not None)."""
    cs = jd_checksum("")
    assert cs.startswith("sha256:")


# ---------------------------------------------------------------------------
# company_checksum
# ---------------------------------------------------------------------------


def test_company_checksum_deterministic():
    """Same inputs produce same checksum."""
    cs1 = company_checksum("Anthropic", "anthropic.com")
    cs2 = company_checksum("Anthropic", "anthropic.com")
    assert cs1 == cs2


def test_company_checksum_case_insensitive():
    """Case differences in name or domain produce same checksum."""
    cs1 = company_checksum("OpenAI", "openai.com")
    cs2 = company_checksum("openai", "OPENAI.COM")
    assert cs1 == cs2


def test_company_checksum_name_whitespace_tolerant():
    """Leading/trailing whitespace in name is ignored."""
    cs1 = company_checksum("  Anthropic  ", "anthropic.com")
    cs2 = company_checksum("Anthropic", "anthropic.com")
    assert cs1 == cs2


def test_company_checksum_none_domain():
    """None domain is treated the same as empty string."""
    cs1 = company_checksum("Anthropic", None)
    cs2 = company_checksum("Anthropic", "")
    assert cs1 == cs2


def test_company_checksum_different_names_differ():
    """Different company names produce different checksums."""
    cs1 = company_checksum("Anthropic", "anthropic.com")
    cs2 = company_checksum("OpenAI", "anthropic.com")
    assert cs1 != cs2


def test_company_checksum_prefixed():
    """Checksum is prefixed with 'sha256:'."""
    cs = company_checksum("TestCo", "test.com")
    assert cs.startswith("sha256:")
