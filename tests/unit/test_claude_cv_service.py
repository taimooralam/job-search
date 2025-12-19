"""
Unit tests for Claude CV Service.

Tests the multi-agent CV generation service without making actual CLI calls.
All external dependencies (ClaudeCLI) are mocked.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from src.services.claude_cv_service import (
    ClaudeCVService,
    CVResult,
    GeneratedRole,
    GeneratedBullet,
    GeneratedProfile,
    ATSValidationResult,
    generate_cv_with_claude,
)
from src.layer6_v2.prompts.cv_generation_prompts import (
    ROLE_KEYWORDS,
    FEW_SHOT_BULLETS,
    ACRONYM_EXPANSIONS,
    build_role_bullet_prompt,
    build_profile_prompt,
    build_ats_validation_prompt,
    get_role_level_from_category,
    expand_acronym,
)


class TestRoleKeywords:
    """Tests for role-level keyword definitions."""

    def test_engineering_manager_keywords_exist(self):
        """Engineering manager keywords should be defined."""
        keywords = ROLE_KEYWORDS.get("engineering_manager")
        assert keywords is not None
        assert len(keywords) > 10
        assert "Agile" in keywords
        assert "Team Leadership" in keywords

    def test_director_keywords_exist(self):
        """Director keywords should be defined."""
        keywords = ROLE_KEYWORDS.get("director")
        assert keywords is not None
        assert "Organizational Design" in keywords
        assert "Budget Management" in keywords

    def test_cto_keywords_exist(self):
        """CTO keywords should be defined."""
        keywords = ROLE_KEYWORDS.get("cto")
        assert keywords is not None
        assert "Technology Strategy" in keywords
        assert "Board Relations" in keywords

    def test_staff_principal_keywords_exist(self):
        """Staff/Principal keywords should be defined."""
        keywords = ROLE_KEYWORDS.get("staff_principal")
        assert keywords is not None
        assert "System Design" in keywords
        assert "Architecture" in keywords


class TestFewShotBullets:
    """Tests for few-shot bullet examples."""

    def test_engineering_manager_examples_exist(self):
        """Engineering manager bullet examples should exist."""
        bullets = FEW_SHOT_BULLETS.get("engineering_manager")
        assert bullets is not None
        assert len(bullets) >= 3

    def test_bullets_contain_metrics(self):
        """Bullet examples should contain quantified metrics."""
        for role_level, bullets in FEW_SHOT_BULLETS.items():
            for bullet in bullets:
                # Check for numbers (metrics)
                has_number = any(char.isdigit() for char in bullet)
                assert has_number, f"Bullet for {role_level} lacks metrics: {bullet[:50]}..."

    def test_bullets_are_appropriate_length(self):
        """Bullets should be 25-50 words."""
        for role_level, bullets in FEW_SHOT_BULLETS.items():
            for bullet in bullets:
                word_count = len(bullet.split())
                assert 15 <= word_count <= 60, f"Bullet for {role_level} has {word_count} words"


class TestAcronymExpansions:
    """Tests for acronym expansion mapping."""

    def test_common_acronyms_defined(self):
        """Common tech acronyms should be defined."""
        assert "AWS" in ACRONYM_EXPANSIONS
        assert "CI/CD" in ACRONYM_EXPANSIONS
        assert "ML" in ACRONYM_EXPANSIONS

    def test_expansion_format(self):
        """Expansions should include both forms."""
        for acronym, expansion in ACRONYM_EXPANSIONS.items():
            # Expansion should contain the acronym
            assert acronym in expansion or acronym.lower() in expansion.lower()

    def test_expand_acronym_function(self):
        """expand_acronym should return correct expansions."""
        assert expand_acronym("AWS") == "Amazon Web Services (AWS)"
        assert expand_acronym("unknown") == "unknown"  # Returns original if not found


class TestGetRoleLevelFromCategory:
    """Tests for role category to level mapping."""

    def test_engineering_manager_mapping(self):
        """Engineering manager categories should map correctly."""
        assert get_role_level_from_category("engineering_manager") == "engineering_manager"
        assert get_role_level_from_category("senior_engineering_manager") == "engineering_manager"

    def test_director_mapping(self):
        """Director categories should map correctly."""
        assert get_role_level_from_category("director_of_engineering") == "director"
        assert get_role_level_from_category("director") == "director"

    def test_vp_mapping(self):
        """VP/Head categories should map correctly."""
        assert get_role_level_from_category("vp_engineering") == "vp_head"
        assert get_role_level_from_category("head_of_engineering") == "vp_head"

    def test_cto_mapping(self):
        """CTO categories should map correctly."""
        assert get_role_level_from_category("cto") == "cto"
        assert get_role_level_from_category("chief_technology_officer") == "cto"

    def test_unknown_defaults_to_em(self):
        """Unknown categories should default to engineering_manager."""
        assert get_role_level_from_category("unknown_role") == "engineering_manager"


class TestBuildRoleBulletPrompt:
    """Tests for role bullet prompt builder."""

    def test_prompt_includes_role_info(self):
        """Prompt should include role title and company."""
        prompt = build_role_bullet_prompt(
            role_title="Engineering Manager",
            role_company="ACME Corp",
            role_achievements=["Led team of 10"],
            persona_statement="Tech leader",
            core_strengths=["Leadership"],
            pain_points=["Scaling challenges"],
            role_level="engineering_manager",
            priority_keywords=["Agile"],
        )
        assert "Engineering Manager" in prompt
        assert "ACME Corp" in prompt

    def test_prompt_includes_cars_framework(self):
        """Prompt should include CARS framework guidance."""
        prompt = build_role_bullet_prompt(
            role_title="Director",
            role_company="Tech Inc",
            role_achievements=["Scaled team 5x"],
            persona_statement="Leader",
            core_strengths=["Strategy"],
            pain_points=["Growth"],
            role_level="director",
            priority_keywords=["Scaling"],
        )
        assert "CARS" in prompt or "Challenge" in prompt
        assert "Action" in prompt
        assert "Results" in prompt

    def test_prompt_includes_few_shot_examples(self):
        """Prompt should include few-shot examples."""
        prompt = build_role_bullet_prompt(
            role_title="Staff Engineer",
            role_company="BigTech",
            role_achievements=["Designed system"],
            persona_statement="Architect",
            core_strengths=["Architecture"],
            pain_points=["Scalability"],
            role_level="staff_principal",
            priority_keywords=["System Design"],
        )
        # Should contain at least one example metric
        assert "$" in prompt or "%" in prompt


class TestBuildProfilePrompt:
    """Tests for profile prompt builder."""

    def test_prompt_includes_persona(self):
        """Prompt should include persona statement."""
        prompt = build_profile_prompt(
            persona_statement="Visionary tech leader",
            primary_identity="Engineering Executive",
            core_strengths=["Strategy", "Leadership"],
            role_bullets_summary="Led teams...",
            priority_keywords=["Agile"],
            pain_points=["Scaling"],
            target_role_level="director",
        )
        assert "Visionary tech leader" in prompt

    def test_prompt_includes_tree_of_thoughts(self):
        """Prompt should include Tree-of-Thoughts technique."""
        prompt = build_profile_prompt(
            persona_statement="Leader",
            primary_identity="CTO",
            core_strengths=["Vision"],
            role_bullets_summary="Transformed...",
            priority_keywords=["Innovation"],
            pain_points=["Digital transformation"],
            target_role_level="cto",
        )
        assert "Metric" in prompt or "metric" in prompt
        assert "Narrative" in prompt or "narrative" in prompt
        assert "Keyword" in prompt or "keyword" in prompt


class TestBuildATSValidationPrompt:
    """Tests for ATS validation prompt builder."""

    def test_prompt_includes_cv_text(self):
        """Prompt should include CV text to validate."""
        cv_text = "# John Doe\nEngineering Leader..."
        prompt = build_ats_validation_prompt(
            cv_text=cv_text,
            must_have_keywords=["Agile", "Scrum"],
            nice_to_have_keywords=["Kubernetes"],
            target_role_level="engineering_manager",
        )
        assert "John Doe" in prompt

    def test_prompt_includes_keywords(self):
        """Prompt should include must-have and nice-to-have keywords."""
        prompt = build_ats_validation_prompt(
            cv_text="Sample CV",
            must_have_keywords=["Python", "AWS"],
            nice_to_have_keywords=["Docker"],
            target_role_level="staff_principal",
        )
        assert "Python" in prompt
        assert "AWS" in prompt
        assert "Docker" in prompt


class TestGeneratedBullet:
    """Tests for GeneratedBullet dataclass."""

    def test_bullet_creation(self):
        """Should create bullet with all fields."""
        bullet = GeneratedBullet(
            text="Led team of 12 engineers",
            keywords_used=["Team Leadership"],
            pain_point_addressed="Scaling challenges",
        )
        assert bullet.text == "Led team of 12 engineers"
        assert "Team Leadership" in bullet.keywords_used
        assert bullet.pain_point_addressed == "Scaling challenges"

    def test_bullet_defaults(self):
        """Should have sensible defaults."""
        bullet = GeneratedBullet(text="Simple bullet")
        assert bullet.keywords_used == []
        assert bullet.pain_point_addressed is None


class TestGeneratedRole:
    """Tests for GeneratedRole dataclass."""

    def test_role_creation(self):
        """Should create role with bullets."""
        bullets = [
            GeneratedBullet(text="Achievement 1"),
            GeneratedBullet(text="Achievement 2"),
        ]
        role = GeneratedRole(
            role_id="acme_em",
            company="ACME",
            title="Engineering Manager",
            period="2020-2023",
            location="NYC",
            bullets=bullets,
        )
        assert role.company == "ACME"
        assert len(role.bullets) == 2


class TestGeneratedProfile:
    """Tests for GeneratedProfile dataclass."""

    def test_profile_creation(self):
        """Should create profile with all sections."""
        profile = GeneratedProfile(
            headline="Engineering Leader",
            tagline="Building high-performing teams",
            key_achievements=["Led 50+ engineers"],
            core_competencies={"leadership": ["Team Building"]},
        )
        assert profile.headline == "Engineering Leader"
        assert len(profile.key_achievements) == 1


class TestATSValidationResult:
    """Tests for ATSValidationResult dataclass."""

    def test_ats_result_creation(self):
        """Should create ATS result with all fields."""
        result = ATSValidationResult(
            ats_score=85,
            missing_keywords={"critical": ["AWS"]},
            acronyms_to_expand=[{"term": "ML", "expansion": "Machine Learning (ML)"}],
            keyword_placement_issues=[],
            red_flags=[],
            role_level_check={"pass": True},
            fixes=[],
            summary={"overall": "Good"},
        )
        assert result.ats_score == 85
        assert "AWS" in result.missing_keywords["critical"]


class TestCVResult:
    """Tests for CVResult dataclass."""

    def test_cv_result_to_dict(self):
        """Should serialize to dictionary correctly."""
        profile = GeneratedProfile(
            headline="Leader",
            tagline="Building teams",
            key_achievements=["Achievement"],
            core_competencies={"tech": ["Python"]},
        )
        roles = [
            GeneratedRole(
                role_id="role1",
                company="ACME",
                title="EM",
                period="2020-2023",
                location="NYC",
                bullets=[GeneratedBullet(text="Bullet 1")],
            )
        ]
        result = CVResult(
            profile=profile,
            roles=roles,
            ats_validation=None,
            total_cost_usd=0.5,
            total_time_ms=5000,
            models_used={"role": "sonnet", "profile": "opus"},
            generated_at="2025-01-01T00:00:00",
        )

        d = result.to_dict()
        assert d["profile"]["headline"] == "Leader"
        assert len(d["roles"]) == 1
        assert d["metadata"]["total_cost_usd"] == 0.5


class TestClaudeCVServiceInit:
    """Tests for ClaudeCVService initialization."""

    @patch("src.services.claude_cv_service.ClaudeCLI")
    def test_service_initialization(self, mock_cli_class):
        """Service should initialize with three CLI instances."""
        mock_cli_class.return_value = MagicMock()
        service = ClaudeCVService(timeout=120)

        # Should create 3 CLI instances (role, profile, validator)
        assert mock_cli_class.call_count == 3

    @patch("src.services.claude_cv_service.ClaudeCLI")
    def test_service_tier_configuration(self, mock_cli_class):
        """Service should use correct tiers for each CLI."""
        mock_cli_class.return_value = MagicMock()
        service = ClaudeCVService()

        # Check tier arguments
        calls = mock_cli_class.call_args_list
        tiers = [call.kwargs.get("tier") for call in calls]
        assert "balanced" in tiers  # Sonnet for roles
        assert "quality" in tiers  # Opus for profile
        assert "fast" in tiers  # Haiku for validation


class TestClaudeCVServiceHelpers:
    """Tests for ClaudeCVService helper methods."""

    @patch("src.services.claude_cv_service.ClaudeCLI")
    def test_extract_priority_keywords(self, mock_cli_class):
        """Should extract keywords from JD and annotations."""
        mock_cli_class.return_value = MagicMock()
        service = ClaudeCVService()

        extracted_jd = {"top_keywords": ["Python", "AWS", "Kubernetes"]}
        jd_annotations = {
            "annotations": [
                {"requirement_type": "must_have", "matching_skill": "Agile"},
                {"requirement_type": "nice_to_have", "matching_skill": "Docker"},
            ]
        }

        keywords = service._extract_priority_keywords(extracted_jd, jd_annotations)
        assert "Python" in keywords
        assert "Agile" in keywords
        # Nice to have not included in priority
        assert len(keywords) <= 15

    @patch("src.services.claude_cv_service.ClaudeCLI")
    def test_get_must_have_keywords(self, mock_cli_class):
        """Should extract must-have keywords from annotations."""
        mock_cli_class.return_value = MagicMock()
        service = ClaudeCVService()

        jd_annotations = {
            "annotations": [
                {"requirement_type": "must_have", "matching_skill": "Python"},
                {"requirement_type": "must_have", "matching_skill": "AWS"},
                {"requirement_type": "nice_to_have", "matching_skill": "Docker"},
            ]
        }

        keywords = service._get_must_have_keywords(jd_annotations)
        assert "Python" in keywords
        assert "AWS" in keywords
        assert "Docker" not in keywords

    @patch("src.services.claude_cv_service.ClaudeCLI")
    def test_summarize_role_bullets(self, mock_cli_class):
        """Should summarize role bullets for profile generation."""
        mock_cli_class.return_value = MagicMock()
        service = ClaudeCVService()

        roles = [
            GeneratedRole(
                role_id="role1",
                company="ACME",
                title="EM",
                period="2020-2023",
                location="NYC",
                bullets=[
                    GeneratedBullet(text="Led team of 10"),
                    GeneratedBullet(text="Delivered project"),
                ],
            )
        ]

        summary = service._summarize_role_bullets(roles)
        assert "ACME" in summary
        assert "EM" in summary
        assert "Led team" in summary

    @patch("src.services.claude_cv_service.ClaudeCLI")
    def test_assemble_cv_text(self, mock_cli_class):
        """Should assemble full CV text from components."""
        mock_cli_class.return_value = MagicMock()
        service = ClaudeCVService()

        profile = GeneratedProfile(
            headline="Engineering Leader",
            tagline="Building teams",
            key_achievements=["Achievement 1"],
            core_competencies={"leadership": ["Team Building"]},
        )
        roles = [
            GeneratedRole(
                role_id="role1",
                company="ACME",
                title="EM",
                period="2020-2023",
                location="NYC",
                bullets=[GeneratedBullet(text="Led team")],
            )
        ]

        cv_text = service._assemble_cv_text(profile, roles)
        assert "Engineering Leader" in cv_text
        assert "ACME" in cv_text
        assert "Led team" in cv_text


class TestClaudeCVServiceFallbacks:
    """Tests for ClaudeCVService fallback behavior."""

    @patch("src.services.claude_cv_service.ClaudeCLI")
    def test_create_fallback_role(self, mock_cli_class):
        """Should create fallback role from raw achievements."""
        mock_cli_class.return_value = MagicMock()
        service = ClaudeCVService()

        role_data = {
            "title": "Engineer",
            "company": "Tech Inc",
            "period": "2020-2023",
            "location": "SF",
            "achievements": ["Built system", "Led project", "Improved performance"],
        }

        fallback = service._create_fallback_role(role_data)
        assert fallback.company == "Tech Inc"
        assert len(fallback.bullets) == 3
        assert fallback.bullets[0].text == "Built system"

    @patch("src.services.claude_cv_service.ClaudeCLI")
    def test_create_fallback_profile(self, mock_cli_class):
        """Should create fallback profile from persona."""
        mock_cli_class.return_value = MagicMock()
        service = ClaudeCVService()

        fallback = service._create_fallback_profile(
            persona_statement="Visionary tech leader",
            core_strengths=["Strategy", "Architecture"],
            duration_ms=100,
        )

        assert "Senior Engineering Leader" in fallback.headline
        assert len(fallback.key_achievements) > 0


@pytest.mark.asyncio
class TestClaudeCVServiceAsync:
    """Async tests for ClaudeCVService."""

    @patch("src.services.claude_cv_service.ClaudeCLI")
    async def test_generate_single_role_success(self, mock_cli_class):
        """Should generate single role successfully."""
        # Mock CLI
        mock_cli = MagicMock()
        mock_cli.invoke.return_value = MagicMock(
            success=True,
            result={
                "role_bullets": [
                    {
                        "text": "Led team of 12 engineers delivering platform",
                        "keywords_used": ["Team Leadership"],
                        "pain_point_addressed": "Scaling",
                    }
                ],
                "keyword_coverage": {"Team Leadership": 1},
            },
            cost_usd=0.05,
        )
        mock_cli_class.return_value = mock_cli

        service = ClaudeCVService()
        role = await service._generate_single_role(
            role={"title": "EM", "company": "ACME", "period": "2020-2023", "achievements": ["Led team"]},
            persona_statement="Leader",
            core_strengths=["Leadership"],
            pain_points=["Scaling"],
            role_level="engineering_manager",
            priority_keywords=["Agile"],
            annotations=[],
        )

        assert role.company == "ACME"
        assert len(role.bullets) == 1

    @patch("src.services.claude_cv_service.ClaudeCLI")
    async def test_generate_single_role_fallback_on_failure(self, mock_cli_class):
        """Should fall back on CLI failure."""
        mock_cli = MagicMock()
        mock_cli.invoke.return_value = MagicMock(
            success=False,
            error="CLI timeout",
            cost_usd=None,
        )
        mock_cli_class.return_value = mock_cli

        service = ClaudeCVService()
        role = await service._generate_single_role(
            role={"title": "EM", "company": "ACME", "period": "2020", "achievements": ["A1", "A2"]},
            persona_statement="Leader",
            core_strengths=["Leadership"],
            pain_points=["Scaling"],
            role_level="engineering_manager",
            priority_keywords=["Agile"],
            annotations=[],
        )

        # Should return fallback with original achievements
        assert role.company == "ACME"
        assert len(role.bullets) == 2
        assert role.bullets[0].text == "A1"

    @patch("src.services.claude_cv_service.ClaudeCLI")
    async def test_generate_profile_success(self, mock_cli_class):
        """Should generate profile successfully."""
        mock_cli = MagicMock()
        mock_cli.invoke.return_value = MagicMock(
            success=True,
            result={
                "headline": "Engineering Director | 15+ Years",
                "tagline": "Building high-performing teams",
                "key_achievements": ["Led 50+ engineers", "Delivered $10M savings"],
                "core_competencies": {
                    "leadership": ["Team Building", "Strategy"],
                    "technical": ["Architecture", "Cloud"],
                },
                "reasoning": {"metric_pass_summary": "Focus on scale"},
            },
            cost_usd=0.25,
        )
        mock_cli_class.return_value = mock_cli

        service = ClaudeCVService()
        profile = await service._generate_profile(
            persona_statement="Tech leader",
            primary_identity="Director",
            core_strengths=["Leadership"],
            role_bullets_summary="Led teams...",
            priority_keywords=["Agile"],
            pain_points=["Scaling"],
            role_level="director",
        )

        assert "Director" in profile.headline
        assert len(profile.key_achievements) == 2

    @patch("src.services.claude_cv_service.ClaudeCLI")
    async def test_validate_ats_success(self, mock_cli_class):
        """Should validate ATS successfully."""
        mock_cli = MagicMock()
        mock_cli.invoke.return_value = MagicMock(
            success=True,
            result={
                "ats_score": 85,
                "missing_keywords": {"critical": [], "nice_to_have": ["Docker"]},
                "acronyms_to_expand": [],
                "keyword_placement_issues": [],
                "red_flags": [],
                "role_level_check": {"pass": True, "required_found": 3},
                "fixes": [],
                "summary": {"overall": "Good"},
            },
            cost_usd=0.01,
        )
        mock_cli_class.return_value = mock_cli

        service = ClaudeCVService()
        result = await service._validate_ats(
            cv_text="Sample CV text",
            must_have_keywords=["Python", "AWS"],
            nice_to_have_keywords=["Docker"],
            role_level="engineering_manager",
        )

        assert result is not None
        assert result.ats_score == 85

    @patch("src.services.claude_cv_service.ClaudeCLI")
    async def test_validate_ats_returns_none_on_failure(self, mock_cli_class):
        """Should return None on ATS validation failure."""
        mock_cli = MagicMock()
        mock_cli.invoke.return_value = MagicMock(
            success=False,
            error="Validation failed",
            cost_usd=None,
        )
        mock_cli_class.return_value = mock_cli

        service = ClaudeCVService()
        result = await service._validate_ats(
            cv_text="Sample CV",
            must_have_keywords=["Python"],
            nice_to_have_keywords=[],
            role_level="engineering_manager",
        )

        assert result is None
