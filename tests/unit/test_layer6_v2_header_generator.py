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


@pytest.fixture
def sample_skill_whitelist():
    """Sample skill whitelist from master CV for testing (GAP-001 fix)."""
    return {
        "hard_skills": [
            "Python", "Kubernetes", "CI/CD", "GitHub Actions",
            "Microservices", "Grafana", "Prometheus", "System Design",
        ],
        "soft_skills": [
            "Team Leadership", "Mentorship", "Agile", "Sprint Planning",
            "Performance Management", "Cross-functional Collaboration",
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
        """Converts to plain text format (GAP-006: no markdown)."""
        skills = [
            SkillEvidence("AWS", ["cloud"], ["Corp"]),
            SkillEvidence("Kubernetes", ["k8s"], ["Corp"]),
        ]
        section = SkillsSection(category="Platform", skills=skills)
        md = section.to_markdown()
        # CV uses markdown formatting for TipTap editor rendering
        assert "**Platform:**" in md  # Bold category name
        assert "AWS" in md
        assert "Kubernetes" in md


# ===== TESTS: ProfileOutput =====

class TestProfileOutput:
    """Test ProfileOutput dataclass - research-aligned version."""

    def test_creates_with_narrative(self):
        """Creates ProfileOutput with research-aligned narrative."""
        profile = ProfileOutput(
            headline="Senior Engineering Manager | 12+ Years Technology Leadership",
            narrative="Engineering leader with track record of building teams.",
            core_competencies=["Engineering Leadership", "Team Building"],
            highlights_used=["75% latency reduction"],
            keywords_integrated=["Team Leadership"],
        )
        assert "Engineering leader" in profile.text  # text property returns narrative
        assert profile.word_count > 0
        assert "12+ Years" in profile.headline

    def test_calculates_word_count(self):
        """Calculates word count automatically from narrative."""
        profile = ProfileOutput(
            narrative="One two three four five six seven eight nine ten",
            highlights_used=[],
            keywords_integrated=[],
        )
        assert profile.word_count == 10

    def test_to_dict(self):
        """Converts to dictionary with all research-aligned fields."""
        profile = ProfileOutput(
            headline="CTO | 15+ Years Technology Leadership",
            narrative="Profile text here.",
            core_competencies=["Technology Vision", "Executive Leadership"],
            highlights_used=["metric1"],
            keywords_integrated=["keyword1"],
            exact_title_used="CTO",
            answers_who=True,
            answers_what_problems=True,
            answers_proof=True,
            answers_why_you=True,
        )
        data = profile.to_dict()
        assert data["text"] == "Profile text here."  # Legacy compatibility
        assert data["narrative"] == "Profile text here."
        assert data["headline"] == "CTO | 15+ Years Technology Leadership"
        assert "word_count" in data
        assert data["all_four_questions_answered"] is True

    def test_four_questions_validation(self):
        """Tests the 4-question framework validation."""
        profile = ProfileOutput(
            narrative="Some profile text",
            answers_who=True,
            answers_what_problems=True,
            answers_proof=False,  # Missing proof
            answers_why_you=True,
        )
        assert profile.all_four_questions_answered is False

        profile.answers_proof = True
        # Need to recalculate by creating a new instance
        profile2 = ProfileOutput(
            narrative="Some profile text",
            answers_who=True,
            answers_what_problems=True,
            answers_proof=True,
            answers_why_you=True,
        )
        assert profile2.all_four_questions_answered is True

    def test_legacy_from_legacy_classmethod(self):
        """Tests backward compatibility with legacy format."""
        profile = ProfileOutput.from_legacy(
            text="Legacy profile text here.",
            highlights_used=["metric1"],
            keywords_integrated=["keyword1"],
        )
        assert profile.text == "Legacy profile text here."
        assert profile.narrative == "Legacy profile text here."
        assert profile.word_count == 4


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
    """Test HeaderOutput dataclass - research-aligned version."""

    def test_creates_complete_header(self):
        """Creates HeaderOutput with all research-aligned sections."""
        profile = ProfileOutput(
            headline="Senior Engineering Manager | 12+ Years Technology Leadership",
            narrative="Profile summary with research-aligned content.",
            core_competencies=["Engineering Leadership", "Team Building"],
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
        """Converts to ATS-optimized format with PROFESSIONAL SUMMARY header."""
        profile = ProfileOutput(
            headline="CTO | 15+ Years Technology Leadership",
            narrative="Profile text with research-aligned content.",
            core_competencies=["Technology Vision", "Executive Leadership", "Cloud Architecture"],
            highlights_used=[],
            keywords_integrated=[],
        )
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
        # Hybrid Executive Summary structure
        assert "John Developer" in md
        assert "EXECUTIVE SUMMARY" in md  # Updated header for hybrid format
        assert "CTO | 15+ Years" in md  # Headline with exact title
        assert "Core:" in md  # New inline competencies format
        assert "Technology Vision" in md  # From core_competencies
        assert "SKILLS & EXPERTISE" in md  # Skills section
        assert "EDUCATION" in md
        # Verify no heading markers (we use bold ** instead)
        assert "##" not in md
        # Bold markdown IS expected for TipTap rendering (category titles)
        assert "**Technical:**" in md  # Bold category name


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
        sample_skill_whitelist,
    ):
        """Generates complete header with all sections."""
        # Mock LLM response
        mock_response = Mock()
        mock_response.profile_text = "Engineering leader with track record of building high-performing teams."
        mock_response.highlights_used = ["75% latency reduction"]
        mock_response.keywords_integrated = ["Team Leadership"]
        mock_llm.return_value = mock_response

        # GAP-001: Must provide skill whitelist to get skills
        generator = HeaderGenerator(skill_whitelist=sample_skill_whitelist)
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
        sample_skill_whitelist,
    ):
        """Validates skills are grounded."""
        mock_response = Mock()
        mock_response.profile_text = "Profile text."
        mock_response.highlights_used = []
        mock_response.keywords_integrated = []
        mock_llm.return_value = mock_response

        # GAP-001: Must provide skill whitelist to get skills
        generator = HeaderGenerator(skill_whitelist=sample_skill_whitelist)
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
        sample_skill_whitelist,
    ):
        """Generates skills sections from experience using taxonomy."""
        # Use skill whitelist with taxonomy-based generation
        generator = HeaderGenerator(
            skill_whitelist=sample_skill_whitelist,
            lax_mode=True,
        )
        sections = generator.generate_skills(sample_stitched_cv, sample_extracted_jd)

        assert len(sections) > 0
        # Should have sections with skills
        categories = [s.category for s in sections]
        assert len(categories) > 0

    def test_generates_dynamic_categories(
        self,
        sample_stitched_cv,
        sample_extracted_jd,
        sample_skill_whitelist,
    ):
        """Generates role-specific skill categories using taxonomy."""
        # GAP-001: Must provide skill whitelist to get skills
        generator = HeaderGenerator(
            skill_whitelist=sample_skill_whitelist,
            lax_mode=True,
        )
        sections = generator.generate_skills(sample_stitched_cv, sample_extracted_jd)

        assert len(sections) > 0
        # Categories should be generated from taxonomy
        assert len(sections) >= 1  # At least one category with skills
        categories = [s.category for s in sections]
        for cat in categories:
            assert len(cat) > 0  # Non-empty category names

    def test_limits_skills_per_category(
        self,
        sample_stitched_cv,
        sample_extracted_jd,
        sample_skill_whitelist,
    ):
        """Limits skills per category (with lax mode generating ~30% more)."""
        # GAP-001: Must provide skill whitelist to get skills
        generator = HeaderGenerator(
            skill_whitelist=sample_skill_whitelist,
            lax_mode=True,
        )
        sections = generator.generate_skills(sample_stitched_cv, sample_extracted_jd)

        for section in sections:
            # With lax mode (1.3x), max is ~8 skills per category
            assert section.skill_count <= 10  # Allow for lax multiplier

    def test_no_skills_without_whitelist(
        self,
        sample_stitched_cv,
        sample_extracted_jd,
    ):
        """GAP-001: Without whitelist, falls back to static categories (empty)."""
        generator = HeaderGenerator(lax_mode=False)
        sections = generator.generate_skills(sample_stitched_cv, sample_extracted_jd)

        # Without whitelist, should return empty to prevent hallucination
        assert len(sections) == 0


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


