"""
Unit tests for MENA region detection utility.

Tests the deterministic region detection logic without making
any external API calls.
"""

import pytest

from src.common.mena_detector import (
    MenaContext,
    detect_mena_region,
    format_mena_greeting,
    format_mena_closing,
    get_vision_reference,
)


class TestDetectMenaRegion:
    """Tests for detect_mena_region function."""

    # ===== COUNTRY DETECTION TESTS =====

    def test_detect_saudi_arabia_by_country_name(self):
        """Detect Saudi Arabia from explicit country name."""
        context = detect_mena_region(location="Riyadh, Saudi Arabia")

        assert context.is_mena is True
        assert context.region == "Saudi Arabia"
        assert context.confidence == "high"
        assert context.use_arabic_greeting is True
        assert context.formality_level == "high"
        assert "Vision 2030" in context.vision_references

    def test_detect_saudi_arabia_by_ksa(self):
        """Detect Saudi Arabia from KSA abbreviation."""
        context = detect_mena_region(location="Jeddah, KSA")

        assert context.is_mena is True
        assert context.region == "Saudi Arabia"
        assert context.confidence == "high"

    def test_detect_uae_by_country_name(self):
        """Detect UAE from country name."""
        context = detect_mena_region(location="Dubai, UAE")

        assert context.is_mena is True
        assert context.region == "UAE"
        assert context.confidence == "high"
        assert context.use_arabic_greeting is False  # Only Saudi gets Arabic greeting
        assert context.formality_level == "high"

    def test_detect_qatar(self):
        """Detect Qatar from country name."""
        context = detect_mena_region(location="Doha, Qatar")

        assert context.is_mena is True
        assert context.region == "Qatar"
        assert context.confidence == "high"

    def test_detect_kuwait(self):
        """Detect Kuwait from country name."""
        context = detect_mena_region(location="Kuwait City, Kuwait")

        assert context.is_mena is True
        assert context.region == "Kuwait"

    # ===== CITY DETECTION TESTS =====

    def test_detect_riyadh_city(self):
        """Detect Saudi Arabia from Riyadh city alone."""
        context = detect_mena_region(location="Riyadh")

        assert context.is_mena is True
        assert context.region == "Saudi Arabia"
        assert context.confidence == "high"

    def test_detect_dubai_city(self):
        """Detect UAE from Dubai city alone."""
        context = detect_mena_region(location="Dubai")

        assert context.is_mena is True
        assert context.region == "UAE"
        assert context.confidence == "high"

    def test_detect_doha_city(self):
        """Detect Qatar from Doha city alone."""
        context = detect_mena_region(location="Doha")

        assert context.is_mena is True
        assert context.region == "Qatar"

    def test_detect_cairo_city(self):
        """Detect Egypt from Cairo city."""
        context = detect_mena_region(location="Cairo")

        assert context.is_mena is True
        assert context.region == "Egypt"
        assert context.formality_level == "standard"  # Non-GCC

    # ===== COMPANY DETECTION TESTS =====

    def test_detect_neom_company(self):
        """Detect Saudi Arabia from NEOM company."""
        context = detect_mena_region(company="NEOM")

        assert context.is_mena is True
        assert context.region == "Saudi Arabia"
        assert context.confidence == "medium"
        assert "Vision 2030" in context.vision_references
        assert "digital transformation" in context.vision_references

    def test_detect_aramco_company(self):
        """Detect Saudi Arabia from Aramco company."""
        context = detect_mena_region(company="Saudi Aramco")

        assert context.is_mena is True
        assert context.region == "Saudi Arabia"
        assert "energy transformation" in context.vision_references

    def test_detect_sabic_company(self):
        """Detect Saudi Arabia from SABIC company."""
        context = detect_mena_region(company="SABIC")

        assert context.is_mena is True
        assert context.region == "Saudi Arabia"

    def test_detect_misk_foundation(self):
        """Detect Saudi Arabia from Misk Foundation."""
        context = detect_mena_region(company="Misk Foundation")

        assert context.is_mena is True
        assert context.region == "Saudi Arabia"
        assert "Vision 2030" in context.vision_references

    def test_detect_etisalat_company(self):
        """Detect UAE from Etisalat company."""
        context = detect_mena_region(company="Etisalat")

        assert context.is_mena is True
        assert context.region == "UAE"

    # ===== JD TEXT DETECTION TESTS =====

    def test_detect_vision_2030_keyword(self):
        """Detect Saudi Arabia from Vision 2030 in JD text."""
        context = detect_mena_region(
            jd_text="Join us in building the future. This role supports Vision 2030 initiatives."
        )

        assert context.is_mena is True
        assert context.region == "Saudi Arabia"
        assert context.confidence == "low"  # Keywords alone are low confidence

    def test_detect_gcc_keyword(self):
        """Detect GCC region from GCC keyword."""
        context = detect_mena_region(
            jd_text="We are looking for candidates with GCC experience."
        )

        assert context.is_mena is True
        assert context.region == "GCC Region"
        assert context.confidence == "low"

    # ===== COMBINED DETECTION TESTS =====

    def test_location_overrides_company(self):
        """Location detection takes precedence and is high confidence."""
        context = detect_mena_region(
            location="Riyadh, Saudi Arabia",
            company="Unknown Tech Corp"
        )

        assert context.is_mena is True
        assert context.region == "Saudi Arabia"
        assert context.confidence == "high"

    def test_company_adds_vision_refs(self):
        """Company detection adds vision references even with location."""
        context = detect_mena_region(
            location="Riyadh",
            company="NEOM"
        )

        assert context.is_mena is True
        assert context.region == "Saudi Arabia"
        assert "Vision 2030" in context.vision_references
        assert "digital transformation" in context.vision_references

    # ===== NON-MENA TESTS =====

    def test_non_mena_us_location(self):
        """Non-MENA location returns default context."""
        context = detect_mena_region(location="San Francisco, CA, USA")

        assert context.is_mena is False
        assert context.region is None
        assert context.confidence == "none"
        assert context.use_arabic_greeting is False
        assert context.formality_level == "standard"
        assert context.timeline_multiplier == 1.0

    def test_non_mena_uk_location(self):
        """Non-MENA UK location returns default context."""
        context = detect_mena_region(location="London, UK")

        assert context.is_mena is False
        assert context.region is None

    def test_non_mena_company(self):
        """Non-MENA company returns default context."""
        context = detect_mena_region(company="Google")

        assert context.is_mena is False
        assert context.region is None

    def test_empty_inputs(self):
        """Empty inputs return default context."""
        context = detect_mena_region()

        assert context.is_mena is False
        assert context.region is None
        assert context.confidence == "none"

    def test_none_inputs(self):
        """None inputs return default context."""
        context = detect_mena_region(location=None, company=None, jd_text=None)

        assert context.is_mena is False
        assert context.region is None


