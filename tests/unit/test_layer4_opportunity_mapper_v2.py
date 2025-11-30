"""
Unit tests for Layer 4 Opportunity Mapper V2 prompt improvements.

Tests new validation rules:
- Rationale must cite at least one STAR by company name
- Rationale must reference specific pain point by key terms
- Rationale must be at least 50 words (increased from 10)
- Validation rejects generic rationales (max 1 generic phrase, down from 2)
- Few-shot examples improve output quality

These tests follow TDD approach and should FAIL initially until
prompt improvements are implemented.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Import test utilities
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.validation_helpers import (
    validate_rationale_v2,
    count_pain_point_references,
    extract_star_companies,
    count_generic_phrases,
    extract_metrics
)
from fixtures.sample_jobs import (
    create_mock_state_for_job,
    SAMPLE_STARS,
    get_sample_job
)

# Import module under test
from src.layer4.opportunity_mapper import OpportunityMapper


# ===== FIXTURES =====

@pytest.fixture
def sample_state_tech_saas():
    """Sample state for tech SaaS backend engineer role."""
    return create_mock_state_for_job(
        "tech_saas_backend_engineer",
        selected_stars=[SAMPLE_STARS[0], SAMPLE_STARS[2]]  # Microservices + deployment
    )


@pytest.fixture
def sample_state_fintech():
    """Sample state for fintech payments architect role."""
    return create_mock_state_for_job(
        "fintech_payments_architect",
        selected_stars=[SAMPLE_STARS[3]]  # Fraud detection
    )


@pytest.fixture
def sample_state_healthcare():
    """Sample state for healthcare platform engineer role."""
    return create_mock_state_for_job(
        "healthcare_platform_engineer",
        selected_stars=[SAMPLE_STARS[1], SAMPLE_STARS[2]]  # SRE + CI/CD
    )


@pytest.fixture
def mock_llm_providers(mocker):
    """Mock all LLM providers to prevent real API calls."""
    # Mock OpenAI
    mock_openai = mocker.patch("langchain_openai.ChatOpenAI")
    mock_instance = MagicMock()
    mock_openai.return_value = mock_instance

    # Configure with_structured_output to return a mock that can be invoked
    mock_structured = MagicMock()
    mock_instance.with_structured_output.return_value = mock_structured

    # Mock invoke response
    from langchain_core.messages import AIMessage
    mock_structured.invoke.return_value = {
        "fit_score": 85,
        "fit_rationale": "At Seven.One Entertainment Group, candidate reduced infrastructure costs by 75% ($3M annually), directly addressing the cost optimization pain point. Built microservices architecture handling 10M requests daily with 99.9% uptime, matching the scalability requirements. However, lacks specific Kubernetes expertise at scale.",
        "fit_category": "strong_fit"
    }

    return {"openai": mock_openai}


# ===== TESTS: Validation Helpers =====

class TestValidationHelpers:
    """Test validation helper functions work correctly."""

    def test_extract_star_companies(self, sample_state_tech_saas):
        """Should extract company names from STAR records."""
        companies = extract_star_companies(sample_state_tech_saas)

        assert len(companies) >= 1
        assert "Seven.One Entertainment Group" in companies or "DataCorp" in companies

    def test_count_pain_point_references_exact_match(self, sample_state_tech_saas):
        """Should count pain points referenced by exact keywords."""
        text = "The monolithic architecture is blocking feature velocity and needs migration."
        pain_points = sample_state_tech_saas["pain_points"]

        count = count_pain_point_references(text, pain_points)

        # Should match "Monolithic architecture blocking feature velocity"
        assert count >= 1

    def test_count_pain_point_references_semantic_match(self, sample_state_tech_saas):
        """Should count pain points referenced semantically."""
        text = "Scaling the API to handle growing traffic is a critical priority."
        pain_points = sample_state_tech_saas["pain_points"]

        count = count_pain_point_references(text, pain_points)

        # Should match "API platform cannot handle traffic growth efficiently"
        assert count >= 1

    def test_count_generic_phrases(self):
        """Should detect generic boilerplate phrases."""
        generic_text = "I am excited to apply for this perfect fit role as a strong team player with proven track record."

        count = count_generic_phrases(generic_text)

        # Should find: "excited to apply", "perfect fit", "strong team player", "proven track record"
        assert count >= 3

    def test_extract_metrics(self):
        """Should extract quantified metrics from text."""
        text = "Reduced costs by 75% and saved $3M while improving deployment 16x"

        metrics = extract_metrics(text)

        assert "75" in metrics or "75.0" in metrics
        assert "3" in metrics
        assert "16" in metrics


# ===== TESTS: Rationale Validation V2 =====

class TestRationaleValidationV2:
    """Test V2 validation rules for fit rationales."""

    def test_rationale_cites_star_by_company_name(self, sample_state_tech_saas):
        """Rationale must cite at least one STAR by company name."""
        # Good rationale
        good_rationale = "At Seven.One Entertainment Group, candidate reduced costs by 75%, directly addressing cost optimization."

        errors = validate_rationale_v2(
            good_rationale,
            sample_state_tech_saas["selected_stars"],
            sample_state_tech_saas["pain_points"]
        )

        # Should pass - cites "Seven.One Entertainment Group"
        star_errors = [e for e in errors if "STAR" in e or "company" in e.lower()]
        assert len(star_errors) == 0

    def test_rationale_fails_without_star_citation(self, sample_state_tech_saas):
        """Rationale without STAR citation should fail validation."""
        bad_rationale = "Candidate has extensive experience in microservices and cloud platforms with strong background in scalability and performance optimization across multiple domains."

        errors = validate_rationale_v2(
            bad_rationale,
            sample_state_tech_saas["selected_stars"],
            sample_state_tech_saas["pain_points"],
            min_word_count=20  # Lower for this test
        )

        # Should fail - no company name cited
        assert any("STAR" in e or "company" in e.lower() for e in errors)

    def test_rationale_references_specific_pain_point(self, sample_state_tech_saas):
        """Rationale must reference at least one pain point by key terms."""
        good_rationale = "At DataCorp, candidate led migration from monolithic architecture to microservices, reducing deployment time from 4 hours to 15 minutes (16x improvement), directly addressing the feature velocity bottleneck."

        errors = validate_rationale_v2(
            good_rationale,
            sample_state_tech_saas["selected_stars"],
            sample_state_tech_saas["pain_points"]
        )

        # Should pass - references "monolithic architecture" and "feature velocity"
        pain_errors = [e for e in errors if "pain point" in e.lower()]
        assert len(pain_errors) == 0

    def test_rationale_fails_without_pain_point_reference(self, sample_state_tech_saas):
        """Rationale without pain point reference should fail."""
        bad_rationale = "At Seven.One Entertainment Group, candidate demonstrated strong technical leadership capabilities managing multiple engineering initiatives and delivering successful cloud migration projects with measurable impact."

        errors = validate_rationale_v2(
            bad_rationale,
            sample_state_tech_saas["selected_stars"],
            sample_state_tech_saas["pain_points"]
        )

        # Should fail - no pain point referenced
        assert any("pain point" in e.lower() for e in errors)

    def test_rationale_minimum_length_50_words(self, sample_state_tech_saas):
        """Rationale must be at least 50 words for substantive analysis."""
        short_rationale = "At Seven.One, candidate built microservices handling 10M requests. Fits well."

        errors = validate_rationale_v2(
            short_rationale,
            sample_state_tech_saas["selected_stars"],
            sample_state_tech_saas["pain_points"]
        )

        # Should fail - too short
        assert any("too short" in e.lower() or "word" in e.lower() for e in errors)

    def test_rationale_allows_50_plus_words(self, sample_state_tech_saas):
        """Rationale with 50+ words should pass length check."""
        good_rationale = """
        At Seven.One Entertainment Group, candidate led team of 12 engineers delivering
        cloud-native platform migration for 50M+ users, reducing AWS costs by 75% ($3M annually).
        This directly addresses the API scalability pain point. Additionally, built CI/CD pipeline
        improving deployment frequency 300%, solving the feature velocity challenge. However,
        lacks specific Kubernetes expertise at the scale required for 10M+ daily users.
        """

        errors = validate_rationale_v2(
            good_rationale,
            sample_state_tech_saas["selected_stars"],
            sample_state_tech_saas["pain_points"]
        )

        # Should pass length check
        length_errors = [e for e in errors if "short" in e.lower()]
        assert len(length_errors) == 0

    def test_validation_rejects_generic_rationale(self, sample_state_tech_saas):
        """Validation must reject rationales with >1 generic phrase."""
        generic_rationale = """
        Candidate has strong background and extensive experience as a proven team player
        with excellent problem-solving skills. This perfect fit role aligns well with
        candidate's diverse background and solid foundation in backend engineering.
        Excited to apply for this ideal candidate opportunity at Seven.One Entertainment Group.
        """

        errors = validate_rationale_v2(
            generic_rationale,
            sample_state_tech_saas["selected_stars"],
            sample_state_tech_saas["pain_points"],
            max_generic_phrases=1
        )

        # Should fail - multiple generic phrases
        assert any("generic" in e.lower() for e in errors)

    def test_rationale_allows_one_generic_phrase(self, sample_state_tech_saas):
        """Rationale with exactly 1 generic phrase should pass (threshold)."""
        acceptable_rationale = """
        At DataCorp, candidate led migration from monolith to microservices, reducing
        deployment time from 4 hours to 15 minutes (16x improvement). This extensive experience
        with microservices architecture directly addresses the feature velocity pain point.
        Built CI/CD pipeline using GitHub Actions and Kubernetes. However, lacks domain
        expertise in live streaming or video platforms.
        """

        errors = validate_rationale_v2(
            acceptable_rationale,
            sample_state_tech_saas["selected_stars"],
            sample_state_tech_saas["pain_points"],
            max_generic_phrases=1
        )

        # Should pass - only 1 generic phrase ("extensive experience")
        generic_errors = [e for e in errors if "generic" in e.lower()]
        assert len(generic_errors) == 0

    def test_rationale_requires_quantified_metric(self, sample_state_tech_saas):
        """Rationale must include at least one quantified metric."""
        no_metric_rationale = """
        At Seven.One Entertainment Group, candidate led team building cloud platform
        and improving deployment processes. Demonstrated strong technical leadership
        managing multiple engineering initiatives. Addressed scalability challenges
        through microservices architecture. However, lacks specific domain experience.
        """

        errors = validate_rationale_v2(
            no_metric_rationale,
            sample_state_tech_saas["selected_stars"],
            sample_state_tech_saas["pain_points"]
        )

        # Should fail - no metrics
        assert any("metric" in e.lower() for e in errors)


# ===== TESTS: OpportunityMapper Integration =====

class TestOpportunityMapperV2Integration:
    """Test OpportunityMapper with V2 validation enabled."""

    @pytest.mark.skip(reason="Will fail until V2 prompts implemented")
    def test_few_shot_example_improves_quality(self, mock_llm_providers, sample_state_tech_saas):
        """Test that domain-specific few-shot examples improve output quality."""
        # This test will fail initially - validates improvement after V2 implementation
        mapper = OpportunityMapper()

        # Mock LLM to return output that should pass V2 validation
        result = mapper.map_opportunity(sample_state_tech_saas)

        # Validate result meets V2 standards
        errors = validate_rationale_v2(
            result["fit_rationale"],
            sample_state_tech_saas["selected_stars"],
            sample_state_tech_saas["pain_points"]
        )

        assert len(errors) == 0, f"Rationale failed V2 validation: {errors}"

    @pytest.mark.skip(reason="Will fail until V2 prompts implemented")
    def test_structured_reasoning_framework_applied(self, mock_llm_providers, sample_state_tech_saas):
        """Test that 4-step reasoning framework is applied."""
        mapper = OpportunityMapper()

        result = mapper.map_opportunity(sample_state_tech_saas)

        # Check rationale shows evidence of structured reasoning
        rationale = result["fit_rationale"]

        # Should reference pain points
        assert count_pain_point_references(rationale, sample_state_tech_saas["pain_points"]) >= 1

        # Should cite STAR companies
        companies = extract_star_companies(sample_state_tech_saas)
        assert any(company.lower() in rationale.lower() for company in companies)

        # Should include metrics
        assert len(extract_metrics(rationale)) >= 1

    @pytest.mark.skip(reason="Will fail until V2 prompts implemented")
    def test_cross_domain_consistency(self, mock_llm_providers):
        """Test that prompt improvements work across different job domains."""
        mapper = OpportunityMapper()

        domains = ["tech_saas_backend_engineer", "fintech_payments_architect", "healthcare_platform_engineer"]

        for domain in domains:
            state = create_mock_state_for_job(domain, selected_stars=[SAMPLE_STARS[0]])

            result = mapper.map_opportunity(state)

            # All domains should pass V2 validation
            errors = validate_rationale_v2(
                result["fit_rationale"],
                state["selected_stars"],
                state["pain_points"]
            )

            assert len(errors) == 0, f"Domain '{domain}' failed validation: {errors}"


# ===== TESTS: Edge Cases =====

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_validates_empty_rationale(self, sample_state_tech_saas):
        """Should reject empty rationale."""
        errors = validate_rationale_v2(
            "",
            sample_state_tech_saas["selected_stars"],
            sample_state_tech_saas["pain_points"]
        )

        assert len(errors) > 0
        assert any("empty" in e.lower() for e in errors)

    def test_validates_rationale_with_no_stars(self, sample_state_tech_saas):
        """Should handle case when no STARs are selected."""
        rationale = "Candidate has relevant experience but lacks specific quantified achievements."

        errors = validate_rationale_v2(
            rationale,
            [],  # No STARs
            sample_state_tech_saas["pain_points"]
        )

        # Should not require STAR citation if no STARs available
        # But should still require other validations
        assert len(errors) >= 2  # Missing metric, too short, etc.

    def test_validates_rationale_with_no_pain_points(self, sample_state_tech_saas):
        """Should handle case when no pain points identified."""
        rationale = """
        At Seven.One Entertainment Group, candidate reduced costs by 75% and
        improved deployment frequency 300% through microservices architecture.
        Demonstrates strong technical leadership with quantified impact.
        """

        errors = validate_rationale_v2(
            rationale,
            sample_state_tech_saas["selected_stars"],
            [],  # No pain points
            min_word_count=30
        )

        # Should not require pain point reference if none available
        pain_errors = [e for e in errors if "pain point" in e.lower()]
        assert len(pain_errors) == 0

    def test_handles_special_characters_in_company_names(self):
        """Should handle company names with special characters."""
        state = {
            "selected_stars": [
                {"company": "Seven.One Entertainment Group"},
                {"company": "Data-Corp, Inc."}
            ],
            "pain_points": ["Scalability issues"]
        }

        rationale = "At Seven.One Entertainment Group, candidate reduced costs by 75%."

        errors = validate_rationale_v2(rationale, state["selected_stars"], state["pain_points"], min_word_count=10)

        # Should match "Seven.One Entertainment Group"
        star_errors = [e for e in errors if "STAR" in e or "company" in e.lower()]
        assert len(star_errors) == 0


# ===== TESTS: A/B Comparison =====

class TestABComparison:
    """Tests for comparing V1 vs V2 prompt outputs."""

    @pytest.mark.skip(reason="Baseline comparison - run after V2 implementation")
    def test_v2_reduces_generic_phrases(self, mock_llm_providers, sample_state_tech_saas):
        """V2 prompts should reduce generic phrase count vs V1."""
        # This test validates that V2 improves on V1
        # Will be used for A/B testing during implementation

        mapper = OpportunityMapper()
        result = mapper.map_opportunity(sample_state_tech_saas)

        generic_count = count_generic_phrases(result["fit_rationale"])

        # Target: <0.5 generic phrases on average (strict)
        assert generic_count <= 1, f"Too many generic phrases: {generic_count}"

    @pytest.mark.skip(reason="Baseline comparison - run after V2 implementation")
    def test_v2_increases_star_citation_rate(self, mock_llm_providers, sample_state_tech_saas):
        """V2 prompts should increase STAR citation rate to >90%."""
        mapper = OpportunityMapper()
        result = mapper.map_opportunity(sample_state_tech_saas)

        companies = extract_star_companies(sample_state_tech_saas)
        cited = any(company.lower() in result["fit_rationale"].lower() for company in companies)

        # Target: 90%+ citation rate
        assert cited, "Rationale must cite at least one STAR company"

    @pytest.mark.skip(reason="Baseline comparison - run after V2 implementation")
    def test_v2_increases_average_rationale_length(self, mock_llm_providers, sample_state_tech_saas):
        """V2 prompts should increase average rationale length from ~30 to ~60 words."""
        mapper = OpportunityMapper()
        result = mapper.map_opportunity(sample_state_tech_saas)

        word_count = len(result["fit_rationale"].split())

        # Target: 50-100 words (increased from ~30)
        assert 50 <= word_count <= 150, f"Rationale length {word_count} outside target range"