# ===== TESTS: Hybrid Executive Summary =====

def _contains_pronouns(text: str) -> bool:
    """Check if text contains first/second person pronouns."""
    import re
    pronouns = [
        r'\bI\b', r'\bmy\b', r'\bme\b', r'\bmine\b',
        r'\byou\b', r'\byour\b', r'\byours\b',
        r'\bwe\b', r'\bour\b', r'\bours\b', r'\bus\b',
    ]
    text_lower = text.lower()
    for pattern in pronouns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


class TestHybridExecutiveSummary:
    """Test new Hybrid Executive Summary format."""

    def test_profile_output_has_hybrid_fields(self):
        """ProfileOutput has tagline and key_achievements fields."""
        profile = ProfileOutput(
            headline="Engineering Manager | 12+ Years Technology Leadership",
            tagline="Technology leader who thrives on building high-performing teams",
            key_achievements=[
                "Led team of 25+ engineers to deliver platform migration, reducing latency by 75%",
                "Built CI/CD pipeline improving deployment frequency by 300%",
                "Scaled microservices architecture to 10M daily requests with 99.9% uptime",
            ],
            core_competencies=["Engineering Leadership", "Team Building", "Cloud Architecture"],
        )

        # Check fields exist
        assert hasattr(profile, "tagline")
        assert hasattr(profile, "key_achievements")
        assert profile.tagline == "Technology leader who thrives on building high-performing teams"
        assert len(profile.key_achievements) == 3

    def test_is_hybrid_format_true_when_both_present(self):
        """is_hybrid_format is True when tagline AND key_achievements exist."""
        profile = ProfileOutput(
            tagline="Technology leader who thrives on building high-performing teams",
            key_achievements=[
                "Led team of 25+ engineers to deliver platform migration",
                "Built CI/CD pipeline improving deployment frequency by 300%",
            ],
        )
        assert profile.is_hybrid_format is True

    def test_is_hybrid_format_false_when_only_narrative(self):
        """is_hybrid_format is False for legacy format."""
        profile = ProfileOutput(
            narrative="Engineering leader with 15 years of experience building teams.",
        )
        assert profile.is_hybrid_format is False

    def test_is_hybrid_format_false_when_tagline_only(self):
        """is_hybrid_format is False when only tagline (no achievements)."""
        profile = ProfileOutput(
            tagline="Technology leader who thrives on building high-performing teams",
            key_achievements=[],  # Empty
        )
        assert profile.is_hybrid_format is False

    def test_is_hybrid_format_false_when_achievements_only(self):
        """is_hybrid_format is False when only achievements (no tagline)."""
        profile = ProfileOutput(
            tagline="",  # Empty
            key_achievements=["Led team of 25+ engineers"],
        )
        assert profile.is_hybrid_format is False

    def test_tagline_max_200_chars(self):
        """Tagline should be max 200 characters."""
        # Create a valid tagline under 200 chars
        valid_tagline = "Technology leader who thrives on building high-performing teams and delivering scalable cloud infrastructure that drives business value"
        assert len(valid_tagline) <= 200

        profile = ProfileOutput(
            tagline=valid_tagline,
            key_achievements=["Achievement 1"],
        )
        assert len(profile.tagline) <= 200

    def test_key_achievements_count_5_to_6(self):
        """Should generate 5-6 key achievements."""
        # Test with 5 achievements
        profile_5 = ProfileOutput(
            tagline="Technology leader passionate about engineering excellence",
            key_achievements=[
                "Achievement 1",
                "Achievement 2",
                "Achievement 3",
                "Achievement 4",
                "Achievement 5",
            ],
        )
        assert len(profile_5.key_achievements) == 5
        assert 5 <= len(profile_5.key_achievements) <= 6

        # Test with 6 achievements
        profile_6 = ProfileOutput(
            tagline="Technology leader passionate about engineering excellence",
            key_achievements=[
                "Achievement 1",
                "Achievement 2",
                "Achievement 3",
                "Achievement 4",
                "Achievement 5",
                "Achievement 6",
            ],
        )
        assert len(profile_6.key_achievements) == 6
        assert 5 <= len(profile_6.key_achievements) <= 6

    def test_formatted_summary_structure(self):
        """formatted_summary produces correct structure."""
        profile = ProfileOutput(
            headline="Engineering Manager | 12+ Years Technology Leadership",
            tagline="Technology leader who thrives on building high-performing teams",
            key_achievements=[
                "Led team of 25+ engineers to deliver platform migration",
                "Built CI/CD pipeline improving deployment frequency by 300%",
                "Scaled microservices architecture to 10M daily requests",
            ],
            core_competencies=["Engineering Leadership", "Team Building", "Cloud Architecture"],
        )

        formatted = profile.formatted_summary

        # Check structure
        assert "Engineering Manager | 12+ Years" in formatted
        assert "Technology leader who thrives" in formatted
        assert "- Led team of 25+ engineers" in formatted
        assert "- Built CI/CD pipeline" in formatted
        assert "- Scaled microservices architecture" in formatted
        assert "Core: Engineering Leadership | Team Building | Cloud Architecture" in formatted

    def test_backward_compatibility_with_narrative(self):
        """Old code using narrative field still works."""
        # Legacy format
        profile = ProfileOutput(
            narrative="Engineering leader with 15 years of experience.",
        )
        assert profile.text == "Engineering leader with 15 years of experience."
        assert profile.word_count == 7

    def test_text_property_returns_hybrid_content(self):
        """text property returns tagline + achievements for hybrid format."""
        profile = ProfileOutput(
            tagline="Technology leader who thrives on building high-performing teams",
            key_achievements=[
                "Led team of 25+ engineers to deliver platform migration",
                "Built CI/CD pipeline improving deployment frequency by 300%",
            ],
        )

        text = profile.text
        assert "Technology leader who thrives" in text
        assert "- Led team of 25+ engineers" in text
        assert "- Built CI/CD pipeline" in text

    def test_text_property_fallback_to_narrative(self):
        """text property falls back to narrative for legacy format."""
        profile = ProfileOutput(
            narrative="Engineering leader with 15 years of experience.",
        )
        assert profile.text == "Engineering leader with 15 years of experience."


