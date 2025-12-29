"""
Unit tests for V2 Header Generation System.

Tests the V2 header generation components with anti-hallucination guarantees:
1. src/layer6_v2/types.py - V2 dataclasses
2. src/layer6_v2/skills_taxonomy.py - CoreCompetencyGeneratorV2
3. src/layer6_v2/prompts/header_generation.py - V2 prompts
4. src/layer6_v2/header_generator.py - V2 integration
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, List

from src.layer6_v2.types import (
    AchievementSource,
    SkillsProvenance,
    CoreCompetencySection,
    SelectionResult,
    ScoringWeights,
    ProfileOutput,
)
from src.layer6_v2.skills_taxonomy import (
    SkillsTaxonomy,
    CoreCompetencyGeneratorV2,
)
from src.layer6_v2.prompts.header_generation import (
    VALUE_PROPOSITION_TEMPLATES,
    build_value_proposition_prompt_v2,
    build_key_achievement_bullets_prompt_v2,
)


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def sample_skill_whitelist():
    """Sample skill whitelist for testing."""
    return {
        "hard_skills": [
            "TypeScript", "Python", "AWS", "AWS Lambda", "Kubernetes",
            "Terraform", "Microservices", "Event-Driven Architecture",
            "Docker", "CI/CD", "MongoDB", "REST API", "Domain-Driven Design"
        ],
        "soft_skills": [
            "Technical Leadership", "Mentoring", "Team Building",
            "Hiring & Interviewing", "Stakeholder Management", "Agile",
            "Cross-functional Collaboration"
        ],
    }


@pytest.fixture
def sample_extracted_jd():
    """Sample extracted JD data."""
    return {
        "title": "Engineering Manager",
        "role_category": "engineering_manager",
        "priority_keywords": ["kubernetes", "aws", "team leadership", "microservices"],
        "technical_skills": ["python", "typescript", "docker"],
        "keywords": ["agile", "ci/cd", "mentoring"],
        "pain_points": [
            "Need to scale team while maintaining code quality",
            "Legacy infrastructure needs modernization"
        ],
        "responsibilities": [
            "Lead team of 10+ engineers",
            "Drive platform modernization",
            "Establish engineering best practices"
        ],
    }


@pytest.fixture
def sample_master_cv_bullets():
    """Sample master CV bullets for testing."""
    return [
        {
            "text": "Led team of 12 engineers to deliver platform migration reducing costs by 40%",
            "role_id": "01_seven_one_entertainment",
        },
        {
            "text": "Built Kubernetes infrastructure handling 10M daily requests with 99.99% uptime",
            "role_id": "01_seven_one_entertainment",
        },
        {
            "text": "Implemented CI/CD pipeline reducing deployment time from hours to minutes",
            "role_id": "02_clary_business",
        },
        {
            "text": "Mentored 5 engineers to senior level, achieving 100% promotion rate",
            "role_id": "01_seven_one_entertainment",
        },
        {
            "text": "Architected event-driven microservices using AWS Lambda and EventBridge",
            "role_id": "02_clary_business",
        },
    ]


@pytest.fixture
def sample_taxonomy_data():
    """Sample taxonomy data for testing."""
    return {
        "target_roles": {
            "engineering_manager": {
                "display_name": "Engineering Manager",
                "max_sections": 4,
                "max_skills_per_section": 6,
                "lax_multiplier": 1.3,
                "static_competency_sections": {
                    "section_1": {
                        "name": "Technical Leadership",
                        "description": "Leading teams and technical initiatives"
                    },
                    "section_2": {
                        "name": "People Management",
                        "description": "Team building and mentoring"
                    },
                    "section_3": {
                        "name": "Cloud & Platform",
                        "description": "AWS, Kubernetes, infrastructure"
                    },
                    "section_4": {
                        "name": "Delivery & Process",
                        "description": "Agile, CI/CD, quality"
                    }
                },
                "sections": [
                    {
                        "name": "Technical Leadership",
                        "priority": 1,
                        "description": "Leadership",
                        "skills": ["Technical Leadership", "Team Building", "Mentoring"],
                        "jd_signals": ["lead", "team", "technical"]
                    },
                    {
                        "name": "Cloud & Platform",
                        "priority": 2,
                        "description": "Cloud",
                        "skills": ["AWS", "Kubernetes", "Docker", "Terraform"],
                        "jd_signals": ["aws", "kubernetes", "cloud"]
                    },
                    {
                        "name": "Delivery & Process",
                        "priority": 3,
                        "description": "Delivery",
                        "skills": ["Agile", "CI/CD"],
                        "jd_signals": ["agile", "ci/cd"]
                    },
                    {
                        "name": "Architecture",
                        "priority": 4,
                        "description": "Architecture",
                        "skills": ["Microservices", "Event-Driven Architecture"],
                        "jd_signals": ["architecture", "microservices"]
                    }
                ]
            }
        },
        "skill_aliases": {
            "AWS": ["Amazon Web Services", "AWS"],
            "Kubernetes": ["K8s", "Kubernetes"],
        },
        "default_fallback_role": "engineering_manager"
    }


# ============================================================================
# TEST AchievementSource
# ============================================================================

class TestAchievementSource:
    """Tests for AchievementSource dataclass."""

    def test_is_exact_match_true(self):
        """Should return True for exact matches."""
        source = AchievementSource(
            bullet_text="Led team of 12 engineers",
            source_bullet="Led team of 12 engineers",
            source_role_id="01_test",
            source_role_title="Engineering Manager",
            match_confidence=1.0,
            tailoring_applied=False
        )
        assert source.is_exact_match is True

    def test_is_exact_match_false_tailored(self):
        """Should return False when tailoring was applied."""
        source = AchievementSource(
            bullet_text="Led team of 12 engineers",
            source_bullet="Managed team of 12 engineers",
            source_role_id="01_test",
            source_role_title="Engineering Manager",
            match_confidence=1.0,
            tailoring_applied=True
        )
        assert source.is_exact_match is False

    def test_is_exact_match_false_low_confidence(self):
        """Should return False for low confidence scores."""
        source = AchievementSource(
            bullet_text="Led team of 12 engineers",
            source_bullet="Led team of 12 engineers",
            source_role_id="01_test",
            source_role_title="Engineering Manager",
            match_confidence=0.85,
            tailoring_applied=False
        )
        assert source.is_exact_match is False

    def test_total_score(self):
        """Should calculate total score from breakdown."""
        source = AchievementSource(
            bullet_text="Test bullet",
            source_bullet="Test bullet",
            source_role_id="01_test",
            source_role_title="Test",
            scoring_breakdown={
                "pain_point": 2.0,
                "keyword": 0.5,
                "recency": 1.0
            }
        )
        assert source.total_score == 3.5

    def test_to_dict(self):
        """Should serialize to dict correctly."""
        source = AchievementSource(
            bullet_text="Led team",
            source_bullet="Led team",
            source_role_id="01_test",
            source_role_title="Manager",
            match_confidence=1.0,
            scoring_breakdown={"pain_point": 2.0}
        )
        result = source.to_dict()
        assert result["bullet_text"] == "Led team"
        assert result["match_confidence"] == 1.0
        assert result["is_exact_match"] is True
        assert result["total_score"] == 2.0


# ============================================================================
# TEST SkillsProvenance
# ============================================================================

class TestSkillsProvenance:
    """Tests for SkillsProvenance dataclass."""

    def test_jd_match_ratio(self):
        """Should calculate JD match ratio correctly."""
        provenance = SkillsProvenance(
            all_from_whitelist=True,
            total_skills_selected=10,
            jd_matched_skills=["AWS", "Kubernetes", "Python"],
            whitelist_only_skills=["TypeScript", "Docker"],
        )
        assert provenance.jd_match_ratio == 0.3  # 3/10

    def test_jd_match_ratio_zero_skills(self):
        """Should return 0 when no skills selected."""
        provenance = SkillsProvenance(
            all_from_whitelist=True,
            total_skills_selected=0,
            jd_matched_skills=[],
            whitelist_only_skills=[],
        )
        assert provenance.jd_match_ratio == 0.0

    def test_hallucination_prevented_count(self):
        """Should count rejected JD skills."""
        provenance = SkillsProvenance(
            all_from_whitelist=True,
            rejected_jd_skills=["Java", "React", "PHP"],
        )
        assert provenance.hallucination_prevented_count == 3

    def test_to_dict(self):
        """Should serialize to dict with calculated properties."""
        provenance = SkillsProvenance(
            all_from_whitelist=True,
            whitelist_source="master_cv",
            total_skills_selected=5,
            jd_matched_skills=["AWS", "Kubernetes"],
            whitelist_only_skills=["TypeScript"],
            rejected_jd_skills=["Java"],
            skills_by_section={"Technical": ["AWS", "Kubernetes"]}
        )
        result = provenance.to_dict()
        assert result["all_from_whitelist"] is True
        assert result["jd_match_ratio"] == 0.4  # 2/5
        assert result["hallucination_prevented_count"] == 1


# ============================================================================
# TEST CoreCompetencySection
# ============================================================================

class TestCoreCompetencySection:
    """Tests for CoreCompetencySection dataclass."""

    def test_skill_count(self):
        """Should return correct skill count."""
        section = CoreCompetencySection(
            name="Technical Leadership",
            skills=["AWS", "Kubernetes", "Docker"],
            jd_matched_count=2
        )
        assert section.skill_count == 3

    def test_jd_match_ratio(self):
        """Should calculate JD match ratio."""
        section = CoreCompetencySection(
            name="Technical Leadership",
            skills=["AWS", "Kubernetes", "Docker", "Python"],
            jd_matched_count=2
        )
        assert section.jd_match_ratio == 0.5  # 2/4

    def test_jd_match_ratio_zero_skills(self):
        """Should return 0 when no skills."""
        section = CoreCompetencySection(
            name="Empty Section",
            skills=[],
            jd_matched_count=0
        )
        assert section.jd_match_ratio == 0.0

    def test_to_markdown(self):
        """Should format as markdown correctly."""
        section = CoreCompetencySection(
            name="Technical Leadership",
            skills=["AWS", "Kubernetes", "Docker"]
        )
        result = section.to_markdown()
        assert result == "**Technical Leadership:** AWS, Kubernetes, Docker"

    def test_to_dict(self):
        """Should serialize with calculated properties."""
        section = CoreCompetencySection(
            name="Cloud & Platform",
            skills=["AWS", "Kubernetes"],
            jd_matched_count=1,
            max_skills=10
        )
        result = section.to_dict()
        assert result["name"] == "Cloud & Platform"
        assert result["skill_count"] == 2
        assert result["jd_match_ratio"] == 0.5


# ============================================================================
# TEST SelectionResult
# ============================================================================

class TestSelectionResult:
    """Tests for SelectionResult dataclass."""

    def test_met_target_exact(self):
        """Should return True when target met exactly."""
        result = SelectionResult(
            bullets_selected=6,
            target_count=6
        )
        assert result.met_target is True

    def test_met_target_one_below(self):
        """Should return True when one below target."""
        result = SelectionResult(
            bullets_selected=5,
            target_count=6
        )
        assert result.met_target is True

    def test_met_target_too_few(self):
        """Should return False when too few bullets."""
        result = SelectionResult(
            bullets_selected=4,
            target_count=6
        )
        assert result.met_target is False

    def test_to_dict(self):
        """Should serialize with calculated property."""
        result = SelectionResult(
            bullets_selected=5,
            target_count=6,
            needs_review=False,
            lowest_score_selected=3.5
        )
        result_dict = result.to_dict()
        assert result_dict["bullets_selected"] == 5
        assert result_dict["met_target"] is True


# ============================================================================
# TEST ScoringWeights
# ============================================================================

class TestScoringWeights:
    """Tests for ScoringWeights dataclass."""

    def test_default_values(self):
        """Should use correct default weights."""
        weights = ScoringWeights()
        assert weights.pain_point_match == 2.0
        assert weights.annotation_suggested == 3.0
        assert weights.keyword_match == 0.5
        assert weights.recency_current_role == 1.0

    def test_custom_values(self):
        """Should accept custom weights."""
        weights = ScoringWeights(
            pain_point_match=5.0,
            keyword_match=2.0
        )
        assert weights.pain_point_match == 5.0
        assert weights.keyword_match == 2.0

    def test_to_dict(self):
        """Should serialize all weights."""
        weights = ScoringWeights()
        result = weights.to_dict()
        assert "pain_point_match" in result
        assert "annotation_suggested" in result
        assert "keyword_match" in result


# ============================================================================
# TEST ProfileOutput V2
# ============================================================================

class TestProfileOutputV2:
    """Tests for ProfileOutput V2 fields."""

    def test_is_v2_format_true(self):
        """Should detect V2 format."""
        profile = ProfileOutput(
            generation_mode="v2",
            value_proposition="Test value prop",
            headline="Test Headline"
        )
        assert profile.is_v2_format is True

    def test_is_v2_format_false(self):
        """Should detect V1 format."""
        profile = ProfileOutput(
            generation_mode="v1",
            headline="Test Headline"
        )
        assert profile.is_v2_format is False

    def test_effective_tagline_v2(self):
        """Should return value_proposition in V2 mode."""
        profile = ProfileOutput(
            generation_mode="v2",
            value_proposition="Engineering leader with 12+ years",
            tagline="Old tagline",
            headline="Test"
        )
        assert profile.effective_tagline == "Engineering leader with 12+ years"

    def test_effective_tagline_v1(self):
        """Should return tagline in V1 mode."""
        profile = ProfileOutput(
            generation_mode="v1",
            tagline="Technology leader who builds teams",
            headline="Test"
        )
        assert profile.effective_tagline == "Technology leader who builds teams"

    def test_effective_summary_title_executive(self):
        """Should return EXECUTIVE SUMMARY for executive roles."""
        profile = ProfileOutput(
            summary_type="executive_summary",
            headline="Test"
        )
        assert profile.effective_summary_title == "EXECUTIVE SUMMARY"

    def test_effective_summary_title_professional(self):
        """Should return PROFESSIONAL SUMMARY for non-executive roles."""
        profile = ProfileOutput(
            summary_type="professional_summary",
            headline="Test"
        )
        assert profile.effective_summary_title == "PROFESSIONAL SUMMARY"

    def test_to_dict_v2_fields(self):
        """Should include V2 fields in dict when V2 mode."""
        achievement_source = AchievementSource(
            bullet_text="Test",
            source_bullet="Test",
            source_role_id="01_test",
            source_role_title="Manager"
        )
        provenance = SkillsProvenance(
            all_from_whitelist=True,
            total_skills_selected=5
        )

        profile = ProfileOutput(
            generation_mode="v2",
            value_proposition="Test value prop",
            achievement_sources=[achievement_source],
            skills_provenance=provenance,
            core_competencies_v2={"Technical": ["AWS", "Python"]},
            summary_type="professional_summary",
            headline="Test"
        )

        result = profile.to_dict()
        assert result["generation_mode"] == "v2"
        assert result["is_v2_format"] is True
        assert result["value_proposition"] == "Test value prop"
        assert "achievement_sources" in result
        assert "skills_provenance" in result
        assert "core_competencies_v2" in result
        assert result["effective_tagline"] == "Test value prop"


# ============================================================================
# TEST CoreCompetencyGeneratorV2
# ============================================================================

class TestCoreCompetencyGeneratorV2:
    """Tests for CoreCompetencyGeneratorV2 class."""

    @pytest.fixture
    def taxonomy(self, sample_taxonomy_data):
        """Create taxonomy from sample data."""
        return SkillsTaxonomy(taxonomy_data=sample_taxonomy_data)

    @pytest.fixture
    def generator(self, taxonomy, sample_skill_whitelist):
        """Create generator instance."""
        return CoreCompetencyGeneratorV2(
            role_category="engineering_manager",
            skill_whitelist=sample_skill_whitelist,
            taxonomy=taxonomy
        )

    def test_initialization(self, generator):
        """Should initialize with correct role category."""
        assert generator._role_category == "engineering_manager"
        assert len(generator._whitelist_skills) > 0

    def test_get_static_section_names(self, generator):
        """Should return 4 static section names."""
        sections = generator.get_static_section_names()
        assert len(sections) == 4
        assert "Technical Leadership" in sections
        assert "People Management" in sections
        assert "Cloud & Platform" in sections
        assert "Delivery & Process" in sections

    def test_generate_returns_dict_and_provenance(self, generator, sample_extracted_jd):
        """Should return dict of skills and provenance."""
        competencies, provenance = generator.generate(
            extracted_jd=sample_extracted_jd,
            annotations=None
        )

        assert isinstance(competencies, dict)
        assert isinstance(provenance, SkillsProvenance)
        assert len(competencies) > 0

    def test_whitelist_enforcement(self, generator, sample_extracted_jd):
        """Should only include skills from whitelist."""
        competencies, provenance = generator.generate(
            extracted_jd=sample_extracted_jd,
            annotations=None
        )

        # Verify all selected skills are in whitelist
        all_whitelist = (
            generator._skill_whitelist.get("hard_skills", []) +
            generator._skill_whitelist.get("soft_skills", [])
        )
        all_whitelist_lower = {s.lower() for s in all_whitelist}

        for section_name, skills in competencies.items():
            for skill in skills:
                assert skill.lower() in all_whitelist_lower, \
                    f"Skill '{skill}' not in whitelist (section: {section_name})"

    def test_jd_boost_scoring(self, generator, sample_extracted_jd):
        """Should prioritize JD-matched skills."""
        competencies, provenance = generator.generate(
            extracted_jd=sample_extracted_jd,
            annotations=None
        )

        # Check that JD-matched skills appear in results
        assert len(provenance.jd_matched_skills) > 0

        # Verify JD keywords boost is working (JD matched should be > 0)
        assert provenance.jd_match_ratio > 0.0

    def test_no_duplicates_across_sections(self, generator, sample_extracted_jd):
        """Should not duplicate skills across sections."""
        competencies, provenance = generator.generate(
            extracted_jd=sample_extracted_jd,
            annotations=None
        )

        all_skills = []
        for skills in competencies.values():
            all_skills.extend(skills)

        # Check for duplicates
        assert len(all_skills) == len(set(all_skills)), \
            "Found duplicate skills across sections"

    def test_provenance_all_from_whitelist(self, generator, sample_extracted_jd):
        """Should mark provenance as all_from_whitelist=True."""
        competencies, provenance = generator.generate(
            extracted_jd=sample_extracted_jd,
            annotations=None
        )

        assert provenance.all_from_whitelist is True

    def test_rejected_jd_skills(self, generator):
        """Should track rejected JD skills not in whitelist."""
        # Add JD keywords that aren't in whitelist
        extracted_jd = {
            "role_category": "engineering_manager",
            "priority_keywords": ["java", "react", "php"],  # Not in whitelist
            "technical_skills": ["kubernetes"],  # In whitelist
        }

        competencies, provenance = generator.generate(
            extracted_jd=extracted_jd,
            annotations=None
        )

        # Should have rejected non-whitelist skills
        assert len(provenance.rejected_jd_skills) >= 2  # java, react, php


# ============================================================================
# TEST VALUE_PROPOSITION_TEMPLATES
# ============================================================================

class TestValuePropositionTemplates:
    """Tests for VALUE_PROPOSITION_TEMPLATES."""

    def test_all_8_role_categories_present(self):
        """Should have templates for all 8 role categories."""
        expected_roles = [
            "senior_engineer",
            "tech_lead",
            "staff_principal_engineer",
            "engineering_manager",
            "head_of_engineering",
            "director_of_engineering",
            "vp_engineering",
            "cto"
        ]

        for role in expected_roles:
            assert role in VALUE_PROPOSITION_TEMPLATES, \
                f"Missing template for {role}"

    def test_each_template_has_required_fields(self):
        """Should have formula, examples, and emphasis for each role."""
        for role, template_data in VALUE_PROPOSITION_TEMPLATES.items():
            assert "formula" in template_data, f"{role} missing formula"
            assert "examples" in template_data, f"{role} missing examples"
            assert "emphasis" in template_data, f"{role} missing emphasis"

            # Check examples list
            assert len(template_data["examples"]) >= 3, \
                f"{role} should have at least 3 examples"

            # Check emphasis list
            assert len(template_data["emphasis"]) >= 3, \
                f"{role} should have at least 3 emphasis areas"


# ============================================================================
# TEST build_value_proposition_prompt_v2
# ============================================================================

class TestBuildValuePropositionPromptV2:
    """Tests for build_value_proposition_prompt_v2."""

    def test_includes_role_templates(self):
        """Should include role-specific templates in prompt."""
        prompt = build_value_proposition_prompt_v2(
            role_category="engineering_manager",
            candidate_achievements=["Led team of 10 engineers"],
            candidate_scope={"years_experience": 12},
            extracted_jd={"role_category": "engineering_manager"}
        )

        assert "FORMULA:" in prompt
        assert "EXAMPLES:" in prompt
        assert "EMPHASIS AREAS:" in prompt

    def test_includes_candidate_achievements(self):
        """Should include candidate achievements in prompt."""
        achievements = [
            "Led team of 10 engineers",
            "Reduced costs by 40%"
        ]
        prompt = build_value_proposition_prompt_v2(
            role_category="engineering_manager",
            candidate_achievements=achievements,
            candidate_scope={},
            extracted_jd={}
        )

        for achievement in achievements:
            assert achievement in prompt

    def test_includes_scope_indicators(self):
        """Should include scope indicators in prompt."""
        scope = {
            "years_experience": 12,
            "team_size": 25,
            "user_scale": "10M+ users"
        }
        prompt = build_value_proposition_prompt_v2(
            role_category="engineering_manager",
            candidate_achievements=[],
            candidate_scope=scope,
            extracted_jd={}
        )

        assert "12" in prompt
        assert "25" in prompt or "team" in prompt.lower()


# ============================================================================
# TEST build_key_achievement_bullets_prompt_v2
# ============================================================================

class TestBuildKeyAchievementBulletsPromptV2:
    """Tests for build_key_achievement_bullets_prompt_v2."""

    def test_includes_whitelist(self, sample_skill_whitelist, sample_master_cv_bullets, sample_extracted_jd):
        """Should include skill whitelist in prompt."""
        prompt = build_key_achievement_bullets_prompt_v2(
            master_cv_bullets=sample_master_cv_bullets,
            skill_whitelist=sample_skill_whitelist,
            extracted_jd=sample_extracted_jd,
            annotations=None,
            role_category="engineering_manager"
        )

        assert "SKILL WHITELIST" in prompt
        assert "TypeScript" in prompt
        assert "AWS" in prompt

    def test_includes_master_cv_bullets(self, sample_skill_whitelist, sample_master_cv_bullets, sample_extracted_jd):
        """Should include all master CV bullets."""
        prompt = build_key_achievement_bullets_prompt_v2(
            master_cv_bullets=sample_master_cv_bullets,
            skill_whitelist=sample_skill_whitelist,
            extracted_jd=sample_extracted_jd,
            annotations=None,
            role_category="engineering_manager"
        )

        for bullet in sample_master_cv_bullets:
            assert bullet["text"] in prompt

    def test_includes_jd_context(self, sample_skill_whitelist, sample_master_cv_bullets, sample_extracted_jd):
        """Should include JD keywords and pain points."""
        prompt = build_key_achievement_bullets_prompt_v2(
            master_cv_bullets=sample_master_cv_bullets,
            skill_whitelist=sample_skill_whitelist,
            extracted_jd=sample_extracted_jd,
            annotations=None,
            role_category="engineering_manager"
        )

        assert "JD KEYWORDS" in prompt
        assert "kubernetes" in prompt.lower()
        assert "JD PAIN POINTS" in prompt


# ============================================================================
# TEST _is_header_v2_enabled
# ============================================================================

class TestIsHeaderV2Enabled:
    """Tests for _is_header_v2_enabled function."""

    def test_returns_true_for_true(self):
        """Should return True when env var is 'true'."""
        with patch.dict('os.environ', {'USE_HEADER_V2': 'true'}):
            from src.layer6_v2.header_generator import _is_header_v2_enabled
            assert _is_header_v2_enabled() is True

    def test_returns_true_for_1(self):
        """Should return True when env var is '1'."""
        with patch.dict('os.environ', {'USE_HEADER_V2': '1'}):
            from src.layer6_v2.header_generator import _is_header_v2_enabled
            assert _is_header_v2_enabled() is True

    def test_returns_false_for_false(self):
        """Should return False when env var is 'false'."""
        with patch.dict('os.environ', {'USE_HEADER_V2': 'false'}):
            from src.layer6_v2.header_generator import _is_header_v2_enabled
            assert _is_header_v2_enabled() is False

    def test_returns_false_for_empty(self):
        """Should return False when env var is empty."""
        with patch.dict('os.environ', {'USE_HEADER_V2': ''}):
            from src.layer6_v2.header_generator import _is_header_v2_enabled
            assert _is_header_v2_enabled() is False


# ============================================================================
# TEST HeaderGenerator V2 Integration
# ============================================================================

class TestHeaderGeneratorV2Integration:
    """Tests for HeaderGenerator V2 integration."""

    @pytest.fixture
    def mock_llm(self):
        """Mock UnifiedLLM."""
        mock = MagicMock()
        mock.config = MagicMock()
        mock.config.tier = "middle"
        return mock

    @pytest.fixture
    def mock_stitched_cv(self):
        """Mock StitchedCV."""
        from src.layer6_v2.types import StitchedCV, StitchedRole

        role = StitchedRole(
            role_id="01_test",
            company="Test Corp",
            title="Engineering Manager",
            location="San Francisco, CA",
            period="2020–Present",
            bullets=[
                "Led team of 12 engineers to deliver platform migration",
                "Built Kubernetes infrastructure handling 10M daily requests",
                "Implemented CI/CD pipeline reducing deployment time by 75%"
            ]
        )

        return StitchedCV(roles=[role])

    @pytest.mark.asyncio
    async def test_v2_profile_generation_success(
        self,
        mock_llm,
        mock_stitched_cv,
        sample_extracted_jd,
        sample_skill_whitelist
    ):
        """Should generate V2 profile with all components."""
        from src.layer6_v2.header_generator import HeaderGenerator
        from src.common.unified_llm import LLMResult

        # Mock LLM responses
        async def mock_invoke(prompt, system, validate_json=False):
            if "value proposition" in system.lower():
                return LLMResult(
                    success=True,
                    content="Engineering leader with 12+ years building teams of 25+ engineers.",
                    parsed_json=None,
                    backend="mock",
                    model="mock-model",
                    tier="middle",
                    duration_ms=100
                )
            elif "achievement bullets" in system.lower():
                return LLMResult(
                    success=True,
                    content="",
                    parsed_json={
                        "selected_bullets": [
                            {
                                "bullet_text": "Led team of 12 engineers to deliver platform migration",
                                "source_bullet": "Led team of 12 engineers to deliver platform migration",
                                "source_role": "01_test",
                                "score": 8.5,
                                "score_breakdown": {"pain_point": 2.0, "keyword": 1.5},
                                "tailoring_applied": False,
                                "tailoring_changes": None
                            }
                        ],
                        "rejected_jd_skills": ["Java", "React"]
                    },
                    backend="mock",
                    model="mock-model",
                    tier="middle",
                    duration_ms=100
                )
            return LLMResult(
                success=False,
                error="Unknown prompt",
                content="",
                backend="mock",
                model="mock-model",
                tier="middle",
                duration_ms=0
            )

        with patch('src.layer6_v2.header_generator.UnifiedLLM') as MockLLM:
            MockLLM.return_value = mock_llm
            mock_llm.invoke = AsyncMock(side_effect=mock_invoke)

            with patch.dict('os.environ', {'USE_HEADER_V2': 'true'}):
                generator = HeaderGenerator(
                    skill_whitelist=sample_skill_whitelist
                )

                profile = await generator.generate_profile(
                    stitched_cv=mock_stitched_cv,
                    extracted_jd=sample_extracted_jd,
                    candidate_name="Test Candidate"
                )

                # Verify V2 mode
                assert profile.generation_mode == "v2"
                assert profile.is_v2_format is True

                # Verify components
                assert profile.value_proposition != ""
                assert len(profile.key_achievements) > 0
                assert profile.skills_provenance is not None
                assert profile.skills_provenance.all_from_whitelist is True

    @pytest.mark.asyncio
    async def test_v2_core_competencies_algorithmic(
        self,
        mock_llm,
        mock_stitched_cv,
        sample_extracted_jd,
        sample_skill_whitelist,
        sample_taxonomy_data
    ):
        """Should generate core competencies algorithmically."""
        from src.layer6_v2.header_generator import HeaderGenerator
        from src.common.unified_llm import LLMResult

        # Mock LLM responses (only for value prop and bullets, not competencies)
        async def mock_invoke(prompt, system, validate_json=False):
            if "value proposition" in system.lower():
                return LLMResult(
                    success=True,
                    content="Engineering leader",
                    parsed_json=None,
                    backend="mock",
                    model="mock-model",
                    tier="middle",
                    duration_ms=100
                )
            elif "achievement bullets" in system.lower():
                return LLMResult(
                    success=True,
                    content="",
                    parsed_json={
                        "selected_bullets": [
                            {
                                "bullet_text": "Test bullet",
                                "source_bullet": "Test bullet",
                                "source_role": "01_test",
                                "score": 5.0,
                                "score_breakdown": {},
                                "tailoring_applied": False
                            }
                        ],
                        "rejected_jd_skills": []
                    },
                    backend="mock",
                    model="mock-model",
                    tier="middle",
                    duration_ms=100
                )
            return LLMResult(
                success=False,
                error="Unknown",
                content="",
                backend="mock",
                model="mock-model",
                tier="middle",
                duration_ms=0
            )

        with patch('src.layer6_v2.header_generator.UnifiedLLM') as MockLLM:
            MockLLM.return_value = mock_llm
            mock_llm.invoke = AsyncMock(side_effect=mock_invoke)

            with patch('src.layer6_v2.header_generator.SkillsTaxonomy') as MockTaxonomy:
                mock_taxonomy = SkillsTaxonomy(taxonomy_data=sample_taxonomy_data)
                MockTaxonomy.return_value = mock_taxonomy

                with patch.dict('os.environ', {'USE_HEADER_V2': 'true'}):
                    generator = HeaderGenerator(
                        skill_whitelist=sample_skill_whitelist
                    )

                    profile = await generator.generate_profile(
                        stitched_cv=mock_stitched_cv,
                        extracted_jd=sample_extracted_jd,
                        candidate_name="Test Candidate"
                    )

                    # Verify V2 competencies
                    assert len(profile.core_competencies_v2) > 0
                    assert profile.skills_provenance is not None

                    # Verify all skills are from whitelist
                    all_whitelist = (
                        sample_skill_whitelist["hard_skills"] +
                        sample_skill_whitelist["soft_skills"]
                    )
                    all_whitelist_lower = {s.lower() for s in all_whitelist}

                    for section_skills in profile.core_competencies_v2.values():
                        for skill in section_skills:
                            assert skill.lower() in all_whitelist_lower


# ============================================================================
# TEST COVERAGE SUMMARY
# ============================================================================

"""
Test Coverage Summary:

| Component                    | Tests | Coverage |
|------------------------------|-------|----------|
| AchievementSource            | 5     | ✅       |
| SkillsProvenance             | 4     | ✅       |
| CoreCompetencySection        | 5     | ✅       |
| SelectionResult              | 4     | ✅       |
| ScoringWeights               | 3     | ✅       |
| ProfileOutput V2             | 7     | ✅       |
| CoreCompetencyGeneratorV2    | 8     | ✅       |
| VALUE_PROPOSITION_TEMPLATES  | 2     | ✅       |
| build_value_proposition...   | 3     | ✅       |
| build_key_achievement...     | 3     | ✅       |
| _is_header_v2_enabled        | 4     | ✅       |
| HeaderGenerator V2           | 2     | ✅       |

Total: 50 tests covering all V2 components
"""
