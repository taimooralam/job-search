"""
Unit Tests for Layer 1.4: JD Extractor

Tests structured job description extraction using UnifiedLLM:
- Role category classification (EM, Staff, Director, Head of Eng, CTO)
- Competency weights validation (sum = 100)
- ATS keyword extraction (15 keywords)
- Pydantic schema validation
- LLM response parsing
- ExtractionResult handling
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

from src.layer1_4.claude_jd_extractor import (
    JDExtractor,
    ExtractionResult,
    ExtractedJDModel,
    CompetencyWeightsModel,
    RoleCategory,
    SeniorityLevel,
    RemotePolicy,
)
from src.common.unified_llm import LLMResult


# ===== FIXTURES =====

@pytest.fixture
def sample_job_params():
    """Sample job parameters for extraction."""
    return {
        "job_id": "test_001",
        "title": "Head of Engineering",
        "company": "TechStartup Inc",
        "job_description": """
        Head of Engineering - Remote (EU)

        We're looking for a Head of Engineering to build and lead our engineering team.
        This is a founding role - you'll be employee #1 on the engineering side.

        Responsibilities:
        - Build the engineering team from scratch (target: 10 engineers in 12 months)
        - Define engineering culture, hiring bar, and technical processes
        - Architect scalable systems to support 100x growth
        - Partner with CEO on product strategy and roadmap
        - Establish CI/CD, code review, and quality standards

        Requirements:
        - 10+ years software engineering experience
        - 5+ years leading engineering teams (EM or Director level)
        - Experience scaling systems from 0 to 1M+ users
        - Strong background in Python, TypeScript, AWS/GCP
        - Prior startup experience preferred
        - Experience building engineering culture from scratch

        Nice to have:
        - Previous CTO or Head of Eng experience
        - Background in FinTech or B2B SaaS
        - Experience with remote-first teams

        Compensation: $180k - $220k + equity
        Location: Remote (EU timezone preferred)
        """,
    }


@pytest.fixture
def sample_extracted_jd():
    """Sample valid extracted JD response."""
    return {
        "title": "Head of Engineering",
        "company": "TechStartup Inc",
        "location": "Remote (EU)",
        "remote_policy": "fully_remote",
        "role_category": "head_of_engineering",
        "seniority_level": "director",
        "competency_weights": {
            "delivery": 25,
            "process": 15,
            "architecture": 20,
            "leadership": 40
        },
        "responsibilities": [
            "Build the engineering team from scratch",
            "Define engineering culture and hiring bar",
            "Architect scalable systems for 100x growth",
            "Partner with CEO on product strategy",
            "Establish CI/CD and quality standards"
        ],
        "qualifications": [
            "10+ years software engineering experience",
            "5+ years leading engineering teams",
            "Experience scaling 0 to 1M+ users",
            "Strong Python, TypeScript, AWS/GCP"
        ],
        "nice_to_haves": [
            "Previous CTO or Head of Eng experience",
            "Background in FinTech or B2B SaaS",
            "Experience with remote-first teams"
        ],
        "technical_skills": ["Python", "TypeScript", "AWS", "GCP", "CI/CD"],
        "soft_skills": ["Leadership", "Team Building", "Strategic Thinking"],
        "implied_pain_points": [
            "No engineering team or processes exist",
            "Need to move fast while building proper foundations",
            "Scaling challenges ahead as company grows"
        ],
        "success_metrics": [
            "10 engineers hired in 12 months",
            "System architecture supports 100x growth",
            "Engineering culture and processes established"
        ],
        "top_keywords": [
            "Head of Engineering", "Engineering Leadership", "Python", "TypeScript",
            "AWS", "GCP", "CI/CD", "Team Building", "Startup", "Remote",
            "Scaling", "Architecture", "Engineering Culture", "Hiring", "SaaS"
        ],
        "industry_background": "B2B SaaS",
        "years_experience_required": 10,
        "education_requirements": None
    }


def create_cli_output(extracted_jd: dict) -> str:
    """Create mock CLI JSON output."""
    return json.dumps({
        "result": json.dumps(extracted_jd),
        "cost": {"input_tokens": 1000, "output_tokens": 500},
        "model": "claude-opus-4-5-20251101",
    })


# ===== TESTS: Competency Weights Validation =====

class TestCompetencyWeightsValidation:
    """Test competency weights must sum to exactly 100."""

    def test_valid_weights_sum_to_100(self):
        """Weights summing to 100 pass validation."""
        weights = CompetencyWeightsModel(
            delivery=30,
            process=20,
            architecture=25,
            leadership=25
        )
        assert weights.delivery + weights.process + weights.architecture + weights.leadership == 100

    def test_weights_not_summing_to_100_fails(self):
        """Weights not summing to 100 raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            CompetencyWeightsModel(
                delivery=30,
                process=30,
                architecture=30,
                leadership=30  # Sum = 120, not 100
            )
        assert "must sum to 100" in str(exc_info.value)

    def test_weights_below_100_fails(self):
        """Weights summing to less than 100 raise validation error."""
        with pytest.raises(ValidationError):
            CompetencyWeightsModel(
                delivery=20,
                process=20,
                architecture=20,
                leadership=20  # Sum = 80, not 100
            )

    def test_negative_weights_fail(self):
        """Negative weights raise validation error."""
        with pytest.raises(ValidationError):
            CompetencyWeightsModel(
                delivery=-10,
                process=40,
                architecture=40,
                leadership=30
            )


