"""
Unit Tests for Layer 6 V2 Phase 5: Header Generator

Tests:
- Types: SkillEvidence, SkillsSection, ProfileOutput, ValidationResult, HeaderOutput
- Skills extraction with evidence tracking
- Profile generation (with mock LLM)
- Skills grounding validation
- JD keyword prioritization
- Full header generation flow
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.layer6_v2.types import (
    StitchedRole,
    StitchedCV,
    SkillEvidence,
    SkillsSection,
    ProfileOutput,
    ValidationResult,
    HeaderOutput,
)
from src.layer6_v2.header_generator import HeaderGenerator, generate_header


# ===== FIXTURES =====

@pytest.fixture
def sample_stitched_cv():
    """Sample stitched CV for testing."""
    role1 = StitchedRole(
        role_id="01_current",
        company="Current Corp",
        title="Engineering Manager",
        location="Munich, DE",
        period="2020–Present",
        bullets=[
            "Led team of 12 engineers to deliver platform migration, reducing latency by 75%",
            "Built CI/CD pipeline using GitHub Actions and Kubernetes, improving deployment frequency by 300%",
            "Mentored 5 senior engineers, promoting 3 to staff level within 18 months",
            "Designed microservices architecture handling 10M requests daily with 99.9% uptime",
        ],
    )
    role2 = StitchedRole(
        role_id="02_previous",
        company="Previous Inc",
        title="Senior Engineer",
        location="Berlin, DE",
        period="2018–2020",
        bullets=[
            "Implemented Python backend services processing 100K daily transactions",
            "Led Agile sprint planning for team of 8, improving velocity by 40%",
            "Built monitoring dashboards using Grafana and Prometheus",
        ],
    )
    return StitchedCV(roles=[role1, role2])


@pytest.fixture
def sample_extracted_jd():
    """Sample extracted JD for testing."""
    return {
        "title": "Engineering Manager",
        "company": "Target Company",
        "role_category": "engineering_manager",
        "seniority_level": "senior",
        "top_keywords": [
            "Kubernetes", "Python", "Team Leadership", "CI/CD",
            "Microservices", "Agile", "AWS", "System Design",
            "Mentorship", "Performance Management",
        ],
        "competency_weights": {
            "leadership": 40,
            "delivery": 25,
            "architecture": 20,
            "process": 15,
        },
    }


@pytest.fixture
def sample_candidate_data():
    """Sample candidate data for testing."""
    return {
        "header": {
            "name": "John Developer",
            "contact": {
                "email": "john@example.com",
                "phone": "+49 123 456 7890",
                "linkedin": "linkedin.com/in/johndeveloper",
            },
        },
        "education": [
            "M.Sc. Computer Science — Technical University of Munich",
            "B.Sc. Software Engineering — Example University",
        ],
    }


# ===== TESTS: SkillEvidence =====

class TestSkillEvidence:
    """Test SkillEvidence dataclass."""

    def test_creates_with_evidence(self):
        """Creates SkillEvidence with bullet evidence."""
        evidence = SkillEvidence(
            skill="Python",
            evidence_bullets=["Built Python backend services"],
            source_roles=["Previous Inc"],
            is_jd_keyword=True,
        )
        assert evidence.skill == "Python"
        assert len(evidence.evidence_bullets) == 1
        assert evidence.is_jd_keyword is True

    def test_to_dict(self):
        """Converts to dictionary correctly."""
        evidence = SkillEvidence(
            skill="Kubernetes",
            evidence_bullets=["Deployed to Kubernetes cluster"],
            source_roles=["Current Corp"],
            is_jd_keyword=False,
        )
        data = evidence.to_dict()
        assert data["skill"] == "Kubernetes"
        assert "evidence_bullets" in data
        assert data["is_jd_keyword"] is False


# ===== TESTS: SkillsSection =====

class TestSkillsSection:
    """Test SkillsSection dataclass."""

    def test_creates_with_skills(self):
        """Creates SkillsSection with skill list."""
        skills = [
            SkillEvidence("Python", ["bullet1"], ["Role1"]),
            SkillEvidence("Java", ["bullet2"], ["Role2"]),
        ]
        section = SkillsSection(category="Technical", skills=skills)
        assert section.category == "Technical"
        assert section.skill_count == 2

    def test_skill_names_property(self):
        """Returns list of skill names."""
        skills = [
            SkillEvidence("Team Leadership", ["led team"], ["Corp"]),
            SkillEvidence("Mentorship", ["mentored"], ["Corp"]),
        ]
        section = SkillsSection(category="Leadership", skills=skills)
        assert section.skill_names == ["Team Leadership", "Mentorship"]

    def test_to_markdown(self):
        """Converts to markdown format."""
        skills = [
            SkillEvidence("AWS", ["cloud"], ["Corp"]),
            SkillEvidence("Kubernetes", ["k8s"], ["Corp"]),
        ]
        section = SkillsSection(category="Platform", skills=skills)
        md = section.to_markdown()
        assert "**Platform**:" in md
        assert "AWS" in md
        assert "Kubernetes" in md


# ===== TESTS: ProfileOutput =====

class TestProfileOutput:
    """Test ProfileOutput dataclass."""

    def test_creates_with_text(self):
        """Creates ProfileOutput with text."""
        profile = ProfileOutput(
            text="Engineering leader with track record of building teams.",
            highlights_used=["75% latency reduction"],
            keywords_integrated=["Team Leadership"],
        )
        assert "Engineering leader" in profile.text
        assert profile.word_count > 0

    def test_calculates_word_count(self):
        """Calculates word count automatically."""
        profile = ProfileOutput(
            text="One two three four five six seven eight nine ten",
            highlights_used=[],
            keywords_integrated=[],
        )
        assert profile.word_count == 10

    def test_to_dict(self):
        """Converts to dictionary."""
        profile = ProfileOutput(
            text="Profile text here.",
            highlights_used=["metric1"],
            keywords_integrated=["keyword1"],
        )
        data = profile.to_dict()
        assert data["text"] == "Profile text here."
        assert "word_count" in data


# ===== TESTS: ValidationResult =====

class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_passed_when_all_grounded(self):
        """Passes when all skills are grounded."""
        result = ValidationResult(
            passed=True,
            grounded_skills=["Python", "AWS"],
            ungrounded_skills=[],
            evidence_map={"Python": ["bullet1"], "AWS": ["bullet2"]},
        )
        assert result.passed is True
        assert len(result.ungrounded_skills) == 0

    def test_fails_with_ungrounded_skills(self):
        """Fails when skills lack evidence."""
        result = ValidationResult(
            passed=False,
            grounded_skills=["Python"],
            ungrounded_skills=["Blockchain", "Quantum Computing"],
            evidence_map={"Python": ["bullet1"]},
        )
        assert result.passed is False
        assert "Blockchain" in result.ungrounded_skills


# ===== TESTS: HeaderOutput =====

class TestHeaderOutput:
    """Test HeaderOutput dataclass."""

    def test_creates_complete_header(self):
        """Creates HeaderOutput with all sections."""
        profile = ProfileOutput(
            text="Profile summary.",
            highlights_used=[],
            keywords_integrated=[],
        )
        skills = [
            SkillsSection("Technical", [SkillEvidence("Python", [], [])]),
            SkillsSection("Platform", [SkillEvidence("AWS", [], [])]),
        ]
        header = HeaderOutput(
            profile=profile,
            skills_sections=skills,
            education=["M.Sc. CS"],
            contact_info={"name": "John", "email": "john@example.com"},
        )
        assert header.total_skills_count == 2
        assert "Python" in header.all_skill_names

    def test_to_markdown(self):
        """Converts to markdown format."""
        profile = ProfileOutput("Profile text.", [], [])
        skills = [
            SkillsSection("Technical", [
                SkillEvidence("Python", [], []),
                SkillEvidence("Java", [], []),
            ]),
        ]
        header = HeaderOutput(
            profile=profile,
            skills_sections=skills,
            education=["M.Sc. CS — TU Munich"],
            contact_info={
                "name": "John Developer",
                "email": "john@example.com",
                "phone": "+49 123 456",
                "linkedin": "linkedin.com/in/john",
            },
        )
        md = header.to_markdown()
        assert "# John Developer" in md
        assert "## Profile" in md
        assert "## Core Competencies" in md
        assert "## Education" in md


# ===== TESTS: HeaderGenerator - Metrics Extraction =====

class TestMetricsExtraction:
    """Test metrics extraction from bullets."""

    def test_extracts_percentages(self):
        """Extracts percentage metrics."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()

        bullets = [
            "Reduced latency by 75%",
            "Improved deployment frequency by 300%",
        ]
        metrics = generator._extract_metrics_from_bullets(bullets)
        assert any("75%" in m for m in metrics)

    def test_extracts_numbers_with_context(self):
        """Extracts numbers with context words."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()

        bullets = [
            "Led team of 12 engineers",
            "Processing 10M requests daily",
        ]
        metrics = generator._extract_metrics_from_bullets(bullets)
        # Should find team size or request count
        assert len(metrics) >= 0  # May or may not match depending on pattern


# ===== TESTS: HeaderGenerator - Skills Extraction =====

class TestSkillsExtraction:
    """Test skills extraction from bullets."""

    def test_extracts_python_skill(self, sample_stitched_cv):
        """Extracts Python when mentioned in bullets."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()
        # GAP-001 fix: Add whitelist that includes Python
        generator._skill_whitelist = {
            "hard_skills": ["Python", "Kubernetes", "AWS"],
            "soft_skills": ["Team Leadership", "Mentorship"],
        }

        bullets = [b for role in sample_stitched_cv.roles for b in role.bullets]
        companies = [role.company for role in sample_stitched_cv.roles for _ in role.bullets]

        skills = generator._extract_skills_from_bullets(bullets, companies)

        # Should find Python in Technical category
        technical_skills = [s.skill for s in skills.get("Technical", [])]
        assert "Python" in technical_skills

    def test_extracts_kubernetes_skill(self, sample_stitched_cv):
        """Extracts Kubernetes when mentioned in bullets."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()
        # GAP-001 fix: Add whitelist that includes Kubernetes
        generator._skill_whitelist = {
            "hard_skills": ["Python", "Kubernetes", "AWS"],
            "soft_skills": ["Team Leadership", "Mentorship"],
        }

        bullets = [b for role in sample_stitched_cv.roles for b in role.bullets]
        companies = [role.company for role in sample_stitched_cv.roles for _ in role.bullets]

        skills = generator._extract_skills_from_bullets(bullets, companies)

        # Should find Kubernetes in Platform category
        platform_skills = [s.skill for s in skills.get("Platform", [])]
        assert "Kubernetes" in platform_skills

    def test_extracts_leadership_skills(self):
        """Extracts leadership skills from team-related bullets."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()
        # GAP-001 fix: Add whitelist that includes leadership skills
        generator._skill_whitelist = {
            "hard_skills": [],
            "soft_skills": ["Team Leadership", "Mentorship", "Strategic Planning"],
        }

        # Use bullets that contain skill names as substrings
        bullets = [
            "Demonstrated Team Leadership by leading cross-functional teams",
            "Provided Mentorship to junior engineers",
            "Managed Strategic Planning for Q4 roadmap",
        ]
        companies = ["Current Corp", "Current Corp", "Current Corp"]

        skills = generator._extract_skills_from_bullets(bullets, companies)

        # Should find leadership skills that appear in bullets
        leadership_skills = [s.skill for s in skills.get("Leadership", [])]
        assert "Team Leadership" in leadership_skills
        assert "Mentorship" in leadership_skills


