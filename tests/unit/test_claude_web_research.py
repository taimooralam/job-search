"""
Unit tests for src/common/claude_web_research.py

Tests the ClaudeWebResearcher for company/role/people research via Claude CLI.
Covers web search integration via invoke_unified_sync, schema validation, error handling, and tier support.
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pydantic import ValidationError

from src.common.claude_web_research import (
    ClaudeWebResearcher,
    WebResearchResult,
    CompanySignalModel,
    CompanyResearchModel,
    ContactModel,
    PeopleResearchModel,
    RoleResearchModel,
    research_company,
    research_people,
    research_role,
    CLAUDE_MODEL_TIERS,
)
from src.common.unified_llm import LLMResult


# ===== FIXTURES =====

@pytest.fixture
def valid_company_research_data():
    """Valid company research data matching schema."""
    return {
        "summary": "TechCorp is a Series B SaaS platform with 10M users.",
        "signals": [
            {
                "type": "funding",
                "description": "Raised $50M Series B from Sequoia",
                "date": "2024-06-15",
                "source": "https://techcorp.com/news",
                "business_context": "Enables enterprise expansion and scaling"
            },
            {
                "type": "growth",
                "description": "Team grew 40% in 2024",
                "date": "2024-03-01",
                "source": "https://linkedin.com/company/techcorp",
                "business_context": "Rapid hiring indicates strong product-market fit"
            }
        ],
        "url": "https://techcorp.com",
        "company_type": "employer"
    }


@pytest.fixture
def valid_people_research_data():
    """Valid people research data matching schema."""
    return {
        "primary_contacts": [
            {
                "name": "Sarah Chen",
                "role": "VP Engineering",
                "company": "TechCorp",
                "why_relevant": "Direct hiring manager for platform team",
                "linkedin_url": "https://linkedin.com/in/sarahchen",
                "email": None
            },
            {
                "name": "John Smith",
                "role": "Director of Platform",
                "company": "TechCorp",
                "why_relevant": "Technical decision maker for infrastructure",
                "linkedin_url": "https://linkedin.com/in/johnsmith",
                "email": None
            }
        ],
        "secondary_contacts": [
            {
                "name": "Emily Rodriguez",
                "role": "Head of Talent",
                "company": "TechCorp",
                "why_relevant": "Recruiter responsible for engineering hires",
                "linkedin_url": "https://linkedin.com/in/emilyrodriguez",
                "email": None
            }
        ]
    }


@pytest.fixture
def valid_role_research_data():
    """Valid role research data matching schema."""
    return {
        "business_impact": [
            "Enable 10x user growth through scalable architecture",
            "Reduce infrastructure costs by 30%",
            "Accelerate feature delivery with improved deployment pipeline"
        ],
        "why_now": "Recent $50M funding requires scaling infrastructure to support enterprise expansion",
        "team_context": "Senior engineer will lead platform team of 5",
        "challenges": [
            "Migrate legacy monolith to microservices",
            "Implement reliable CI/CD automation"
        ]
    }


@pytest.fixture
def mock_llm_result_factory():
    """Factory to create mock LLMResult objects."""
    def _create_result(data_dict=None, success=True, error=None):
        """Create a mock LLMResult with the given data."""
        return LLMResult(
            content=json.dumps(data_dict) if data_dict and success else "",
            parsed_json=data_dict if data_dict and success else None,
            backend="claude_cli",
            model="claude-sonnet-4-5-20250929",
            tier="middle",
            duration_ms=1500,
            success=success,
            error=error,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05
        )
    return _create_result


# ===== SCHEMA VALIDATION TESTS =====

class TestPydanticSchemas:
    """Test Pydantic schema validation."""

    def test_company_signal_model_valid(self):
        """CompanySignalModel validates correct data."""
        signal = CompanySignalModel(
            type="funding",
            description="Raised $50M Series B",
            date="2024-06-15",
            source="https://techcorp.com/news",
            business_context="Enables scaling"
        )

        assert signal.type == "funding"
        assert signal.description == "Raised $50M Series B"

    def test_company_signal_model_missing_required(self):
        """CompanySignalModel fails without required fields."""
        with pytest.raises(ValidationError):
            CompanySignalModel(
                type="funding",
                # Missing description and source
                date="2024-06-15"
            )

    def test_company_research_model_valid(self, valid_company_research_data):
        """CompanyResearchModel validates correct data."""
        research = CompanyResearchModel(**valid_company_research_data)

        assert research.summary == valid_company_research_data["summary"]
        assert len(research.signals) == 2
        assert research.company_type == "employer"

    def test_company_research_model_enforces_max_signals(self):
        """CompanyResearchModel enforces max 10 signals."""
        with pytest.raises(ValidationError):
            CompanyResearchModel(
                summary="Test company",
                signals=[
                    {
                        "type": "funding",
                        "description": f"Signal {i}",
                        "source": "https://test.com"
                    }
                    for i in range(11)  # 11 signals, max is 10
                ],
                url="https://test.com",
                company_type="employer"
            )

    def test_contact_model_valid(self):
        """ContactModel validates correct contact data."""
        contact = ContactModel(
            name="Sarah Chen",
            role="VP Engineering",
            company="TechCorp",
            why_relevant="Direct hiring manager",
            linkedin_url="https://linkedin.com/in/sarah"
        )

        assert contact.name == "Sarah Chen"
        assert contact.email is None  # Optional field

    def test_people_research_model_valid(self, valid_people_research_data):
        """PeopleResearchModel validates correct data."""
        people = PeopleResearchModel(**valid_people_research_data)

        assert len(people.primary_contacts) == 2
        assert len(people.secondary_contacts) == 1

    def test_people_research_model_enforces_max_contacts(self):
        """PeopleResearchModel enforces max 3 primary contacts."""
        with pytest.raises(ValidationError):
            PeopleResearchModel(
                primary_contacts=[
                    {
                        "name": f"Person {i}",
                        "role": "Engineer",
                        "company": "TechCorp",
                        "why_relevant": "Relevant"
                    }
                    for i in range(4)  # 4 contacts, max is 3
                ],
                secondary_contacts=[]
            )

    def test_role_research_model_valid(self, valid_role_research_data):
        """RoleResearchModel validates correct data."""
        role = RoleResearchModel(**valid_role_research_data)

        assert len(role.business_impact) > 0
        assert role.why_now != ""


# ===== INITIALIZATION TESTS =====

class TestClaudeWebResearcherInitialization:
    """Test ClaudeWebResearcher initialization."""

    def test_init_with_default_tier(self):
        """Should initialize with balanced tier by default."""
        researcher = ClaudeWebResearcher()

        assert researcher.tier == "balanced"
        assert researcher.model == CLAUDE_MODEL_TIERS["balanced"]
        assert researcher.max_searches == 8
        assert researcher.timeout == 120

    def test_init_with_fast_tier(self):
        """Should initialize with fast tier (Haiku)."""
        researcher = ClaudeWebResearcher(tier="fast")

        assert researcher.tier == "fast"
        assert researcher.model == CLAUDE_MODEL_TIERS["fast"]

    def test_init_with_quality_tier(self):
        """Should initialize with quality tier (Opus)."""
        researcher = ClaudeWebResearcher(tier="quality")

        assert researcher.tier == "quality"
        assert researcher.model == CLAUDE_MODEL_TIERS["quality"]

    def test_init_with_custom_max_searches(self):
        """Should accept custom max_searches."""
        researcher = ClaudeWebResearcher(max_searches=12)

        assert researcher.max_searches == 12


# ===== COMPANY RESEARCH TESTS =====

class TestCompanyResearch:
    """Test company research functionality."""

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.invoke_unified_sync')
    async def test_successful_company_research(
        self,
        mock_invoke,
        valid_company_research_data,
        mock_llm_result_factory
    ):
        """Should successfully research company and return validated data."""
        # Mock invoke_unified_sync to return LLMResult with company data
        mock_invoke.return_value = mock_llm_result_factory(valid_company_research_data)

        researcher = ClaudeWebResearcher(tier="balanced")
        result = await researcher.research_company(
            company_name="TechCorp",
            job_context="Building scalable systems",
            job_title="Senior Software Engineer"
        )

        # Verify result
        assert result.success is True
        assert result.data["summary"] == valid_company_research_data["summary"]
        assert len(result.data["signals"]) == 2
        assert result.model == "claude-sonnet-4-5-20250929"
        assert result.input_tokens == 1000
        assert result.output_tokens == 500

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.invoke_unified_sync')
    async def test_company_research_with_web_search_tool(
        self,
        mock_invoke,
        valid_company_research_data,
        mock_llm_result_factory
    ):
        """Should invoke unified LLM correctly (web search is handled by Claude CLI)."""
        mock_invoke.return_value = mock_llm_result_factory(valid_company_research_data)

        researcher = ClaudeWebResearcher(max_searches=10)
        await researcher.research_company("TechCorp")

        # Verify invoke_unified_sync was called
        assert mock_invoke.called
        call_kwargs = mock_invoke.call_args[1]
        assert call_kwargs["step_name"] == "research_company"
        assert call_kwargs["validate_json"] is True

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.invoke_unified_sync')
    async def test_company_research_handles_api_error(self, mock_invoke):
        """Should handle API errors gracefully."""
        mock_invoke.side_effect = RuntimeError("API Error")

        researcher = ClaudeWebResearcher()
        result = await researcher.research_company("TechCorp")

        assert result.success is False
        assert "API Error" in result.error

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.invoke_unified_sync')
    async def test_company_research_handles_invalid_json(
        self,
        mock_invoke,
        mock_llm_result_factory
    ):
        """Should handle invalid JSON from API."""
        # Return success=True but with invalid JSON content
        bad_result = mock_llm_result_factory()
        bad_result.content = "Not valid JSON!"
        bad_result.parsed_json = None
        mock_invoke.return_value = bad_result

        researcher = ClaudeWebResearcher()
        result = await researcher.research_company("TechCorp")

        assert result.success is False
        assert "JSON" in result.error

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.invoke_unified_sync')
    async def test_company_research_validates_schema(
        self,
        mock_invoke,
        mock_llm_result_factory
    ):
        """Should validate response against Pydantic schema."""
        # Missing required field 'url'
        invalid_data = {
            "summary": "Test",
            "signals": [],
            # Missing 'url'
            "company_type": "employer"
        }
        mock_invoke.return_value = mock_llm_result_factory(invalid_data)

        researcher = ClaudeWebResearcher()
        result = await researcher.research_company("TechCorp")

        assert result.success is False
        assert "validation failed" in result.error.lower()


# ===== PEOPLE RESEARCH TESTS =====

class TestPeopleResearch:
    """Test people research functionality."""

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.invoke_unified_sync')
    async def test_successful_people_research(
        self,
        mock_invoke,
        valid_people_research_data,
        mock_llm_result_factory
    ):
        """Should successfully research people and return validated data."""
        mock_invoke.return_value = mock_llm_result_factory(valid_people_research_data)

        researcher = ClaudeWebResearcher()
        result = await researcher.research_people(
            company_name="TechCorp",
            role="Senior Software Engineer",
            department="Engineering"
        )

        assert result.success is True
        assert len(result.data["primary_contacts"]) == 2
        assert len(result.data["secondary_contacts"]) == 1
        assert result.data["primary_contacts"][0]["name"] == "Sarah Chen"

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.invoke_unified_sync')
    async def test_people_research_includes_role_context(
        self,
        mock_invoke,
        valid_people_research_data,
        mock_llm_result_factory
    ):
        """Should include role and department context in prompt."""
        mock_invoke.return_value = mock_llm_result_factory(valid_people_research_data)

        researcher = ClaudeWebResearcher()
        await researcher.research_people(
            company_name="TechCorp",
            role="Senior Software Engineer",
            department="Platform Engineering"
        )

        # Verify prompt includes context
        call_kwargs = mock_invoke.call_args[1]
        prompt = call_kwargs["prompt"]

        assert "TechCorp" in prompt
        assert "Senior Software Engineer" in prompt
        assert "Platform Engineering" in prompt


# ===== ROLE RESEARCH TESTS =====

class TestRoleResearch:
    """Test role research functionality."""

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.invoke_unified_sync')
    async def test_successful_role_research(
        self,
        mock_invoke,
        valid_role_research_data,
        mock_llm_result_factory
    ):
        """Should successfully research role and return validated data."""
        mock_invoke.return_value = mock_llm_result_factory(valid_role_research_data)

        researcher = ClaudeWebResearcher()
        result = await researcher.research_role(
            company_name="TechCorp",
            role_title="Senior Software Engineer",
            job_description="Build scalable systems..."
        )

        assert result.success is True
        assert len(result.data["business_impact"]) == 3
        assert result.data["why_now"] != ""
        assert len(result.data["challenges"]) == 2


# ===== SEARCH COUNT TRACKING TESTS =====

class TestSearchCountTracking:
    """Test web search count tracking."""

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.invoke_unified_sync')
    async def test_tracks_search_count(
        self,
        mock_invoke,
        valid_company_research_data,
        mock_llm_result_factory
    ):
        """Should track number of web searches performed (currently 0 for CLI mode)."""
        mock_invoke.return_value = mock_llm_result_factory(valid_company_research_data)

        researcher = ClaudeWebResearcher()
        result = await researcher.research_company("TechCorp")

        # CLI doesn't report search count currently
        assert result.searches_performed == 0


# ===== API AVAILABILITY CHECK TESTS =====

class TestAPIAvailabilityCheck:
    """Test API availability checking."""

    @patch('src.common.claude_web_research.invoke_unified_sync')
    def test_check_api_available_success(self, mock_invoke):
        """Should return True when API is available."""
        mock_invoke.return_value = LLMResult(
            content="ok",
            backend="claude_cli",
            model="test",
            tier="low",
            duration_ms=100,
            success=True
        )

        researcher = ClaudeWebResearcher()
        assert researcher.check_api_available() is True

    @patch('src.common.claude_web_research.invoke_unified_sync')
    def test_check_api_not_available(self, mock_invoke):
        """Should return False when API fails."""
        mock_invoke.side_effect = Exception("API error")

        researcher = ClaudeWebResearcher()
        assert researcher.check_api_available() is False


# ===== TIER DISPLAY INFO TESTS =====

class TestTierDisplayInfo:
    """Test tier display information."""

    def test_get_tier_display_info(self):
        """Should return tier information for UI."""
        tiers = ClaudeWebResearcher.get_tier_display_info()

        assert len(tiers) == 3
        assert all("value" in tier for tier in tiers)
        assert all("label" in tier for tier in tiers)
        assert all("model" in tier for tier in tiers)

        tier_values = [t["value"] for t in tiers]
        assert "fast" in tier_values
        assert "balanced" in tier_values
        assert "quality" in tier_values


# ===== WEB RESEARCH RESULT TESTS =====

class TestWebResearchResult:
    """Test WebResearchResult dataclass."""

    def test_create_success_result(self, valid_company_research_data):
        """Should create valid success result."""
        result = WebResearchResult(
            success=True,
            data=valid_company_research_data,
            error=None,
            model="claude-sonnet-4-5-20250929",
            tier="balanced",
            duration_ms=1500,
            researched_at="2024-01-01T00:00:00Z",
            searches_performed=3,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05
        )

        assert result.success is True
        assert result.searches_performed == 3
        assert result.cost_usd == 0.05

    def test_create_failure_result(self):
        """Should create valid failure result."""
        result = WebResearchResult(
            success=False,
            data=None,
            error="API timeout",
            model="claude-sonnet-4-5-20250929",
            tier="balanced",
            duration_ms=120000,
            researched_at="2024-01-01T00:00:00Z"
        )

        assert result.success is False
        assert result.error == "API timeout"
        assert result.data is None

    def test_webresearchresult_to_dict(self):
        """Should convert WebResearchResult to dictionary."""
        result = WebResearchResult(
            success=True,
            data={"test": "data"},
            error=None,
            model="claude-sonnet-4-5-20250929",
            tier="balanced",
            duration_ms=1500,
            researched_at="2024-01-01T00:00:00Z"
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["success"] is True
        assert result_dict["tier"] == "balanced"


# ===== CONVENIENCE FUNCTION TESTS =====

class TestConvenienceFunctions:
    """Test async convenience functions."""

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.ClaudeWebResearcher')
    async def test_research_company_convenience(self, mock_researcher_class):
        """research_company() convenience function should work."""
        mock_researcher = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True

        async def mock_research(*args, **kwargs):
            return mock_result

        mock_researcher.research_company = mock_research
        mock_researcher_class.return_value = mock_researcher

        result = await research_company(
            company_name="TechCorp",
            job_context="Test context",
            tier="fast"
        )

        assert result.success is True
        mock_researcher_class.assert_called_once_with(tier="fast")

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.ClaudeWebResearcher')
    async def test_research_people_convenience(self, mock_researcher_class):
        """research_people() convenience function should work."""
        mock_researcher = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True

        async def mock_research(*args, **kwargs):
            return mock_result

        mock_researcher.research_people = mock_research
        mock_researcher_class.return_value = mock_researcher

        result = await research_people(
            company_name="TechCorp",
            role="Engineer",
            tier="balanced"
        )

        assert result.success is True

    @pytest.mark.asyncio
    @patch('src.common.claude_web_research.ClaudeWebResearcher')
    async def test_research_role_convenience(self, mock_researcher_class):
        """research_role() convenience function should work."""
        mock_researcher = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True

        async def mock_research(*args, **kwargs):
            return mock_result

        mock_researcher.research_role = mock_research
        mock_researcher_class.return_value = mock_researcher

        result = await research_role(
            company_name="TechCorp",
            role_title="Senior Engineer",
            tier="quality"
        )

        assert result.success is True
