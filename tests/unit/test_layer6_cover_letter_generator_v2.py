"""
Unit tests for Layer 6a Cover Letter Generator V2 prompt improvements.

Tests new validation rules:
- Cover letter must reference ≥2 pain points semantically
- Must cite company name + metric in same sentence
- Must reference company signal by type (funding/launch/etc)
- Zero generic phrases allowed (down from 2)
- Planning phase improves structure

These tests follow TDD approach and should FAIL initially until
prompt improvements are implemented.
"""

import re

# Import test utilities
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fixtures.sample_jobs import SAMPLE_STARS, create_mock_state_for_job
from helpers.validation_helpers import (
    count_pain_point_references,
    extract_sentences_with_keyword,
    validate_cover_letter_v2,
)

# Import module under test

# ===== FIXTURES =====

@pytest.fixture
def sample_state_tech_saas():
    """Sample state for tech SaaS backend engineer role."""
    return create_mock_state_for_job(
        "tech_saas_backend_engineer",
        selected_stars=[SAMPLE_STARS[0], SAMPLE_STARS[2]],  # Platform migration + microservices
        company_research={
            "signals": [
                {"type": "funding", "description": "Series B funded, growing 300% YoY", "source": "job description"}
            ]
        }
    )

@pytest.fixture
def sample_state_healthcare():
    """Sample state for healthcare platform engineer role."""
    return create_mock_state_for_job(
        "healthcare_platform_engineer",
        selected_stars=[SAMPLE_STARS[1], SAMPLE_STARS[2]],  # SRE practices + CI/CD
        company_research={
            "signals": [
                {"type": "growth", "description": "Series A funded, 50+ hospital partners", "source": "job description"}
            ]
        }
    )

@pytest.fixture
def mock_llm_providers(mocker):
    """Mock all LLM providers to prevent real API calls."""
    # Mock OpenAI
    mock_openai = mocker.patch("langchain_openai.ChatOpenAI")
    mock_instance = MagicMock()
    mock_openai.return_value = mock_instance

    # Mock invoke response with structured output
    from langchain_core.messages import AIMessage
    mock_instance.invoke.return_value = AIMessage(
        content="""
Your Series B funding signals exciting growth—and also critical challenges: API platform performance and microservices migration. At Seven.One Entertainment Group, I led a similar transformation, building event-driven microservices architecture handling 10M requests daily with 99.9% uptime.

I reduced AWS infrastructure costs by 75% ($3M annually) while improving deployment frequency 300% through CI/CD automation. At DataCorp, I led monolith-to-microservices migration reducing deployment time from 4 hours to 15 minutes (16x improvement)—directly addressing your feature velocity bottleneck.

Your roadmap requires both scalability and velocity. My track record demonstrates I can deliver both simultaneously, critical as you scale post-funding. I have applied for this role. Let's discuss how my experience maps to your specific challenges: https://calendly.com/taimooralam/15min
        """.strip()
    )

    return {"openai": mock_openai}

# ===== TESTS: Validation Helpers for Cover Letters =====

class TestCoverLetterValidationHelpers:
    """Test cover letter-specific validation helpers."""

    def test_extract_sentences_with_company_name(self):
        """Should extract sentences containing company name."""
        text = "At Seven.One Entertainment Group, I reduced costs by 75%. This improved platform reliability."

        sentences = extract_sentences_with_keyword(text, "Seven.One Entertainment Group")

        assert len(sentences) >= 1
        assert "Seven.One Entertainment Group" in sentences[0]
        assert "75%" in sentences[0]

    def test_detect_company_metric_cooccurrence(self):
        """Should detect when company and metric appear in same sentence."""
        text = "At Seven.One, I reduced AWS costs by 75% ($3M annually) through rightsizing."

        sentences = extract_sentences_with_keyword(text, "Seven.One")

        # Check if any sentence contains both company and metric
        has_metric = any(
            re.search(r'\d+%|\$\d+[KMB]?', sent)
            for sent in sentences
        )

        assert has_metric

    def test_count_pain_point_references_in_cover_letter(self, sample_state_tech_saas):
        """Should count pain points referenced in cover letter."""
        cover_letter = """
        Your API platform scalability challenges and monolithic architecture migration needs
        align perfectly with my experience. At Seven.One, I built microservices handling 10M
        requests daily, addressing similar traffic growth issues.
        """

        pain_points = sample_state_tech_saas["pain_points"]
        count = count_pain_point_references(cover_letter, pain_points)

        # Should match "API platform" and "monolithic architecture"
        assert count >= 2

# ===== TESTS: Cover Letter Validation V2 =====