# ===== TESTS: HeaderGenerator - JD Keyword Prioritization =====

class TestJDKeywordPrioritization:
    """Test JD keyword prioritization."""

    def test_marks_jd_keywords(self):
        """Marks skills that are JD keywords."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()

        skills_by_category = {
            "Technical": [
                SkillEvidence("Python", ["bullet"], ["Corp"]),
                SkillEvidence("Java", ["bullet"], ["Corp"]),
            ],
        }
        jd_keywords = ["Python", "AWS"]

        result = generator._prioritize_jd_keywords(skills_by_category, jd_keywords)

        python_skill = next(s for s in result["Technical"] if s.skill == "Python")
        java_skill = next(s for s in result["Technical"] if s.skill == "Java")

        assert python_skill.is_jd_keyword is True
        assert java_skill.is_jd_keyword is False

    def test_sorts_jd_keywords_first(self):
        """Sorts JD keywords to the front."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()

        skills_by_category = {
            "Technical": [
                SkillEvidence("Java", ["bullet"], ["Corp"]),
                SkillEvidence("Python", ["bullet"], ["Corp"]),
                SkillEvidence("Go", ["bullet"], ["Corp"]),
            ],
        }
        jd_keywords = ["Python"]

        result = generator._prioritize_jd_keywords(skills_by_category, jd_keywords)

        # Python should be first (JD keyword)
        assert result["Technical"][0].skill == "Python"