# ===== TESTS: Role Category Classification =====

class TestRoleCategoryClassification:
    """Test role category enum validation."""

    @pytest.mark.parametrize("category", [
        "engineering_manager",
        "staff_principal_engineer",
        "director_of_engineering",
        "head_of_engineering",
        "vp_engineering",
        "cto",
        "tech_lead",
        "senior_engineer"
    ])
    def test_valid_role_categories(self, category):
        """All valid role categories are accepted."""
        role = RoleCategory(category)
        assert role.value == category

    def test_invalid_role_category_fails(self):
        """Invalid role category raises error."""
        with pytest.raises(ValueError):
            RoleCategory("senior_developer")


# ===== TESTS: Seniority Level Validation =====

class TestSeniorityLevelValidation:
    """Test seniority level enum validation."""

    @pytest.mark.parametrize("level", [
        "senior", "staff", "principal", "director", "vp", "c_level"
    ])
    def test_valid_seniority_levels(self, level):
        """All valid seniority levels are accepted."""
        seniority = SeniorityLevel(level)
        assert seniority.value == level


# ===== TESTS: Remote Policy Validation =====

class TestRemotePolicyValidation:
    """Test remote policy enum validation."""

    @pytest.mark.parametrize("policy,expected", [
        ("fully_remote", RemotePolicy.FULLY_REMOTE),
        ("hybrid", RemotePolicy.HYBRID),
        ("onsite", RemotePolicy.ONSITE),
        ("not_specified", RemotePolicy.NOT_SPECIFIED),
    ])
    def test_valid_remote_policies(self, policy, expected):
        """All valid remote policies are accepted."""
        remote = RemotePolicy(policy)
        assert remote == expected


# ===== TESTS: Full Schema Validation =====

class TestExtractedJDModelValidation:
    """Test full ExtractedJDModel validation."""

    def test_valid_model_passes(self, sample_extracted_jd):
        """Valid JSON passes full schema validation."""
        model = ExtractedJDModel(**sample_extracted_jd)
        assert model.role_category == RoleCategory.HEAD_OF_ENGINEERING
        assert model.seniority_level == SeniorityLevel.DIRECTOR
        assert len(model.top_keywords) == 15

    def test_missing_required_field_fails(self, sample_extracted_jd):
        """Missing required field raises validation error."""
        del sample_extracted_jd["role_category"]
        with pytest.raises(ValidationError) as exc_info:
            ExtractedJDModel(**sample_extracted_jd)
        assert "role_category" in str(exc_info.value)

    def test_empty_responsibilities_fails(self, sample_extracted_jd):
        """Empty responsibilities list fails validation."""
        sample_extracted_jd["responsibilities"] = []
        with pytest.raises(ValidationError):
            ExtractedJDModel(**sample_extracted_jd)

    def test_too_few_keywords_fails(self, sample_extracted_jd):
        """Fewer than 10 keywords fails validation."""
        sample_extracted_jd["top_keywords"] = ["keyword1", "keyword2", "keyword3"]
        with pytest.raises(ValidationError):
            ExtractedJDModel(**sample_extracted_jd)

    def test_keyword_deduplication(self, sample_extracted_jd):
        """Duplicate keywords are removed."""
        sample_extracted_jd["top_keywords"] = ["Python", "python", "PYTHON", "AWS", "aws"] + sample_extracted_jd["top_keywords"]
        model = ExtractedJDModel(**sample_extracted_jd)
        # Should deduplicate case-insensitively
        python_count = sum(1 for k in model.top_keywords if k.lower() == "python")
        assert python_count == 1


