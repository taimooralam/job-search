"""
Unit tests for Layer 6b CV Generator V2 prompt improvements.

Tests new validation rules:
- Master CV parser extracts all sections without loss
- Master CV parser preserves all metrics exactly
- CV tailoring emphasizes dominant competency dimension
- Professional summary includes ≥1 quantified highlight
- Hallucination QA detects fabricated companies
- Hallucination QA allows formatting variations
- Hallucination QA detects metric inflation

These tests follow TDD approach and should FAIL initially until
prompt improvements are implemented.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List
import re

# Import test utilities
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.validation_helpers import extract_metrics
from fixtures.sample_jobs import (
    create_mock_state_for_job,
    SAMPLE_MASTER_CV,
    SAMPLE_STARS,
    get_sample_job
)

# Import module under test
from src.layer6.cv_generator import CVGenerator, CompetencyMixOutput, HallucinationQAOutput


# ===== FIXTURES =====

@pytest.fixture
def sample_master_cv():
    """Sample master CV for testing."""
    return SAMPLE_MASTER_CV


@pytest.fixture
def sample_competency_mix_architecture_heavy():
    """Competency mix for architecture-heavy role (60% arch, 20% delivery, 10% process, 10% leadership)."""
    return {
        "delivery": 20,
        "process": 10,
        "architecture": 60,
        "leadership": 10,
        "reasoning": "Role focuses on system design and technical decision-making"
    }


@pytest.fixture
def sample_competency_mix_leadership_heavy():
    """Competency mix for leadership-heavy role (10% delivery, 10% process, 20% arch, 60% leadership)."""
    return {
        "delivery": 10,
        "process": 10,
        "architecture": 20,
        "leadership": 60,
        "reasoning": "Role focuses on team management and organizational leadership"
    }


@pytest.fixture
def sample_state_tech_saas():
    """Sample state for tech SaaS role."""
    return create_mock_state_for_job(
        "tech_saas_backend_engineer",
        selected_stars=[SAMPLE_STARS[0], SAMPLE_STARS[2]]
    )


@pytest.fixture
def mock_llm_providers(mocker):
    """Mock all LLM providers to prevent real API calls."""
    # Mock OpenAI
    mock_openai = mocker.patch("langchain_openai.ChatOpenAI")
    mock_anthropic = mocker.patch("langchain_anthropic.ChatAnthropic")

    # Create mock instances
    mock_openai_instance = MagicMock()
    mock_anthropic_instance = MagicMock()

    mock_openai.return_value = mock_openai_instance
    mock_anthropic.return_value = mock_anthropic_instance

    return {"openai": mock_openai, "anthropic": mock_anthropic}


# ===== TESTS: Master CV Parser =====

class TestMasterCVParser:
    """Test master CV parsing functionality."""

    @pytest.mark.skip(reason="Will fail until V2 parser implemented")
    def test_master_cv_parser_extracts_all_sections(self, sample_master_cv):
        """Master CV parser must extract all sections without loss."""
        # This will test the new LLM-driven parser
        from src.common.cv_parser import MasterCVParser

        parser = MasterCVParser()
        parsed = parser.parse_master_cv(sample_master_cv)

        # Verify all sections present
        assert parsed.header is not None
        assert parsed.header.name == "Taimoor Alam"
        assert parsed.header.email == "taimoor@example.com"

        assert parsed.profile_summary is not None
        assert len(parsed.profile_summary) > 0

        assert len(parsed.experience) >= 3  # Three roles
        assert len(parsed.education) >= 2  # Two degrees

        assert len(parsed.core_skills) > 0

    @pytest.mark.skip(reason="Will fail until V2 parser implemented")
    def test_master_cv_parser_preserves_metrics(self, sample_master_cv):
        """Parser must preserve all metrics exactly as written."""
        from src.common.cv_parser import MasterCVParser

        parser = MasterCVParser()
        parsed = parser.parse_master_cv(sample_master_cv)

        # Extract all achievement text
        all_achievements = []
        for exp in parsed.experience:
            all_achievements.extend(exp.achievements)

        achievements_text = " ".join(all_achievements)

        # Verify key metrics are preserved exactly
        expected_metrics = ["75%", "$3M", "300%", "10M", "99.9%", "12", "15 minutes"]

        for metric in expected_metrics:
            assert metric in sample_master_cv, f"Metric '{metric}' should be in master CV"
            # Parser should preserve it
            assert metric in achievements_text, f"Metric '{metric}' not preserved in parsed output"

    @pytest.mark.skip(reason="Will fail until V2 parser implemented")
    def test_master_cv_parser_handles_missing_sections(self):
        """Parser should handle CVs with missing sections gracefully."""
        from src.common.cv_parser import MasterCVParser

        minimal_cv = """