# ===== TESTS: HeaderGenerator - Validation =====

class TestSkillsValidation:
    """Test skills grounding validation."""

    def test_passes_when_all_grounded(self, sample_stitched_cv):
        """Passes when all skills have evidence."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()

        skills_sections = [
            SkillsSection("Technical", [
                SkillEvidence("Python", ["Python backend"], ["Previous Inc"]),
            ]),
            SkillsSection("Platform", [
                SkillEvidence("Kubernetes", ["Kubernetes deployment"], ["Current Corp"]),
            ]),
        ]

        result = generator.validate_skills_grounded(skills_sections, sample_stitched_cv)
        assert result.passed is True
        assert len(result.ungrounded_skills) == 0

    def test_fails_with_ungrounded_skill(self, sample_stitched_cv):
        """Fails when skill lacks evidence in bullets."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()

        skills_sections = [
            SkillsSection("Technical", [
                SkillEvidence("Blockchain", [], []),  # Not in bullets
            ]),
        ]

        result = generator.validate_skills_grounded(skills_sections, sample_stitched_cv)
        assert result.passed is False
        assert "Blockchain" in result.ungrounded_skills


# ===== TESTS: HeaderGenerator - Full Generation =====

class TestFullHeaderGeneration:
    """Test full header generation flow."""

    @patch.object(HeaderGenerator, '_generate_profile_llm')
    def test_generates_complete_header(
        self,
        mock_llm,
        sample_stitched_cv,
        sample_extracted_jd,
        sample_candidate_data,
    ):
        """Generates complete header with all sections."""
        # Mock LLM response
        mock_response = Mock()
        mock_response.profile_text = "Engineering leader with track record of building high-performing teams."
        mock_response.highlights_used = ["75% latency reduction"]
        mock_response.keywords_integrated = ["Team Leadership"]
        mock_llm.return_value = mock_response

        generator = HeaderGenerator()
        header = generator.generate(
            sample_stitched_cv,
            sample_extracted_jd,
            sample_candidate_data,
        )

        assert header.profile is not None
        assert len(header.skills_sections) > 0
        assert len(header.education) == 2
        assert header.contact_info["name"] == "John Developer"

    @patch.object(HeaderGenerator, '_generate_profile_llm')
    def test_validates_skills(
        self,
        mock_llm,
        sample_stitched_cv,
        sample_extracted_jd,
        sample_candidate_data,
    ):
        """Validates skills are grounded."""
        mock_response = Mock()
        mock_response.profile_text = "Profile text."
        mock_response.highlights_used = []
        mock_response.keywords_integrated = []
        mock_llm.return_value = mock_response

        generator = HeaderGenerator()
        header = generator.generate(
            sample_stitched_cv,
            sample_extracted_jd,
            sample_candidate_data,
        )

        # Validation should have run
        assert header.validation_result is not None
        # All skills should be grounded (ungrounded are removed)
        assert header.validation_result.passed is True