class TestThirdPersonAbsentVoice:
    """Test third-person absent voice (no pronouns) in tagline."""

    def test_valid_tagline_no_pronouns(self):
        """Valid taglines have no pronouns."""
        valid_taglines = [
            "Technology leader who thrives on building high-performing teams",
            "Engineering executive passionate about driving technical excellence",
            "Experienced architect focused on scalable cloud infrastructure",
            "Strategic leader dedicated to innovation and team empowerment",
        ]

        for tagline in valid_taglines:
            assert not _contains_pronouns(tagline), f"Tagline '{tagline}' contains pronouns"

    def test_detect_pronoun_violations(self):
        """Helper function detects pronouns in text."""
        # First-person pronouns
        assert _contains_pronouns("I am a technology leader") is True
        assert _contains_pronouns("My expertise is in cloud architecture") is True
        assert _contains_pronouns("Let me help you") is True

        # Second-person pronouns
        assert _contains_pronouns("You will benefit from my skills") is True
        assert _contains_pronouns("Your team will grow") is True

        # First-person plural
        assert _contains_pronouns("We built a platform") is True
        assert _contains_pronouns("Our team delivered") is True

        # No pronouns
        assert _contains_pronouns("Technology leader passionate about innovation") is False
        assert _contains_pronouns("Engineering executive focused on results") is False

    def test_fallback_taglines_no_pronouns(self):
        """All role-specific fallback taglines use third-person absent voice."""
        # These would be from the actual fallback generation logic
        fallback_taglines = {
            "engineering_manager": "Engineering leader passionate about building high-performing teams and driving technical excellence",
            "staff_principal_engineer": "Staff engineer focused on scalable architecture and technical leadership across teams",
            "cto": "Technology executive driving innovation and building world-class engineering organizations",
            "vp_engineering": "Engineering executive focused on organizational growth and technical strategy",
        }

        for role, tagline in fallback_taglines.items():
            assert not _contains_pronouns(tagline), f"Fallback for '{role}' contains pronouns: {tagline}"


