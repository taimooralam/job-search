"""
Unit Tests for Layer 6 V2 Phase 6: Grader + Improver

Tests:
- Types: DimensionScore, GradeResult, ImprovementResult, FinalCV
- CVGrader rule-based grading
- CVGrader LLM grading (mocked)
- CVImprover single-pass improvement (mocked)
- Convenience functions
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.layer6_v2.types import (
    DimensionScore,
    GradeResult,
    ImprovementResult,
    FinalCV,
    StitchedRole,
    StitchedCV,
    HeaderOutput,
    ProfileOutput,
    SkillsSection,
    SkillEvidence,
)
from src.layer6_v2.grader import CVGrader, grade_cv
from src.layer6_v2.improver import CVImprover, improve_cv


# ===== FIXTURES =====

@pytest.fixture
def sample_cv_text():
    """Sample CV text for grading."""
    return """# John Developer
john@example.com | +49 123 456 7890 | linkedin.com/in/johndeveloper

## Profile
Engineering leader with 15 years experience building high-performing teams.
Led strategic platform transformation reducing latency by 75%. Expertise in Python, Kubernetes, and AWS.

## Core Competencies
**Leadership**: Team Leadership, Mentorship, Hiring
**Technical**: Python, Kubernetes, Microservices, System Design
**Platform**: AWS, Docker, CI/CD, Terraform
**Delivery**: Agile, Sprint Planning, Release Management

## Professional Experience

### Current Corp
**Engineering Manager** | Munich, DE | 2020–Present

• Led team of 12 engineers to deliver strategic platform initiative, driving revenue growth of $2M
• Managed and scaled the organization from 8 to 12 engineers through strategic hiring
• Built CI/CD pipeline using GitHub Actions and Kubernetes, improving deployment frequency by 300%
• Mentored 5 senior engineers, promoting 3 to staff level within 18 months
• Designed microservices architecture handling 10M requests daily with 99.9% uptime, driving customer retention

### Previous Inc
**Senior Engineer** | Berlin, DE | 2018–2020

• Implemented Python backend services processing 100K daily transactions, improving efficiency by 40%
• Led Agile sprint planning for team of 8, improving velocity by 40%
• Built monitoring dashboards using Grafana and Prometheus

## Education
- M.Sc. Computer Science — Technical University of Munich
"""


@pytest.fixture
def sample_extracted_jd():
    """Sample extracted JD for testing."""
    return {
        "title": "Engineering Manager",
        "company": "Target Company",
        "role_category": "engineering_manager",
        "seniority_level": "senior",
        "top_keywords": [
            "Python", "Kubernetes", "Team Leadership", "CI/CD",
            "Microservices", "Agile", "AWS", "System Design",
            "Mentorship", "Performance Management", "Docker",
            "Sprint Planning", "Engineering Excellence", "DevOps",
            "Cloud Infrastructure",
        ],
        "implied_pain_points": [
            "Need to scale engineering team",
            "Improve deployment velocity",
            "Build reliable systems",
        ],
        "technical_skills": ["Python", "Kubernetes", "AWS", "Docker"],
        "soft_skills": ["Leadership", "Communication", "Mentorship"],
        "responsibilities": [
            "Lead engineering team",
            "Improve delivery processes",
            "Build scalable systems",
        ],
    }


@pytest.fixture
def sample_master_cv():
    """Sample master CV for hallucination checking."""
    return """## Seven.One Entertainment Group
**Technical Lead** | Munich, DE | 2020–Present