# ===== TESTS: JDExtractor UnifiedLLM Integration =====

class TestJDExtractorCLI:
    """Test JDExtractor UnifiedLLM-based extraction."""

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_successful_extraction(self, mock_invoke, sample_job_params, sample_extracted_jd):
        """Successful LLM extraction returns ExtractionResult with data."""
        mock_invoke.return_value = LLMResult(
            content=json.dumps(sample_extracted_jd),
            parsed_json=sample_extracted_jd,
            backend="claude_cli",
            model="claude-opus-4-5-20251101",
            tier="middle",
            duration_ms=5000,
            success=True,
        )

        extractor = JDExtractor()
        result = extractor.extract(**sample_job_params)

        assert isinstance(result, ExtractionResult)
        assert result.success is True
        assert result.extracted_jd is not None
        assert result.extracted_jd["role_category"] == "head_of_engineering"
        assert result.extracted_jd["competency_weights"]["leadership"] == 40
        assert result.error is None

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_cli_failure_returns_error(self, mock_invoke, sample_job_params):
        """LLM failure (when fallback disabled) returns ExtractionResult with error."""
        mock_invoke.return_value = LLMResult(
            content="",
            backend="none",
            model="",
            tier="middle",
            duration_ms=0,
            success=False,
            error="CLI authentication failed and fallback is disabled",
        )

        extractor = JDExtractor()
        result = extractor.extract(**sample_job_params)

        assert result.success is False
        assert result.extracted_jd is None
        assert "failed" in result.error.lower()

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_invalid_json_returns_error(self, mock_invoke, sample_job_params):
        """Invalid JSON in LLM output returns error."""
        mock_invoke.return_value = LLMResult(
            content="not valid json at all",
            parsed_json=None,
            backend="claude_cli",
            model="claude-opus-4-5-20251101",
            tier="middle",
            duration_ms=5000,
            success=True,  # LLM call succeeded but content is invalid
        )

        extractor = JDExtractor()
        result = extractor.extract(**sample_job_params)

        assert result.success is False
        assert result.extracted_jd is None
        assert "parse" in result.error.lower() or "json" in result.error.lower()

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_validation_error_returns_error(self, mock_invoke, sample_job_params, sample_extracted_jd):
        """Schema validation failure returns error."""
        # Make the response fail validation by removing required field
        invalid_jd = {**sample_extracted_jd}
        del invalid_jd["role_category"]

        mock_invoke.return_value = LLMResult(
            content=json.dumps(invalid_jd),
            parsed_json=invalid_jd,
            backend="claude_cli",
            model="claude-opus-4-5-20251101",
            tier="middle",
            duration_ms=5000,
            success=True,
        )

        extractor = JDExtractor()
        result = extractor.extract(**sample_job_params)

        assert result.success is False
        assert result.extracted_jd is None
        assert "validation" in result.error.lower()

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_timeout_returns_error(self, mock_invoke, sample_job_params):
        """LLM timeout returns ExtractionResult with timeout error."""
        mock_invoke.return_value = LLMResult(
            content="",
            backend="claude_cli",
            model="claude-opus-4-5-20251101",
            tier="middle",
            duration_ms=120000,
            success=False,
            error="CLI timeout after 120s",
        )

        extractor = JDExtractor(timeout=120)
        result = extractor.extract(**sample_job_params)

        assert result.success is False
        assert result.extracted_jd is None
        assert "timeout" in result.error.lower()

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_tracks_duration(self, mock_invoke, sample_job_params, sample_extracted_jd):
        """Extraction tracks duration in milliseconds."""
        mock_invoke.return_value = LLMResult(
            content=json.dumps(sample_extracted_jd),
            parsed_json=sample_extracted_jd,
            backend="claude_cli",
            model="claude-opus-4-5-20251101",
            tier="middle",
            duration_ms=5000,
            success=True,
        )

        extractor = JDExtractor()
        result = extractor.extract(**sample_job_params)

        assert result.duration_ms >= 0
        assert result.extracted_at is not None

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_fallback_to_langchain(self, mock_invoke, sample_job_params, sample_extracted_jd):
        """When CLI fails, fallback to LangChain succeeds."""
        mock_invoke.return_value = LLMResult(
            content=json.dumps(sample_extracted_jd),
            parsed_json=sample_extracted_jd,
            backend="langchain",  # Fallback was used
            model="gpt-4o",
            tier="middle",
            duration_ms=3000,
            success=True,
        )

        extractor = JDExtractor()
        result = extractor.extract(**sample_job_params)

        assert result.success is True
        assert result.model == "gpt-4o"  # Fallback model
        assert result.extracted_jd is not None