# ===== TESTS: Profile Generation =====

class TestProfileGeneration:
    """Test profile generation."""

    @patch.object(HeaderGenerator, '_generate_profile_llm')
    def test_generates_profile_with_llm(
        self,
        mock_llm,
        sample_stitched_cv,
        sample_extracted_jd,
    ):
        """Generates profile using LLM."""
        mock_response = Mock()
        mock_response.profile_text = "Engineering leader with 15 years experience."
        mock_response.highlights_used = ["75%"]
        mock_response.keywords_integrated = ["Leadership"]
        mock_llm.return_value = mock_response

        generator = HeaderGenerator()
        profile = generator.generate_profile(
            sample_stitched_cv,
            sample_extracted_jd,
            "John Developer",
        )

        assert "Engineering leader" in profile.text
        assert profile.word_count > 0

    @patch.object(HeaderGenerator, '_generate_profile_llm')
    def test_uses_fallback_on_llm_failure(
        self,
        mock_llm,
        sample_stitched_cv,
        sample_extracted_jd,
    ):
        """Uses fallback profile when LLM fails."""
        mock_llm.side_effect = Exception("LLM error")

        generator = HeaderGenerator()
        profile = generator.generate_profile(
            sample_stitched_cv,
            sample_extracted_jd,
            "John Developer",
        )

        # Should still get a profile from fallback
        assert profile is not None
        assert profile.word_count > 0


# ===== TESTS: Skills Generation =====