- Led team of 12 engineers to deliver platform migration
- Reduced latency by 75% through architectural improvements
- Built CI/CD pipeline using GitHub Actions and Kubernetes
- Deployment frequency improved by 300%
- Mentored 5 senior engineers, 3 promoted to staff level
- Designed microservices architecture handling 10M requests daily
- Achieved 99.9% uptime
"""


# ===== TESTS: DimensionScore =====

class TestDimensionScore:
    """Test DimensionScore dataclass."""

    def test_creates_with_score(self):
        """Creates DimensionScore with score and weight."""
        dim = DimensionScore(
            dimension="ats_optimization",
            score=8.5,
            weight=0.20,
            feedback="Good keyword coverage",
        )
        assert dim.score == 8.5
        assert dim.weight == 0.20
        assert dim.weighted_score == pytest.approx(1.7)  # 8.5 * 0.20

    def test_calculates_weighted_score(self):
        """Calculates weighted score correctly."""
        dim = DimensionScore(
            dimension="impact_clarity",
            score=10.0,
            weight=0.25,
            feedback="Excellent metrics",
        )
        assert dim.weighted_score == 2.5

    def test_to_dict(self):
        """Converts to dictionary correctly."""
        dim = DimensionScore(
            dimension="jd_alignment",
            score=7.0,
            weight=0.25,
            feedback="Good alignment",
            issues=["Missing pain point coverage"],
            strengths=["Uses JD terminology"],
        )
        data = dim.to_dict()
        assert data["dimension"] == "jd_alignment"
        assert data["score"] == 7.0
        assert data["weighted_score"] == 1.75
        assert len(data["issues"]) == 1


# ===== TESTS: GradeResult =====

class TestGradeResult:
    """Test GradeResult dataclass."""

    def test_calculates_composite_score(self):
        """Calculates composite score from dimensions."""
        dims = [
            DimensionScore("ats_optimization", 8.0, 0.20, "feedback"),
            DimensionScore("impact_clarity", 9.0, 0.25, "feedback"),
            DimensionScore("jd_alignment", 8.5, 0.25, "feedback"),
            DimensionScore("executive_presence", 7.5, 0.15, "feedback"),
            DimensionScore("anti_hallucination", 9.5, 0.15, "feedback"),
        ]
        result = GradeResult(dimension_scores=dims)

        # Expected: 8*0.2 + 9*0.25 + 8.5*0.25 + 7.5*0.15 + 9.5*0.15 = 8.525
        assert abs(result.composite_score - 8.525) < 0.01

    def test_determines_passing(self):
        """Determines if CV passes threshold."""
        # Passing case
        dims = [
            DimensionScore("ats_optimization", 9.0, 0.20, ""),
            DimensionScore("impact_clarity", 9.0, 0.25, ""),
            DimensionScore("jd_alignment", 9.0, 0.25, ""),
            DimensionScore("executive_presence", 9.0, 0.15, ""),
            DimensionScore("anti_hallucination", 9.0, 0.15, ""),
        ]
        result = GradeResult(dimension_scores=dims, passing_threshold=8.5)
        assert result.passed is True

        # Failing case
        dims_low = [
            DimensionScore("ats_optimization", 6.0, 0.20, ""),
            DimensionScore("impact_clarity", 6.0, 0.25, ""),
            DimensionScore("jd_alignment", 6.0, 0.25, ""),
            DimensionScore("executive_presence", 6.0, 0.15, ""),
            DimensionScore("anti_hallucination", 6.0, 0.15, ""),
        ]
        result_low = GradeResult(dimension_scores=dims_low, passing_threshold=8.5)
        assert result_low.passed is False

    def test_finds_lowest_dimension(self):
        """Identifies lowest scoring dimension."""
        dims = [
            DimensionScore("ats_optimization", 8.0, 0.20, ""),
            DimensionScore("impact_clarity", 9.0, 0.25, ""),
            DimensionScore("jd_alignment", 6.5, 0.25, ""),  # Lowest
            DimensionScore("executive_presence", 7.5, 0.15, ""),
            DimensionScore("anti_hallucination", 9.0, 0.15, ""),
        ]
        result = GradeResult(dimension_scores=dims)
        assert result.lowest_dimension == "jd_alignment"

    def test_get_dimension_by_name(self):
        """Gets dimension score by name."""
        dims = [
            DimensionScore("ats_optimization", 8.0, 0.20, "ATS feedback"),
        ]
        result = GradeResult(dimension_scores=dims)
        dim = result.get_dimension("ats_optimization")
        assert dim is not None
        assert dim.feedback == "ATS feedback"

    def test_scores_by_dimension_property(self):
        """Returns scores indexed by dimension name."""
        dims = [
            DimensionScore("ats_optimization", 8.0, 0.20, ""),
            DimensionScore("impact_clarity", 9.0, 0.25, ""),
        ]
        result = GradeResult(dimension_scores=dims)
        scores = result.scores_by_dimension
        assert scores["ats_optimization"] == 8.0
        assert scores["impact_clarity"] == 9.0


# ===== TESTS: ImprovementResult =====

class TestImprovementResult:
    """Test ImprovementResult dataclass."""

    def test_creates_with_changes(self):
        """Creates ImprovementResult with changes."""
        result = ImprovementResult(
            improved=True,
            target_dimension="jd_alignment",
            changes_made=["Added pain point coverage", "Used JD terminology"],
            original_score=6.5,
            cv_text="Improved CV text...",
            improvement_summary="Added 3 pain point references",
        )
        assert result.improved is True
        assert len(result.changes_made) == 2

    def test_to_dict(self):
        """Converts to dictionary correctly."""
        result = ImprovementResult(
            improved=True,
            target_dimension="impact_clarity",
            changes_made=["Added metrics"],
            original_score=7.0,
            cv_text="CV...",
        )
        data = result.to_dict()
        assert data["improved"] is True
        assert data["target_dimension"] == "impact_clarity"


# ===== TESTS: FinalCV =====

class TestFinalCV:
    """Test FinalCV dataclass."""

    def test_creates_complete_cv(self):
        """Creates FinalCV with header and experience."""
        profile = ProfileOutput("Profile text.", [], [])
        skills = [SkillsSection("Technical", [SkillEvidence("Python", [], [])])]
        header = HeaderOutput(
            profile=profile,
            skills_sections=skills,
            education=["M.Sc. CS"],
            contact_info={"name": "John", "email": "john@example.com"},
        )

        role = StitchedRole(
            role_id="01",
            company="Corp",
            title="Manager",
            location="Munich",
            period="2020-Present",
            bullets=["Achievement 1", "Achievement 2"],
        )
        experience = StitchedCV(roles=[role])

        final = FinalCV(header=header, experience=experience)

        assert final.total_word_count > 0
        assert final.is_passing is False  # No grade result yet

    def test_is_passing_property(self):
        """Checks passing status from grade result."""
        profile = ProfileOutput("Profile.", [], [])
        header = HeaderOutput(
            profile=profile,
            skills_sections=[],
            education=[],
            contact_info={"name": "John"},
        )
        experience = StitchedCV(roles=[])

        # With passing grade
        dims = [DimensionScore("ats", 9.0, 1.0, "")]
        grade = GradeResult(dimension_scores=dims, passing_threshold=8.0)

        final = FinalCV(header=header, experience=experience, grade_result=grade)
        assert final.is_passing is True

    def test_to_markdown(self):
        """Converts to complete plain text (GAP-006: no markdown)."""
        profile = ProfileOutput("Engineering leader.", [], [])
        header = HeaderOutput(
            profile=profile,
            skills_sections=[],
            education=["M.Sc. CS"],
            contact_info={"name": "John", "email": "j@e.com", "phone": "123", "linkedin": "li"},
        )

        role = StitchedRole(
            role_id="01",
            company="Corp",
            title="Manager",
            location="Munich",
            period="2020",
            bullets=["Achievement"],
        )
        experience = StitchedCV(roles=[role])

        final = FinalCV(header=header, experience=experience)
        md = final.to_markdown()

        # CV uses markdown formatting for TipTap editor rendering
        assert "John" in md
        assert "Professional Experience" in md or "Corp" in md  # Role content
        assert "Achievement" in md
        # Bold ** markers ARE expected for TipTap to parse
        assert "**Corp • Manager**" in md  # Bold company/title


# ===== TESTS: CVGrader - Rule Based =====

class TestCVGraderRuleBased:
    """Test CVGrader rule-based grading."""

    def test_grades_ats_optimization(self, sample_cv_text, sample_extracted_jd):
        """Grades ATS optimization dimension."""
        grader = CVGrader(use_llm_grading=False)
        jd_keywords = sample_extracted_jd["top_keywords"]

        score = grader._grade_ats_optimization(sample_cv_text, jd_keywords)

        assert score.dimension == "ats_optimization"
        assert score.score >= 5  # Should find several keywords
        assert "keywords" in score.feedback.lower()

    def test_grades_impact_clarity(self, sample_cv_text):
        """Grades impact clarity dimension."""
        grader = CVGrader(use_llm_grading=False)

        score = grader._grade_impact_clarity(sample_cv_text)

        assert score.dimension == "impact_clarity"
        assert score.score >= 5  # Has metrics and action verbs
        assert "metrics" in score.feedback.lower()

    def test_grades_jd_alignment(self, sample_cv_text, sample_extracted_jd):
        """Grades JD alignment dimension."""
        grader = CVGrader(use_llm_grading=False)

        score = grader._grade_jd_alignment(sample_cv_text, sample_extracted_jd)

        assert score.dimension == "jd_alignment"
        assert score.score >= 5  # Has some alignment

    def test_grades_executive_presence(self, sample_cv_text, sample_extracted_jd):
        """Grades executive presence dimension."""
        grader = CVGrader(use_llm_grading=False)
        role_category = sample_extracted_jd["role_category"]

        score = grader._grade_executive_presence(sample_cv_text, role_category)

        assert score.dimension == "executive_presence"
        assert score.score >= 5  # Has leadership evidence

    def test_grades_anti_hallucination(self, sample_cv_text, sample_master_cv):
        """Grades anti-hallucination dimension."""
        grader = CVGrader(use_llm_grading=False)

        score = grader._grade_anti_hallucination(sample_cv_text, sample_master_cv)

        assert score.dimension == "anti_hallucination"
        assert score.score >= 7  # Metrics match source

    def test_full_grade_rule_based(
        self, sample_cv_text, sample_extracted_jd, sample_master_cv
    ):
        """Runs full rule-based grading."""
        grader = CVGrader(use_llm_grading=False)

        result = grader.grade(sample_cv_text, sample_extracted_jd, sample_master_cv)

        assert len(result.dimension_scores) == 5
        assert result.composite_score > 0
        assert result.lowest_dimension != ""


# ===== TESTS: CVGrader - With Mocked LLM =====

class TestCVGraderWithLLM:
    """Test CVGrader with mocked LLM."""

    @patch.object(CVGrader, '_grade_with_llm')
    def test_uses_llm_grading(
        self, mock_llm, sample_cv_text, sample_extracted_jd, sample_master_cv
    ):
        """Uses LLM for grading when enabled."""
        # Mock LLM response
        mock_response = Mock()
        mock_response.ats_optimization = Mock(
            score=8.5, feedback="Good", issues=[], strengths=[]
        )
        mock_response.impact_clarity = Mock(
            score=9.0, feedback="Excellent", issues=[], strengths=[]
        )
        mock_response.jd_alignment = Mock(
            score=8.0, feedback="Good", issues=[], strengths=[]
        )
        mock_response.executive_presence = Mock(
            score=7.5, feedback="OK", issues=[], strengths=[]
        )
        mock_response.anti_hallucination = Mock(
            score=9.5, feedback="Accurate", issues=[], strengths=[]
        )
        mock_response.exemplary_sections = ["Profile is strong"]
        mock_llm.return_value = mock_response

        grader = CVGrader(use_llm_grading=True)
        result = grader.grade(sample_cv_text, sample_extracted_jd, sample_master_cv)

        assert mock_llm.called
        assert len(result.dimension_scores) == 5

    @patch.object(CVGrader, '_grade_with_llm')
    def test_falls_back_on_llm_failure(
        self, mock_llm, sample_cv_text, sample_extracted_jd, sample_master_cv
    ):
        """Falls back to rule-based when LLM fails."""
        mock_llm.side_effect = Exception("LLM error")

        grader = CVGrader(use_llm_grading=True)
        result = grader.grade(sample_cv_text, sample_extracted_jd, sample_master_cv)

        # Should still get results from fallback
        assert len(result.dimension_scores) == 5
        assert result.composite_score > 0


# ===== TESTS: CVImprover =====

class TestCVImprover:
    """Test CVImprover."""

    def test_skips_improvement_if_passing(self, sample_cv_text, sample_extracted_jd):
        """Skips improvement if CV already passes."""
        # Create passing grade
        dims = [
            DimensionScore("ats_optimization", 9.0, 0.20, ""),
            DimensionScore("impact_clarity", 9.0, 0.25, ""),
            DimensionScore("jd_alignment", 9.0, 0.25, ""),
            DimensionScore("executive_presence", 9.0, 0.15, ""),
            DimensionScore("anti_hallucination", 9.0, 0.15, ""),
        ]
        passing_grade = GradeResult(dimension_scores=dims, passing_threshold=8.5)

        improver = CVImprover()
        result = improver.improve(sample_cv_text, passing_grade, sample_extracted_jd)

        assert result.improved is False
        assert "already meets" in result.improvement_summary.lower()

    @patch.object(CVImprover, '_call_improvement_llm')
    def test_targets_lowest_dimension(
        self, mock_llm, sample_cv_text, sample_extracted_jd
    ):
        """Targets lowest-scoring dimension for improvement."""
        # Create failing grade with lowest jd_alignment
        dims = [
            DimensionScore("ats_optimization", 8.0, 0.20, ""),
            DimensionScore("impact_clarity", 9.0, 0.25, ""),
            DimensionScore("jd_alignment", 6.0, 0.25, "", issues=["Missing pain points"]),
            DimensionScore("executive_presence", 7.5, 0.15, ""),
            DimensionScore("anti_hallucination", 9.0, 0.15, ""),
        ]
        failing_grade = GradeResult(dimension_scores=dims, passing_threshold=8.5)

        # Mock improvement response
        mock_response = Mock()
        mock_response.improved_cv = "Improved CV text"
        mock_response.changes_made = ["Added pain point coverage"]
        mock_response.improvement_summary = "Improved JD alignment"
        mock_llm.return_value = mock_response

        improver = CVImprover()
        result = improver.improve(sample_cv_text, failing_grade, sample_extracted_jd)

        assert result.improved is True
        assert result.target_dimension == "jd_alignment"
        assert mock_llm.called

    @patch.object(CVImprover, '_call_improvement_llm')
    def test_handles_improvement_failure(
        self, mock_llm, sample_cv_text, sample_extracted_jd
    ):
        """Handles LLM improvement failure gracefully."""
        dims = [
            DimensionScore("ats_optimization", 6.0, 0.20, ""),
            DimensionScore("impact_clarity", 6.0, 0.25, ""),
            DimensionScore("jd_alignment", 6.0, 0.25, ""),
            DimensionScore("executive_presence", 6.0, 0.15, ""),
            DimensionScore("anti_hallucination", 6.0, 0.15, ""),
        ]
        failing_grade = GradeResult(dimension_scores=dims)

        mock_llm.side_effect = Exception("LLM error")

        improver = CVImprover()
        result = improver.improve(sample_cv_text, failing_grade, sample_extracted_jd)

        assert result.improved is False
        assert "failed" in result.improvement_summary.lower()


# ===== TESTS: Convenience Functions =====

class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_grade_cv_function(
        self, sample_cv_text, sample_extracted_jd, sample_master_cv
    ):
        """grade_cv convenience function works."""
        with patch.object(CVGrader, '_grade_with_llm') as mock_llm:
            mock_llm.side_effect = Exception("Skip LLM")

            result = grade_cv(
                sample_cv_text,
                sample_extracted_jd,
                sample_master_cv,
                passing_threshold=8.0,
            )

            assert result is not None
            assert len(result.dimension_scores) == 5

    def test_improve_cv_function(self, sample_cv_text, sample_extracted_jd):
        """improve_cv convenience function works."""
        dims = [DimensionScore("ats", 9.0, 1.0, "")]
        passing_grade = GradeResult(dimension_scores=dims, passing_threshold=8.0)

        result = improve_cv(sample_cv_text, passing_grade, sample_extracted_jd)

        assert result is not None
        assert result.improved is False  # Already passing


# ===== TESTS: Edge Cases =====

class TestEdgeCases:
    """Test edge cases."""

    def test_empty_cv_text(self, sample_extracted_jd, sample_master_cv):
        """Handles empty CV text."""
        grader = CVGrader(use_llm_grading=False)
        result = grader.grade("", sample_extracted_jd, sample_master_cv)

        # Should still return valid result
        assert len(result.dimension_scores) == 5
        assert result.composite_score < 5  # Should be low

    def test_empty_jd_keywords(self, sample_cv_text, sample_master_cv):
        """Handles empty JD keywords."""
        extracted_jd = {
            "top_keywords": [],
            "role_category": "engineering_manager",
            "implied_pain_points": [],
            "technical_skills": [],
            "soft_skills": [],
            "responsibilities": [],
        }

        grader = CVGrader(use_llm_grading=False)
        result = grader.grade(sample_cv_text, extracted_jd, sample_master_cv)

        assert len(result.dimension_scores) == 5

    def test_all_dimensions_equal(self):
        """Handles all dimensions with equal scores."""
        dims = [
            DimensionScore("ats_optimization", 7.0, 0.20, ""),
            DimensionScore("impact_clarity", 7.0, 0.25, ""),
            DimensionScore("jd_alignment", 7.0, 0.25, ""),
            DimensionScore("executive_presence", 7.0, 0.15, ""),
            DimensionScore("anti_hallucination", 7.0, 0.15, ""),
        ]
        result = GradeResult(dimension_scores=dims)

        # Lowest should be first alphabetically when tied
        assert result.lowest_dimension in [d.dimension for d in dims]


# ===== TESTS: Metric Extraction =====

class TestMetricExtraction:
    """Test metric extraction helpers."""

    def test_counts_percentages(self):
        """Counts percentage metrics."""
        grader = CVGrader(use_llm_grading=False)
        text = "Improved by 75% and reduced costs by 30%"
        count = grader._count_metrics(text)
        assert count >= 2

    def test_counts_action_verbs(self):
        """Counts strong action verbs."""
        grader = CVGrader(use_llm_grading=False)
        text = "• Led team\n• Built platform\n• Designed system"
        count, verbs = grader._count_action_verbs(text)
        assert count >= 3
        assert "led" in [v.lower() for v in verbs]

    def test_counts_keywords(self):
        """Counts keyword matches."""
        grader = CVGrader(use_llm_grading=False)
        text = "Experience with Python and Kubernetes in AWS"
        keywords = ["Python", "Kubernetes", "AWS", "Go", "Azure"]
        count, found = grader._count_keywords(text, keywords)
        assert count == 3
        assert "Python" in found
