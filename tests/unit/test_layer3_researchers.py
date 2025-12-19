"""
Unit Tests for Layer 3: Company & Role Researchers (Phase 5)

Tests Phase 5.1 (Company Researcher) and Phase 5.2 (Role Researcher):
- Mocked FireCrawl and LLM responses for determinism
- Schema validation with Pydantic
- Hallucination prevention controls
- Cache functionality
- Error handling and fallback logic
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime


def create_firecrawl_mock(scrape_markdown: str, search_url: str = "https://techcorp.com"):
    """
    Create a properly configured FireCrawl mock with both search() and scrape().

    Phase 5.1 uses firecrawl.search() first, then firecrawl.scrape().
    Tests need to mock both methods for the Phase 5.1 path to work.

    Phase 5.2 quality gate requires >= 100 characters to pass.

    Args:
        scrape_markdown: The markdown content that scrape() should return
        search_url: The URL that search results should contain

    Returns:
        Configured MagicMock for FirecrawlApp
    """
    mock_firecrawl = MagicMock()

    # Phase 5.2 quality gate requires >= 100 chars - pad short content
    # Add business-related padding to pass quality gate and not trigger boilerplate detection
    padded_content = scrape_markdown
    if len(scrape_markdown) < 100:
        padded_content = f"{scrape_markdown} TechCorp is a leading technology company specializing in cloud infrastructure and enterprise solutions. The company has been expanding rapidly with new products and strategic partnerships."

    # Mock scrape() - returns object with .markdown attribute
    mock_scrape_result = MagicMock()
    mock_scrape_result.markdown = padded_content
    mock_firecrawl.scrape.return_value = mock_scrape_result

    # Mock search() - returns object with .web attribute containing result objects
    mock_search_result_item = MagicMock()
    mock_search_result_item.url = search_url
    mock_search_result_item.markdown = padded_content

    mock_search_response = MagicMock()
    mock_search_response.web = [mock_search_result_item]
    mock_firecrawl.search.return_value = mock_search_response

    return mock_firecrawl

from src.layer3.company_researcher import (
    CompanyResearcher,
    CompanyResearchOutput,
    CompanySignalModel,
    company_researcher_node
)
from src.layer3.role_researcher import (
    RoleResearcher,
    RoleResearchOutput,
    role_researcher_node
)


# ===== FIXTURES =====

@pytest.fixture
def sample_job_state():
    """Sample JobState for testing."""
    return {
        "job_id": "test_001",
        "title": "Senior Software Engineer",
        "company": "TechCorp",
        "job_description": "Build scalable systems for 10M users. Required: Python, AWS, Kubernetes.",
        "job_url": "https://example.com/job",
        "source": "test",
        "candidate_profile": "",
        "pain_points": None,
        "strategic_needs": None,
        "risks_if_unfilled": None,
        "success_metrics": None,
        "selected_stars": None,
        "star_to_pain_mapping": None,
        "company_summary": None,
        "company_url": None,
        "company_research": None,
        "role_research": None,
        "fit_score": None,
        "fit_rationale": None,
        "people": None,
        "cover_letter": None,
        "cv_path": None,
        "drive_folder_url": None,
        "sheet_row_id": None,
        "run_id": None,
        "created_at": None,
        "errors": [],
        "status": "processing"
    }


@pytest.fixture
def valid_company_research_json():
    """Valid company research JSON matching schema."""
    return {
        "summary": "TechCorp builds cloud infrastructure for enterprise clients.",
        "signals": [
            {
                "type": "funding",
                "description": "Raised $50M Series B from Accel Partners",
                "date": "2024-01-15",
                "source": "https://techcorp.com/news"
            },
            {
                "type": "growth",
                "description": "Expanded engineering team by 40%",
                "date": "2024-03-01",
                "source": "https://linkedin.com/techcorp"
            }
        ],
        "url": "https://techcorp.com"
    }


@pytest.fixture
def valid_role_research_json():
    """Valid role research JSON matching schema."""
    return {
        "summary": "Senior engineer will lead platform team of 5, owning core infrastructure",
        "business_impact": [
            "Enable 10x user growth through scalable architecture",
            "Reduce infrastructure costs by 30% through optimization",
            "Accelerate feature delivery with improved deployment pipeline"
        ],
        "why_now": "Recent $50M funding requires scaling infrastructure to support enterprise expansion"
    }


# ===== COMPANY RESEARCHER TESTS =====

class TestCompanyResearcherSchema:
    """Test Pydantic schema validation for Company Researcher."""

    def test_valid_company_research_schema(self, valid_company_research_json):
        """Valid JSON passes schema validation."""
        validated = CompanyResearchOutput(**valid_company_research_json)

        assert validated.summary == valid_company_research_json["summary"]
        assert len(validated.signals) == 2
        assert validated.url == valid_company_research_json["url"]

    def test_missing_required_field_fails_validation(self):
        """Schema validation fails when required field missing."""
        invalid_data = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": []
            # Missing 'url'
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            CompanyResearchOutput(**invalid_data)

    def test_signal_without_source_fails_validation(self):
        """Signal without source URL fails validation."""
        invalid_data = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [
                {
                    "type": "funding",
                    "description": "Raised funding",
                    "date": "2024-01-01"
                    # Missing 'source'
                }
            ],
            "url": "https://techcorp.com"
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            CompanyResearchOutput(**invalid_data)


class TestCompanyResearcherWithMockedDependencies:
    """Test Company Researcher with mocked FireCrawl and LLM."""

    @patch('src.layer3.company_researcher.create_tracked_llm')
    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_multi_source_scraping_and_signal_extraction(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        mock_llm_class,
        sample_job_state,
        valid_company_research_json
    ):
        """Phase 5.1: Multi-source scraping extracts signals successfully."""
        # Mock FireCrawl - use helper for search + scrape
        mock_firecrawl = create_firecrawl_mock(
            "TechCorp is a leading cloud infrastructure provider. Recently raised $50M Series B."
        )
        mock_firecrawl_class.return_value = mock_firecrawl

        # Mock LLM to return valid company research JSON
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(valid_company_research_json)
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        # Mock MongoDB (empty cache)
        mock_mongo = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None  # Cache miss
        mock_mongo.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_mongo

        # Run Company Researcher (use_claude_api=False for legacy FireCrawl mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Assertions
        assert "company_research" in result
        assert result["company_research"]["summary"] == valid_company_research_json["summary"]
        assert len(result["company_research"]["signals"]) == 2
        assert result["company_research"]["signals"][0]["type"] == "funding"

        # Legacy fields populated for backward compatibility
        assert result["company_summary"] == valid_company_research_json["summary"]
        assert result["company_url"] == valid_company_research_json["url"]

    @patch('src.layer3.company_researcher.create_tracked_llm')
    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_cache_hit_returns_cached_data(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        mock_llm_class,
        sample_job_state,
        valid_company_research_json
    ):
        """Cache hit returns cached research without multi-source scraping."""
        # Mock MongoDB to return cached data
        mock_mongo = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = {
            "company_key": "techcorp",
            "company_research": valid_company_research_json,
            "cached_at": datetime.utcnow()
        }
        mock_mongo.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_mongo

        # Mock FireCrawl (job posting scrape happens, but search/multi-source should NOT)
        mock_firecrawl = MagicMock()
        mock_scrape_result = MagicMock()
        mock_scrape_result.markdown = "Job posting content"
        mock_firecrawl.scrape.return_value = mock_scrape_result
        mock_firecrawl_class.return_value = mock_firecrawl

        mock_llm_class.return_value = MagicMock()

        # Run Company Researcher (use_claude_api=False for legacy FireCrawl mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Assertions
        assert "company_research" in result
        assert result["company_research"]["summary"] == valid_company_research_json["summary"]
        print("   ✓ Cache HIT for TechCorp")

        # Verify multi-source scraping was NOT called (cache hit)
        # Job posting scrape may happen (intentional), but search shouldn't be called
        mock_firecrawl.search.assert_not_called()

    @patch('src.layer3.company_researcher.create_tracked_llm')
    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_hallucination_controls_in_prompt(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        mock_llm_class
    ):
        """Prompt includes hallucination prevention instructions."""
        from src.layer3.company_researcher import SYSTEM_PROMPT_COMPANY_SIGNALS

        # Verify hallucination controls present in prompt
        # Phase 5.2 prompt uses: "Use ONLY explicit facts from scraped content"
        assert "Use ONLY explicit facts from scraped content" in SYSTEM_PROMPT_COMPANY_SIGNALS
        # Phase 5.2 prompt uses: "NEVER invent details not in sources"
        assert "NEVER invent" in SYSTEM_PROMPT_COMPANY_SIGNALS
        assert "unknown" in SYSTEM_PROMPT_COMPANY_SIGNALS.lower()

    @patch('src.layer3.company_researcher.create_tracked_llm')
    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_signal_type_funding(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        mock_llm_class,
        sample_job_state
    ):
        """Extract funding signal type correctly."""
        funding_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "funding",
                "description": "Raised $100M Series C from Sequoia",
                "date": "2024-06-15",
                "source": "https://techcorp.com/news"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies - use helper for search + scrape
        mock_firecrawl = create_firecrawl_mock("TechCorp raised $100M Series C")
        mock_firecrawl_class.return_value = mock_firecrawl

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(funding_signal_json)
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mock_mongo = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_mongo.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_mongo

        # Run (use_claude_api=False for legacy FireCrawl mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Assert funding signal extracted
        assert result["company_research"]["signals"][0]["type"] == "funding"
        assert "100M" in result["company_research"]["signals"][0]["description"]

    @patch('src.layer3.company_researcher.create_tracked_llm')
    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_signal_type_acquisition(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        mock_llm_class,
        sample_job_state
    ):
        """Extract acquisition signal type correctly."""
        acquisition_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "acquisition",
                "description": "Acquired DataCo for $50M",
                "date": "2024-03-20",
                "source": "https://techcorp.com/news"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies - use helper for search + scrape
        mock_firecrawl = create_firecrawl_mock("TechCorp acquired DataCo")
        mock_firecrawl_class.return_value = mock_firecrawl

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(acquisition_signal_json)
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mock_mongo = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_mongo.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_mongo

        # Run (use_claude_api=False for legacy FireCrawl mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Assert acquisition signal extracted
        assert result["company_research"]["signals"][0]["type"] == "acquisition"
        assert "DataCo" in result["company_research"]["signals"][0]["description"]

    @patch('src.layer3.company_researcher.create_tracked_llm')
    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_signal_type_leadership_change(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        mock_llm_class,
        sample_job_state
    ):
        """Extract leadership_change signal type correctly."""
        leadership_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "leadership_change",
                "description": "Appointed Jane Smith as new CTO",
                "date": "2024-05-10",
                "source": "https://techcorp.com/news"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies - use helper for search + scrape
        mock_firecrawl = create_firecrawl_mock("Jane Smith joins as CTO")
        mock_firecrawl_class.return_value = mock_firecrawl

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(leadership_signal_json)
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mock_mongo = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_mongo.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_mongo

        # Run (use_claude_api=False for legacy FireCrawl mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Assert leadership_change signal extracted
        assert result["company_research"]["signals"][0]["type"] == "leadership_change"
        assert "Jane Smith" in result["company_research"]["signals"][0]["description"]

    @patch('src.layer3.company_researcher.create_tracked_llm')
    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_signal_type_product_launch(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        mock_llm_class,
        sample_job_state
    ):
        """Extract product_launch signal type correctly."""
        product_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "product_launch",
                "description": "Launched new AI-powered analytics platform",
                "date": "2024-04-01",
                "source": "https://techcorp.com/products"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies - use helper for search + scrape
        mock_firecrawl = create_firecrawl_mock("New AI analytics platform launched")
        mock_firecrawl_class.return_value = mock_firecrawl

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(product_signal_json)
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mock_mongo = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_mongo.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_mongo

        # Run (use_claude_api=False for legacy FireCrawl mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Assert product_launch signal extracted
        assert result["company_research"]["signals"][0]["type"] == "product_launch"
        assert "analytics" in result["company_research"]["signals"][0]["description"]

    @patch('src.layer3.company_researcher.create_tracked_llm')
    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_signal_type_partnership(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        mock_llm_class,
        sample_job_state
    ):
        """Extract partnership signal type correctly."""
        partnership_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "partnership",
                "description": "Strategic partnership with AWS announced",
                "date": "2024-02-15",
                "source": "https://techcorp.com/news"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies - use helper for search + scrape
        mock_firecrawl = create_firecrawl_mock("Partnership with AWS")
        mock_firecrawl_class.return_value = mock_firecrawl

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(partnership_signal_json)
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mock_mongo = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_mongo.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_mongo

        # Run (use_claude_api=False for legacy FireCrawl mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Assert partnership signal extracted
        assert result["company_research"]["signals"][0]["type"] == "partnership"
        assert "AWS" in result["company_research"]["signals"][0]["description"]

    @patch('src.layer3.company_researcher.create_tracked_llm')
    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_signal_type_growth(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        mock_llm_class,
        sample_job_state
    ):
        """Extract growth signal type correctly."""
        growth_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "growth",
                "description": "Expanded engineering team by 50%, now 200 engineers",
                "date": "2024-01-10",
                "source": "https://linkedin.com/techcorp"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies - use helper for search + scrape
        mock_firecrawl = create_firecrawl_mock("Team grew to 200 engineers")
        mock_firecrawl_class.return_value = mock_firecrawl

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(growth_signal_json)
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mock_mongo = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_mongo.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_mongo

        # Run (use_claude_api=False for legacy FireCrawl mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Assert growth signal extracted
        assert result["company_research"]["signals"][0]["type"] == "growth"
        assert "200" in result["company_research"]["signals"][0]["description"]

    @patch('src.layer3.company_researcher.create_tracked_llm')
    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_quality_gate_minimum_signals(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        mock_llm_class,
        sample_job_state
    ):
        """Quality gate: Extract ≥3 signals for rich content."""
        rich_signals_json = {
            "summary": "TechCorp is a leading cloud infrastructure provider with 500+ employees.",
            "signals": [
                {
                    "type": "funding",
                    "description": "Raised $100M Series C from Sequoia",
                    "date": "2024-06-15",
                    "source": "https://techcorp.com/news"
                },
                {
                    "type": "acquisition",
                    "description": "Acquired DataCo for $50M",
                    "date": "2024-03-20",
                    "source": "https://techcorp.com/news"
                },
                {
                    "type": "leadership_change",
                    "description": "Appointed Jane Smith as new CTO",
                    "date": "2024-05-10",
                    "source": "https://techcorp.com/about"
                },
                {
                    "type": "product_launch",
                    "description": "Launched AI-powered analytics platform",
                    "date": "2024-04-01",
                    "source": "https://techcorp.com/products"
                }
            ],
            "url": "https://techcorp.com"
        }

        # Mock dependencies - use helper for search + scrape
        mock_firecrawl = create_firecrawl_mock("TechCorp raised $100M, acquired DataCo, Jane Smith CTO, new AI platform")
        mock_firecrawl_class.return_value = mock_firecrawl

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(rich_signals_json)
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mock_mongo = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_mongo.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_mongo

        # Run (use_claude_api=False for legacy FireCrawl mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Quality gate: ≥3 signals for rich content
        assert len(result["company_research"]["signals"]) >= 3
        assert result["company_research"]["signals"][0]["type"] == "funding"
        assert result["company_research"]["signals"][1]["type"] == "acquisition"
        assert result["company_research"]["signals"][2]["type"] == "leadership_change"


# ===== ROLE RESEARCHER TESTS =====

class TestRoleResearcherSchema:
    """Test Pydantic schema validation for Role Researcher."""

    def test_valid_role_research_schema(self, valid_role_research_json):
        """Valid JSON passes schema validation."""
        validated = RoleResearchOutput(**valid_role_research_json)

        assert validated.summary == valid_role_research_json["summary"]
        assert len(validated.business_impact) == 3
        assert validated.why_now == valid_role_research_json["why_now"]

    def test_too_few_business_impact_items_fails(self):
        """Schema validation fails with <3 business_impact items."""
        invalid_data = {
            "summary": "Senior engineer will lead platform team",
            "business_impact": ["Impact 1", "Impact 2"],  # Only 2 items (min is 3)
            "why_now": "Expansion requires scaling"
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            RoleResearchOutput(**invalid_data)

    def test_too_many_business_impact_items_fails(self):
        """Schema validation fails with >5 business_impact items."""
        invalid_data = {
            "summary": "Senior engineer will lead platform team",
            "business_impact": ["Impact 1", "Impact 2", "Impact 3", "Impact 4", "Impact 5", "Impact 6"],  # 6 items (max is 5)
            "why_now": "Expansion requires scaling"
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            RoleResearchOutput(**invalid_data)


class TestRoleResearcherWithMockedLLM:
    """Test Role Researcher with mocked LLM."""

    @patch('src.layer3.role_researcher.FirecrawlApp')
    @patch('src.layer3.role_researcher.create_tracked_llm')
    def test_role_analysis_with_company_signals(
        self,
        mock_llm_class,
        mock_firecrawl_class,
        sample_job_state,
        valid_role_research_json
    ):
        """Role research references company signals in 'why_now'."""
        # Add company signals to job state (from Phase 5.1)
        sample_job_state["company_research"] = {
            "summary": "TechCorp builds cloud infrastructure",
            "signals": [
                {
                    "type": "funding",
                    "description": "Raised $50M Series B",
                    "date": "2024-01-15",
                    "source": "https://techcorp.com/news"
                }
            ],
            "url": "https://techcorp.com"
        }

        # Mock LLM to return valid role research JSON
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(valid_role_research_json)
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        # Run Role Researcher (use_claude_api=False for legacy FireCrawl mode)
        researcher = RoleResearcher(use_claude_api=False)
        result = researcher.research_role(sample_job_state)

        # Assertions
        assert "role_research" in result
        assert result["role_research"]["summary"] == valid_role_research_json["summary"]
        assert len(result["role_research"]["business_impact"]) == 3
        # Verify "why_now" mentions signal context
        assert "funding" in result["role_research"]["why_now"].lower() or "$50m" in result["role_research"]["why_now"].lower()

    @patch('src.layer3.role_researcher.create_tracked_llm')
    def test_hallucination_controls_in_role_prompt(self, mock_llm_class):
        """Role Researcher prompt includes hallucination prevention."""
        from src.layer3.role_researcher import SYSTEM_PROMPT_ROLE_RESEARCH

        # Verify hallucination controls present
        assert "Only use facts" in SYSTEM_PROMPT_ROLE_RESEARCH
        assert "DO NOT invent" in SYSTEM_PROMPT_ROLE_RESEARCH
        assert "explicitly reference" in SYSTEM_PROMPT_ROLE_RESEARCH.lower() or "reference" in SYSTEM_PROMPT_ROLE_RESEARCH.lower()

    @patch('src.layer3.role_researcher.FirecrawlApp')
    @patch('src.layer3.role_researcher.create_tracked_llm')
    def test_role_research_handles_llm_failure_gracefully(
        self,
        mock_llm_class,
        mock_firecrawl_class,
        sample_job_state
    ):
        """Role research handles LLM failures without blocking pipeline."""
        # Mock LLM to raise exception
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM API error")
        mock_llm_class.return_value = mock_llm

        # Run Role Researcher (use_claude_api=False for legacy FireCrawl mode)
        researcher = RoleResearcher(use_claude_api=False)
        result = researcher.research_role(sample_job_state)

        # Should return None but not raise exception
        assert result["role_research"] is None
        assert "errors" in result
        assert any("Role Researcher" in error for error in result["errors"])


# ===== INTEGRATION TESTS =====

@pytest.mark.integration
@patch('src.layer3.company_researcher.create_tracked_llm')
@patch('src.layer3.company_researcher.MongoClient')
@patch('src.layer3.company_researcher.FirecrawlApp')
def test_company_researcher_node_integration(
    mock_firecrawl_class,
    mock_mongo_class,
    mock_llm_class,
    sample_job_state,
    valid_company_research_json
):
    """Integration test for company_researcher_node."""
    # Mock dependencies - use helper for search + scrape
    mock_firecrawl = create_firecrawl_mock("TechCorp is a cloud provider.")
    mock_firecrawl_class.return_value = mock_firecrawl

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps(valid_company_research_json)
    mock_llm.invoke.return_value = mock_response
    mock_llm_class.return_value = mock_llm

    mock_mongo = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = None
    mock_mongo.__getitem__.return_value.__getitem__.return_value = mock_collection
    mock_mongo_class.return_value = mock_mongo

    # Run node function (use_claude_api=False for legacy FireCrawl mode)
    updates = company_researcher_node(sample_job_state, use_claude_api=False)

    # Assertions
    assert "company_research" in updates
    assert updates["company_research"]["summary"] is not None


@pytest.mark.integration
@patch('src.layer3.role_researcher.FirecrawlApp')
@patch('src.layer3.role_researcher.create_tracked_llm')
def test_role_researcher_node_integration(
    mock_llm_class,
    mock_firecrawl_class,
    sample_job_state,
    valid_role_research_json
):
    """Integration test for role_researcher_node."""
    # Mock LLM
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps(valid_role_research_json)
    mock_llm.invoke.return_value = mock_response
    mock_llm_class.return_value = mock_llm

    # Run node function (use_claude_api=False for legacy FireCrawl mode)
    updates = role_researcher_node(sample_job_state, use_claude_api=False)

    # Assertions
    assert "role_research" in updates
    assert updates["role_research"]["summary"] is not None
    assert len(updates["role_research"]["business_impact"]) >= 3


# ===== FIRECRAWL NORMALIZER TESTS =====

class TestFireCrawlNormalizer:
    """Test FireCrawl response normalizer across SDK versions."""

    def test_normalizer_with_new_sdk_web_attribute(self):
        """Normalizer extracts results from new SDK (v4.8.0+) with .web attribute."""
        from src.layer3.company_researcher import _extract_search_results

        # Mock SearchData with .web attribute (new SDK)
        mock_response = Mock()
        mock_result = Mock()
        mock_result.url = "https://example.com"
        mock_result.markdown = "Test content"
        mock_response.web = [mock_result]

        results = _extract_search_results(mock_response)

        assert len(results) == 1
        assert results[0].url == "https://example.com"
        assert results[0].markdown == "Test content"

    def test_normalizer_with_old_sdk_data_attribute(self):
        """Normalizer extracts results from old SDK with .data attribute."""
        from src.layer3.company_researcher import _extract_search_results

        # Mock SearchData with .data attribute (old SDK)
        mock_response = Mock()
        mock_result = Mock()
        mock_result.url = "https://oldapi.com"
        mock_result.markdown = "Old SDK content"
        mock_response.data = [mock_result]
        # Explicitly set web to None to simulate old SDK
        mock_response.web = None

        results = _extract_search_results(mock_response)

        assert len(results) == 1
        assert results[0].url == "https://oldapi.com"
        assert results[0].markdown == "Old SDK content"

    def test_normalizer_with_dict_web_key(self):
        """Normalizer handles dict response with 'web' key."""
        from src.layer3.company_researcher import _extract_search_results

        # Dict shape with "web" key
        mock_response = {
            "web": [
                {"url": "https://dict.com", "markdown": "Dict content"}
            ]
        }

        results = _extract_search_results(mock_response)

        assert len(results) == 1
        assert results[0]["url"] == "https://dict.com"

    def test_normalizer_with_dict_data_key(self):
        """Normalizer handles dict response with 'data' key (fallback)."""
        from src.layer3.company_researcher import _extract_search_results

        # Dict shape with "data" key
        mock_response = {
            "data": [
                {"url": "https://legacy.com", "markdown": "Legacy content"}
            ]
        }

        results = _extract_search_results(mock_response)

        assert len(results) == 1
        assert results[0]["url"] == "https://legacy.com"

    def test_normalizer_with_bare_list(self):
        """Normalizer handles bare list response."""
        from src.layer3.company_researcher import _extract_search_results

        # Bare list shape
        mock_response = [
            {"url": "https://bare1.com", "markdown": "Item 1"},
            {"url": "https://bare2.com", "markdown": "Item 2"}
        ]

        results = _extract_search_results(mock_response)

        assert len(results) == 2
        assert results[0]["url"] == "https://bare1.com"
        assert results[1]["url"] == "https://bare2.com"

    def test_normalizer_with_none_response(self):
        """Normalizer returns empty list for None response."""
        from src.layer3.company_researcher import _extract_search_results

        results = _extract_search_results(None)

        assert results == []

    def test_normalizer_with_empty_results(self):
        """Normalizer returns empty list when no results present."""
        from src.layer3.company_researcher import _extract_search_results

        # Mock response with empty web
        mock_response = Mock()
        mock_response.web = []

        results = _extract_search_results(mock_response)

        assert results == []

    def test_normalizer_prioritizes_web_over_data(self):
        """Normalizer prefers .web over .data when both present."""
        from src.layer3.company_researcher import _extract_search_results

        # Mock response with both .web and .data
        mock_response = Mock()
        mock_web_result = Mock()
        mock_web_result.url = "https://web.com"
        mock_response.web = [mock_web_result]

        mock_data_result = Mock()
        mock_data_result.url = "https://data.com"
        mock_response.data = [mock_data_result]

        results = _extract_search_results(mock_response)

        # Should return .web results, not .data
        assert len(results) == 1
        assert results[0].url == "https://web.com"

    def test_normalizer_in_role_researcher(self):
        """Role researcher normalizer works identically."""
        from src.layer3.role_researcher import _extract_search_results

        # Mock new SDK response
        mock_response = Mock()
        mock_result = Mock()
        mock_result.url = "https://role.com"
        mock_response.web = [mock_result]

        results = _extract_search_results(mock_response)

        assert len(results) == 1
        assert results[0].url == "https://role.com"

    def test_normalizer_in_people_mapper(self):
        """People mapper normalizer works identically."""
        from src.layer5.people_mapper import _extract_search_results

        # Mock new SDK response
        mock_response = Mock()
        mock_result = Mock()
        mock_result.url = "https://linkedin.com/people"
        mock_response.web = [mock_result]

        results = _extract_search_results(mock_response)

        assert len(results) == 1
        assert results[0].url == "https://linkedin.com/people"


# ===== PHASE 5 ENHANCEMENT TESTS (Fallback & STAR-awareness) =====

class TestCompanyResearcherFallback:
    """Tests for Phase 5 defensive fallback when multi-source scrape yields 0 signals."""

    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    @patch.object(CompanyResearcher, '_check_cache')
    @patch.object(CompanyResearcher, '_scrape_job_posting')
    @patch.object(CompanyResearcher, '_scrape_multiple_sources')
    @patch.object(CompanyResearcher, '_analyze_company_signals')
    @patch.object(CompanyResearcher, '_fallback_signal_extraction')
    def test_fallback_triggered_on_empty_signals(
        self,
        mock_fallback,
        mock_analyze,
        mock_scrape_multi,
        mock_scrape_job,
        mock_cache,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state
    ):
        """Fallback is triggered when LLM returns 0 signals."""
        # Setup mocks
        mock_cache.return_value = None  # Cache miss
        mock_scrape_job.return_value = None
        mock_scrape_multi.return_value = {
            "official_site": {"url": "https://techcorp.com", "content": "TechCorp is a tech company."}
        }

        # First analysis returns empty signals
        mock_analyze.return_value = CompanyResearchOutput(
            summary="TechCorp is a tech company.",
            signals=[],
            url="https://techcorp.com"
        )

        # Fallback returns at least one signal
        mock_fallback.return_value = CompanyResearchOutput(
            summary="TechCorp is a tech company.",
            signals=[CompanySignalModel(
                type="growth",
                description="TechCorp operates in the tech industry",
                date="unknown",
                source="https://techcorp.com"
            )],
            url="https://techcorp.com"
        )

        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Verify fallback was called
        mock_fallback.assert_called_once()
        assert result["company_research"]["signals"]
        assert len(result["company_research"]["signals"]) >= 1

    @patch.object(CompanyResearcher, '__init__')
    def test_fallback_extraction_produces_signal(self, mock_init):
        """_fallback_signal_extraction always produces at least one signal."""
        mock_init.return_value = None

        researcher = CompanyResearcher.__new__(CompanyResearcher)
        researcher.llm = Mock()
        researcher.logger = Mock()  # Added for logging migration

        # Mock LLM response with valid JSON
        mock_response = Mock()
        mock_response.content = json.dumps({
            "summary": "TechCorp builds software.",
            "signals": [{"type": "growth", "description": "Software company", "date": "unknown", "source": "https://techcorp.com"}],
            "url": "https://techcorp.com"
        })
        researcher.llm.invoke.return_value = mock_response

        result = researcher._fallback_signal_extraction(
            "TechCorp",
            {"url": "https://techcorp.com", "content": "TechCorp builds software."}
        )

        assert result.signals
        assert len(result.signals) >= 1
        assert result.signals[0].source == "https://techcorp.com"

    @patch.object(CompanyResearcher, '__init__')
    def test_fallback_creates_minimal_signal_on_parse_failure(self, mock_init):
        """Fallback creates minimal valid output even if LLM response is unparseable."""
        mock_init.return_value = None

        researcher = CompanyResearcher.__new__(CompanyResearcher)
        researcher.llm = Mock()
        researcher.logger = Mock()  # Added for logging migration

        # Mock LLM response with invalid JSON
        mock_response = Mock()
        mock_response.content = "This is not valid JSON"
        researcher.llm.invoke.return_value = mock_response

        result = researcher._fallback_signal_extraction(
            "TechCorp",
            {"url": "https://techcorp.com", "content": "TechCorp builds software."}
        )

        # Should return minimal valid output
        assert result.summary
        assert result.signals
        assert len(result.signals) >= 1
        assert result.url == "https://techcorp.com"


class TestSTARAwareness:
    """Tests for Phase 5 STAR-aware research prompts."""

    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_extract_star_context_with_selected_stars(self, mock_firecrawl_class, mock_mongo_class, sample_job_state):
        """STAR context extraction works with selected_stars."""
        # Add selected_stars to state
        sample_job_state["selected_stars"] = [
            {
                "id": "star-1",
                "company": "OldCorp",
                "role_title": "Engineer",
                "domain_areas": ["Cloud Infrastructure", "Platform Engineering"],
                "outcome_types": ["Cost Reduction", "Operational Efficiency"]
            },
            {
                "id": "star-2",
                "company": "AnotherCorp",
                "role_title": "Lead Engineer",
                "domain_areas": ["Platform Engineering", "DevOps"],
                "outcome_types": ["Velocity/Speed", "Cost Reduction"]
            }
        ]

        researcher = CompanyResearcher(use_claude_api=False)
        domains, outcomes = researcher._extract_star_context(sample_job_state)

        assert domains is not None
        assert "Cloud Infrastructure" in domains
        assert "Platform Engineering" in domains
        assert "DevOps" in domains

        assert outcomes is not None
        assert "Cost Reduction" in outcomes
        assert "Operational Efficiency" in outcomes
        assert "Velocity/Speed" in outcomes

    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    def test_extract_star_context_returns_none_without_stars(self, mock_firecrawl_class, mock_mongo_class, sample_job_state):
        """STAR context extraction returns None when no selected_stars."""
        researcher = CompanyResearcher(use_claude_api=False)
        domains, outcomes = researcher._extract_star_context(sample_job_state)

        assert domains is None
        assert outcomes is None

    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    @patch.object(CompanyResearcher, '_check_cache')
    @patch.object(CompanyResearcher, '_scrape_job_posting')
    @patch.object(CompanyResearcher, '_scrape_multiple_sources')
    @patch.object(CompanyResearcher, '_analyze_company_signals')
    @patch.object(CompanyResearcher, '_store_cache')
    def test_star_context_passed_to_analysis(
        self,
        mock_store,
        mock_analyze,
        mock_scrape_multi,
        mock_scrape_job,
        mock_cache,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state
    ):
        """STAR context is passed to _analyze_company_signals."""
        # Add selected_stars to state
        sample_job_state["selected_stars"] = [
            {
                "id": "star-1",
                "company": "OldCorp",
                "role_title": "Engineer",
                "domain_areas": ["Cloud Infrastructure"],
                "outcome_types": ["Cost Reduction"]
            }
        ]

        mock_cache.return_value = None
        mock_scrape_job.return_value = None
        mock_scrape_multi.return_value = {
            "official_site": {"url": "https://techcorp.com", "content": "Content"}
        }
        mock_analyze.return_value = CompanyResearchOutput(
            summary="TechCorp is a technology company with strong growth signals.",
            signals=[CompanySignalModel(type="growth", description="Company expanding rapidly", date="unknown", source="https://techcorp.com")],
            url="https://techcorp.com"
        )

        researcher = CompanyResearcher(use_claude_api=False)
        researcher.research_company(sample_job_state)

        # Verify _analyze_company_signals was called with STAR context
        mock_analyze.assert_called_once()
        call_kwargs = mock_analyze.call_args[1]
        assert "star_domains" in call_kwargs
        assert "star_outcomes" in call_kwargs
        assert "Cloud Infrastructure" in call_kwargs["star_domains"]
        assert "Cost Reduction" in call_kwargs["star_outcomes"]


class TestRoleResearcherSTARAwareness:
    """Tests for STAR-awareness in Role Researcher."""

    @patch('src.layer3.role_researcher.FirecrawlApp')
    def test_extract_star_context_in_role_researcher(self, mock_firecrawl_class, sample_job_state):
        """Role researcher extracts STAR context correctly."""
        sample_job_state["selected_stars"] = [
            {
                "id": "star-1",
                "company": "OldCorp",
                "role_title": "Engineer",
                "domain_areas": ["Platform Engineering"],
                "outcome_types": ["Revenue Growth"]
            }
        ]

        researcher = RoleResearcher(use_claude_api=False)
        domains, outcomes = researcher._extract_star_context(sample_job_state)

        assert "Platform Engineering" in domains
        assert "Revenue Growth" in outcomes


class TestPhase5Integration:
    """Integration tests for Phase 5 (Company & Role Research)."""

    @patch('src.layer3.company_researcher.MongoClient')
    @patch('src.layer3.company_researcher.FirecrawlApp')
    @patch.object(CompanyResearcher, '_check_cache')
    @patch.object(CompanyResearcher, '_scrape_job_posting')
    @patch.object(CompanyResearcher, '_scrape_multiple_sources')
    @patch.object(CompanyResearcher, '_store_cache')
    @patch('src.layer3.company_researcher.create_tracked_llm')
    def test_company_researcher_produces_valid_output(
        self,
        mock_llm_class,
        mock_store,
        mock_scrape_multi,
        mock_scrape_job,
        mock_cache,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state
    ):
        """Company researcher produces valid schema output with signals."""
        mock_cache.return_value = None
        mock_scrape_job.return_value = None
        mock_scrape_multi.return_value = {
            "official_site": {"url": "https://techcorp.com", "content": "TechCorp is a cloud infrastructure company."}
        }

        # Mock LLM
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = json.dumps({
            "summary": "TechCorp is a cloud infrastructure company.",
            "signals": [
                {"type": "growth", "description": "Cloud infrastructure provider", "date": "unknown", "source": "https://techcorp.com"}
            ],
            "url": "https://techcorp.com"
        })
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Verify schema compliance
        assert "company_research" in result
        assert result["company_research"]["summary"]
        assert result["company_research"]["signals"]
        assert len(result["company_research"]["signals"]) >= 1
        assert result["company_research"]["url"]

        # Verify signals have required fields
        for signal in result["company_research"]["signals"]:
            assert "type" in signal
            assert "description" in signal
            assert "source" in signal

    @patch('src.layer3.role_researcher.create_tracked_llm')
    @patch('src.layer3.role_researcher.FirecrawlApp')
    def test_role_researcher_produces_valid_output(
        self,
        mock_firecrawl_class,
        mock_llm_class,
        sample_job_state
    ):
        """Role researcher produces valid schema output with business impact."""
        # Setup state with company_research
        sample_job_state["company_research"] = {
            "summary": "TechCorp is a cloud company.",
            "signals": [{"type": "funding", "description": "Raised $50M", "date": "2024-01", "source": "https://techcorp.com"}],
            "url": "https://techcorp.com"
        }

        # Mock LLM
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = json.dumps({
            "summary": "Senior engineer leads platform team.",
            "business_impact": [
                "Enable 10x user growth",
                "Reduce costs by 30%",
                "Accelerate feature delivery"
            ],
            "why_now": "Recent funding requires scaling infrastructure."
        })
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        # Mock FireCrawl (to skip role context scraping)
        mock_firecrawl = Mock()
        mock_firecrawl.search.return_value = None
        mock_firecrawl_class.return_value = mock_firecrawl

        researcher = RoleResearcher(use_claude_api=False)
        result = researcher.research_role(sample_job_state)

        # Verify schema compliance
        assert "role_research" in result
        assert result["role_research"]["summary"]
        assert result["role_research"]["business_impact"]
        assert len(result["role_research"]["business_impact"]) >= 3
        assert result["role_research"]["why_now"]