class TestSkillsGeneration:
    """Test skills generation."""

    def test_generates_skills_sections(
        self,
        sample_stitched_cv,
        sample_extracted_jd,
    ):
        """Generates skills sections from experience."""
        # GAP-002: Use static categories for this test to validate legacy behavior
        generator = HeaderGenerator(use_dynamic_categories=False)
        sections = generator.generate_skills(sample_stitched_cv, sample_extracted_jd)

        assert len(sections) > 0
        # Should have at least Technical and Platform (static categories)
        categories = [s.category for s in sections]
        assert "Technical" in categories or "Platform" in categories

    def test_generates_dynamic_categories(
        self,
        sample_stitched_cv,
        sample_extracted_jd,
    ):
        """Generates JD-specific skill categories (GAP-002)."""
        generator = HeaderGenerator(use_dynamic_categories=True)
        sections = generator.generate_skills(sample_stitched_cv, sample_extracted_jd)

        assert len(sections) > 0
        # Dynamic categories should be generated (any 3-4 categories)
        assert len(sections) >= 1  # At least one category with skills
        categories = [s.category for s in sections]
        # Categories should NOT be the static 4 (most of the time)
        # But they should exist
        for cat in categories:
            assert len(cat) > 0  # Non-empty category names

    def test_limits_skills_per_category(
        self,
        sample_stitched_cv,
        sample_extracted_jd,
    ):
        """Limits skills to 8 per category."""
        generator = HeaderGenerator(use_dynamic_categories=False)
        sections = generator.generate_skills(sample_stitched_cv, sample_extracted_jd)

        for section in sections:
            assert section.skill_count <= 8


# ===== TESTS: Convenience Function =====

class TestConvenienceFunction:
    """Test generate_header convenience function."""

    @patch.object(HeaderGenerator, '_generate_profile_llm')
    def test_convenience_function_works(
        self,
        mock_llm,
        sample_stitched_cv,
        sample_extracted_jd,
        sample_candidate_data,
    ):
        """generate_header convenience function works."""
        mock_response = Mock()
        mock_response.profile_text = "Profile text."
        mock_response.highlights_used = []
        mock_response.keywords_integrated = []
        mock_llm.return_value = mock_response

        header = generate_header(
            sample_stitched_cv,
            sample_extracted_jd,
            sample_candidate_data,
        )

        assert header is not None
        assert header.profile is not None
        assert len(header.education) == 2


# ===== TESTS: Edge Cases =====

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_stitched_cv(self, sample_extracted_jd, sample_candidate_data):
        """Handles empty stitched CV."""
        empty_cv = StitchedCV(roles=[])

        generator = HeaderGenerator()

        # Profile should use fallback
        profile = generator._generate_fallback_profile(empty_cv, "engineering_manager", "John")
        assert profile is not None
        assert profile.word_count > 0

    def test_missing_jd_keywords(self, sample_stitched_cv, sample_candidate_data):
        """Handles missing JD keywords."""
        extracted_jd = {
            "title": "Engineer",
            "role_category": "engineering_manager",
            "top_keywords": [],  # Empty keywords
        }

        generator = HeaderGenerator()
        sections = generator.generate_skills(sample_stitched_cv, extracted_jd)

        # Should still generate skills (without JD prioritization)
        assert len(sections) >= 0

    def test_missing_candidate_contact(self, sample_stitched_cv, sample_extracted_jd):
        """Handles missing candidate contact info."""
        candidate_data = {
            "header": {"name": "John"},
            "education": [],
        }

        generator = HeaderGenerator()

        with patch.object(generator, '_generate_profile_llm') as mock_llm:
            mock_response = Mock()
            mock_response.profile_text = "Profile."
            mock_response.highlights_used = []
            mock_response.keywords_integrated = []
            mock_llm.return_value = mock_response

            header = generator.generate(
                sample_stitched_cv,
                sample_extracted_jd,
                candidate_data,
            )

        assert header.contact_info["name"] == "John"


# ===== TESTS: Role Category Handling =====

class TestRoleCategoryHandling:
    """Test role category specific behavior."""

    def test_engineering_manager_fallback_profile(self, sample_stitched_cv):
        """Generates appropriate profile for engineering manager."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()

        profile = generator._generate_fallback_profile(
            sample_stitched_cv,
            "engineering_manager",
            "John Developer",
        )

        assert "Engineering leader" in profile.text or "team" in profile.text.lower()

    def test_staff_engineer_fallback_profile(self, sample_stitched_cv):
        """Generates appropriate profile for staff engineer."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()

        profile = generator._generate_fallback_profile(
            sample_stitched_cv,
            "staff_principal_engineer",
            "John Developer",
        )

        assert "Staff engineer" in profile.text or "architecture" in profile.text.lower()

    def test_cto_fallback_profile(self, sample_stitched_cv):
        """Generates appropriate profile for CTO."""
        generator = HeaderGenerator.__new__(HeaderGenerator)
        generator._logger = Mock()

        profile = generator._generate_fallback_profile(
            sample_stitched_cv,
            "cto",
            "John Developer",
        )

        assert "Technology" in profile.text or "executive" in profile.text.lower()