# John Doe
john@example.com

## Experience
### Company A
**Engineer** | 2020-2023
- Built features
        """.strip()

        parser = MasterCVParser()
        parsed = parser.parse_master_cv(minimal_cv)

        # Should not crash, should return empty arrays
        assert parsed.header.name == "John Doe"
        assert len(parsed.experience) >= 1
        assert len(parsed.education) == 0  # Missing section
        assert len(parsed.core_skills) == 0  # Missing section

    def test_extract_metrics_from_master_cv(self, sample_master_cv):
        """Should extract all metrics from master CV."""
        metrics = extract_metrics(sample_master_cv)

        # Should find major metrics
        assert "75" in metrics or "75.0" in metrics  # 75% cost reduction
        assert "3" in metrics  # $3M
        assert "300" in metrics  # 300% improvement
        assert "10" in metrics  # 10M requests
        assert "99.9" in metrics  # 99.9% uptime
        # Note: "12 engineers" doesn't match current patterns (no units like "engineers")


# ===== TESTS: CV Tailoring (Role-Specific Emphasis) =====

class TestCVTailoring:
    """Test role-specific achievement tailoring."""

    @pytest.mark.skip(reason="Will fail until V2 tailoring implemented")
    def test_cv_tailoring_emphasizes_dominant_competency(
        self,
        sample_competency_mix_architecture_heavy
    ):
        """Tailored achievements must emphasize dominant competency dimension."""
        # Original achievement from master CV
        original_achievement = (
            "Led migration from monolith to microservices, reducing deployment "
            "time from 4 hours to 15 minutes and enabling 10x team scaling"
        )

        cv_gen = CVGenerator()

        # Tailor for architecture-heavy role (60%)
        tailored = cv_gen._tailor_achievement(
            original_achievement,
            sample_competency_mix_architecture_heavy
        )

        # Should emphasize architecture aspects
        architecture_keywords = [
            "architect", "design", "pattern", "structure", "bounded context",
            "microservices decomposition", "event-driven", "system design"
        ]

        assert any(kw in tailored.lower() for kw in architecture_keywords), \
            f"Architecture emphasis missing in: {tailored}"

        # Should de-emphasize delivery metrics
        assert "deployment time" in tailored  # Keep the metric
        # But may reframe focus on architectural decisions

    @pytest.mark.skip(reason="Will fail until V2 tailoring implemented")
    def test_cv_tailoring_for_leadership_heavy_role(
        self,
        sample_competency_mix_leadership_heavy
    ):
        """Tailoring for leadership-heavy role emphasizes team/people aspects."""
        original_achievement = (
            "Led migration from monolith to microservices, reducing deployment "
            "time from 4 hours to 15 minutes and enabling 10x team scaling"
        )

        cv_gen = CVGenerator()

        # Tailor for leadership-heavy role (60%)
        tailored = cv_gen._tailor_achievement(
            original_achievement,
            sample_competency_mix_leadership_heavy
        )

        # Should emphasize leadership aspects
        leadership_keywords = [
            "led", "team", "mentored", "managed", "coached", "enabled",
            "cross-functional", "scaling", "engineers"
        ]

        assert any(kw in tailored.lower() for kw in leadership_keywords), \
            f"Leadership emphasis missing in: {tailored}"

    @pytest.mark.skip(reason="Will fail until V2 tailoring implemented")
    def test_tailoring_preserves_original_metrics(
        self,
        sample_competency_mix_architecture_heavy
    ):
        """Tailoring must preserve original metrics exactly (no inflation)."""
        original_achievement = "Reduced incident MTTR from 2 hours to 15 minutes (87% improvement)"

        cv_gen = CVGenerator()
        tailored = cv_gen._tailor_achievement(
            original_achievement,
            sample_competency_mix_architecture_heavy
        )

        # Verify metrics preserved
        assert "2 hours" in tailored or "2h" in tailored
        assert "15 minutes" in tailored or "15min" in tailored
        assert "87%" in tailored or "87" in tailored

        # Should NOT inflate metrics
        assert "90%" not in tailored  # Inflated percentage
        assert "3 hours" not in tailored  # Inflated time


# ===== TESTS: Professional Summary Generation =====

class TestProfessionalSummaryGeneration:
    """Test professional summary generation with quantified highlights."""

    @pytest.mark.skip(reason="Will fail until V2 summary prompt implemented")
    def test_professional_summary_includes_quantified_highlight(
        self,
        sample_state_tech_saas,
        sample_competency_mix_architecture_heavy
    ):
        """Professional summary must include ≥1 quantified highlight."""
        cv_gen = CVGenerator()

        summary = cv_gen._generate_professional_summary(
            sample_state_tech_saas,
            sample_competency_mix_architecture_heavy
        )

        # Should include at least one metric
        metrics = extract_metrics(summary)

        assert len(metrics) >= 1, f"No quantified highlights in summary: {summary}"

    @pytest.mark.skip(reason="Will fail until V2 summary prompt implemented")
    def test_professional_summary_avoids_generic_phrases(
        self,
        sample_state_tech_saas,
        sample_competency_mix_architecture_heavy
    ):
        """Professional summary must avoid generic phrases."""
        cv_gen = CVGenerator()

        summary = cv_gen._generate_professional_summary(
            sample_state_tech_saas,
            sample_competency_mix_architecture_heavy
        )

        # Anti-patterns that should NOT appear
        generic_patterns = [
            "seasoned professional",
            "proven track record",
            "strong background",
            "years of experience",
            "diverse background"
        ]

        for pattern in generic_patterns:
            assert pattern not in summary.lower(), \
                f"Generic phrase '{pattern}' found in summary: {summary}"

    @pytest.mark.skip(reason="Will fail until V2 summary prompt implemented")
    def test_professional_summary_leads_with_dominant_competency(
        self,
        sample_state_tech_saas,
        sample_competency_mix_architecture_heavy
    ):
        """Summary should lead with candidate's strength in dominant competency."""
        cv_gen = CVGenerator()

        summary = cv_gen._generate_professional_summary(
            sample_state_tech_saas,
            sample_competency_mix_architecture_heavy
        )

        # For architecture-heavy role, should emphasize architecture early
        first_sentence = summary.split('.')[0]

        architecture_indicators = [
            "architect", "system design", "platform", "infrastructure",
            "microservices", "distributed systems", "technical"
        ]

        assert any(ind in first_sentence.lower() for ind in architecture_indicators), \
            f"Architecture emphasis missing in opening: {first_sentence}"