class TestCoverLetterValidationV2:
    """Test V2 validation rules for cover letters."""

    def test_references_at_least_two_pain_points(self, sample_state_tech_saas):
        """Cover letter must reference ≥2 pain points semantically."""
        good_letter = """
Your Series B funding signals exciting growth—and critical challenges with API scalability
and monolithic architecture migration. At Seven.One Entertainment Group, I led similar
transformations building microservices handling 10M requests daily.

I reduced deployment time from 4 hours to 15 minutes (16x improvement) at DataCorp,
directly addressing feature velocity bottlenecks. This experience solving API performance
and deployment challenges positions me to tackle your platform modernization.

I have applied for this role. Let's discuss: https://calendly.com/taimooralam/15min
        """

        errors = validate_cover_letter_v2(good_letter, sample_state_tech_saas, min_pain_points=2)

        # Should pass - references "API scalability" and "monolithic architecture migration"
        pain_errors = [e for e in errors if "pain point" in e.lower()]
        assert len(pain_errors) == 0

    def test_fails_with_insufficient_pain_point_coverage(self, sample_state_tech_saas):
        """Cover letter with <2 pain points should fail."""
        bad_letter = """
I am excited to apply for this role at StreamCo. I have strong background in backend
engineering with proven track record delivering scalable systems.

My experience includes Python, Kubernetes, and microservices. I am a team player
with excellent problem-solving skills.

I have applied for this role. Let's discuss: https://calendly.com/taimooralam/15min
        """

        errors = validate_cover_letter_v2(bad_letter, sample_state_tech_saas, min_pain_points=2)

        # Should fail - generic content, no specific pain points
        assert any("pain point" in e.lower() for e in errors)

    def test_cites_company_and_metric_in_same_sentence(self, sample_state_tech_saas):
        """Must cite company name + metric in same sentence for grounding."""
        good_letter = """
Your API scalability challenges mirror those I solved at Seven.One Entertainment Group,
where I reduced infrastructure costs by 75% ($3M annually) while handling 10M daily requests.

At DataCorp, I improved deployment speed 16x (4 hours to 15 minutes), addressing the
monolith migration pain point you're experiencing.

I have applied for this role. Let's discuss: https://calendly.com/taimooralam/15min
        """

        errors = validate_cover_letter_v2(good_letter, sample_state_tech_saas)

        # Should pass - "Seven.One" + "75%" in same sentence
        cooccurrence_errors = [e for e in errors if "same sentence" in e.lower() or "metric" in e.lower()]
        assert len(cooccurrence_errors) == 0

    def test_fails_without_company_metric_cooccurrence(self, sample_state_tech_saas):
        """Cover letter without company+metric in same sentence should fail."""
        bad_letter = """
At Seven.One Entertainment Group, I led platform engineering initiatives. I reduced
infrastructure costs significantly and improved system performance across the board.

The metrics were impressive with cost reductions of 75% and deployment improvements.
This experience is relevant to your API scalability challenges.

I have applied for this role. Let's discuss: https://calendly.com/taimooralam/15min
        """

        errors = validate_cover_letter_v2(bad_letter, sample_state_tech_saas)

        # Should fail - company and metrics in different sentences
        assert any("same sentence" in e.lower() for e in errors)

    def test_references_company_signal_by_type(self, sample_state_tech_saas):
        """Must reference at least one company signal (funding/launch/etc)."""
        good_letter = """
Your Series B funding signals an exciting growth phase—and critical infrastructure challenges.
At Seven.One, I scaled platforms handling 10M requests daily with 99.9% uptime.

This growth trajectory requires both API scalability and deployment velocity, which I've
delivered through microservices architecture reducing costs 75% at Seven.One.

I have applied for this role. Let's discuss: https://calendly.com/taimooralam/15min
        """

        errors = validate_cover_letter_v2(good_letter, sample_state_tech_saas, require_company_signal=True)

        # Should pass - references "Series B funding" and "growth"
        signal_errors = [e for e in errors if "signal" in e.lower() or "company context" in e.lower()]
        assert len(signal_errors) == 0

    def test_fails_without_company_signal_reference(self, sample_state_tech_saas):
        """Cover letter without company signal reference should fail."""
        bad_letter = """
I am interested in the Senior Backend Engineer position at StreamCo. I have extensive
experience with microservices architecture and API development with strong background.

At Seven.One, I reduced costs by 75% while building scalable platforms. This experience
is relevant to your engineering challenges.

I have applied for this role. Let's discuss: https://calendly.com/taimooralam/15min
        """

        errors = validate_cover_letter_v2(bad_letter, sample_state_tech_saas, require_company_signal=True)

        # Should fail - no company signal referenced
        assert any("signal" in e.lower() or "company context" in e.lower() for e in errors)

    def test_zero_generic_phrases_allowed(self, sample_state_tech_saas):
        """V2 validation allows zero generic phrases (down from 2)."""
        generic_letter = """
I am excited to apply for this perfect fit role at StreamCo. I have strong background
and proven track record as a team player with excellent problem-solving skills.

My extensive experience and diverse background make me an ideal candidate. I am
confident that my solid foundation in backend engineering aligns well.

I have applied for this role. Let's discuss: https://calendly.com/taimooralam/15min
        """

        errors = validate_cover_letter_v2(generic_letter, sample_state_tech_saas, allow_generic_phrases=0)

        # Should fail - multiple generic phrases
        assert any("generic" in e.lower() for e in errors)

    def test_specific_cover_letter_passes_validation(self, sample_state_tech_saas):
        """Specific, well-grounded cover letter should pass all V2 gates."""
        excellent_letter = """
Your Series B funding signals exciting growth—and critical infrastructure challenges:
API scalability and microservices migration. At Seven.One Entertainment Group, I led
a team of 12 engineers building event-driven microservices handling 10M requests daily
with 99.9% uptime, reducing AWS costs by 75% ($3M annually).

At DataCorp, I addressed similar monolithic architecture bottlenecks, leading migration
that reduced deployment time from 4 hours to 15 minutes (16x improvement). This experience
solving API performance and deployment velocity challenges positions me to tackle your
platform modernization while maintaining reliability.

Your roadmap requires both scalability and speed. My track record demonstrates I can
deliver both simultaneously, critical as you scale post-funding. I have applied for
this role. Let's discuss how my experience maps to your specific challenges:
https://calendly.com/taimooralam/15min
        """

        errors = validate_cover_letter_v2(excellent_letter, sample_state_tech_saas, allow_generic_phrases=0)

        # Should pass all gates
        assert len(errors) == 0, f"Validation errors: {errors}"

