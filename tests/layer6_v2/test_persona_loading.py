"""
Tests for Role Persona Loading from role_skills_taxonomy.json.

These tests verify that:
1. All 8 role categories have valid persona data
2. Persona schema is complete (identity, voice, verbs, templates)
3. Fallback behavior when persona is missing
4. Persona data is correctly injected into prompts
"""

import pytest
from typing import Dict, List

from src.layer6_v2.header_generator import _load_role_persona
from src.layer6_v2.prompts.header_generation import (
    ROLE_SUPERPOWERS,
    build_profile_user_prompt,
    build_persona_user_prompt,
)
from src.layer1_4.jd_extractor import RoleCategory


# ===== FIXTURES =====

@pytest.fixture
def all_role_categories() -> List[str]:
    """All 8 role categories as strings."""
    return [r.value for r in RoleCategory]


@pytest.fixture
def sample_experience_bullets() -> List[str]:
    """Sample experience bullets for testing."""
    return [
        "Led team of 15 engineers to deliver platform migration",
        "Reduced deployment time by 75% through CI/CD improvements",
        "Scaled infrastructure to handle 10M daily requests",
        "Built engineering culture that reduced attrition from 25% to 8%",
        "Delivered $2M annual savings through cloud optimization",
    ]


@pytest.fixture
def sample_metrics() -> List[str]:
    """Sample metrics for testing."""
    return ["75% reduction", "10M requests", "$2M savings", "25% to 8%"]


# ===== TESTS: Persona Loading =====

class TestPersonaLoadingAllRoles:
    """Test that all 8 roles have valid persona data."""

    def test_all_role_categories_have_personas(self, all_role_categories):
        """Every role category should have a persona defined."""
        for role in all_role_categories:
            persona = _load_role_persona(role)
            assert persona, f"Role {role} should have persona data"
            assert isinstance(persona, dict), f"Persona for {role} should be a dict"

    @pytest.mark.parametrize("role", [r.value for r in RoleCategory])
    def test_persona_has_identity_statement(self, role):
        """Each persona should have an identity statement."""
        persona = _load_role_persona(role)
        assert "identity_statement" in persona, f"{role} missing identity_statement"
        assert len(persona["identity_statement"]) > 20, f"{role} identity_statement too short"

    @pytest.mark.parametrize("role", [r.value for r in RoleCategory])
    def test_persona_has_voice(self, role):
        """Each persona should have a voice description."""
        persona = _load_role_persona(role)
        assert "voice" in persona, f"{role} missing voice"
        assert len(persona["voice"]) > 10, f"{role} voice too short"

    @pytest.mark.parametrize("role", [r.value for r in RoleCategory])
    def test_persona_has_power_verbs(self, role):
        """Each persona should have power verbs."""
        persona = _load_role_persona(role)
        assert "power_verbs" in persona, f"{role} missing power_verbs"
        assert isinstance(persona["power_verbs"], list), f"{role} power_verbs should be list"
        assert len(persona["power_verbs"]) >= 5, f"{role} should have at least 5 power verbs"

    @pytest.mark.parametrize("role", [r.value for r in RoleCategory])
    def test_persona_has_tagline_templates(self, role):
        """Each persona should have tagline templates."""
        persona = _load_role_persona(role)
        assert "tagline_templates" in persona, f"{role} missing tagline_templates"
        assert isinstance(persona["tagline_templates"], list), f"{role} tagline_templates should be list"
        assert len(persona["tagline_templates"]) >= 2, f"{role} should have at least 2 templates"

    @pytest.mark.parametrize("role", [r.value for r in RoleCategory])
    def test_persona_has_metric_priorities(self, role):
        """Each persona should have metric priorities."""
        persona = _load_role_persona(role)
        assert "metric_priorities" in persona, f"{role} missing metric_priorities"
        assert isinstance(persona["metric_priorities"], list), f"{role} metric_priorities should be list"
        assert len(persona["metric_priorities"]) >= 3, f"{role} should have at least 3 metric priorities"

    @pytest.mark.parametrize("role", [r.value for r in RoleCategory])
    def test_persona_has_key_achievement_focus(self, role):
        """Each persona should have key achievement focus areas."""
        persona = _load_role_persona(role)
        assert "key_achievement_focus" in persona, f"{role} missing key_achievement_focus"
        assert isinstance(persona["key_achievement_focus"], list)
        assert len(persona["key_achievement_focus"]) >= 3

    @pytest.mark.parametrize("role", [r.value for r in RoleCategory])
    def test_persona_has_differentiators(self, role):
        """Each persona should have differentiators."""
        persona = _load_role_persona(role)
        assert "differentiators" in persona, f"{role} missing differentiators"
        assert isinstance(persona["differentiators"], list)
        assert len(persona["differentiators"]) >= 3


