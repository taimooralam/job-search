"""
Unit Tests for Layer 1.4: JD Extractor (CV Gen V2)

Tests structured job description extraction:
- Role category classification (EM, Staff, Director, Head of Eng, CTO)
- Competency weights validation (sum = 100)
- ATS keyword extraction (15 keywords)
- Pydantic schema validation
- LLM response parsing
- Node function integration
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

from src.layer1_4.jd_extractor import (
    JDExtractor,
    jd_extractor_node,
    ExtractedJDModel,
    CompetencyWeightsModel,
    RoleCategory,
    SeniorityLevel,
    RemotePolicy,
)


# ===== FIXTURES =====

@pytest.fixture
def sample_job_state():
    """Sample JobState with minimal fields for Layer 1.4."""
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
        "job_url": "https://example.com/job",
        "source": "test",
        "candidate_profile": "",
        "run_id": "test-run-001",
        "errors": [],
    }


@pytest.fixture
def sample_llm_response():
    """Sample valid LLM response for JD extraction."""
    return json.dumps({
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
        "cto"
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

    def test_valid_model_passes(self, sample_llm_response):
        """Valid JSON passes full schema validation."""
        data = json.loads(sample_llm_response)
        model = ExtractedJDModel(**data)
        assert model.role_category == RoleCategory.HEAD_OF_ENGINEERING
        assert model.seniority_level == SeniorityLevel.DIRECTOR
        assert len(model.top_keywords) == 15

    def test_missing_required_field_fails(self, sample_llm_response):
        """Missing required field raises validation error."""
        data = json.loads(sample_llm_response)
        del data["role_category"]
        with pytest.raises(ValidationError) as exc_info:
            ExtractedJDModel(**data)
        assert "role_category" in str(exc_info.value)

    def test_empty_responsibilities_fails(self, sample_llm_response):
        """Empty responsibilities list fails validation."""
        data = json.loads(sample_llm_response)
        data["responsibilities"] = []
        with pytest.raises(ValidationError):
            ExtractedJDModel(**data)

    def test_too_few_keywords_fails(self, sample_llm_response):
        """Fewer than 10 keywords fails validation."""
        data = json.loads(sample_llm_response)
        data["top_keywords"] = ["keyword1", "keyword2", "keyword3"]
        with pytest.raises(ValidationError):
            ExtractedJDModel(**data)

    def test_keyword_deduplication(self, sample_llm_response):
        """Duplicate keywords are removed."""
        data = json.loads(sample_llm_response)
        data["top_keywords"] = ["Python", "python", "PYTHON", "AWS", "aws"] + data["top_keywords"]
        model = ExtractedJDModel(**data)
        # Should deduplicate case-insensitively
        python_count = sum(1 for k in model.top_keywords if k.lower() == "python")
        assert python_count == 1


# ===== TESTS: LLM Response Parsing =====

class TestLLMResponseParsing:
    """Test parsing of LLM responses."""

    @patch('src.layer1_4.jd_extractor.create_tracked_llm')
    def test_parses_valid_json_response(self, mock_llm_class, sample_job_state, sample_llm_response):
        """Valid JSON response is parsed correctly."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = sample_llm_response
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        extractor = JDExtractor()
        result = extractor.extract(sample_job_state)

        assert result["extracted_jd"] is not None
        assert result["extracted_jd"]["role_category"] == "head_of_engineering"
        assert result["extracted_jd"]["competency_weights"]["leadership"] == 40

    @patch('src.layer1_4.jd_extractor.create_tracked_llm')
    def test_parses_json_with_markdown_wrapper(self, mock_llm_class, sample_job_state, sample_llm_response):
        """JSON wrapped in markdown code blocks is parsed correctly."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = f"```json\n{sample_llm_response}\n```"
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        extractor = JDExtractor()
        result = extractor.extract(sample_job_state)

        assert result["extracted_jd"] is not None
        assert result["extracted_jd"]["title"] == "Head of Engineering"

    @patch('src.layer1_4.jd_extractor.create_tracked_llm')
    def test_handles_invalid_json_gracefully(self, mock_llm_class, sample_job_state):
        """Invalid JSON returns None and adds error."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "This is not valid JSON at all"
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        extractor = JDExtractor()
        result = extractor.extract(sample_job_state)

        assert result["extracted_jd"] is None
        assert len(result["errors"]) > 0
        assert "Layer 1.4" in result["errors"][0]


