"""
Tests for Persona-Enhanced Header Generation.

These tests verify that:
1. HeaderGenerator loads and uses persona data
2. Fallback profiles work for all 8 roles
3. Profile generation integrates persona correctly
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List

from src.layer6_v2.header_generator import (
    HeaderGenerator,
    _load_role_persona,
)
from src.layer6_v2.types import StitchedCV, StitchedRole
from src.layer1_4.claude_jd_extractor import RoleCategory


# ===== FIXTURES =====

@pytest.fixture
def sample_stitched_cv() -> StitchedCV:
    """Create a sample stitched CV for testing."""
    return StitchedCV(
        roles=[
            StitchedRole(
                role_id="role_1",
                title="Engineering Manager",
                company="TechCorp",
                location="San Francisco, CA",
                period="2020-Present",
                bullets=[
                    "Led team of 15 engineers to deliver platform migration",
                    "Reduced deployment time by 75% through CI/CD improvements",
                    "Scaled infrastructure to handle 10M daily requests",
                    "Built engineering culture that reduced attrition from 25% to 8%",
                    "Delivered $2M annual savings through cloud optimization",
                ],
            ),
            StitchedRole(
                role_id="role_2",
                title="Senior Engineer",
                company="StartupCo",
                location="New York, NY",
                period="2017-2020",
                bullets=[
                    "Architected microservices platform serving 5M users",
                    "Mentored junior engineers on best practices",
                    "Improved system reliability to 99.9% uptime",
                ],
            ),
        ]
    )


@pytest.fixture
def sample_extracted_jd() -> Dict:
    """Create a sample extracted JD for testing."""
    return {
        "title": "Engineering Manager",
        "role_category": "engineering_manager",
        "top_keywords": ["leadership", "team building", "agile", "CI/CD"],
        "technical_skills": ["Python", "AWS", "Kubernetes"],
        "responsibilities": [
            "Lead engineering team",
            "Drive technical decisions",
            "Build high-performing culture",
        ],
        "pain_points": [
            "Need to scale the team",
            "Improve delivery velocity",
        ],
    }


@pytest.fixture
def sample_candidate_data() -> Dict:
    """Create sample candidate data for testing."""
    return {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1-555-0100",
        "linkedin": "linkedin.com/in/johndoe",
        "location": "San Francisco, CA",
        "education": [{"degree": "BS Computer Science", "school": "MIT", "year": "2015"}],
        "certifications": ["AWS Solutions Architect"],
        "languages": ["English", "Spanish"],
    }


@pytest.fixture
def skill_whitelist() -> Dict[str, List[str]]:
    """Create sample skill whitelist."""
    return {
        "hard_skills": ["Python", "AWS", "Kubernetes", "CI/CD", "Microservices"],
        "soft_skills": ["Leadership", "Team Building", "Communication"],
    }


# ===== TESTS: Fallback Profile Generation =====

class TestFallbackProfileAllRoles:
    """Test that fallback profiles work for all 8 roles."""

    @pytest.mark.parametrize("role", [r.value for r in RoleCategory])
    def test_fallback_profile_generates_for_role(
        self, role, sample_stitched_cv, skill_whitelist
    ):
        """Fallback profile should generate successfully for each role."""
        generator = HeaderGenerator(skill_whitelist=skill_whitelist)

        profile = generator._generate_fallback_profile(
            stitched_cv=sample_stitched_cv,
            role_category=role,
            candidate_name="Test Candidate",
            job_title=f"Test {role.replace('_', ' ').title()}",
            regional_variant="us_eu",
        )

        assert profile is not None, f"Fallback profile should generate for {role}"
        assert profile.headline, f"Fallback headline should exist for {role}"
        assert profile.tagline, f"Fallback tagline should exist for {role}"
        assert len(profile.key_achievements) >= 3, f"Should have at least 3 achievements for {role}"
        assert len(profile.core_competencies) >= 4, f"Should have at least 4 competencies for {role}"

    @pytest.mark.parametrize("role", [r.value for r in RoleCategory])
    def test_fallback_tagline_is_third_person(self, role, sample_stitched_cv, skill_whitelist):
        """Fallback taglines should be in third-person (no I/my/you)."""
        generator = HeaderGenerator(skill_whitelist=skill_whitelist)

        profile = generator._generate_fallback_profile(
            stitched_cv=sample_stitched_cv,
            role_category=role,
            candidate_name="Test Candidate",
            job_title="Test Role",
        )

        tagline_lower = profile.tagline.lower()
        assert " i " not in f" {tagline_lower} ", f"Tagline for {role} should not contain 'I'"
        assert " my " not in f" {tagline_lower} ", f"Tagline for {role} should not contain 'my'"
        assert " you " not in f" {tagline_lower} ", f"Tagline for {role} should not contain 'you'"

    def test_vp_engineering_fallback_exists(self, sample_stitched_cv, skill_whitelist):
        """VP Engineering should have a dedicated fallback profile."""
        generator = HeaderGenerator(skill_whitelist=skill_whitelist)

        profile = generator._generate_fallback_profile(
            stitched_cv=sample_stitched_cv,
            role_category="vp_engineering",
            candidate_name="Test VP",
            job_title="VP Engineering",
        )

        # VP Engineering tagline should mention scale or operational excellence
        tagline_lower = profile.tagline.lower()
        assert "scale" in tagline_lower or "operational" in tagline_lower or "strategic" in tagline_lower, \
            "VP Engineering tagline should reflect VP-level focus"


# ===== TESTS: Persona Loading in HeaderGenerator =====

class TestHeaderGeneratorPersonaLoading:
    """Test that HeaderGenerator correctly loads and uses persona data."""

    def test_load_role_persona_returns_dict(self):
        """_load_role_persona should return a dict."""
        persona = _load_role_persona("engineering_manager")
        assert isinstance(persona, dict)
        assert "identity_statement" in persona

    def test_load_role_persona_for_vp_engineering(self):
        """VP Engineering persona should load correctly."""
        persona = _load_role_persona("vp_engineering")
        assert persona, "VP Engineering persona should exist"
        assert "engineering executive" in persona.get("identity_statement", "").lower(), \
            "VP Engineering identity should mention executive"


# ===== TESTS: Prompt Building with Persona =====

class TestPromptBuildingWithPersona:
    """Test that prompts are correctly built with persona data."""

    @patch("src.layer6_v2.header_generator.create_tracked_llm")
    def test_generate_profile_llm_loads_persona(
        self,
        mock_create_llm,
        sample_stitched_cv,
        sample_extracted_jd,
        skill_whitelist,
    ):
        """_generate_profile_llm should load and use persona data."""
        # Create mock LLM that returns a valid response
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.headline = "Test Headline | 10+ Years"
        mock_response.tagline = "Test tagline for the role."
        mock_response.key_achievements = ["Achievement 1", "Achievement 2", "Achievement 3", "Achievement 4", "Achievement 5"]
        mock_response.core_competencies = ["Skill 1", "Skill 2", "Skill 3", "Skill 4", "Skill 5", "Skill 6"]
        mock_response.highlights_used = ["metric 1"]
        mock_response.keywords_integrated = ["keyword 1"]
        mock_response.exact_title_used = "Engineering Manager"
        mock_response.answers_who = True
        mock_response.answers_what_problems = True
        mock_response.answers_proof = True
        mock_response.answers_why_you = True

        mock_llm.with_structured_output.return_value.invoke.return_value = mock_response
        mock_create_llm.return_value = mock_llm

        generator = HeaderGenerator(skill_whitelist=skill_whitelist)

        # This should not raise and should load persona internally
        profile = generator.generate_profile(
            stitched_cv=sample_stitched_cv,
            extracted_jd=sample_extracted_jd,
            candidate_name="Test Candidate",
        )

        assert profile is not None
        assert profile.headline


# ===== TESTS: Role-Specific Competencies =====

class TestRoleSpecificCompetencies:
    """Test that competencies are role-appropriate."""

    def test_em_competencies_include_people_skills(self, sample_stitched_cv, skill_whitelist):
        """Engineering Manager fallback should have people-focused competencies."""
        generator = HeaderGenerator(skill_whitelist=skill_whitelist)

        profile = generator._generate_fallback_profile(
            stitched_cv=sample_stitched_cv,
            role_category="engineering_manager",
            candidate_name="Test EM",
            job_title="Engineering Manager",
        )

        competencies_lower = [c.lower() for c in profile.core_competencies]
        people_keywords = ["team", "people", "leadership", "development", "management"]

        has_people_focus = any(
            any(kw in comp for kw in people_keywords)
            for comp in competencies_lower
        )
        assert has_people_focus, "EM competencies should include people-focused skills"

    def test_staff_competencies_include_technical_skills(self, sample_stitched_cv, skill_whitelist):
        """Staff Engineer fallback should have technical competencies."""
        generator = HeaderGenerator(skill_whitelist=skill_whitelist)

        profile = generator._generate_fallback_profile(
            stitched_cv=sample_stitched_cv,
            role_category="staff_principal_engineer",
            candidate_name="Test Staff",
            job_title="Staff Engineer",
        )

        competencies_lower = [c.lower() for c in profile.core_competencies]
        tech_keywords = ["architecture", "system", "technical", "design", "code"]

        has_tech_focus = any(
            any(kw in comp for kw in tech_keywords)
            for comp in competencies_lower
        )
        assert has_tech_focus, "Staff competencies should include technical skills"

    def test_cto_competencies_include_vision(self, sample_stitched_cv, skill_whitelist):
        """CTO fallback should have vision/strategy competencies."""
        generator = HeaderGenerator(skill_whitelist=skill_whitelist)

        profile = generator._generate_fallback_profile(
            stitched_cv=sample_stitched_cv,
            role_category="cto",
            candidate_name="Test CTO",
            job_title="CTO",
        )

        competencies_lower = [c.lower() for c in profile.core_competencies]
        vision_keywords = ["vision", "strategy", "executive", "transformation", "board"]

        has_vision_focus = any(
            any(kw in comp for kw in vision_keywords)
            for comp in competencies_lower
        )
        assert has_vision_focus, "CTO competencies should include vision/strategy skills"


# ===== TESTS: Years Experience Calculation =====

class TestYearsExperienceCalculation:
    """Test years of experience calculation."""

    def test_calculates_years_from_periods(self, sample_stitched_cv, skill_whitelist):
        """Should calculate years from role periods."""
        generator = HeaderGenerator(skill_whitelist=skill_whitelist)
        years = generator._calculate_years_experience(sample_stitched_cv)

        # 2017-Present should be ~7+ years
        assert years >= 5, "Should calculate at least 5 years"
        assert years <= 15, "Should not calculate more than 15 years for this CV"

    def test_returns_default_for_empty_cv(self, skill_whitelist):
        """Should return default 10 years for empty CV."""
        generator = HeaderGenerator(skill_whitelist=skill_whitelist)
        empty_cv = StitchedCV(roles=[])
        years = generator._calculate_years_experience(empty_cv)

        assert years == 10, "Should return default 10 years for empty CV"


# ===== TESTS: Metrics Extraction =====

class TestMetricsExtraction:
    """Test metrics extraction from bullets."""

    def test_extracts_percentages(self, skill_whitelist):
        """Should extract percentage metrics from bullets."""
        generator = HeaderGenerator(skill_whitelist=skill_whitelist)
        bullets = [
            "Reduced deployment time by 75%",
            "Improved test coverage to 95%",
        ]
        metrics = generator._extract_metrics_from_bullets(bullets)

        assert any("75%" in m for m in metrics), "Should extract 75%"
        assert any("95%" in m for m in metrics), "Should extract 95%"

    def test_extracts_team_sizes(self, skill_whitelist):
        """Should extract team size metrics from bullets."""
        generator = HeaderGenerator(skill_whitelist=skill_whitelist)
        bullets = [
            "Led team of 15 engineers",
            "Managed 50 engineers across 5 teams",
        ]
        metrics = generator._extract_metrics_from_bullets(bullets)

        assert any("15" in m and "engineer" in m.lower() for m in metrics) or \
               any("50" in m and "engineer" in m.lower() for m in metrics), \
            "Should extract team size metrics"