class TestMenaContextProperties:
    """Tests for MenaContext dataclass properties."""

    def test_gcc_countries_have_high_formality(self):
        """All GCC countries should have high formality."""
        gcc_countries = ["Saudi Arabia", "UAE", "Qatar", "Kuwait", "Oman", "Bahrain"]
        for country in gcc_countries:
            context = detect_mena_region(location=country)
            assert context.formality_level == "high", f"{country} should have high formality"

    def test_gcc_countries_have_timeline_multiplier(self):
        """All GCC countries should have 1.5x timeline multiplier."""
        gcc_countries = ["Saudi Arabia", "UAE", "Qatar", "Kuwait", "Oman", "Bahrain"]
        for country in gcc_countries:
            context = detect_mena_region(location=country)
            assert context.timeline_multiplier == 1.5, f"{country} should have 1.5x timeline"

    def test_only_saudi_has_arabic_greeting(self):
        """Only Saudi Arabia should have Arabic greeting enabled."""
        context_saudi = detect_mena_region(location="Saudi Arabia")
        context_uae = detect_mena_region(location="UAE")

        assert context_saudi.use_arabic_greeting is True
        assert context_uae.use_arabic_greeting is False

    def test_mena_context_to_dict(self):
        """MenaContext should serialize to dictionary."""
        context = detect_mena_region(location="Riyadh, Saudi Arabia")
        result = context.to_dict()

        assert isinstance(result, dict)
        assert result["is_mena"] is True
        assert result["region"] == "Saudi Arabia"
        assert "Vision 2030" in result["vision_references"]