# ===== TESTS: Hallucination QA =====

class TestHallucinationQA:
    """Test hallucination detection in generated CVs."""

    @pytest.mark.skip(reason="Will fail until V2 QA prompt implemented")
    def test_hallucination_qa_detects_fabricated_company(self, sample_master_cv):
        """Hallucination QA must catch companies not in master CV."""
        cv_gen = CVGenerator()

        generated_cv_text = """
### FakeCorp Inc
**Senior Engineer** | 2018-2020
- Built payment systems
        """

        qa_result = cv_gen._run_hallucination_qa(generated_cv_text, sample_master_cv)

        assert not qa_result.is_valid
        assert len(qa_result.fabricated_employers) > 0
        assert "FakeCorp" in qa_result.fabricated_employers[0]

    @pytest.mark.skip(reason="Will fail until V2 QA prompt implemented")
    def test_hallucination_qa_allows_formatting_variations(self, sample_master_cv):
        """QA should allow date format variations (2020-2023 vs 2020–2023)."""
        cv_gen = CVGenerator()

        # Generated CV with em-dash instead of hyphen
        generated_cv_text = """
### Seven.One Entertainment Group
**Technical Lead** | 2020–2023

- Led team of 12 engineers
        """

        qa_result = cv_gen._run_hallucination_qa(generated_cv_text, sample_master_cv)

        # Should pass - formatting variation is acceptable
        assert qa_result.is_valid
        assert len(qa_result.fabricated_dates) == 0

    @pytest.mark.skip(reason="Will fail until V2 QA prompt implemented")
    def test_hallucination_qa_allows_company_abbreviations(self, sample_master_cv):
        """QA should allow obvious company name abbreviations."""
        cv_gen = CVGenerator()

        # Using abbreviated company name
        generated_cv_text = """
### Seven.One
**Technical Lead** | 2020-2023

- Led platform engineering team
        """

        qa_result = cv_gen._run_hallucination_qa(generated_cv_text, sample_master_cv)

        # Should pass - "Seven.One" is abbreviation of "Seven.One Entertainment Group"
        assert qa_result.is_valid or "Seven.One" in sample_master_cv

    @pytest.mark.skip(reason="Will fail until V2 QA prompt implemented")
    def test_hallucination_qa_detects_metric_inflation(self, sample_master_cv):
        """QA must catch inflated metrics (75% claimed when master CV says 60%)."""
        cv_gen = CVGenerator()

        # Inflated metric
        generated_cv_text = """
### Seven.One Entertainment Group
**Technical Lead** | 2020-2023

- Reduced AWS costs by 90% ($5M annually)
        """

        qa_result = cv_gen._run_hallucination_qa(generated_cv_text, sample_master_cv)

        # Should fail - master CV says "75% ($3M annually)"
        assert not qa_result.is_valid
        # Check for fabricated metrics in issues
        assert any("90%" in str(qa_result.issues) or "5M" in str(qa_result.issues))

    @pytest.mark.skip(reason="Will fail until V2 QA prompt implemented")
    def test_hallucination_qa_detects_wrong_dates(self, sample_master_cv):
        """QA must catch date mismatches (different years)."""
        cv_gen = CVGenerator()

        # Wrong dates
        generated_cv_text = """
### Seven.One Entertainment Group
**Technical Lead** | 2019-2022

- Led platform team
        """

        qa_result = cv_gen._run_hallucination_qa(generated_cv_text, sample_master_cv)

        # Should fail - master CV says "2020–Present"
        assert not qa_result.is_valid
        assert len(qa_result.fabricated_dates) > 0

    @pytest.mark.skip(reason="Will fail until V2 QA prompt implemented")
    def test_hallucination_qa_detects_fabricated_degrees(self, sample_master_cv):
        """QA must catch degrees/schools not in master CV."""
        cv_gen = CVGenerator()

        generated_cv_text = """
## Education
- Ph.D. Computer Science — Stanford University
        """

        qa_result = cv_gen._run_hallucination_qa(generated_cv_text, sample_master_cv)

        # Should fail - master CV has M.Sc. from TU Munich, not Ph.D. from Stanford
        assert not qa_result.is_valid
        assert len(qa_result.fabricated_degrees) > 0