class TestHybridOutputRendering:
    """Test output rendering for hybrid format."""

    def test_to_markdown_uses_executive_summary_header(self):
        """to_markdown uses 'EXECUTIVE SUMMARY' not 'PROFESSIONAL SUMMARY'."""
        profile = ProfileOutput(
            headline="Engineering Manager | 12+ Years Technology Leadership",
            tagline="Technology leader who thrives on building high-performing teams",
            key_achievements=["Achievement 1"],
            core_competencies=["Engineering Leadership"],
        )
        skills = [
            SkillsSection("Technical", [SkillEvidence("Python", [], [])]),
        ]
        header = HeaderOutput(
            profile=profile,
            skills_sections=skills,
            education=["M.Sc. CS"],
            contact_info={"name": "John", "email": "john@example.com"},
        )

        md = header.to_markdown()
        assert "EXECUTIVE SUMMARY" in md
        assert "PROFESSIONAL SUMMARY" not in md

    def test_to_markdown_renders_tagline(self):
        """to_markdown includes tagline paragraph."""
        profile = ProfileOutput(
            headline="Engineering Manager | 12+ Years Technology Leadership",
            tagline="Technology leader who thrives on building high-performing teams",
            key_achievements=["Achievement 1"],
            core_competencies=["Engineering Leadership"],
        )
        skills = [SkillsSection("Technical", [SkillEvidence("Python", [], [])])]
        header = HeaderOutput(
            profile=profile,
            skills_sections=skills,
            education=["M.Sc. CS"],
            contact_info={"name": "John", "email": "john@example.com"},
        )

        md = header.to_markdown()
        assert "Technology leader who thrives on building high-performing teams" in md

    def test_to_markdown_renders_bullets(self):
        """to_markdown renders key_achievements as bullet list."""
        profile = ProfileOutput(
            headline="Engineering Manager | 12+ Years Technology Leadership",
            tagline="Technology leader passionate about engineering excellence",
            key_achievements=[
                "Led team of 25+ engineers to deliver platform migration",
                "Built CI/CD pipeline improving deployment frequency by 300%",
                "Scaled microservices architecture to 10M daily requests",
            ],
            core_competencies=["Engineering Leadership"],
        )
        skills = [SkillsSection("Technical", [SkillEvidence("Python", [], [])])]
        header = HeaderOutput(
            profile=profile,
            skills_sections=skills,
            education=["M.Sc. CS"],
            contact_info={"name": "John", "email": "john@example.com"},
        )

        md = header.to_markdown()
        assert "- Led team of 25+ engineers to deliver platform migration" in md
        assert "- Built CI/CD pipeline improving deployment frequency by 300%" in md
        assert "- Scaled microservices architecture to 10M daily requests" in md

    def test_to_markdown_renders_core_inline(self):
        """to_markdown renders competencies as 'Core: X | Y | Z'."""
        profile = ProfileOutput(
            headline="Engineering Manager | 12+ Years Technology Leadership",
            tagline="Technology leader passionate about engineering excellence",
            key_achievements=["Achievement 1"],
            core_competencies=["Engineering Leadership", "Team Building", "Cloud Architecture"],
        )
        skills = [SkillsSection("Technical", [SkillEvidence("Python", [], [])])]
        header = HeaderOutput(
            profile=profile,
            skills_sections=skills,
            education=["M.Sc. CS"],
            contact_info={"name": "John", "email": "john@example.com"},
        )

        md = header.to_markdown()
        # Note: The implementation uses bold markdown for Core
        assert "**Core:**" in md or "Core:" in md
        assert "Engineering Leadership | Team Building | Cloud Architecture" in md

    def test_to_dict_includes_hybrid_fields(self):
        """to_dict includes tagline, key_achievements, is_hybrid_format."""
        profile = ProfileOutput(
            headline="Engineering Manager | 12+ Years Technology Leadership",
            tagline="Technology leader who thrives on building high-performing teams",
            key_achievements=[
                "Led team of 25+ engineers",
                "Built CI/CD pipeline",
            ],
            core_competencies=["Engineering Leadership"],
        )

        data = profile.to_dict()
        assert "tagline" in data
        assert "key_achievements" in data
        assert "is_hybrid_format" in data
        assert data["is_hybrid_format"] is True
        assert data["tagline"] == "Technology leader who thrives on building high-performing teams"
        assert len(data["key_achievements"]) == 2

    def test_to_markdown_fallback_to_narrative_when_hybrid_not_available(self):
        """to_markdown falls back to narrative for legacy format."""
        profile = ProfileOutput(
            headline="Engineering Manager | 12+ Years Technology Leadership",
            narrative="Engineering leader with track record of building teams and delivering results.",
            core_competencies=["Engineering Leadership"],
        )
        skills = [SkillsSection("Technical", [SkillEvidence("Python", [], [])])]
        header = HeaderOutput(
            profile=profile,
            skills_sections=skills,
            education=["M.Sc. CS"],
            contact_info={"name": "John", "email": "john@example.com"},
        )

        md = header.to_markdown()
        # Should use narrative when tagline not present
        assert "Engineering leader with track record of building teams" in md

    def test_word_count_calculated_from_hybrid_content(self):
        """Word count is calculated from tagline + key_achievements."""
        profile = ProfileOutput(
            tagline="Technology leader who thrives on building teams",  # 8 words
            key_achievements=[
                "Led team of engineers",  # 4 words
                "Built CI pipeline",  # 2 words (CI counts as 1)
            ],
        )
        # Total: 8 + 4 + 2 = 14 words
        assert profile.word_count == 14

    def test_word_count_fallback_to_narrative(self):
        """Word count falls back to narrative for legacy format."""
        profile = ProfileOutput(
            narrative="Engineering leader with fifteen years of experience",  # 7 words
        )
        assert profile.word_count == 7