# ===== TESTS: CoverLetterGenerator Integration =====

class TestCoverLetterGeneratorV2Integration:
    """Test CoverLetterGenerator with V2 validation enabled."""

# ===== TESTS: Edge Cases =====

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_validates_empty_cover_letter(self, sample_state_tech_saas):
        """Should reject empty cover letter."""
        errors = validate_cover_letter_v2("", sample_state_tech_saas)

        assert len(errors) > 0
        assert any("empty" in e.lower() for e in errors)

    def test_handles_state_with_no_company_signals(self, sample_state_tech_saas):
        """Should handle state without company signals gracefully."""
        state = sample_state_tech_saas.copy()
        state["company_research"] = {}  # No signals

        cover_letter = """
Your API scalability and microservices migration challenges align with my experience.
At Seven.One Entertainment Group, I reduced costs by 75% ($3M) while handling 10M
requests daily. At DataCorp, I improved deployment speed 16x.

I have applied for this role. Let's discuss: https://calendly.com/taimooralam/15min
        """

        errors = validate_cover_letter_v2(
            cover_letter,
            state,
            require_company_signal=False  # Disable signal check
        )

        # Should not fail on missing signal if check disabled
        signal_errors = [e for e in errors if "signal" in e.lower()]
        assert len(signal_errors) == 0

    def test_handles_state_with_no_stars(self, sample_state_tech_saas):
        """Should handle state without STAR records."""
        state = sample_state_tech_saas.copy()
        state["selected_stars"] = []

        cover_letter = """
Your API scalability challenges require expertise in microservices and cloud platforms.
My experience includes building systems handling millions of requests with high reliability.

I have applied for this role. Let's discuss: https://calendly.com/taimooralam/15min
        """

        errors = validate_cover_letter_v2(cover_letter, state)

        # Should not require company+metric if no STARs
        # But should still validate pain points and generic phrases
        assert len(errors) >= 1  # Should fail on pain points or generics

    def test_handles_very_long_cover_letter(self, sample_state_tech_saas):
        """Should validate very long cover letters."""
        long_letter = """
Your Series B funding signals exciting growth—and critical challenges with API scalability
and microservices migration. """ + "At Seven.One Entertainment Group, I led transformations. " * 50 + """
I reduced costs by 75% ($3M annually) while handling 10M requests daily.

I have applied for this role. Let's discuss: https://calendly.com/taimooralam/15min
        """

        errors = validate_cover_letter_v2(long_letter, sample_state_tech_saas)

        # Should validate regardless of length
        assert isinstance(errors, list)

# ===== TESTS: A/B Comparison =====

class TestABComparison:
    """Tests for comparing V1 vs V2 prompt outputs."""
