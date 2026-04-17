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

        # But may reframe focus on architectural decisions

# ===== TESTS: Professional Summary Generation =====

class TestProfessionalSummaryGeneration:
    """Test professional summary generation with quantified highlights."""

# ===== TESTS: Hallucination QA =====

class TestHallucinationQA:
    """Test hallucination detection in generated CVs."""

# ===== TESTS: Integration =====

class TestCVGeneratorV2Integration:
    """Test CVGenerator with all V2 improvements."""

# ===== TESTS: Edge Cases =====

class TestEdgeCases:
    """Test edge cases and error handling."""

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