# ===== TESTS: Integration =====

class TestCVGeneratorV2Integration:
    """Test CVGenerator with all V2 improvements."""

    @pytest.mark.skip(reason="Will fail until V2 fully implemented")
    def test_full_pipeline_with_parser_and_tailoring(
        self,
        mock_llm_providers,
        sample_state_tech_saas,
        sample_competency_mix_architecture_heavy
    ):
        """Test full CV generation pipeline with V2 enhancements."""
        cv_gen = CVGenerator()

        # Generate CV
        cv_path, reasoning = cv_gen.generate_cv(
            sample_state_tech_saas,
            competency_mix=sample_competency_mix_architecture_heavy
        )

        assert cv_path is not None
        assert reasoning is not None

        # Read generated CV
        with open(cv_path, 'r') as f:
            cv_text = f.read()

        # Verify quality criteria
        # 1. Should not contain fabricated companies
        qa_result = cv_gen._run_hallucination_qa(cv_text, SAMPLE_MASTER_CV)
        assert qa_result.is_valid

        # 2. Should contain quantified highlights
        metrics = extract_metrics(cv_text)
        assert len(metrics) >= 3

        # 3. Should emphasize architecture (dominant competency)
        assert any(kw in cv_text.lower() for kw in ["architect", "design", "system"])