class TestPersonaLoadingFallback:
    """Test fallback behavior when persona is missing."""

    def test_invalid_role_returns_empty_dict(self):
        """Invalid role category should return empty dict."""
        persona = _load_role_persona("nonexistent_role")
        assert persona == {}, "Invalid role should return empty dict"

    def test_empty_string_returns_empty_dict(self):
        """Empty string should return empty dict."""
        persona = _load_role_persona("")
        assert persona == {}, "Empty string should return empty dict"


# ===== TESTS: Role Superpowers =====

class TestRoleSuperpowers:
    """Test that ROLE_SUPERPOWERS covers all 8 roles."""

    def test_all_roles_have_superpowers(self, all_role_categories):
        """Every role category should have superpowers defined."""
        for role in all_role_categories:
            assert role in ROLE_SUPERPOWERS, f"Role {role} missing from ROLE_SUPERPOWERS"
            assert len(ROLE_SUPERPOWERS[role]) >= 4, f"Role {role} should have at least 4 superpowers"

    def test_superpowers_are_strings(self, all_role_categories):
        """All superpowers should be strings."""
        for role in all_role_categories:
            for superpower in ROLE_SUPERPOWERS[role]:
                assert isinstance(superpower, str), f"Superpower in {role} should be string"
                assert len(superpower) > 3, f"Superpower in {role} should be meaningful"


# ===== TESTS: Persona Differentiation =====

class TestPersonaDifferentiation:
    """Test that personas are meaningfully different between roles."""

    def test_em_vs_staff_have_different_voices(self):
        """Engineering Manager and Staff Engineer should have different voices."""
        em_persona = _load_role_persona("engineering_manager")
        staff_persona = _load_role_persona("staff_principal_engineer")

        assert em_persona["voice"] != staff_persona["voice"], \
            "EM and Staff should have different voices"

    def test_em_vs_staff_have_different_power_verbs(self):
        """Engineering Manager and Staff Engineer should have different power verbs."""
        em_persona = _load_role_persona("engineering_manager")
        staff_persona = _load_role_persona("staff_principal_engineer")

        em_verbs = set(em_persona["power_verbs"])
        staff_verbs = set(staff_persona["power_verbs"])

        # They should have some different verbs
        assert em_verbs != staff_verbs, "EM and Staff should have different power verbs"

    def test_vp_vs_cto_have_different_identities(self):
        """VP Engineering and CTO should have different identities."""
        vp_persona = _load_role_persona("vp_engineering")
        cto_persona = _load_role_persona("cto")

        assert vp_persona["identity_statement"] != cto_persona["identity_statement"], \
            "VP and CTO should have different identity statements"

    def test_tech_lead_vs_senior_have_different_focus(self):
        """Tech Lead and Senior Engineer should have different focus areas."""
        lead_persona = _load_role_persona("tech_lead")
        senior_persona = _load_role_persona("senior_engineer")

        assert lead_persona["key_achievement_focus"] != senior_persona["key_achievement_focus"], \
            "Tech Lead and Senior should have different achievement focus"

    def test_em_voice_is_people_focused(self):
        """Engineering Manager voice should mention people/team focus."""
        em_persona = _load_role_persona("engineering_manager")
        voice = em_persona["voice"].lower()

        assert "people" in voice or "team" in voice or "delivery" in voice, \
            "EM voice should be people/team focused"

    def test_staff_voice_is_technically_focused(self):
        """Staff Engineer voice should mention technical depth."""
        staff_persona = _load_role_persona("staff_principal_engineer")
        voice = staff_persona["voice"].lower()

        assert "technical" in voice or "deep" in voice or "architect" in voice, \
            "Staff voice should be technically focused"


# ===== TESTS: Prompt Injection =====