class TestFormatMenaGreeting:
    """Tests for format_mena_greeting function."""

    def test_saudi_greeting_with_arabic(self):
        """Saudi context should include Arabic greeting."""
        context = detect_mena_region(location="Saudi Arabia")
        greeting = format_mena_greeting("Ahmed", context, "Mr.")

        assert "As-salaam Alaykum" in greeting
        assert "Dear Mr. Ahmed" in greeting

    def test_uae_greeting_formal(self):
        """UAE context should be formal but not Arabic."""
        context = detect_mena_region(location="UAE")
        greeting = format_mena_greeting("Mohammed", context, "Dr.")

        assert "As-salaam Alaykum" not in greeting
        assert "Dear Dr. Mohammed" in greeting

    def test_non_mena_greeting_standard(self):
        """Non-MENA context should use standard greeting."""
        context = detect_mena_region(location="USA")
        greeting = format_mena_greeting("John", context, "Mr.")

        assert greeting == "Dear Mr. John,"

    def test_greeting_without_title(self):
        """Greeting without title should still work."""
        context = detect_mena_region(location="Saudi Arabia")
        greeting = format_mena_greeting("Ahmed", context)

        assert "Dear Ahmed" in greeting


class TestFormatMenaClosing:
    """Tests for format_mena_closing function."""

    def test_saudi_closing_with_shukran(self):
        """Saudi context should include Shukran."""
        context = detect_mena_region(location="Saudi Arabia")
        closing = format_mena_closing(context)

        assert "Shukran" in closing
        assert "Best regards" in closing

    def test_uae_closing_formal(self):
        """UAE context should be formal but not Arabic."""
        context = detect_mena_region(location="UAE")
        closing = format_mena_closing(context)

        assert "Shukran" not in closing
        assert "Thank you" in closing

    def test_non_mena_closing_brief(self):
        """Non-MENA context should use brief closing."""
        context = detect_mena_region(location="USA")
        closing = format_mena_closing(context)

        assert closing == "Best regards,"


class TestGetVisionReference:
    """Tests for get_vision_reference function."""

    def test_saudi_returns_vision_2030(self):
        """Saudi context should return Vision 2030."""
        context = detect_mena_region(location="Saudi Arabia")
        reference = get_vision_reference(context)

        assert reference == "Vision 2030"

    def test_neom_returns_vision_2030(self):
        """NEOM company should return Vision 2030."""
        context = detect_mena_region(company="NEOM")
        reference = get_vision_reference(context)

        assert reference == "Vision 2030"

    def test_non_mena_returns_none(self):
        """Non-MENA context should return None."""
        context = detect_mena_region(location="USA")
        reference = get_vision_reference(context)

        assert reference is None


class TestSuggestedAdaptations:
    """Tests for suggested_adaptations in MenaContext."""

    def test_saudi_has_vision_2030_adaptation(self):
        """Saudi context should suggest Vision 2030 reference."""
        context = detect_mena_region(location="Saudi Arabia")

        adaptations_text = " ".join(context.suggested_adaptations)
        assert "Vision 2030" in adaptations_text

    def test_saudi_has_email_structure_adaptation(self):
        """Saudi context should suggest Saudi email structure."""
        context = detect_mena_region(location="Saudi Arabia")

        adaptations_text = " ".join(context.suggested_adaptations)
        assert "email structure" in adaptations_text.lower() or "Saudi" in adaptations_text

    def test_gcc_has_formal_greeting_adaptation(self):
        """GCC context should suggest formal greeting."""
        context = detect_mena_region(location="UAE")

        adaptations_text = " ".join(context.suggested_adaptations)
        assert "formal" in adaptations_text.lower() or "Dear" in adaptations_text

    def test_non_mena_has_no_adaptations(self):
        """Non-MENA context should have no suggested adaptations."""
        context = detect_mena_region(location="USA")

        assert len(context.suggested_adaptations) == 0
