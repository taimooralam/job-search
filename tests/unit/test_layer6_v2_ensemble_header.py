"""
Tests for Ensemble Header Generator.

Tests the tiered ensemble generation system:
- Gold tier: 3 passes + synthesis + validation
- Silver tier: 2 passes + synthesis
- Bronze/Skip tier: single-shot (delegates to HeaderGenerator)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass

from src.layer6_v2.ensemble_header_generator import (
    EnsembleHeaderGenerator,
    PersonaType,
    PersonaProfileResult,
    generate_ensemble_header,
)
from src.layer6_v2.types import (
    StitchedCV,
    StitchedRole,
    ProfileOutput,
    SkillsSection,
    SkillEvidence,
    HeaderOutput,
    ValidationFlags,
    EnsembleMetadata,
)
from src.common.tiering import (
    ProcessingTier,
    TierConfig,
    get_tier_config,
)


# ===== FIXTURES =====


@pytest.fixture
def sample_stitched_cv():
    """Sample stitched CV for testing."""
    return StitchedCV(
        roles=[
            StitchedRole(
                role_id="01_test_corp",
                company="Test Corp",
                title="Engineering Manager",
                location="Berlin, DE",
                period="2020-Present",
                bullets=[
                    "Led team of 15 engineers to deliver $2M cost savings through cloud migration",
                    "Reduced deployment time by 75% through CI/CD pipeline improvements",
                    "Built event-driven architecture handling 50,000 requests/second",
                ],
                skills=["AWS", "Python", "Kubernetes"],
            ),
        ],
        deduplication_result=None,
    )


@pytest.fixture
def sample_extracted_jd():
    """Sample extracted JD for testing."""
    return {
        "title": "Senior Engineering Manager",
        "company": "Acme Inc",
        "role_category": "engineering_manager",
        "top_keywords": ["AWS", "Python", "Kubernetes", "Leadership", "CI/CD"],
        "pain_points": ["Scale engineering team", "Improve delivery"],
        "differentiators": ["Technical leadership", "Cloud expertise"],
    }


@pytest.fixture
def sample_candidate_data():
    """Sample candidate data for testing."""
    return {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1 555-1234",
        "linkedin": "linkedin.com/in/johndoe",
        "location": "Berlin, DE",
        "education_masters": "M.Sc. Computer Science - TUM",
        "education_bachelors": "B.Sc. Software Engineering",
        "certifications": ["AWS Solutions Architect"],
        "languages": ["English (C1)", "German (B2)"],
    }


@pytest.fixture
def sample_skill_whitelist():
    """Sample skill whitelist for testing."""
    return {
        "hard_skills": ["Python", "AWS", "Kubernetes", "TypeScript", "CI/CD"],
        "soft_skills": ["Leadership", "Mentoring", "Strategic Planning"],
    }


@pytest.fixture
def gold_tier_config():
    """Gold tier configuration."""
    return get_tier_config(ProcessingTier.GOLD)


@pytest.fixture
def silver_tier_config():
    """Silver tier configuration."""
    return get_tier_config(ProcessingTier.SILVER)


@pytest.fixture
def bronze_tier_config():
    """Bronze tier configuration."""
    return get_tier_config(ProcessingTier.BRONZE)


@pytest.fixture
def mock_profile_response():
    """Mock ProfileResponse for LLM calls."""
    mock = Mock()
    mock.headline = "Senior Engineering Manager | 10+ Years Technology Leadership"
    mock.narrative = "Technology leader with expertise in scaling engineering teams..."
    mock.core_competencies = ["Engineering Leadership", "AWS", "Python", "CI/CD"]
    mock.highlights_used = ["$2M cost savings", "75% reduction"]
    mock.keywords_integrated = ["AWS", "Python", "Kubernetes"]
    mock.exact_title_used = "Senior Engineering Manager"
    mock.answers_who = True
    mock.answers_what_problems = True
    mock.answers_proof = True
    mock.answers_why_you = True
    return mock


# ===== TESTS: PersonaType =====


class TestPersonaType:
    """Test PersonaType enum."""

    def test_has_metric_persona(self):
        """Metric persona exists."""
        assert PersonaType.METRIC.value == "metric"

    def test_has_narrative_persona(self):
        """Narrative persona exists."""
        assert PersonaType.NARRATIVE.value == "narrative"

    def test_has_keyword_persona(self):
        """Keyword persona exists."""
        assert PersonaType.KEYWORD.value == "keyword"


# ===== TESTS: Tier Routing =====


class TestTierRouting:
    """Test tier-based routing logic."""

    def test_gold_tier_uses_three_personas(self):
        """Gold tier should use 3 personas."""
        personas = EnsembleHeaderGenerator.TIER_PERSONAS[ProcessingTier.GOLD]
        assert len(personas) == 3
        assert PersonaType.METRIC in personas
        assert PersonaType.NARRATIVE in personas
        assert PersonaType.KEYWORD in personas

    def test_silver_tier_uses_two_personas(self):
        """Silver tier should use 2 personas."""
        personas = EnsembleHeaderGenerator.TIER_PERSONAS[ProcessingTier.SILVER]
        assert len(personas) == 2
        assert PersonaType.METRIC in personas
        assert PersonaType.KEYWORD in personas

    def test_bronze_tier_uses_no_personas(self):
        """Bronze tier should use single-shot (no personas)."""
        personas = EnsembleHeaderGenerator.TIER_PERSONAS[ProcessingTier.BRONZE]
        assert len(personas) == 0

    def test_skip_tier_uses_no_personas(self):
        """Skip tier should use single-shot (no personas)."""
        personas = EnsembleHeaderGenerator.TIER_PERSONAS[ProcessingTier.SKIP]
        assert len(personas) == 0


# ===== TESTS: Initialization =====


class TestEnsembleGeneratorInit:
    """Test EnsembleHeaderGenerator initialization."""

    @pytest.mark.asyncio
    @patch('src.layer6_v2.ensemble_header_generator.UnifiedLLM')
    @patch('src.layer6_v2.ensemble_header_generator.HeaderGenerator')
    async def test_initializes_with_gold_tier(
        self, mock_header_gen, mock_unified_llm, gold_tier_config, sample_skill_whitelist
    ):
        """Initializes correctly with Gold tier."""
        generator = EnsembleHeaderGenerator(
            tier_config=gold_tier_config,
            skill_whitelist=sample_skill_whitelist,
        )
        assert generator.tier_config == gold_tier_config
        assert generator._skill_whitelist == sample_skill_whitelist

    @pytest.mark.asyncio
    @patch('src.layer6_v2.ensemble_header_generator.UnifiedLLM')
    @patch('src.layer6_v2.ensemble_header_generator.HeaderGenerator')
    async def test_initializes_with_silver_tier(
        self, mock_header_gen, mock_unified_llm, silver_tier_config
    ):
        """Initializes correctly with Silver tier."""
        generator = EnsembleHeaderGenerator(
            tier_config=silver_tier_config,
        )
        assert generator.tier_config == silver_tier_config


# ===== TESTS: Validation Flags =====


class TestValidationFlags:
    """Test ValidationFlags dataclass."""

    def test_empty_flags(self):
        """Empty flags should have no flags."""
        flags = ValidationFlags()
        assert not flags.has_flags
        assert flags.total_flags == 0

    def test_flags_with_ungrounded_metrics(self):
        """Flags with ungrounded metrics."""
        flags = ValidationFlags(ungrounded_metrics=["$5M revenue"])
        assert flags.has_flags
        assert flags.total_flags == 1

    def test_flags_with_ungrounded_skills(self):
        """Flags with ungrounded skills."""
        flags = ValidationFlags(ungrounded_skills=["React", "Java"])
        assert flags.has_flags
        assert flags.total_flags == 2

    def test_flags_with_flagged_claims(self):
        """Flags with flagged claims."""
        flags = ValidationFlags(flagged_claims=["Led 100-person team"])
        assert flags.has_flags
        assert flags.total_flags == 1

    def test_flags_to_dict(self):
        """Flags serialize to dict correctly."""
        flags = ValidationFlags(
            ungrounded_metrics=["$5M"],
            ungrounded_skills=["React"],
            flagged_claims=["Claim 1"],
        )
        d = flags.to_dict()
        assert d["ungrounded_metrics"] == ["$5M"]
        assert d["ungrounded_skills"] == ["React"]
        assert d["flagged_claims"] == ["Claim 1"]
        assert d["has_flags"] is True
        assert d["total_flags"] == 3


# ===== TESTS: Ensemble Metadata =====


class TestEnsembleMetadata:
    """Test EnsembleMetadata dataclass."""

    def test_default_metadata(self):
        """Default metadata values."""
        meta = EnsembleMetadata()
        assert meta.tier_used == ""
        assert meta.passes_executed == 1
        assert meta.personas_used == []
        assert meta.synthesis_applied is False

    def test_gold_tier_metadata(self):
        """Gold tier metadata."""
        meta = EnsembleMetadata(
            tier_used="GOLD",
            passes_executed=3,
            personas_used=["metric", "narrative", "keyword"],
            synthesis_model="claude-3-5-haiku-20241022",
            synthesis_applied=True,
            generation_time_ms=15000,
        )
        assert meta.tier_used == "GOLD"
        assert meta.passes_executed == 3
        assert len(meta.personas_used) == 3
        assert meta.synthesis_applied is True

    def test_metadata_with_validation_flags(self):
        """Metadata with validation flags."""
        flags = ValidationFlags(ungrounded_metrics=["$5M"])
        meta = EnsembleMetadata(
            tier_used="GOLD",
            validation_flags=flags,
        )
        assert meta.validation_flags is not None
        assert meta.validation_flags.has_flags

    def test_metadata_to_dict(self):
        """Metadata serializes to dict correctly."""
        meta = EnsembleMetadata(
            tier_used="SILVER",
            passes_executed=2,
            personas_used=["metric", "keyword"],
            synthesis_applied=True,
            generation_time_ms=10000,
        )
        d = meta.to_dict()
        assert d["tier_used"] == "SILVER"
        assert d["passes_executed"] == 2
        assert d["personas_used"] == ["metric", "keyword"]
        assert d["generation_time_ms"] == 10000


# ===== TESTS: Generate with Mocked LLMs =====


class TestGenerateWithMockedLLMs:
    """Test generate() with mocked LLM calls."""

    @pytest.mark.asyncio
    @patch('src.layer6_v2.ensemble_header_generator.UnifiedLLM')
    @patch('src.layer6_v2.ensemble_header_generator.HeaderGenerator')
    async def test_bronze_tier_uses_fallback(
        self,
        mock_header_gen_class,
        mock_unified_llm,
        bronze_tier_config,
        sample_stitched_cv,
        sample_extracted_jd,
        sample_candidate_data,
    ):
        """Bronze tier uses fallback single-shot generator."""
        # Setup mock - need to return async mock
        from unittest.mock import AsyncMock
        mock_header_output = Mock(spec=HeaderOutput)
        mock_header_output.profile = Mock()
        mock_header_output.profile.word_count = 100
        mock_header_output.skills_sections = []
        mock_header_output.ensemble_metadata = None
        mock_header_gen_class.return_value.generate = AsyncMock(return_value=mock_header_output)

        generator = EnsembleHeaderGenerator(tier_config=bronze_tier_config)
        result = await generator.generate(
            sample_stitched_cv,
            sample_extracted_jd,
            sample_candidate_data,
        )

        # Verify fallback was used
        mock_header_gen_class.return_value.generate.assert_called_once()

        # Verify metadata reflects single-shot
        assert result.ensemble_metadata is not None
        assert result.ensemble_metadata.passes_executed == 1
        assert result.ensemble_metadata.synthesis_applied is False


# ===== TESTS: Convenience Function =====


class TestConvenienceFunction:
    """Test generate_ensemble_header convenience function."""

    @pytest.mark.asyncio
    @patch('src.layer6_v2.ensemble_header_generator.EnsembleHeaderGenerator')
    async def test_convenience_function_with_fit_score(
        self,
        mock_generator_class,
        sample_stitched_cv,
        sample_extracted_jd,
        sample_candidate_data,
    ):
        """Convenience function uses fit score for tier."""
        from unittest.mock import AsyncMock
        mock_header = Mock(spec=HeaderOutput)
        mock_generator_class.return_value.generate = AsyncMock(return_value=mock_header)

        result = await generate_ensemble_header(
            sample_stitched_cv,
            sample_extracted_jd,
            sample_candidate_data,
            fit_score=90,  # Gold tier
        )

        mock_generator_class.return_value.generate.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.layer6_v2.ensemble_header_generator.EnsembleHeaderGenerator')
    async def test_convenience_function_with_tier_override(
        self,
        mock_generator_class,
        sample_stitched_cv,
        sample_extracted_jd,
        sample_candidate_data,
    ):
        """Convenience function respects tier override."""
        from unittest.mock import AsyncMock
        mock_header = Mock(spec=HeaderOutput)
        mock_generator_class.return_value.generate = AsyncMock(return_value=mock_header)

        result = await generate_ensemble_header(
            sample_stitched_cv,
            sample_extracted_jd,
            sample_candidate_data,
            tier_override="BRONZE",
        )

        mock_generator_class.return_value.generate.assert_called_once()


# ===== TESTS: Languages Bug Fix =====


class TestLanguagesBugFix:
    """Test that languages are properly handled."""

    def test_languages_in_candidate_data(self, sample_candidate_data):
        """Candidate data includes languages."""
        assert "languages" in sample_candidate_data
        assert len(sample_candidate_data["languages"]) == 2

    @pytest.mark.asyncio
    @patch('src.layer6_v2.ensemble_header_generator.UnifiedLLM')
    @patch('src.layer6_v2.ensemble_header_generator.HeaderGenerator')
    async def test_languages_passed_to_header_output(
        self,
        mock_header_gen_class,
        mock_unified_llm,
        bronze_tier_config,
        sample_stitched_cv,
        sample_extracted_jd,
        sample_candidate_data,
    ):
        """Languages are passed through to header output."""
        # Setup mock that preserves languages
        from unittest.mock import AsyncMock
        mock_header_output = Mock(spec=HeaderOutput)
        mock_header_output.profile = Mock()
        mock_header_output.profile.word_count = 100
        mock_header_output.skills_sections = []
        mock_header_output.ensemble_metadata = None
        mock_header_output.languages = sample_candidate_data["languages"]
        mock_header_gen_class.return_value.generate = AsyncMock(return_value=mock_header_output)

        generator = EnsembleHeaderGenerator(tier_config=bronze_tier_config)
        result = await generator.generate(
            sample_stitched_cv,
            sample_extracted_jd,
            sample_candidate_data,
        )

        # Languages should be present
        assert result.languages == sample_candidate_data["languages"]


# ===== TESTS: Prompt Functions =====


class TestPromptFunctions:
    """Test persona prompt building functions."""

    def test_build_persona_user_prompt_metric(self):
        """Metric persona prompt includes emphasis."""
        from src.layer6_v2.prompts.header_generation import build_persona_user_prompt

        prompt = build_persona_user_prompt(
            persona="metric",
            candidate_name="John Doe",
            job_title="Engineering Manager",
            role_category="engineering_manager",
            top_keywords=["AWS", "Python"],
            experience_bullets=["Led team of 15..."],
            metrics=["$2M savings"],
        )

        assert "METRIC" in prompt
        assert "quantified" in prompt.lower() or "numbers" in prompt.lower()

    def test_build_persona_user_prompt_narrative(self):
        """Narrative persona prompt includes emphasis."""
        from src.layer6_v2.prompts.header_generation import build_persona_user_prompt

        prompt = build_persona_user_prompt(
            persona="narrative",
            candidate_name="John Doe",
            job_title="Engineering Manager",
            role_category="engineering_manager",
            top_keywords=["AWS", "Python"],
            experience_bullets=["Led team of 15..."],
            metrics=["$2M savings"],
        )

        assert "NARRATIVE" in prompt
        assert "story" in prompt.lower() or "transformation" in prompt.lower()

    def test_build_persona_user_prompt_keyword(self):
        """Keyword persona prompt includes emphasis."""
        from src.layer6_v2.prompts.header_generation import build_persona_user_prompt

        prompt = build_persona_user_prompt(
            persona="keyword",
            candidate_name="John Doe",
            job_title="Engineering Manager",
            role_category="engineering_manager",
            top_keywords=["AWS", "Python"],
            experience_bullets=["Led team of 15..."],
            metrics=["$2M savings"],
        )

        assert "KEYWORD" in prompt
        assert "ats" in prompt.lower() or "keyword" in prompt.lower()

    def test_build_synthesis_user_prompt(self):
        """Synthesis prompt includes all persona outputs."""
        from src.layer6_v2.prompts.header_generation import build_synthesis_user_prompt

        persona_outputs = [
            {"persona": "metric", "headline": "EM | 10+ Years", "narrative": "Metrics...", "core_competencies": [], "highlights_used": [], "keywords_integrated": []},
            {"persona": "narrative", "headline": "EM | 10+ Years", "narrative": "Story...", "core_competencies": [], "highlights_used": [], "keywords_integrated": []},
        ]

        prompt = build_synthesis_user_prompt(
            persona_outputs=persona_outputs,
            job_title="Engineering Manager",
            top_keywords=["AWS"],
        )

        assert "METRIC-FOCUSED" in prompt
        assert "NARRATIVE-FOCUSED" in prompt
        assert "Synthesize" in prompt or "combine" in prompt.lower()