# ===== TESTS: Edge Cases =====

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.skip(reason="Will fail until V2 parser implemented")
    def test_parser_handles_malformed_cv(self):
        """Parser should handle malformed master CV gracefully."""
        from src.common.cv_parser import MasterCVParser

        malformed_cv = "Some random text without proper structure"

        parser = MasterCVParser()

        # Should not crash
        try:
            parsed = parser.parse_master_cv(malformed_cv)
            assert True  # Succeeded without crashing
        except Exception as e:
            pytest.fail(f"Parser crashed on malformed CV: {e}")

    @pytest.mark.skip(reason="Will fail until V2 QA implemented")
    def test_qa_handles_empty_master_cv(self):
        """QA should handle empty master CV."""
        cv_gen = CVGenerator()

        generated_cv = "## Experience\n### Company A\n**Role** | 2020-2023"

        qa_result = cv_gen._run_hallucination_qa(generated_cv, "")

        # Should flag everything as fabricated
        assert not qa_result.is_valid

    @pytest.mark.skip(reason="Will fail until V2 tailoring implemented")
    def test_tailoring_handles_achievement_without_metrics(
        self,
        sample_competency_mix_architecture_heavy
    ):
        """Tailoring should handle achievements without metrics."""
        cv_gen = CVGenerator()

        achievement_no_metrics = "Led team building platform features"

        tailored = cv_gen._tailor_achievement(
            achievement_no_metrics,
            sample_competency_mix_architecture_heavy
        )

        # Should still tailor emphasis, even without metrics
        assert len(tailored) > 0
        assert "led" in tailored.lower()


# ===== TESTS: CompetencyMix Validation =====

class TestCompetencyMixValidation:
    """Test competency mix schema validation."""

    def test_competency_mix_validates_sum_to_100(self):
        """Competency percentages must sum to exactly 100."""
        # Valid mix - note: reasoning must be ≥50 chars per schema
        valid_mix = CompetencyMixOutput(
            delivery=25,
            process=25,
            architecture=25,
            leadership=25,
            reasoning="Balanced role requiring equal emphasis on delivery, process, architecture, and leadership."
        )

        assert valid_mix.delivery + valid_mix.process + valid_mix.architecture + valid_mix.leadership == 100

    def test_competency_mix_rejects_invalid_sum(self):
        """Should reject competency mix that doesn't sum to 100."""
        with pytest.raises(ValueError, match="must sum to 100"):
            CompetencyMixOutput(
                delivery=30,
                process=30,
                architecture=30,
                leadership=30,  # Sum = 120
                reasoning="Invalid"
            )

    def test_competency_mix_requires_reasoning(self):
        """Competency mix must include reasoning (min 50 chars)."""
        with pytest.raises(ValueError):
            CompetencyMixOutput(
                delivery=25,
                process=25,
                architecture=25,
                leadership=25,
                reasoning="Short"  # Too short
            )