class TestPersonaPromptInjection:
    """Test that persona data is correctly injected into prompts."""

    def test_build_profile_prompt_includes_persona_section(
        self, sample_experience_bullets, sample_metrics
    ):
        """build_profile_user_prompt should include ROLE PERSONA section when persona provided."""
        persona = _load_role_persona("engineering_manager")

        prompt = build_profile_user_prompt(
            candidate_name="Test Candidate",
            job_title="Engineering Manager",
            role_category="engineering_manager",
            top_keywords=["leadership", "team building"],
            experience_bullets=sample_experience_bullets,
            metrics=sample_metrics,
            role_persona=persona,
        )

        assert "=== ROLE PERSONA" in prompt, "Prompt should include ROLE PERSONA section"

    def test_prompt_includes_identity_statement(
        self, sample_experience_bullets, sample_metrics
    ):
        """Prompt should include the identity statement from persona."""
        persona = _load_role_persona("engineering_manager")

        prompt = build_profile_user_prompt(
            candidate_name="Test Candidate",
            job_title="Engineering Manager",
            role_category="engineering_manager",
            top_keywords=["leadership"],
            experience_bullets=sample_experience_bullets,
            metrics=sample_metrics,
            role_persona=persona,
        )

        assert "IDENTITY:" in prompt, "Prompt should include IDENTITY field"

    def test_prompt_includes_voice(
        self, sample_experience_bullets, sample_metrics
    ):
        """Prompt should include the voice from persona."""
        persona = _load_role_persona("vp_engineering")

        prompt = build_profile_user_prompt(
            candidate_name="Test Candidate",
            job_title="VP Engineering",
            role_category="vp_engineering",
            top_keywords=["leadership"],
            experience_bullets=sample_experience_bullets,
            metrics=sample_metrics,
            role_persona=persona,
        )

        assert "VOICE:" in prompt, "Prompt should include VOICE field"

    def test_prompt_includes_power_verbs(
        self, sample_experience_bullets, sample_metrics
    ):
        """Prompt should include power verbs from persona."""
        persona = _load_role_persona("cto")

        prompt = build_profile_user_prompt(
            candidate_name="Test Candidate",
            job_title="CTO",
            role_category="cto",
            top_keywords=["vision"],
            experience_bullets=sample_experience_bullets,
            metrics=sample_metrics,
            role_persona=persona,
        )

        assert "POWER VERBS" in prompt, "Prompt should include POWER VERBS"

    def test_prompt_without_persona_has_no_persona_section(
        self, sample_experience_bullets, sample_metrics
    ):
        """Prompt without persona should not have ROLE PERSONA section."""
        prompt = build_profile_user_prompt(
            candidate_name="Test Candidate",
            job_title="Engineering Manager",
            role_category="engineering_manager",
            top_keywords=["leadership"],
            experience_bullets=sample_experience_bullets,
            metrics=sample_metrics,
            role_persona=None,
        )

        assert "=== ROLE PERSONA" not in prompt, \
            "Prompt without persona should not have ROLE PERSONA section"

    def test_build_persona_prompt_includes_role_persona(
        self, sample_experience_bullets, sample_metrics
    ):
        """build_persona_user_prompt should include role persona when provided."""
        persona = _load_role_persona("director_of_engineering")

        prompt = build_persona_user_prompt(
            persona="metric",
            candidate_name="Test Candidate",
            job_title="Director of Engineering",
            role_category="director_of_engineering",
            top_keywords=["scale", "leadership"],
            experience_bullets=sample_experience_bullets,
            metrics=sample_metrics,
            role_persona=persona,
        )

        assert "=== ROLE PERSONA" in prompt, \
            "build_persona_user_prompt should include ROLE PERSONA section"


# ===== TESTS: Role Category Enum =====

class TestRoleCategoryEnum:
    """Test that RoleCategory enum has all 8 roles."""

    def test_role_category_has_8_values(self):
        """RoleCategory enum should have exactly 8 values."""
        assert len(RoleCategory) == 8, "RoleCategory should have 8 values"

    def test_vp_engineering_in_enum(self):
        """VP Engineering should be in the enum."""
        assert hasattr(RoleCategory, "VP_ENGINEERING"), "VP_ENGINEERING should be in RoleCategory"
        assert RoleCategory.VP_ENGINEERING.value == "vp_engineering"

    def test_all_expected_roles_present(self):
        """All 8 expected roles should be present."""
        expected = {
            "engineering_manager",
            "staff_principal_engineer",
            "director_of_engineering",
            "head_of_engineering",
            "vp_engineering",
            "cto",
            "tech_lead",
            "senior_engineer",
        }
        actual = {r.value for r in RoleCategory}
        assert actual == expected, f"Missing roles: {expected - actual}"