# ===== TESTS: TypedDict Conversion =====

class TestTypedDictConversion:
    """Test conversion from Pydantic model to TypedDict."""

    def test_to_extracted_jd_preserves_all_fields(self, sample_extracted_jd):
        """Conversion to TypedDict preserves all fields."""
        model = ExtractedJDModel(**sample_extracted_jd)
        typed_dict = model.to_extracted_jd()

        assert typed_dict["title"] == sample_extracted_jd["title"]
        assert typed_dict["role_category"] == "head_of_engineering"
        assert typed_dict["competency_weights"]["leadership"] == 40
        assert len(typed_dict["top_keywords"]) == 15
        assert typed_dict["industry_background"] == "B2B SaaS"

    def test_to_extracted_jd_handles_optional_nulls(self, sample_extracted_jd):
        """Conversion handles None values for optional fields."""
        sample_extracted_jd["industry_background"] = None
        sample_extracted_jd["years_experience_required"] = None
        model = ExtractedJDModel(**sample_extracted_jd)
        typed_dict = model.to_extracted_jd()

        assert typed_dict["industry_background"] is None
        assert typed_dict["years_experience_required"] is None


# ===== TESTS: ExtractionResult =====

class TestExtractionResult:
    """Test ExtractionResult dataclass."""

    def test_to_dict_serialization(self):
        """ExtractionResult can be serialized to dict."""
        result = ExtractionResult(
            job_id="test_001",
            success=True,
            extracted_jd={"role_category": "head_of_engineering"},
            error=None,
            model="claude-opus-4-5-20251101",
            duration_ms=1234,
            extracted_at="2024-01-01T00:00:00"
        )

        result_dict = result.to_dict()
        assert result_dict["job_id"] == "test_001"
        assert result_dict["success"] is True
        assert result_dict["extracted_jd"]["role_category"] == "head_of_engineering"
        assert result_dict["duration_ms"] == 1234

    def test_failure_result_structure(self):
        """Failed ExtractionResult has expected structure."""
        result = ExtractionResult(
            job_id="test_001",
            success=False,
            extracted_jd=None,
            error="Validation failed",
            model="claude-opus-4-5-20251101",
            duration_ms=500,
            extracted_at="2024-01-01T00:00:00"
        )

        assert result.success is False
        assert result.extracted_jd is None
        assert result.error == "Validation failed"


# ===== TESTS: CLI Availability Check =====

class TestCLIAvailability:
    """Test CLI availability checking."""

    @patch('subprocess.run')
    def test_check_cli_available_success(self, mock_run):
        """check_cli_available returns True when CLI is installed."""
        mock_run.return_value = MagicMock(returncode=0)

        extractor = JDExtractor()
        assert extractor.check_cli_available() is True

    @patch('subprocess.run')
    def test_check_cli_available_failure(self, mock_run):
        """check_cli_available returns False when CLI is not installed."""
        mock_run.side_effect = FileNotFoundError()

        extractor = JDExtractor()
        assert extractor.check_cli_available() is False
