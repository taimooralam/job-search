"""
Unit tests for STAR format enforcement (GAP-005).

Tests the STAR validation, correction prompts, and retry logic
that ensures all CV bullets follow the STAR format.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.layer6_v2.role_qa import RoleQA
from src.layer6_v2.types import (
    GeneratedBullet,
    RoleBullets,
    STARResult,
)
from src.layer6_v2.prompts.role_generation import (
    STAR_CORRECTION_SYSTEM_PROMPT,
    build_star_correction_user_prompt,
)


# ===== STAR Format Detection Tests =====

class TestSTARSituationDetection:
    """Tests for situation/challenge opener detection."""

    @pytest.fixture
    def qa(self):
        return RoleQA()

    @pytest.mark.parametrize("bullet,expected", [
        ("Facing 30% outage increase, led migration...", True),
        ("To address team scaling challenges, established...", True),
        ("Responding to customer churn, architected...", True),
        ("Given budget constraints, optimized...", True),
        ("When performance degraded, implemented...", True),
        ("After acquisition announcement, integrated...", True),
        ("Amid rapid growth, designed scalable...", True),
        ("Following security audit, remediated...", True),
        ("Recognizing technical debt, refactored...", True),
        ("Confronted with legacy systems, modernized...", True),
        # Negative cases
        ("Led migration to microservices...", False),
        ("Improved system reliability by 50%", False),
        ("Managed team of 10 engineers", False),
        ("Architected cloud-native platform", False),
    ])
    def test_detects_situation_openers(self, qa, bullet, expected):
        """Verifies detection of STAR situation opener phrases."""
        assert qa._has_situation(bullet) == expected


class TestSTARResultDetection:
    """Tests for result/outcome detection."""

    @pytest.fixture
    def qa(self):
        return RoleQA()

    @pytest.mark.parametrize("bullet,expected", [
        ("...achieving 75% incident reduction", True),
        ("...resulting in 20% cost savings", True),
        ("...delivering $1M annual savings", True),
        ("...enabling 50% faster deployments", True),
        ("...improving latency by 40%", True),
        ("...reducing errors by 90%", True),
        ("...growing team from 5 to 15 engineers", True),
        ("Deployed to 1000 users", True),  # Has user count pattern
        # Negative cases - no metrics or result indicators
        ("Led migration to microservices architecture", False),
        ("Managed engineering team", False),
    ])
    def test_detects_result_indicators(self, qa, bullet, expected):
        """Verifies detection of quantified results."""
        assert qa._has_result(bullet) == expected


class TestSTARActionWithSkillDetection:
    """Tests for action with skill/technology detection."""

    @pytest.fixture
    def qa(self):
        return RoleQA()

    @pytest.mark.parametrize("bullet,expected", [
        ("...using AWS Lambda and EventBridge...", True),
        ("...with Kubernetes orchestration...", True),
        ("...implemented CI/CD pipeline...", True),
        ("...built microservices architecture...", True),
        ("...using Python and GraphQL...", True),
        ("...with Agile methodology...", True),
        ("...through DevOps practices...", True),
        ("...mentoring junior engineers...", True),
        ("...establishing hiring pipeline...", True),
        # Negative cases
        ("Led project successfully", False),
        ("Improved performance significantly", False),
        ("Managed large initiative", False),
    ])
    def test_detects_action_with_skills(self, qa, bullet, expected):
        """Verifies detection of actions with specific skills."""
        assert qa._has_action_with_skill(bullet) == expected


# ===== STAR Validation Tests =====

class TestSTARFormatValidation:
    """Tests for full STAR format validation."""

    @pytest.fixture
    def qa(self):
        return RoleQA()

    def test_passes_complete_star_bullets(self, qa):
        """Bullets with all STAR elements should pass."""
        bullets = [
            GeneratedBullet(
                text="Facing 30% annual outage increase, led 12-month migration to event-driven microservices using AWS Lambda, achieving 75% incident reduction",
                source_text="Led microservices migration, reduced incidents by 75%",
            ),
            GeneratedBullet(
                text="To address team scaling challenges, established engineering hiring pipeline interviewing 50+ candidates, growing team from 5 to 15 engineers",
                source_text="Built hiring pipeline, grew team from 5 to 15",
            ),
        ]
        role_bullets = RoleBullets(
            role_id="test",
            company="TestCo",
            title="Staff Engineer",
            period="2020-2024",
            location="Remote",
            bullets=bullets,
        )

        result = qa.check_star_format(role_bullets)

        assert result.passed
        assert result.star_coverage >= 0.8
        assert result.bullets_with_star == 2
        assert result.bullets_without_star == 0

    def test_fails_non_star_bullets(self, qa):
        """Bullets missing STAR elements should be flagged."""
        bullets = [
            GeneratedBullet(
                text="Led migration to microservices architecture",  # No situation, no result
                source_text="Led microservices migration",
            ),
            GeneratedBullet(
                text="Managed team of engineers",  # No situation, no skill, no result
                source_text="Managed engineering team",
            ),
        ]
        role_bullets = RoleBullets(
            role_id="test",
            company="TestCo",
            title="Staff Engineer",
            period="2020-2024",
            location="Remote",
            bullets=bullets,
        )

        result = qa.check_star_format(role_bullets)

        assert not result.passed
        assert result.star_coverage < 0.8
        assert result.bullets_without_star == 2
        assert len(result.missing_elements) >= 2

    def test_passes_when_explicit_star_components_present(self, qa):
        """Bullets with explicit STAR components should pass even if text detection fails."""
        bullet = GeneratedBullet(
            text="Some generic text without STAR openers",
            source_text="Source achievement",
            situation="Performance degradation causing customer complaints",
            action="Implemented caching layer using Redis",
            result="Reduced latency by 50%",
        )
        role_bullets = RoleBullets(
            role_id="test",
            company="TestCo",
            title="Engineer",
            period="2020-2024",
            location="Remote",
            bullets=[bullet],
        )

        result = qa.check_star_format(role_bullets)

        assert result.passed
        assert result.bullets_with_star == 1

    def test_80_percent_threshold(self, qa):
        """Should pass if at least 80% of bullets have STAR format."""
        # All bullets must include skill keywords from the skill_indicators list:
        # 'kubernetes', 'python', 'aws', 'docker', 'terraform', 'devops', etc.
        bullets = [
            GeneratedBullet(
                text="Facing scaling issues, implemented Kubernetes orchestration, achieving 99.9% uptime",
                source_text="Implemented K8s, achieved 99.9% uptime",
            ),
            GeneratedBullet(
                text="To address security concerns, led DevOps transformation using Terraform, achieving 50% faster deployments",
                source_text="Led DevOps transformation, 50% faster deployments",
            ),
            GeneratedBullet(
                text="Given technical debt, refactored legacy codebase using Python, reducing bugs by 40%",
                source_text="Refactored legacy code, reduced bugs 40%",
            ),
            GeneratedBullet(
                text="When observability was lacking, deployed monitoring with AWS CloudWatch, improving MTTR by 60%",
                source_text="Deployed AWS monitoring, improved MTTR 60%",
            ),
            GeneratedBullet(
                text="Managed engineering projects",  # Non-STAR (20%)
                source_text="Managed projects",
            ),
        ]
        role_bullets = RoleBullets(
            role_id="test",
            company="TestCo",
            title="Staff Engineer",
            period="2020-2024",
            location="Remote",
            bullets=bullets,
        )

        result = qa.check_star_format(role_bullets)

        assert result.passed  # 80% = exactly threshold
        assert result.star_coverage == 0.8


# ===== STAR Correction Prompt Tests =====

class TestSTARCorrectionPrompt:
    """Tests for STAR correction prompt building."""

    def test_prompt_includes_all_elements(self):
        """Correction prompt should include bullet, missing elements, and source."""
        prompt = build_star_correction_user_prompt(
            failed_bullet="Led migration to microservices",
            source_text="Led 12-month migration to microservices, reducing incidents by 75%",
            missing_elements=["situation/challenge opener", "action with skill/technology"],
            role_title="Staff Engineer",
            company="TechCorp",
        )

        assert "Led migration to microservices" in prompt
        assert "situation/challenge opener" in prompt
        assert "action with skill/technology" in prompt
        assert "12-month migration" in prompt
        assert "Staff Engineer" in prompt
        assert "TechCorp" in prompt

    def test_system_prompt_has_aris_template(self):
        """System prompt should include ARIS format template (updated from STAR)."""
        assert "SITUATION" in STAR_CORRECTION_SYSTEM_PROMPT or "situation" in STAR_CORRECTION_SYSTEM_PROMPT.lower()
        assert "ACTION" in STAR_CORRECTION_SYSTEM_PROMPT or "action" in STAR_CORRECTION_SYSTEM_PROMPT.lower()
        assert "RESULT" in STAR_CORRECTION_SYSTEM_PROMPT or "result" in STAR_CORRECTION_SYSTEM_PROMPT.lower()

    def test_system_prompt_has_examples(self):
        """System prompt should include good ARIS examples (situation at end)."""
        # ARIS bullets start with action, situation at end with —addressing
        assert "Led" in STAR_CORRECTION_SYSTEM_PROMPT  # Action starts bullets
        assert "addressing" in STAR_CORRECTION_SYSTEM_PROMPT  # Situation endings


# ===== STAR Enforcement Integration Tests =====

class TestSTAREnforcementIntegration:
    """Integration tests for STAR enforcement in role generator."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM that returns STAR-formatted bullets."""
        mock = MagicMock()
        mock.invoke.return_value = MagicMock(content='''
        {
            "bullets": [
                {
                    "text": "Facing performance issues, optimized database queries using PostgreSQL indexes, achieving 50% latency reduction",
                    "source_text": "Optimized database, reduced latency 50%",
                    "source_metric": "50%",
                    "jd_keyword_used": "PostgreSQL",
                    "pain_point_addressed": null,
                    "situation": "Performance issues affecting user experience",
                    "action": "Optimized database queries using PostgreSQL indexes",
                    "result": "50% latency reduction"
                }
            ],
            "total_word_count": 15,
            "keywords_integrated": ["PostgreSQL"]
        }
        ''')
        return mock

    @pytest.fixture
    def sample_role(self):
        """Create sample role data."""
        from src.layer6_v2.cv_loader import RoleData
        return RoleData(
            id="test_role",
            company="TestCorp",
            title="Staff Engineer",
            period="2020-2024",
            location="Remote",
            industry="Technology",
            achievements=[
                "Optimized database queries, reducing latency by 50%",
                "Led team of 5 engineers",
            ],
            hard_skills=["PostgreSQL", "Python"],
            soft_skills=["Leadership"],
            is_current=True,
        )

    @pytest.fixture
    def sample_jd(self):
        """Create sample extracted JD."""
        return {
            "title": "Staff Engineer",
            "company": "TargetCo",
            "role_category": "staff_principal_engineer",
            "seniority_level": "senior",
            "top_keywords": ["PostgreSQL", "optimization"],
            "implied_pain_points": ["Performance issues"],
            "competency_weights": {"delivery": 30, "process": 20, "architecture": 30, "leadership": 20},
        }

    def test_identifies_failing_bullets(self):
        """Should correctly identify bullets that fail STAR validation."""
        from src.layer6_v2.role_generator import RoleGenerator

        # Create a generator (won't actually call LLM in this test)
        with patch('src.layer6_v2.role_generator.create_tracked_llm'):
            generator = RoleGenerator()

        # Create bullets with mixed STAR compliance
        bullets = [
            GeneratedBullet(
                text="Facing scaling issues, implemented Kubernetes, achieving 99.9% uptime",
                source_text="Implemented K8s",
            ),
            GeneratedBullet(
                text="Managed engineering team",  # Non-STAR
                source_text="Managed team",
            ),
            GeneratedBullet(
                text="Led project successfully",  # Non-STAR
                source_text="Led project",
            ),
        ]
        role_bullets = RoleBullets(
            role_id="test",
            company="TestCo",
            title="Engineer",
            period="2020",
            location="Remote",
            bullets=bullets,
        )

        qa = RoleQA()
        failing_indices = generator._identify_failing_bullets(role_bullets, qa)

        assert 0 not in failing_indices  # First bullet passes
        assert 1 in failing_indices  # Second bullet fails
        assert 2 in failing_indices  # Third bullet fails

    def test_gets_missing_star_elements(self):
        """Should correctly identify which STAR elements are missing."""
        from src.layer6_v2.role_generator import RoleGenerator

        with patch('src.layer6_v2.role_generator.create_tracked_llm'):
            generator = RoleGenerator()

        qa = RoleQA()

        # Bullet with no STAR elements
        missing = generator._get_missing_star_elements("Managed engineering team", qa)
        assert "situation/challenge opener" in missing
        assert "action with skill/technology" in missing
        assert "quantified result" in missing

        # Bullet with situation but no result
        missing = generator._get_missing_star_elements("Facing issues, led team migration", qa)
        assert "situation/challenge opener" not in missing  # Has situation
        assert "quantified result" in missing  # No result

    def test_orchestrator_uses_star_enforcement_by_default(self):
        """Orchestrator should use STAR enforcement by default."""
        from src.layer6_v2.orchestrator import CVGeneratorV2

        with patch('src.layer6_v2.orchestrator.RoleGenerator'):
            with patch('src.layer6_v2.orchestrator.CVLoader'):
                with patch('src.layer6_v2.orchestrator.HeaderGenerator'):
                    with patch('src.layer6_v2.orchestrator.CVGrader'):
                        with patch('src.layer6_v2.orchestrator.CVImprover'):
                            generator = CVGeneratorV2()

        assert generator.use_star_enforcement is True

    def test_orchestrator_can_disable_star_enforcement(self):
        """Orchestrator should allow disabling STAR enforcement."""
        from src.layer6_v2.orchestrator import CVGeneratorV2

        with patch('src.layer6_v2.orchestrator.RoleGenerator'):
            with patch('src.layer6_v2.orchestrator.CVLoader'):
                with patch('src.layer6_v2.orchestrator.HeaderGenerator'):
                    with patch('src.layer6_v2.orchestrator.CVGrader'):
                        with patch('src.layer6_v2.orchestrator.CVImprover'):
                            generator = CVGeneratorV2(use_star_enforcement=False)

        assert generator.use_star_enforcement is False


# ===== STARResult Tests =====

class TestSTARResult:
    """Tests for STARResult dataclass."""

    def test_to_dict(self):
        """STARResult should serialize correctly."""
        result = STARResult(
            passed=True,
            bullets_with_star=4,
            bullets_without_star=1,
            missing_elements=["Bullet 5: missing situation"],
            star_coverage=0.8,
        )

        d = result.to_dict()

        assert d["passed"] is True
        assert d["bullets_with_star"] == 4
        assert d["bullets_without_star"] == 1
        assert d["star_coverage"] == 0.8
        assert len(d["missing_elements"]) == 1

    def test_coverage_calculation(self):
        """Coverage should be calculated correctly."""
        result = STARResult(
            passed=True,
            bullets_with_star=8,
            bullets_without_star=2,
            missing_elements=[],
            star_coverage=0.8,
        )

        assert result.star_coverage == 0.8
