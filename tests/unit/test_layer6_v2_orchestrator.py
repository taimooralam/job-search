"""
Unit tests for CV Generation V2 Orchestrator.

Tests the integration of all 6 phases into a cohesive pipeline.
All LLM calls are mocked for deterministic testing.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.layer6_v2.orchestrator import CVGeneratorV2, cv_generator_v2_node
from src.layer6_v2.types import (
    RoleBullets,
    GeneratedBullet,
    StitchedCV,
    StitchedRole,
    HeaderOutput,
    ProfileOutput,
    SkillsSection,
    SkillEvidence,
    ValidationResult,
    GradeResult,
    DimensionScore,
    ImprovementResult,
)
from src.layer6_v2.cv_loader import RoleData, CandidateData


# ===== FIXTURES =====

@pytest.fixture
def sample_state():
    """Sample JobState for testing."""
    return {
        "job_id": "test-123",
        "title": "Engineering Manager",
        "company": "Test Corp",
        "job_description": "We need an engineering manager...",
        "extracted_jd": {
            "title": "Engineering Manager",
            "company": "Test Corp",
            "role_category": "engineering_manager",
            "seniority_level": "senior",
            "top_keywords": ["Python", "Kubernetes", "Leadership", "CI/CD", "AWS"],
            "implied_pain_points": ["Scale engineering team", "Improve delivery"],
            "success_metrics": ["Team velocity", "System reliability"],
            "technical_skills": ["Python", "Kubernetes"],
            "soft_skills": ["Leadership", "Communication"],
            "responsibilities": ["Lead team", "Build systems"],
            "qualifications": ["5+ years experience"],
            "nice_to_haves": ["MBA"],
            "competency_weights": {
                "delivery": 30,
                "process": 20,
                "architecture": 25,
                "leadership": 25,
            },
        },
        "run_id": "test-run-001",
    }


@pytest.fixture
def sample_candidate_data():
    """Sample candidate data from CV loader."""
    return CandidateData(
        name="Test Candidate",
        title_base="Engineering Manager",
        email="test@example.com",
        phone="+49 123 456 7890",
        linkedin="linkedin.com/in/test",
        location="Munich, DE",
        languages=["English", "German"],
        education_masters="M.Sc. Computer Science - Test University",
        education_bachelors="B.Sc. Computer Science - Test College",
        certifications=["AWS Solutions Architect"],
        years_experience=15,
        roles=[
            RoleData(
                id="01_current_corp",
                company="Current Corp",
                title="Engineering Manager",
                period="2020-Present",
                location="Munich, DE",
                start_year=2020,
                end_year=None,
                is_current=True,
                duration_years=4,
                industry="Technology",
                team_size="12",
                primary_competencies=["leadership", "architecture"],
                keywords=["team", "performance", "CI/CD"],
                achievements=[
                    "Led team of 12 engineers",
                    "Reduced latency by 75%",
                    "Built CI/CD pipeline",
                ],
                hard_skills=["Python", "Kubernetes"],
                soft_skills=["Leadership"],
            ),
            RoleData(
                id="02_previous_inc",
                company="Previous Inc",
                title="Senior Engineer",
                period="2018-2020",
                location="Berlin, DE",
                start_year=2018,
                end_year=2020,
                is_current=False,
                duration_years=2,
                industry="Technology",
                team_size="8",
                primary_competencies=["delivery", "process"],
                keywords=["microservices", "testing"],
                achievements=[
                    "Implemented microservices",
                    "Improved test coverage to 90%",
                ],
                hard_skills=["Python", "Docker"],
                soft_skills=["Communication"],
            ),
        ],
    )


@pytest.fixture
def sample_role_bullets():
    """Sample generated role bullets."""
    return [
        RoleBullets(
            role_id="current_corp_em",
            company="Current Corp",
            title="Engineering Manager",
            period="2020-Present",
            bullets=[
                GeneratedBullet(
                    text="Led team of 12 engineers to deliver platform migration, reducing latency by 75%",
                    source_text="Led team of 12 engineers",
                    jd_keyword_used="team leadership",
                    word_count=13,
                ),
            ],
            qa_result=None,
        ),
        RoleBullets(
            role_id="previous_inc_se",
            company="Previous Inc",
            title="Senior Engineer",
            period="2018-2020",
            bullets=[
                GeneratedBullet(
                    text="Designed and implemented microservices architecture processing 100K requests daily",
                    source_text="Implemented microservices",
                    jd_keyword_used="microservices",
                    word_count=9,
                ),
            ],
            qa_result=None,
        ),
    ]


@pytest.fixture
def sample_stitched_cv():
    """Sample stitched CV."""
    return StitchedCV(
        roles=[
            StitchedRole(
                role_id="current_corp_em",
                company="Current Corp",
                title="Engineering Manager",
                period="2020-Present",
                location="Munich, DE",
                bullets=[
                    "Led team of 12 engineers to deliver platform migration, reducing latency by 75%",
                ],
                word_count=13,
            ),
            StitchedRole(
                role_id="previous_inc_se",
                company="Previous Inc",
                title="Senior Engineer",
                period="2018-2020",
                location="Berlin, DE",
                bullets=[
                    "Designed and implemented microservices architecture processing 100K requests daily",
                ],
                word_count=9,
            ),
        ],
        total_word_count=22,
        total_bullet_count=2,
        keywords_coverage=["Python"],
        deduplication_result=None,
    )


@pytest.fixture
def sample_header_output():
    """Sample header output."""
    return HeaderOutput(
        profile=ProfileOutput(
            text="Engineering leader with 10+ years experience building high-performing teams.",
            highlights_used=["Platform migration", "75% latency reduction"],
            keywords_integrated=["engineering", "leader", "platform"],
        ),
        skills_sections=[
            SkillsSection(
                category="Leadership",
                skills=[
                    SkillEvidence(
                        skill="Team Leadership",
                        evidence_bullets=["Led team of 12"],
                        source_roles=["Current Corp"],
                    ),
                ],
            ),
            SkillsSection(
                category="Technical",
                skills=[
                    SkillEvidence(
                        skill="Python",
                        evidence_bullets=["Backend services"],
                        source_roles=["Previous Inc"],
                    ),
                ],
            ),
        ],
        education=["M.Sc. Computer Science - Test University"],
        contact_info={
            "name": "Test Candidate",
            "email": "test@example.com",
        },
        validation_result=ValidationResult(
            passed=True,
            grounded_skills=["Team Leadership", "Python"],
            ungrounded_skills=[],
            evidence_map={
                "Team Leadership": ["Led team of 12"],
                "Python": ["Backend services"],
            },
        ),
    )


@pytest.fixture
def sample_grade_result():
    """Sample grade result that passes."""
    return GradeResult(
        dimension_scores=[
            DimensionScore("ats_optimization", 9.0, 0.20, "Good"),
            DimensionScore("impact_clarity", 9.0, 0.25, "Excellent"),
            DimensionScore("jd_alignment", 8.5, 0.25, "Good"),
            DimensionScore("executive_presence", 8.5, 0.15, "Strong"),
            DimensionScore("anti_hallucination", 9.5, 0.15, "No issues"),
        ],
        passing_threshold=8.5,
    )


# ===== TESTS: CVGeneratorV2 Initialization =====

class TestCVGeneratorV2Init:
    """Test CVGeneratorV2 initialization."""

    def test_initializes_with_defaults(self):
        """Initializes with default configuration."""
        generator = CVGeneratorV2()
        assert generator.passing_threshold == 8.5
        assert generator.word_budget is None  # None = no limit, include all roles fully
        assert generator.use_llm_grading is True

    def test_initializes_with_custom_config(self):
        """Initializes with custom configuration."""
        generator = CVGeneratorV2(
            passing_threshold=9.0,
            word_budget=500,
            use_llm_grading=False,
        )
        assert generator.passing_threshold == 9.0
        assert generator.word_budget == 500
        assert generator.use_llm_grading is False


# ===== TESTS: Default Extracted JD =====

class TestDefaultExtractedJD:
    """Test fallback when extracted_jd is missing."""

    def test_builds_default_from_state(self, sample_state):
        """Builds default extracted_jd from state."""
        generator = CVGeneratorV2()
        state_without_jd = {**sample_state, "extracted_jd": None}

        default_jd = generator._build_default_extracted_jd(state_without_jd)

        assert default_jd["title"] == "Engineering Manager"
        assert default_jd["company"] == "Test Corp"
        assert default_jd["role_category"] == "engineering_manager"
        assert sum(default_jd["competency_weights"].values()) == 100


# ===== TESTS: CV Assembly =====

class TestCVAssembly:
    """Test CV text assembly."""

    def test_assembles_complete_cv(
        self, sample_header_output, sample_stitched_cv, sample_candidate_data
    ):
        """Assembles complete CV markdown."""
        generator = CVGeneratorV2()

        cv_text = generator._assemble_cv_text(
            sample_header_output,
            sample_stitched_cv,
            sample_candidate_data,
        )

        # Check header (GAP-006: now plain text, no markdown; name is uppercase)
        assert "TEST CANDIDATE" in cv_text
        assert "test@example.com" in cv_text

        # Check profile (GAP-006: uppercase section headers)
        assert "PROFILE" in cv_text
        assert "Engineering leader" in cv_text

        # Check skills
        assert "CORE COMPETENCIES" in cv_text
        assert "Leadership" in cv_text

        # Check experience
        assert "PROFESSIONAL EXPERIENCE" in cv_text
        assert "Current Corp" in cv_text
        assert "Previous Inc" in cv_text

        # Check education
        assert "EDUCATION" in cv_text

        # CV uses markdown formatting for TipTap editor rendering
        # Bold ** and italic * markers ARE expected for TipTap to parse
        assert "**PROFILE**" in cv_text or "**PROFESSIONAL EXPERIENCE**" in cv_text


# ===== TESTS: Reasoning Summary =====

class TestReasoningSummary:
    """Test reasoning summary generation."""

    def test_builds_reasoning_for_passing_cv(
        self, sample_grade_result, sample_stitched_cv, sample_header_output
    ):
        """Builds reasoning for passing CV (GAP-006: plain text format)."""
        generator = CVGeneratorV2()

        reasoning = generator._build_reasoning(
            sample_grade_result,
            None,  # No improvement needed
            sample_stitched_cv,
            sample_header_output,
        )

        # Reasoning section uses plain text (not shown to user in CV)
        assert "CV GENERATION V2 REASONING" in reasoning
        assert "Quality Score" in reasoning
        assert "Passed" in reasoning
        assert "Dimension Scores" in reasoning

    def test_builds_reasoning_with_improvement(
        self, sample_stitched_cv, sample_header_output
    ):
        """Builds reasoning when improvement was applied."""
        generator = CVGeneratorV2()

        # Failing grade
        failing_grade = GradeResult(
            dimension_scores=[
                DimensionScore("ats_optimization", 7.0, 0.20, "Needs work"),
                DimensionScore("impact_clarity", 8.0, 0.25, "Good"),
                DimensionScore("jd_alignment", 6.0, 0.25, "Low"),
                DimensionScore("executive_presence", 7.5, 0.15, "OK"),
                DimensionScore("anti_hallucination", 9.0, 0.15, "Good"),
            ],
            passing_threshold=8.5,
        )

        improvement = ImprovementResult(
            improved=True,
            target_dimension="jd_alignment",
            changes_made=["Added pain point coverage", "Used JD terminology"],
            original_score=6.0,
            cv_text="Improved CV text",
            improvement_summary="Improved JD alignment",
        )

        reasoning = generator._build_reasoning(
            failing_grade,
            improvement,
            sample_stitched_cv,
            sample_header_output,
        )

        assert "Improvement Applied" in reasoning
        assert "jd_alignment" in reasoning
        assert "Changes Made" in reasoning


# ===== TESTS: Full Pipeline (Mocked) =====

class TestFullPipelineMocked:
    """Test full pipeline with mocked components."""

    @patch('src.layer6_v2.orchestrator.CVLoader')
    @patch.object(CVGeneratorV2, '_get_master_cv_text')
    @patch.object(CVGeneratorV2, '_save_cv_to_disk')
    @patch('src.layer6_v2.orchestrator.grade_cv')
    @patch('src.layer6_v2.orchestrator.generate_header')
    @patch('src.layer6_v2.orchestrator.stitch_all_roles')
    @patch('src.layer6_v2.orchestrator.run_qa_on_all_roles')
    @patch.object(CVGeneratorV2, '_generate_all_role_bullets')
    def test_generate_produces_cv(
        self,
        mock_generate_bullets,
        mock_qa,
        mock_stitch,
        mock_header,
        mock_grade,
        mock_save,
        mock_master_cv,
        mock_cv_loader_class,
        sample_state,
        sample_role_bullets,
        sample_stitched_cv,
        sample_header_output,
        sample_grade_result,
        sample_candidate_data,
    ):
        """Full generate() produces CV output."""
        # Setup mocks
        mock_cv_loader_class.return_value.load.return_value = sample_candidate_data
        mock_generate_bullets.return_value = sample_role_bullets
        mock_qa.return_value = ([], [])  # Returns tuple of (qa_results, ats_results)
        mock_stitch.return_value = sample_stitched_cv
        mock_header.return_value = sample_header_output
        mock_grade.return_value = sample_grade_result
        mock_save.return_value = "outputs/test_corp/cv_engineering_manager.md"
        mock_master_cv.return_value = "Master CV text"

        generator = CVGeneratorV2()
        result = generator.generate(sample_state)

        # Verify output structure
        assert "cv_text" in result
        assert "cv_path" in result
        assert "cv_reasoning" in result
        assert result["cv_text"] is not None
        assert result["cv_path"] == "outputs/test_corp/cv_engineering_manager.md"

    @patch('src.layer6_v2.orchestrator.CVLoader')
    def test_handles_generation_error(self, mock_loader_class, sample_state):
        """Handles errors gracefully."""
        mock_loader_class.return_value.load.side_effect = Exception("CV load failed")

        generator = CVGeneratorV2()
        result = generator.generate(sample_state)

        assert result["cv_text"] is None
        assert result["cv_path"] is None
        assert "errors" in result
        assert "Generation failed" in result["cv_reasoning"]


# ===== TESTS: Node Function =====

class TestNodeFunction:
    """Test cv_generator_v2_node function."""

    @patch.object(CVGeneratorV2, 'generate')
    def test_node_calls_generator(self, mock_generate, sample_state):
        """Node function calls generator."""
        mock_generate.return_value = {
            "cv_text": "Generated CV",
            "cv_path": "/path/to/cv.md",
            "cv_reasoning": "Reasoning",
        }

        result = cv_generator_v2_node(sample_state)

        assert result["cv_text"] == "Generated CV"
        assert result["cv_path"] == "/path/to/cv.md"


# ===== TESTS: QA Summary =====

class TestQASummary:
    """Test QA summary logging."""

    def test_logs_qa_summary(self, caplog, sample_role_bullets):
        """Logs QA summary correctly."""
        from src.layer6_v2.types import QAResult

        generator = CVGeneratorV2()
        qa_results = [
            QAResult(
                passed=True,
                flagged_bullets=[],
                issues=[],
                verified_metrics=["75%"],
                confidence=0.9,
            ),
            QAResult(
                passed=False,
                flagged_bullets=["invented metric bullet"],
                issues=["Metric not in source"],
                verified_metrics=[],
                confidence=0.5,
            ),
        ]

        # This should not raise
        generator._log_qa_summary(qa_results, sample_role_bullets)


# ===== TESTS: Grade Logging =====

class TestGradeLogging:
    """Test grade result logging."""

    def test_logs_grade_result(self, sample_grade_result, caplog):
        """Logs grade result correctly."""
        generator = CVGeneratorV2()

        # This should not raise
        generator._log_grade_result(sample_grade_result)