# ===== TESTS: Role Category Detection Accuracy =====

class TestRoleCategoryDetection:
    """Test role category is detected correctly from JD context."""

    @patch('src.layer1_4.jd_extractor.create_tracked_llm')
    def test_engineering_manager_classification(self, mock_llm_class):
        """Engineering Manager JD is classified correctly."""
        state = {
            "job_id": "em_test",
            "title": "Engineering Manager",
            "company": "TestCo",
            "job_description": "Manage a team of 8 engineers. Run 1:1s, sprint planning.",
            "run_id": None,
            "errors": [],
        }

        response = json.dumps({
            "title": "Engineering Manager",
            "company": "TestCo",
            "location": "San Francisco",
            "remote_policy": "hybrid",
            "role_category": "engineering_manager",
            "seniority_level": "senior",
            "competency_weights": {"delivery": 30, "process": 20, "architecture": 10, "leadership": 40},
            "responsibilities": ["Manage team", "Run 1:1s", "Sprint planning"],
            "qualifications": ["3+ years managing engineers", "Strong technical background"],
            "nice_to_haves": [],
            "technical_skills": ["Python"],
            "soft_skills": ["Leadership"],
            "implied_pain_points": ["Team needs direction"],
            "success_metrics": ["Team velocity increases"],
            "top_keywords": ["Engineering Manager"] * 15,  # Simplified for test
            "industry_background": None,
            "years_experience_required": 5,
            "education_requirements": None
        })

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = response
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        extractor = JDExtractor()
        result = extractor.extract(state)

        assert result["extracted_jd"]["role_category"] == "engineering_manager"
        assert result["extracted_jd"]["competency_weights"]["leadership"] == 40


# ===== TESTS: Node Function Integration =====

class TestJDExtractorNode:
    """Test jd_extractor_node LangGraph integration."""

    @patch('src.layer1_4.jd_extractor.create_tracked_llm')
    def test_node_returns_state_updates(self, mock_llm_class, sample_job_state, sample_llm_response):
        """Node function returns correct state updates."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = sample_llm_response
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        updates = jd_extractor_node(sample_job_state)

        assert "extracted_jd" in updates
        assert updates["extracted_jd"]["role_category"] == "head_of_engineering"
        assert len(updates["extracted_jd"]["top_keywords"]) == 15

    @patch('src.layer1_4.jd_extractor.create_tracked_llm')
    def test_node_handles_errors_gracefully(self, mock_llm_class, sample_job_state):
        """Node function handles errors without crashing."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM API Error")
        mock_llm_class.return_value = mock_llm

        updates = jd_extractor_node(sample_job_state)

        assert updates["extracted_jd"] is None
        assert len(updates["errors"]) > 0


# ===== TESTS: TypedDict Conversion =====

class TestTypedDictConversion:
    """Test conversion from Pydantic model to TypedDict."""

    def test_to_extracted_jd_preserves_all_fields(self, sample_llm_response):
        """Conversion to TypedDict preserves all fields."""
        data = json.loads(sample_llm_response)
        model = ExtractedJDModel(**data)
        typed_dict = model.to_extracted_jd()

        assert typed_dict["title"] == data["title"]
        assert typed_dict["role_category"] == "head_of_engineering"
        assert typed_dict["competency_weights"]["leadership"] == 40
        assert len(typed_dict["top_keywords"]) == 15
        assert typed_dict["industry_background"] == "B2B SaaS"

    def test_to_extracted_jd_handles_optional_nulls(self, sample_llm_response):
        """Conversion handles None values for optional fields."""
        data = json.loads(sample_llm_response)
        data["industry_background"] = None
        data["years_experience_required"] = None
        model = ExtractedJDModel(**data)
        typed_dict = model.to_extracted_jd()

        assert typed_dict["industry_background"] is None
        assert typed_dict["years_experience_required"] is None
